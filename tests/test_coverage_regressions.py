from __future__ import annotations

import http.client
import json
import logging
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, cast
from unittest.mock import Mock, patch
from urllib.parse import quote

import pytest

from kyth.control import ControlService
from kyth.injection.middleware import (
    ASGIMessage,
    ASGIScope,
    HTMLInjectionMiddleware,
    InjectionConfig,
    Receive,
    Send,
)
from kyth.invalidation import BrowserUpdateDecision
from kyth.model import ChildState, ChildStatus, DevelopmentState
from kyth.supervisor import Supervisor, SupervisorConfig

if TYPE_CHECKING:
    import socket

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


@pytest.mark.unit
@pytest.mark.small
@pytest.mark.asyncio
async def test_non_http_asgi_scope_passes_through_unchanged() -> None:
    seen_scopes: list[ASGIScope] = []
    sent: list[ASGIMessage] = []

    async def app(scope: ASGIScope, receive: Receive, send: Send) -> None:
        seen_scopes.append(scope)
        assert await receive() == {"type": "websocket.connect"}
        await send({"type": "websocket.accept"})

    async def receive() -> ASGIMessage:
        return {"type": "websocket.connect"}

    async def send(message: ASGIMessage) -> None:
        sent.append(message)

    with patch("kyth.injection.middleware.install_jinja_tracing"):
        middleware = HTMLInjectionMiddleware(
            app,
            InjectionConfig(
                control_url="http://127.0.0.1:9000",
                token="token",
                generation=3,
            ),
        )

    scope: ASGIScope = {"type": "websocket", "path": "/ws"}
    await middleware(scope, receive, send)

    assert seen_scopes == [scope]
    assert sent == [{"type": "websocket.accept"}]


@pytest.mark.component
@pytest.mark.small
def test_supervisor_open_releases_resources_when_control_start_fails() -> None:
    supervisor = Supervisor(SupervisorConfig("example:app"))
    app_socket = Mock()
    control = Mock()
    control.start.side_effect = RuntimeError("control start failed")

    with (
        patch("kyth.supervisor.bind_listening_socket", return_value=app_socket),
        patch("kyth.supervisor.ControlService", return_value=control),
        pytest.raises(RuntimeError, match="control start failed"),
    ):
        supervisor.open()

    control.close.assert_called_once_with()
    app_socket.close.assert_called_once_with()
    assert supervisor._socket is None
    assert supervisor._control is None


@pytest.mark.component
@pytest.mark.small
def test_supervisor_close_releases_socket_when_cleanup_fails() -> None:
    supervisor = Supervisor(SupervisorConfig("example:app"))
    supervisor._child = cast("ChildProcess", object())
    control = Mock()
    control.close.side_effect = RuntimeError("control cleanup failed")
    app_socket = Mock()
    supervisor._control = cast("ControlService", control)
    supervisor._socket = cast("socket.socket", app_socket)
    child_error = RuntimeError("child cleanup failed")

    with (
        patch.object(supervisor, "stop_child", side_effect=child_error),
        pytest.raises(RuntimeError, match="child cleanup failed") as exc_info,
    ):
        supervisor.close()

    control.close.assert_called_once_with()
    app_socket.close.assert_called_once_with()
    assert supervisor._control is None
    assert supervisor._socket is None
    assert getattr(exc_info.value, "__notes__", ()) == ["control cleanup also failed: control cleanup failed"]


@pytest.mark.integration
@pytest.mark.medium
def test_invalid_manifest_reload_preserves_last_valid_index(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
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
                    "url": "/",
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
    expected_outputs = supervisor._generated.known_outputs

    manifest_path.write_text("{", encoding="utf-8")
    with caplog.at_level(logging.ERROR, logger="kyth.supervisor"):
        supervisor._refresh_changed_manifests((manifest_path,))

    assert supervisor._generated.known_outputs == expected_outputs
    assert "generated dependency manifest reload failed" in caplog.text
