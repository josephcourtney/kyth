from __future__ import annotations

import asyncio
import contextlib
import fnmatch
import json
import os
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Protocol

from starlette.websockets import WebSocket, WebSocketDisconnect
from watchfiles import Change, awatch

from kyth.constants import (
    DEBOUNCE_SECONDS,
    GLOB_CHARS,
    IGNORED_DIR_NAMES,
    SHUTDOWN_GRACE_SECONDS,
    WATCH_EXTENSIONS,
)
from kyth.logging import eprint, info


class Broadcaster(Protocol):
    async def broadcast(self, message: dict[str, object]) -> None: ...


def path_is_within(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    else:
        return True


def should_restart(_change: Change, path: str) -> bool:
    p = Path(path)
    return p.suffix == ".py" and "__pycache__" not in p.parts and ".git" not in p.parts


def normalize_selector(value: str) -> str:
    return value.replace("\\", "/")


def pure_path_match(path_text: str, pattern: str) -> bool:
    with contextlib.suppress(ValueError):
        return PurePosixPath(path_text).match(pattern)
    return False


def glob_matches(path_text: str, pattern: str) -> bool:
    normalized = normalize_selector(pattern)
    zero_depth = normalized.replace("**/", "")
    return (
        fnmatch.fnmatchcase(path_text, normalized)
        or fnmatch.fnmatchcase(path_text, zero_depth)
        or pure_path_match(path_text, normalized)
    )


def relative_path_text(path: Path, root: Path) -> str | None:
    with contextlib.suppress(ValueError):
        return path.resolve().relative_to(root.resolve()).as_posix()
    return None


def display_path(path: Path, root: Path) -> str:
    rel = relative_path_text(path, root)
    return rel if rel is not None else str(path)


def matches_glob_selector(path: Path, root: Path, selector: str) -> bool:
    abs_path = path.resolve()
    selector_path = Path(selector)

    path_texts = [abs_path.as_posix()]
    rel_text = relative_path_text(abs_path, root)
    if rel_text is not None:
        path_texts.append(rel_text)

    if selector_path.is_absolute():
        patterns = [selector_path.as_posix()]
    else:
        patterns = [normalize_selector(selector), (root / selector).resolve().as_posix()]

    return any(glob_matches(path_text, pattern) for path_text in path_texts for pattern in patterns)


def matches_plain_selector(path: Path, root: Path, selector: str) -> bool:
    selector_path = Path(selector)
    selected = selector_path if selector_path.is_absolute() else root / selector_path
    selected = selected.resolve()
    path = path.resolve()
    return path == selected or path_is_within(path, selected)


def has_glob_chars(value: str) -> bool:
    return any(char in value for char in GLOB_CHARS)


def matches_change_selector(path: Path, root: Path, selector: str) -> bool:
    selector = selector.strip()
    if not selector:
        return False
    if has_glob_chars(selector):
        return matches_glob_selector(path, root, selector)
    return matches_plain_selector(path, root, selector)


def should_watch(path: Path, root: Path) -> bool:
    if not path_is_within(path, root):
        return False
    if any(part in IGNORED_DIR_NAMES for part in path.parts):
        return False
    return path.suffix.lower() in WATCH_EXTENSIONS


def should_run_on_change(path: Path, root: Path, selectors: tuple[str, ...]) -> bool:
    if any(part in IGNORED_DIR_NAMES for part in path.parts):
        return False
    if not selectors:
        return should_watch(path, root)
    return any(matches_change_selector(path, root, selector) for selector in selectors)


def selector_prefix(selector: str) -> Path:
    prefix_parts: list[str] = []

    for part in Path(selector).parts:
        if has_glob_chars(part):
            break
        prefix_parts.append(part)

    return Path(*prefix_parts) if prefix_parts else Path()


def existing_watch_root(path: Path) -> Path:
    path = path.resolve()
    while not path.exists() and path != path.parent:
        path = path.parent
    return path if path.is_dir() else path.parent


def selector_watch_root(root: Path, selector: str) -> Path:
    selector = selector.strip()
    if not selector:
        return root.resolve()

    selector_path = Path(selector)

    if has_glob_chars(selector):
        prefix = selector_prefix(selector)
        candidate = prefix if prefix.is_absolute() else root / prefix
    else:
        candidate = selector_path if selector_path.is_absolute() else root / selector_path

    return existing_watch_root(candidate)


def command_watch_roots(root: Path, selectors: tuple[str, ...]) -> list[str]:
    roots = {root.resolve()}
    roots.update(selector_watch_root(root, selector) for selector in selectors if selector.strip())
    return [str(path) for path in sorted(roots)]


def resolved_path(path: str) -> Path:
    return Path(path).resolve()


@dataclass(slots=True)
class LiveReloadState:
    reload_root: Path
    command_cwd: Path
    clients: set[WebSocket] = field(default_factory=set)
    stop_event: asyncio.Event = field(default_factory=asyncio.Event)
    watcher_task: asyncio.Task[None] | None = None
    command_task: asyncio.Task[None] | None = None
    on_change_command: str | None = None
    on_change_paths: tuple[str, ...] = ()
    reload_paths: tuple[str, ...] = ()

    async def broadcast(self, message: dict[str, object]) -> None:
        if not self.clients:
            return

        dead: list[WebSocket] = []
        for ws in list(self.clients):
            try:
                await ws.send_json(message)
            except (RuntimeError, OSError, WebSocketDisconnect):
                dead.append(ws)

        for ws in dead:
            self.clients.discard(ws)

    def schedule_on_change_command(self, changed_paths: list[Path]) -> None:
        if self.on_change_command is None:
            return

        if not hasattr(self, "command_pending_paths"):
            self.command_pending_paths = set()  # type: ignore[attr-defined]

        self.command_pending_paths.update(changed_paths)  # type: ignore[attr-defined]

        if self.command_task is None or self.command_task.done():
            self.command_task = asyncio.create_task(self.run_on_change_command_loop())

    async def run_on_change_command_loop(self) -> None:
        command = self.on_change_command
        if command is None:
            return

        while getattr(self, "command_pending_paths", set()):
            paths = sorted(self.command_pending_paths)  # type: ignore[attr-defined]
            self.command_pending_paths.clear()  # type: ignore[attr-defined]

            display_paths = [display_path(path, self.command_cwd) for path in paths]

            env = os.environ.copy()
            env["KYTH_CHANGED_FILES"] = os.pathsep.join(display_paths)
            env["KYTH_CHANGED_FILES_JSON"] = json.dumps(display_paths)

            info("[run] changed:", ", ".join(display_paths))
            info("[run] command:", command)

            proc = await asyncio.create_subprocess_shell(
                command,
                cwd=str(self.command_cwd),
                env=env,
            )

            try:
                returncode = await proc.wait()
            except asyncio.CancelledError:
                with contextlib.suppress(ProcessLookupError):
                    proc.terminate()

                try:
                    await asyncio.wait_for(proc.wait(), SHUTDOWN_GRACE_SECONDS)
                except TimeoutError:
                    with contextlib.suppress(ProcessLookupError):
                        proc.kill()
                    await proc.wait()

                raise

            if returncode == 0:
                info("[run] command exited: 0")
            else:
                eprint(f"[run] command failed: exit status {returncode}")

    def watch_roots(self) -> list[str]:
        roots = {self.reload_root.resolve()}
        roots.update(Path(path).resolve() for path in self.reload_paths if path.strip())
        roots.update(
            selector_watch_root(self.command_cwd, selector)
            for selector in self.on_change_paths
            if selector.strip()
        )
        return [str(path) for path in sorted(roots)]

    def should_reload(self, path: Path) -> bool:
        if self.reload_paths:
            return any(
                matches_change_selector(path, self.command_cwd, selector) for selector in self.reload_paths
            )
        return should_watch(path, self.reload_root)

    async def watch_changes(self) -> None:
        pending_reload: set[Path] = set()
        pending_command: set[Path] = set()

        async for changes in awatch(*self.watch_roots(), stop_event=self.stop_event):
            for _change, changed_path in changes:
                path = resolved_path(changed_path)

                if self.should_reload(path):
                    pending_reload.add(path)

                if self.on_change_command and should_run_on_change(
                    path,
                    self.command_cwd,
                    self.on_change_paths,
                ):
                    pending_command.add(path)

            if not pending_reload and not pending_command:
                continue

            await asyncio.sleep(DEBOUNCE_SECONDS)

            reload_changed = sorted(pending_reload)
            command_changed = sorted(pending_command)
            pending_reload.clear()
            pending_command.clear()

            rel_paths = [display_path(path, self.command_cwd) for path in reload_changed]

            if rel_paths:
                info("[watch] changed:", ", ".join(rel_paths))
                await self.broadcast({"type": "reload", "paths": rel_paths})

            if command_changed:
                self.schedule_on_change_command(command_changed)

    async def startup(self) -> None:
        self.watcher_task = asyncio.create_task(self.watch_changes())

    async def shutdown(self) -> None:
        self.stop_event.set()

        if self.watcher_task is not None:
            self.watcher_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.watcher_task
            self.watcher_task = None

        if self.command_task is not None:
            self.command_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.command_task
            self.command_task = None
