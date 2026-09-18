from __future__ import annotations

from pathlib import PurePosixPath
from typing import TYPE_CHECKING
from urllib.parse import unquote, urlsplit

if TYPE_CHECKING:
    from collections.abc import Collection, Mapping
    from pathlib import Path

    from kyth.model import BrowserResource

HTML_SUFFIXES = frozenset({".htm", ".html"})


class DirectOutputIndex:
    """Track direct URL-to-HTML-output relationships observed in active views."""

    def __init__(self, roots: tuple[Path, ...]) -> None:
        """Create an index over filesystem roots that may directly serve documents."""
        self._roots = tuple(_normalize_path(root) for root in roots)
        self._view_outputs: dict[str, Path] = {}
        self._known_outputs: set[Path] = set()

    @property
    def known_outputs(self) -> frozenset[Path]:
        return frozenset(self._known_outputs)

    @property
    def output_views(self) -> dict[Path, tuple[str, ...]]:
        grouped: dict[Path, list[str]] = {}
        for view_id, output in self._view_outputs.items():
            grouped.setdefault(output, []).append(view_id)
        return {output: tuple(sorted(view_ids)) for output, view_ids in grouped.items()}

    def reconcile(self, view_urls: Mapping[str, str]) -> None:
        """Refresh active direct mappings while retaining previously observed outputs."""
        active_ids = set(view_urls)
        for view_id in tuple(self._view_outputs):
            if view_id not in active_ids:
                del self._view_outputs[view_id]

        for view_id, url in view_urls.items():
            output = self._resolve_view(url)
            if output is None:
                self._view_outputs.pop(view_id, None)
                continue
            self._view_outputs[view_id] = output
            self._known_outputs.add(output)

    @staticmethod
    def normalize_changed_path(path: Path) -> Path:
        """Normalize a watcher path into the same identity used by the index."""
        return _normalize_path(path)

    def _resolve_view(self, url: str) -> Path | None:
        relative = direct_document_relative_path(url)
        if relative is None:
            return None

        return _resolve_candidate(
            self._roots,
            relative,
            known_paths=self._known_outputs,
        )


class DirectResourceIndex:
    """Track direct browser-resource URLs observed in active views."""

    def __init__(self, roots: tuple[Path, ...]) -> None:
        """Create an index over filesystem roots that may directly serve resources."""
        self._roots = tuple(_normalize_path(root) for root in roots)
        self._view_resources: dict[str, dict[Path, tuple[BrowserResource, ...]]] = {}
        self._known_resources: set[Path] = set()
        self._complete_views: set[str] = set()

    @property
    def known_resources(self) -> frozenset[Path]:
        return frozenset(self._known_resources)

    @property
    def complete_view_ids(self) -> frozenset[str]:
        return frozenset(self._complete_views)

    @property
    def resource_views(self) -> dict[Path, dict[str, tuple[BrowserResource, ...]]]:
        grouped: dict[Path, dict[str, tuple[BrowserResource, ...]]] = {}
        for view_id, resources in self._view_resources.items():
            for path, references in resources.items():
                grouped.setdefault(path, {})[view_id] = references
        return grouped

    def reconcile(
        self,
        view_resources: Mapping[str, Collection[BrowserResource]],
        *,
        complete_view_ids: Collection[str],
    ) -> None:
        """Refresh active resource mappings while retaining previously observed paths."""
        active_ids = set(view_resources)
        self._complete_views = active_ids & set(complete_view_ids)

        for view_id in tuple(self._view_resources):
            if view_id not in active_ids:
                del self._view_resources[view_id]

        for view_id, resources in view_resources.items():
            resolved: dict[Path, list[BrowserResource]] = {}
            for resource in resources:
                path = self._resolve_resource(resource.url)
                if path is None:
                    continue
                resolved.setdefault(path, []).append(resource)
                self._known_resources.add(path)

            self._view_resources[view_id] = {
                path: tuple(sorted(references, key=lambda item: (item.url, item.kind.value)))
                for path, references in resolved.items()
            }

    @staticmethod
    def normalize_changed_path(path: Path) -> Path:
        """Normalize a watcher path into the same identity used by the index."""
        return _normalize_path(path)

    def _resolve_resource(self, url: str) -> Path | None:
        relative = direct_resource_relative_path(url)
        if relative is None:
            return None

        return _resolve_candidate(
            self._roots,
            relative,
            known_paths=self._known_resources,
        )


def direct_document_relative_path(url: str) -> PurePosixPath | None:
    """Return the direct HTML path implied by a URL, or None when ambiguous."""
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.path.startswith("/"):
        return None

    decoded = unquote(parsed.path)
    relative = PurePosixPath(decoded.removeprefix("/"))
    if any(part in {"", ".", ".."} for part in relative.parts):
        return None

    if decoded.endswith("/"):
        return relative / "index.html"

    if relative.suffix.lower() in HTML_SUFFIXES:
        return relative
    return None


def direct_resource_relative_path(url: str) -> PurePosixPath | None:
    """Return the explicit resource path implied by a URL, or None when ambiguous."""
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.path.startswith("/"):
        return None

    decoded = unquote(parsed.path)
    if decoded.endswith("/"):
        return None
    relative = PurePosixPath(decoded.removeprefix("/"))
    if not relative.parts or any(part in {"", ".", ".."} for part in relative.parts):
        return None
    return relative


def _resolve_candidate(
    roots: tuple[Path, ...],
    relative: PurePosixPath,
    *,
    known_paths: set[Path],
) -> Path | None:
    candidates = tuple(
        candidate
        for root in roots
        if (candidate := _candidate(root, relative)) is not None
    )
    existing = tuple(candidate for candidate in candidates if candidate.is_file())
    if len(existing) == 1:
        return existing[0]

    known = tuple(candidate for candidate in candidates if candidate in known_paths)
    if len(known) == 1:
        return known[0]
    return None


def _candidate(root: Path, relative: PurePosixPath) -> Path | None:
    candidate = _normalize_path(root.joinpath(*relative.parts))
    if not candidate.is_relative_to(root):
        return None
    return candidate


def _normalize_path(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)
