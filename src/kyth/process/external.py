"""Launch an ASGI child under a project-selected Python interpreter.

The Kyth supervisor remains in its own environment. Only the child runtime is
made importable in the project process; the project environment is not modified.
"""

from __future__ import annotations

import contextlib
import importlib.util
import os
import socket
import subprocess  # noqa: S404
import tempfile
from multiprocessing.connection import Connection
from pathlib import Path
from typing import TYPE_CHECKING, cast

from kyth.process.manager import ChildProcess

if TYPE_CHECKING:
    from multiprocessing.process import BaseProcess


class _SubprocessAdapter:
    """Provide the small lifecycle interface used by ChildProcess."""

    def __init__(self, process: subprocess.Popen[bytes]) -> None:
        self.process = process

    @property
    def pid(self) -> int:
        return self.process.pid

    @property
    def exitcode(self) -> int | None:
        return self.process.poll()

    def is_alive(self) -> bool:
        return self.process.poll() is None

    def join(self, timeout: float) -> None:
        with contextlib.suppress(subprocess.TimeoutExpired):
            self.process.wait(timeout=timeout)

    def terminate(self) -> None:
        self.process.terminate()

    def kill(self) -> None:
        self.process.kill()

    def close(self) -> None:
        # Popen has no close(): all IPC descriptors are owned separately.
        pass


def _runtime_fallback_paths() -> tuple[str, ...]:
    """Expose Kyth's pure-Python ASGI server dependencies only as fallbacks.

    These paths are appended *after* the project environment's site-packages
    in the worker. They do not replace the project's packages or interpreter.
    """
    roots: list[str] = []
    for name in ("uvicorn", "h11", "click", "typing_extensions"):
        spec = importlib.util.find_spec(name)
        if spec is None or spec.origin is None:
            continue
        origin = Path(spec.origin).absolute()
        root = str(origin.parent.parent if spec.submodule_search_locations is not None else origin.parent)
        if root not in roots:
            roots.append(root)
    return tuple(roots)


def _spawn_worker(
    python: Path,
    bootstrap: tempfile.TemporaryDirectory[str],
    listening_socket: socket.socket,
    child: socket.socket,
) -> subprocess.Popen[bytes]:
    """Expose only Kyth's package to the project interpreter and launch it."""
    (Path(bootstrap.name) / "kyth").symlink_to(
        Path(__file__).absolute().parents[1],
        target_is_directory=True,
    )
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(part for part in (bootstrap.name, env.get("PYTHONPATH", "")) if part)
    args = [
        str(python),
        "-m",
        "kyth.process.worker",
        str(listening_socket.fileno()),
        str(child.fileno()),
    ]
    # The command is constructed internally; no shell or user-provided arguments.
    return subprocess.Popen(  # noqa: S603
        args,
        cwd=Path.cwd(),
        env=env,
        pass_fds=(listening_socket.fileno(), child.fileno()),
        close_fds=True,
    )


def _worker_settings(
    app_target: str,
    import_root: Path,
    listening_socket: socket.socket,
    *,
    control_url: str,
    control_token: str,
    generation: int,
) -> dict[str, object]:
    """Return the child bootstrap payload without importing the application."""
    return {
        "app_target": app_target,
        "import_root": str(import_root),
        "socket_family": int(listening_socket.family),
        "socket_type": int(listening_socket.type),
        "socket_proto": listening_socket.proto,
        "control_url": control_url,
        "control_token": control_token,
        "generation": generation,
        "fallback_paths": _runtime_fallback_paths(),
    }


class ExternalChildProcess(ChildProcess):
    """Start the existing ASGI worker with an independently selected Python."""

    def __init__(self, *, python: Path, app_dir: Path) -> None:
        """Keep the selected interpreter and application source root."""
        super().__init__()
        self.python = python
        self.app_dir = app_dir
        self._bootstrap: tempfile.TemporaryDirectory[str] | None = None

    def start(
        self,
        app_target: str,
        listening_socket: socket.socket,
        *,
        control_url: str,
        control_token: str,
        generation: int,
    ) -> None:
        if self._process is not None:
            msg = "child process has already been started"
            raise RuntimeError(msg)

        bootstrap = tempfile.TemporaryDirectory(prefix="kyth-worker-")
        try:
            parent, child = socket.socketpair()
        except OSError:
            bootstrap.cleanup()
            raise
        channel: Connection | None = None
        process: subprocess.Popen[bytes] | None = None
        try:
            process = _spawn_worker(self.python, bootstrap, listening_socket, child)
            channel = Connection(parent.detach())
            channel.send(
                _worker_settings(
                    app_target,
                    self.app_dir,
                    listening_socket,
                    control_url=control_url,
                    control_token=control_token,
                    generation=generation,
                )
            )
        except Exception:
            if channel is not None:
                channel.close()
            if process is not None:
                if process.poll() is None:
                    process.kill()
                process.wait()
            bootstrap.cleanup()
            raise
        finally:
            parent.close()
            child.close()

        if process is None or channel is None:
            msg = "application subprocess launch did not initialize IPC"
            raise RuntimeError(msg)

        # The inherited ChildProcess policy owns all readiness, generation,
        # shutdown escalation, and cleanup. One duplex channel is sufficient:
        # only the worker reads commands, and only the supervisor reads events.
        self._process = cast("BaseProcess", _SubprocessAdapter(process))
        self._readiness = channel
        self._control = channel
        self._bootstrap = bootstrap

    def close(self) -> None:
        """Close worker IPC and release its temporary, package-only import path."""
        try:
            super().close()
        finally:
            if self._bootstrap is not None:
                self._bootstrap.cleanup()
                self._bootstrap = None
