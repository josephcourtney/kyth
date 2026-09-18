from pathlib import Path, PurePosixPath

import pytest

from kyth.provenance import DirectOutputIndex, direct_document_relative_path


@pytest.mark.unit
@pytest.mark.small
def test_direct_document_relative_path_accepts_only_explicit_html_documents() -> None:
    assert direct_document_relative_path("http://127.0.0.1:8000/") == PurePosixPath("index.html")
    assert direct_document_relative_path("http://127.0.0.1:8000/about.html?x=1") == PurePosixPath("about.html")
    assert direct_document_relative_path("http://127.0.0.1:8000/docs/") == PurePosixPath("docs/index.html")
    assert direct_document_relative_path("http://127.0.0.1:8000/about") is None
    assert direct_document_relative_path("http://127.0.0.1:8000/%2e%2e/secret.html") is None


@pytest.mark.integration
@pytest.mark.medium
def test_direct_output_index_tracks_active_and_previously_observed_outputs(tmp_path: Path) -> None:
    index = tmp_path / "index.html"
    about = tmp_path / "about.html"
    index.write_text("<h1>Home</h1>", encoding="utf-8")
    about.write_text("<h1>About</h1>", encoding="utf-8")

    provenance = DirectOutputIndex((tmp_path,))
    provenance.reconcile(
        {
            "home": "http://127.0.0.1:8000/",
            "about": "http://127.0.0.1:8000/about.html",
            "dynamic": "http://127.0.0.1:8000/about",
        }
    )

    assert provenance.output_views == {
        index.resolve(): ("home",),
        about.resolve(): ("about",),
    }
    assert provenance.known_outputs == frozenset({index.resolve(), about.resolve()})

    provenance.reconcile({"home": "http://127.0.0.1:8000/"})

    assert provenance.output_views == {index.resolve(): ("home",)}
    assert provenance.known_outputs == frozenset({index.resolve(), about.resolve()})


@pytest.mark.integration
@pytest.mark.medium
def test_direct_output_index_rejects_ambiguous_roots(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    (first / "index.html").write_text("one", encoding="utf-8")
    (second / "index.html").write_text("two", encoding="utf-8")

    provenance = DirectOutputIndex((first, second))
    provenance.reconcile({"home": "http://127.0.0.1:8000/"})

    assert provenance.output_views == {}
    assert provenance.known_outputs == frozenset()
