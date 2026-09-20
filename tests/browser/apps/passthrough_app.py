from __future__ import annotations

import gzip
from http import HTTPStatus
from typing import Any

from kyth.injection import client_script


async def app(scope: dict[str, Any], receive: Any, send: Any) -> None:
    if scope["type"] == "lifespan":
        await _lifespan(receive, send)
        return
    if scope["type"] != "http":
        return

    await _serve_path(str(scope["path"]), send)


async def _serve_path(path: str, send: Any) -> None:
    if path == "/normal/":
        await _response(
            send,
            HTTPStatus.OK,
            [(b"content-type", b"text/html")],
            b"<html><body>normal</body></html>",
        )
    elif path == "/streaming/":
        await _streaming_response(send)
    elif path == "/streaming-explicit/":
        await _explicit_streaming_response(send)
    elif path == "/streaming-csp/":
        await _explicit_streaming_response(send, csp=True)
    elif path == "/compressed/":
        await _compressed_response(send)
    elif path == "/compressed-explicit/":
        await _explicit_compressed_response(send)
    elif path == "/range/":
        await _range_response(send)
    elif path == "/plain/":
        await _response(
            send,
            HTTPStatus.OK,
            [(b"content-type", b"text/plain")],
            b"plain",
        )
    else:
        await _response(
            send,
            HTTPStatus.NOT_FOUND,
            [(b"content-type", b"text/plain")],
            b"missing",
        )


async def _streaming_response(send: Any) -> None:
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


async def _explicit_streaming_response(send: Any, *, csp: bool = False) -> None:
    script = client_script().encode()
    headers = [(b"content-type", b"text/html")]
    if csp:
        headers.append((b"content-security-policy", b"default-src 'self'"))
    await send({
        "type": "http.response.start",
        "status": HTTPStatus.OK,
        "headers": headers,
    })
    await send({
        "type": "http.response.body",
        "body": b'<html><body><h1 id="status">explicit-streaming</h1>',
        "more_body": True,
    })
    await send({
        "type": "http.response.body",
        "body": script + b"</body></html>",
        "more_body": False,
    })


async def _compressed_response(send: Any) -> None:
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


async def _explicit_compressed_response(send: Any) -> None:
    source = f"<html><body>compressed{client_script()}</body></html>".encode()
    body = gzip.compress(source)
    await _response(
        send,
        HTTPStatus.OK,
        [
            (b"content-type", b"text/html"),
            (b"content-encoding", b"gzip"),
        ],
        body,
    )


async def _range_response(send: Any) -> None:
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
