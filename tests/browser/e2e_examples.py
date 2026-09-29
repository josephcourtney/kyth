from __future__ import annotations

import http.client
import importlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, cast
from urllib.parse import urlsplit

import pytest

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator, Sequence
    from types import TracebackType

pytestmark = [
    pytest.mark.system,
    pytest.mark.acceptance,
    pytest.mark.ui,
    pytest.mark.medium,
]

REPO_ROOT = Path(__file__).parents[2]
EXAMPLE_ROOT = REPO_ROOT / "examples" / "e2e"
BROWSER_TIMEOUT_MS = 10_000
SERVER_TIMEOUT_SECONDS = 10.0
WATCH_SETTLE_SECONDS = 0.75


class _Page(Protocol):
    def goto(self, url: str, *, wait_until: str) -> object: ...
    def evaluate(self, expression: str) -> object: ...
    def wait_for_function(self, expression: str, *, timeout: float) -> object: ...


class _BrowserContext(Protocol):
    def new_page(self) -> _Page: ...
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


@dataclass(slots=True)
class _CliServer:
    process: subprocess.Popen[str]
    root: Path
    log_path: Path
    origin: str

    def log(self) -> str:
        return self.log_path.read_text(encoding="utf-8")

    def stop(self) -> None:
        if self.process.poll() is not None:
            return
        if os.name == "posix":
            self.process.send_signal(signal.SIGINT)
        else:
            self.process.terminate()
        try:
            self.process.wait(timeout=5.0)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=5.0)


@pytest.fixture(
    scope="session",
    params=("chromium", "firefox"),
    ids=("chromium", "firefox"),
)
def e2e_browser(request: pytest.FixtureRequest) -> Iterator[_Browser]:
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


def _copy_example(tmp_path: Path, name: str) -> Path:
    target = tmp_path / name
    shutil.copytree(EXAMPLE_ROOT / name, target)
    return target


def _kyth_executable() -> Path:
    executable = shutil.which("kyth")
    assert executable is not None, "Kyth console script is not on PATH"
    return Path(executable)


def _start_cli(root: Path, *extra_args: str) -> _CliServer:
    log_path = root.parent / f"{root.name}-kyth-e2e.log"
    command = [
        str(_kyth_executable()),
        "app:app",
        "--port",
        "0",
        "--verbose",
        *extra_args,
    ]
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    with log_path.open("w", encoding="utf-8") as log_file:
        process = subprocess.Popen(
            command,
            cwd=root,
            env=environment,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            text=True,
        )

    deadline = time.monotonic() + SERVER_TIMEOUT_SECONDS
    pattern = re.compile(r"application listening on 127\.0\.0\.1:(\d+)")
    origin: str | None = None
    while time.monotonic() < deadline:
        if process.poll() is not None:
            pytest.fail(f"Kyth exited during startup:\n{log_path.read_text(encoding='utf-8')}")
        match = pattern.search(log_path.read_text(encoding="utf-8"))
        if match is not None:
            origin = f"http://127.0.0.1:{match.group(1)}"
            break
        time.sleep(0.02)

    if origin is None:
        process.kill()
        pytest.fail(f"Kyth did not report a listening address:\n{log_path.read_text(encoding='utf-8')}")

    server = _CliServer(process=process, root=root, log_path=log_path, origin=origin)
    _wait_for_http(server)
    return server


def _wait_for_http(server: _CliServer) -> None:
    deadline = time.monotonic() + SERVER_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        try:
            status, _, _ = _http_get(server, "/")
        except (OSError, http.client.HTTPException):
            status = 500
        if status < 500:
            return
        if server.process.poll() is not None:
            pytest.fail(f"Kyth exited before serving HTTP:\n{server.log()}")
        time.sleep(0.02)
    pytest.fail(f"Kyth never became reachable:\n{server.log()}")


def _http_get(server: _CliServer, path: str) -> tuple[int, dict[str, str], bytes]:
    split = urlsplit(server.origin)
    assert split.hostname is not None
    assert split.port is not None
    connection = http.client.HTTPConnection(split.hostname, split.port, timeout=1.0)
    try:
        connection.request("GET", path)
        response = connection.getresponse()
        body = response.read()
        headers = {name.lower(): value for name, value in response.getheaders()}
        return response.status, headers, body
    finally:
        connection.close()


def _replace(path: Path, old: str, new: str) -> None:
    _replace_many(path, ((old, new),))


def _replace_many(path: Path, replacements: Sequence[tuple[str, str]]) -> None:
    text = path.read_text(encoding="utf-8")
    for old, new in replacements:
        assert old in text
        text = text.replace(old, new, 1)
    path.write_text(text, encoding="utf-8")


def _append(path: Path, text: str) -> None:
    path.write_text(path.read_text(encoding="utf-8") + text, encoding="utf-8")


def _run_build(root: Path, target: str) -> None:
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    subprocess.run(
        [sys.executable, "build.py", target],
        cwd=root,
        env=environment,
        check=True,
    )


def _set_probe(page: _Page, value: str) -> None:
    page.evaluate(f"window.__kythProbe = {json.dumps(value)}")


def _assert_probe(page: _Page, value: str) -> None:
    assert page.evaluate("window.__kythProbe") == value


def _wait_probe_lost(page: _Page, value: str) -> None:
    page.wait_for_function(
        f"window.__kythProbe !== {json.dumps(value)}",
        timeout=BROWSER_TIMEOUT_MS,
    )


def _wait_text(page: _Page, text: str) -> None:
    page.wait_for_function(
        f"document.body.textContent.includes({json.dumps(text)})",
        timeout=BROWSER_TIMEOUT_MS,
    )


def _wait_log(server: _CliServer, text: str, *, occurrences: int = 1) -> None:
    deadline = time.monotonic() + SERVER_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if server.log().count(text) >= occurrences:
            return
        if server.process.poll() is not None:
            pytest.fail(f"Kyth exited while waiting for log text {text!r}:\n{server.log()}")
        time.sleep(0.02)
    pytest.fail(f"Kyth never logged {text!r} {occurrences} time(s):\n{server.log()}")


def test_plain_asgi_field_workflow(tmp_path: Path, e2e_browser: _Browser) -> None:
    root = _copy_example(tmp_path, "plain_asgi")
    server = _start_cli(root)
    context = e2e_browser.new_context()
    try:
        home = context.new_page()
        about = context.new_page()
        home.goto(server.origin, wait_until="load")
        about.goto(f"{server.origin}/about", wait_until="load")

        _set_probe(home, "css-home")
        _set_probe(about, "css-about")
        _replace(root / "static" / "site.css", "max-width: 48rem;", "max-width: 32rem;")
        home.wait_for_function(
            "getComputedStyle(document.body).maxWidth === '512px'",
            timeout=BROWSER_TIMEOUT_MS,
        )
        about.wait_for_function(
            "getComputedStyle(document.body).maxWidth === '512px'",
            timeout=BROWSER_TIMEOUT_MS,
        )
        _assert_probe(home, "css-home")
        _assert_probe(about, "css-about")

        _set_probe(home, "svg-home")
        initial_src = cast("str", home.evaluate("document.querySelector('img').currentSrc"))
        _replace(root / "static" / "badge.svg", 'fill="#5e81ac"', 'fill="#bf616a"')
        home.wait_for_function(
            f"document.querySelector('img').currentSrc !== {json.dumps(initial_src)}",
            timeout=BROWSER_TIMEOUT_MS,
        )
        _assert_probe(home, "svg-home")

        _set_probe(home, "js-home")
        _set_probe(about, "js-about")
        _replace(root / "static" / "app.js", "JavaScript loaded.", "JavaScript reloaded.")
        _wait_text(home, "JavaScript reloaded.")
        _wait_text(about, "JavaScript reloaded.")
        _wait_probe_lost(home, "js-home")
        _wait_probe_lost(about, "js-about")

        _set_probe(home, "python-home")
        _set_probe(about, "python-about")
        _replace_many(
            root / "app.py",
            (
                ("Direct resources are visible below.", "Python restart reached home."),
                ("This is an independent browser view.", "Python restart reached about."),
            ),
        )
        _wait_text(home, "Python restart reached home.")
        _wait_text(about, "Python restart reached about.")
        _wait_probe_lost(home, "python-home")
        _wait_probe_lost(about, "python-about")

        app_path = root / "app.py"
        valid_app = app_path.read_text(encoding="utf-8")
        _set_probe(home, "broken-home")
        _set_probe(about, "broken-about")
        app_path.write_text(f"{valid_app}\nthis is not valid python ???\n", encoding="utf-8")
        _wait_log(server, "application startup failed")
        _assert_probe(home, "broken-home")
        _assert_probe(about, "broken-about")

        app_path.write_text(valid_app, encoding="utf-8")
        _wait_probe_lost(home, "broken-home")
        _wait_probe_lost(about, "broken-about")
        assert server.process.poll() is None
    finally:
        context.close()
        server.stop()


def test_jinja_field_workflow(tmp_path: Path, e2e_browser: _Browser) -> None:
    root = _copy_example(tmp_path, "jinja_site")
    server = _start_cli(root)
    context = e2e_browser.new_context()
    try:
        home = context.new_page()
        about = context.new_page()
        home.goto(server.origin, wait_until="load")
        about.goto(f"{server.origin}/about", wait_until="load")

        _set_probe(home, "home-include")
        _set_probe(about, "about-include")
        _replace(
            root / "templates" / "_home_panel.html",
            "This include is used only by the home route.",
            "The home-only include changed.",
        )
        _wait_text(home, "The home-only include changed.")
        _wait_probe_lost(home, "home-include")
        _assert_probe(about, "about-include")

        _set_probe(home, "home-about-template")
        _set_probe(about, "about-template")
        _replace(
            root / "templates" / "about.html",
            "This template is independent of the home-only include.",
            "The about template changed independently.",
        )
        _wait_text(about, "The about template changed independently.")
        _wait_probe_lost(about, "about-template")
        _assert_probe(home, "home-about-template")

        _set_probe(home, "base-home")
        _set_probe(about, "base-about")
        _replace(root / "templates" / "base.html", "<body>", '<body data-field-test="base">')
        home.wait_for_function(
            "document.body.dataset.fieldTest === 'base'",
            timeout=BROWSER_TIMEOUT_MS,
        )
        about.wait_for_function(
            "document.body.dataset.fieldTest === 'base'",
            timeout=BROWSER_TIMEOUT_MS,
        )
        _wait_probe_lost(home, "base-home")
        _wait_probe_lost(about, "base-about")

        _set_probe(home, "jinja-css-home")
        _set_probe(about, "jinja-css-about")
        _replace(root / "static" / "site.css", "max-width: 46rem;", "max-width: 38rem;")
        home.wait_for_function(
            "getComputedStyle(document.body).maxWidth === '608px'",
            timeout=BROWSER_TIMEOUT_MS,
        )
        about.wait_for_function(
            "getComputedStyle(document.body).maxWidth === '608px'",
            timeout=BROWSER_TIMEOUT_MS,
        )
        _assert_probe(home, "jinja-css-home")
        _assert_probe(about, "jinja-css-about")

        _set_probe(home, "jinja-python-home")
        _set_probe(about, "jinja-python-about")
        _append(root / "app.py", "\nFIELD_TEST_RESTART = 1\n")
        _wait_probe_lost(home, "jinja-python-home")
        _wait_probe_lost(about, "jinja-python-about")
        assert server.process.poll() is None
    finally:
        context.close()
        server.stop()


def test_generated_site_field_workflow(tmp_path: Path, e2e_browser: _Browser) -> None:
    root = _copy_example(tmp_path, "generated_site")
    server = _start_cli(root, "--manifest", "kyth-manifest.json")
    context = e2e_browser.new_context()
    try:
        home = context.new_page()
        notes = context.new_page()
        home.goto(server.origin, wait_until="load")
        notes.goto(f"{server.origin}/notes/", wait_until="load")

        _set_probe(home, "generated-home")
        _set_probe(notes, "generated-notes")
        (root / "content" / "home.txt").write_text("Home content changed.\n", encoding="utf-8")
        _wait_log(server, "generated output(s) stale; waiting for rebuild")
        _assert_probe(home, "generated-home")
        _assert_probe(notes, "generated-notes")
        _run_build(root, "home")
        _wait_text(home, "Home content changed.")
        _wait_probe_lost(home, "generated-home")
        _assert_probe(notes, "generated-notes")

        _set_probe(home, "notes-source-home")
        _set_probe(notes, "notes-source-notes")
        (root / "content" / "notes.txt").write_text("Notes content changed.\n", encoding="utf-8")
        _wait_log(server, "generated output(s) stale; waiting for rebuild", occurrences=2)
        _assert_probe(home, "notes-source-home")
        _assert_probe(notes, "notes-source-notes")
        _run_build(root, "notes")
        _wait_text(notes, "Notes content changed.")
        _wait_probe_lost(notes, "notes-source-notes")
        _assert_probe(home, "notes-source-home")

        _set_probe(home, "generator-home")
        _set_probe(notes, "generator-notes")
        _append(root / "build.py", "\n# shared generator field-test edit\n")
        _wait_log(server, "2 generated view(s) deferred")
        _assert_probe(home, "generator-home")
        _assert_probe(notes, "generator-notes")
        _run_build(root, "home")
        _wait_probe_lost(home, "generator-home")
        _assert_probe(notes, "generator-notes")
        _run_build(root, "notes")
        _wait_probe_lost(notes, "generator-notes")

        _set_probe(home, "generated-css-home")
        _set_probe(notes, "generated-css-notes")
        _replace(root / "public" / "site.css", "max-width: 44rem;", "max-width: 36rem;")
        home.wait_for_function(
            "getComputedStyle(document.body).maxWidth === '576px'",
            timeout=BROWSER_TIMEOUT_MS,
        )
        notes.wait_for_function(
            "getComputedStyle(document.body).maxWidth === '576px'",
            timeout=BROWSER_TIMEOUT_MS,
        )
        _assert_probe(home, "generated-css-home")
        _assert_probe(notes, "generated-css-notes")
    finally:
        context.close()
        server.stop()


def test_streaming_and_gzip_field_workflow(tmp_path: Path, e2e_browser: _Browser) -> None:
    root = _copy_example(tmp_path, "streaming_site")
    server = _start_cli(root)
    context = e2e_browser.new_context()
    try:
        stream = context.new_page()
        gzip_page = context.new_page()
        stream.goto(f"{server.origin}/stream", wait_until="load")
        gzip_page.goto(f"{server.origin}/gzip", wait_until="load")

        status, headers, body = _http_get(server, "/gzip")
        assert status == 200
        assert headers["content-encoding"] == "gzip"
        assert body.startswith(b"\x1f\x8b")
        _wait_text(gzip_page, "Gzip HTML")

        _set_probe(stream, "stream-css")
        _set_probe(gzip_page, "gzip-css")
        _replace(root / "static" / "site.css", "max-width: 46rem;", "max-width: 38rem;")
        stream.wait_for_function(
            "getComputedStyle(document.body).maxWidth === '608px'",
            timeout=BROWSER_TIMEOUT_MS,
        )
        gzip_page.wait_for_function(
            "getComputedStyle(document.body).maxWidth === '608px'",
            timeout=BROWSER_TIMEOUT_MS,
        )
        _assert_probe(stream, "stream-css")
        _assert_probe(gzip_page, "gzip-css")

        _set_probe(stream, "stream-python")
        _set_probe(gzip_page, "gzip-python")
        _append(root / "app.py", "\nFIELD_TEST_RESTART = 1\n")
        _wait_probe_lost(stream, "stream-python")
        _wait_probe_lost(gzip_page, "gzip-python")

        _set_probe(stream, "stream-pass-through")
        _set_probe(gzip_page, "gzip-pass-through")
        _replace(root / "app.py", "  {client_script()}\n", "")
        _wait_probe_lost(stream, "stream-pass-through")
        _wait_probe_lost(gzip_page, "gzip-pass-through")

        _set_probe(stream, "stream-unsynchronized")
        _set_probe(gzip_page, "gzip-unsynchronized")
        _replace(root / "static" / "site.css", "max-width: 38rem;", "max-width: 30rem;")
        time.sleep(WATCH_SETTLE_SECONDS)
        _assert_probe(stream, "stream-unsynchronized")
        _assert_probe(gzip_page, "gzip-unsynchronized")
        assert stream.evaluate("getComputedStyle(document.body).maxWidth") == "608px"
        assert gzip_page.evaluate("getComputedStyle(document.body).maxWidth") == "608px"
    finally:
        context.close()
        server.stop()


def test_explicit_integration_field_workflow(tmp_path: Path, e2e_browser: _Browser) -> None:
    root = _copy_example(tmp_path, "integration_api")
    server = _start_cli(root, "--restart-on", "ready.flag")
    context = e2e_browser.new_context()
    try:
        home = context.new_page()
        other = context.new_page()
        home.goto(server.origin, wait_until="load")
        other.goto(f"{server.origin}/other", wait_until="load")

        _set_probe(home, "dependency-home")
        _set_probe(other, "dependency-other")
        (root / "content" / "page.txt").write_text(
            "The explicit render dependency changed.\n",
            encoding="utf-8",
        )
        _wait_text(home, "The explicit render dependency changed.")
        _wait_probe_lost(home, "dependency-home")
        _assert_probe(other, "dependency-other")

        _set_probe(home, "counter-home")
        (root / "data" / "counter.json").write_text('{"value": 2}\n', encoding="utf-8")
        home.wait_for_function(
            "document.querySelector('#counter').textContent === '2'",
            timeout=BROWSER_TIMEOUT_MS,
        )
        _assert_probe(home, "counter-home")

        home.evaluate("document.querySelector('#draft').value = 'preserve this draft'")
        _set_probe(home, "draft-home")
        _set_probe(other, "draft-other")
        _append(root / "app.py", "\nFIELD_TEST_RESTART = 1\n")
        _wait_probe_lost(home, "draft-home")
        _wait_probe_lost(other, "draft-other")
        home.wait_for_function(
            "document.querySelector('#draft').value === 'preserve this draft'",
            timeout=BROWSER_TIMEOUT_MS,
        )

        _set_probe(home, "blocked-home")
        _set_probe(other, "blocked-other")
        (root / "ready.flag").write_text("blocked\n", encoding="utf-8")
        home.wait_for_function(
            "document.querySelector('#server-error').textContent.length > 0",
            timeout=BROWSER_TIMEOUT_MS,
        )
        _assert_probe(home, "blocked-home")
        _assert_probe(other, "blocked-other")

        (root / "ready.flag").write_text("ready\n", encoding="utf-8")
        _wait_probe_lost(home, "blocked-home")
        _wait_probe_lost(other, "blocked-other")
        assert server.process.poll() is None
    finally:
        context.close()
        server.stop()
