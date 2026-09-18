from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class StartupEventKind(StrEnum):
    READY = "ready"
    FAILED = "failed"


class ChildCommand(StrEnum):
    SHUTDOWN = "shutdown"


@dataclass(frozen=True, slots=True)
class GenerationUpdate:
    generation: int


@dataclass(frozen=True, slots=True)
class GenerationApplied:
    generation: int


@dataclass(frozen=True, slots=True)
class StartupEvent:
    kind: StartupEventKind
    detail: str | None = None

    @classmethod
    def ready(cls) -> StartupEvent:
        return cls(StartupEventKind.READY)

    @classmethod
    def failed(cls, detail: str) -> StartupEvent:
        return cls(StartupEventKind.FAILED, detail)
