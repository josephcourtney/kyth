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
    def sync(
        cls,
        generation: int,
        *,
        reload_required: bool | None = None,
    ) -> ControlEvent:
        data: dict[str, object] = {}
        if reload_required is not None:
            data["reload_required"] = reload_required
        return cls(ControlEventKind.SYNC, generation, data)

    @classmethod
    def reload(cls, generation: int, *, reason: str) -> ControlEvent:
        return cls(ControlEventKind.RELOAD, generation, {"reason": reason})

    @classmethod
    def css_update(cls, generation: int, *, resources: tuple[str, ...]) -> ControlEvent:
        return cls(ControlEventKind.CSS_UPDATE, generation, {"resources": list(resources)})

    @classmethod
    def asset_update(cls, generation: int, *, resources: tuple[str, ...]) -> ControlEvent:
        return cls(ControlEventKind.ASSET_UPDATE, generation, {"resources": list(resources)})

    @classmethod
    def data_update(cls, generation: int, *, identities: tuple[str, ...]) -> ControlEvent:
        return cls(ControlEventKind.DATA_UPDATE, generation, {"identities": list(identities)})

    @classmethod
    def server_error(cls, generation: int, *, message: str) -> ControlEvent:
        return cls(ControlEventKind.SERVER_ERROR, generation, {"message": message})
