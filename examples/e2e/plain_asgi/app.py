from __future__ import annotations

from pathlib import Path
from typing import Any

ROOT = Path(__file__).parent
STATIC = ROOT / "static"

STATIC_FILES = {
    "/static/site.css": ("text/css; charset=utf-8", STATIC / "site.css"),
    "/static/app.js": ("text/javascript; charset=utf-8", STATIC / "app.js"),
    "/static/badge.svg": ("image/svg+xml", STATIC / "badge.svg"),
}


def _page(title: str, body: str) -> bytes:
    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>{title}</title>
  <link rel="stylesheet" href="/static/site.css">
  <script src="/static/app.js" defer></script>
</head>
<body>
  <nav><a href="/">Home</a> <a href="/about">About</a></nav>
  <main>{body}</main>
  <p id="js-status">JavaScript has not run yet.</p>
</body>
</html>
""".encode()


async def _send(send: Any, status: int, body: bytes, content_type: str) -> None:
    await send({
        "type": "http.response.start",
        "status": status,
        "headers": [
            (b"content-type", content_type.encode()),
            (b"content-length", str(len(body)).encode()),
        ],
    })
    await send({"type": "http.response.body", "body": body})


async def app(scope: dict[str, Any], _receive: Any, send: Any) -> None:
    if scope.get("type") != "http":
        return

    path = str(scope.get("path", "/"))
    static_entry = STATIC_FILES.get(path)
    if static_entry is not None:
        content_type, file_path = static_entry
        await _send(send, 200, file_path.read_bytes(), content_type)
        return

    if path == "/":
        body = _page(
            "Kyth plain ASGI",
            '<h1>Plain ASGI</h1><p>Direct resources are visible below.</p><img src="/static/badge.svg" alt="Kyth test badge">',
        )
        await _send(send, 200, body, "text/html; charset=utf-8")
        return

    if path == "/about":
        body = _page("About", "<h1>About</h1><p>This is an independent browser view.</p>")
        await _send(send, 200, body, "text/html; charset=utf-8")
        return

    await _send(send, 404, b"not found\n", "text/plain; charset=utf-8")
