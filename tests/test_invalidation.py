from pathlib import Path

import pytest

from kyth.invalidation import (
    BrowserActionKind,
    ReloadScope,
    decide_browser_invalidation,
    decide_browser_updates,
)
from kyth.model import BrowserResource, BrowserResourceKind


@pytest.mark.unit
@pytest.mark.small
def test_known_direct_output_reloads_only_affected_and_unknown_views() -> None:
    home = Path("/site/index.html")
    about = Path("/site/about.html")
    decision = decide_browser_invalidation(
        (about,),
        known_outputs={home, about},
        output_views={
            home: ("home",),
            about: ("about",),
        },
        active_view_ids={"home", "about", "dynamic"},
    )

    assert decision.scope is ReloadScope.TARGETED
    assert decision.invalidated_outputs == (about,)
    assert decision.reload_view_ids == ("about", "dynamic")
    assert decision.current_view_ids == ("home",)
    assert decision.reason == "known-direct-output"


@pytest.mark.unit
@pytest.mark.small
def test_known_inactive_output_does_not_reload_unrelated_direct_views() -> None:
    home = Path("/site/index.html")
    about = Path("/site/about.html")
    archived = Path("/site/archive.html")
    decision = decide_browser_invalidation(
        (archived,),
        known_outputs={home, about, archived},
        output_views={
            home: ("home",),
            about: ("about",),
        },
        active_view_ids={"home", "about"},
    )

    assert decision.scope is ReloadScope.NONE
    assert decision.reload_view_ids == ()
    assert decision.current_view_ids == ("about", "home")


@pytest.mark.unit
@pytest.mark.small
def test_unknown_browser_dependency_falls_back_to_all_active_views() -> None:
    template = Path("/project/templates/base.html")
    decision = decide_browser_invalidation(
        (template,),
        known_outputs={Path("/site/index.html")},
        output_views={Path("/site/index.html"): ("home",)},
        active_view_ids={"home", "dynamic"},
    )

    assert decision.scope is ReloadScope.ALL
    assert decision.reload_view_ids == ("dynamic", "home")
    assert decision.current_view_ids == ()
    assert decision.reason == "ambiguous-browser-dependency"


@pytest.mark.unit
@pytest.mark.small
def test_direct_stylesheet_change_uses_css_update_for_complete_view() -> None:
    stylesheet = Path("/site/static/site.css")
    decision = decide_browser_updates(
        (stylesheet,),
        known_outputs=(),
        output_views={},
        known_render_sources=(),
        render_source_views={},
        complete_render_view_ids=(),
        deferred_source_views={},
        known_resources={stylesheet},
        resource_views={
            stylesheet: {
                "styled": (
                    BrowserResource(
                        "http://127.0.0.1:8000/static/site.css",
                        BrowserResourceKind.STYLESHEET,
                    ),
                ),
            },
        },
        complete_resource_view_ids={"styled", "other"},
        active_view_ids={"styled", "other"},
    )

    assert [(action.view_id, action.kind, action.resource_urls) for action in decision.actions] == [
        (
            "styled",
            BrowserActionKind.CSS_UPDATE,
            ("http://127.0.0.1:8000/static/site.css",),
        )
    ]
    assert decision.current_view_ids == ("other",)


@pytest.mark.unit
@pytest.mark.small
def test_observed_only_resource_and_incomplete_view_reload_conservatively() -> None:
    stylesheet = Path("/site/static/site.css")
    decision = decide_browser_updates(
        (stylesheet,),
        known_outputs=(),
        output_views={},
        known_render_sources=(),
        render_source_views={},
        complete_render_view_ids=(),
        deferred_source_views={},
        known_resources={stylesheet},
        resource_views={
            stylesheet: {
                "observed": (
                    BrowserResource(
                        "http://127.0.0.1:8000/static/site.css",
                        BrowserResourceKind.OBSERVED,
                    ),
                ),
            },
        },
        complete_resource_view_ids={"observed"},
        active_view_ids={"observed", "incomplete"},
    )

    assert [(action.view_id, action.kind) for action in decision.actions] == [
        ("incomplete", BrowserActionKind.RELOAD),
        ("observed", BrowserActionKind.RELOAD),
    ]
    assert decision.current_view_ids == ()


@pytest.mark.unit
@pytest.mark.small
def test_mixed_css_and_image_changes_collapse_to_one_reload_per_view() -> None:
    stylesheet = Path("/site/static/site.css")
    image = Path("/site/static/logo.svg")
    decision = decide_browser_updates(
        (stylesheet, image),
        known_outputs=(),
        output_views={},
        known_render_sources=(),
        render_source_views={},
        complete_render_view_ids=(),
        deferred_source_views={},
        known_resources={stylesheet, image},
        resource_views={
            stylesheet: {
                "view": (
                    BrowserResource(
                        "http://127.0.0.1:8000/static/site.css",
                        BrowserResourceKind.STYLESHEET,
                    ),
                ),
            },
            image: {
                "view": (
                    BrowserResource(
                        "http://127.0.0.1:8000/static/logo.svg",
                        BrowserResourceKind.IMAGE,
                    ),
                ),
            },
        },
        complete_resource_view_ids={"view"},
        active_view_ids={"view"},
    )

    assert [(action.view_id, action.kind) for action in decision.actions] == [("view", BrowserActionKind.RELOAD)]


@pytest.mark.unit
@pytest.mark.small
def test_unknown_resource_change_keeps_phase_4_full_reload_fallback() -> None:
    script = Path("/site/static/app.js")
    decision = decide_browser_updates(
        (script,),
        known_outputs=(),
        output_views={},
        known_render_sources=(),
        render_source_views={},
        complete_render_view_ids=(),
        deferred_source_views={},
        known_resources=(),
        resource_views={},
        complete_resource_view_ids={"first", "second"},
        active_view_ids={"first", "second"},
    )

    assert [(action.view_id, action.kind) for action in decision.actions] == [
        ("first", BrowserActionKind.RELOAD),
        ("second", BrowserActionKind.RELOAD),
    ]
    assert decision.current_view_ids == ()


@pytest.mark.unit
@pytest.mark.small
def test_direct_image_change_uses_asset_update_for_complete_view() -> None:
    image = Path("/site/static/logo.svg")
    decision = decide_browser_updates(
        (image,),
        known_outputs=(),
        output_views={},
        known_render_sources=(),
        render_source_views={},
        complete_render_view_ids=(),
        deferred_source_views={},
        known_resources={image},
        resource_views={
            image: {
                "image-view": (
                    BrowserResource(
                        "http://127.0.0.1:8000/static/logo.svg",
                        BrowserResourceKind.IMAGE,
                    ),
                ),
            },
        },
        complete_resource_view_ids={"image-view"},
        active_view_ids={"image-view"},
    )

    assert [(action.view_id, action.kind, action.resource_urls) for action in decision.actions] == [
        (
            "image-view",
            BrowserActionKind.ASSET_UPDATE,
            ("http://127.0.0.1:8000/static/logo.svg",),
        )
    ]


@pytest.mark.unit
@pytest.mark.small
def test_complete_render_provenance_reloads_only_dependent_view() -> None:
    first = Path("/templates/first.html")
    decision = decide_browser_updates(
        (first,),
        known_outputs=(),
        output_views={},
        known_render_sources={first, Path("/templates/second.html")},
        render_source_views={
            first: ("first-view",),
            Path("/templates/second.html"): ("second-view",),
        },
        complete_render_view_ids={"first-view", "second-view"},
        deferred_source_views={},
        known_resources=(),
        resource_views={},
        complete_resource_view_ids=(),
        active_view_ids={"first-view", "second-view"},
    )

    assert [(action.view_id, action.kind) for action in decision.actions] == [("first-view", BrowserActionKind.RELOAD)]
    assert decision.current_view_ids == ("second-view",)
    assert decision.reason == "render-provenance"


@pytest.mark.unit
@pytest.mark.small
def test_manifest_generated_views_are_deferred_for_shared_render_source() -> None:
    template = Path("/templates/base.html")
    decision = decide_browser_updates(
        (template,),
        known_outputs=(),
        output_views={},
        known_render_sources={template},
        render_source_views={template: ("dynamic", "generated")},
        complete_render_view_ids={"dynamic", "generated"},
        deferred_source_views={template: ("generated",)},
        known_resources=(),
        resource_views={},
        complete_resource_view_ids=(),
        active_view_ids={"dynamic", "generated"},
    )

    assert [(action.view_id, action.kind) for action in decision.actions] == [("dynamic", BrowserActionKind.RELOAD)]
    assert decision.current_view_ids == ("generated",)


@pytest.mark.unit
@pytest.mark.small
def test_semantic_data_dependency_uses_data_update_for_dependent_view() -> None:
    data = Path("/project/data/inventory.json")
    decision = decide_browser_updates(
        (data,),
        known_outputs=(),
        output_views={},
        known_render_sources=(),
        render_source_views={},
        complete_render_view_ids={"inventory", "other"},
        deferred_source_views={},
        known_resources=(),
        resource_views={},
        complete_resource_view_ids=(),
        active_view_ids={"inventory", "other"},
        known_data_sources={data},
        data_source_views={data: {"inventory": ("inventory",)}},
    )

    assert [(action.view_id, action.kind, action.data_ids) for action in decision.actions] == [
        ("inventory", BrowserActionKind.DATA_UPDATE, ("inventory",)),
    ]
    assert decision.current_view_ids == ("other",)


@pytest.mark.unit
@pytest.mark.small
def test_mixed_template_and_data_dependency_falls_back_to_reload() -> None:
    data = Path("/project/data/inventory.json")
    decision = decide_browser_updates(
        (data,),
        known_outputs=(),
        output_views={},
        known_render_sources={data},
        render_source_views={data: ("view",)},
        complete_render_view_ids={"view"},
        deferred_source_views={},
        known_resources=(),
        resource_views={},
        complete_resource_view_ids=(),
        active_view_ids={"view"},
        known_data_sources={data},
        data_source_views={data: {"view": ("inventory",)}},
    )

    assert [(action.view_id, action.kind) for action in decision.actions] == [
        ("view", BrowserActionKind.RELOAD),
    ]


@pytest.mark.unit
@pytest.mark.small
def test_manifest_deferred_view_suppresses_semantic_data_update_until_output_ready() -> None:
    source = Path("/project/content.json")
    decision = decide_browser_updates(
        (source,),
        known_outputs=(),
        output_views={},
        known_render_sources=(),
        render_source_views={},
        complete_render_view_ids={"dynamic", "generated"},
        deferred_source_views={source: ("generated",)},
        known_resources=(),
        resource_views={},
        complete_resource_view_ids=(),
        active_view_ids={"dynamic", "generated"},
        known_data_sources={source},
        data_source_views={
            source: {
                "dynamic": ("content",),
                "generated": ("content",),
            }
        },
    )

    assert [(action.view_id, action.kind) for action in decision.actions] == [
        ("dynamic", BrowserActionKind.DATA_UPDATE),
    ]
    assert decision.current_view_ids == ("generated",)


@pytest.mark.unit
@pytest.mark.small
def test_unknown_dependency_scope_reloads_only_scoped_uncertain_views() -> None:
    unknown = Path("/project/content/guide.md")
    decision = decide_browser_updates(
        (unknown,),
        known_outputs=(),
        output_views={},
        known_render_sources=(),
        render_source_views={},
        complete_render_view_ids=(),
        deferred_source_views={},
        known_resources=(),
        resource_views={},
        complete_resource_view_ids=(),
        active_view_ids={"docs", "admin"},
        fallback_scope_views={unknown: {"docs"}},
    )

    assert [(action.view_id, action.kind) for action in decision.actions] == [
        ("docs", BrowserActionKind.RELOAD),
    ]
    assert decision.current_view_ids == ("admin",)
    assert decision.reason == "scoped-conservative-fallback"
    assert decision.fallbacks[0].uncertain_view_ids == ("admin", "docs")
    assert decision.fallbacks[0].reload_view_ids == ("docs",)
    assert decision.fallbacks[0].scoped is True


@pytest.mark.unit
@pytest.mark.small
def test_matching_empty_scope_can_leave_all_uncertain_views_current() -> None:
    unknown = Path("/project/content/guide.md")
    decision = decide_browser_updates(
        (unknown,),
        known_outputs=(),
        output_views={},
        known_render_sources=(),
        render_source_views={},
        complete_render_view_ids=(),
        deferred_source_views={},
        known_resources=(),
        resource_views={},
        complete_resource_view_ids=(),
        active_view_ids={"admin"},
        fallback_scope_views={unknown: ()},
    )

    assert decision.actions == ()
    assert decision.current_view_ids == ("admin",)
    assert decision.reason == "scoped-conservative-fallback"


@pytest.mark.unit
@pytest.mark.small
def test_unmatched_ambiguous_path_widens_mixed_batch_back_to_global_reload() -> None:
    scoped = Path("/project/content/guide.md")
    unscoped = Path("/project/mystery.bin")
    decision = decide_browser_updates(
        (scoped, unscoped),
        known_outputs=(),
        output_views={},
        known_render_sources=(),
        render_source_views={},
        complete_render_view_ids=(),
        deferred_source_views={},
        known_resources=(),
        resource_views={},
        complete_resource_view_ids=(),
        active_view_ids={"docs", "admin"},
        fallback_scope_views={scoped: {"docs"}},
    )

    assert [(action.view_id, action.kind) for action in decision.actions] == [
        ("admin", BrowserActionKind.RELOAD),
        ("docs", BrowserActionKind.RELOAD),
    ]
    assert decision.current_view_ids == ()
    assert decision.reason == "ambiguous-browser-dependency"


@pytest.mark.unit
@pytest.mark.small
def test_precise_render_dependency_outside_scope_is_never_suppressed() -> None:
    template = Path("/project/templates/shared.html")
    decision = decide_browser_updates(
        (template,),
        known_outputs=(),
        output_views={},
        known_render_sources={template},
        render_source_views={template: ("outside-precise",)},
        complete_render_view_ids={"outside-precise"},
        deferred_source_views={},
        known_resources=(),
        resource_views={},
        complete_resource_view_ids=(),
        active_view_ids={"outside-precise", "uncertain-in", "uncertain-out"},
        fallback_scope_views={template: {"uncertain-in"}},
    )

    assert [(action.view_id, action.kind) for action in decision.actions] == [
        ("outside-precise", BrowserActionKind.RELOAD),
        ("uncertain-in", BrowserActionKind.RELOAD),
    ]
    assert decision.current_view_ids == ("uncertain-out",)
    assert decision.reason == "scoped-conservative-fallback"


@pytest.mark.unit
@pytest.mark.small
def test_scope_narrows_only_incomplete_resource_views() -> None:
    stylesheet = Path("/project/static/site.css")
    decision = decide_browser_updates(
        (stylesheet,),
        known_outputs=(),
        output_views={},
        known_render_sources=(),
        render_source_views={},
        complete_render_view_ids=(),
        deferred_source_views={},
        known_resources={stylesheet},
        resource_views={
            stylesheet: {
                "complete": (
                    BrowserResource(
                        "http://127.0.0.1:8000/static/site.css",
                        BrowserResourceKind.STYLESHEET,
                    ),
                ),
            },
        },
        complete_resource_view_ids={"complete"},
        active_view_ids={"complete", "incomplete-in", "incomplete-out"},
        fallback_scope_views={stylesheet: {"incomplete-in"}},
    )

    assert [(action.view_id, action.kind) for action in decision.actions] == [
        ("complete", BrowserActionKind.CSS_UPDATE),
        ("incomplete-in", BrowserActionKind.RELOAD),
    ]
    assert decision.current_view_ids == ("incomplete-out",)
    assert decision.reason == "scoped-conservative-fallback"


@pytest.mark.unit
@pytest.mark.small
def test_scope_does_not_change_action_when_it_contains_all_uncertain_views() -> None:
    unknown = Path("/project/content/guide.md")
    decision = decide_browser_updates(
        (unknown,),
        known_outputs=(),
        output_views={},
        known_render_sources=(),
        render_source_views={},
        complete_render_view_ids=(),
        deferred_source_views={},
        known_resources=(),
        resource_views={},
        complete_resource_view_ids=(),
        active_view_ids={"docs"},
        fallback_scope_views={unknown: {"docs"}},
    )

    assert [(action.view_id, action.kind) for action in decision.actions] == [
        ("docs", BrowserActionKind.RELOAD),
    ]
    assert decision.reason == "ambiguous-browser-dependency"
