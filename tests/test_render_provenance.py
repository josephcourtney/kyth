from pathlib import Path

import pytest

from kyth.model import RenderRecord, SourceVersion
from kyth.provenance import RenderProvenanceIndex


@pytest.mark.integration
@pytest.mark.medium
def test_render_provenance_indexes_dependencies_and_completeness() -> None:
    base = SourceVersion("/templates/base.html", 10, 100)
    first = SourceVersion("/templates/first.html", 11, 101)
    second = SourceVersion("/templates/second.html", 12, 102)
    records = (
        RenderRecord("render-first", 1, (base, first), True, "jinja"),
        RenderRecord("render-second", 1, (base, second), False, "jinja"),
    )

    index = RenderProvenanceIndex()
    index.reconcile(
        records,
        {
            "first-view": "render-first",
            "second-view": "render-second",
        },
    )

    normalized_base = Path("/templates/base.html").resolve(strict=False)
    normalized_first = Path("/templates/first.html").resolve(strict=False)
    normalized_second = Path("/templates/second.html").resolve(strict=False)
    assert index.known_sources == frozenset({
        normalized_base,
        normalized_first,
        normalized_second,
    })
    assert index.source_views[normalized_base] == ("first-view", "second-view")
    assert index.source_views[normalized_first] == ("first-view",)
    assert index.complete_view_ids == frozenset({"first-view"})
    assert index.source_view_versions[normalized_base]["first-view"] == base


@pytest.mark.integration
@pytest.mark.medium
def test_render_provenance_skips_view_already_rendered_from_current_source_version(tmp_path: Path) -> None:
    source = tmp_path / "page.html"
    source.write_text("first", encoding="utf-8")
    stat = source.stat()
    version = SourceVersion(str(source.resolve()), stat.st_mtime_ns, stat.st_size)
    record = RenderRecord("render", 1, (version,), True, "jinja")

    index = RenderProvenanceIndex()
    index.reconcile((record,), {"view": "render"})

    assert index.stale_source_views((source,)) == {}

    source.write_text("second version", encoding="utf-8")

    assert index.stale_source_views((source,)) == {
        source.resolve(): ("view",),
    }
