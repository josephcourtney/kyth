from __future__ import annotations

import argparse
import contextlib
import logging
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
    parser.add_argument("--host", default="127.0.0.1", help="application host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="application port (default: 8000)")
    parser.add_argument("--startup-timeout", type=float, default=10.0, help="seconds to wait for ASGI startup")
    parser.add_argument("--shutdown-timeout", type=float, default=2.0, help="seconds to wait for graceful shutdown")
    return parser


def cli(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    config = SupervisorConfig(
        app_target=args.app,
        host=args.host,
        port=args.port,
        startup_timeout=args.startup_timeout,
        shutdown_timeout=args.shutdown_timeout,
    )

    with Supervisor(config) as supervisor:
        supervisor.start_child()
        with contextlib.suppress(KeyboardInterrupt):
            supervisor.run_forever()
    return 0
