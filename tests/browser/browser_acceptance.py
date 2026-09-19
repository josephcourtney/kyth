from __future__ import annotations

import importlib
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, cast
from urllib.parse import urlsplit

import pytest

from kyth.model import FileBatch, FileEvent, FileOperation
from kyth.protocol import ControlEvent
from kyth.supervisor import Supervisor, SupervisorConfig

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from types import TracebackType

    from kyth.control.views import BrowserView

pytestmark = [
    pytest.mark.system,
    pytest.mark.acceptance,
    pytest.mark.ui,
    pytest.mark.medium,
]

APP_DIR = Path(__file__).with_name("apps")
RESOURCE_ROOT_ENV = "KYTH_BROWSER_FIXTURE_ROOT"
BROWSER_TIMEOUT_MS = 7_500
RECONNECT_TIMEOUT_MS = 15_000
REGISTRATION_TIMEOUT_SECONDS = 7.5


class _Page(Protocol):
    def goto(self, url: str, *, wait_until: str) -> object: ...
    def evaluate(self, expression: str) -> object: ...
    def wait_for_function(self, expression: str, *, timeout: float) -> object: ...


class _BrowserContext(Protocol):
    def new_page(self) -> _Page: ...
    def set_offline(self, *, offline: bool) -> None: ...
    def close(self) -> None: ...


class _Browser(Protocol):
    def new_context(self) -> _BrowserContext: ...
    def close(self) -> None: ...


class _BrowserType(Protocol):
    def launch(self, *, headless: bool) -> _Browser: ...


class _Playwright(Protocol):
    chromium: _BrowserType
    firefox: _BrowserType


class _PlaywrightManager(Protocol):
    def __enter__(self) -> _Playwright: ...
    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...


class _NoPendingBatches:
    def start(self) -> None:
        return None

    def next_batch(self, timeout: float | None = None) -> FileBatch | None:
        return None

    def drain_pending(self) -> FileBatch | None:
        return None

    def close(self) -> None:
        return None


@dataclass(frozen=True, slots=True)
class _Harness:
    context: _BrowserContext
    page: _Page
    supervisor: Supervisor
    origin: str
    root: Path

    def asset(self, name: str) -> Path:
        return self.root / name


@pytest.fixture(
    scope="session",
    params=("chromium", "firefox"),
    ids=("chromium", "firefox"),
)
def browser(request: pytest.FixtureRequest) -> Iterator[_Browser]:
    engine = cast("str", request.param)
    sync_api = importlib.import_module("playwright.sync_api")
    manager_factory = cast(
        "Callable[[], _PlaywrightManager]",
        vars(sync_api)["sync_playwright"],
    )
    with manager_factory() as playwright:
        browser_type = playwright.chromium if engine == "chromium" else playwright.firefox
        launched = browser_type.launch(headless=True)
        try:
            yield launched
        finally:
            launched.close()


@pytest.fixture
def resource_harness(
    tmp_path: Path,
    browser: _Browser,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[_Harness]:
    _seed_resource_fixture(tmp_path)
    monkeypatch.setenv(RESOURCE_ROOT_ENV, str(tmp_path))
    with (
        _app_import_path(),
        Supervisor(
            SupervisorConfig(
                "resource_app:app",
                port=0,
                startup_timeout=5.0,
                shutdown_timeout=1.0,
                watch_roots=(tmp_path,),
            )
        ) as supervisor,
    ):
        assert supervisor.start_child()
        context = browser.new_context()
        try:
            page = context.new_page()
            origin = _origin(supervisor)
            page.goto(origin, wait_until="load")
            _wait_for_complete_views(supervisor, 1)
            yield _Harness(context, page, supervisor, origin, tmp_path)
        finally:
            context.close()


@pytest.fixture
def jinja_harness(
    tmp_path: Path,
    browser: _Browser,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[_Harness]:
    _seed_jinja_fixture(tmp_path)
    monkeypatch.setenv(RESOURCE_ROOT_ENV, str(tmp_path))
    with (
        _app_import_path(),
        Supervisor(
            SupervisorConfig(
                "jinja_app:app",
                port=0,
                startup_timeout=5.0,
                shutdown_timeout=1.0,
                watch_roots=(tmp_path,),
            )
        ) as supervisor,
    ):
        assert supervisor.start_child()
        context = browser.new_context()
        try:
            page = context.new_page()
            origin = _origin(supervisor)
            page.goto(f"{origin}/a/", wait_until="load")
            _wait_for_complete_views(supervisor, 1)
            _wait_for_render_records(supervisor, 1)
            yield _Harness(context, page, supervisor, origin, tmp_path)
        finally:
            context.close()


@pytest.fixture
def manifest_harness(
    tmp_path: Path,
    browser: _Browser,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[_Harness]:
    _seed_resource_fixture(tmp_path)
    tmp_path.joinpath("content.md").write_text("first", encoding="utf-8")
    tmp_path.joinpath("generator.py").write_text("VERSION = 1\n", encoding="utf-8")
    tmp_path.joinpath("generated.html").write_text(
        _page("generated-one"),
        encoding="utf-8",
    )
    manifest = tmp_path / "kyth-manifest.json"
    manifest.write_text(
        json.dumps({
            "version": 1,
            "outputs": [
                {
                    "output": "generated.html",
                    "url": "/generated/",
                    "sources": ["content.md", "generator.py"],
                }
            ],
        }),
        encoding="utf-8",
    )
    monkeypatch.setenv(RESOURCE_ROOT_ENV, str(tmp_path))
    with (
        _app_import_path(),
        Supervisor(
            SupervisorConfig(
                "resource_app:app",
                port=0,
                startup_timeout=5.0,
                shutdown_timeout=1.0,
                watch_roots=(tmp_path,),
                manifest_paths=(manifest,),
            )
        ) as supervisor,
    ):
        assert supervisor.start_child()
        context = browser.new_context()
        try:
            page = context.new_page()
            origin = _origin(supervisor)
            page.goto(f"{origin}/generated/", wait_until="load")
            _wait_for_complete_views(supervisor, 1)
            yield _Harness(context, page, supervisor, origin, tmp_path)
        finally:
            context.close()


@pytest.fixture
def passthrough_harness(
    tmp_path: Path,
    browser: _Browser,
) -> Iterator[_Harness]:
    with (
        _app_import_path(),
        Supervisor(
            SupervisorConfig(
                "passthrough_app:app",
                port=0,
                startup_timeout=5.0,
                shutdown_timeout=1.0,
                watch_roots=(tmp_path,),
            )
        ) as supervisor,
    ):
        assert supervisor.start_child()
        context = browser.new_context()
        try:
            page = context.new_page()
            yield _Harness(context, page, supervisor, _origin(supervisor), tmp_path)
        finally:
            context.close()


def test_client_registers_complete_resource_snapshot(resource_harness: _Harness) -> None:
    view = _single_view(resource_harness.supervisor)

    assert view.resources_complete is True
    assert {(urlsplit(resource.url).path, resource.kind.value) for resource in view.resources} >= {
        ("/site.css", "stylesheet"),
        ("/logo.svg", "image"),
        ("/app.js", "javascript"),
    }


def test_stylesheet_change_updates_without_document_reload(resource_harness: _Harness) -> None:
    harness = resource_harness
    _set_sentinel(harness.page, "keep")
    generation = harness.supervisor.state.generation + 1
    harness.asset("site.css").write_text(
        "body { background-color: rgb(40, 50, 60); }",
        encoding="utf-8",
    )

    harness.supervisor._reload_for_browser_change((harness.asset("site.css"),))

    harness.page.wait_for_function(
        "() => getComputedStyle(document.body).backgroundColor === 'rgb(40, 50, 60)'",
        timeout=BROWSER_TIMEOUT_MS,
    )
    assert _sentinel(harness.page) == "keep"
    _wait_for_generation(harness.supervisor, generation)


def test_image_change_cache_busts_without_document_reload(resource_harness: _Harness) -> None:
    harness = resource_harness
    _set_sentinel(harness.page, "keep")
    generation = harness.supervisor.state.generation + 1
    harness.asset("logo.svg").write_text(_svg("two"), encoding="utf-8")

    harness.supervisor._reload_for_browser_change((harness.asset("logo.svg"),))

    harness.page.wait_for_function(
        f"""() => document.querySelector('#logo').src.includes(
            '__kyth_generation__={generation}'
        )""",
        timeout=BROWSER_TIMEOUT_MS,
    )
    assert _sentinel(harness.page) == "keep"
    _wait_for_generation(harness.supervisor, generation)


def test_opt_in_state_is_restored_after_full_reload(resource_harness: _Harness) -> None:
    harness = resource_harness
    harness.page.goto(f"{harness.origin}/state/", wait_until="load")
    _wait_for_registered_path(harness.supervisor, "/state/")

    assert harness.supervisor.restart_child()

    harness.page.wait_for_function(
        "() => window.__kythRestoredState?.value === 'preserved'",
        timeout=BROWSER_TIMEOUT_MS,
    )


def test_successful_server_restart_reloads_document(resource_harness: _Harness) -> None:
    harness = resource_harness
    _set_sentinel(harness.page, "discard")
    generation = harness.supervisor.state.generation + 1

    assert harness.supervisor.restart_child()

    harness.page.wait_for_function(
        "() => window.__kythSentinel === undefined",
        timeout=BROWSER_TIMEOUT_MS,
    )
    _wait_for_generation(harness.supervisor, generation)


def test_failed_replacement_startup_does_not_reload_until_ready(
    resource_harness: _Harness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = resource_harness
    _set_sentinel(harness.page, "keep")
    harness.page.evaluate(
        """() => addEventListener("kyth:server-error", (event) => {
            window.__kythServerError = event.detail.message;
        })"""
    )
    generation = harness.supervisor.state.generation
    monkeypatch.setenv("KYTH_BROWSER_FAIL_STARTUP", "1")

    assert not harness.supervisor.restart_child()
    harness.page.wait_for_function(
        "() => window.__kythServerError?.includes('browser fixture startup failure')",
        timeout=BROWSER_TIMEOUT_MS,
    )
    assert harness.supervisor.state.generation == generation
    time.sleep(0.5)
    assert _sentinel(harness.page) == "keep"

    monkeypatch.delenv("KYTH_BROWSER_FAIL_STARTUP")
    assert harness.supervisor.restart_child()
    harness.page.wait_for_function(
        "() => window.__kythSentinel === undefined",
        timeout=BROWSER_TIMEOUT_MS,
    )
    _wait_for_generation(harness.supervisor, generation + 1)


def test_javascript_change_falls_back_to_full_reload(resource_harness: _Harness) -> None:
    harness = resource_harness
    _set_sentinel(harness.page, "discard")
    harness.asset("app.js").write_text(
        'window.__appScriptVersion = "two";',
        encoding="utf-8",
    )

    harness.supervisor._reload_for_browser_change((harness.asset("app.js"),))

    harness.page.wait_for_function(
        """() =>
            window.__appScriptVersion === 'two' &&
            window.__kythSentinel === undefined
        """,
        timeout=BROWSER_TIMEOUT_MS,
    )


@pytest.mark.parametrize("asset_name", ["site.css", "logo.svg"])
def test_failed_narrow_update_falls_back_to_full_reload(
    resource_harness: _Harness,
    asset_name: str,
) -> None:
    harness = resource_harness
    _set_sentinel(harness.page, "discard")
    asset = harness.asset(asset_name)
    asset.unlink()

    harness.supervisor._reload_for_browser_change((asset,))

    harness.page.wait_for_function(
        "() => window.__kythSentinel === undefined",
        timeout=BROWSER_TIMEOUT_MS,
    )


def test_two_tabs_with_distinct_resources_only_update_affected_view(resource_harness: _Harness) -> None:
    harness = resource_harness
    other = harness.context.new_page()
    other.goto(f"{harness.origin}/other/", wait_until="load")
    _wait_for_complete_views(harness.supervisor, 2)
    _set_sentinel(harness.page, "home")
    _set_sentinel(other, "other")

    harness.asset("site.css").write_text(
        "body { background-color: rgb(70, 80, 90); }",
        encoding="utf-8",
    )
    harness.supervisor._reload_for_browser_change((harness.asset("site.css"),))

    harness.page.wait_for_function(
        "() => getComputedStyle(document.body).backgroundColor === 'rgb(70, 80, 90)'",
        timeout=BROWSER_TIMEOUT_MS,
    )
    assert _sentinel(harness.page) == "home"
    assert _sentinel(other) == "other"
    assert other.evaluate("() => getComputedStyle(document.body).color") == "rgb(20, 30, 40)"


def test_dynamic_dom_resource_is_registered_and_then_updates_narrowly(
    resource_harness: _Harness,
) -> None:
    harness = resource_harness
    _set_sentinel(harness.page, "keep")
    harness.page.evaluate(
        """() => {
            const image = document.createElement('img');
            image.id = 'dynamic-logo';
            image.src = '/logo2.svg';
            image.alt = 'dynamic';
            document.body.append(image);
        }"""
    )
    _wait_for_resource_path(harness.supervisor, "/logo2.svg")
    generation = harness.supervisor.state.generation + 1
    harness.asset("logo2.svg").write_text(_svg("dynamic-two"), encoding="utf-8")

    harness.supervisor._reload_for_browser_change((harness.asset("logo2.svg"),))

    harness.page.wait_for_function(
        f"""() => document.querySelector('#dynamic-logo').src.includes(
            '__kyth_generation__={generation}'
        )""",
        timeout=BROWSER_TIMEOUT_MS,
    )
    assert _sentinel(harness.page) == "keep"


def test_duplicate_stylesheet_references_are_all_replaced(resource_harness: _Harness) -> None:
    harness = resource_harness
    harness.page.goto(f"{harness.origin}/duplicate/", wait_until="load")
    _wait_for_registered_path(harness.supervisor, "/duplicate/")
    _set_sentinel(harness.page, "keep")
    generation = harness.supervisor.state.generation + 1

    harness.asset("site.css").write_text(
        "body { background-color: rgb(100, 110, 120); }",
        encoding="utf-8",
    )
    harness.supervisor._reload_for_browser_change((harness.asset("site.css"),))

    harness.page.wait_for_function(
        f"""() => {{
            const links = Array.from(document.querySelectorAll('link[href*="site.css"]'));
            return links.length === 2 &&
                links.every((link) => link.href.includes('__kyth_generation__={generation}'));
        }}""",
        timeout=BROWSER_TIMEOUT_MS,
    )
    assert _sentinel(harness.page) == "keep"


def test_stylesheet_query_parameters_survive_cache_busting(resource_harness: _Harness) -> None:
    harness = resource_harness
    harness.page.goto(f"{harness.origin}/query/", wait_until="load")
    _wait_for_registered_path(harness.supervisor, "/query/")
    _set_sentinel(harness.page, "keep")
    generation = harness.supervisor.state.generation + 1

    harness.asset("site.css").write_text(
        "body { background-color: rgb(130, 140, 150); }",
        encoding="utf-8",
    )
    harness.supervisor._reload_for_browser_change((harness.asset("site.css"),))

    harness.page.wait_for_function(
        f"""() => {{
            const href = document.querySelector('link[rel~="stylesheet"]').href;
            return href.includes('fixture=1') &&
                href.includes('__kyth_generation__={generation}');
        }}""",
        timeout=BROWSER_TIMEOUT_MS,
    )
    assert _sentinel(harness.page) == "keep"


@pytest.mark.parametrize(
    ("route", "asset_name"),
    [
        ("/srcset/", "logo.svg"),
        ("/picture/", "logo2.svg"),
    ],
)
def test_unsafe_image_forms_fall_back_to_reload(
    resource_harness: _Harness,
    route: str,
    asset_name: str,
) -> None:
    harness = resource_harness
    harness.page.goto(f"{harness.origin}{route}", wait_until="load")
    _wait_for_registered_path(harness.supervisor, route)
    _set_sentinel(harness.page, "discard")
    asset = harness.asset(asset_name)
    asset.write_text(_svg("unsafe-update"), encoding="utf-8")

    harness.supervisor._reload_for_browser_change((asset,))

    harness.page.wait_for_function(
        "() => window.__kythSentinel === undefined",
        timeout=BROWSER_TIMEOUT_MS,
    )


def test_css_observed_asset_change_falls_back_to_reload(resource_harness: _Harness) -> None:
    harness = resource_harness
    harness.page.goto(f"{harness.origin}/background/", wait_until="load")
    _wait_for_resource_path(harness.supervisor, "/background.svg")
    _set_sentinel(harness.page, "discard")
    harness.asset("background.svg").write_text(_svg("background-two"), encoding="utf-8")

    harness.supervisor._reload_for_browser_change((harness.asset("background.svg"),))

    harness.page.wait_for_function(
        "() => window.__kythSentinel === undefined",
        timeout=BROWSER_TIMEOUT_MS,
    )


def test_font_change_falls_back_to_reload(resource_harness: _Harness) -> None:
    harness = resource_harness
    harness.page.goto(f"{harness.origin}/font/", wait_until="load")
    _wait_for_resource_path(harness.supervisor, "/font.woff2")
    _set_sentinel(harness.page, "discard")
    harness.asset("font.woff2").write_bytes(b"updated fake font")

    harness.supervisor._reload_for_browser_change((harness.asset("font.woff2"),))

    harness.page.wait_for_function(
        "() => window.__kythSentinel === undefined",
        timeout=BROWSER_TIMEOUT_MS,
    )


def test_mixed_css_and_image_batch_collapses_to_reload(resource_harness: _Harness) -> None:
    harness = resource_harness
    _set_sentinel(harness.page, "discard")
    harness.asset("site.css").write_text(
        "body { background-color: rgb(160, 170, 180); }",
        encoding="utf-8",
    )
    harness.asset("logo.svg").write_text(_svg("mixed"), encoding="utf-8")

    harness.supervisor._reload_for_browser_change((
        harness.asset("site.css"),
        harness.asset("logo.svg"),
    ))

    harness.page.wait_for_function(
        "() => window.__kythSentinel === undefined",
        timeout=BROWSER_TIMEOUT_MS,
    )


def test_multiple_stylesheets_update_atomically_without_reload(resource_harness: _Harness) -> None:
    harness = resource_harness
    harness.page.goto(f"{harness.origin}/two-css/", wait_until="load")
    _wait_for_registered_path(harness.supervisor, "/two-css/")
    _set_sentinel(harness.page, "keep")
    harness.asset("site.css").write_text(
        "body { background-color: rgb(190, 200, 210); }",
        encoding="utf-8",
    )
    harness.asset("other.css").write_text(
        "body { color: rgb(80, 90, 100); }",
        encoding="utf-8",
    )

    harness.supervisor._reload_for_browser_change((
        harness.asset("site.css"),
        harness.asset("other.css"),
    ))

    harness.page.wait_for_function(
        """() =>
            getComputedStyle(document.body).backgroundColor === 'rgb(190, 200, 210)' &&
            getComputedStyle(document.body).color === 'rgb(80, 90, 100)'
        """,
        timeout=BROWSER_TIMEOUT_MS,
    )
    assert _sentinel(harness.page) == "keep"


def test_unknown_browser_resource_change_uses_conservative_reload(resource_harness: _Harness) -> None:
    harness = resource_harness
    _set_sentinel(harness.page, "discard")
    unknown = harness.asset("unknown.js")
    unknown.write_text('window.__unknown = "two";', encoding="utf-8")

    harness.supervisor._reload_for_browser_change((unknown,))

    harness.page.wait_for_function(
        "() => window.__kythSentinel === undefined",
        timeout=BROWSER_TIMEOUT_MS,
    )


def test_direct_html_output_change_reloads_new_document(resource_harness: _Harness) -> None:
    harness = resource_harness
    _set_sentinel(harness.page, "discard")
    harness.asset("index.html").write_text(
        _page(
            "changed",
            '<link rel="stylesheet" href="/site.css">',
            '<script src="/app.js"></script>',
            '<img id="logo" src="/logo.svg" alt="test">',
        ),
        encoding="utf-8",
    )

    harness.supervisor._reload_for_browser_change((harness.asset("index.html"),))

    harness.page.wait_for_function(
        """() =>
            document.querySelector('#status').textContent === 'changed' &&
            window.__kythSentinel === undefined
        """,
        timeout=BROWSER_TIMEOUT_MS,
    )


def test_csp_page_allows_injected_client_and_control_connection(resource_harness: _Harness) -> None:
    harness = resource_harness
    harness.page.goto(f"{harness.origin}/csp/", wait_until="load")

    _wait_for_registered_path(harness.supervisor, "/csp/")

    assert harness.page.evaluate("() => document.querySelector('script[data-kyth-control]') !== null")


def test_html_fragment_without_closing_tags_still_registers(resource_harness: _Harness) -> None:
    harness = resource_harness
    harness.page.goto(f"{harness.origin}/fragment/", wait_until="load")

    _wait_for_registered_path(harness.supervisor, "/fragment/")

    assert harness.page.evaluate("() => document.querySelector('script[data-kyth-control]') !== null")


def test_missed_event_recovers_conservatively_after_sse_reconnect(resource_harness: _Harness) -> None:
    harness = resource_harness
    _set_sentinel(harness.page, "discard")
    old_generation = _single_view(harness.supervisor).generation
    harness.context.set_offline(offline=True)
    harness.page.wait_for_function(
        "() => navigator.onLine === false",
        timeout=BROWSER_TIMEOUT_MS,
    )
    harness.asset("site.css").write_text(
        "body { background-color: rgb(210, 220, 230); }",
        encoding="utf-8",
    )
    harness.supervisor._reload_for_browser_change((harness.asset("site.css"),))
    assert _single_view(harness.supervisor).generation == old_generation

    harness.context.set_offline(offline=False)
    harness.page.wait_for_function(
        "() => navigator.onLine === true",
        timeout=BROWSER_TIMEOUT_MS,
    )

    harness.page.wait_for_function(
        """() =>
            window.__kythSentinel === undefined &&
            getComputedStyle(document.body).backgroundColor === 'rgb(210, 220, 230)'
        """,
        timeout=RECONNECT_TIMEOUT_MS,
    )


def test_duplicate_reload_for_current_generation_is_ignored(resource_harness: _Harness) -> None:
    harness = resource_harness
    _set_sentinel(harness.page, "keep")
    generation = harness.supervisor.state.generation

    harness.supervisor._require_control().publish(
        ControlEvent.reload(generation, reason="duplicate-test"),
    )
    time.sleep(0.5)

    assert _sentinel(harness.page) == "keep"


def test_real_jinja_include_change_reloads_only_dependent_view(
    jinja_harness: _Harness,
) -> None:
    harness = jinja_harness
    other = harness.context.new_page()
    other.goto(f"{harness.origin}/b/", wait_until="load")
    _wait_for_complete_views(harness.supervisor, 2)
    _wait_for_render_records(harness.supervisor, 2)
    _set_sentinel(harness.page, "a")
    _set_sentinel(other, "b")
    shared = harness.asset("templates/shared.html")
    shared.write_text('<span id="shared">shared-two</span>', encoding="utf-8")

    harness.supervisor._reload_for_browser_change((shared,))

    harness.page.wait_for_function(
        """() =>
            document.querySelector('#shared').textContent === 'shared-two' &&
            window.__kythSentinel === undefined
        """,
        timeout=BROWSER_TIMEOUT_MS,
    )
    assert _sentinel(other) == "b"


def test_real_jinja_base_change_reloads_all_dependent_views(
    jinja_harness: _Harness,
) -> None:
    harness = jinja_harness
    other = harness.context.new_page()
    other.goto(f"{harness.origin}/b/", wait_until="load")
    _wait_for_complete_views(harness.supervisor, 2)
    _wait_for_render_records(harness.supervisor, 2)
    _set_sentinel(harness.page, "a")
    _set_sentinel(other, "b")
    base = harness.asset("templates/base.html")
    base.write_text(
        '<!doctype html><html data-base="two"><body>{% block content %}{% endblock %}</body></html>',
        encoding="utf-8",
    )

    harness.supervisor._reload_for_browser_change((base,))

    for page in (harness.page, other):
        page.wait_for_function(
            """() =>
                document.documentElement.dataset.base === 'two' &&
                window.__kythSentinel === undefined
            """,
            timeout=BROWSER_TIMEOUT_MS,
        )


def test_semantic_data_update_runs_handler_without_document_reload(
    resource_harness: _Harness,
) -> None:
    harness = resource_harness
    harness.page.goto(f"{harness.origin}/data/", wait_until="load")
    _wait_for_registered_path(harness.supervisor, "/data/")
    _wait_for_render_records(harness.supervisor, 1)
    _set_sentinel(harness.page, "keep")
    generation = harness.supervisor.state.generation + 1
    data = harness.asset("inventory.json")
    data.write_text('{"count": 2}', encoding="utf-8")

    harness.supervisor._reload_for_browser_change((data,))

    harness.page.wait_for_function(
        "() => document.querySelector('#count').textContent === '2'",
        timeout=BROWSER_TIMEOUT_MS,
    )
    assert _sentinel(harness.page) == "keep"
    _wait_for_generation(harness.supervisor, generation)


def test_unhandled_semantic_data_update_falls_back_to_reload(
    resource_harness: _Harness,
) -> None:
    harness = resource_harness
    harness.page.goto(f"{harness.origin}/data-unhandled/", wait_until="load")
    _wait_for_registered_path(harness.supervisor, "/data-unhandled/")
    _wait_for_render_records(harness.supervisor, 1)
    _set_sentinel(harness.page, "discard")
    data = harness.asset("inventory.json")
    data.write_text('{"count": 3}', encoding="utf-8")

    harness.supervisor._reload_for_browser_change((data,))

    harness.page.wait_for_function(
        "() => window.__kythSentinel === undefined",
        timeout=BROWSER_TIMEOUT_MS,
    )


def test_restart_worthy_generated_source_waits_for_output_after_child_ready(
    manifest_harness: _Harness,
) -> None:
    harness = manifest_harness
    _set_sentinel(harness.page, "keep")
    source = harness.asset("generator.py")
    output = harness.asset("generated.html")
    generation = harness.supervisor.state.generation + 1
    source.write_text("VERSION = 2\n", encoding="utf-8")

    harness.supervisor._handle_change_cycle(
        FileBatch.from_events([FileEvent(source, FileOperation.MODIFIED)]),
        _NoPendingBatches(),
    )

    assert harness.supervisor.state.generation == generation
    _wait_for_generation(harness.supervisor, generation)
    assert _sentinel(harness.page) == "keep"
    assert output.resolve() in harness.supervisor._generated.stale_outputs

    output.write_text(_page("generated-after-restart"), encoding="utf-8")
    harness.supervisor._handle_change_cycle(
        FileBatch.from_events([FileEvent(output, FileOperation.MODIFIED)]),
        _NoPendingBatches(),
    )

    harness.page.wait_for_function(
        """() =>
            document.querySelector('#status').textContent === 'generated-after-restart' &&
            window.__kythSentinel === undefined
        """,
        timeout=BROWSER_TIMEOUT_MS,
    )


def test_generated_source_waits_for_rebuild_before_browser_reload(
    manifest_harness: _Harness,
) -> None:
    harness = manifest_harness
    _set_sentinel(harness.page, "keep")
    source = harness.asset("content.md")
    output = harness.asset("generated.html")
    source.write_text("second", encoding="utf-8")

    harness.supervisor._handle_change_cycle(
        FileBatch.from_events([FileEvent(source, FileOperation.MODIFIED)]),
        _NoPendingBatches(),
    )

    assert _sentinel(harness.page) == "keep"
    assert output.resolve() in harness.supervisor._generated.stale_outputs

    output.write_text(_page("generated-two"), encoding="utf-8")
    harness.supervisor._handle_change_cycle(
        FileBatch.from_events([FileEvent(output, FileOperation.MODIFIED)]),
        _NoPendingBatches(),
    )

    harness.page.wait_for_function(
        """() =>
            document.querySelector('#status').textContent === 'generated-two' &&
            window.__kythSentinel === undefined
        """,
        timeout=BROWSER_TIMEOUT_MS,
    )
    assert output.resolve() not in harness.supervisor._generated.stale_outputs


def test_normal_buffered_html_is_injected(passthrough_harness: _Harness) -> None:
    harness = passthrough_harness
    harness.page.goto(f"{harness.origin}/normal/", wait_until="load")

    assert harness.page.evaluate("() => document.querySelector('script[data-kyth-control]') !== null")


@pytest.mark.parametrize(
    "route",
    ["/streaming/", "/compressed/", "/range/", "/plain/"],
)
def test_noninjectable_response_forms_remain_untouched(
    passthrough_harness: _Harness,
    route: str,
) -> None:
    harness = passthrough_harness
    harness.page.goto(f"{harness.origin}/normal/", wait_until="load")

    untouched = harness.page.evaluate(
        f"""async () => {{
            const response = await fetch({route!r});
            const body = await response.text();
            return !body.includes('data-kyth-control');
        }}"""
    )

    assert untouched is True


def _seed_jinja_fixture(root: Path) -> None:
    templates = root / "templates"
    templates.mkdir()
    templates.joinpath("base.html").write_text(
        '<!doctype html><html data-base="one"><body>{% block content %}{% endblock %}</body></html>',
        encoding="utf-8",
    )
    templates.joinpath("shared.html").write_text(
        '<span id="shared">shared-one</span>',
        encoding="utf-8",
    )
    templates.joinpath("page-a.html").write_text(
        """{% extends "base.html" %}
{% block content %}
<h1 id="status">A</h1>
{% include "shared.html" %}
{% endblock %}
""",
        encoding="utf-8",
    )
    templates.joinpath("page-b.html").write_text(
        """{% extends "base.html" %}
{% block content %}
<h1 id="status">B</h1>
{% endblock %}
""",
        encoding="utf-8",
    )


def _seed_resource_fixture(root: Path) -> None:
    root.joinpath("site.css").write_text(
        "body { background-color: rgb(10, 20, 30); }",
        encoding="utf-8",
    )
    root.joinpath("other.css").write_text(
        "body { color: rgb(20, 30, 40); }",
        encoding="utf-8",
    )
    root.joinpath("background.css").write_text(
        "body { background-image: url('/background.svg'); }",
        encoding="utf-8",
    )
    root.joinpath("logo.svg").write_text(_svg("one"), encoding="utf-8")
    root.joinpath("logo2.svg").write_text(_svg("two"), encoding="utf-8")
    root.joinpath("background.svg").write_text(_svg("background-one"), encoding="utf-8")
    root.joinpath("font.woff2").write_bytes(b"fake font")
    root.joinpath("app.js").write_text(
        'window.__appScriptVersion = "one";',
        encoding="utf-8",
    )
    root.joinpath("unknown.js").write_text(
        'window.__unknown = "one";',
        encoding="utf-8",
    )
    root.joinpath("inventory.json").write_text('{"count": 1}', encoding="utf-8")
    root.joinpath("data.html").write_text(
        """<!doctype html>
<html><head><script>
addEventListener("kyth:data-update", (event) => {
  if (event.detail.identity === "inventory") {
    event.detail.handle(
      fetch("/inventory.json")
        .then((response) => response.json())
        .then((data) => {
          document.querySelector("#count").textContent = String(data.count);
        })
    );
  }
});
</script></head><body>
<h1 id="status">data</h1><span id="count">1</span>
</body></html>
""",
        encoding="utf-8",
    )
    root.joinpath("data-unhandled.html").write_text(
        _page("data-unhandled"),
        encoding="utf-8",
    )
    root.joinpath("state.html").write_text(
        """<!doctype html>
<html><head><script>
addEventListener("kyth:before-reload", (event) => {
  event.detail.preserve({value: "preserved"});
});
addEventListener("kyth:restore-state", (event) => {
  window.__kythRestoredState = event.detail.state;
});
</script></head><body><h1 id="status">state</h1></body></html>
""",
        encoding="utf-8",
    )
    root.joinpath("index.html").write_text(
        _page(
            "home",
            '<link rel="stylesheet" href="/site.css">',
            '<script src="/app.js"></script>',
            '<img id="logo" src="/logo.svg" alt="test">',
        ),
        encoding="utf-8",
    )
    root.joinpath("other.html").write_text(
        _page(
            "other",
            '<link rel="stylesheet" href="/other.css">',
            '<img id="other-logo" src="/logo2.svg" alt="other">',
        ),
        encoding="utf-8",
    )
    root.joinpath("duplicate.html").write_text(
        _page(
            "duplicate",
            '<link rel="stylesheet" href="/site.css">',
            '<link rel="stylesheet" href="/site.css">',
        ),
        encoding="utf-8",
    )
    root.joinpath("query.html").write_text(
        _page(
            "query",
            '<link rel="stylesheet" href="/site.css?fixture=1">',
        ),
        encoding="utf-8",
    )
    root.joinpath("srcset.html").write_text(
        _page(
            "srcset",
            '<img id="logo" src="/logo.svg" srcset="/logo.svg 1x" alt="test">',
        ),
        encoding="utf-8",
    )
    root.joinpath("picture.html").write_text(
        _page(
            "picture",
            '<picture><source srcset="/logo2.svg"><img id="logo" src="/logo.svg" alt="test"></picture>',
        ),
        encoding="utf-8",
    )
    root.joinpath("background.html").write_text(
        _page(
            "background",
            '<link rel="stylesheet" href="/background.css">',
        ),
        encoding="utf-8",
    )
    root.joinpath("font.html").write_text(
        _page(
            "font",
            '<link rel="preload" as="font" href="/font.woff2" type="font/woff2">',
        ),
        encoding="utf-8",
    )
    root.joinpath("csp.html").write_text(
        _page(
            "csp",
            '<link rel="stylesheet" href="/site.css">',
        ),
        encoding="utf-8",
    )
    root.joinpath("fragment.html").write_text(
        '<h1 id="status">fragment</h1>',
        encoding="utf-8",
    )
    root.joinpath("two-css.html").write_text(
        _page(
            "two-css",
            '<link rel="stylesheet" href="/site.css">',
            '<link rel="stylesheet" href="/other.css">',
        ),
        encoding="utf-8",
    )


def _page(status: str, *elements: str) -> str:
    joined = "\n  ".join(elements)
    return (
        "<!doctype html>\n"
        "<html>\n<head>\n"
        f"  {joined}\n"
        "</head>\n<body>\n"
        f'  <h1 id="status">{status}</h1>\n'
        "</body>\n</html>\n"
    )


def _svg(label: str) -> str:
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">'
        f'<title>{label}</title><rect width="10" height="10"/>'
        "</svg>"
    )


class _AppImportPath:
    def __enter__(self) -> None:
        sys.path.insert(0, str(APP_DIR))

    def __exit__(self, *_args: object) -> None:
        sys.path.remove(str(APP_DIR))


def _app_import_path() -> _AppImportPath:
    return _AppImportPath()


def _origin(supervisor: Supervisor) -> str:
    return f"http://{supervisor.address[0]}:{supervisor.address[1]}"


def _single_view(supervisor: Supervisor) -> BrowserView:
    views = supervisor._require_control().views.snapshot()
    assert len(views) == 1
    return views[0]


def _set_sentinel(page: _Page, value: str) -> None:
    page.evaluate(f"() => {{ window.__kythSentinel = {value!r}; }}")


def _sentinel(page: _Page) -> object:
    return page.evaluate("() => window.__kythSentinel")


def _wait_for_complete_views(supervisor: Supervisor, expected: int) -> None:
    deadline = time.monotonic() + REGISTRATION_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        views = supervisor._require_control().views.snapshot()
        if len(views) == expected and all(view.resources_complete is True for view in views):
            return
        time.sleep(0.02)
    msg = f"browser did not register {expected} complete view(s)"
    raise AssertionError(msg)


def _wait_for_registered_path(supervisor: Supervisor, path: str) -> None:
    deadline = time.monotonic() + REGISTRATION_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        views = supervisor._require_control().views.snapshot()
        if any(urlsplit(view.url).path == path and view.resources_complete is True for view in views):
            return
        time.sleep(0.02)
    msg = f"browser did not register path {path}"
    raise AssertionError(msg)


def _wait_for_resource_path(supervisor: Supervisor, path: str) -> None:
    deadline = time.monotonic() + REGISTRATION_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        views = supervisor._require_control().views.snapshot()
        if any(urlsplit(resource.url).path == path for view in views for resource in view.resources):
            return
        time.sleep(0.02)
    msg = f"browser did not register resource {path}"
    raise AssertionError(msg)


def _wait_for_render_records(supervisor: Supervisor, expected: int) -> None:
    deadline = time.monotonic() + REGISTRATION_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        views = supervisor._require_control().views.snapshot()
        records = [
            supervisor._require_control().renders.get(view.render_id) for view in views if view.render_id is not None
        ]
        if len(records) == expected and all(record is not None and record.complete for record in records):
            return
        time.sleep(0.02)
    msg = f"browser did not associate {expected} complete render record(s)"
    raise AssertionError(msg)


def _wait_for_generation(supervisor: Supervisor, generation: int) -> None:
    deadline = time.monotonic() + REGISTRATION_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        views = supervisor._require_control().views.snapshot()
        if len(views) == 1 and views[0].generation == generation:
            return
        time.sleep(0.02)
    msg = f"browser did not acknowledge generation {generation}"
    raise AssertionError(msg)
