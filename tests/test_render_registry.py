import pytest

from kyth.control.renders import RenderRegistry
from kyth.model import RenderRecord


@pytest.mark.unit
@pytest.mark.small
def test_render_registry_is_bounded_and_replaces_existing_render_id() -> None:
    registry = RenderRegistry(max_records=2)
    first = RenderRecord("first", 1, (), True, "jinja")
    second = RenderRecord("second", 1, (), True, "jinja")
    replacement = RenderRecord("first", 2, (), True, "jinja")
    third = RenderRecord("third", 2, (), True, "jinja")

    registry.register(first)
    registry.register(second)
    registry.register(replacement)
    registry.register(third)

    assert registry.get("first") == replacement
    assert registry.get("second") is None
    assert registry.get("third") == third
