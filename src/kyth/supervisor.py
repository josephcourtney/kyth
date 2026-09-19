from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, Self

from kyth.changes import ChangePolicy, ChangeSet, classify_batch
from kyth.control import ControlService
from kyth.invalidation import BrowserActionKind, BrowserUpdateDecision, decide_browser_updates
from kyth.model import ChildState, ChildStatus, DevelopmentState, FileBatch, FileOperation
from kyth.process.manager import ChildProcess
from kyth.process.socket import DEFAULT_BACKLOG, bind_listening_socket
from kyth.protocol import ControlEvent
from kyth.provenance import (
    DirectOutputIndex,
    DirectResourceIndex,
    GeneratedManifestIndex,
    ManifestError,
    RenderProvenanceIndex,
)
from kyth.watcher import BatchSource, FileWatcher, WatcherConfig

if TYPE_CHECKING:
    import socket
    from multiprocessing.context import SpawnContext
    from types import TracebackType

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class SupervisorConfig:
    app_target: str
    host: str = "127.0.0.1"
    port: int = 8000
    backlog: int = DEFAULT_BACKLOG
    startup_timeout: float = 10.0
    shutdown_timeout: float = 2.0
    terminate_timeout: float = 1.0
    watch_roots: tuple[Path, ...] = ()
    ignored_paths: tuple[Path, ...] = ()
    watch_debounce_ms: int = 300
    watch_step_ms: int = 50
    control_port: int = 0
    view_inactivity_timeout: float = 300.0
    generation_update_timeout: float = 2.0
    manifest_paths: tuple[Path, ...] = ()
    restart_patterns: tuple[str, ...] = ()


class Supervisor:
    """Long-lived owner of the public socket, control plane, and application child."""

    def __init__(self, config: SupervisorConfig, *, process_context: SpawnContext | None = None) -> None:
        """Initialize supervisor state without binding resources yet."""
        self.config = config
        self.state = DevelopmentState()
        self._process_context = process_context
        self._socket: socket.socket | None = None
        self._child: ChildProcess | None = None
        self._control: ControlService | None = None
        roots = _development_roots(config)
        self._direct_outputs = DirectOutputIndex(roots)
        self._direct_resources = DirectResourceIndex(roots)
        self._render_provenance = RenderProvenanceIndex()
        self._generated = GeneratedManifestIndex(config.manifest_paths)
        self._change_policy = ChangePolicy(config.restart_patterns)

    @property
    def address(self) -> tuple[str, int]:
        sock = self._require_socket()
        host, port = sock.getsockname()[:2]
        return str(host), int(port)

    @property
    def socket_fileno(self) -> int:
        return self._require_socket().fileno()

    @property
    def control_address(self) -> tuple[str, int]:
        return self._require_control().address

    @property
    def control_token(self) -> str:
        return self._require_control().token

    def open(self) -> None:
        if self._socket is not None:
            return

        self._generated.load_all()
        app_socket = bind_listening_socket(self.config.host, self.config.port, backlog=self.config.backlog)
        control: ControlService | None = None
        try:
            control = ControlService(
                port=self.config.control_port,
                generation=self.state.generation,
                inactivity_timeout=self.config.view_inactivity_timeout,
            )
            control.start()
        except Exception:
            if control is not None:
                control.close()
            app_socket.close()
            raise

        self._socket = app_socket
        self._control = control
        logger.info("application listening on %s:%d", *self.address)
        logger.info("control plane listening on %s:%d", *self.control_address)

    def start_child(self) -> bool:
        return self._start_child(reload_browsers=False)

    def restart_child(self) -> bool:
        self.stop_child()
        return self._start_child(reload_browsers=True)

    def stop_child(self) -> None:
        if self._child is None:
            if self.state.child.status is not ChildStatus.FAILED:
                self.state = replace(self.state, child=ChildState())
            return

        pid = self._child.pid
        self.state = replace(self.state, child=ChildState(ChildStatus.STOPPING, pid=pid))
        exit_code = self._child.stop(
            grace_timeout=self.config.shutdown_timeout,
            terminate_timeout=self.config.terminate_timeout,
        )
        self._child = None
        self.state = replace(self.state, child=ChildState(ChildStatus.ABSENT, exit_code=exit_code))

    def poll(self) -> None:
        self._refresh_provenance()
        if self._child is None or self.state.child.status is not ChildStatus.READY or self._child.is_alive:
            return
        exit_code = self._child.exit_code
        self._child.close()
        self._child = None
        self.state = replace(
            self.state,
            child=ChildState(ChildStatus.FAILED, error="application child exited", exit_code=exit_code),
        )

    def run_forever(self, *, poll_interval: float = 0.1, batch_source: BatchSource | None = None) -> None:
        source = batch_source or self._create_watcher()
        source.start()
        try:
            if self._child is None:
                self.start_child()
                pending = source.drain_pending()
                if pending is not None:
                    self._handle_change_cycle(pending, source)

            while True:
                self.poll()
                batch = source.next_batch(timeout=poll_interval)
                if batch is not None:
                    self._handle_change_cycle(batch, source)
        finally:
            source.close()

    def close(self) -> None:
        child_error: Exception | None = None
        control_error: Exception | None = None
        try:
            if self._child is not None:
                self.stop_child()
        except Exception as exc:  # ruff: ignore[blind-except] - cleanup must continue before re-raising child failure
            child_error = exc

        try:
            if self._control is not None:
                self._control.close()
        except Exception as exc:  # ruff: ignore[blind-except] - application socket must still be released
            control_error = exc
        finally:
            self._control = None
            if self._socket is not None:
                self._socket.close()
                self._socket = None

        if child_error is not None:
            if control_error is not None:
                child_error.add_note(f"control cleanup also failed: {control_error}")
            raise child_error
        if control_error is not None:
            raise control_error

    def __enter__(self) -> Self:
        """Open supervisor-owned application and control-plane sockets."""
        self.open()
        return self

    def __exit__(
        self,
        _exc_type: type[BaseException] | None,
        _exc_value: BaseException | None,
        _traceback: TracebackType | None,
    ) -> None:
        """Release the child and supervisor-owned sockets."""
        self.close()

    def _start_child(self, *, reload_browsers: bool, commit_control: bool = True) -> bool:
        listening_socket = self._require_socket()
        if self._child is not None:
            msg = "cannot start a child while another child is owned"
            raise RuntimeError(msg)

        control = self._require_control()
        generation = self.state.generation + 1
        control_host, control_port = control.address
        child = ChildProcess(context=self._process_context)
        child.start(
            self.config.app_target,
            listening_socket,
            control_url=f"http://{control_host}:{control_port}",
            control_token=control.token,
            generation=generation,
        )
        self._child = child
        self.state = replace(self.state, child=ChildState(ChildStatus.STARTING, pid=child.pid))

        result = child.wait_for_startup(self.config.startup_timeout)
        if result.ready:
            self.state = DevelopmentState(generation, ChildState(ChildStatus.READY, pid=child.pid))
            if commit_control:
                control.set_generation(generation)
                if reload_browsers:
                    control.publish(ControlEvent.reload(generation, reason="server-restart"))
            logger.info("child %s ready; generation %d", child.pid, generation)
            return True

        error = result.error or "application startup failed"
        exit_code = self._stop_owned_child_if_needed()
        self.state = replace(
            self.state,
            child=ChildState(
                ChildStatus.FAILED,
                error=error,
                exit_code=result.exit_code if result.exit_code is not None else exit_code,
            ),
        )
        logger.error("application startup failed: %s", error)
        return False

    def _handle_change_cycle(self, initial_batch: FileBatch, source: BatchSource) -> None:
        batch = initial_batch
        while True:
            self._refresh_provenance()
            self._refresh_changed_manifests(batch.paths)
            stale_outputs = self._generated.mark_sources_changed(batch.paths)
            changes = classify_batch(batch, policy=self._change_policy)
            relevant_paths = self._relevant_browser_paths(changes)
            self._log_change_set(changes, relevant_paths, stale_outputs)
            self._generated.mark_outputs_updated(relevant_paths)

            if changes.requires_restart:
                self._restart_for_change_cycle()
            elif relevant_paths:
                self._reload_for_browser_change(relevant_paths)
            else:
                return

            pending = source.drain_pending()
            if pending is None:
                return
            batch = pending

    def _restart_for_change_cycle(self) -> None:
        """Replace the child, then synchronize only views whose served state is ready."""
        self.stop_child()
        if not self._start_child(reload_browsers=False, commit_control=False):
            return

        control = self._require_control()
        generation = self.state.generation
        deferred_view_ids = self._stale_generated_view_ids()
        if deferred_view_ids:
            control.mark_views_current(deferred_view_ids, generation)
        control.set_generation(generation)
        if deferred_view_ids:
            control.publish(
                ControlEvent.sync(generation, reload_required=False),
                view_ids=deferred_view_ids,
            )

        active_view_ids = {view.view_id for view in control.views.snapshot()}
        reload_view_ids = tuple(sorted(active_view_ids - set(deferred_view_ids)))
        if reload_view_ids:
            control.publish(
                ControlEvent.reload(generation, reason="server-restart"),
                view_ids=reload_view_ids,
            )
        logger.info(
            "replacement child ready; generation %d; %d view(s) reloaded; %d generated view(s) deferred",
            generation,
            len(reload_view_ids),
            len(deferred_view_ids),
        )

    def _stale_generated_view_ids(self) -> tuple[str, ...]:
        control = self._require_control()
        views = control.views.snapshot()
        output_views = self._generated.output_views({view.view_id: view.url for view in views if view.url})
        stale_outputs = self._generated.stale_outputs
        return tuple(
            sorted({view_id for output, view_ids in output_views.items() if output in stale_outputs for view_id in view_ids})
        )

    def _reload_for_browser_change(self, changed_paths: tuple[Path, ...]) -> None:
        if self._child is None or self.state.child.status is not ChildStatus.READY or self._control is None:
            logger.info("browser-facing change deferred because no application child is ready")
            return

        decision = self._browser_updates(changed_paths)
        generation = self.state.generation + 1
        try:
            self._child.set_generation(
                generation,
                timeout=self.config.generation_update_timeout,
            )
        except RuntimeError:
            logger.warning("child generation update failed; restarting application before browser reload")
            self.restart_child()
            return

        if decision.current_view_ids:
            self._control.mark_views_current(decision.current_view_ids, generation)
        self.state = replace(self.state, generation=generation)
        self._control.set_generation(generation)
        self._publish_browser_decision(decision, generation)
        action_counts = {
            kind.value: sum(action.kind is kind for action in decision.actions) for kind in BrowserActionKind
        }
        logger.info(
            "browser-facing state ready; generation %d; reason=%s; actions=%s",
            generation,
            decision.reason,
            action_counts,
        )

    def _browser_updates(self, changed_paths: tuple[Path, ...]) -> BrowserUpdateDecision:
        self._refresh_provenance()
        control = self._require_control()
        views = control.views.snapshot()
        normalized = tuple(self._direct_outputs.normalize_changed_path(path) for path in changed_paths)
        generated_output_views = self._generated.output_views({view.view_id: view.url for view in views if view.url})
        output_views = self._combined_output_views(generated_output_views)
        return decide_browser_updates(
            normalized,
            known_outputs=self._direct_outputs.known_outputs | self._generated.known_outputs,
            output_views=output_views,
            known_render_sources=self._render_provenance.known_sources,
            render_source_views=self._render_provenance.stale_source_views(normalized),
            complete_render_view_ids=self._render_provenance.complete_view_ids,
            deferred_source_views=self._generated_source_views(generated_output_views),
            known_resources=self._direct_resources.known_resources,
            resource_views=self._direct_resources.resource_views,
            complete_resource_view_ids=self._direct_resources.complete_view_ids,
            active_view_ids=tuple(view.view_id for view in views),
        )

    def _publish_browser_decision(
        self,
        decision: BrowserUpdateDecision,
        generation: int,
    ) -> None:
        control = self._require_control()
        if decision.current_view_ids:
            control.publish(
                ControlEvent.sync(generation, reload_required=False),
                view_ids=decision.current_view_ids,
            )

        for action in decision.actions:
            if action.kind is BrowserActionKind.RELOAD:
                event = ControlEvent.reload(generation, reason=decision.reason)
            elif action.kind is BrowserActionKind.CSS_UPDATE:
                event = ControlEvent.css_update(generation, resources=action.resource_urls)
            else:
                event = ControlEvent.asset_update(generation, resources=action.resource_urls)
            control.publish(event, view_ids=(action.view_id,))

    def _refresh_provenance(self) -> None:
        if self._control is None:
            return
        views = self._control.views.snapshot()
        view_urls = {view.view_id: view.url for view in views if view.url}
        self._direct_outputs.reconcile(view_urls)
        self._direct_resources.reconcile(
            {view.view_id: view.resources for view in views},
            complete_view_ids=tuple(view.view_id for view in views if view.resources_complete is True),
        )
        self._render_provenance.reconcile(
            self._control.renders.snapshot(),
            {view.view_id: view.render_id for view in views if view.render_id is not None},
        )

    def _combined_output_views(
        self,
        generated_output_views: dict[Path, tuple[str, ...]],
    ) -> dict[Path, tuple[str, ...]]:
        combined = {output: set(view_ids) for output, view_ids in self._direct_outputs.output_views.items()}
        for output, view_ids in generated_output_views.items():
            combined.setdefault(output, set()).update(view_ids)
        return {output: tuple(sorted(view_ids)) for output, view_ids in combined.items()}

    def _generated_source_views(
        self,
        generated_output_views: dict[Path, tuple[str, ...]],
    ) -> dict[Path, tuple[str, ...]]:
        return {
            source: tuple(
                sorted({view_id for output in outputs for view_id in generated_output_views.get(output, ())})
            )
            for source, outputs in self._generated.source_outputs.items()
        }

    def _relevant_browser_paths(self, changes: ChangeSet) -> tuple[Path, ...]:
        manifest_paths = self._generated.manifest_paths
        manifest_sources = self._generated.known_sources
        render_sources = self._render_provenance.known_sources
        direct_outputs = self._direct_outputs.known_outputs
        direct_resources = self._direct_resources.known_resources

        relevant: set[Path] = set()
        for path in changes.batch.paths:
            normalized = self._direct_outputs.normalize_changed_path(path)
            if normalized in manifest_paths:
                continue
            if normalized in self._generated.known_outputs and not self._generated_output_ready(
                changes.batch,
                normalized,
            ):
                continue
            if normalized in render_sources:
                relevant.add(path)
                continue
            if normalized in manifest_sources and normalized not in direct_outputs | direct_resources:
                continue
            if path in changes.browser_paths:
                relevant.add(path)
        return tuple(sorted(relevant, key=Path.as_posix))

    def _generated_output_ready(self, batch: FileBatch, output: Path) -> bool:
        return any(
            self._direct_outputs.normalize_changed_path(event.path) == output
            and event.operation is not FileOperation.DELETED
            for event in batch.events
        )

    def _refresh_changed_manifests(self, changed_paths: tuple[Path, ...]) -> None:
        try:
            reloaded = self._generated.reload_changed(changed_paths)
        except (ManifestError, TypeError):
            logger.exception("generated dependency manifest reload failed")
            return
        if reloaded:
            logger.info(
                "reloaded generated dependency manifest(s): %s",
                ", ".join(str(path) for path in reloaded),
            )

    def _create_watcher(self) -> FileWatcher:
        return FileWatcher(
            WatcherConfig(
                roots=_development_roots(self.config),
                ignored_paths=self.config.ignored_paths,
                debounce_ms=self.config.watch_debounce_ms,
                step_ms=self.config.watch_step_ms,
            )
        )

    @staticmethod
    def _log_change_set(
        changes: ChangeSet,
        relevant_paths: tuple[Path, ...],
        stale_outputs: tuple[Path, ...],
    ) -> None:
        rendered = ", ".join(_display_path(path) for path in changes.batch.paths)
        if changes.requires_restart:
            logger.info("%s changed -> restart then browser reload", rendered)
            return
        if relevant_paths:
            logger.info("%s changed -> browser invalidation", rendered)
            return
        if stale_outputs:
            logger.info(
                "%s changed -> %d generated output(s) stale; waiting for rebuild",
                rendered,
                len(stale_outputs),
            )
            return
        logger.info("%s changed -> no action", rendered)

    def _stop_owned_child_if_needed(self) -> int | None:
        if self._child is None:
            return None
        exit_code = self._child.exit_code
        if self._child.is_alive:
            exit_code = self._child.stop(
                grace_timeout=self.config.shutdown_timeout,
                terminate_timeout=self.config.terminate_timeout,
            )
        else:
            self._child.close()
        self._child = None
        return exit_code

    def _require_socket(self) -> socket.socket:
        if self._socket is None:
            msg = "supervisor socket is not open"
            raise RuntimeError(msg)
        return self._socket

    def _require_control(self) -> ControlService:
        if self._control is None:
            msg = "control service is not open"
            raise RuntimeError(msg)
        return self._control


def _development_roots(config: SupervisorConfig) -> tuple[Path, ...]:
    roots = [path.expanduser().resolve(strict=False) for path in (config.watch_roots or (Path.cwd(),))]
    for manifest_path in config.manifest_paths:
        parent = manifest_path.expanduser().resolve(strict=False).parent
        if not any(parent.is_relative_to(root) for root in roots):
            roots.append(parent)
    return tuple(roots)


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(Path.cwd()))
    except ValueError:
        return str(path)
