from __future__ import annotations

import pytest

from kyth import DEVCLIENT_PATH, KythApp, live_reload
from kyth.browser import make_devclient_js
from kyth.injection import ensure_devclient_script
from kyth.watcher import reload_message_for_paths


@pytest.mark.unit
@pytest.mark.small
def test_public_imports() -> None:
    assert DEVCLIENT_PATH == "/__devclient__.js"
    assert KythApp is not None
    assert live_reload is not None


@pytest.mark.unit
@pytest.mark.medium
def test_devclient_payload_contains_websocket_path() -> None:
    payload = make_devclient_js("/custom-ws")

    assert "/custom-ws" in payload
    assert "__KYTH_WS_PATH__" not in payload


@pytest.mark.unit
@pytest.mark.small
def test_injects_devclient_script() -> None:
    html = "<!doctype html><html><head></head><body></body></html>"

    result = ensure_devclient_script(html)

    assert '<script src="/__devclient__.js"></script>' in result


@pytest.mark.unit
@pytest.mark.small
def test_reload_message_classification() -> None:
    assert reload_message_for_paths(["static/card.css"])["type"] == "css-reload"
    assert reload_message_for_paths(["static/logo.svg"])["type"] == "asset-reload"
    assert reload_message_for_paths(["templates/card.html.j2"])["type"] == "reload"
