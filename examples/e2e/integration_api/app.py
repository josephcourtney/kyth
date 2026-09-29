from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from kyth.injection import depend_on, depend_on_data, register_readiness_check

ROOT = Path(__file__).parent
PAGE_TEXT = ROOT / "content" / "page.txt"
OTHER_TEXT = ROOT / "content" / "other.txt"
COUNTER_DATA = ROOT / "data" / "counter.json"
READY_FLAG = ROOT / "ready.flag"


@register_readiness_check
def example_ready() -> bool:
    return READY_FLAG.read_text(encoding="utf-8").strip() == "ready"


def _counter() -> int:
    payload = json.loads(COUNTER_DATA.read_text(encoding="utf-8"))
    return int(payload["value"])


def _home() -> bytes:
    depend_on(PAGE_TEXT)
    depend_on_data("counter", COUNTER_DATA)
    text = PAGE_TEXT.read_text(encoding="utf-8").strip()
    counter = _counter()
    return f"""<!doctype html>
<html>
<head><meta charset="utf-8"><title>Kyth integration API</title></head>
<body>
  <nav><a href="/">Home</a> <a href="/other">Other</a></nav>
  <h1>Explicit integration APIs</h1>
  <p>{text}</p>
  <p>Counter: <strong id="counter">{counter}</strong></p>
  <label>Draft <input id="draft" value=""></label>
  <p id="server-error"></p>
  <script>
    const counter = document.querySelector("#counter");
    const draft = document.querySelector("#draft");
    const serverError = document.querySelector("#server-error");

    addEventListener("kyth:data-update", (event) => {{
      if (event.detail.identity !== "counter") return;
      event.detail.handle(
        fetch("/api/counter", {{cache: "no-store"}})
          .then((response) => response.json())
          .then((payload) => {{ counter.textContent = String(payload.value); }})
      );
    }});

    addEventListener("kyth:before-reload", (event) => {{
      event.detail.preserve({{draft: draft.value}});
    }});

    addEventListener("kyth:restore-state", (event) => {{
      if (event.detail.state?.draft) draft.value = event.detail.state.draft;
    }});

    addEventListener("kyth:server-error", (event) => {{
      serverError.textContent = event.detail.message;
    }});
  </script>
</body>
</html>
""".encode()


def _other() -> bytes:
    depend_on(OTHER_TEXT)
    text = OTHER_TEXT.read_text(encoding="utf-8").strip()
    return f"""<!doctype html>
<html>
<head><meta charset="utf-8"><title>Other</title></head>
<body>
  <h1>Unrelated view</h1>
  <p>{text}</p>
  <a href="/">Home</a>
</body>
</html>
""".encode()


async def _respond(send: Any, status: int, body: bytes, content_type: str) -> None:
    await send({
        "type": "http.response.start",
        "status": status,
        "headers": [(b"content-type", content_type.encode())],
    })
    await send({"type": "http.response.body", "body": body})


async def app(scope: dict[str, Any], _receive: Any, send: Any) -> None:
    if scope.get("type") != "http":
        return

    path = str(scope.get("path", "/"))
    if path == "/":
        await _respond(send, 200, _home(), "text/html; charset=utf-8")
        return
    if path == "/other":
        await _respond(send, 200, _other(), "text/html; charset=utf-8")
        return
    if path == "/api/counter":
        body = json.dumps({"value": _counter()}).encode()
        await _respond(send, 200, body, "application/json")
        return

    await _respond(send, 404, b"not found\n", "text/plain; charset=utf-8")
