from __future__ import annotations

import asyncio
import importlib
import sys
import tempfile
import threading
from typing import TYPE_CHECKING, cast

import uvicorn

from kyth.injection import ASGIApp, HTMLInjectionMiddleware, InjectionConfig
from kyth.injection.integration import run_readiness_checks
from kyth.process.readiness import ChildCommand, GenerationApplied, GenerationUpdate, StartupEvent
from kyth.process.socket import rebuild_listening_socket

if TYPE_CHECKING:
    import socket
    from multiprocessing.connection import Connection

    from kyth.process.socket import SocketTransfer


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
        if not self.started:
            self._report(StartupEvent.failed("ASGI lifespan startup did not complete"))
            return
        try:
            await run_readiness_checks()
        except Exception as exc:  # ruff: ignore[blind-except] - application checks are a startup boundary
            self.should_exit = True
            self._report(StartupEvent.failed(f"custom readiness check failed: {exc}"))
            return
        self._report(StartupEvent.ready())


def _watch_control(
    server: uvicorn.Server,
    control: Connection,
    readiness: Connection,
    injection: HTMLInjectionMiddleware,
) -> None:
    while True:
        try:
            command = control.recv()
        except EOFError:
            server.should_exit = True
            return

        if command == ChildCommand.SHUTDOWN:
            server.should_exit = True
            return

        if isinstance(command, GenerationUpdate):
            injection.set_generation(command.generation)
            readiness.send(GenerationApplied(command.generation))


def run_child(
    app_target: str,
    socket_transfer: SocketTransfer,
    socket_family: int,
    socket_type: int,
    socket_proto: int,
    control_url: str,
    control_token: str,
    generation: int,
    readiness: Connection,
    control: Connection,
) -> None:
    """Process entry point for one restartable ASGI child."""
    listening_socket = rebuild_listening_socket(
        socket_transfer,
        socket_family,
        socket_type,
        socket_proto,
    )
    try:
        with tempfile.TemporaryDirectory(prefix="kyth-pycache-") as pycache_dir:
            sys.pycache_prefix = pycache_dir
            importlib.invalidate_caches()
            application = HTMLInjectionMiddleware(
                _load_application(app_target),
                InjectionConfig(
                    control_url=control_url,
                    token=control_token,
                    generation=generation,
                ),
            )
            config = uvicorn.Config(application, reload=False, workers=1, interface="asgi3")
            server = _ReadinessServer(config, readiness)
            control_thread = threading.Thread(
                target=_watch_control,
                args=(server, control, readiness, application),
                daemon=True,
            )
            control_thread.start()
            asyncio.run(server.serve(sockets=[listening_socket]))
    finally:
        readiness.close()
        control.close()
        listening_socket.close()


def _load_application(target: str) -> ASGIApp:
    module_name, separator, attribute_path = target.partition(":")
    if not separator or not module_name or not attribute_path:
        msg = f"invalid ASGI import target: {target!r}"
        raise ValueError(msg)

    value: object = importlib.import_module(module_name)
    for attribute in attribute_path.split("."):
        value = getattr(value, attribute)

    if not callable(value):
        msg = f"ASGI target is not callable: {target!r}"
        raise TypeError(msg)
    return cast("ASGIApp", value)
