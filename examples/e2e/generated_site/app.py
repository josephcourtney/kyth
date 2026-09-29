from __future__ import annotations

from pathlib import Path
from typing import Any

ROOT = Path(__file__).parent
PUBLIC = ROOT / "public"
ROUTES = {
    "/": ("text/html; charset=utf-8", PUBLIC / "index.html"),
    "/notes/": ("text/html; charset=utf-8", PUBLIC / "notes.html"),
    "/site.css": ("text/css; charset=utf-8", PUBLIC / "site.css"),
}


async def app(scope: dict[str, Any], _receive: Any, send: Any) -> None:
    if scope.get("type") != "http":
        return

    entry = ROUTES.get(str(scope.get("path", "/")))
    if entry is None:
        body = b"not found\n"
        status = 404
        content_type = "text/plain; charset=utf-8"
    else:
        content_type, path = entry
        body = path.read_bytes()
        status = 200

    await send({
        "type": "http.response.start",
        "status": status,
        "headers": [(b"content-type", content_type.encode())],
    })
    await send({"type": "http.response.body", "body": body})
