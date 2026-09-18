from __future__ import annotations

import importlib
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, cast

import pytest

from kyth.supervisor import Supervisor, SupervisorConfig

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from types import TracebackType

pytestmark = [
    pytest.mark.system,
    pytest.mark.acceptance,
    pytest.mark.ui,
    pytest.mark.medium,
]

BROWSER_TIMEOUT_MS = 5_000
REGISTRATION_TIMEOUT_SECONDS = 5.0


class _Page(Protocol):
    def goto(self, url: str, *, wait_until: str) -> object: ...
    def evaluate(self, expression: str) -> object: ...
    def wait_for_function(self, expression: str, *, timeout: float) -> object: ...


class _Browser(Protocol):
    def new_page(self) -> _Page: ...
    def close(self) -> None: ...


class _BrowserType(Protocol):
    def launch(self, *, headless: bool) -> _Browser: ...


class _Playwright(Protocol):
    chromium: _BrowserType


class _PlaywrightManager(Protocol):
    def __enter__(self) -> _Playwright: ...
    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...


@dataclass(frozen=True, slots=True)
class _Harness:
    page: _Page
    supervisor: Supervisor
    css: Path
    image: Path
    script: Path


@pytest.fixture
def browser_harness(tmp_path: Path) -> Iterator[_Harness]:
    module = tmp_path / "browser_app.py"
    css = tmp_path / "site.css"
    image = tmp_path / "logo.svg"
    script = tmp_path / "app.js"
    css.write_text("body { background-color: rgb(10, 20, 30); }", encoding="utf-8")
    image.write_text(_svg("one"), encoding="utf-8")
    script.write_text('window.__appScriptVersion = "one";', encoding="utf-8")
    _write_browser_app(module, css=css, image=image, script=script)

    sys.path.insert(0, str(tmp_path))
    try:
        config = SupervisorConfig(
            "browser_app:app",
            port=0,
            startup_timeout=5.0,
            shutdown_timeout=1.0,
            watch_roots=(tmp_path,),
        )
        with Supervisor(config) as supervisor:
            assert supervisor.start_child()
            sync_api = importlib.import_module("playwright.sync_api")
            manager_factory = cast(
                "Callable[[], _PlaywrightManager]",
                vars(sync_api)["sync_playwright"],
            )
            with manager_factory() as playwright:
                browser = playwright.chromium.launch(headless=True)
                try:
                    page = browser.new_page()
                    origin = f"http://{supervisor.address[0]}:{supervisor.address[1]}"
                    page.goto(origin, wait_until="load")
                    _wait_for_complete_registration(supervisor)
                    yield _Harness(page, supervisor, css, image, script)
                finally:
                    browser.close()
    finally:
        sys.path.remove(str(tmp_path))


def test_stylesheet_change_updates_without_document_reload(browser_harness: _Harness) -> None:
    harness = browser_harness
    harness.page.evaluate("() => { window.__kythSentinel = 'keep'; }")
    next_generation = harness.supervisor.state.generation + 1
    harness.css.write_text(
        "body { background-color: rgb(40, 50, 60); }",
        encoding="utf-8",
    )

    harness.supervisor._reload_for_browser_change((harness.css,))

    harness.page.wait_for_function(
        "() => getComputedStyle(document.body).backgroundColor === 'rgb(40, 50, 60)'",
        timeout=BROWSER_TIMEOUT_MS,
    )
    assert harness.page.evaluate("() => window.__kythSentinel") == "keep"
    _wait_for_generation(harness.supervisor, next_generation)


def test_image_change_cache_busts_without_document_reload(browser_harness: _Harness) -> None:
    harness = browser_harness
    harness.page.evaluate("() => { window.__kythSentinel = 'keep'; }")
    next_generation = harness.supervisor.state.generation + 1
    harness.image.write_text(_svg("two"), encoding="utf-8")

    harness.supervisor._reload_for_browser_change((harness.image,))

    harness.page.wait_for_function(
        f"""() => document.querySelector('#logo').src.includes(
            '__kyth_generation__={next_generation}'
        )""",
        timeout=BROWSER_TIMEOUT_MS,
    )
    assert harness.page.evaluate("() => window.__kythSentinel") == "keep"
    _wait_for_generation(harness.supervisor, next_generation)


def test_javascript_change_falls_back_to_full_reload(browser_harness: _Harness) -> None:
    harness = browser_harness
    harness.page.evaluate("() => { window.__kythSentinel = 'discard'; }")
    harness.script.write_text('window.__appScriptVersion = "two";', encoding="utf-8")

    harness.supervisor._reload_for_browser_change((harness.script,))

    harness.page.wait_for_function(
        """() =>
            window.__appScriptVersion === 'two' &&
            window.__kythSentinel === undefined
        """,
        timeout=BROWSER_TIMEOUT_MS,
    )


def test_failed_stylesheet_update_falls_back_to_full_reload(browser_harness: _Harness) -> None:
    harness = browser_harness
    harness.page.evaluate("() => { window.__kythSentinel = 'discard'; }")
    harness.css.unlink()

    harness.supervisor._reload_for_browser_change((harness.css,))

    harness.page.wait_for_function(
        "() => window.__kythSentinel === undefined",
        timeout=BROWSER_TIMEOUT_MS,
    )


def test_failed_image_update_falls_back_to_full_reload(browser_harness: _Harness) -> None:
    harness = browser_harness
    harness.page.evaluate("() => { window.__kythSentinel = 'discard'; }")
    harness.image.unlink()

    harness.supervisor._reload_for_browser_change((harness.image,))

    harness.page.wait_for_function(
        "() => window.__kythSentinel === undefined",
        timeout=BROWSER_TIMEOUT_MS,
    )


def _wait_for_complete_registration(supervisor: Supervisor) -> None:
    deadline = time.monotonic() + REGISTRATION_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        views = supervisor._require_control().views.snapshot()
        if len(views) == 1 and views[0].resources_complete is True:
            return
        time.sleep(0.02)
    raise AssertionError("browser did not register a complete resource snapshot")


def _wait_for_generation(supervisor: Supervisor, generation: int) -> None:
    deadline = time.monotonic() + REGISTRATION_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        views = supervisor._require_control().views.snapshot()
        if len(views) == 1 and views[0].generation == generation:
            return
        time.sleep(0.02)
    raise AssertionError(f"browser did not acknowledge generation {generation}")


def _svg(label: str) -> str:
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">'
        f"<title>{label}</title><rect width=\"10\" height=\"10\"/>"
        "</svg>"
    )


def _write_browser_app(
    module: Path,
    *,
    css: Path,
    image: Path,
    script: Path,
) -> None:
    html = b"""<!doctype html>
<html>
<head>
  <link rel="stylesheet" href="/site.css">
  <script src="/app.js"></script>
</head>
<body>
  <h1 id="status">ready</h1>
  <img id="logo" src="/logo.svg" alt="test">
</body>
</html>"""
    module.write_text(
        f"""
from http import HTTPStatus
from pathlib import Path

CSS = Path({str(css)!r})
IMAGE = Path({str(image)!r})
SCRIPT = Path({str(script)!r})
HTML = {html!r}


async def app(scope, receive, send):
    if scope["type"] == "lifespan":
        while True:
            message = await receive()
            if message["type"] == "lifespan.startup":
                await send({{"type": "lifespan.startup.complete"}})
            elif message["type"] == "lifespan.shutdown":
                await send({{"type": "lifespan.shutdown.complete"}})
                return

    if scope["type"] != "http":
        return

    path = scope["path"]
    if path == "/":
        await _response(send, HTTPStatus.OK, b"text/html", HTML)
    elif path == "/site.css":
        await _file_response(send, CSS, b"text/css")
    elif path == "/logo.svg":
        await _file_response(send, IMAGE, b"image/svg+xml")
    elif path == "/app.js":
        await _file_response(send, SCRIPT, b"text/javascript")
    else:
        await _response(send, HTTPStatus.NOT_FOUND, b"text/plain", b"missing")


async def _file_response(send, path, content_type):
    if not path.exists():
        await _response(send, HTTPStatus.NOT_FOUND, b"text/plain", b"missing")
        return
    await _response(send, HTTPStatus.OK, content_type, path.read_bytes())


async def _response(send, status, content_type, body):
    await send({{
        "type": "http.response.start",
        "status": status,
        "headers": [
            (b"content-type", content_type),
            (b"content-length", str(len(body)).encode()),
        ],
    }})
    await send({{"type": "http.response.body", "body": body}})
""".lstrip(),
        encoding="utf-8",
    )
