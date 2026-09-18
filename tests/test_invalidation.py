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

    assert [(action.view_id, action.kind) for action in decision.actions] == [
        ("view", BrowserActionKind.RELOAD)
    ]

@pytest.mark.unit
@pytest.mark.small
def test_unknown_resource_change_keeps_phase_4_full_reload_fallback() -> None:
    script = Path("/site/static/app.js")
    decision = decide_browser_updates(
        (script,),
        known_outputs=(),
        output_views={},
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
