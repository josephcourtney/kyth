from __future__ import annotations

import gzip
from pathlib import Path
from typing import Any

from kyth.injection import client_script

ROOT = Path(__file__).parent
STATIC = ROOT / "static"


def _document(title: str) -> str:
    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>{title}</title>
  <link rel="stylesheet" href="/static/site.css">
</head>
<body>
  <nav><a href="/stream">Stream</a> <a href="/gzip">Gzip</a></nav>
  <main><h1>{title}</h1><p>This document opted into Kyth explicitly.</p></main>
  {client_script()}
</body>
</html>
"""


async def _start(send: Any, headers: list[tuple[bytes, bytes]]) -> None:
    await send({"type": "http.response.start", "status": 200, "headers": headers})


async def app(scope: dict[str, Any], _receive: Any, send: Any) -> None:
    if scope.get("type") != "http":
        return

    path = str(scope.get("path", "/"))
    if path == "/static/site.css":
        body = (STATIC / "site.css").read_bytes()
        await _start(send, [(b"content-type", b"text/css; charset=utf-8")])
        await send({"type": "http.response.body", "body": body})
        return

    if path == "/stream":
        document = _document("Streaming HTML").encode()
        split = len(document) // 2
        await _start(send, [(b"content-type", b"text/html; charset=utf-8")])
        await send({"type": "http.response.body", "body": document[:split], "more_body": True})
        await send({"type": "http.response.body", "body": document[split:]})
        return

    if path == "/gzip":
        body = gzip.compress(_document("Gzip HTML").encode())
        await _start(
            send,
            [
                (b"content-type", b"text/html; charset=utf-8"),
                (b"content-encoding", b"gzip"),
                (b"content-length", str(len(body)).encode()),
            ],
        )
        await send({"type": "http.response.body", "body": body})
        return

    body = b'<a href="/stream">stream</a> <a href="/gzip">gzip</a>'
    await _start(send, [(b"content-type", b"text/html; charset=utf-8")])
    await send({"type": "http.response.body", "body": body})
