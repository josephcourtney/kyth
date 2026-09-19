from __future__ import annotations

import pytest
from hypothesis import given, settings, strategies as st
from hypothesis.database import InMemoryExampleDatabase

_HYPOTHESIS_PROFILE = "kyth-hermetic"

settings.register_profile(
    _HYPOTHESIS_PROFILE,
    database=InMemoryExampleDatabase(),
)
settings.load_profile(_HYPOTHESIS_PROFILE)


@settings(max_examples=1, database=None)
@given(st.none())
def _warm_hypothesis(value: None) -> None:
    """Force Hypothesis' lazy execution imports before small-test isolation starts."""
    assert value is None


def pytest_sessionstart(_session: pytest.Session) -> None:
    """Initialize Hypothesis while the test-category filesystem blocker is inactive."""
    _warm_hypothesis()
