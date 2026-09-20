from __future__ import annotations

import asyncio
import gzip
from http import HTTPStatus
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, patch

import pytest

from kyth.injection import HTMLInjectionMiddleware, InjectionConfig, client_script, depend_on

if TYPE_CHECKING:
    from pathlib import Path

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


@pytest.mark.unit
@pytest.mark.small
def test_explicit_client_script_is_empty_outside_managed_request() -> None:
    assert client_script() == ""


@pytest.mark.unit
@pytest.mark.small
@pytest.mark.asyncio
async def test_explicit_client_inclusion_preserves_streaming_body_and_rewrites_headers() -> None:
    sent: list[ASGIMessage] = []
    emitted_script = ""

    async def capture(message: ASGIMessage) -> None:  # ruff: ignore[unused-async] - ASGI send is async by contract
        sent.append(message)

    async def app(_scope, _receive, send) -> None:
        nonlocal emitted_script
        emitted_script = client_script()
        await send({
            "type": "http.response.start",
            "status": HTTPStatus.OK,
            "headers": [
                (b"content-type", b"text/html"),
                (b"cache-control", b"public, max-age=3600"),
                (b"etag", b'"stream-v1"'),
                (b"content-security-policy", b"default-src 'self'"),
            ],
        })
        await send({
            "type": "http.response.body",
            "body": b"<html><body>",
            "more_body": True,
        })
        await send({
            "type": "http.response.body",
            "body": emitted_script.encode() + b"</body></html>",
            "more_body": False,
        })

    middleware = HTMLInjectionMiddleware(
        app,
        InjectionConfig("http://127.0.0.1:9001", "token", 4),
    )
    await middleware({"type": "http", "method": "GET", "headers": []}, _receive, capture)

    assert sent[1]["body"] == b"<html><body>"
    assert sent[2]["body"] == emitted_script.encode() + b"</body></html>"
    assert sum(bytes(message.get("body", b"")).count(b"data-kyth-control") for message in sent) == 1
    headers = dict(sent[0]["headers"])
    assert headers[b"cache-control"] == b"no-store"
    assert b"etag" not in headers
    policy = headers[b"content-security-policy"].decode()
    assert "script-src 'self' 'nonce-" in policy
    assert "connect-src 'self' http://127.0.0.1:9001" in policy


@pytest.mark.unit
@pytest.mark.small
@pytest.mark.asyncio
async def test_explicit_client_prevents_automatic_double_injection() -> None:
    sent: list[ASGIMessage] = []

    async def capture(message: ASGIMessage) -> None:  # ruff: ignore[unused-async] - ASGI send is async by contract
        sent.append(message)

    async def app(_scope, _receive, send) -> None:
        script = client_script().encode()
        body = b"<html><body>" + script + b"</body></html>"
        await send({
            "type": "http.response.start",
            "status": HTTPStatus.OK,
            "headers": [
                (b"content-type", b"text/html"),
                (b"content-length", str(len(body)).encode()),
            ],
        })
        await send({"type": "http.response.body", "body": body, "more_body": False})

    middleware = HTMLInjectionMiddleware(
        app,
        InjectionConfig("http://127.0.0.1:9001", "token", 2),
    )
    await middleware({"type": "http", "method": "GET", "headers": []}, _receive, capture)

    body = bytes(sent[1]["body"])
    assert body.count(b"/client.js?token=token") == 1
    assert int(dict(sent[0]["headers"])[b"content-length"]) == len(body)


@pytest.mark.unit
@pytest.mark.small
@pytest.mark.asyncio
async def test_explicit_client_preserves_content_encoded_body_bytes() -> None:
    sent: list[ASGIMessage] = []
    compressed = b""

    async def capture(message: ASGIMessage) -> None:  # ruff: ignore[unused-async] - ASGI send is async by contract
        sent.append(message)

    async def app(_scope, _receive, send) -> None:
        nonlocal compressed
        source = f"<html><body>{client_script()}</body></html>".encode()
        compressed = gzip.compress(source)
        await send({
            "type": "http.response.start",
            "status": HTTPStatus.OK,
            "headers": [
                (b"content-type", b"text/html"),
                (b"content-encoding", b"gzip"),
                (b"content-length", str(len(compressed)).encode()),
                (b"content-security-policy", b"default-src 'self'"),
            ],
        })
        await send({"type": "http.response.body", "body": compressed, "more_body": False})

    middleware = HTMLInjectionMiddleware(
        app,
        InjectionConfig("http://127.0.0.1:9001", "token", 3),
    )
    await middleware({"type": "http", "method": "GET", "headers": []}, _receive, capture)

    assert sent[1]["body"] == compressed
    assert b"data-kyth-control" in gzip.decompress(compressed)
    headers = dict(sent[0]["headers"])
    assert headers[b"content-encoding"] == b"gzip"
    assert int(headers[b"content-length"]) == len(compressed)


@pytest.mark.unit
@pytest.mark.small
@pytest.mark.asyncio
async def test_explicit_client_context_is_isolated_between_concurrent_requests() -> None:
    entered = 0
    ready = asyncio.Event()
    scripts: list[str] = []

    async def app(_scope, _receive, send) -> None:
        nonlocal entered
        entered += 1
        if entered == 2:
            ready.set()
        await ready.wait()
        script = client_script()
        scripts.append(script)
        body = f"<html><body>{script}</body></html>".encode()
        await send({
            "type": "http.response.start",
            "status": HTTPStatus.OK,
            "headers": [(b"content-type", b"text/html")],
        })
        await send({"type": "http.response.body", "body": body})

    middleware = HTMLInjectionMiddleware(
        app,
        InjectionConfig("http://127.0.0.1:9001", "token", 5),
    )
    outputs: tuple[list[ASGIMessage], list[ASGIMessage]] = ([], [])

    async def run(index: int) -> None:
        async def capture(message: ASGIMessage) -> None:  # ruff: ignore[unused-async] - ASGI send is async by contract
            outputs[index].append(message)

        await middleware(
            {"type": "http", "method": "GET", "path": f"/{index}", "headers": []},
            _receive,
            capture,
        )

    await asyncio.gather(run(0), run(1))

    assert len(scripts) == 2
    assert scripts[0] != scripts[1]
    assert all('data-kyth-generation="5"' in script for script in scripts)
    assert all(len(messages) == 2 for messages in outputs)


@pytest.mark.unit
@pytest.mark.small
@pytest.mark.asyncio
async def test_explicit_client_use_after_stream_headers_commit_fails() -> None:
    sent: list[ASGIMessage] = []

    async def capture(message: ASGIMessage) -> None:  # ruff: ignore[unused-async] - ASGI send is async by contract
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
        client_script()

    middleware = HTMLInjectionMiddleware(
        app,
        InjectionConfig("http://127.0.0.1:9001", "token", 1),
    )

    with pytest.raises(RuntimeError, match="before response headers are committed"):
        await middleware({"type": "http", "method": "GET", "headers": []}, _receive, capture)

    assert len(sent) == 2


@pytest.mark.unit
@pytest.mark.small
@pytest.mark.asyncio
async def test_explicit_client_rejects_non_document_response() -> None:
    async def discard(_message: ASGIMessage) -> None:  # ruff: ignore[unused-async] - ASGI send is async by contract
        return None

    async def app(_scope, _receive, send) -> None:
        client_script()
        await send({
            "type": "http.response.start",
            "status": HTTPStatus.OK,
            "headers": [(b"content-type", b"text/plain")],
        })
        await send({"type": "http.response.body", "body": b"plain"})

    middleware = HTMLInjectionMiddleware(
        app,
        InjectionConfig("http://127.0.0.1:9001", "token", 1),
    )

    with pytest.raises(RuntimeError, match="requires an HTML document response"):
        await middleware({"type": "http", "method": "GET", "headers": []}, _receive, discard)


@pytest.mark.integration
@pytest.mark.medium
@pytest.mark.asyncio
async def test_explicit_client_and_render_provenance_share_render_identity(tmp_path: Path) -> None:
    sent: list[ASGIMessage] = []
    dependency = tmp_path / "template.html"
    dependency.write_text("template", encoding="utf-8")

    async def capture(message: ASGIMessage) -> None:  # ruff: ignore[unused-async] - ASGI send is async by contract
        sent.append(message)

    async def app(_scope, _receive, send) -> None:
        script = client_script()
        assert depend_on(dependency)
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
            "body": script.encode() + b"</body></html>",
            "more_body": False,
        })

    middleware = HTMLInjectionMiddleware(
        app,
        InjectionConfig("http://127.0.0.1:9001", "token", 9),
    )
    reporter = AsyncMock()
    with patch("kyth.injection.middleware.report_render_record", reporter):
        await middleware({"type": "http", "method": "GET", "headers": []}, _receive, capture)

    reporter.assert_awaited_once()
    record = reporter.await_args.args[2]
    assert f'data-kyth-render-id="{record.render_id}"'.encode() in bytes(sent[2]["body"])
    assert record.generation == 9
    assert tuple(item.path for item in record.dependencies) == (str(dependency.resolve()),)
