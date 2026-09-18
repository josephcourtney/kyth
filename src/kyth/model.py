from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Self


class ChildStatus(StrEnum):
    ABSENT = "absent"
    STARTING = "starting"
    READY = "ready"
    STOPPING = "stopping"
    FAILED = "failed"


class FileOperation(StrEnum):
    ADDED = "added"
    MODIFIED = "modified"
    DELETED = "deleted"


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


@dataclass(frozen=True, slots=True)
class FileEvent:
    path: Path
    operation: FileOperation


@dataclass(frozen=True, slots=True)
class FileBatch:
    events: tuple[FileEvent, ...] = ()

    @classmethod
    def from_events(cls, events: tuple[FileEvent, ...] | list[FileEvent] | set[FileEvent]) -> Self:
        unique = set(events)
        ordered = tuple(sorted(unique, key=lambda event: (event.path.as_posix(), event.operation.value)))
        return cls(ordered)

    @property
    def paths(self) -> tuple[Path, ...]:
        return tuple(sorted({event.path for event in self.events}, key=Path.as_posix))

    def merged(self, *others: FileBatch) -> Self:
        events = list(self.events)
        for other in others:
            events.extend(other.events)
        return self.from_events(events)
