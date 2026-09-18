from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Collection

MANIFEST_VERSION = 1
MAX_MANIFEST_OUTPUTS = 10_000
MAX_SOURCES_PER_OUTPUT = 10_000
HTML_SUFFIXES = frozenset({".htm", ".html"})


class ManifestError(ValueError):
    """Raised when a generated dependency manifest is invalid."""


@dataclass(frozen=True, slots=True)
class ManifestOutput:
    """One generated HTML output and its complete declared source set."""

    output: Path
    sources: tuple[Path, ...]


@dataclass(frozen=True, slots=True)
class DependencyManifest:
    """One validated versioned dependency manifest."""

    path: Path
    outputs: tuple[ManifestOutput, ...]


def load_manifest(path: Path) -> DependencyManifest:
    """Load and validate one versioned generated-site dependency manifest."""
    manifest_path = path.expanduser().resolve(strict=False)
    try:
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        msg = f"cannot load manifest {manifest_path}: {exc}"
        raise ManifestError(msg) from exc
    if not isinstance(raw, dict):
        msg = "manifest root must be a JSON object"
        raise ManifestError(msg)

    version = raw.get("version")
    if not isinstance(version, int) or isinstance(version, bool) or version != MANIFEST_VERSION:
        msg = f"unsupported manifest version: {version!r}"
        raise ManifestError(msg)

    raw_outputs = raw.get("outputs")
    if not isinstance(raw_outputs, list):
        msg = "manifest outputs must be a JSON array"
        raise ManifestError(msg)
    if len(raw_outputs) > MAX_MANIFEST_OUTPUTS:
        msg = "manifest contains too many outputs"
        raise ManifestError(msg)

    outputs = tuple(_parse_output(item, base=manifest_path.parent) for item in raw_outputs)
    paths = [entry.output for entry in outputs]
    if len(paths) != len(set(paths)):
        msg = "manifest output paths must be unique"
        raise ManifestError(msg)
    return DependencyManifest(manifest_path, tuple(sorted(outputs, key=lambda item: item.output.as_posix())))


class GeneratedManifestIndex:
    """Combine explicit generator manifests into source-to-output provenance."""

    def __init__(self, manifest_paths: tuple[Path, ...]) -> None:
        """Create an index for explicitly configured manifest files."""
        self._manifest_paths = tuple(path.expanduser().resolve(strict=False) for path in manifest_paths)
        self._manifests: dict[Path, DependencyManifest] = {}
        self._source_outputs: dict[Path, set[Path]] = {}
        self._known_outputs: set[Path] = set()
        self._stale_outputs: set[Path] = set()

    @property
    def manifest_paths(self) -> frozenset[Path]:
        return frozenset(self._manifest_paths)

    @property
    def known_outputs(self) -> frozenset[Path]:
        return frozenset(self._known_outputs)

    @property
    def known_sources(self) -> frozenset[Path]:
        return frozenset(self._source_outputs)

    @property
    def stale_outputs(self) -> frozenset[Path]:
        return frozenset(self._stale_outputs)

    @property
    def source_outputs(self) -> dict[Path, tuple[Path, ...]]:
        return {
            source: tuple(sorted(outputs, key=Path.as_posix))
            for source, outputs in self._source_outputs.items()
        }

    def load_all(self) -> None:
        """Load all configured manifests, raising on the first invalid manifest."""
        manifests = {path: load_manifest(path) for path in self._manifest_paths}
        source_outputs, known_outputs = _build_indexes(manifests.values())
        self._manifests = manifests
        self._source_outputs = source_outputs
        self._known_outputs = known_outputs
        self._stale_outputs &= known_outputs

    def reload_changed(self, changed_paths: Collection[Path]) -> tuple[Path, ...]:
        """Reload configured manifests touched by a filesystem batch transactionally."""
        changed = {_normalize_path(path) for path in changed_paths}
        targets = tuple(path for path in self._manifest_paths if path in changed)
        if not targets:
            return ()

        replacements = {path: load_manifest(path) for path in targets}
        manifests = {**self._manifests, **replacements}
        source_outputs, known_outputs = _build_indexes(manifests.values())
        self._manifests = manifests
        self._source_outputs = source_outputs
        self._known_outputs = known_outputs
        self._stale_outputs &= known_outputs
        return targets

    def mark_sources_changed(self, changed_paths: Collection[Path]) -> tuple[Path, ...]:
        """Mark generated outputs stale from source changes without browser action."""
        affected: set[Path] = set()
        for path in changed_paths:
            affected.update(self._source_outputs.get(_normalize_path(path), ()))
        self._stale_outputs.update(affected)
        return tuple(sorted(affected, key=Path.as_posix))

    def mark_outputs_updated(self, changed_paths: Collection[Path]) -> tuple[Path, ...]:
        """Clear stale outputs whose generated files were updated."""
        updated = {_normalize_path(path) for path in changed_paths}
        cleared = self._stale_outputs & updated
        self._stale_outputs.difference_update(cleared)
        return tuple(sorted(cleared, key=Path.as_posix))

def _build_indexes(
    manifests: Collection[DependencyManifest],
) -> tuple[dict[Path, set[Path]], set[Path]]:
    source_outputs: dict[Path, set[Path]] = {}
    known_outputs: set[Path] = set()
    for manifest in manifests:
        for entry in manifest.outputs:
            if entry.output in known_outputs:
                msg = f"generated output is declared by multiple manifests: {entry.output}"
                raise ManifestError(msg)
            known_outputs.add(entry.output)
            for source in entry.sources:
                source_outputs.setdefault(source, set()).add(entry.output)
    return source_outputs, known_outputs


def _parse_output(value: object, *, base: Path) -> ManifestOutput:
    if not isinstance(value, dict):
        msg = "each manifest output must be a JSON object"
        raise ManifestError(msg)
    output_value = value.get("output")
    sources_value = value.get("sources")
    if not isinstance(output_value, str):
        msg = "manifest output path must be a string"
        raise ManifestError(msg)
    if not isinstance(sources_value, list):
        msg = "manifest output sources must be a JSON array"
        raise ManifestError(msg)
    if len(sources_value) > MAX_SOURCES_PER_OUTPUT:
        msg = "manifest output contains too many sources"
        raise ManifestError(msg)

    output = _resolve_relative_path(output_value, base=base, label="output")
    if output.suffix.lower() not in HTML_SUFFIXES:
        msg = f"manifest output must be HTML: {output_value!r}"
        raise ManifestError(msg)

    sources: list[Path] = []
    for source_value in sources_value:
        if not isinstance(source_value, str):
            msg = "manifest source path must be a string"
            raise ManifestError(msg)
        sources.append(_resolve_relative_path(source_value, base=base, label="source"))
    if not sources:
        msg = f"manifest output must declare at least one source: {output_value!r}"
        raise ManifestError(msg)
    return ManifestOutput(output, tuple(sorted(set(sources), key=Path.as_posix)))


def _resolve_relative_path(value: str, *, base: Path, label: str) -> Path:
    pure = PurePosixPath(value)
    if pure.is_absolute() or not pure.parts or any(part in {"", ".", ".."} for part in pure.parts):
        msg = f"manifest {label} path must be a normalized relative path: {value!r}"
        raise ManifestError(msg)
    candidate = base.joinpath(*pure.parts).resolve(strict=False)
    if not candidate.is_relative_to(base):
        msg = f"manifest {label} path escapes manifest directory: {value!r}"
        raise ManifestError(msg)
    return candidate


def _normalize_path(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)
