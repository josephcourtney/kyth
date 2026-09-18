from __future__ import annotations

import time
from collections.abc import Collection
from dataclasses import dataclass, replace
from threading import Lock
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable


@dataclass(frozen=True, slots=True)
class BrowserView:
    view_id: str
    url: str
    generation: int
    render_id: str | None
    last_seen: float


class ViewRegistry:
    """Thread-safe registry of browser views active in one development session."""

    def __init__(
        self,
        *,
        inactivity_timeout: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """Create a registry with monotonic inactivity expiration."""
        if inactivity_timeout <= 0:
            msg = "view inactivity timeout must be positive"
            raise ValueError(msg)
        self._inactivity_timeout = inactivity_timeout
        self._clock = clock
        self._lock = Lock()
        self._views: dict[str, BrowserView] = {}

    def register(
        self,
        *,
        view_id: str,
        url: str,
        generation: int,
        render_id: str | None = None,
    ) -> BrowserView:
        now = self._clock()
        view = BrowserView(view_id, url, generation, render_id, now)
        with self._lock:
            self._views[view_id] = view
        return view

    def ensure(self, view_id: str) -> BrowserView:
        now = self._clock()
        with self._lock:
            current = self._views.get(view_id)
            current = BrowserView(view_id, "", 0, None, now) if current is None else replace(current, last_seen=now)
            self._views[view_id] = current
            return current

    def touch(self, view_id: str) -> BrowserView | None:
        now = self._clock()
        with self._lock:
            current = self._views.get(view_id)
            if current is None:
                return None
            updated = replace(current, last_seen=now)
            self._views[view_id] = updated
            return updated

    def set_generation(self, view_ids: Collection[str], generation: int) -> None:
        """Mark selected views as valid through a committed generation."""
        selected = set(view_ids)
        with self._lock:
            for view_id in selected:
                current = self._views.get(view_id)
                if current is None or generation < current.generation:
                    continue
                self._views[view_id] = replace(current, generation=generation)

    def get(self, view_id: str) -> BrowserView | None:
        with self._lock:
            return self._views.get(view_id)

    def snapshot(self) -> tuple[BrowserView, ...]:
        with self._lock:
            return tuple(sorted(self._views.values(), key=lambda view: view.view_id))

    def expire_inactive(self) -> tuple[str, ...]:
        cutoff = self._clock() - self._inactivity_timeout
        with self._lock:
            expired = tuple(sorted(view_id for view_id, view in self._views.items() if view.last_seen < cutoff))
            for view_id in expired:
                del self._views[view_id]
        return expired
