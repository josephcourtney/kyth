from __future__ import annotations

import hmac
import ipaddress
import json
import logging
import secrets
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from queue import Empty
from threading import Lock, Thread
from typing import TYPE_CHECKING, Self, cast
from urllib.parse import parse_qs, urlsplit

from kyth.control.client import CLIENT_JAVASCRIPT
from kyth.control.sse import EventBroker, SubscriberQueue, encode_sse
from kyth.control.views import BrowserView, ViewRegistry
from kyth.protocol import ControlEvent

if TYPE_CHECKING:
    from collections.abc import Collection

logger = logging.getLogger(__name__)

MAX_REQUEST_BODY = 64 * 1024
DEFAULT_HEARTBEAT_SECONDS = 15.0


class _ControlState:
    def __init__(
        self,
        *,
        token: str,
        generation: int,
        inactivity_timeout: float,
    ) -> None:
        self.token = token
        self.views = ViewRegistry(inactivity_timeout=inactivity_timeout)
        self.broker = EventBroker()
        self._generation = generation
        self._lock = Lock()

    @property
    def generation(self) -> int:
        with self._lock:
            return self._generation

    def set_generation(self, generation: int) -> None:
        with self._lock:
            if generation < self._generation:
                msg = "control generation cannot move backwards"
                raise ValueError(msg)
            if generation == self._generation:
                return
            self._generation = generation


class _ControlHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(
        self,
        server_address: tuple[str, int],
        state: _ControlState,
        *,
        heartbeat_seconds: float,
    ) -> None:
        self.control_state = state
        self.heartbeat_seconds = heartbeat_seconds
        super().__init__(server_address, _ControlRequestHandler)

    def service_actions(self) -> None:
        self.control_state.views.expire_inactive()


class _ControlRequestHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_OPTIONS(self) -> None:
        authorized, origin = self._authorize_request()
        if not authorized:
            return
        if self._request_path() != "/views":
            self._send_status(HTTPStatus.NOT_FOUND, origin=origin)
            return
        self.send_response(HTTPStatus.NO_CONTENT)
        self._send_cors_headers(origin)
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_POST(self) -> None:
        authorized, origin = self._authorize_request()
        if not authorized:
            return
        if self._request_path() != "/views":
            self._send_status(HTTPStatus.NOT_FOUND, origin=origin)
            return

        payload = self._read_json_object(origin)
        if payload is None:
            return

        try:
            view_id = _required_string(payload, "view_id")
            url = _required_string(payload, "url")
            generation = _required_nonnegative_int(payload, "generation")
            render_id = _optional_string(payload, "render_id")
        except ValueError as exc:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)}, origin=origin)
            return

        view = self._state.views.register(
            view_id=view_id,
            url=url,
            generation=generation,
            render_id=render_id,
        )
        self._send_json(HTTPStatus.OK, _view_payload(view), origin=origin)

    def do_GET(self) -> None:
        authorized, origin = self._authorize_request()
        if not authorized:
            return

        path = self._request_path()
        if path == "/events":
            self._serve_events(origin)
            return
        if path == "/client.js":
            self._send_javascript(CLIENT_JAVASCRIPT, origin=origin)
            return
        if path == "/health":
            self._send_json(
                HTTPStatus.OK,
                {
                    "generation": self._state.generation,
                    "active_views": len(self._state.views.snapshot()),
                },
                origin=origin,
            )
            return
        self._send_status(HTTPStatus.NOT_FOUND, origin=origin)

    def log_message(self, format: str, *args: object) -> None:  # ruff: ignore[builtin-argument-shadowing] - stdlib override name
        logger.debug(
            "control request: command=%s path=%s message=%s args=%r",
            self.command,
            self._request_path(),
            format,
            args,
        )

    @property
    def _control_server(self) -> _ControlHTTPServer:
        return cast("_ControlHTTPServer", self.server)

    @property
    def _state(self) -> _ControlState:
        return self._control_server.control_state

    def _authorize_request(self) -> tuple[bool, str | None]:
        query = parse_qs(urlsplit(self.path).query)
        token = query.get("token", [""])[0]
        if not hmac.compare_digest(token, self._state.token):
            self._send_status(HTTPStatus.FORBIDDEN)
            return False, None

        origin = self.headers.get("Origin")
        if origin is not None and not _is_loopback_origin(origin):
            self._send_status(HTTPStatus.FORBIDDEN)
            return False, None
        return True, origin

    def _serve_events(self, origin: str | None) -> None:
        query = parse_qs(urlsplit(self.path).query)
        view_id = query.get("view_id", [""])[0]
        if not view_id:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "view_id is required"}, origin=origin)
            return

        current_generation = self._state.generation
        current_view = self._state.views.get(view_id)
        self._state.views.ensure(view_id)
        subscriber = self._state.broker.subscribe(view_id)
        reload_required = (
            None
            if current_view is None
            else current_view.generation < current_generation
        )
        try:
            self._open_event_stream(origin)
            self._write_event(
                ControlEvent.sync(
                    current_generation,
                    reload_required=reload_required,
                )
            )
            self._event_loop(view_id, subscriber)
        except OSError:
            return
        finally:
            self._state.broker.unsubscribe(subscriber)

    def _open_event_stream(self, origin: str | None) -> None:
        self.send_response(HTTPStatus.OK)
        self._send_cors_headers(origin)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()

    def _write_event(self, event: ControlEvent) -> None:
        self.wfile.write(encode_sse(event))
        self.wfile.flush()

    def _event_loop(self, view_id: str, subscriber: SubscriberQueue) -> None:
        while True:
            try:
                event = subscriber.get(timeout=self._control_server.heartbeat_seconds)
            except Empty:
                self._state.views.touch(view_id)
                self.wfile.write(b": keepalive\n\n")
                self.wfile.flush()
                continue
            if event is None:
                return
            self._state.views.touch(view_id)
            self._write_event(event)

    def _read_json_object(self, origin: str | None) -> dict[str, object] | None:
        raw_length = self.headers.get("Content-Length")
        try:
            length = int(raw_length or "0")
        except ValueError:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "invalid Content-Length"}, origin=origin)
            return None
        if length <= 0 or length > MAX_REQUEST_BODY:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "invalid request body size"}, origin=origin)
            return None

        try:
            value = json.loads(self.rfile.read(length))
        except (json.JSONDecodeError, UnicodeDecodeError):
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "request body must be JSON"}, origin=origin)
            return None
        if not isinstance(value, dict):
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "request body must be a JSON object"}, origin=origin)
            return None
        return cast("dict[str, object]", value)

    def _send_javascript(self, source: str, *, origin: str | None) -> None:
        body = source.encode()
        self.send_response(HTTPStatus.OK)
        self._send_cors_headers(origin)
        self.send_header("Content-Type", "text/javascript; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Cross-Origin-Resource-Policy", "cross-origin")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_json(
        self,
        status: HTTPStatus,
        payload: dict[str, object],
        *,
        origin: str | None = None,
    ) -> None:
        body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
        self.send_response(status)
        self._send_cors_headers(origin)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_status(self, status: HTTPStatus, *, origin: str | None = None) -> None:
        self.send_response(status)
        self._send_cors_headers(origin)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _send_cors_headers(self, origin: str | None) -> None:
        if origin is None:
            return
        self.send_header("Access-Control-Allow-Origin", origin)
        self.send_header("Vary", "Origin")

    def _request_path(self) -> str:
        return urlsplit(self.path).path


class ControlService:
    """Supervisor-owned HTTP/SSE control plane for one development session."""

    def __init__(
        self,
        *,
        port: int = 0,
        generation: int = 0,
        inactivity_timeout: float = 300.0,
        heartbeat_seconds: float = DEFAULT_HEARTBEAT_SECONDS,
        token: str | None = None,
    ) -> None:
        """Create a loopback-only control service for one development session."""
        if heartbeat_seconds <= 0:
            msg = "SSE heartbeat interval must be positive"
            raise ValueError(msg)
        self._state = _ControlState(
            token=token or secrets.token_urlsafe(32),
            generation=generation,
            inactivity_timeout=inactivity_timeout,
        )
        self._server = _ControlHTTPServer(
            ("127.0.0.1", port),
            self._state,
            heartbeat_seconds=heartbeat_seconds,
        )
        self._thread: Thread | None = None

    @property
    def address(self) -> tuple[str, int]:
        host, port = cast("tuple[str, int]", self._server.server_address)
        return host, port

    @property
    def token(self) -> str:
        return self._state.token

    @property
    def generation(self) -> int:
        return self._state.generation

    @property
    def views(self) -> ViewRegistry:
        return self._state.views

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = Thread(target=self._server.serve_forever, name="kyth-control", daemon=True)
        self._thread.start()

    def set_generation(self, generation: int) -> None:
        self._state.set_generation(generation)

    def publish(
        self,
        event: ControlEvent,
        *,
        view_ids: Collection[str] | None = None,
    ) -> None:
        """Publish one structured event to all or selected connected browser views."""
        self._state.broker.publish(event, view_ids=view_ids)

    def mark_views_current(self, view_ids: Collection[str], generation: int) -> None:
        """Mark selected views valid through a generation without reloading them."""
        self._state.views.set_generation(view_ids, generation)

    def close(self) -> None:
        self._state.broker.close()
        stopped = True
        if self._thread is not None:
            self._server.shutdown()
            self._thread.join(timeout=2.0)
            stopped = not self._thread.is_alive()
            if stopped:
                self._thread = None
        self._server.server_close()
        if not stopped:
            msg = "control server did not stop"
            raise RuntimeError(msg)

    def __enter__(self) -> Self:
        """Start the control service and return it."""
        self.start()
        return self

    def __exit__(self, *_args: object) -> None:
        """Close the control service when leaving its context."""
        self.close()


def _is_loopback_origin(origin: str) -> bool:
    parsed = urlsplit(origin)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        return False
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        return False
    if parsed.hostname == "localhost":
        return True
    try:
        return ipaddress.ip_address(parsed.hostname).is_loopback
    except ValueError:
        return False


def _required_string(payload: dict[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        msg = f"{key} must be a non-empty string"
        raise ValueError(msg)
    return value


def _optional_string(payload: dict[str, object], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        msg = f"{key} must be a non-empty string or null"
        raise ValueError(msg)
    return value


def _required_nonnegative_int(payload: dict[str, object], key: str) -> int:
    value = payload.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        msg = f"{key} must be a non-negative integer"
        raise ValueError(msg)
    return value


def _view_payload(view: BrowserView) -> dict[str, object]:
    return {
        "view_id": view.view_id,
        "url": view.url,
        "generation": view.generation,
        "render_id": view.render_id,
    }
