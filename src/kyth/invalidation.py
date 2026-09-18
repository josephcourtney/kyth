from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Collection, Mapping

HTML_SUFFIXES = frozenset({".htm", ".html"})


class ReloadScope(StrEnum):
    NONE = "none"
    TARGETED = "targeted"
    ALL = "all"


@dataclass(frozen=True, slots=True)
class InvalidationDecision:
    """Separate invalidated outputs from the browser action they require."""

    invalidated_outputs: tuple[Path, ...]
    scope: ReloadScope
    reload_view_ids: tuple[str, ...] = ()
    current_view_ids: tuple[str, ...] = ()
    reason: str = ""


def decide_browser_invalidation(
    changed_paths: Collection[Path],
    *,
    known_outputs: Collection[Path],
    output_views: Mapping[Path, Collection[str]],
    active_view_ids: Collection[str],
) -> InvalidationDecision:
    """Choose targeted reload only when every changed browser path is a known output."""
    paths = tuple(sorted(set(changed_paths), key=Path.as_posix))
    active = set(active_view_ids)
    known = set(known_outputs)

    if not paths:
        return InvalidationDecision((), ReloadScope.NONE, current_view_ids=tuple(sorted(active)))

    if any(path.suffix.lower() not in HTML_SUFFIXES or path not in known for path in paths):
        return InvalidationDecision(
            paths,
            ReloadScope.ALL,
            reload_view_ids=tuple(sorted(active)),
            reason="ambiguous-browser-dependency",
        )

    direct_views: set[str] = set()
    affected: set[str] = set()
    for view_ids in output_views.values():
        direct_views.update(view_ids)
    for path in paths:
        affected.update(output_views.get(path, ()))

    direct_views &= active
    affected &= active
    unknown = active - direct_views
    reload_views = affected | unknown
    current = direct_views - affected

    return InvalidationDecision(
        paths,
        ReloadScope.TARGETED if reload_views else ReloadScope.NONE,
        reload_view_ids=tuple(sorted(reload_views)),
        current_view_ids=tuple(sorted(current)),
        reason="known-direct-output",
    )
