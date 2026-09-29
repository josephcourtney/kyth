from __future__ import annotations

import os
import signal
import sys
import time
from typing import TYPE_CHECKING

import pytest

from kyth.model import ChildStatus
from kyth.supervisor import Supervisor, SupervisorConfig

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="POSIX SIGINT process semantics")


def _write_app(path: Path) -> None:
    path.write_text(
        """async def app(scope, receive, send):
    if scope["type"] == "lifespan":
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
def test_spawned_child_sigint_exits_cleanly(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_app(tmp_path / "sigint_app.py")
    monkeypatch.chdir(tmp_path)

    config = SupervisorConfig("sigint_app:app", port=0, startup_timeout=5.0, shutdown_timeout=0.5)
    with Supervisor(config) as supervisor:
        assert supervisor.start_child()
        child = supervisor._child
        assert child is not None
        pid = child.pid
        assert pid is not None

        os.kill(pid, signal.SIGINT)
        deadline = time.monotonic() + 5.0
        while child.is_alive and time.monotonic() < deadline:
            time.sleep(0.01)

        assert not child.is_alive
        assert child.exit_code == 0
        supervisor.poll()
        assert supervisor.state.child.status is ChildStatus.FAILED
        assert supervisor.state.child.exit_code == 0
