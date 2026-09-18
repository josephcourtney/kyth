from __future__ import annotations

import secrets
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from http import HTTPStatus
from threading import Lock
from typing import Any

from kyth.injection.html import browser_script, inject_script, rewrite_headers

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
    """Inject Kyth's browser client into ordinary uncompressed HTML responses."""

    def __init__(self, app: ASGIApp, config: InjectionConfig) -> None:
        """Wrap an ASGI application with development-only HTML injection."""
        self._app = app
        self._control_url = config.control_url.rstrip("/")
        self._token = config.token
        self._generation = config.generation
        self._generation_lock = Lock()

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
        """Run the wrapped ASGI application and inject supported HTML responses."""
        if scope.get("type") != "http":
            await self._app(scope, receive, send)
            return

        request_scope = _without_accept_encoding(scope)
        injector = _ResponseInjector(
            send=send,
            control_url=self._control_url,
            token=self._token,
            generation=self.generation,
            method=str(scope.get("method", "GET")),
        )
        await self._app(request_scope, receive, injector.send)


class _ResponseInjector:
    def __init__(
        self,
        *,
        send: Send,
        control_url: str,
        token: str,
        generation: int,
        method: str,
    ) -> None:
        self._send = send
        self._control_url = control_url
        self._token = token
        self._generation = generation
        self._method = method.upper()
        self._start: ASGIMessage | None = None
        self._passthrough = False

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

        if bool(message.get("more_body", False)) or not self._injectable():
            await self._flush_start()
            self._passthrough = bool(message.get("more_body", False))
            await self._send(message)
            return

        body = bytes(message.get("body", b""))
        nonce = secrets.token_urlsafe(16)
        render_id = secrets.token_urlsafe(12)
        script = browser_script(
            control_url=self._control_url,
            token=self._token,
            generation=self._generation,
            render_id=render_id,
            nonce=nonce,
        )
        injected = inject_script(body, script)
        start = self._rewritten_start(body_length=len(injected), nonce=nonce)
        await self._send(start)
        await self._send({**message, "body": injected})

    async def _flush_start(self) -> None:
        if self._start is not None:
            await self._send(self._start)
            self._start = None

    def _injectable(self) -> bool:
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
        if content_type is None or not content_type.lower().startswith(b"text/html"):
            return False
        content_encoding = _header_value(headers, b"content-encoding")
        return content_encoding is None or content_encoding.lower() == b"identity"

    def _rewritten_start(self, *, body_length: int, nonce: str) -> ASGIMessage:
        if self._start is None:
            msg = "response start is unavailable"
            raise RuntimeError(msg)
        headers = rewrite_headers(
            _headers(self._start),
            body_length=body_length,
            control_origin=self._control_url,
            nonce=nonce,
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
