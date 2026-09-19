from __future__ import annotations

import pytest

from kyth.provenance.manifest import (
    MANIFEST_VERSION,
    MAX_MANIFEST_OUTPUTS,
    MAX_SOURCES_PER_OUTPUT,
    ManifestError,
    _manifest_document,
    _manifest_outputs,
    _output_fields,
    _validate_manifest_version,
    _validate_url_path,
)

pytestmark = [
    pytest.mark.unit,
    pytest.mark.small,
]


@pytest.mark.parametrize("value", [None, [], "manifest", 1, True])
def test_manifest_document_requires_json_object(value: object) -> None:
    with pytest.raises(TypeError, match="manifest root must be a JSON object"):
        _manifest_document(value)


@pytest.mark.parametrize("version", [None, "1", True, 1.0])
def test_manifest_version_requires_integer(version: object) -> None:
    with pytest.raises(TypeError, match="manifest version must be an integer"):
        _validate_manifest_version({"version": version})


def test_manifest_version_rejects_unsupported_integer() -> None:
    with pytest.raises(ManifestError, match="unsupported manifest version"):
        _validate_manifest_version({"version": MANIFEST_VERSION + 1})


def test_manifest_version_accepts_current_version() -> None:
    _validate_manifest_version({"version": MANIFEST_VERSION})


@pytest.mark.parametrize("outputs", [None, {}, "outputs", 1, True])
def test_manifest_outputs_requires_array(outputs: object) -> None:
    with pytest.raises(TypeError, match="manifest outputs must be a JSON array"):
        _manifest_outputs({"outputs": outputs})


def test_manifest_outputs_rejects_excessive_entries() -> None:
    with pytest.raises(ManifestError, match="manifest contains too many outputs"):
        _manifest_outputs({"outputs": [None] * (MAX_MANIFEST_OUTPUTS + 1)})


@pytest.mark.parametrize(
    ("value", "message"),
    [
        (None, "each manifest output must be a JSON object"),
        ({"output": 1, "sources": []}, "manifest output path must be a string"),
        ({"output": "index.html", "sources": None}, "manifest output sources must be a JSON array"),
        (
            {"output": "index.html", "sources": ["source.md"], "url": 1},
            "manifest output url must be a string or null",
        ),
    ],
)
def test_output_fields_reject_invalid_shapes(value: object, message: str) -> None:
    with pytest.raises(TypeError, match=message):
        _output_fields(value)


def test_output_fields_rejects_excessive_sources() -> None:
    value = {
        "output": "index.html",
        "sources": ["source.md"] * (MAX_SOURCES_PER_OUTPUT + 1),
    }

    with pytest.raises(ManifestError, match="manifest output contains too many sources"):
        _output_fields(value)


def test_output_fields_preserves_optional_url() -> None:
    assert _output_fields({
        "output": "index.html",
        "sources": ["source.md"],
        "url": "/docs/",
    }) == ("index.html", ["source.md"], "/docs/")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("/", "/"),
        ("/about", "/about"),
        ("/about/", "/about/"),
        ("/space%20name/", "/space name/"),
    ],
)
def test_manifest_url_accepts_absolute_normalized_paths(value: str, expected: str) -> None:
    assert _validate_url_path(value) == expected


@pytest.mark.parametrize(
    ("value", "message"),
    [
        ("https://example.com/about", "path only"),
        ("//example.com/about", "path only"),
        ("/about?preview=1", "path only"),
        ("/about#section", "path only"),
        ("about/", "must be absolute"),
        ("", "must be absolute"),
        ("/a//b", "must be normalized"),
        ("/a/./b", "must be normalized"),
        ("/a/../b", "must be normalized"),
        ("/a/%2e%2e/b", "must be normalized"),
    ],
)
def test_manifest_url_rejects_non_path_or_non_normalized_forms(
    value: str,
    message: str,
) -> None:
    with pytest.raises(ManifestError, match=message):
        _validate_url_path(value)
