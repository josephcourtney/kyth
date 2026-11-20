"""Entry point imported by the selected application interpreter.

The only initial imports are standard-library modules and Kyth's wire types.
The application's environment takes precedence over Kyth's optional runtime
fallbacks before the ASGI server and application modules are imported.
"""

from __future__ import annotations

import contextlib
import sys
import traceback
from multiprocessing.connection import Connection
from typing import TypedDict, cast

from kyth.process.readiness import StartupEvent

EXPECTED_ARGUMENT_COUNT = 3


class _WorkerSettings(TypedDict):
    app_target: str
    import_root: str
    socket_family: int
    socket_type: int
    socket_proto: int
    control_url: str
    control_token: str
    generation: int
    fallback_paths: tuple[str, ...]


class _InheritedSocket:
    def __init__(self, fd: int) -> None:
        self.fd = fd

    def detach(self) -> int:
        return self.fd


def _receive_settings(channel: Connection) -> _WorkerSettings:
    """Reject malformed bootstrap envelopes before loading the ASGI runtime."""
    settings = channel.recv()
    if not isinstance(settings, dict):
        msg = "invalid application worker configuration"
        raise TypeError(msg)
    return cast("_WorkerSettings", settings)


def _run_worker(channel: Connection, listening_fd: int) -> None:
    """Import the runtime after setting project-priority fallback paths."""
    settings = _receive_settings(channel)
    for root in settings["fallback_paths"]:
        if root not in sys.path:
            sys.path.append(root)

    # Worker-only dependencies must load after environment fallbacks.
    from kyth.process.child import run_child  # noqa: PLC0415

    run_child(
        settings["app_target"],
        settings["import_root"],
        _InheritedSocket(listening_fd),
        settings["socket_family"],
        settings["socket_type"],
        settings["socket_proto"],
        settings["control_url"],
        settings["control_token"],
        settings["generation"],
        channel,
        channel,
    )


def main() -> int:
    """Run a single worker and translate startup errors to protocol events."""
    if len(sys.argv) != EXPECTED_ARGUMENT_COUNT:
        msg = "expected listening-socket and IPC file descriptors"
        raise ValueError(msg)

    listening_fd = int(sys.argv[1])
    channel = Connection(int(sys.argv[2]))
    try:
        _run_worker(channel, listening_fd)
    except Exception as exc:  # noqa: BLE001
        # The supervisor may already have disconnected.
        with contextlib.suppress(BrokenPipeError, EOFError, OSError):
            channel.send(StartupEvent.failed(f"{type(exc).__name__}: {exc}"))
        traceback.print_exc()
        return 1
    finally:
        channel.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
