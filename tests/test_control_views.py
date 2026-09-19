import pytest

from kyth.control.views import ViewRegistry
from kyth.model import BrowserResource, BrowserResourceKind


@pytest.mark.unit
@pytest.mark.small
def test_view_registry_expires_inactive_views() -> None:
    now = [10.0]
    registry = ViewRegistry(inactivity_timeout=5.0, clock=lambda: now[0])
    registry.register(
        view_id="view-a",
        url="http://127.0.0.1:8000/",
        generation=2,
    )

    now[0] = 14.0
    assert registry.expire_inactive() == ()
    assert registry.get("view-a") is not None

    now[0] = 16.0
    assert registry.expire_inactive() == ("view-a",)
    assert registry.get("view-a") is None


@pytest.mark.unit
@pytest.mark.small
def test_ensure_and_touch_keep_a_view_alive() -> None:
    now = [1.0]
    registry = ViewRegistry(inactivity_timeout=3.0, clock=lambda: now[0])

    placeholder = registry.ensure("view-a")
    assert placeholder.url == ""

    now[0] = 3.0
    assert registry.touch("view-a") is not None
    now[0] = 5.0

    assert registry.expire_inactive() == ()


@pytest.mark.unit
@pytest.mark.small
def test_set_generation_marks_only_selected_views_current() -> None:
    registry = ViewRegistry(inactivity_timeout=5.0, clock=lambda: 10.0)
    registry.register(view_id="first", url="http://127.0.0.1/first.html", generation=1)
    registry.register(view_id="second", url="http://127.0.0.1/second.html", generation=1)

    registry.set_generation(("first",), 2)

    first = registry.get("first")
    second = registry.get("second")
    assert first is not None
    assert second is not None
    assert first.generation == 2
    assert second.generation == 1


@pytest.mark.unit
@pytest.mark.small
def test_stale_registration_cannot_overwrite_newer_view_state() -> None:
    now = [1.0]
    registry = ViewRegistry(inactivity_timeout=5.0, clock=lambda: now[0])
    current_resource = BrowserResource(
        "http://127.0.0.1/current.css",
        BrowserResourceKind.STYLESHEET,
    )
    stale_resource = BrowserResource(
        "http://127.0.0.1/stale.css",
        BrowserResourceKind.STYLESHEET,
    )
    registry.register(
        view_id="view",
        url="http://127.0.0.1/current",
        generation=4,
        render_id="render-current",
        resources=(current_resource,),
        resources_complete=True,
    )

    now[0] = 2.0
    returned = registry.register(
        view_id="view",
        url="http://127.0.0.1/stale",
        generation=3,
        render_id="render-stale",
        resources=(stale_resource,),
        resources_complete=False,
    )

    assert returned.generation == 4
    assert returned.url == "http://127.0.0.1/current"
    assert returned.render_id == "render-current"
    assert returned.resources == (current_resource,)
    assert returned.resources_complete is True
    assert returned.last_seen == 2.0
    assert registry.get("view") == returned
