from __future__ import annotations

import contextlib
from pathlib import Path
from urllib.parse import unquote

from starlette.responses import FileResponse, PlainTextResponse, Response

from kyth.constants import DEVCLIENT_PATH
from kyth.injection import ensure_devclient_script
from kyth.watcher import path_is_within

if False:
    from starlette.requests import Request


def resolve_request_path(root: Path, url_path: str) -> Path | None:
    rel = unquote(url_path.lstrip("/"))
    candidate = (root / rel).resolve()
    if not path_is_within(candidate, root):
        return None
    return candidate


def resolve_file_to_serve(root: Path, url_path: str) -> tuple[Path | None, Response | None]:
    path = resolve_request_path(root, url_path)
    if path is None:
        return None, PlainTextResponse("Forbidden", status_code=403)

    if path.is_dir():
        index_html = path / "index.html"
        if index_html.exists():
            path = index_html
        else:
            return None, PlainTextResponse("Not Found", status_code=404)

    if not path.exists() or not path.is_file():
        return None, PlainTextResponse("Not Found", status_code=404)

    return path, None


def build_html_response(path: Path, *, client_path: str = DEVCLIENT_PATH) -> Response:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return PlainTextResponse("HTML file is not valid UTF-8", status_code=500)
    except OSError as exc:
        return PlainTextResponse(f"Failed to read file: {exc}", status_code=500)

    body = ensure_devclient_script(text, client_path=client_path)
    return Response(
        body,
        media_type="text/html",
        headers={"Cache-Control": "no-store, no-cache, must-revalidate"},
    )


def static_response(root: Path, url_path: str, *, client_path: str = DEVCLIENT_PATH) -> Response:
    path, error_response = resolve_file_to_serve(root, url_path)
    if error_response is not None:
        return error_response
    if path is None:
        return PlainTextResponse("Not Found", status_code=404)

    if path.suffix.lower() in {".html", ".htm"}:
        return build_html_response(path, client_path=client_path)

    return FileResponse(path)


def static_handler(request: Request) -> Response:  # type: ignore[name-defined]
    state = request.app.state.dev
    return static_response(state.root, request.url.path, client_path=state.client_path)


@contextlib.contextmanager
def nullcontext() -> object:
    yield
