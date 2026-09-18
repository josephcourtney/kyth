import pytest

from kyth.control.views import ViewRegistry


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
