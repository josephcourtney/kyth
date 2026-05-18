from __future__ import annotations

import importlib
import sys


DEFAULT_PUBLIC_MODULES = [
    "kyth",
    "kyth.core",
]


def main(modules: list[str] | None = None) -> int:
    module_names = modules or DEFAULT_PUBLIC_MODULES

    for module_name in module_names:
        module = importlib.import_module(module_name)
        exported = getattr(module, "__all__", ())

        missing = [name for name in exported if not hasattr(module, name)]
        if missing:
            print(f"{module_name}: missing exports: {', '.join(missing)}", file=sys.stderr)
            return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
