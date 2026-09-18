from __future__ import annotations

from collections import OrderedDict
from threading import Lock
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from kyth.model import RenderRecord

DEFAULT_MAX_RENDER_RECORDS = 2048


class RenderRegistry:
    """Bounded thread-safe store of recently reported render provenance."""

    def __init__(self, *, max_records: int = DEFAULT_MAX_RENDER_RECORDS) -> None:
        """Create a registry that retains the most recent render records."""
        if max_records <= 0:
            msg = "render record capacity must be positive"
            raise ValueError(msg)
        self._max_records = max_records
        self._lock = Lock()
        self._records: OrderedDict[str, RenderRecord] = OrderedDict()

    def register(self, record: RenderRecord) -> None:
        """Insert or replace one render record and enforce the bounded capacity."""
        with self._lock:
            self._records.pop(record.render_id, None)
            self._records[record.render_id] = record
            while len(self._records) > self._max_records:
                self._records.popitem(last=False)

    def get(self, render_id: str) -> RenderRecord | None:
        with self._lock:
            return self._records.get(render_id)

    def snapshot(self) -> tuple[RenderRecord, ...]:
        with self._lock:
            return tuple(self._records.values())
