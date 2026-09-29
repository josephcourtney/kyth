from __future__ import annotations

from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

ROOT = Path(__file__).parent
TEMPLATES = ROOT / "templates"
STATIC = ROOT / "static"
ENV = Environment(
    loader=FileSystemLoader(TEMPLATES),
    autoescape=select_autoescape(("html", "xml")),
)


async def _send(send: Any, status: int, body: bytes, content_type: str) -> None:
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
    if path == "/static/site.css":
        await _send(send, 200, (STATIC / "site.css").read_bytes(), "text/css; charset=utf-8")
        return

    template_name = {"/": "index.html", "/about": "about.html"}.get(path)
    if template_name is None:
        await _send(send, 404, b"not found\n", "text/plain; charset=utf-8")
        return

    template = ENV.get_template(template_name)
    body = template.render(path=path).encode()
    await _send(send, 200, body, "text/html; charset=utf-8")
