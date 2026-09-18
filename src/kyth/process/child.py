from __future__ import annotations

import asyncio
import threading
from typing import TYPE_CHECKING

import uvicorn

from kyth.process.readiness import ChildCommand, StartupEvent

if TYPE_CHECKING:
    import socket
    from multiprocessing.connection import Connection


class _ReadinessServer(uvicorn.Server):
    def __init__(self, config: uvicorn.Config, readiness: Connection) -> None:
        """Initialize a Uvicorn server that reports successful startup."""
        super().__init__(config)
        self._readiness = readiness
        self._startup_reported = False

    def _report(self, event: StartupEvent) -> None:
        if self._startup_reported:
            return
        self._startup_reported = True
        self._readiness.send(event)

    async def startup(self, sockets: list[socket.socket] | None = None) -> None:
        await super().startup(sockets=sockets)
        if self.started:
            self._report(StartupEvent.ready())
        else:
            self._report(StartupEvent.failed("ASGI lifespan startup did not complete"))


def _watch_control(server: uvicorn.Server, control: Connection) -> None:
    try:
        command = control.recv()
    except EOFError:
        server.should_exit = True
        return

    if command == ChildCommand.SHUTDOWN:
        server.should_exit = True


def run_child(
    app_target: str,
    listening_socket: socket.socket,
    readiness: Connection,
    control: Connection,
) -> None:
    """Process entry point for one restartable ASGI child."""
    config = uvicorn.Config(app_target, reload=False, workers=1)
    server = _ReadinessServer(config, readiness)
    control_thread = threading.Thread(target=_watch_control, args=(server, control), daemon=True)
    control_thread.start()

    try:
        asyncio.run(server.serve(sockets=[listening_socket]))
    finally:
        readiness.close()
        control.close()
        listening_socket.close()
