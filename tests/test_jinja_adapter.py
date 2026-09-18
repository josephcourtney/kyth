from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING

import pytest

import kyth.injection.jinja as jinja_adapter
from kyth.injection.jinja import capture_render, install_jinja_tracing

if TYPE_CHECKING:
    from pytest import MonkeyPatch


@pytest.mark.integration
@pytest.mark.medium
def test_jinja_adapter_captures_runtime_selected_template_dependencies(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    for name in ("page.html", "base.html", "include-a.html", "macros.html"):
        (tmp_path / name).write_text(name, encoding="utf-8")

    class FakeEnvironment:
        def get_template(self, name: str) -> FakeTemplate:
            return FakeTemplate(self, tmp_path / name)

        def select_template(self, names: tuple[str, ...]) -> FakeTemplate:
            return self.get_template(names[0])

    class FakeTemplate:
        def __init__(self, environment: FakeEnvironment, path: Path) -> None:
            self.environment = environment
            self.filename = str(path)

        def render(self, include_name: str) -> str:
            self.environment.get_template("base.html")
            self.environment.get_template(include_name)
            self.environment.select_template(("macros.html",))
            return "rendered"

        async def render_async(self, include_name: str) -> str:
            await asyncio.sleep(0)
            return self.render(include_name)

    module = SimpleNamespace(Environment=FakeEnvironment, Template=FakeTemplate)
    monkeypatch.setattr(jinja_adapter.importlib, "import_module", lambda _name: module)

    assert install_jinja_tracing()
    environment = FakeEnvironment()
    with capture_render("render-1", 7) as trace:
        environment.get_template("page.html").render("include-a.html")

    record = trace.to_record()
    assert record.complete
    assert record.adapter == "jinja"
    assert record.render_id == "render-1"
    assert record.generation == 7
    assert {Path(item.path).name for item in record.dependencies} == {
        "page.html",
        "base.html",
        "include-a.html",
        "macros.html",
    }


@pytest.mark.unit
@pytest.mark.small
def test_jinja_trace_marks_non_file_template_incomplete() -> None:
    with capture_render("render-2", 1) as trace:
        trace.record_template(SimpleNamespace(filename=None))

    record = trace.to_record()
    assert not record.complete
    assert record.dependencies == ()
