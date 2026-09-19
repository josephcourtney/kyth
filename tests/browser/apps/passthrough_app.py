from __future__ import annotations

import gzip
from http import HTTPStatus
from typing import Any


async def app(scope: dict[str, Any], receive: Any, send: Any) -> None:
    if scope["type"] == "lifespan":
        await _lifespan(receive, send)
        return
    if scope["type"] != "http":
        return

    path = str(scope["path"])
    if path == "/normal/":
        await _response(send, HTTPStatus.OK, [(b"content-type", b"text/html")], b"<html><body>normal</body></html>")
        return
    if path == "/streaming/":
        await send({
            "type": "http.response.start",
            "status": HTTPStatus.OK,
            "headers": [(b"content-type", b"text/html")],
        })
        await send({
            "type": "http.response.body",
            "body": b"<html><body>stream",
            "more_body": True,
        })
        await send({
            "type": "http.response.body",
            "body": b"ing</body></html>",
            "more_body": False,
        })
        return
    if path == "/compressed/":
        body = gzip.compress(b"<html><body>compressed</body></html>")
        await _response(
            send,
            HTTPStatus.OK,
            [
                (b"content-type", b"text/html"),
                (b"content-encoding", b"gzip"),
            ],
            body,
        )
        return
    if path == "/range/":
        body = b"<html><body>partial</body></html>"
        await _response(
            send,
            HTTPStatus.PARTIAL_CONTENT,
            [
                (b"content-type", b"text/html"),
                (
                    b"content-range",
                    f"bytes 0-{len(body) - 1}/{len(body)}".encode(),
                ),
            ],
            body,
        )
        return
    if path == "/plain/":
        await _response(send, HTTPStatus.OK, [(b"content-type", b"text/plain")], b"plain")
        return
    await _response(send, HTTPStatus.NOT_FOUND, [(b"content-type", b"text/plain")], b"missing")


async def _lifespan(receive: Any, send: Any) -> None:
    while True:
        message = await receive()
        if message["type"] == "lifespan.startup":
            await send({"type": "lifespan.startup.complete"})
        elif message["type"] == "lifespan.shutdown":
            await send({"type": "lifespan.shutdown.complete"})
            return


async def _response(
    send: Any,
    status: HTTPStatus,
    headers: list[tuple[bytes, bytes]],
    body: bytes,
) -> None:
    await send({
        "type": "http.response.start",
        "status": status,
        "headers": [
            *headers,
            (b"content-length", str(len(body)).encode()),
        ],
    })
    await send({"type": "http.response.body", "body": body})
