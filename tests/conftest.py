from __future__ import annotations

import sys

from hypothesis import settings
from hypothesis.database import InMemoryExampleDatabase

_HYPOTHESIS_PROFILE = "kyth-hermetic"

# Pytest's assertion-rewrite importer normally writes rewritten bytecode for
# modules imported during tests. Hypothesis lazily imports parts of its
# conjecture engine while generated examples run, which would otherwise make
# genuinely pure small tests trip filesystem isolation.
sys.dont_write_bytecode = True

settings.register_profile(
    _HYPOTHESIS_PROFILE,
    database=InMemoryExampleDatabase(),
)
settings.load_profile(_HYPOTHESIS_PROFILE)
