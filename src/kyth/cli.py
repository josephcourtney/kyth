from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from kyth.constants import DEFAULT_HOST, DEFAULT_HTTP_PORT, DEFAULT_WS_PORT
from kyth.server import invoke_asgi_run_process, invoke_static_run_process

ROOT_ARGUMENT = typer.Argument(
    exists=False,
    file_okay=False,
    dir_okay=True,
    readable=True,
    resolve_path=False,
    help="Directory to serve.",
)
TARGET_ARGUMENT = typer.Argument(
    help="ASGI application target in module:app syntax.",
)
HOST_OPTION = typer.Option(help="Bind host.")
PORT_OPTION = typer.Option(min=0, max=65535, help="Preferred HTTP port.")
WS_PORT_OPTION = typer.Option(
    "--ws-port",
    min=0,
    max=65535,
    help="Ignored. Retained for CLI compatibility; WebSocket shares the HTTP port.",
    rich_help_panel="Compatibility",
)
NO_OPEN_OPTION = typer.Option("--no-open", help="Do not open the browser automatically.")
ON_CHANGE_OPTION = typer.Option(
    "--on-change",
    "-x",
    help="Shell command to run after selected files change.",
)
ON_CHANGE_PATH_OPTION = typer.Option(
    "--on-change-path",
    "--watch-command",
    "-w",
    help=(
        "File, directory, or glob that triggers --on-change. "
        "May be repeated. Relative paths are resolved from the invocation working directory."
    ),
)
WATCH_PATH_OPTION = typer.Option(
    "--watch",
    help=(
        "File, directory, or glob that triggers browser reload for ASGI apps. "
        "May be repeated. Relative paths are resolved from the invocation working directory."
    ),
)

cli = typer.Typer(
    add_completion=True,
    no_args_is_help=False,
    pretty_exceptions_enable=False,
    help="Static and ASGI dev server with HTML injection, browser console forwarding, and live reload.",
)


@cli.command(context_settings={"allow_extra_args": False})
def serve(
    ctx: typer.Context,
    root: Annotated[Path, ROOT_ARGUMENT] = Path(),
    host: Annotated[str, HOST_OPTION] = DEFAULT_HOST,
    port: Annotated[int, PORT_OPTION] = DEFAULT_HTTP_PORT,
    ws_port: Annotated[int, WS_PORT_OPTION] = DEFAULT_WS_PORT,
    on_change: Annotated[str | None, ON_CHANGE_OPTION] = None,
    on_change_path: Annotated[list[str] | None, ON_CHANGE_PATH_OPTION] = None,
    *,
    no_open: Annotated[bool, NO_OPEN_OPTION] = False,
) -> None:
    del ctx, ws_port

    raise typer.Exit(
        invoke_static_run_process(
            root=str(root),
            host=host,
            port=port,
            no_open=no_open,
            invocation_cwd=str(Path.cwd()),
            on_change=on_change,
            on_change_paths=tuple(on_change_path or ()),
        )
    )


@cli.command("asgi", context_settings={"allow_extra_args": False})
def asgi_app(
    ctx: typer.Context,
    target: Annotated[str, TARGET_ARGUMENT],
    host: Annotated[str, HOST_OPTION] = DEFAULT_HOST,
    port: Annotated[int, PORT_OPTION] = DEFAULT_HTTP_PORT,
    ws_port: Annotated[int, WS_PORT_OPTION] = DEFAULT_WS_PORT,
    watch: Annotated[list[str] | None, WATCH_PATH_OPTION] = None,
    on_change: Annotated[str | None, ON_CHANGE_OPTION] = None,
    on_change_path: Annotated[list[str] | None, ON_CHANGE_PATH_OPTION] = None,
    *,
    no_open: Annotated[bool, NO_OPEN_OPTION] = False,
) -> None:
    del ctx, ws_port

    raise typer.Exit(
        invoke_asgi_run_process(
            target=target,
            host=host,
            port=port,
            no_open=no_open,
            invocation_cwd=str(Path.cwd()),
            watch_paths=tuple(watch or ()),
            on_change=on_change,
            on_change_paths=tuple(on_change_path or ()),
        )
    )
