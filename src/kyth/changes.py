from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from kyth.model import FileBatch

PYTHON_SUFFIXES = frozenset({".py", ".pyi", ".pyx"})
BROWSER_SUFFIXES = frozenset({
    ".css",
    ".gif",
    ".htm",
    ".html",
    ".ico",
    ".jpeg",
    ".jpg",
    ".js",
    ".json",
    ".map",
    ".mjs",
    ".cjs",
    ".otf",
    ".png",
    ".svg",
    ".ttf",
    ".webp",
    ".woff",
    ".woff2",
})
RESTART_FILENAMES = frozenset({"pyproject.toml"})


@dataclass(frozen=True, slots=True)
class ChangePolicy:
    """Configurable additions to Kyth's conservative default change policy."""

    restart_patterns: tuple[str, ...] = ()
    external_hmr_patterns: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """Validate configured path patterns."""
        if any(not pattern.strip() for pattern in self.restart_patterns):
            msg = "restart patterns must be non-empty"
            raise ValueError(msg)
        if any(not pattern.strip() for pattern in self.external_hmr_patterns):
            msg = "external HMR patterns must be non-empty"
            raise ValueError(msg)


class ChangeEffect(StrEnum):
    SERVER_RESTART = "server-restart"
    BROWSER_CHANGE = "browser-change"
    EXTERNAL_HMR = "external-hmr"
    OTHER = "other"


@dataclass(frozen=True, slots=True)
class ClassifiedPath:
    path: Path
    effect: ChangeEffect


@dataclass(frozen=True, slots=True)
class ChangeSet:
    batch: FileBatch
    paths: tuple[ClassifiedPath, ...]

    @property
    def requires_restart(self) -> bool:
        return any(item.effect is ChangeEffect.SERVER_RESTART for item in self.paths)

    @property
    def restart_paths(self) -> tuple[Path, ...]:
        return tuple(item.path for item in self.paths if item.effect is ChangeEffect.SERVER_RESTART)

    @property
    def browser_paths(self) -> tuple[Path, ...]:
        return tuple(item.path for item in self.paths if item.effect is ChangeEffect.BROWSER_CHANGE)

    @property
    def external_hmr_paths(self) -> tuple[Path, ...]:
        return tuple(item.path for item in self.paths if item.effect is ChangeEffect.EXTERNAL_HMR)

    @property
    def other_paths(self) -> tuple[Path, ...]:
        return tuple(item.path for item in self.paths if item.effect is ChangeEffect.OTHER)


def classify_batch(batch: FileBatch, *, policy: ChangePolicy | None = None) -> ChangeSet:
    active_policy = policy or ChangePolicy()
    classified = tuple(
        ClassifiedPath(path=path, effect=classify_path(path, policy=active_policy)) for path in batch.paths
    )
    return ChangeSet(batch=batch, paths=classified)


def classify_path(path: Path, *, policy: ChangePolicy | None = None) -> ChangeEffect:
    active_policy = policy or ChangePolicy()
    if path.suffix.lower() in PYTHON_SUFFIXES:
        return ChangeEffect.SERVER_RESTART
    if path.name in RESTART_FILENAMES or _is_environment_file(path.name):
        return ChangeEffect.SERVER_RESTART
    if any(path.match(pattern) for pattern in active_policy.restart_patterns):
        return ChangeEffect.SERVER_RESTART
    if any(path.match(pattern) for pattern in active_policy.external_hmr_patterns):
        return ChangeEffect.EXTERNAL_HMR
    if path.suffix.lower() in BROWSER_SUFFIXES:
        return ChangeEffect.BROWSER_CHANGE
    return ChangeEffect.OTHER


def _is_environment_file(name: str) -> bool:
    return name == ".env" or name.startswith(".env.")
