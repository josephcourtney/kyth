from __future__ import annotations

import multiprocessing
import socket
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from kyth.process.child import run_child
from kyth.process.readiness import ChildCommand, StartupEvent, StartupEventKind

if TYPE_CHECKING:
    from multiprocessing.connection import Connection
    from multiprocessing.context import BaseContext
    from multiprocessing.process import BaseProcess


@dataclass(frozen=True, slots=True)
class StartupResult:
    ready: bool
    error: str | None = None
    exit_code: int | None = None


class ChildProcess:
    """Own one application child and its supervisor-side IPC endpoints."""

    def __init__(self, *, context: BaseContext | None = None) -> None:
        """Create a child-process owner using a spawn context by default."""
        self._context = context or multiprocessing.get_context("spawn")
        self._process: BaseProcess | None = None
        self._readiness: Connection | None = None
        self._control: Connection | None = None

    @property
    def pid(self) -> int | None:
        return None if self._process is None else self._process.pid

    @property
    def exit_code(self) -> int | None:
        return None if self._process is None else self._process.exitcode

    @property
    def is_alive(self) -> bool:
        return self._process is not None and self._process.is_alive()

    def start(self, app_target: str, listening_socket: socket.socket) -> None:
        if self._process is not None:
            msg = "child process has already been started"
            raise RuntimeError(msg)

        readiness_recv, readiness_send = self._context.Pipe(duplex=False)
        control_recv, control_send = self._context.Pipe(duplex=False)
        process = self._context.Process(
            target=run_child,
            args=(app_target, listening_socket, readiness_send, control_recv),
            daemon=False,
        )
        process.start()

        readiness_send.close()
        control_recv.close()
        self._process = process
        self._readiness = readiness_recv
        self._control = control_send

    def wait_for_startup(self, timeout: float) -> StartupResult:
        process = self._require_process()
        readiness = self._require_readiness()
        deadline = time.monotonic() + timeout

        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return StartupResult(False, "startup timed out", process.exitcode)

            if readiness.poll(min(remaining, 0.05)):
                try:
                    event = readiness.recv()
                except EOFError:
                    return StartupResult(False, "child exited before reporting readiness", process.exitcode)
                if not isinstance(event, StartupEvent):
                    return StartupResult(False, "child sent an invalid startup event", process.exitcode)
                if event.kind is StartupEventKind.READY:
                    return StartupResult(True)
                return StartupResult(False, event.detail, process.exitcode)

            if not process.is_alive():
                return StartupResult(False, "child exited before reporting readiness", process.exitcode)

    def stop(self, *, grace_timeout: float, terminate_timeout: float) -> int | None:
        process = self._require_process()
        if process.is_alive():
            self._request_shutdown()
            process.join(grace_timeout)

        if process.is_alive():
            process.terminate()
            process.join(terminate_timeout)

        if process.is_alive():
            process.kill()
            process.join(terminate_timeout)

        if process.is_alive():
            msg = f"child process {process.pid} did not exit after kill"
            raise RuntimeError(msg)

        exit_code = process.exitcode
        self.close()
        return exit_code

    def close(self) -> None:
        if self._readiness is not None:
            self._readiness.close()
            self._readiness = None
        if self._control is not None:
            self._control.close()
            self._control = None
        if self._process is not None:
            self._process.close()
            self._process = None

    def _request_shutdown(self) -> None:
        control = self._require_control()
        try:
            control.send(ChildCommand.SHUTDOWN)
        except (BrokenPipeError, EOFError, OSError):
            return

    def _require_process(self) -> BaseProcess:
        if self._process is None:
            msg = "child process has not been started"
            raise RuntimeError(msg)
        return self._process

    def _require_readiness(self) -> Connection:
        if self._readiness is None:
            msg = "readiness channel is unavailable"
            raise RuntimeError(msg)
        return self._readiness

    def _require_control(self) -> Connection:
        if self._control is None:
            msg = "control channel is unavailable"
            raise RuntimeError(msg)
        return self._control
