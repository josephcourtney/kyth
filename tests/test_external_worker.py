"""Cross-interpreter worker acceptance tests.

The isolated virtual environment deliberately does not install Kyth or Uvicorn.
"""

from __future__ import annotations

import http.client
import os
import subprocess
import sys
from dataclasses import replace
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from kyth.model import ChildStatus
from kyth.supervisor import Supervisor, SupervisorConfig

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="POSIX file descriptor passing")


def _project(tmp_path: Path) -> tuple[Path, Path]:
    src = tmp_path / "src"
    package = src / "sample_app"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    target_python = os.environ.get("KYTH_TEST_CHILD_PYTHON", sys.executable)
    subprocess.run(
        [target_python, "-m", "venv", "--without-pip", "--symlinks", str(tmp_path / ".venv")],
        check=True,
        timeout=30,
    )
    python = tmp_path / ".venv" / "bin" / "python"
    subprocess.run(
        [str(python), "-I", "-c", "import importlib.util; assert importlib.util.find_spec('kyth') is None"],
        check=True,
        timeout=10,
    )
    return package / "server.py", python


def _write_application(module: Path, *, text: str) -> None:
    module.write_text(
        f"""import sys

async def app(scope, receive, send):
    if scope["type"] == "lifespan":
        while True:
            event = await receive()
            if event["type"] == "lifespan.startup":
                await send({{"type": "lifespan.startup.complete"}})
            elif event["type"] == "lifespan.shutdown":
                await send({{"type": "lifespan.shutdown.complete"}})
                return
    elif scope["type"] == "http":
        data = ("<html><body>" + {text!r} + "|" + sys.prefix + "</body></html>").encode()
        await send({{"type": "http.response.start", "status": 200,
                    "headers": [(b"content-type", b"text/html")]}})
        await send({{"type": "http.response.body", "body": data}})
""",
        encoding="utf-8",
    )


def _get_html(supervisor: Supervisor) -> str:
    connection = http.client.HTTPConnection(*supervisor.address, timeout=5)
    try:
        connection.request("GET", "/")
        response = connection.getresponse()
        assert response.status == 200
        return response.read().decode()
    finally:
        connection.close()


@pytest.mark.system
@pytest.mark.medium
def test_project_venv_without_kyth_imports_src_app_and_survives_restart(tmp_path: Path) -> None:
    module, python = _project(tmp_path)
    _write_application(module, text="first")
    config = SupervisorConfig(
        "sample_app.server:app",
        python=python,
        app_dir=tmp_path / "src",
        watch_roots=(tmp_path,),
        port=0,
        startup_timeout=12.0,
        shutdown_timeout=1.0,
    )
    with Supervisor(config) as supervisor:
        address = supervisor.address
        fd = supervisor.socket_fileno
        assert supervisor.start_child()
        assert supervisor.state.child.status is ChildStatus.READY
        first = _get_html(supervisor)
        assert "first|" in first
        assert str(tmp_path / ".venv") in first
        assert 'data-kyth-generation="1"' in first
        assert "/client.js?token=" in first

        first_pid = supervisor.state.child.pid
        supervisor._reload_for_browser_change((tmp_path / "style.css",))
        assert supervisor.state.child.pid == first_pid
        assert 'data-kyth-generation="2"' in _get_html(supervisor)

        _write_application(module, text="second")
        assert supervisor.restart_child()
        assert supervisor.address == address
        assert supervisor.socket_fileno == fd
        assert supervisor.state.child.pid != first_pid
        assert "second|" in _get_html(supervisor)
        assert 'data-kyth-generation="3"' in _get_html(supervisor)


@pytest.mark.system
@pytest.mark.medium
def test_external_worker_reports_import_failure_and_recovers(tmp_path: Path) -> None:
    module, python = _project(tmp_path)
    config = SupervisorConfig(
        "sample_app.server:app",
        python=python,
        app_dir=tmp_path / "src",
        port=0,
        startup_timeout=12.0,
        shutdown_timeout=1.0,
    )
    with Supervisor(config) as supervisor:
        assert not supervisor.start_child()
        assert supervisor.state.child.status is ChildStatus.FAILED
        assert supervisor.state.child.error is not None
        assert "ModuleNotFoundError" in supervisor.state.child.error
        assert supervisor.state.generation == 0

        _write_application(module, text="recovered")
        assert supervisor.restart_child()
        assert supervisor.state.generation == 1
        assert "recovered|" in _get_html(supervisor)


@pytest.mark.system
@pytest.mark.medium
def test_missing_project_interpreter_is_reported_and_can_recover(tmp_path: Path) -> None:
    module, python = _project(tmp_path)
    _write_application(module, text="available")
    target = python.readlink()
    config = SupervisorConfig(
        "sample_app.server:app",
        python=python,
        app_dir=tmp_path / "src",
        port=0,
        startup_timeout=12.0,
        shutdown_timeout=1.0,
    )
    with Supervisor(config) as supervisor:
        python.unlink()
        try:
            assert not supervisor.start_child()
            assert supervisor.state.child.status is ChildStatus.FAILED
            assert supervisor.state.child.error is not None
            assert "FileNotFoundError" in supervisor.state.child.error
        finally:
            python.symlink_to(target)

        assert supervisor.restart_child()
        assert supervisor.state.generation == 1
        assert "available|" in _get_html(supervisor)


@pytest.mark.system
@pytest.mark.medium
def test_dependency_restart_recovers_without_another_file_event(tmp_path: Path) -> None:
    module, python = _project(tmp_path)
    lockfile = tmp_path / "uv.lock"
    lockfile.write_text("lock in progress", encoding="utf-8")
    config = SupervisorConfig(
        "sample_app.server:app",
        python=python,
        app_dir=tmp_path / "src",
        port=0,
        startup_timeout=12.0,
        shutdown_timeout=1.0,
    )
    with Supervisor(config) as supervisor:
        from unittest.mock import Mock

        from kyth.model import FileBatch, FileEvent, FileOperation

        source = Mock()
        source.drain_pending.return_value = None
        source.next_batch.return_value = None
        initial = FileBatch.from_events([FileEvent(lockfile, FileOperation.MODIFIED)])
        supervisor._handle_change_cycle(initial, source)
        assert supervisor.state.child.status is ChildStatus.FAILED
        pending = supervisor._dependency_recovery
        assert pending is not None

        # Installing the application changes only the ignored environment.
        # No second watched batch is needed to make the worker ready.
        _write_application(module, text="installed")
        supervisor._dependency_recovery = replace(pending, due_at=0.0)
        supervisor._retry_failed_dependency_restart()

        assert supervisor.state.child.status is ChildStatus.READY
        assert supervisor.state.generation == 1
        assert supervisor._dependency_recovery is None
        assert "installed|" in _get_html(supervisor)
