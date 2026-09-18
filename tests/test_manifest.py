import json
from pathlib import Path

import pytest

from kyth.provenance import GeneratedManifestIndex, ManifestError, load_manifest


def _write_manifest(path: Path) -> None:
    path.write_text(
        json.dumps({
            "version": 1,
            "outputs": [
                {
                    "output": "public/index.html",
                    "sources": ["content/index.md", "templates/base.html"],
                },
                {
                    "output": "public/about.html",
                    "sources": ["content/about.md", "templates/base.html"],
                },
            ],
        }),
        encoding="utf-8",
    )


@pytest.mark.integration
@pytest.mark.medium
def test_manifest_loads_relative_source_to_output_dependencies(tmp_path: Path) -> None:
    manifest_path = tmp_path / "kyth-manifest.json"
    _write_manifest(manifest_path)

    manifest = load_manifest(manifest_path)

    assert [entry.output for entry in manifest.outputs] == [
        (tmp_path / "public" / "about.html").resolve(),
        (tmp_path / "public" / "index.html").resolve(),
    ]
    index_entry = next(entry for entry in manifest.outputs if entry.output.name == "index.html")
    assert index_entry.sources == (
        (tmp_path / "content" / "index.md").resolve(),
        (tmp_path / "templates" / "base.html").resolve(),
    )


@pytest.mark.integration
@pytest.mark.medium
def test_manifest_index_marks_outputs_stale_until_generated_output_changes(tmp_path: Path) -> None:
    manifest_path = tmp_path / "kyth-manifest.json"
    _write_manifest(manifest_path)
    source = tmp_path / "content" / "index.md"
    output = tmp_path / "public" / "index.html"

    index = GeneratedManifestIndex((manifest_path,))
    index.load_all()

    assert index.mark_sources_changed((source,)) == (output.resolve(),)
    assert index.stale_outputs == frozenset({output.resolve()})
    assert index.mark_outputs_updated((output,)) == (output.resolve(),)
    assert index.stale_outputs == frozenset()


@pytest.mark.integration
@pytest.mark.medium
def test_manifest_rejects_path_escape_and_unsupported_version(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text(
        json.dumps({
            "version": 1,
            "outputs": [{"output": "../outside.html", "sources": ["source.md"]}],
        }),
        encoding="utf-8",
    )
    with pytest.raises(ManifestError, match="normalized relative path"):
        load_manifest(path)

    path.write_text(json.dumps({"version": 2, "outputs": []}), encoding="utf-8")
    with pytest.raises(ManifestError, match="unsupported manifest version"):
        load_manifest(path)
