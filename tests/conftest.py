from __future__ import annotations

import sys

sys.dont_write_bytecode = True

from hypothesis import settings
from hypothesis.database import InMemoryExampleDatabase

_HYPOTHESIS_PROFILE = "kyth-hermetic"

settings.register_profile(
    _HYPOTHESIS_PROFILE,
    database=InMemoryExampleDatabase(),
)
settings.load_profile(_HYPOTHESIS_PROFILE)
