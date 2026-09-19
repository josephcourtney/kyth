import json
from functools import partial
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
                    "url": "/",
                    "sources": ["content/index.md", "templates/base.html"],
                },
                {
                    "output": "public/about.html",
                    "url": "/about/",
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
    assert index_entry.url_path == "/"


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


@pytest.mark.integration
@pytest.mark.medium
def test_manifest_explicit_urls_map_active_views_to_generated_outputs(tmp_path: Path) -> None:
    manifest_path = tmp_path / "kyth-manifest.json"
    _write_manifest(manifest_path)
    index = GeneratedManifestIndex((manifest_path,))
    index.load_all()

    views = index.output_views({
        "home": "http://127.0.0.1:8000/?preview=1",
        "about": "http://127.0.0.1:8000/about/",
        "dynamic": "http://127.0.0.1:8000/dynamic",
    })

    assert views == {
        (tmp_path / "public" / "about.html").resolve(): ("about",),
        (tmp_path / "public" / "index.html").resolve(): ("home",),
    }


@pytest.mark.integration
@pytest.mark.medium
@pytest.mark.parametrize(
    ("payload", "error_type", "message"),
    [
        (
            {"version": 1, "outputs": [{"output": "public/index.txt", "sources": ["source.md"]}]},
            ManifestError,
            "manifest output must be HTML",
        ),
        (
            {"version": 1, "outputs": [{"output": "public/index.html", "sources": []}]},
            ManifestError,
            "must declare at least one source",
        ),
        (
            {"version": 1, "outputs": [{"output": "public/index.html", "sources": [1]}]},
            TypeError,
            "manifest source path must be a string",
        ),
        (
            {
                "version": 1,
                "outputs": [
                    {"output": "public/index.html", "sources": ["a.md"]},
                    {"output": "public/index.html", "sources": ["b.md"]},
                ],
            },
            ManifestError,
            "manifest output paths must be unique",
        ),
        (
            {
                "version": 1,
                "outputs": [
                    {"output": "public/a.html", "url": "/same/", "sources": ["a.md"]},
                    {"output": "public/b.html", "url": "/same/", "sources": ["b.md"]},
                ],
            },
            ManifestError,
            "generated URL is declared by multiple outputs",
        ),
    ],
)
def test_manifest_rejects_semantically_invalid_outputs(
    tmp_path: Path,
    payload: object,
    error_type: type[Exception],
    message: str,
) -> None:
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    if message == "generated URL is declared by multiple outputs":
        invalid_load = GeneratedManifestIndex((path,)).load_all
    else:
        invalid_load = partial(load_manifest, path)

    with pytest.raises(error_type, match=message):
        invalid_load()


@pytest.mark.integration
@pytest.mark.medium
def test_manifest_load_wraps_missing_file_and_invalid_json(tmp_path: Path) -> None:
    missing = tmp_path / "missing.json"
    with pytest.raises(ManifestError, match="cannot load manifest"):
        load_manifest(missing)

    invalid = tmp_path / "invalid.json"
    invalid.write_text("{not-json", encoding="utf-8")
    with pytest.raises(ManifestError, match="cannot load manifest"):
        load_manifest(invalid)


@pytest.mark.integration
@pytest.mark.medium
def test_manifest_deduplicates_sources_and_normalizes_order(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    path.write_text(
        json.dumps({
            "version": 1,
            "outputs": [
                {
                    "output": "public/index.html",
                    "sources": ["z.md", "a.md", "z.md"],
                }
            ],
        }),
        encoding="utf-8",
    )

    manifest = load_manifest(path)

    assert manifest.outputs[0].sources == (
        (tmp_path / "a.md").resolve(),
        (tmp_path / "z.md").resolve(),
    )


@pytest.mark.integration
@pytest.mark.medium
def test_manifest_reload_is_transactional_on_invalid_replacement(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    _write_manifest(path)
    index = GeneratedManifestIndex((path,))
    index.load_all()
    known_outputs = index.known_outputs
    known_sources = index.known_sources
    url_outputs = index.url_outputs

    path.write_text(json.dumps({"version": 2, "outputs": []}), encoding="utf-8")

    with pytest.raises(ManifestError, match="unsupported manifest version"):
        index.reload_changed((path,))

    assert index.known_outputs == known_outputs
    assert index.known_sources == known_sources
    assert index.url_outputs == url_outputs


@pytest.mark.integration
@pytest.mark.medium
def test_manifest_index_rejects_output_declared_by_multiple_manifests(tmp_path: Path) -> None:
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    payload = {
        "version": 1,
        "outputs": [
            {
                "output": "public/index.html",
                "sources": ["source.md"],
            }
        ],
    }
    first.write_text(json.dumps(payload), encoding="utf-8")
    second.write_text(json.dumps(payload), encoding="utf-8")

    index = GeneratedManifestIndex((first, second))

    with pytest.raises(ManifestError, match="generated output is declared by multiple manifests"):
        index.load_all()
