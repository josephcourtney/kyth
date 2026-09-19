from __future__ import annotations

import importlib
import os
from http import HTTPStatus
from pathlib import Path
from typing import Any

ROOT_ENV = "KYTH_BROWSER_FIXTURE_ROOT"

_jinja = importlib.import_module("jinja2")
_environment_type = vars(_jinja)["Environment"]
_loader_type = vars(_jinja)["FileSystemLoader"]
_environment = _environment_type(
    loader=_loader_type(str(Path(os.environ[ROOT_ENV]) / "templates")),
    autoescape=True,
)


async def app(scope: dict[str, Any], receive: Any, send: Any) -> None:
    if scope["type"] == "lifespan":
        await _lifespan(receive, send)
        return
    if scope["type"] != "http":
        return

    template_name = {
        "/a/": "page-a.html",
        "/b/": "page-b.html",
    }.get(str(scope["path"]))
    if template_name is None:
        await _response(send, HTTPStatus.NOT_FOUND, b"missing")
        return

    template = _environment.get_template(template_name)
    body = template.render().encode()
    await _response(send, HTTPStatus.OK, body)


async def _lifespan(receive: Any, send: Any) -> None:
    while True:
        message = await receive()
        if message["type"] == "lifespan.startup":
            await send({"type": "lifespan.startup.complete"})
        elif message["type"] == "lifespan.shutdown":
            await send({"type": "lifespan.shutdown.complete"})
            return


async def _response(send: Any, status: HTTPStatus, body: bytes) -> None:
    await send({
        "type": "http.response.start",
        "status": status,
        "headers": [
            (b"content-type", b"text/html; charset=utf-8"),
            (b"content-length", str(len(body)).encode()),
        ],
    })
    await send({"type": "http.response.body", "body": body})
