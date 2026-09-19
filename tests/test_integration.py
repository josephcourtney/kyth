from pathlib import Path

import pytest

from kyth.injection import depend_on, depend_on_data
from kyth.injection.jinja import capture_render


@pytest.mark.integration
@pytest.mark.medium
def test_depend_on_adds_explicit_dependency_to_render_record(tmp_path: Path) -> None:
    dependency = tmp_path / "settings.yaml"
    dependency.write_text("enabled: true", encoding="utf-8")

    with capture_render("render-explicit", 4) as trace:
        assert depend_on(dependency)

    record = trace.to_record()
    assert record.adapter == "explicit"
    assert record.complete
    assert len(record.dependencies) == 1
    assert record.dependencies[0].path == str(dependency.resolve())
    assert record.dependencies[0].mtime_ns is not None
    assert record.dependencies[0].size == dependency.stat().st_size


@pytest.mark.unit
@pytest.mark.small
def test_depend_on_is_safe_outside_active_render() -> None:
    assert not depend_on("/tmp/not-an-active-render")


@pytest.mark.integration
@pytest.mark.medium
def test_explicit_and_jinja_dependencies_share_one_render_record(tmp_path: Path) -> None:
    explicit = tmp_path / "data.json"
    template = tmp_path / "page.html"
    explicit.write_text("{}", encoding="utf-8")
    template.write_text("page", encoding="utf-8")

    class Template:
        filename = str(template)

    with capture_render("render-mixed", 5) as trace:
        trace.record_template(Template())
        assert depend_on(explicit)

    record = trace.to_record()
    assert record.adapter == "explicit+jinja"
    assert {Path(item.path).name for item in record.dependencies} == {"data.json", "page.html"}


@pytest.mark.integration
@pytest.mark.medium
def test_depend_on_data_records_semantic_dependency(tmp_path: Path) -> None:
    source = tmp_path / "inventory.json"
    source.write_text('{"count": 1}', encoding="utf-8")

    with capture_render("render-data", 6) as trace:
        assert depend_on_data("inventory", source)

    record = trace.to_record()
    assert record.adapter == "data"
    assert record.dependencies == ()
    assert len(record.data_dependencies) == 1
    dependency = record.data_dependencies[0]
    assert dependency.identity == "inventory"
    assert dependency.source.path == str(source.resolve())


@pytest.mark.unit
@pytest.mark.small
def test_depend_on_data_rejects_empty_identity() -> None:
    with pytest.raises(ValueError, match="identity must be non-empty"):
        depend_on_data("", "/tmp/data.json")
