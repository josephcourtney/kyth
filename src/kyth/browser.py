from __future__ import annotations

import functools
import importlib.resources
import json
from dataclasses import dataclass

from starlette.responses import PlainTextResponse, Response
from starlette.websockets import WebSocket, WebSocketDisconnect

from kyth.constants import WS_PATH
from kyth.logging import info


@functools.cache
def _payload_template() -> str:
    return importlib.resources.files("kyth.resources").joinpath("payload.js").read_text(encoding="utf-8")


def make_devclient_js(ws_path: str = WS_PATH) -> str:
    return (
        _payload_template()
        .replace(
            "__KYTH_WS_PATH__",
            json.dumps(ws_path),
        )
        .lstrip()
    )


def pretty_console_args(args: object) -> list[str]:
    if not isinstance(args, list):
        return []

    pretty_args: list[str] = []
    for arg in args:
        try:
            parsed_arg = json.loads(arg) if isinstance(arg, str) else arg
            pretty_args.append(json.dumps(parsed_arg, indent=2))
        except (json.JSONDecodeError, TypeError):
            pretty_args.append(str(arg))
    return pretty_args


@dataclass(frozen=True, slots=True)
class BrowserMessage:
    type: str
    payload: dict[str, object]


def parse_browser_message(raw: str) -> BrowserMessage | None:
    try:
        msg = json.loads(raw)
    except json.JSONDecodeError:
        return None

    if not isinstance(msg, dict):
        return None

    msg_type = msg.get("type")
    payload = msg.get("payload", {})

    if not isinstance(msg_type, str) or not isinstance(payload, dict):
        return None

    return BrowserMessage(type=msg_type, payload=payload)


def devclient_response(devclient_js: str) -> Response:
    return PlainTextResponse(
        devclient_js,
        media_type="application/javascript",
        headers={"Cache-Control": "no-store, no-cache, must-revalidate"},
    )


async def websocket_handler(websocket: WebSocket, *, clients: set[WebSocket]) -> None:
    await websocket.accept()
    clients.add(websocket)
    peer = websocket.client
    info(f"[ws] connected: {peer}")

    try:
        while True:
            raw = await websocket.receive_text()
            parsed = parse_browser_message(raw)
            if parsed is None:
                info("[browser] <invalid json>", raw)
                continue

            if parsed.type == "hello":
                url = str(parsed.payload.get("url", ""))
                title = str(parsed.payload.get("title", ""))
                suffix = f" ({title})" if title else ""
                info(f"[browser] page connected: {url}{suffix}")
                continue

            if parsed.type == "console":
                level = str(parsed.payload.get("level", "log"))
                url = str(parsed.payload.get("url", ""))
                info(f"[browser:{level}] {url}", *pretty_console_args(parsed.payload.get("args")))
                continue

            info(f"[ws] unknown message type: {parsed.type}")
    except WebSocketDisconnect:
        pass
    except (RuntimeError, OSError) as exc:
        info(f"[ws] connection error: {exc}")
    finally:
        clients.discard(websocket)
        info(f"[ws] disconnected: {peer}")
