from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING

from kyth.model import BrowserResourceKind

if TYPE_CHECKING:
    from collections.abc import Collection, Mapping

    from kyth.model import BrowserResource

HTML_SUFFIXES = frozenset({".htm", ".html"})
IMAGE_SUFFIXES = frozenset({".avif", ".bmp", ".gif", ".ico", ".jpeg", ".jpg", ".png", ".svg", ".webp"})


class ReloadScope(StrEnum):
    NONE = "none"
    TARGETED = "targeted"
    ALL = "all"


@dataclass(frozen=True, slots=True)
class InvalidationDecision:
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

    direct_views = {view_id for view_ids in output_views.values() for view_id in view_ids} & active
    affected = {view_id for path in paths for view_id in output_views.get(path, ())} & active
    reload_views = affected | (active - direct_views)
    current = direct_views - affected
    return InvalidationDecision(
        paths,
        ReloadScope.TARGETED if reload_views else ReloadScope.NONE,
        reload_view_ids=tuple(sorted(reload_views)),
        current_view_ids=tuple(sorted(current)),
        reason="known-direct-output",
    )


class BrowserActionKind(StrEnum):
    RELOAD = "reload"
    CSS_UPDATE = "css-update"
    ASSET_UPDATE = "asset-update"
    DATA_UPDATE = "data-update"


@dataclass(frozen=True, slots=True)
class BrowserAction:
    view_id: str
    kind: BrowserActionKind
    resource_urls: tuple[str, ...] = ()
    data_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class BrowserFallback:
    """Explain conservative treatment of one path's uncertain view set."""

    path: Path
    uncertain_view_ids: tuple[str, ...]
    reload_view_ids: tuple[str, ...]
    scoped: bool


@dataclass(frozen=True, slots=True)
class BrowserUpdateDecision:
    invalidated_paths: tuple[Path, ...]
    actions: tuple[BrowserAction, ...]
    current_view_ids: tuple[str, ...]
    reason: str
    fallbacks: tuple[BrowserFallback, ...] = ()


def decide_browser_updates(
    changed_paths: Collection[Path],
    *,
    known_outputs: Collection[Path],
    output_views: Mapping[Path, Collection[str]],
    known_render_sources: Collection[Path],
    render_source_views: Mapping[Path, Collection[str]],
    complete_render_view_ids: Collection[str],
    deferred_source_views: Mapping[Path, Collection[str]],
    known_resources: Collection[Path],
    resource_views: Mapping[Path, Mapping[str, Collection[BrowserResource]]],
    complete_resource_view_ids: Collection[str],
    active_view_ids: Collection[str],
    known_data_sources: Collection[Path] = (),
    data_source_views: Mapping[Path, Mapping[str, Collection[str]]] | None = None,
    fallback_scope_views: Mapping[Path, Collection[str]] | None = None,
) -> BrowserUpdateDecision:
    """Choose one coherent browser action per view for a stable change batch."""
    paths = tuple(sorted(set(changed_paths), key=Path.as_posix))
    active = set(active_view_ids)
    data_views = {} if data_source_views is None else data_source_views
    scope_views = {} if fallback_scope_views is None else fallback_scope_views
    if not paths:
        return BrowserUpdateDecision((), (), tuple(sorted(active)), "no-browser-change")

    known_output_paths = set(known_outputs)
    known_render_paths = set(known_render_sources)
    known_data_paths = set(known_data_sources)
    known_content_paths = known_output_paths | known_render_paths | known_data_paths
    known_resource_paths = set(known_resources)
    direct_views = {view_id for view_ids in output_views.values() for view_id in view_ids} & active
    complete_render_views = set(complete_render_view_ids) & active
    complete_resource_views = set(complete_resource_view_ids) & active

    actions: dict[str, BrowserAction] = {}
    fallbacks: list[BrowserFallback] = []
    unknown_paths: set[Path] = set()
    removed_by_scope: set[str] = set()

    for path in paths:
        if path in known_content_paths:
            uncertain = _merge_content_path(
                actions,
                path,
                active=active,
                direct_views=direct_views,
                complete_render_views=complete_render_views,
                known_output_paths=known_output_paths,
                output_views=output_views,
                known_render_paths=known_render_paths,
                render_source_views=render_source_views,
                deferred_source_views=deferred_source_views,
                known_data_paths=known_data_paths,
                data_source_views=data_views,
            )
        elif path in known_resource_paths:
            uncertain = _merge_resource_path(
                actions,
                path,
                active=active,
                complete_resource_views=complete_resource_views,
                resource_views=resource_views,
            )
        else:
            unknown_paths.add(path)
            uncertain = set(active)

        fallback = _apply_fallback(path, uncertain, scope_views=scope_views)
        fallbacks.append(fallback)
        removed_by_scope.update(set(fallback.uncertain_view_ids) - set(fallback.reload_view_ids))
        for view_id in fallback.reload_view_ids:
            _merge_action(actions, BrowserAction(view_id, BrowserActionKind.RELOAD))

    ordered_actions = tuple(sorted(actions.values(), key=lambda action: action.view_id))
    current = tuple(sorted(active - set(actions)))
    materially_scoped = any(
        view_id not in actions or actions[view_id].kind is not BrowserActionKind.RELOAD
        for view_id in removed_by_scope
    )
    reason = _decision_reason(
        ordered_actions,
        paths=paths,
        unknown_paths=unknown_paths,
        known_render_sources=known_render_paths,
        known_content_paths=known_content_paths,
        known_resources=known_resource_paths,
        materially_scoped=materially_scoped,
    )
    return BrowserUpdateDecision(paths, ordered_actions, current, reason, tuple(fallbacks))


def _merge_content_path(
    actions: dict[str, BrowserAction],
    path: Path,
    *,
    active: set[str],
    direct_views: set[str],
    complete_render_views: set[str],
    known_output_paths: set[Path],
    output_views: Mapping[Path, Collection[str]],
    known_render_paths: set[Path],
    render_source_views: Mapping[Path, Collection[str]],
    deferred_source_views: Mapping[Path, Collection[str]],
    known_data_paths: set[Path],
    data_source_views: Mapping[Path, Mapping[str, Collection[str]]],
) -> set[str]:
    precise: set[str] = set()
    known_affected: set[str] = set()
    deferred = set(deferred_source_views.get(path, ())) & active

    if path in known_output_paths:
        precise.update(direct_views)
        known_affected.update(set(output_views.get(path, ())) & active)

    if path in known_render_paths:
        precise.update(complete_render_views)
        known_affected.update((set(render_source_views.get(path, ())) & active) - deferred)

    data_affected: set[str] = set()
    if path in known_data_paths:
        precise.update(complete_render_views)
        data_affected = _merge_data_actions(
            actions,
            data_source_views.get(path, {}),
            active=active,
            deferred=deferred,
        )
        for view_id in data_affected - complete_render_views:
            _merge_action(actions, BrowserAction(view_id, BrowserActionKind.RELOAD))

    precise.update(deferred)
    for view_id in known_affected:
        _merge_action(actions, BrowserAction(view_id, BrowserActionKind.RELOAD))

    return active - precise - known_affected - data_affected


def _merge_data_actions(
    actions: dict[str, BrowserAction],
    identities_by_view: Mapping[str, Collection[str]],
    *,
    active: set[str],
    deferred: set[str],
) -> set[str]:
    affected: set[str] = set()
    for view_id, identities in identities_by_view.items():
        if view_id not in active or view_id in deferred:
            continue
        affected.add(view_id)
        _merge_action(
            actions,
            BrowserAction(
                view_id,
                BrowserActionKind.DATA_UPDATE,
                data_ids=tuple(sorted(set(identities))),
            ),
        )
    return affected


def _merge_resource_path(
    actions: dict[str, BrowserAction],
    path: Path,
    *,
    active: set[str],
    complete_resource_views: set[str],
    resource_views: Mapping[Path, Mapping[str, Collection[BrowserResource]]],
) -> set[str]:
    referenced: set[str] = set()
    for view_id, references in resource_views.get(path, {}).items():
        if view_id not in active:
            continue
        referenced.add(view_id)
        candidate = (
            _resource_action(path, view_id, references)
            if view_id in complete_resource_views
            else BrowserAction(view_id, BrowserActionKind.RELOAD)
        )
        _merge_action(actions, candidate)

    return active - complete_resource_views - referenced


def _apply_fallback(
    path: Path,
    uncertain: set[str],
    *,
    scope_views: Mapping[Path, Collection[str]],
) -> BrowserFallback:
    scoped = path in scope_views
    selected = uncertain & set(scope_views[path]) if scoped else uncertain
    return BrowserFallback(
        path=path,
        uncertain_view_ids=tuple(sorted(uncertain)),
        reload_view_ids=tuple(sorted(selected)),
        scoped=scoped,
    )


def _resource_action(
    path: Path,
    view_id: str,
    references: Collection[BrowserResource],
) -> BrowserAction:
    resources = tuple(references)
    urls = tuple(sorted({resource.url for resource in resources}))
    kinds = {resource.kind for resource in resources}
    suffix = path.suffix.lower()
    if suffix == ".css" and kinds == {BrowserResourceKind.STYLESHEET}:
        return BrowserAction(view_id, BrowserActionKind.CSS_UPDATE, urls)
    if suffix in IMAGE_SUFFIXES and kinds == {BrowserResourceKind.IMAGE}:
        return BrowserAction(view_id, BrowserActionKind.ASSET_UPDATE, urls)
    return BrowserAction(view_id, BrowserActionKind.RELOAD)


def _merge_action(actions: dict[str, BrowserAction], candidate: BrowserAction) -> None:
    current = actions.get(candidate.view_id)
    if current is None:
        actions[candidate.view_id] = candidate
        return
    if current.kind is BrowserActionKind.RELOAD:
        return
    if candidate.kind is BrowserActionKind.RELOAD or candidate.kind is not current.kind:
        actions[candidate.view_id] = BrowserAction(candidate.view_id, BrowserActionKind.RELOAD)
        return
    actions[candidate.view_id] = BrowserAction(
        candidate.view_id,
        candidate.kind,
        tuple(sorted(set(current.resource_urls) | set(candidate.resource_urls))),
        tuple(sorted(set(current.data_ids) | set(candidate.data_ids))),
    )


def _decision_reason(
    actions: tuple[BrowserAction, ...],
    *,
    paths: tuple[Path, ...],
    unknown_paths: set[Path],
    known_render_sources: set[Path],
    known_content_paths: set[Path],
    known_resources: set[Path],
    materially_scoped: bool,
) -> str:
    if materially_scoped:
        return "scoped-conservative-fallback"
    if unknown_paths:
        return "ambiguous-browser-dependency"
    if any(action.kind is not BrowserActionKind.RELOAD for action in actions):
        return "narrow-browser-update"
    if any(path in known_render_sources for path in paths):
        return "render-provenance"
    if paths and all(path in known_content_paths for path in paths):
        return "known-direct-output"
    if all(path in known_resources for path in paths):
        return "known-browser-dependency"
    return "known-browser-dependency"
