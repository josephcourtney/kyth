from __future__ import annotations

from typing import Any

import pytest

from kyth.injection import HTMLInjectionMiddleware, InjectionConfig

ASGIMessage = dict[str, Any]


async def _receive() -> ASGIMessage:
    return {"type": "http.request", "body": b"", "more_body": False}


@pytest.mark.unit
@pytest.mark.small
@pytest.mark.asyncio
async def test_injects_client_and_rewrites_html_response_metadata() -> None:
    received_scope: dict[str, Any] = {}
    sent: list[ASGIMessage] = []

    async def capture(message: ASGIMessage) -> None:
        sent.append(message)

    async def app(scope, _receive, send) -> None:
        received_scope.update(scope)
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [
                    (b"content-type", b"text/html; charset=utf-8"),
                    (b"content-length", b"31"),
                    (b"etag", b'"abc"'),
                    (b"content-security-policy", b"default-src 'self'"),
                ],
            }
        )
        await send(
            {
                "type": "http.response.body",
                "body": b"<html><body>Hello</body></html>",
                "more_body": False,
            }
        )

    middleware = HTMLInjectionMiddleware(
        app,
        InjectionConfig(
            control_url="http://127.0.0.1:9001",
            token="secret-token",
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
    assert b"/client.js?token=secret-token" in body
    assert b'data-kyth-generation="7"' in body
    assert b"data-kyth-render-id=" in body
    assert body.index(b"<script ") < body.index(b"</body>")

    headers = dict(start["headers"])
    assert b"etag" not in headers
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

    async def capture(message: ASGIMessage) -> None:
        sent.append(message)

    async def app(_scope, _receive, send) -> None:
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"content-type", b"text/html")],
            }
        )
        await send(
            {
                "type": "http.response.body",
                "body": b"<html><body>",
                "more_body": True,
            }
        )
        await send(
            {
                "type": "http.response.body",
                "body": b"</body></html>",
                "more_body": False,
            }
        )

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

    async def capture(message: ASGIMessage) -> None:
        sent.append(message)

    async def app(_scope, _receive, send) -> None:
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [
                    (b"content-type", b"text/html"),
                    (b"content-encoding", b"gzip"),
                ],
            }
        )
        await send(
            {
                "type": "http.response.body",
                "body": b"compressed",
                "more_body": False,
            }
        )

    middleware = HTMLInjectionMiddleware(
        app,
        InjectionConfig("http://127.0.0.1:9001", "token", 1),
    )
    await middleware({"type": "http", "method": "GET", "headers": []}, _receive, capture)

    assert sent[1]["body"] == b"compressed"
    assert b"client.js" not in sent[1]["body"]
