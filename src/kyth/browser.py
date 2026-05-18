from __future__ import annotations

import json
from dataclasses import dataclass

from starlette.responses import PlainTextResponse, Response
from starlette.websockets import WebSocket, WebSocketDisconnect

from kyth.constants import WS_PATH
from kyth.logging import info


def make_devclient_js(ws_path: str = WS_PATH) -> str:
    return f"""
(() => {{
  if (window.__PY_DEVSERVER_INSTALLED__) return;
  window.__PY_DEVSERVER_INSTALLED__ = true;

  const WS_URL = `${{location.protocol === "https:" ? "wss" : "ws"}}://${{location.host}}{ws_path}`;
  let ws = null;
  let reconnectTimer = null;
  let intentionallyClosed = false;
  const timers = new Map();

  function stringify(value) {{
    try {{
      if (typeof value === "string") return value;
      if (value instanceof Error) return value.stack || `${{value.name}}: ${{value.message}}`;
      return JSON.stringify(value);
    }} catch {{
      try {{
        return String(value);
      }} catch {{
        return "[unprintable value]";
      }}
    }}
  }}

  function send(type, payload) {{
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    try {{
      ws.send(JSON.stringify({{ type, payload }}));
    }} catch {{
    }}
  }}

  function connect() {{
    ws = new WebSocket(WS_URL);

    ws.addEventListener("open", () => {{
      send("hello", {{
        url: location.href,
        title: document.title || "",
        userAgent: navigator.userAgent
      }});
    }});

    ws.addEventListener("message", (event) => {{
      let msg;
      try {{
        msg = JSON.parse(event.data);
      }} catch {{
        return;
      }}

      if (msg.type === "reload") {{
        location.reload();
        return;
      }}
    }});

    ws.addEventListener("close", () => {{
      if (intentionallyClosed) return;
      if (reconnectTimer) return;
      reconnectTimer = setTimeout(() => {{
        reconnectTimer = null;
        connect();
      }}, 500);
    }});
  }}

  for (const level of ["log", "info", "warn", "error", "debug"]) {{
    const original = console[level] ? console[level].bind(console) : null;
    console[level] = (...args) => {{
      try {{
        if (original) original(...args);
      }} finally {{
        send("console", {{
          level,
          url: location.href,
          args: args.map(stringify)
        }});
      }}
    }};
  }}

  const originalTime = console.time ? console.time.bind(console) : null;
  const originalTimeLog = console.timeLog ? console.timeLog.bind(console) : null;
  const originalTimeEnd = console.timeEnd ? console.timeEnd.bind(console) : null;

  console.time = (label = "default") => {{
    timers.set(String(label), performance.now());
    if (originalTime) originalTime(label);
  }};

  console.timeLog = (label = "default", ...args) => {{
    const key = String(label);
    const start = timers.get(key);
    if (start != null) {{
      const ms = performance.now() - start;
      send("console", {{
        level: "info",
        url: location.href,
        args: [`${{key}}: ${{ms.toFixed(3)}}ms`, ...args.map(stringify)]
      }});
    }}
    if (originalTimeLog) originalTimeLog(label, ...args);
  }};

  console.timeEnd = (label = "default") => {{
    const key = String(label);
    const start = timers.get(key);
    if (start != null) {{
      const ms = performance.now() - start;
      send("console", {{
        level: "info",
        url: location.href,
        args: [`${{key}}: ${{ms.toFixed(3)}}ms - timer ended`]
      }});
      timers.delete(key);
    }}
    if (originalTimeEnd) originalTimeEnd(label);
  }};

  window.addEventListener("error", (event) => {{
    send("console", {{
      level: "error",
      url: location.href,
      args: [
        `window.onerror: ${{event.message}}`,
        event.filename ? `file: ${{event.filename}}` : "",
        Number.isFinite(event.lineno) ? `line: ${{event.lineno}}` : "",
        Number.isFinite(event.colno) ? `col: ${{event.colno}}` : ""
      ].filter(Boolean)
    }});
  }});

  window.addEventListener("unhandledrejection", (event) => {{
    send("console", {{
      level: "error",
      url: location.href,
      args: ["unhandledrejection", stringify(event.reason)]
    }});
  }});

  connect();
}})();
""".lstrip()


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
