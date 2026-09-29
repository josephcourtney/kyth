from pathlib import Path

import pytest

from kyth.provenance import load_manifest

EXAMPLES = Path(__file__).parents[1] / "examples" / "e2e"
PROJECTS = {
    "generated_site",
    "integration_api",
    "jinja_site",
    "plain_asgi",
    "streaming_site",
}


@pytest.mark.integration
@pytest.mark.medium
def test_e2e_example_projects_are_syntactically_valid() -> None:
    discovered = {path.name for path in EXAMPLES.iterdir() if path.is_dir()}
    assert discovered == PROJECTS

    for project in sorted(PROJECTS):
        root = EXAMPLES / project
        assert (root / "README.md").is_file()
        assert (root / "app.py").is_file()

    python_files = sorted(EXAMPLES.rglob("*.py"), key=Path.as_posix)
    assert python_files
    for path in python_files:
        source = path.read_text(encoding="utf-8")
        compile(source, path.as_posix(), "exec")


@pytest.mark.integration
@pytest.mark.medium
def test_generated_e2e_manifest_resolves_existing_files() -> None:
    root = EXAMPLES / "generated_site"
    manifest = load_manifest(root / "kyth-manifest.json")

    assert {entry.url_path for entry in manifest.outputs} == {"/", "/notes/"}
    for entry in manifest.outputs:
        assert entry.output.is_file()
        assert all(source.is_file() for source in entry.sources)
