from pathlib import Path

import pytest

from kyth.invalidation import ReloadScope, decide_browser_invalidation


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
