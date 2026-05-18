from __future__ import annotations

import sys


def info(*args: object) -> None:
    print(*args, file=sys.stderr, flush=True)


def eprint(*args: object) -> None:
    print(*args, file=sys.stderr, flush=True)
