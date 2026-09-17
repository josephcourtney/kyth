from __future__ import annotations

import http.client
import socket
import sys
import time
from pathlib import Path

import pytest

from kyth.model import ChildStatus
from kyth.supervisor import Supervisor, SupervisorConfig


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

    shutdown_code = "await asyncio.Event().wait()" if shutdown_hang else (
        'await send({"type": "lifespan.shutdown.complete"})\n                return'
    )
    path.write_text(
        f'''import asyncio
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
        await send({{"type": "http.response.start", "status": 200, "headers": []}})
        await send({{"type": "http.response.body", "body": {body.encode()!r}}})
''',
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
