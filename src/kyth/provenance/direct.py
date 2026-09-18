from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlsplit

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
        return {
            output: tuple(sorted(view_ids))
            for output, view_ids in grouped.items()
        }

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

    def normalize_changed_path(self, path: Path) -> Path:
        """Normalize a watcher path into the same identity used by the index."""
        return _normalize_path(path)

    def _resolve_view(self, url: str) -> Path | None:
        relative = direct_document_relative_path(url)
        if relative is None:
            return None

        candidates = tuple(
            candidate
            for root in self._roots
            if (candidate := _candidate(root, relative)).is_file()
        )
        if len(candidates) != 1:
            return None
        return candidates[0]


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


def _candidate(root: Path, relative: PurePosixPath) -> Path:
    return _normalize_path(root.joinpath(*relative.parts))


def _normalize_path(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)
