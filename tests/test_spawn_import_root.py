from __future__ import annotations

import sys
from pathlib import Path

import pytest

from kyth.model import ChildStatus
from kyth.supervisor import Supervisor, SupervisorConfig


def _write_app(path: Path) -> None:
    path.write_text(
        """async def app(scope, receive, send):
    if scope["type"] != "lifespan":
        return
    while True:
        message = await receive()
        if message["type"] == "lifespan.startup":
            await send({"type": "lifespan.startup.complete"})
        elif message["type"] == "lifespan.shutdown":
            await send({"type": "lifespan.shutdown.complete"})
            return
""",
        encoding="utf-8",
    )


@pytest.mark.system
@pytest.mark.medium
def test_spawned_child_imports_app_from_supervisor_working_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_app(tmp_path / "local_app.py")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        sys,
        "path",
        [entry for entry in sys.path if entry and Path(entry).resolve() != tmp_path.resolve()],
    )

    config = SupervisorConfig("local_app:app", port=0, startup_timeout=5.0, shutdown_timeout=1.0)
    with Supervisor(config) as supervisor:
        assert supervisor.start_child()
        assert supervisor.state.child.status is ChildStatus.READY
