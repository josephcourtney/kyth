from __future__ import annotations

from pathlib import Path

from kyth.injection.jinja import record_data_dependency, record_dependency


def depend_on(path: str | Path) -> bool:
    """Register a filesystem dependency for the current Kyth-managed HTML render.

    Returns False when called outside an active injectable HTTP render so optional
    development integration never becomes an application correctness dependency.
    """
    return record_dependency(path)


def depend_on_data(identity: str, path: str | Path) -> bool:
    """Register browser-consumed data provenance for the current HTML render."""
    if not identity:
        msg = "data dependency identity must be non-empty"
        raise ValueError(msg)
    return record_data_dependency(identity, path)
