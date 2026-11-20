"""Entry point imported by the selected application interpreter.

The only initial imports are standard-library modules and Kyth's wire types.
The application's environment takes precedence over Kyth's optional runtime
fallbacks before the ASGI server and application modules are imported.
"""

from __future__ import annotations

import sys
import traceback
from multiprocessing.connection import Connection

from kyth.process.readiness import StartupEvent


class _InheritedSocket:
    def __init__(self, fd: int) -> None:
        self.fd = fd

    def detach(self) -> int:
        return self.fd


def main() -> int:
    if len(sys.argv) != 3:
        msg = "expected listening-socket and IPC file descriptors"
        raise ValueError(msg)

    listening_fd = int(sys.argv[1])
    channel = Connection(int(sys.argv[2]))
    try:
        settings = channel.recv()
        if not isinstance(settings, dict):
            msg = "invalid application worker configuration"
            raise TypeError(msg)

        # Do not alter project installations. When the project does not supply
        # Uvicorn, use Kyth's own installed pure-Python server dependencies.
        for root in settings["fallback_paths"]:
            if root not in sys.path:
                sys.path.append(root)

        from kyth.process.child import run_child  # noqa: PLC0415 - load runtime after fallback paths

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
    except Exception as exc:  # noqa: BLE001 - report arbitrary worker startup failures
        try:
            channel.send(StartupEvent.failed(f"{type(exc).__name__}: {exc}"))
        except (BrokenPipeError, EOFError, OSError):
            # The supervisor may already have disconnected.
            pass  # noqa: S110
        traceback.print_exc()
        return 1
    finally:
        channel.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
