from __future__ import annotations

import http.client
import json
from urllib.parse import quote

import pytest

from kyth.control import ControlService
from kyth.control.sse import encode_sse
from kyth.protocol import ControlEvent

LOOPBACK_ORIGIN = "http://127.0.0.1:8000"


def _event_path(service: ControlService, view_id: str) -> str:
    return f"/events?token={quote(service.token)}&view_id={quote(view_id)}"


def _view_path(service: ControlService) -> str:
    return f"/views?token={quote(service.token)}"


def _read_sse_event(response: http.client.HTTPResponse) -> dict[str, str]:
    fields: dict[str, str] = {}
    while True:
        line = response.readline().decode().rstrip("\r\n")
        if not line:
            return fields
        if line.startswith(":"):
            continue
        key, value = line.split(":", 1)
        fields[key] = value.lstrip()


@pytest.mark.unit
@pytest.mark.small
def test_sse_encoding_contains_generation_event_and_structured_data() -> None:
    encoded = encode_sse(ControlEvent.sync(7)).decode()

    assert encoded == 'id: 7\nevent: sync\ndata: {"data":{},"generation":7}\n\n'


@pytest.mark.integration
@pytest.mark.medium
def test_registration_and_sse_generation_sync() -> None:
    with ControlService(generation=4) as service:
        registration = http.client.HTTPConnection(*service.address, timeout=2.0)
        body = json.dumps(
            {
                "view_id": "view-a",
                "url": f"{LOOPBACK_ORIGIN}/page",
                "generation": 3,
                "render_id": None,
            }
        )
        registration.request(
            "POST",
            _view_path(service),
            body=body,
            headers={"Content-Type": "application/json", "Origin": LOOPBACK_ORIGIN},
        )
        response = registration.getresponse()
        assert response.status == 200
        assert response.getheader("Access-Control-Allow-Origin") == LOOPBACK_ORIGIN
        response.read()
        registration.close()

        events = http.client.HTTPConnection(*service.address, timeout=2.0)
        events.request("GET", _event_path(service, "view-a"), headers={"Origin": LOOPBACK_ORIGIN})
        stream = events.getresponse()
        assert stream.status == 200
        assert stream.getheader("Content-Type") == "text/event-stream"
        assert _read_sse_event(stream) == {
            "id": "4",
            "event": "sync",
            "data": '{"data":{},"generation":4}',
        }

        service.set_generation(5)

        assert _read_sse_event(stream) == {
            "id": "5",
            "event": "sync",
            "data": '{"data":{},"generation":5}',
        }
        stream.close()
        events.close()

        reconnect = http.client.HTTPConnection(*service.address, timeout=2.0)
        reconnect.request("GET", _event_path(service, "view-a"), headers={"Origin": LOOPBACK_ORIGIN})
        reconnected_stream = reconnect.getresponse()
        assert _read_sse_event(reconnected_stream) == {
            "id": "5",
            "event": "sync",
            "data": '{"data":{},"generation":5}',
        }
        reconnected_stream.close()
        reconnect.close()

        view = service.views.get("view-a")
        assert view is not None
        assert view.url == f"{LOOPBACK_ORIGIN}/page"


@pytest.mark.integration
@pytest.mark.medium
def test_control_service_rejects_bad_token_and_non_loopback_origin() -> None:
    with ControlService() as service:
        connection = http.client.HTTPConnection(*service.address, timeout=2.0)
        connection.request("GET", f"/health?token={quote(service.token)}x")
        response = connection.getresponse()
        assert response.status == 403
        response.read()

        connection.request(
            "GET",
            f"/health?token={quote(service.token)}",
            headers={"Origin": "https://example.com"},
        )
        response = connection.getresponse()
        assert response.status == 403
        response.read()
        connection.close()


@pytest.mark.integration
@pytest.mark.medium
def test_preflight_reflects_only_allowed_loopback_origin() -> None:
    with ControlService() as service:
        connection = http.client.HTTPConnection(*service.address, timeout=2.0)
        connection.request(
            "OPTIONS",
            _view_path(service),
            headers={
                "Origin": LOOPBACK_ORIGIN,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Content-Type",
            },
        )
        response = connection.getresponse()

        assert response.status == 204
        assert response.getheader("Access-Control-Allow-Origin") == LOOPBACK_ORIGIN
        assert response.getheader("Access-Control-Allow-Methods") == "POST, OPTIONS"
        response.read()
        connection.close()
