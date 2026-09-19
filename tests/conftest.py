from __future__ import annotations

from hypothesis import settings
from hypothesis.database import InMemoryExampleDatabase

_HYPOTHESIS_PROFILE = "kyth-hermetic"

settings.register_profile(
    _HYPOTHESIS_PROFILE,
    database=InMemoryExampleDatabase(),
)
settings.load_profile(_HYPOTHESIS_PROFILE)
