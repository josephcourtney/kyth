from pathlib import Path

import pytest

from kyth.fallback import FallbackScopeIndex, FallbackScopeRule, scope_view_mapping


@pytest.mark.unit
@pytest.mark.small
def test_rule_validation_rejects_malformed_patterns() -> None:
    with pytest.raises(ValueError, match="relative POSIX"):
        FallbackScopeRule("/templates/**", "/admin/**")
    with pytest.raises(ValueError, match="absolute path glob"):
        FallbackScopeRule("templates/**", "admin/**")
    with pytest.raises(ValueError, match="normalized"):
        FallbackScopeRule("templates/../shared/**", "/admin/**")
    with pytest.raises(ValueError, match="normalized"):
        FallbackScopeRule("templates/**", "/admin//**")


@pytest.mark.unit
@pytest.mark.small
def test_nested_roots_union_matching_source_rules() -> None:
    root = Path("/project")
    nested = root / "content"
    source = nested / "docs" / "guide.md"
    rules = (
        FallbackScopeRule("content/docs/**", "/docs/**"),
        FallbackScopeRule("docs/**", "/nested/**"),
    )
    index = FallbackScopeIndex((root, nested), rules)

    matched = index.source_rules(source)

    assert matched == rules


@pytest.mark.unit
@pytest.mark.small
def test_recursive_glob_matches_zero_or_many_segments() -> None:
    root = Path("/project")
    index = FallbackScopeIndex(
        (root,),
        (FallbackScopeRule("content/**", "/docs/**"),),
    )

    assert index.source_rules(root / "content" / "index.md")
    assert index.source_rules(root / "content" / "guides" / "advanced" / "index.md")


@pytest.mark.unit
@pytest.mark.small
def test_scope_resolution_ignores_query_and_fragment() -> None:
    root = Path("/project")
    source = root / "content" / "guide.md"
    index = FallbackScopeIndex(
        (root,),
        (FallbackScopeRule("content/**", "/docs/**"),),
    )

    resolutions = index.resolve(
        (source,),
        {
            "docs": "http://127.0.0.1:8000/docs/guide/?mode=preview#section",
            "admin": "http://127.0.0.1:8000/admin/",
        },
    )

    assert len(resolutions) == 1
    assert resolutions[0].view_ids == ("docs",)
    assert scope_view_mapping(resolutions) == {source: ("docs",)}


@pytest.mark.unit
@pytest.mark.small
def test_matching_scope_with_no_active_matching_view_resolves_empty() -> None:
    root = Path("/project")
    source = root / "content" / "guide.md"
    index = FallbackScopeIndex(
        (root,),
        (FallbackScopeRule("content/**", "/docs/**"),),
    )

    resolutions = index.resolve(
        (source,),
        {"admin": "http://127.0.0.1:8000/admin/"},
    )

    assert len(resolutions) == 1
    assert resolutions[0].view_ids == ()


@pytest.mark.unit
@pytest.mark.small
def test_unclassifiable_view_url_stays_inside_matched_source_scope() -> None:
    root = Path("/project")
    source = root / "content" / "guide.md"
    index = FallbackScopeIndex(
        (root,),
        (FallbackScopeRule("content/**", "/docs/**"),),
    )

    resolutions = index.resolve(
        (source,),
        {
            "docs": "http://127.0.0.1:8000/docs/guide/",
            "unknown": "",
            "outside": "http://127.0.0.1:8000/admin/",
        },
    )

    assert resolutions[0].view_ids == ("docs", "unknown")


@pytest.mark.unit
@pytest.mark.small
def test_duplicate_and_overlapping_rules_union_view_scope_idempotently() -> None:
    root = Path("/project")
    source = root / "content" / "guide.md"
    index = FallbackScopeIndex(
        (root,),
        (
            FallbackScopeRule("content/**", "/docs/**"),
            FallbackScopeRule("content/**", "/docs/**"),
            FallbackScopeRule("content/*.md", "/preview/**"),
        ),
    )

    resolutions = index.resolve(
        (source,),
        {
            "docs": "http://127.0.0.1:8000/docs/guide/",
            "preview": "http://127.0.0.1:8000/preview/guide/",
            "other": "http://127.0.0.1:8000/other/",
        },
    )

    assert resolutions[0].view_ids == ("docs", "preview")
