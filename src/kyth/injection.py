from __future__ import annotations

from collections.abc import Iterable

from kyth.constants import DEVCLIENT_PATH


def ensure_devclient_script(html_text: str, *, client_path: str = DEVCLIENT_PATH) -> str:
    tag = f'<script src="{client_path}"></script>'
    lower = html_text.lower()

    if client_path.lower() in lower:
        return html_text

    head_close = lower.find("</head>")
    if head_close != -1:
        return html_text[:head_close] + tag + "\n" + html_text[head_close:]

    head_open = lower.find("<head>")
    if head_open != -1:
        insert_at = head_open + len("<head>")
        return html_text[:insert_at] + "\n" + tag + html_text[insert_at:]

    html_open = lower.find("<html")
    if html_open != -1:
        gt = lower.find(">", html_open)
        if gt != -1:
            head = f"\n<head>\n{tag}\n</head>\n"
            return html_text[: gt + 1] + head + html_text[gt + 1 :]

    if lower.startswith(("<!doctype", "<html")):
        return f"<head>\n{tag}\n</head>\n{html_text}"

    return f"<head>\n{tag}\n</head>\n{html_text}"


def get_header(headers: Iterable[tuple[bytes, bytes]], name: bytes) -> bytes | None:
    name_lower = name.lower()
    for key, value in headers:
        if key.lower() == name_lower:
            return value
    return None


def set_header(headers: list[tuple[bytes, bytes]], name: bytes, value: bytes) -> list[tuple[bytes, bytes]]:
    name_lower = name.lower()
    replaced = False
    new_headers: list[tuple[bytes, bytes]] = []

    for key, existing_value in headers:
        if key.lower() == name_lower:
            if not replaced:
                new_headers.append((key, value))
                replaced = True
        else:
            new_headers.append((key, existing_value))

    if not replaced:
        new_headers.append((name, value))

    return new_headers


def remove_header(headers: list[tuple[bytes, bytes]], name: bytes) -> list[tuple[bytes, bytes]]:
    name_lower = name.lower()
    return [(key, value) for key, value in headers if key.lower() != name_lower]


def content_type_is_html(headers: Iterable[tuple[bytes, bytes]]) -> bool:
    content_type = get_header(headers, b"content-type")
    if content_type is None:
        return False
    return b"text/html" in content_type.lower()


def has_content_encoding(headers: Iterable[tuple[bytes, bytes]]) -> bool:
    content_encoding = get_header(headers, b"content-encoding")
    return content_encoding is not None and content_encoding.strip() != b""


def should_inject_html_response(
    *,
    status: int,
    headers: Iterable[tuple[bytes, bytes]],
) -> bool:
    return status == 200 and content_type_is_html(headers) and not has_content_encoding(headers)


def inject_html_bytes(body: bytes, *, client_path: str = DEVCLIENT_PATH) -> bytes:
    text = body.decode("utf-8")
    return ensure_devclient_script(text, client_path=client_path).encode("utf-8")
