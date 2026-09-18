from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from kyth.changes import classify_batch
from kyth.model import FileBatch, FileEvent, FileOperation
from kyth.supervisor import Supervisor, SupervisorConfig


class _PendingBatches:
    def __init__(self, batches: list[FileBatch | None]) -> None:
        self._batches = batches

    def start(self) -> None:
        pass

    def next_batch(self, timeout: float | None = None) -> FileBatch | None:
        return None

    def drain_pending(self) -> FileBatch | None:
        if not self._batches:
            return None
        return self._batches.pop(0)

    def close(self) -> None:
        pass


def _batch(path: str) -> FileBatch:
    return FileBatch.from_events([FileEvent(Path(path), FileOperation.MODIFIED)])


@pytest.mark.component
@pytest.mark.small
def test_restart_cycle_coalesces_pending_restart_changes() -> None:
    supervisor = Supervisor(SupervisorConfig("example:app"))
    source = _PendingBatches([
        _batch("/project/second.py").merged(_batch("/project/third.py")),
        None,
    ])

    with patch.object(supervisor, "restart_child", return_value=True) as restart:
        supervisor._handle_change_cycle(_batch("/project/first.py"), source)

    assert restart.call_count == 2


@pytest.mark.component
@pytest.mark.small
def test_browser_only_pending_changes_do_not_trigger_followup_restart() -> None:
    supervisor = Supervisor(SupervisorConfig("example:app"))
    source = _PendingBatches([_batch("/project/site.css")])

    with patch.object(supervisor, "restart_child", return_value=True) as restart:
        supervisor._handle_change_cycle(_batch("/project/app.py"), source)

    assert restart.call_count == 1


@pytest.mark.integration
@pytest.mark.medium
def test_manifest_source_change_is_deferred_until_generated_output_changes(tmp_path: Path) -> None:
    source_path = tmp_path / "content.md"
    output_path = tmp_path / "public" / "index.html"
    manifest_path = tmp_path / "kyth-manifest.json"
    output_path.parent.mkdir()
    source_path.write_text("source", encoding="utf-8")
    output_path.write_text("<html>old</html>", encoding="utf-8")
    manifest_path.write_text(
        json.dumps({
            "version": 1,
            "outputs": [
                {
                    "output": "public/index.html",
                    "sources": ["content.md"],
                }
            ],
        }),
        encoding="utf-8",
    )

    supervisor = Supervisor(
        SupervisorConfig(
            "example:app",
            watch_roots=(tmp_path,),
            manifest_paths=(manifest_path,),
        )
    )
    supervisor._generated.load_all()

    source_batch = FileBatch.from_events([
        FileEvent(source_path, FileOperation.MODIFIED),
    ])
    supervisor._generated.mark_sources_changed(source_batch.paths)
    source_changes = classify_batch(source_batch)

    assert supervisor._relevant_browser_paths(source_changes) == ()
    assert supervisor._generated.stale_outputs == frozenset({output_path.resolve()})

    deletion_batch = FileBatch.from_events([
        FileEvent(output_path, FileOperation.DELETED),
    ])
    deletion_changes = classify_batch(deletion_batch)
    assert supervisor._relevant_browser_paths(deletion_changes) == ()
    assert supervisor._generated.stale_outputs == frozenset({output_path.resolve()})

    output_batch = FileBatch.from_events([
        FileEvent(output_path, FileOperation.MODIFIED),
    ])
    output_changes = classify_batch(output_batch)
    relevant = supervisor._relevant_browser_paths(output_changes)
    supervisor._generated.mark_outputs_updated(relevant)

    assert relevant == (output_path,)
    assert supervisor._generated.stale_outputs == frozenset()
