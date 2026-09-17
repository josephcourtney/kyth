import pytest

from kyth.model import ChildState, ChildStatus, DevelopmentState


@pytest.mark.unit
@pytest.mark.small
def test_development_state_starts_without_child_or_generation() -> None:
    state = DevelopmentState()

    assert state.generation == 0
    assert state.child == ChildState()
    assert state.child.status is ChildStatus.ABSENT
