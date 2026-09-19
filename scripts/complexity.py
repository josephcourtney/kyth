from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from typing import TYPE_CHECKING

from radon.complexity import cc_rank, cc_visit
from radon.raw import analyze

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence


@dataclass(frozen=True, slots=True)
class ComplexityBlock:
    path: Path
    line: int
    name: str
    complexity: int

    @property
    def rank(self) -> str:
        return cc_rank(self.complexity)


def _python_files(roots: Sequence[Path]) -> tuple[Path, ...]:
    files: set[Path] = set()
    for root in roots:
        if root.is_file():
            if root.suffix == ".py":
                files.add(root)
            continue
        files.update(path for path in root.rglob("*.py") if path.is_file())
    return tuple(sorted(files, key=lambda path: path.as_posix()))


def _blocks(path: Path) -> tuple[ComplexityBlock, ...]:
    source = path.read_text(encoding="utf-8")
    return tuple(
        ComplexityBlock(
            path=path,
            line=block.lineno,
            name=block.fullname,
            complexity=block.complexity,
        )
        for block in cc_visit(source)
    )


def _all_blocks(paths: Iterable[Path]) -> tuple[ComplexityBlock, ...]:
    return tuple(block for path in paths for block in _blocks(path))


def _print_complexity(blocks: Sequence[ComplexityBlock]) -> None:
    if not blocks:
        print("No complexity blocks found.")
        return

    for block in blocks:
        print(f"{block.path}:{block.line}: {block.rank} ({block.complexity}) {block.name}")

    print()
    print(f"Average complexity: {mean(block.complexity for block in blocks):.2f}")


def _run_report(paths: Sequence[Path]) -> int:
    _print_complexity(_all_blocks(paths))
    return 0


def _run_strict(paths: Sequence[Path], threshold: int) -> int:
    offenders = tuple(block for block in _all_blocks(paths) if block.complexity >= threshold)
    if not offenders:
        print(f"[complexity] all blocks are below {threshold}")
        return 0

    print(f"[complexity] {len(offenders)} block(s) have complexity >= {threshold}:")
    _print_complexity(offenders)
    return 1


def _run_raw(paths: Sequence[Path]) -> int:
    for path in paths:
        metrics = analyze(path.read_text(encoding="utf-8"))
        print(path)
        print(f"  LOC: {metrics.loc}")
        print(f"  LLOC: {metrics.lloc}")
        print(f"  SLOC: {metrics.sloc}")
        print(f"  comments: {metrics.comments}")
        print(f"  multi: {metrics.multi}")
        print(f"  blank: {metrics.blank}")
        print(f"  single comments: {metrics.single_comments}")
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Report Python complexity using Radon's library API.",
    )
    subparsers = parser.add_subparsers(dest="mode", required=True)

    report = subparsers.add_parser("report")
    report.add_argument("roots", nargs="+", type=Path)

    strict = subparsers.add_parser("strict")
    strict.add_argument("--threshold", type=int, required=True)
    strict.add_argument("roots", nargs="+", type=Path)

    raw = subparsers.add_parser("raw")
    raw.add_argument("roots", nargs="+", type=Path)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    roots = tuple(args.roots)

    missing = tuple(root for root in roots if not root.exists())
    if missing:
        parser.error("path does not exist: " + ", ".join(path.as_posix() for path in missing))

    files = _python_files(roots)
    if not files:
        parser.error("no Python files found")

    if args.mode == "strict" and args.threshold < 1:
        parser.error("--threshold must be at least 1")

    if args.mode == "raw":
        return _run_raw(files)
    if args.mode == "strict":
        return _run_strict(files, args.threshold)
    return _run_report(files)


if __name__ == "__main__":
    raise SystemExit(main())
