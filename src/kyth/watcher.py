from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from queue import Empty, Queue
from threading import Event, Thread
from typing import Protocol, Self

from watchfiles import Change, DefaultFilter, watch

from kyth.model import FileBatch, FileEvent, FileOperation

DEFAULT_DEBOUNCE_MS = 300
DEFAULT_STEP_MS = 50
DEFAULT_RUST_TIMEOUT_MS = 500


@dataclass(frozen=True, slots=True)
class ObservedPathState:
    """Filesystem state used to recognize duplicate watcher notifications."""

    exists: bool
    mtime_ns: int | None = None
    ctime_ns: int | None = None
    size: int | None = None
    device: int | None = None
    inode: int | None = None


class BatchDeduplicator:
    """Suppress batches that do not describe a new observed filesystem state."""

    def __init__(self) -> None:
        self._states: dict[Path, ObservedPathState] = {}

    def filter(self, batch: FileBatch) -> FileBatch:
        retained: list[FileEvent] = []
        for path in batch.paths:
            state = _observe_path(path)
            if self._states.get(path) == state:
                continue
            self._states[path] = state
            retained.extend(event for event in batch.events if event.path == path)
        return FileBatch.from_events(retained)


class BatchSource(Protocol):
    def start(self) -> None:
        """Begin producing filesystem batches."""
        ...

    def next_batch(self, timeout: float | None = None) -> FileBatch | None:
        """Return the next batch, or None when the wait timed out."""
        ...

    def drain_pending(self) -> FileBatch | None:
        """Merge and return all batches currently waiting."""
        ...

    def close(self) -> None:
        """Stop producing filesystem batches."""
        ...


@dataclass(frozen=True, slots=True)
class WatcherConfig:
    roots: tuple[Path, ...]
    ignored_paths: tuple[Path, ...] = ()
    debounce_ms: int = DEFAULT_DEBOUNCE_MS
    step_ms: int = DEFAULT_STEP_MS


def normalize_changes(changes: set[tuple[Change, str]]) -> FileBatch:
    events = {FileEvent(path=Path(raw_path), operation=FileOperation(change.name)) for change, raw_path in changes}
    return FileBatch.from_events(events)


class FileWatcher:
    """Observe watched roots and expose deterministic logical file batches."""

    def __init__(self, config: WatcherConfig) -> None:
        if not config.roots:
            msg = "at least one watched root is required"
            raise ValueError(msg)

        self.config = WatcherConfig(
            roots=tuple(_absolute(path) for path in config.roots),
            ignored_paths=tuple(_absolute(path) for path in config.ignored_paths),
            debounce_ms=config.debounce_ms,
            step_ms=config.step_ms,
        )
        self._filter = DefaultFilter(ignore_paths=self.config.ignored_paths)
        self._queue: Queue[FileBatch] = Queue()
        self._stop = Event()
        self._thread: Thread | None = None
        self._error: Exception | None = None

    def start(self) -> None:
        if self._thread is not None:
            return

        missing = tuple(path for path in self.config.roots if not path.exists())
        if missing:
            rendered = ", ".join(str(path) for path in missing)
            msg = f"watched path does not exist: {rendered}"
            raise FileNotFoundError(msg)

        self._thread = Thread(target=self._run, name="kyth-watchfiles", daemon=True)
        self._thread.start()

    def next_batch(self, timeout: float | None = None) -> FileBatch | None:
        try:
            return self._queue.get(timeout=timeout)
        except Empty:
            self._raise_if_failed()
            return None

    def drain_pending(self) -> FileBatch | None:
        batches: list[FileBatch] = []
        while True:
            try:
                batches.append(self._queue.get_nowait())
            except Empty:
                break

        self._raise_if_failed()
        if not batches:
            return None

        merged = batches[0]
        return merged.merged(*batches[1:])

    def close(self) -> None:
        self._stop.set()
        if self._thread is not None:
            thread = self._thread
            thread.join(timeout=2.0)
            if thread.is_alive():
                msg = "filesystem watcher did not stop"
                raise RuntimeError(msg)
            self._thread = None
        self._raise_if_failed()

    def accepts(self, change: Change, path: str) -> bool:
        """Expose filtering semantics for deterministic tests and diagnostics."""
        return self._filter(change, path)

    def __enter__(self) -> Self:
        """Start watching when entering the context."""
        self.start()
        return self

    def __exit__(self, *_args: object) -> None:
        """Stop watching when leaving the context."""
        self.close()

    def _run(self) -> None:
        try:
            for changes in watch(
                *self.config.roots,
                watch_filter=self._filter,
                debounce=self.config.debounce_ms,
                step=self.config.step_ms,
                stop_event=self._stop,
                rust_timeout=DEFAULT_RUST_TIMEOUT_MS,
                raise_interrupt=False,
            ):
                batch = normalize_changes(changes)
                if batch.events:
                    self._queue.put(batch)
        except Exception as exc:  # ruff: ignore[blind-except] - thread failures must be propagated to the supervisor
            self._error = exc

    def _raise_if_failed(self) -> None:
        if self._error is None:
            return
        msg = "filesystem watcher failed"
        raise RuntimeError(msg) from self._error


def _absolute(path: Path) -> Path:
    if path.is_absolute():
        return path
    return Path.cwd() / path


def _observe_path(path: Path) -> ObservedPathState:
    try:
        stat = path.stat()
    except OSError:
        return ObservedPathState(exists=False)
    return ObservedPathState(
        exists=True,
        mtime_ns=stat.st_mtime_ns,
        ctime_ns=stat.st_ctime_ns,
        size=stat.st_size,
        device=stat.st_dev,
        inode=stat.st_ino,
    )
