from __future__ import annotations

import argparse
import contextlib
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from kyth.supervisor import Supervisor, SupervisorConfig

if TYPE_CHECKING:
    from collections.abc import Sequence


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="kyth",
        description="Run an ASGI application under the Kyth development supervisor.",
    )
    parser.add_argument("app", help="ASGI import target, for example package.module:app")
    parser.add_argument("-v", "--verbose", action="store_true", help="show detailed reload-decision diagnostics")
    parser.add_argument("--host", default="127.0.0.1", help="application host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="application port (default: 8000)")
    parser.add_argument("--startup-timeout", type=float, default=10.0, help="seconds to wait for ASGI startup")
    parser.add_argument("--shutdown-timeout", type=float, default=2.0, help="seconds to wait for graceful shutdown")
    parser.add_argument(
        "--watch",
        dest="watch_roots",
        action="append",
        type=Path,
        help="path to watch recursively; may be repeated (default: current directory)",
    )
    parser.add_argument(
        "--ignore",
        dest="ignored_paths",
        action="append",
        type=Path,
        default=[],
        help="additional path to ignore; may be repeated",
    )
    parser.add_argument(
        "--manifest",
        dest="manifest_paths",
        action="append",
        type=Path,
        default=[],
        help="generated dependency manifest; may be repeated",
    )
    parser.add_argument(
        "--restart-on",
        dest="restart_patterns",
        action="append",
        default=[],
        metavar="PATTERN",
        help="additional path pattern that requires application restart; may be repeated",
    )
    parser.add_argument(
        "--external-hmr-on",
        dest="external_hmr_patterns",
        action="append",
        default=[],
        metavar="PATTERN",
        help="browser path pattern owned by an external HMR server; may be repeated",
    )
    parser.add_argument(
        "--control-port",
        type=int,
        default=0,
        help="loopback browser-control port (default: choose an available port)",
    )
    return parser


def cli(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    watch_roots = tuple(args.watch_roots) if args.watch_roots else (Path.cwd(),)
    config = SupervisorConfig(
        app_target=args.app,
        host=args.host,
        port=args.port,
        startup_timeout=args.startup_timeout,
        shutdown_timeout=args.shutdown_timeout,
        watch_roots=watch_roots,
        ignored_paths=tuple(args.ignored_paths),
        control_port=args.control_port,
        manifest_paths=tuple(args.manifest_paths),
        restart_patterns=tuple(args.restart_patterns),
        external_hmr_patterns=tuple(args.external_hmr_patterns),
    )

    with Supervisor(config) as supervisor, contextlib.suppress(KeyboardInterrupt):
        supervisor.run_forever()
    return 0
