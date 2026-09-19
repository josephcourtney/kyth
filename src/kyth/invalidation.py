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
class BrowserUpdateDecision:
    invalidated_paths: tuple[Path, ...]
    actions: tuple[BrowserAction, ...]
    current_view_ids: tuple[str, ...]
    reason: str


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
) -> BrowserUpdateDecision:
    """Choose one coherent browser action per view for a stable change batch."""
    paths = tuple(sorted(set(changed_paths), key=Path.as_posix))
    active = set(active_view_ids)
    data_views = {} if data_source_views is None else data_source_views
    if not paths:
        return BrowserUpdateDecision((), (), tuple(sorted(active)), "no-browser-change")

    content_paths, resource_paths = _split_paths(
        paths,
        known_outputs=known_outputs,
        known_render_sources=known_render_sources,
        known_data_sources=known_data_sources,
    )
    if _contains_unknown_paths(
        content_paths,
        resource_paths,
        known_outputs=known_outputs,
        known_render_sources=known_render_sources,
        known_data_sources=known_data_sources,
        known_resources=known_resources,
    ):
        return _reload_all(paths, active, reason="ambiguous-browser-dependency")

    actions: dict[str, BrowserAction] = {}
    _merge_content_actions(
        actions,
        content_paths,
        active=active,
        known_outputs=known_outputs,
        output_views=output_views,
        known_render_sources=known_render_sources,
        render_source_views=render_source_views,
        complete_render_view_ids=complete_render_view_ids,
        deferred_source_views=deferred_source_views,
        known_data_sources=known_data_sources,
        data_source_views=data_views,
    )
    _merge_resource_actions(
        actions,
        resource_paths,
        active=active,
        complete_resource_view_ids=complete_resource_view_ids,
        resource_views=resource_views,
    )

    ordered_actions = tuple(sorted(actions.values(), key=lambda action: action.view_id))
    current = tuple(sorted(active - set(actions)))
    reason = _decision_reason(
        ordered_actions,
        content_paths=content_paths,
        resource_paths=resource_paths,
        known_render_sources=known_render_sources,
    )
    return BrowserUpdateDecision(paths, ordered_actions, current, reason)


def _split_paths(
    paths: tuple[Path, ...],
    *,
    known_outputs: Collection[Path],
    known_render_sources: Collection[Path],
    known_data_sources: Collection[Path],
) -> tuple[tuple[Path, ...], tuple[Path, ...]]:
    content_known = set(known_outputs) | set(known_render_sources) | set(known_data_sources)
    content = tuple(path for path in paths if path.suffix.lower() in HTML_SUFFIXES or path in content_known)
    content_set = set(content)
    resources = tuple(path for path in paths if path not in content_set)
    return content, resources


def _contains_unknown_paths(
    content_paths: tuple[Path, ...],
    resource_paths: tuple[Path, ...],
    *,
    known_outputs: Collection[Path],
    known_render_sources: Collection[Path],
    known_data_sources: Collection[Path],
    known_resources: Collection[Path],
) -> bool:
    known_content = set(known_outputs) | set(known_render_sources) | set(known_data_sources)
    known_resource_paths = set(known_resources)
    return any(path not in known_content for path in content_paths) or any(
        path not in known_resource_paths for path in resource_paths
    )


def _merge_content_actions(
    actions: dict[str, BrowserAction],
    paths: tuple[Path, ...],
    *,
    active: set[str],
    known_outputs: Collection[Path],
    output_views: Mapping[Path, Collection[str]],
    known_render_sources: Collection[Path],
    render_source_views: Mapping[Path, Collection[str]],
    complete_render_view_ids: Collection[str],
    deferred_source_views: Mapping[Path, Collection[str]],
    known_data_sources: Collection[Path],
    data_source_views: Mapping[Path, Mapping[str, Collection[str]]],
) -> None:
    known_output_paths = set(known_outputs)
    known_render_paths = set(known_render_sources)
    known_data_paths = set(known_data_sources)
    direct_views = {view_id for view_ids in output_views.values() for view_id in view_ids} & active
    complete_render_views = set(complete_render_view_ids) & active

    for path in paths:
        precise: set[str] = set()
        affected: set[str] = set()
        source_affected: set[str] = set()
        deferred = set(deferred_source_views.get(path, ())) & active
        if path in known_output_paths:
            precise.update(direct_views)
            affected.update(output_views.get(path, ()))
        if path in known_render_paths:
            precise.update(complete_render_views)
            source_affected.update(render_source_views.get(path, ()))
        if path in known_data_paths:
            precise.update(complete_render_views)
            _merge_data_actions(
                actions,
                data_source_views.get(path, {}),
                active=active,
                deferred=deferred,
            )
        precise.update(deferred)
        affected.update(source_affected - deferred)

        for view_id in (affected & active) | (active - precise):
            _merge_action(actions, BrowserAction(view_id, BrowserActionKind.RELOAD))


def _merge_data_actions(
    actions: dict[str, BrowserAction],
    identities_by_view: Mapping[str, Collection[str]],
    *,
    active: set[str],
    deferred: set[str],
) -> None:
    for view_id, identities in identities_by_view.items():
        if view_id not in active or view_id in deferred:
            continue
        _merge_action(
            actions,
            BrowserAction(
                view_id,
                BrowserActionKind.DATA_UPDATE,
                data_ids=tuple(sorted(set(identities))),
            ),
        )


def _merge_resource_actions(
    actions: dict[str, BrowserAction],
    resource_paths: tuple[Path, ...],
    *,
    active: set[str],
    complete_resource_view_ids: Collection[str],
    resource_views: Mapping[Path, Mapping[str, Collection[BrowserResource]]],
) -> None:
    if not resource_paths:
        return
    complete_views = set(complete_resource_view_ids) & active
    for view_id in active - complete_views:
        _merge_action(actions, BrowserAction(view_id, BrowserActionKind.RELOAD))
    for path in resource_paths:
        for view_id, references in resource_views.get(path, {}).items():
            if view_id not in active:
                continue
            candidate = (
                _resource_action(path, view_id, references)
                if view_id in complete_views
                else BrowserAction(view_id, BrowserActionKind.RELOAD)
            )
            _merge_action(actions, candidate)


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
    content_paths: tuple[Path, ...],
    resource_paths: tuple[Path, ...],
    known_render_sources: Collection[Path],
) -> str:
    if any(action.kind is not BrowserActionKind.RELOAD for action in actions):
        return "narrow-browser-update"
    if content_paths and any(path in set(known_render_sources) for path in content_paths):
        return "render-provenance"
    if content_paths and not resource_paths:
        return "known-direct-output"
    return "known-browser-dependency"


def _reload_all(
    paths: tuple[Path, ...],
    active: set[str],
    *,
    reason: str,
) -> BrowserUpdateDecision:
    return BrowserUpdateDecision(
        paths,
        tuple(BrowserAction(view_id, BrowserActionKind.RELOAD) for view_id in sorted(active)),
        (),
        reason,
    )
