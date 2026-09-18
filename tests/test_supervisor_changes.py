from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

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
    source = _PendingBatches(
        [
            _batch("/project/second.py").merged(_batch("/project/third.py")),
            None,
        ]
    )

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
