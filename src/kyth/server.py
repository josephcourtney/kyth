from __future__ import annotations

import contextlib
import importlib
import socket
import tempfile
import webbrowser
from collections.abc import AsyncIterator, Sequence
from pathlib import Path
from typing import Any

import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route, WebSocketRoute
from starlette.types import ASGIApp
from starlette.websockets import WebSocket
from watchfiles import run_process

from kyth.asgi import KythApp
from kyth.browser import devclient_response, make_devclient_js, websocket_handler
from kyth.constants import DEFAULT_HTTP_PORT, DEVCLIENT_PATH, ROOT, WS_PATH
from kyth.logging import eprint, info
from kyth.static import static_response
from kyth.watcher import LiveReloadState, should_restart


def choose_port(host: str, preferred: int) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind((host, preferred))
            return int(s.getsockname()[1])
        except OSError:
            pass

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((host, 0))
        return int(s.getsockname()[1])


def should_open_browser_once(*, no_open: bool, marker_path: str | None) -> bool:
    if no_open:
        return False

    if marker_path is None:
        return True

    marker = Path(marker_path)

    try:
        marker.parent.mkdir(parents=True, exist_ok=True)
        with marker.open("x", encoding="utf-8") as f:
            f.write("opened\n")
    except FileExistsError:
        return False
    except OSError:
        return True

    return True


class EmbeddedUvicornServer(uvicorn.Server):
    @staticmethod
    def install_signal_handlers() -> None:
        return

    @staticmethod
    @contextlib.contextmanager
    def capture_signals() -> AsyncIterator[None]:
        yield


class StaticState:
    def __init__(
        self,
        *,
        root: Path,
        host: str,
        http_port: int,
        client_path: str,
        ws_path: str,
        open_browser: bool,
        command_cwd: Path,
        on_change: str | None,
        on_change_paths: tuple[str, ...],
    ) -> None:
        self.root = root
        self.host = host
        self.http_port = http_port
        self.client_path = client_path
        self.ws_path = ws_path
        self.open_browser = open_browser
        self.command_cwd = command_cwd
        self.devclient_js = make_devclient_js(ws_path)
        self.live = LiveReloadState(
            reload_root=root,
            command_cwd=command_cwd,
            on_change_command=on_change,
            on_change_paths=on_change_paths,
        )

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.http_port}/"

    async def startup(self) -> None:
        info(f"[http] serving {self.root}")
        info(f"[http] url: {self.url}")
        info(f"[ws]   {self.url.rstrip('/')}{self.ws_path}")

        await self.live.startup()

        if self.open_browser:
            opened = webbrowser.open(self.url)
            info(f"[open] browser {'opened' if opened else 'launch requested'}: {self.url}")

    async def shutdown(self) -> None:
        await self.live.shutdown()


def build_static_app(
    *,
    root: Path,
    host: str,
    http_port: int,
    open_browser: bool,
    command_cwd: Path,
    on_change: str | None = None,
    on_change_paths: tuple[str, ...] = (),
    client_path: str = DEVCLIENT_PATH,
    ws_path: str = WS_PATH,
) -> Starlette:
    state = StaticState(
        root=root.resolve(),
        host=host,
        http_port=http_port,
        client_path=client_path,
        ws_path=ws_path,
        open_browser=open_browser,
        command_cwd=command_cwd.resolve(),
        on_change=on_change,
        on_change_paths=on_change_paths,
    )

    async def lifespan(app: Starlette) -> AsyncIterator[None]:
        app.state.dev = state
        await state.startup()
        try:
            yield
        except BaseException:
            raise
        finally:
            await state.shutdown()

    def devclient(request: Request) -> Response:
        return devclient_response(request.app.state.dev.devclient_js)

    async def websocket_endpoint(websocket: WebSocket) -> None:
        await websocket_handler(websocket, clients=websocket.app.state.dev.live.clients)

    def static_handler(request: Request) -> Response:
        app_state = request.app.state.dev
        return static_response(app_state.root, request.url.path, client_path=app_state.client_path)

    return Starlette(
        debug=False,
        routes=[
            Route(client_path, devclient),
            WebSocketRoute(ws_path, websocket_endpoint),
            Route("/{path:path}", static_handler),
        ],
        lifespan=contextlib.asynccontextmanager(lifespan),
    )


def import_asgi_app(target: str) -> ASGIApp:
    module_name, sep, attr_path = target.partition(":")
    if not sep or not module_name or not attr_path:
        raise ValueError("ASGI target must use 'module:app' syntax.")

    module = importlib.import_module(module_name)
    value: Any = module

    for attr in attr_path.split("."):
        value = getattr(value, attr)

    return value


def run_uvicorn_app(*, app: ASGIApp, host: str, port: int) -> int:
    config = uvicorn.Config(
        app,
        host=host,
        port=port,
        log_level="warning",
        access_log=False,
        timeout_graceful_shutdown=1,
    )

    with contextlib.suppress(KeyboardInterrupt):
        EmbeddedUvicornServer(config).run()

    return 0


def run_static_child(
    *,
    root: str,
    host: str,
    port: int,
    no_open: bool,
    invocation_cwd: str,
    on_change: str | None = None,
    on_change_paths: tuple[str, ...] = (),
    browser_open_marker: str | None = None,
) -> int:
    invocation_cwd_path = Path(invocation_cwd).resolve()
    root_path = Path(root)

    if not root_path.is_absolute():
        root_path = invocation_cwd_path / root_path

    if not root_path.exists():
        eprint(f"error: directory does not exist: {root_path}")
        return 2

    if not root_path.is_dir():
        eprint(f"error: not a directory: {root_path}")
        return 2

    http_port = choose_port(host, port)
    app = build_static_app(
        root=root_path,
        host=host,
        http_port=http_port,
        open_browser=should_open_browser_once(
            no_open=no_open,
            marker_path=browser_open_marker,
        ),
        command_cwd=invocation_cwd_path,
        on_change=on_change,
        on_change_paths=on_change_paths,
    )

    return run_uvicorn_app(app=app, host=host, port=http_port)


def run_asgi_child(
    *,
    target: str,
    host: str,
    port: int,
    no_open: bool,
    invocation_cwd: str,
    watch_paths: tuple[str, ...] = (),
    on_change: str | None = None,
    on_change_paths: tuple[str, ...] = (),
    browser_open_marker: str | None = None,
) -> int:
    invocation_cwd_path = Path(invocation_cwd).resolve()
    http_port = choose_port(host, port)

    try:
        app = import_asgi_app(target)
    except Exception as exc:
        eprint(f"error: failed to import ASGI app {target!r}: {exc}")
        return 2

    wrapped = KythApp(
        app,
        watch_paths=watch_paths,
        command_cwd=invocation_cwd_path,
        reload_root=invocation_cwd_path,
        on_change=on_change,
        on_change_paths=on_change_paths,
    )

    url = f"http://{host}:{http_port}/"
    info(f"[http] serving ASGI app {target}")
    info(f"[http] url: {url}")
    info(f"[ws]   {url.rstrip('/')}{WS_PATH}")

    if should_open_browser_once(no_open=no_open, marker_path=browser_open_marker):
        opened = webbrowser.open(url)
        info(f"[open] browser {'opened' if opened else 'launch requested'}: {url}")

    return run_uvicorn_app(app=wrapped, host=host, port=http_port)


def invoke_static_run_process(
    *,
    root: str,
    host: str,
    port: int,
    no_open: bool,
    invocation_cwd: str,
    on_change: str | None = None,
    on_change_paths: tuple[str, ...] = (),
) -> int:
    with tempfile.TemporaryDirectory(prefix="kyth-") as tmp:
        browser_open_marker = str(Path(tmp) / "browser-opened")

        run_process(
            str(ROOT),
            target=run_static_child,
            kwargs={
                "root": root,
                "host": host,
                "port": port,
                "no_open": no_open,
                "invocation_cwd": invocation_cwd,
                "on_change": on_change,
                "on_change_paths": on_change_paths,
                "browser_open_marker": browser_open_marker,
            },
            watch_filter=should_restart,
            recursive=True,
        )

    return 0


def invoke_asgi_run_process(
    *,
    target: str,
    host: str,
    port: int,
    no_open: bool,
    invocation_cwd: str,
    watch_paths: Sequence[str] = (),
    on_change: str | None = None,
    on_change_paths: tuple[str, ...] = (),
) -> int:
    with tempfile.TemporaryDirectory(prefix="kyth-") as tmp:
        browser_open_marker = str(Path(tmp) / "browser-opened")

        run_process(
            str(Path(invocation_cwd).resolve()),
            target=run_asgi_child,
            kwargs={
                "target": target,
                "host": host,
                "port": port,
                "no_open": no_open,
                "invocation_cwd": invocation_cwd,
                "watch_paths": tuple(watch_paths),
                "on_change": on_change,
                "on_change_paths": on_change_paths,
                "browser_open_marker": browser_open_marker,
            },
            watch_filter=should_restart,
            recursive=True,
        )

    return 0


# Backwards-compatible names from the previous core.py API.
build_app = build_static_app
run_child = run_static_child
invoke_run_process = invoke_static_run_process
