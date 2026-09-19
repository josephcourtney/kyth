from __future__ import annotations

import http.client
import json
from http import HTTPStatus
from urllib.parse import quote

import pytest

from kyth.control import ControlService
from kyth.control.sse import encode_sse
from kyth.model import BrowserResourceKind
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
        body = json.dumps({
            "view_id": "view-a",
            "url": f"{LOOPBACK_ORIGIN}/page",
            "generation": 3,
            "render_id": None,
        })
        registration.request(
            "POST",
            _view_path(service),
            body=body,
            headers={"Content-Type": "application/json", "Origin": LOOPBACK_ORIGIN},
        )
        response = registration.getresponse()
        assert response.status == HTTPStatus.OK
        assert response.getheader("Access-Control-Allow-Origin") == LOOPBACK_ORIGIN
        response.read()
        registration.close()

        events = http.client.HTTPConnection(*service.address, timeout=2.0)
        events.request("GET", _event_path(service, "view-a"), headers={"Origin": LOOPBACK_ORIGIN})
        stream = events.getresponse()
        assert stream.status == HTTPStatus.OK
        assert stream.getheader("Content-Type") == "text/event-stream"
        assert _read_sse_event(stream) == {
            "id": "4",
            "event": "sync",
            "data": '{"data":{"reload_required":true},"generation":4}',
        }

        service.set_generation(5)
        service.mark_views_current(("view-a",), 5)
        service.publish(
            ControlEvent.sync(5, reload_required=False),
            view_ids=("view-a",),
        )

        assert _read_sse_event(stream) == {
            "id": "5",
            "event": "sync",
            "data": '{"data":{"reload_required":false},"generation":5}',
        }
        stream.close()
        events.close()

        reconnect = http.client.HTTPConnection(*service.address, timeout=2.0)
        reconnect.request("GET", _event_path(service, "view-a"), headers={"Origin": LOOPBACK_ORIGIN})
        reconnected_stream = reconnect.getresponse()
        assert _read_sse_event(reconnected_stream) == {
            "id": "5",
            "event": "sync",
            "data": '{"data":{"reload_required":false},"generation":5}',
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
        assert response.status == HTTPStatus.FORBIDDEN
        response.read()

        connection.request(
            "GET",
            f"/health?token={quote(service.token)}",
            headers={"Origin": "https://example.com"},
        )
        response = connection.getresponse()
        assert response.status == HTTPStatus.FORBIDDEN
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

        assert response.status == HTTPStatus.NO_CONTENT
        assert response.getheader("Access-Control-Allow-Origin") == LOOPBACK_ORIGIN
        assert response.getheader("Access-Control-Allow-Methods") == "POST, OPTIONS"
        response.read()
        connection.close()


@pytest.mark.integration
@pytest.mark.medium
def test_control_service_serves_token_gated_browser_client() -> None:
    with ControlService() as service:
        connection = http.client.HTTPConnection(*service.address, timeout=2.0)
        connection.request("GET", f"/client.js?token={quote(service.token)}")
        response = connection.getresponse()
        body = response.read().decode()

        assert response.status == HTTPStatus.OK
        assert response.getheader("Content-Type") == "text/javascript; charset=utf-8"
        assert response.getheader("Cache-Control") == "no-store"
        assert "new EventSource" in body
        assert "fetch(url, {" in body
        assert 'addEventListener("reload"' in body
        assert 'addEventListener("css-update"' in body
        assert 'addEventListener("asset-update"' in body
        assert 'addEventListener("data-update"' in body
        assert 'addEventListener("server-error"' in body
        assert '"kyth:data-update"' in body
        assert '"kyth:server-error"' in body
        assert '"kyth:before-reload"' in body
        assert '"kyth:restore-state"' in body
        assert 'addEventListener("offline", disconnectEvents)' in body
        assert 'addEventListener("online", reconnectEvents)' in body
        assert "eventSource.close()" in body
        assert "resources_complete" in body
        assert "registration_sequence" in body
        connection.close()


@pytest.mark.integration
@pytest.mark.medium
def test_view_registration_accepts_resource_snapshot() -> None:
    with ControlService(generation=2) as service:
        connection = http.client.HTTPConnection(*service.address, timeout=2.0)
        body = json.dumps({
            "view_id": "resource-view",
            "url": f"{LOOPBACK_ORIGIN}/",
            "generation": 2,
            "registration_sequence": 7,
            "render_id": None,
            "resources": [
                {
                    "url": f"{LOOPBACK_ORIGIN}/site.css",
                    "kind": "stylesheet",
                },
                {
                    "url": f"{LOOPBACK_ORIGIN}/logo.svg",
                    "kind": "image",
                },
            ],
            "resources_complete": True,
        })
        connection.request(
            "POST",
            _view_path(service),
            body=body,
            headers={"Content-Type": "application/json", "Origin": LOOPBACK_ORIGIN},
        )
        response = connection.getresponse()
        assert response.status == HTTPStatus.OK
        response.read()
        connection.close()

        view = service.views.get("resource-view")
        assert view is not None
        assert view.resources_complete is True
        assert view.registration_sequence == 7
        assert [(resource.url, resource.kind) for resource in view.resources] == [
            (f"{LOOPBACK_ORIGIN}/logo.svg", BrowserResourceKind.IMAGE),
            (f"{LOOPBACK_ORIGIN}/site.css", BrowserResourceKind.STYLESHEET),
        ]


@pytest.mark.integration
@pytest.mark.medium
def test_render_registration_stores_generic_provenance_record() -> None:
    with ControlService(generation=3) as service:
        connection = http.client.HTTPConnection(*service.address, timeout=2.0)
        body = json.dumps({
            "render_id": "render-1",
            "generation": 3,
            "complete": True,
            "adapter": "jinja",
            "data_dependencies": [
                {
                    "identity": "inventory",
                    "path": "/data/inventory.json",
                    "mtime_ns": 12,
                    "size": 42,
                }
            ],
            "dependencies": [
                {
                    "path": "/templates/base.html",
                    "mtime_ns": 10,
                    "size": 100,
                },
                {
                    "path": "/templates/page.html",
                    "mtime_ns": 11,
                    "size": 101,
                },
            ],
        })
        connection.request(
            "POST",
            f"/renders?token={quote(service.token)}",
            body=body,
            headers={"Content-Type": "application/json"},
        )
        response = connection.getresponse()
        assert response.status == HTTPStatus.OK
        response.read()
        connection.close()

        record = service.renders.get("render-1")
        assert record is not None
        assert record.adapter == "jinja"
        assert record.complete
        assert [(item.identity, item.source.path) for item in record.data_dependencies] == [
            ("inventory", "/data/inventory.json"),
        ]
        assert [dependency.path for dependency in record.dependencies] == [
            "/templates/base.html",
            "/templates/page.html",
        ]


@pytest.mark.unit
@pytest.mark.small
def test_data_update_and_server_error_events_have_structured_payloads() -> None:
    data = ControlEvent.data_update(8, identities=("inventory", "prices"))
    error = ControlEvent.server_error(7, message="startup failed")

    assert data.kind.value == "data-update"
    assert data.data == {"identities": ["inventory", "prices"]}
    assert error.kind.value == "server-error"
    assert error.data == {"message": "startup failed"}
