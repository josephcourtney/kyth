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


class ChangeEffect(StrEnum):
    SERVER_RESTART = "server-restart"
    BROWSER_CHANGE = "browser-change"
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
    def other_paths(self) -> tuple[Path, ...]:
        return tuple(item.path for item in self.paths if item.effect is ChangeEffect.OTHER)


def classify_batch(batch: FileBatch) -> ChangeSet:
    classified = tuple(ClassifiedPath(path=path, effect=classify_path(path)) for path in batch.paths)
    return ChangeSet(batch=batch, paths=classified)


def classify_path(path: Path) -> ChangeEffect:
    if path.suffix.lower() in PYTHON_SUFFIXES:
        return ChangeEffect.SERVER_RESTART
    if path.name in RESTART_FILENAMES or _is_environment_file(path.name):
        return ChangeEffect.SERVER_RESTART
    if path.suffix.lower() in BROWSER_SUFFIXES:
        return ChangeEffect.BROWSER_CHANGE
    return ChangeEffect.OTHER


def _is_environment_file(name: str) -> bool:
    return name == ".env" or name.startswith(".env.")
