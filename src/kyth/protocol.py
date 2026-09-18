from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class ControlEventKind(StrEnum):
    SYNC = "sync"
    RELOAD = "reload"
    CSS_UPDATE = "css-update"
    ASSET_UPDATE = "asset-update"
    DATA_UPDATE = "data-update"
    SERVER_ERROR = "server-error"


@dataclass(frozen=True, slots=True)
class ControlEvent:
    kind: ControlEventKind
    generation: int
    data: dict[str, object] = field(default_factory=dict)

    @classmethod
    def sync(cls, generation: int) -> ControlEvent:
        return cls(ControlEventKind.SYNC, generation)
