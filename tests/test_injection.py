from __future__ import annotations

from http import HTTPStatus
from typing import Any

import pytest

from kyth.injection import HTMLInjectionMiddleware, InjectionConfig

ASGIMessage = dict[str, Any]


async def _receive() -> ASGIMessage:  # ruff: ignore[unused-async] - ASGI receive callbacks are async by contract
    return {"type": "http.request", "body": b"", "more_body": False}


@pytest.mark.unit
@pytest.mark.small
@pytest.mark.asyncio
async def test_injects_client_and_rewrites_html_response_metadata() -> None:
    received_scope: dict[str, Any] = {}
    sent: list[ASGIMessage] = []

    async def capture(message: ASGIMessage) -> None:  # ruff: ignore[unused-async] - ASGI send callbacks are async by contract
        sent.append(message)

    async def app(scope, _receive, send) -> None:
        received_scope.update(scope)
        await send({
            "type": "http.response.start",
            "status": HTTPStatus.OK,
            "headers": [
                (b"content-type", b"text/html; charset=utf-8"),
                (b"content-length", b"31"),
                (b"etag", b'"abc"'),
                (b"cache-control", b"public, max-age=31536000, immutable"),
                (b"expires", b"Wed, 21 Oct 2037 07:28:00 GMT"),
                (b"content-security-policy", b"default-src 'self'"),
            ],
        })
        await send({
            "type": "http.response.body",
            "body": b"<html><body>Hello</body></html>",
            "more_body": False,
        })

    fixture_token = "fixture-token"  # ruff: ignore[hardcoded-password-string]
    middleware = HTMLInjectionMiddleware(
        app,
        InjectionConfig(
            control_url="http://127.0.0.1:9001",
            token=fixture_token,
            generation=7,
        ),
    )
    await middleware(
        {
            "type": "http",
            "method": "GET",
            "headers": [(b"accept-encoding", b"gzip"), (b"x-test", b"yes")],
        },
        _receive,
        capture,
    )

    assert received_scope["headers"] == [(b"x-test", b"yes")]
    assert len(sent) == 2
    start, body_message = sent
    body = body_message["body"]
    assert isinstance(body, bytes)
    assert f"/client.js?token={fixture_token}".encode() in body
    assert b'data-kyth-generation="7"' in body
    assert b"data-kyth-render-id=" in body
    assert body.index(b"<script ") < body.index(b"</body>")

    headers = dict(start["headers"])
    assert b"etag" not in headers
    assert b"expires" not in headers
    assert headers[b"cache-control"] == b"no-store"
    assert int(headers[b"content-length"]) == len(body)
    policy = headers[b"content-security-policy"].decode()
    assert "script-src 'self' 'nonce-" in policy
    assert "http://127.0.0.1:9001" in policy
    assert "connect-src 'self' http://127.0.0.1:9001" in policy


@pytest.mark.unit
@pytest.mark.small
@pytest.mark.asyncio
async def test_streaming_html_passes_through_without_injection() -> None:
    sent: list[ASGIMessage] = []

    async def capture(message: ASGIMessage) -> None:  # ruff: ignore[unused-async] - ASGI send callbacks are async by contract
        sent.append(message)

    async def app(_scope, _receive, send) -> None:
        await send({
            "type": "http.response.start",
            "status": HTTPStatus.OK,
            "headers": [(b"content-type", b"text/html")],
        })
        await send({
            "type": "http.response.body",
            "body": b"<html><body>",
            "more_body": True,
        })
        await send({
            "type": "http.response.body",
            "body": b"</body></html>",
            "more_body": False,
        })

    middleware = HTMLInjectionMiddleware(
        app,
        InjectionConfig("http://127.0.0.1:9001", "token", 1),
    )
    await middleware({"type": "http", "method": "GET", "headers": []}, _receive, capture)

    assert sent[1]["body"] == b"<html><body>"
    assert sent[2]["body"] == b"</body></html>"
    assert all(b"client.js" not in message.get("body", b"") for message in sent)


@pytest.mark.unit
@pytest.mark.small
@pytest.mark.asyncio
async def test_explicitly_compressed_html_passes_through() -> None:
    sent: list[ASGIMessage] = []

    async def capture(message: ASGIMessage) -> None:  # ruff: ignore[unused-async] - ASGI send callbacks are async by contract
        sent.append(message)

    async def app(_scope, _receive, send) -> None:
        await send({
            "type": "http.response.start",
            "status": HTTPStatus.OK,
            "headers": [
                (b"content-type", b"text/html"),
                (b"content-encoding", b"gzip"),
            ],
        })
        await send({
            "type": "http.response.body",
            "body": b"compressed",
            "more_body": False,
        })

    middleware = HTMLInjectionMiddleware(
        app,
        InjectionConfig("http://127.0.0.1:9001", "token", 1),
    )
    await middleware({"type": "http", "method": "GET", "headers": []}, _receive, capture)

    assert sent[1]["body"] == b"compressed"
    assert b"client.js" not in sent[1]["body"]


@pytest.mark.unit
@pytest.mark.small
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "status", "headers"),
    [
        ("HEAD", HTTPStatus.OK, [(b"content-type", b"text/html")]),
        ("GET", HTTPStatus.NO_CONTENT, [(b"content-type", b"text/html")]),
        ("GET", HTTPStatus.RESET_CONTENT, [(b"content-type", b"text/html")]),
        ("GET", HTTPStatus.NOT_MODIFIED, [(b"content-type", b"text/html")]),
        (
            "GET",
            HTTPStatus.PARTIAL_CONTENT,
            [
                (b"content-type", b"text/html"),
                (b"content-range", b"bytes 0-9/10"),
            ],
        ),
        ("GET", HTTPStatus.OK, [(b"content-type", b"text/plain")]),
        ("GET", HTTPStatus.OK, []),
        (
            "GET",
            HTTPStatus.OK,
            [
                (b"content-type", b"text/html"),
                (b"content-encoding", b"br"),
            ],
        ),
    ],
)
async def test_noninjectable_response_shapes_pass_through(
    method: str,
    status: HTTPStatus,
    headers: list[tuple[bytes, bytes]],
) -> None:
    sent: list[ASGIMessage] = []

    async def capture(message: ASGIMessage) -> None:  # ruff: ignore[unused-async] - ASGI send callbacks are async by contract
        sent.append(message)

    body = b"<html><body>untouched</body></html>"

    async def app(_scope, _receive, send) -> None:
        await send({
            "type": "http.response.start",
            "status": status,
            "headers": headers,
        })
        await send({
            "type": "http.response.body",
            "body": body,
            "more_body": False,
        })

    middleware = HTMLInjectionMiddleware(
        app,
        InjectionConfig("http://127.0.0.1:9001", "token", 1),
    )
    await middleware({"type": "http", "method": method, "headers": []}, _receive, capture)

    assert sent[1]["body"] == body
    assert b"client.js" not in sent[1]["body"]


@pytest.mark.unit
@pytest.mark.small
@pytest.mark.asyncio
async def test_non_html_response_disables_development_caching() -> None:
    sent: list[ASGIMessage] = []

    async def capture(message: ASGIMessage) -> None:  # ruff: ignore[unused-async] - ASGI send is async by contract
        sent.append(message)

    async def app(_scope, _receive, send) -> None:
        await send({
            "type": "http.response.start",
            "status": HTTPStatus.OK,
            "headers": [
                (b"content-type", b"text/javascript"),
                (b"cache-control", b"public, max-age=31536000, immutable"),
                (b"etag", b'"script-v1"'),
            ],
        })
        await send({
            "type": "http.response.body",
            "body": b"window.VERSION = 1;",
            "more_body": False,
        })

    middleware = HTMLInjectionMiddleware(
        app,
        InjectionConfig("http://127.0.0.1:9001", "token", 1),
    )
    await middleware({"type": "http", "method": "GET", "headers": []}, _receive, capture)

    headers = dict(sent[0]["headers"])
    assert headers[b"cache-control"] == b"no-store"
    assert b"etag" not in headers
    assert sent[1]["body"] == b"window.VERSION = 1;"
