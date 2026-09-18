from __future__ import annotations

import logging
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, Self

from kyth.changes import ChangeSet, classify_batch
from kyth.model import ChildState, ChildStatus, DevelopmentState, FileBatch
from kyth.process.manager import ChildProcess
from kyth.process.socket import DEFAULT_BACKLOG, bind_listening_socket
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


class Supervisor:
    """Long-lived owner of the public socket and restartable application child."""

    def __init__(self, config: SupervisorConfig, *, process_context: SpawnContext | None = None) -> None:
        """Initialize supervisor state without binding resources yet."""
        self.config = config
        self.state = DevelopmentState()
        self._process_context = process_context
        self._socket: socket.socket | None = None
        self._child: ChildProcess | None = None

    @property
    def address(self) -> tuple[str, int]:
        sock = self._require_socket()
        host, port = sock.getsockname()[:2]
        return str(host), int(port)

    @property
    def socket_fileno(self) -> int:
        return self._require_socket().fileno()

    def open(self) -> None:
        if self._socket is not None:
            return
        self._socket = bind_listening_socket(self.config.host, self.config.port, backlog=self.config.backlog)
        logger.info("listening on %s:%d", *self.address)

    def start_child(self) -> bool:
        listening_socket = self._require_socket()
        if self._child is not None:
            msg = "cannot start a child while another child is owned"
            raise RuntimeError(msg)

        child = ChildProcess(context=self._process_context)
        child.start(self.config.app_target, listening_socket)
        self._child = child
        self.state = replace(self.state, child=ChildState(ChildStatus.STARTING, pid=child.pid))

        result = child.wait_for_startup(self.config.startup_timeout)
        if result.ready:
            generation = self.state.generation + 1
            self.state = DevelopmentState(generation, ChildState(ChildStatus.READY, pid=child.pid))
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

    def restart_child(self) -> bool:
        self.stop_child()
        return self.start_child()

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
        if self._child is not None:
            self.stop_child()
        if self._socket is not None:
            self._socket.close()
            self._socket = None

    def __enter__(self) -> Self:
        """Open the supervisor-owned listening socket."""
        self.open()
        return self

    def __exit__(
        self,
        _exc_type: type[BaseException] | None,
        _exc_value: BaseException | None,
        _traceback: TracebackType | None,
    ) -> None:
        """Release the child and listening socket when leaving the context."""
        self.close()

    def _handle_change_cycle(self, initial_batch: FileBatch, source: BatchSource) -> None:
        batch = initial_batch
        while True:
            changes = classify_batch(batch)
            self._log_change_set(changes)
            if not changes.requires_restart:
                return

            self.restart_child()
            pending = source.drain_pending()
            if pending is None:
                return
            batch = pending

    def _create_watcher(self) -> FileWatcher:
        roots = self.config.watch_roots or (Path.cwd(),)
        return FileWatcher(
            WatcherConfig(
                roots=roots,
                ignored_paths=self.config.ignored_paths,
                debounce_ms=self.config.watch_debounce_ms,
                step_ms=self.config.watch_step_ms,
            )
        )

    def _log_change_set(self, changes: ChangeSet) -> None:
        rendered = ", ".join(_display_path(path) for path in changes.batch.paths)
        if changes.requires_restart:
            logger.info("%s changed -> restart", rendered)
            if changes.browser_paths:
                logger.info("browser-facing changes in this batch are deferred until the browser control phase")
            return

        if changes.browser_paths:
            logger.info("%s changed -> browser-facing change; no Phase 2 browser action", rendered)
            return

        logger.info("%s changed -> no restart", rendered)

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


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(Path.cwd()))
    except ValueError:
        return str(path)
