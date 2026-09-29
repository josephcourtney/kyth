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
    from collections.abc import Callable, Iterator
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
    executable = Path(sys.executable).with_name("kyth")
    assert executable.is_file(), f"Kyth console script not found next to {sys.executable}"
    return executable


def _start_cli(root: Path, *extra_args: str) -> _CliServer:
    log_path = root / "kyth-e2e.log"
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
    split = urlsplit(server.origin)
    assert split.hostname is not None
    assert split.port is not None
    deadline = time.monotonic() + SERVER_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        connection = http.client.HTTPConnection(split.hostname, split.port, timeout=0.25)
        try:
            connection.request("GET", "/")
            response = connection.getresponse()
            response.read()
            if response.status < 500:
                return
        except (OSError, http.client.HTTPException):
            pass
        finally:
            connection.close()
        if server.process.poll() is not None:
            pytest.fail(f"Kyth exited before serving HTTP:\n{server.log()}")
        time.sleep(0.02)
    pytest.fail(f"Kyth never became reachable:\n{server.log()}")


def _replace(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    assert old in text
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


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


def _wait_log(server: _CliServer, text: str) -> None:
    deadline = time.monotonic() + SERVER_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if text in server.log():
            return
        if server.process.poll() is not None:
            pytest.fail(f"Kyth exited while waiting for log text {text!r}:\n{server.log()}")
        time.sleep(0.02)
    pytest.fail(f"Kyth never logged {text!r}:\n{server.log()}")


@pytest.mark.parametrize("example_name", ["plain_asgi"])
def test_plain_asgi_field_workflow(
    tmp_path: Path,
    e2e_browser: _Browser,
    example_name: str,
) -> None:
    root = _copy_example(tmp_path, example_name)
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
        _replace(
            root / "static" / "app.js",
            "JavaScript loaded.",
            "JavaScript reloaded.",
        )
        _wait_text(home, "JavaScript reloaded.")
        _wait_text(about, "JavaScript reloaded.")
        _wait_probe_lost(home, "js-home")
        _wait_probe_lost(about, "js-about")

        _set_probe(home, "python-home")
        _set_probe(about, "python-about")
        _replace(
            root / "app.py",
            "Direct resources are visible below.",
            "Python restart reached home.",
        )
        _replace(
            root / "app.py",
            "This is an independent browser view.",
            "Python restart reached about.",
        )
        _wait_text(home, "Python restart reached home.")
        _wait_text(about, "Python restart reached about.")
        _wait_probe_lost(home, "python-home")
        _wait_probe_lost(about, "python-about")

        valid_app = (root / "app.py").read_text(encoding="utf-8")
        _set_probe(home, "broken-home")
        _set_probe(about, "broken-about")
        (root / "app.py").write_text(
            f"{valid_app}\nthis is not valid python ???\n",
            encoding="utf-8",
        )
        _wait_log(server, "application startup failed")
        _assert_probe(home, "broken-home")
        _assert_probe(about, "broken-about")

        (root / "app.py").write_text(valid_app, encoding="utf-8")
        _wait_probe_lost(home, "broken-home")
        _wait_probe_lost(about, "broken-about")
        assert server.process.poll() is None
    finally:
        context.close()
        server.stop()
