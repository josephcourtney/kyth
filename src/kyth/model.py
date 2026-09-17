from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class ChildStatus(StrEnum):
    ABSENT = "absent"
    STARTING = "starting"
    READY = "ready"
    STOPPING = "stopping"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class ChildState:
    status: ChildStatus = ChildStatus.ABSENT
    pid: int | None = None
    error: str | None = None
    exit_code: int | None = None


@dataclass(frozen=True, slots=True)
class DevelopmentState:
    generation: int = 0
    child: ChildState = field(default_factory=ChildState)
