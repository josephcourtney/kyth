from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import TypeVar

from kyth.injection.jinja import record_data_dependency, record_dependency

_ReadinessResult = bool | None | Awaitable[bool | None]
_ReadinessCheck = Callable[[], _ReadinessResult]
_CheckT = TypeVar("_CheckT", bound=_ReadinessCheck)
_READINESS_CHECKS: list[_ReadinessCheck] = []


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


def register_readiness_check(check: _CheckT) -> _CheckT:
    """Register a child-local check that must complete after ASGI lifespan startup."""
    _READINESS_CHECKS.append(check)
    return check


async def run_readiness_checks() -> None:
    """Run all checks registered while importing the application child."""
    for check in tuple(_READINESS_CHECKS):
        result = check()
        if inspect.isawaitable(result):
            result = await result
        if result is False:
            name = getattr(check, "__qualname__", repr(check))
            msg = f"custom readiness check returned false: {name}"
            raise RuntimeError(msg)
