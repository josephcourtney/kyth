from __future__ import annotations

import http.client
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, cast
from unittest.mock import Mock, patch
from urllib.parse import quote

import pytest

from kyth.control import ControlService
from kyth.invalidation import BrowserUpdateDecision
from kyth.model import ChildState, ChildStatus, DevelopmentState
from kyth.supervisor import Supervisor, SupervisorConfig

if TYPE_CHECKING:
    from kyth.process.manager import ChildProcess

LOOPBACK_ORIGIN = "http://127.0.0.1:8000"


def _event_path(service: ControlService, view_id: str) -> str:
    return f"/events?token={quote(service.token)}&view_id={quote(view_id)}"


def _read_sse_event(response: http.client.HTTPResponse) -> dict[str, str]:
    fields: dict[str, str] = {}
    while True:
        line = response.readline().decode().rstrip("\r\n")
        if not line:
            return fields
        if line.startswith(":"):
            continue
        key, value = line.split(":", 1)
        fields[key] = value.lstrip()


@pytest.mark.integration
@pytest.mark.medium
def test_sse_emits_idle_heartbeat() -> None:
    with ControlService(generation=4, heartbeat_seconds=0.01) as service:
        service.views.register(
            view_id="idle",
            url=f"{LOOPBACK_ORIGIN}/idle",
            generation=4,
        )

        connection = http.client.HTTPConnection(*service.address, timeout=2.0)
        connection.request(
            "GET",
            _event_path(service, "idle"),
            headers={"Origin": LOOPBACK_ORIGIN},
        )
        stream = connection.getresponse()

        assert _read_sse_event(stream)["event"] == "sync"
        assert stream.readline().decode().rstrip("\r\n") == ": keepalive"
        assert stream.readline().decode().rstrip("\r\n") == ""

        stream.close()
        connection.close()


@pytest.mark.component
@pytest.mark.small
def test_browser_generation_update_failure_falls_back_to_restart() -> None:
    supervisor = Supervisor(SupervisorConfig("example:app"))
    supervisor.state = DevelopmentState(
        3,
        ChildState(ChildStatus.READY, pid=123),
    )
    supervisor._child = cast(
        "ChildProcess",
        SimpleNamespace(
            set_generation=Mock(
                side_effect=RuntimeError("generation acknowledgement lost"),
            )
        ),
    )
    supervisor._control = cast("ControlService", object())

    changed = (Path("/project/site.css"),)
    initial = BrowserUpdateDecision(
        invalidated_paths=changed,
        actions=(),
        current_view_ids=(),
        reason="narrow-browser-update",
    )
    restarted = BrowserUpdateDecision(
        invalidated_paths=changed,
        actions=(),
        current_view_ids=(),
        reason="server-restart",
    )

    with (
        patch.object(supervisor, "_browser_updates", return_value=initial),
        patch.object(
            supervisor,
            "_restart_for_change_cycle",
            return_value=restarted,
        ) as restart,
    ):
        result = supervisor._reload_for_browser_change(changed)

    assert result is restarted
    restart.assert_called_once_with(changed)
