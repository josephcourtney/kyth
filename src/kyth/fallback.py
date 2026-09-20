from __future__ import annotations

import os
from dataclasses import dataclass
from fnmatch import fnmatchcase
from functools import cache
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import unquote, urlsplit

if TYPE_CHECKING:
    from collections.abc import Collection, Mapping


@dataclass(frozen=True, slots=True)
class FallbackScopeRule:
    """Trusted assertion that matching sources affect only a URL-path scope."""

    source_pattern: str
    url_pattern: str

    def __post_init__(self) -> None:
        """Validate source and URL glob syntax eagerly."""
        _validate_source_pattern(self.source_pattern)
        _validate_url_pattern(self.url_pattern)


@dataclass(frozen=True, slots=True)
class FallbackScopeResolution:
    """Resolved active-view scope for one changed source path."""

    path: Path
    rules: tuple[FallbackScopeRule, ...]
    view_ids: tuple[str, ...]


class FallbackScopeIndex:
    """Resolve configured fallback rules outside pure invalidation policy."""

    def __init__(
        self,
        roots: Collection[Path],
        rules: Collection[FallbackScopeRule],
    ) -> None:
        self._roots = tuple(_normalize_path(path) for path in roots)
        self._rules = tuple(rules)

    @property
    def rules(self) -> tuple[FallbackScopeRule, ...]:
        return self._rules

    def source_rules(self, path: Path) -> tuple[FallbackScopeRule, ...]:
        """Return all rules matching any valid root-relative representation."""
        relative_paths = _relative_paths(path, self._roots)
        return tuple(
            rule
            for rule in self._rules
            if any(_glob_matches(rule.source_pattern, relative) for relative in relative_paths)
        )

    def matching_source_paths(self, paths: Collection[Path]) -> frozenset[Path]:
        """Return changed paths declared browser-relevant by a scope rule."""
        return frozenset(path for path in paths if self.source_rules(path))

    def resolve(
        self,
        paths: Collection[Path],
        view_urls: Mapping[str, str],
    ) -> tuple[FallbackScopeResolution, ...]:
        """Resolve matching source rules into active candidate view IDs."""
        resolutions: list[FallbackScopeResolution] = []
        for path in paths:
            rules = self.source_rules(path)
            if not rules:
                continue
            selected = tuple(
                sorted(view_id for view_id, url in view_urls.items() if _view_matches_any_rule(url, rules))
            )
            resolutions.append(
                FallbackScopeResolution(
                    _normalize_path(path),
                    rules,
                    selected,
                )
            )
        return tuple(resolutions)


def scope_view_mapping(
    resolutions: Collection[FallbackScopeResolution],
) -> dict[Path, tuple[str, ...]]:
    """Convert scope resolutions to the pure invalidation input mapping."""
    return {resolution.path: resolution.view_ids for resolution in resolutions}


def _normalize_path(path: Path) -> Path:
    # Scope matching is lexical; resolving through the filesystem would make pure policy depend on I/O.
    return Path(os.path.abspath(path.expanduser()))  # ruff: ignore[os-path-abspath]


def _relative_paths(path: Path, roots: tuple[Path, ...]) -> tuple[str, ...]:
    resolved = _normalize_path(path)
    relative: set[str] = set()
    for root in roots:
        try:
            candidate = resolved.relative_to(root).as_posix()
        except ValueError:
            continue
        if candidate != ".":
            relative.add(candidate)
    return tuple(sorted(relative))


def _view_matches_any_rule(url: str, rules: tuple[FallbackScopeRule, ...]) -> bool:
    path = _normalized_url_path(url)
    if path is None:
        return True
    candidate = path.removeprefix("/")
    return any(_glob_matches(rule.url_pattern.removeprefix("/"), candidate) for rule in rules)


def _normalized_url_path(url: str) -> str | None:
    try:
        parsed = urlsplit(url)
        decoded = unquote(parsed.path)
    except (UnicodeError, ValueError):
        return None
    if not decoded.startswith("/") or "\\" in decoded or "\x00" in decoded:
        return None
    trailing_slash = decoded.endswith("/") and decoded != "/"
    parts = decoded.split("/")[1:]
    if trailing_slash:
        parts = parts[:-1]
    if any(part in {"", ".", ".."} for part in parts):
        return None
    normalized = "/" + "/".join(parts)
    if trailing_slash:
        normalized += "/"
    return normalized


def _glob_matches(pattern: str, candidate: str) -> bool:
    pattern_parts = tuple(part for part in pattern.split("/") if part)
    candidate_parts = tuple(part for part in candidate.split("/") if part)

    @cache
    def match(pattern_index: int, candidate_index: int) -> bool:
        if pattern_index == len(pattern_parts):
            return candidate_index == len(candidate_parts)

        part = pattern_parts[pattern_index]
        if part == "**":
            return match(pattern_index + 1, candidate_index) or (
                candidate_index < len(candidate_parts) and match(pattern_index, candidate_index + 1)
            )

        if candidate_index == len(candidate_parts):
            return False
        return fnmatchcase(candidate_parts[candidate_index], part) and match(
            pattern_index + 1,
            candidate_index + 1,
        )

    return match(0, 0)


def _validate_source_pattern(pattern: str) -> None:
    if not pattern or pattern.strip() != pattern:
        msg = "fallback scope source pattern must be non-empty and unpadded"
        raise ValueError(msg)
    if pattern.startswith("/") or "\\" in pattern:
        msg = "fallback scope source pattern must be a relative POSIX path glob"
        raise ValueError(msg)
    _validate_pattern_parts(pattern, label="source")


def _validate_url_pattern(pattern: str) -> None:
    if not pattern or pattern.strip() != pattern or not pattern.startswith("/"):
        msg = "fallback scope URL pattern must be an absolute path glob"
        raise ValueError(msg)
    if "\\" in pattern or "#" in pattern:
        msg = "fallback scope URL pattern must be a normalized POSIX path glob"
        raise ValueError(msg)
    _validate_pattern_parts(pattern.removeprefix("/"), label="URL")


def _validate_pattern_parts(pattern: str, *, label: str) -> None:
    parts = pattern.split("/")
    if pattern == "":
        return
    if any(part in {"", ".", ".."} for part in parts):
        msg = f"fallback scope {label} pattern must be normalized"
        raise ValueError(msg)
