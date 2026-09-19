from __future__ import annotations

from pathlib import Path

import pytest
from watchfiles import Change

from kyth.model import FileBatch, FileEvent, FileOperation
from kyth.watcher import BatchDeduplicator, FileWatcher, WatcherConfig, normalize_changes


@pytest.mark.unit
@pytest.mark.small
def test_normalize_changes_is_deterministic() -> None:
    batch = normalize_changes({
        (Change.modified, "/project/z.py"),
        (Change.deleted, "/project/a.py"),
        (Change.added, "/project/a.py"),
    })

    assert batch.events == (
        FileEvent(Path("/project/a.py"), FileOperation.ADDED),
        FileEvent(Path("/project/a.py"), FileOperation.DELETED),
        FileEvent(Path("/project/z.py"), FileOperation.MODIFIED),
    )


@pytest.mark.unit
@pytest.mark.small
def test_watcher_filter_honors_default_and_explicit_ignores() -> None:
    watcher = FileWatcher(
        WatcherConfig(
            roots=(Path("/project"),),
            ignored_paths=(Path("/project/generated"),),
        )
    )

    assert watcher.accepts(Change.modified, "/project/src/app.py")
    assert not watcher.accepts(Change.modified, "/project/.git/index")
    assert not watcher.accepts(Change.modified, "/project/generated/app.py")
    assert not watcher.accepts(Change.modified, "/project/src/app.pyc")


@pytest.mark.unit
@pytest.mark.small
def test_drain_pending_merges_all_waiting_batches() -> None:
    watcher = FileWatcher(WatcherConfig(roots=(Path("/project"),)))
    first = FileBatch.from_events([FileEvent(Path("/project/a.py"), FileOperation.MODIFIED)])
    second = FileBatch.from_events([FileEvent(Path("/project/b.py"), FileOperation.ADDED)])
    watcher._queue.put(first)
    watcher._queue.put(second)

    assert watcher.drain_pending() == first.merged(second)
    assert watcher.drain_pending() is None


@pytest.mark.integration
@pytest.mark.medium
def test_watcher_observes_real_filesystem_change(tmp_path: Path) -> None:
    changed = tmp_path / "changed.py"

    with FileWatcher(
        WatcherConfig(
            roots=(tmp_path,),
            debounce_ms=50,
            step_ms=20,
        )
    ) as watcher:
        batch = None
        for attempt in range(20):
            changed.write_text(f"value = {attempt}\n", encoding="utf-8")
            batch = watcher.next_batch(timeout=0.2)
            if batch is not None and changed in batch.paths:
                break

    assert batch is not None
    assert changed in batch.paths


@pytest.mark.integration
@pytest.mark.medium
def test_batch_deduplicator_suppresses_duplicate_observed_file_state(tmp_path: Path) -> None:
    path = tmp_path / "app.py"
    path.write_text("first", encoding="utf-8")
    batch = FileBatch.from_events([FileEvent(path, FileOperation.MODIFIED)])
    deduplicator = BatchDeduplicator()

    assert deduplicator.filter(batch) == batch
    assert deduplicator.filter(batch).events == ()

    path.write_text("second-version", encoding="utf-8")
    assert deduplicator.filter(batch) == batch

    path.unlink()
    deleted = FileBatch.from_events([FileEvent(path, FileOperation.DELETED)])
    assert deduplicator.filter(deleted) == deleted
    assert deduplicator.filter(deleted).events == ()
