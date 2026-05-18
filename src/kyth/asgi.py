from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Awaitable, Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from starlette.types import ASGIApp, Message, Receive, Scope, Send
from starlette.websockets import WebSocket

from kyth.browser import devclient_response, make_devclient_js, websocket_handler
from kyth.constants import DEVCLIENT_PATH, WS_PATH
from kyth.injection import inject_html_bytes, remove_header, set_header, should_inject_html_response
from kyth.watcher import LiveReloadState

ASGISendCallable = Callable[[Message], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class KythConfig:
    watch_paths: tuple[str, ...] = ()
    command_cwd: Path = Path()
    reload_root: Path = Path()
    client_path: str = DEVCLIENT_PATH
    ws_path: str = WS_PATH
    inject_html: bool = True
    on_change: str | None = None
    on_change_paths: tuple[str, ...] = ()


class HTMLInjectingASGIWrapper:
    def __init__(self, app: ASGIApp, *, client_path: str) -> None:
        self.app = app
        self.client_path = client_path

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        start_message: Message | None = None
        body_parts: list[bytes] = []
        should_buffer = False

        async def wrapped_send(message: Message) -> None:
            nonlocal start_message, should_buffer

            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                status = int(message.get("status", 500))
                should_buffer = should_inject_html_response(status=status, headers=headers)
                if should_buffer:
                    start_message = dict(message)
                    start_message["headers"] = headers
                    return
                await send(message)
                return

            if message["type"] == "http.response.body" and should_buffer:
                body_parts.append(message.get("body", b""))
                if message.get("more_body", False):
                    return

                body = b"".join(body_parts)

                try:
                    injected = inject_html_bytes(body, client_path=self.client_path)
                except UnicodeDecodeError:
                    injected = body

                assert start_message is not None
                headers = list(start_message.get("headers", []))
                headers = remove_header(headers, b"content-length")
                headers = set_header(headers, b"content-length", str(len(injected)).encode("ascii"))
                start_message["headers"] = headers

                await send(start_message)
                await send({"type": "http.response.body", "body": injected, "more_body": False})
                return

            await send(message)

        await self.app(scope, receive, wrapped_send)


class KythApp:
    def __init__(
        self,
        app: ASGIApp,
        *,
        watch_paths: Sequence[str | Path] = (),
        command_cwd: str | Path = Path(),
        reload_root: str | Path = Path(),
        client_path: str = DEVCLIENT_PATH,
        ws_path: str = WS_PATH,
        inject_html: bool = True,
        on_change: str | None = None,
        on_change_paths: Sequence[str] = (),
    ) -> None:
        self.app = app
        self.config = KythConfig(
            watch_paths=tuple(str(path) for path in watch_paths),
            command_cwd=Path(command_cwd).resolve(),
            reload_root=Path(reload_root).resolve(),
            client_path=client_path,
            ws_path=ws_path,
            inject_html=inject_html,
            on_change=on_change,
            on_change_paths=tuple(on_change_paths),
        )
        self.devclient_js = make_devclient_js(ws_path)
        self.live = LiveReloadState(
            reload_root=self.config.reload_root,
            command_cwd=self.config.command_cwd,
            on_change_command=on_change,
            on_change_paths=tuple(on_change_paths),
            reload_paths=tuple(str(path) for path in watch_paths),
        )
        self.injecting_app = HTMLInjectingASGIWrapper(app, client_path=client_path)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        scope_type = scope["type"]

        if scope_type == "lifespan":
            await self.handle_lifespan(scope, receive, send)
            return

        if scope_type == "http" and scope.get("path") == self.config.client_path:
            response = devclient_response(self.devclient_js)
            await response(scope, receive, send)
            return

        if scope_type == "websocket" and scope.get("path") == self.config.ws_path:
            websocket = WebSocket(scope, receive=receive, send=send)
            await websocket_handler(websocket, clients=self.live.clients)
            return

        if self.config.inject_html:
            await self.injecting_app(scope, receive, send)
            return

        await self.app(scope, receive, send)

    async def handle_lifespan(self, scope: Scope, receive: Receive, send: Send) -> None:
        await self.live.startup()

        app_task = asyncio.create_task(self.app(scope, receive, send))

        try:
            await app_task
        except BaseException:
            app_task.cancel()
            with contextlib.suppress(BaseException):
                await app_task
            raise
        finally:
            await self.live.shutdown()


def live_reload(
    app: ASGIApp,
    *,
    watch_paths: Sequence[str | Path] = (),
    command_cwd: str | Path = Path(),
    reload_root: str | Path = Path(),
    client_path: str = DEVCLIENT_PATH,
    ws_path: str = WS_PATH,
    inject_html: bool = True,
    on_change: str | None = None,
    on_change_paths: Sequence[str] = (),
) -> KythApp:
    return KythApp(
        app,
        watch_paths=watch_paths,
        command_cwd=command_cwd,
        reload_root=reload_root,
        client_path=client_path,
        ws_path=ws_path,
        inject_html=inject_html,
        on_change=on_change,
        on_change_paths=on_change_paths,
    )
