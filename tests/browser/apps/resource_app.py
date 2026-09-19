from __future__ import annotations

import asyncio
import os
from http import HTTPStatus
from pathlib import Path
from typing import Any

from kyth.injection import depend_on_data

ROOT_ENV = "KYTH_BROWSER_FIXTURE_ROOT"
FAIL_STARTUP_ENV = "KYTH_BROWSER_FAIL_STARTUP"

_CONTENT_TYPES = {
    ".css": b"text/css",
    ".js": b"text/javascript",
    ".json": b"application/json",
    ".svg": b"image/svg+xml",
    ".woff2": b"font/woff2",
}

_PAGE_ROUTES = {
    "/": "index.html",
    "/other/": "other.html",
    "/duplicate/": "duplicate.html",
    "/query/": "query.html",
    "/srcset/": "srcset.html",
    "/picture/": "picture.html",
    "/background/": "background.html",
    "/font/": "font.html",
    "/csp/": "csp.html",
    "/fragment/": "fragment.html",
    "/two-css/": "two-css.html",
    "/generated/": "generated.html",
    "/data/": "data.html",
    "/data-unhandled/": "data-unhandled.html",
}


async def app(scope: dict[str, Any], receive: Any, send: Any) -> None:
    if scope["type"] == "lifespan":
        await _lifespan(receive, send)
        return
    if scope["type"] != "http":
        return

    root = Path(os.environ[ROOT_ENV])
    path = str(scope["path"])
    page_name = _PAGE_ROUTES.get(path)
    if page_name is not None:
        if path in {"/data/", "/data-unhandled/"}:
            depend_on_data("inventory", root / "inventory.json")
        headers: list[tuple[bytes, bytes]] = []
        if path == "/csp/":
            headers.append((
                b"content-security-policy",
                b"default-src 'self'; script-src 'self'; connect-src 'self'; img-src 'self'",
            ))
        await _file_response(send, root / page_name, b"text/html; charset=utf-8", headers=headers)
        return

    relative = path.removeprefix("/")
    if "/" in relative or not relative:
        await _response(send, HTTPStatus.NOT_FOUND, b"text/plain", b"missing")
        return
    file_path = root / relative
    content_type = _CONTENT_TYPES.get(file_path.suffix)
    if content_type is None:
        await _response(send, HTTPStatus.NOT_FOUND, b"text/plain", b"missing")
        return
    await _file_response(send, file_path, content_type)


async def _lifespan(receive: Any, send: Any) -> None:
    while True:
        message = await receive()
        if message["type"] == "lifespan.startup":
            if os.environ.get(FAIL_STARTUP_ENV) == "1":
                await send({
                    "type": "lifespan.startup.failed",
                    "message": "browser fixture startup failure",
                })
                return
            await send({"type": "lifespan.startup.complete"})
        elif message["type"] == "lifespan.shutdown":
            await send({"type": "lifespan.shutdown.complete"})
            return


async def _file_response(
    send: Any,
    path: Path,
    content_type: bytes,
    *,
    headers: list[tuple[bytes, bytes]] | None = None,
) -> None:
    body = await asyncio.to_thread(_read_file, path)
    if body is None:
        await _response(send, HTTPStatus.NOT_FOUND, b"text/plain", b"missing")
        return
    await _response(
        send,
        HTTPStatus.OK,
        content_type,
        body,
        headers=headers,
    )


def _read_file(path: Path) -> bytes | None:
    try:
        return path.read_bytes()
    except FileNotFoundError:
        return None


async def _response(
    send: Any,
    status: HTTPStatus,
    content_type: bytes,
    body: bytes,
    *,
    headers: list[tuple[bytes, bytes]] | None = None,
) -> None:
    response_headers = [
        (b"content-type", content_type),
        (b"content-length", str(len(body)).encode()),
        *(headers or []),
    ]
    await send({
        "type": "http.response.start",
        "status": status,
        "headers": response_headers,
    })
    await send({"type": "http.response.body", "body": body})
