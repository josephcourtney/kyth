from __future__ import annotations

import http.client
import json
import socket
import sys
import time
from http import HTTPStatus
from typing import TYPE_CHECKING, cast

import pytest

from kyth.model import ChildStatus
from kyth.supervisor import Supervisor, SupervisorConfig

if TYPE_CHECKING:
    from pathlib import Path


def _write_app(
    path: Path,
    *,
    body: str = "ok",
    shutdown_hang: bool = False,
    startup_marker: Path | None = None,
) -> None:
    startup_marker_code = ""
    if startup_marker is not None:
        startup_marker_code = f"Path({str(startup_marker)!r}).write_text('ready', encoding='utf-8')\n                "

    shutdown_code = (
        "await asyncio.Event().wait()"
        if shutdown_hang
        else ('await send({"type": "lifespan.shutdown.complete"})\n                return')
    )
    path.write_text(
        f"""import asyncio
from http import HTTPStatus
from pathlib import Path


async def app(scope, receive, send):
    if scope["type"] == "lifespan":
        while True:
            message = await receive()
            if message["type"] == "lifespan.startup":
                {startup_marker_code}await send({{"type": "lifespan.startup.complete"}})
            elif message["type"] == "lifespan.shutdown":
                {shutdown_code}
    elif scope["type"] == "http":
        await send({{"type": "http.response.start", "status": HTTPStatus.OK, "headers": []}})
        await send({{"type": "http.response.body", "body": {body.encode()!r}}})
""",
        encoding="utf-8",
    )


def _write_html_app(path: Path, *, body: str) -> None:
    path.write_text(
        f"""from http import HTTPStatus


async def app(scope, receive, send):
    if scope["type"] == "lifespan":
        while True:
            message = await receive()
            if message["type"] == "lifespan.startup":
                await send({{"type": "lifespan.startup.complete"}})
            elif message["type"] == "lifespan.shutdown":
                await send({{"type": "lifespan.shutdown.complete"}})
                return
    elif scope["type"] == "http":
        await send({{
            "type": "http.response.start",
            "status": HTTPStatus.OK,
            "headers": [(b"content-type", b"text/html; charset=utf-8")],
        }})
        await send({{
            "type": "http.response.body",
            "body": {body.encode()!r},
        }})
""",
        encoding="utf-8",
    )


def _write_broken_app(path: Path) -> None:
    path.write_text("this is not valid Python !!!\n", encoding="utf-8")


def _request(address: tuple[str, int]) -> str:
    connection = http.client.HTTPConnection(*address, timeout=2.0)
    try:
        connection.request("GET", "/")
        response = connection.getresponse()
        return response.read().decode()
    finally:
        connection.close()


def _request_response(address: tuple[str, int], path: str) -> tuple[int, dict[str, str], bytes]:
    connection = http.client.HTTPConnection(*address, timeout=2.0)
    try:
        connection.request("GET", path)
        response = connection.getresponse()
        headers = {name.lower(): value for name, value in response.getheaders()}
        return response.status, headers, response.read()
    finally:
        connection.close()


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


def _control_health(address: tuple[str, int], token: str) -> dict[str, object]:
    connection = http.client.HTTPConnection(*address, timeout=2.0)
    try:
        connection.request("GET", f"/health?token={token}")
        response = connection.getresponse()
        assert response.status == HTTPStatus.OK
        payload = json.loads(response.read())
        assert isinstance(payload, dict)
        return cast("dict[str, object]", payload)
    finally:
        connection.close()


@pytest.mark.system
@pytest.mark.medium
def test_restart_reuses_supervisor_owned_socket(tmp_path: Path) -> None:
    module = tmp_path / "restart_app.py"
    _write_app(module, body="one")
    sys.path.insert(0, str(tmp_path))
    try:
        config = SupervisorConfig("restart_app:app", port=0, startup_timeout=5.0, shutdown_timeout=1.0)
        with Supervisor(config) as supervisor:
            assert supervisor.start_child()
            address = supervisor.address
            descriptor = supervisor.socket_fileno
            assert _request(address) == "one"
            assert supervisor.state.generation == 1

            supervisor.stop_child()
            probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                try:
                    probe.bind(address)
                except OSError:
                    pass
                else:
                    pytest.fail("supervisor released the public application socket")
            finally:
                probe.close()

            _write_app(module, body="two")
            assert supervisor.start_child()
            assert supervisor.address == address
            assert supervisor.socket_fileno == descriptor
            assert supervisor.state.generation == 2
            assert supervisor.state.child.status is ChildStatus.READY
            assert _request(address) == "two"

            _write_app(module, body="three")
            assert supervisor.restart_child()
            assert supervisor.address == address
            assert supervisor.socket_fileno == descriptor
            assert supervisor.state.generation == 3
            assert _request(address) == "three"
    finally:
        sys.path.remove(str(tmp_path))


@pytest.mark.system
@pytest.mark.medium
def test_failed_startup_can_recover_without_rebinding(tmp_path: Path) -> None:
    module = tmp_path / "recovery_app.py"
    _write_broken_app(module)
    sys.path.insert(0, str(tmp_path))
    try:
        config = SupervisorConfig("recovery_app:app", port=0, startup_timeout=5.0, shutdown_timeout=0.5)
        with Supervisor(config) as supervisor:
            address = supervisor.address
            descriptor = supervisor.socket_fileno

            assert not supervisor.start_child()
            assert supervisor.state.child.status is ChildStatus.FAILED
            assert supervisor.state.generation == 0
            assert supervisor.address == address
            assert supervisor.socket_fileno == descriptor

            _write_app(module, body="recovered")
            assert supervisor.restart_child()

            assert supervisor.state.child.status is ChildStatus.READY
            assert supervisor.state.generation == 1
            assert supervisor.address == address
            assert supervisor.socket_fileno == descriptor
            assert _request(address) == "recovered"
    finally:
        sys.path.remove(str(tmp_path))


@pytest.mark.system
@pytest.mark.medium
def test_ready_is_reported_only_after_lifespan_startup(tmp_path: Path) -> None:
    module = tmp_path / "readiness_app.py"
    marker = tmp_path / "ready.txt"
    _write_app(module, startup_marker=marker)
    sys.path.insert(0, str(tmp_path))
    try:
        config = SupervisorConfig("readiness_app:app", port=0, startup_timeout=5.0)
        with Supervisor(config) as supervisor:
            assert not marker.exists()
            assert supervisor.start_child()
            assert marker.read_text(encoding="utf-8") == "ready"
            assert supervisor.state.child.status is ChildStatus.READY
    finally:
        sys.path.remove(str(tmp_path))


@pytest.mark.system
@pytest.mark.medium
def test_shutdown_is_bounded_when_lifespan_hangs(tmp_path: Path) -> None:
    module = tmp_path / "hanging_app.py"
    _write_app(module, shutdown_hang=True)
    sys.path.insert(0, str(tmp_path))
    try:
        config = SupervisorConfig(
            "hanging_app:app",
            port=0,
            startup_timeout=5.0,
            shutdown_timeout=0.1,
            terminate_timeout=0.1,
        )
        with Supervisor(config) as supervisor:
            assert supervisor.start_child()
            started = time.monotonic()
            supervisor.stop_child()
            elapsed = time.monotonic() - started

            assert elapsed < 2.0
            assert supervisor.state.child.status is ChildStatus.ABSENT
    finally:
        sys.path.remove(str(tmp_path))


@pytest.mark.system
@pytest.mark.medium
def test_control_plane_survives_application_child_restart(tmp_path: Path) -> None:
    module = tmp_path / "control_app.py"
    _write_app(module, body="one")
    sys.path.insert(0, str(tmp_path))
    try:
        config = SupervisorConfig("control_app:app", port=0, startup_timeout=5.0, shutdown_timeout=1.0)
        with Supervisor(config) as supervisor:
            control_address = supervisor.control_address
            control_token = supervisor.control_token

            assert supervisor.start_child()
            assert _control_health(control_address, control_token)["generation"] == 1

            _write_app(module, body="two")
            assert supervisor.restart_child()

            assert supervisor.control_address == control_address
            assert supervisor.control_token == control_token
            assert _control_health(control_address, control_token)["generation"] == 2
    finally:
        sys.path.remove(str(tmp_path))


@pytest.mark.system
@pytest.mark.medium
def test_html_response_injects_control_client_and_tracks_browser_generation(tmp_path: Path) -> None:
    module = tmp_path / "html_app.py"
    _write_html_app(module, body="<html><body>Hello</body></html>")
    sys.path.insert(0, str(tmp_path))
    try:
        config = SupervisorConfig("html_app:app", port=0, startup_timeout=5.0, shutdown_timeout=1.0)
        with Supervisor(config) as supervisor:
            assert supervisor.start_child()
            original_pid = supervisor.state.child.pid
            status, headers, body = _request_response(supervisor.address, "/")
            text = body.decode()

            assert status == HTTPStatus.OK
            assert headers["content-type"] == "text/html; charset=utf-8"
            assert "/client.js?token=" in text
            assert f'data-kyth-generation="{supervisor.state.generation}"' in text
            assert f'data-kyth-control="http://{supervisor.control_address[0]}:{supervisor.control_address[1]}"' in text
            assert "data-kyth-render-id=" in text

            supervisor._reload_for_browser_change()

            assert supervisor.state.child.pid == original_pid
            assert supervisor.state.generation == 2
            _, _, updated_body = _request_response(supervisor.address, "/")
            assert b'data-kyth-generation="2"' in updated_body
    finally:
        sys.path.remove(str(tmp_path))


@pytest.mark.system
@pytest.mark.medium
def test_restart_publishes_reload_only_after_new_generation_is_ready(tmp_path: Path) -> None:
    module = tmp_path / "reload_app.py"
    _write_html_app(module, body="<html><body>one</body></html>")
    sys.path.insert(0, str(tmp_path))
    try:
        config = SupervisorConfig("reload_app:app", port=0, startup_timeout=5.0, shutdown_timeout=1.0)
        with Supervisor(config) as supervisor:
            assert supervisor.start_child()

            events = http.client.HTTPConnection(*supervisor.control_address, timeout=2.0)
            events.request(
                "GET",
                f"/events?token={supervisor.control_token}&view_id=test-view",
                headers={"Origin": f"http://{supervisor.address[0]}:{supervisor.address[1]}"},
            )
            stream = events.getresponse()
            assert _read_sse_event(stream)["event"] == "sync"

            _write_html_app(module, body="<html><body>two</body></html>")
            assert supervisor.restart_child()

            sync_event = _read_sse_event(stream)
            reload_event = _read_sse_event(stream)

            assert sync_event["event"] == "sync"
            assert sync_event["id"] == "2"
            assert reload_event["event"] == "reload"
            assert reload_event["id"] == "2"
            assert '"reason":"server-restart"' in reload_event["data"]

            _, _, body = _request_response(supervisor.address, "/")
            assert b"<body>two" in body
            assert b'data-kyth-generation="2"' in body
            stream.close()
            events.close()
    finally:
        sys.path.remove(str(tmp_path))
