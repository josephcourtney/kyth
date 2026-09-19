from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from kyth.model import SourceVersion

if TYPE_CHECKING:
    from collections.abc import Collection, Mapping

    from kyth.model import RenderRecord


class RenderProvenanceIndex:
    """Index generic render records independently of their capture adapter."""

    def __init__(self) -> None:
        """Create an empty render provenance index."""
        self._records: dict[str, RenderRecord] = {}
        self._known_sources: set[Path] = set()
        self._known_render_sources: set[Path] = set()
        self._known_data_sources: set[Path] = set()
        self._source_views: dict[Path, set[str]] = {}
        self._source_view_versions: dict[Path, dict[str, SourceVersion]] = {}
        self._data_source_views: dict[Path, dict[str, set[str]]] = {}
        self._data_source_view_versions: dict[Path, dict[str, SourceVersion]] = {}
        self._complete_view_ids: set[str] = set()

    @property
    def known_sources(self) -> frozenset[Path]:
        return frozenset(self._known_sources)

    @property
    def known_render_sources(self) -> frozenset[Path]:
        return frozenset(self._known_render_sources)

    @property
    def known_data_sources(self) -> frozenset[Path]:
        return frozenset(self._known_data_sources)

    @property
    def data_source_views(self) -> dict[Path, dict[str, tuple[str, ...]]]:
        return {
            path: {view_id: tuple(sorted(identities)) for view_id, identities in views.items()}
            for path, views in self._data_source_views.items()
        }

    @property
    def source_views(self) -> dict[Path, tuple[str, ...]]:
        return {path: tuple(sorted(view_ids)) for path, view_ids in self._source_views.items()}

    @property
    def source_view_versions(self) -> dict[Path, dict[str, SourceVersion]]:
        return {path: dict(versions) for path, versions in self._source_view_versions.items()}

    @property
    def complete_view_ids(self) -> frozenset[str]:
        return frozenset(self._complete_view_ids)

    def reconcile(
        self,
        records: Collection[RenderRecord],
        view_render_ids: Mapping[str, str],
    ) -> None:
        """Refresh active render relationships while retaining known source identities."""
        self._records = {record.render_id: record for record in records}
        for record in self._records.values():
            for dependency in record.dependencies:
                path = _normalize_path(dependency.path)
                self._known_sources.add(path)
                self._known_render_sources.add(path)
            for dependency in record.data_dependencies:
                path = _normalize_path(dependency.source.path)
                self._known_sources.add(path)
                self._known_data_sources.add(path)

        source_views: dict[Path, set[str]] = {}
        source_view_versions: dict[Path, dict[str, SourceVersion]] = {}
        data_source_views: dict[Path, dict[str, set[str]]] = {}
        data_source_view_versions: dict[Path, dict[str, SourceVersion]] = {}
        complete_view_ids: set[str] = set()
        for view_id, render_id in view_render_ids.items():
            record = self._records.get(render_id)
            if record is None:
                continue
            if record.complete:
                complete_view_ids.add(view_id)
            for dependency in record.dependencies:
                path = _normalize_path(dependency.path)
                source_views.setdefault(path, set()).add(view_id)
                source_view_versions.setdefault(path, {})[view_id] = dependency
            for dependency in record.data_dependencies:
                path = _normalize_path(dependency.source.path)
                data_source_views.setdefault(path, {}).setdefault(view_id, set()).add(dependency.identity)
                data_source_view_versions.setdefault(path, {})[view_id] = dependency.source

        self._source_views = source_views
        self._source_view_versions = source_view_versions
        self._data_source_views = data_source_views
        self._data_source_view_versions = data_source_view_versions
        self._complete_view_ids = complete_view_ids

    def stale_source_views(
        self,
        changed_paths: Collection[Path],
    ) -> dict[Path, tuple[str, ...]]:
        """Return views whose recorded source version differs from the current file."""
        stale: dict[Path, tuple[str, ...]] = {}
        for changed_path in changed_paths:
            path = changed_path.expanduser().resolve(strict=False)
            current = _source_version(path)
            versions = self._source_view_versions.get(path, {})
            view_ids = tuple(sorted(view_id for view_id, version in versions.items() if version != current))
            if view_ids:
                stale[path] = view_ids
        return stale

    def stale_data_source_views(
        self,
        changed_paths: Collection[Path],
    ) -> dict[Path, dict[str, tuple[str, ...]]]:
        """Return semantic data identities for views whose recorded source is stale."""
        stale: dict[Path, dict[str, tuple[str, ...]]] = {}
        for changed_path in changed_paths:
            path = changed_path.expanduser().resolve(strict=False)
            current = _source_version(path)
            versions = self._data_source_view_versions.get(path, {})
            stale_views = {
                view_id: self._data_source_views[path][view_id]
                for view_id, version in versions.items()
                if version != current
            }
            if stale_views:
                stale[path] = stale_views
        return stale

    @staticmethod
    def normalize_changed_path(path: Path) -> Path:
        """Normalize a watcher path into the render source identity space."""
        return path.expanduser().resolve(strict=False)


def _source_version(path: Path) -> SourceVersion:
    try:
        stat = path.stat()
    except OSError:
        return SourceVersion(str(path), None, None)
    return SourceVersion(str(path), stat.st_mtime_ns, stat.st_size)


def _normalize_path(path: str) -> Path:
    return Path(path).expanduser().resolve(strict=False)
