from __future__ import annotations

import json
import logging
from http import HTTPStatus
from typing import TYPE_CHECKING

import pytest

from kyth.injection import reporting
from kyth.model import RenderRecord, SourceVersion

if TYPE_CHECKING:
    from collections.abc import Callable
    from typing import ClassVar


class _Response:
    def __init__(self, status: HTTPStatus) -> None:
        self.status = status
        self.read_called = False

    def read(self) -> bytes:
        self.read_called = True
        return b""


class _Connection:
    instances: ClassVar[list[_Connection]] = []
    response_status: ClassVar[HTTPStatus] = HTTPStatus.OK

    def __init__(self, host: str, port: int, *, timeout: float) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout
        self.request_args: tuple[str, str, str, dict[str, str]] | None = None
        self.response = _Response(self.response_status)
        self.closed = False
        self.instances.append(self)

    def request(
        self,
        method: str,
        path: str,
        *,
        body: str,
        headers: dict[str, str],
    ) -> None:
        self.request_args = (method, path, body, headers)

    def getresponse(self) -> _Response:
        return self.response

    def close(self) -> None:
        self.closed = True


def _record() -> RenderRecord:
    return RenderRecord(
        render_id="render-1",
        generation=7,
        dependencies=(SourceVersion("/templates/page.html", 11, 123),),
        complete=True,
        adapter="jinja",
    )


@pytest.mark.component
@pytest.mark.small
def test_post_render_record_serializes_and_closes_connection(monkeypatch: pytest.MonkeyPatch) -> None:
    _Connection.instances.clear()
    _Connection.response_status = HTTPStatus.OK
    monkeypatch.setattr(reporting.http.client, "HTTPConnection", _Connection)

    reporting._post_render_record("http://127.0.0.1:9000", "token value", _record())

    connection = _Connection.instances[-1]
    assert (connection.host, connection.port, connection.timeout) == (
        "127.0.0.1",
        9000,
        reporting.REPORT_TIMEOUT_SECONDS,
    )
    assert connection.request_args is not None
    method, path, body, headers = connection.request_args
    assert method == "POST"
    assert path == "/renders?token=token+value"
    assert headers == {"Content-Type": "application/json"}
    assert json.loads(body) == {
        "adapter": "jinja",
        "complete": True,
        "dependencies": [
            {
                "mtime_ns": 11,
                "path": "/templates/page.html",
                "size": 123,
            }
        ],
        "generation": 7,
        "render_id": "render-1",
    }
    assert connection.response.read_called
    assert connection.closed


@pytest.mark.component
@pytest.mark.small
def test_post_render_record_logs_rejected_response(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _Connection.instances.clear()
    _Connection.response_status = HTTPStatus.BAD_REQUEST
    caplog.set_level(logging.DEBUG, logger=reporting.logger.name)
    monkeypatch.setattr(reporting.http.client, "HTTPConnection", _Connection)

    reporting._post_render_record("http://127.0.0.1:9000", "token", _record())

    assert "rejected with HTTP 400" in caplog.text
    assert _Connection.instances[-1].closed


@pytest.mark.unit
@pytest.mark.small
@pytest.mark.asyncio
async def test_report_render_record_swallows_transport_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    async def failing_to_thread(  # ruff: ignore[unused-async] - asyncio.to_thread returns an awaitable
        _function: Callable[..., object],
        *_args: object,
    ) -> object:
        msg = "control plane unavailable"
        raise OSError(msg)

    monkeypatch.setattr(reporting.asyncio, "to_thread", failing_to_thread)

    await reporting.report_render_record("http://127.0.0.1:9000", "token", _record())


@pytest.mark.unit
@pytest.mark.small
def test_post_render_record_rejects_unsupported_control_url() -> None:
    with pytest.raises(ValueError, match="unsupported control URL"):
        reporting._post_render_record("https://127.0.0.1:9000", "token", _record())
