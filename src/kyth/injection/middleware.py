from __future__ import annotations

import secrets
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from http import HTTPStatus
from threading import Lock
from typing import Any

from kyth.injection.bootstrap import ClientBootstrap, capture_client_bootstrap
from kyth.injection.html import (
    browser_script,
    inject_script,
    rewrite_cache_headers,
    rewrite_explicit_headers,
    rewrite_headers,
)
from kyth.injection.jinja import capture_render, install_jinja_tracing
from kyth.injection.reporting import report_render_record

ASGIMessage = dict[str, Any]
ASGIScope = dict[str, Any]
Receive = Callable[[], Awaitable[ASGIMessage]]
Send = Callable[[ASGIMessage], Awaitable[None]]
ASGIApp = Callable[[ASGIScope, Receive, Send], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class InjectionConfig:
    control_url: str
    token: str
    generation: int


class HTMLInjectionMiddleware:
    """Synchronize supported HTML through automatic or explicit client inclusion."""

    def __init__(self, app: ASGIApp, config: InjectionConfig) -> None:
        """Wrap an ASGI application with development-only HTML synchronization."""
        self._app = app
        self._control_url = config.control_url.rstrip("/")
        self._token = config.token
        self._generation = config.generation
        self._generation_lock = Lock()
        install_jinja_tracing()

    def set_generation(self, generation: int) -> None:
        """Advance the generation embedded into subsequently rendered documents."""
        with self._generation_lock:
            if generation < self._generation:
                msg = "injected generation cannot move backwards"
                raise ValueError(msg)
            self._generation = generation

    @property
    def generation(self) -> int:
        with self._generation_lock:
            return self._generation

    async def __call__(self, scope: ASGIScope, receive: Receive, send: Send) -> None:
        """Run the wrapped ASGI application and synchronize supported HTML responses."""
        if scope.get("type") != "http":
            await self._app(scope, receive, send)
            return

        request_scope = _without_accept_encoding(scope)
        generation = self.generation
        render_id = secrets.token_urlsafe(12)
        bootstrap = ClientBootstrap(
            control_url=self._control_url,
            token=self._token,
            generation=generation,
            render_id=render_id,
            nonce=secrets.token_urlsafe(16),
        )
        injector = _ResponseInjector(
            send=send,
            bootstrap=bootstrap,
            method=str(scope.get("method", "GET")),
        )
        with capture_client_bootstrap(bootstrap), capture_render(render_id, generation) as trace:
            await self._app(request_scope, receive, injector.send)

        if injector.synchronized and trace.used:
            await report_render_record(
                self._control_url,
                self._token,
                trace.to_record(),
            )


class _ResponseInjector:
    def __init__(
        self,
        *,
        send: Send,
        bootstrap: ClientBootstrap,
        method: str,
    ) -> None:
        self._send = send
        self._bootstrap = bootstrap
        self._method = method.upper()
        self._start: ASGIMessage | None = None
        self._passthrough = False
        self._injected = False
        self._explicit_integrated = False

    @property
    def synchronized(self) -> bool:
        return self._injected or self._explicit_integrated

    async def send(self, message: ASGIMessage) -> None:
        message_type = message.get("type")
        if self._passthrough:
            await self._send(message)
            return

        if message_type == "http.response.start":
            self._start = message
            return

        if message_type != "http.response.body" or self._start is None:
            await self._flush_start()
            await self._send(message)
            return

        if self._bootstrap.explicit_included:
            await self._send_explicit_body(message)
            return

        if bool(message.get("more_body", False)) or not self._injectable():
            await self._flush_start()
            self._passthrough = bool(message.get("more_body", False))
            await self._send(message)
            return

        body = bytes(message.get("body", b""))
        script = browser_script(
            control_url=self._bootstrap.control_url,
            token=self._bootstrap.token,
            generation=self._bootstrap.generation,
            render_id=self._bootstrap.render_id,
            nonce=self._bootstrap.nonce,
        )
        injected = inject_script(body, script)
        start = self._rewritten_start(body_length=len(injected))
        await self._send_start(start)
        await self._send({**message, "body": injected})
        self._injected = True

    async def _send_explicit_body(self, message: ASGIMessage) -> None:
        if not self._document_response():
            msg = "Kyth client_script() requires an HTML document response"
            raise RuntimeError(msg)
        start = self._rewritten_explicit_start()
        await self._send_start(start)
        self._explicit_integrated = True
        self._passthrough = bool(message.get("more_body", False))
        await self._send(message)

    async def _flush_start(self) -> None:
        if self._start is None:
            return
        if self._bootstrap.explicit_included:
            if not self._document_response():
                msg = "Kyth client_script() requires an HTML document response"
                raise RuntimeError(msg)
            start = self._rewritten_explicit_start()
            self._explicit_integrated = True
        else:
            start = {
                **self._start,
                "headers": rewrite_cache_headers(_headers(self._start)),
            }
            self._start = None
        await self._send_start(start)

    async def _send_start(self, start: ASGIMessage) -> None:
        self._bootstrap.headers_committed = True
        await self._send(start)

    def _document_response(self) -> bool:
        if self._method == "HEAD" or self._start is None:
            return False
        status = int(self._start.get("status", HTTPStatus.OK))
        if status < HTTPStatus.OK or status in {
            HTTPStatus.NO_CONTENT,
            HTTPStatus.RESET_CONTENT,
            HTTPStatus.NOT_MODIFIED,
        }:
            return False
        headers = _headers(self._start)
        if _header_value(headers, b"content-range") is not None:
            return False
        content_type = _header_value(headers, b"content-type")
        return content_type is not None and content_type.lower().startswith(b"text/html")

    def _injectable(self) -> bool:
        if not self._document_response() or self._start is None:
            return False
        content_encoding = _header_value(_headers(self._start), b"content-encoding")
        return content_encoding is None or content_encoding.lower() == b"identity"

    def _rewritten_start(self, *, body_length: int) -> ASGIMessage:
        if self._start is None:
            msg = "response start is unavailable"
            raise RuntimeError(msg)
        headers = rewrite_headers(
            _headers(self._start),
            body_length=body_length,
            control_origin=self._bootstrap.control_url,
            nonce=self._bootstrap.nonce,
        )
        start = {**self._start, "headers": headers}
        self._start = None
        return start

    def _rewritten_explicit_start(self) -> ASGIMessage:
        if self._start is None:
            msg = "response start is unavailable"
            raise RuntimeError(msg)
        headers = rewrite_explicit_headers(
            _headers(self._start),
            control_origin=self._bootstrap.control_url,
            nonce=self._bootstrap.nonce,
        )
        start = {**self._start, "headers": headers}
        self._start = None
        return start


def _headers(message: ASGIMessage | None) -> list[tuple[bytes, bytes]]:
    if message is None:
        return []
    raw_headers = message.get("headers", [])
    return [(bytes(name), bytes(value)) for name, value in raw_headers]


def _header_value(headers: list[tuple[bytes, bytes]], name: bytes) -> bytes | None:
    for header_name, value in headers:
        if header_name.lower() == name:
            return value
    return None


def _without_accept_encoding(scope: ASGIScope) -> ASGIScope:
    raw_headers = scope.get("headers")
    if not isinstance(raw_headers, list):
        return scope

    headers = [(name, value) for name, value in raw_headers if bytes(name).lower() != b"accept-encoding"]
    if len(headers) == len(raw_headers):
        return scope
    return {**scope, "headers": headers}
