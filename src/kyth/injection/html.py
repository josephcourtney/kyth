from __future__ import annotations

import html
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable

CACHE_VALIDATOR_HEADERS = frozenset({
    b"content-digest",
    b"content-md5",
    b"digest",
    b"etag",
    b"last-modified",
})
DEVELOPMENT_CACHE_HEADERS = CACHE_VALIDATOR_HEADERS | {b"cache-control", b"expires"}


def rewrite_cache_headers(headers: Iterable[tuple[bytes, bytes]]) -> list[tuple[bytes, bytes]]:
    """Prevent development responses from being hidden behind browser caches."""
    rewritten = [(name, value) for name, value in headers if name.lower() not in DEVELOPMENT_CACHE_HEADERS]
    rewritten.append((b"cache-control", b"no-store"))
    return rewritten


def browser_script(
    *,
    control_url: str,
    token: str,
    generation: int,
    render_id: str,
    nonce: str,
) -> bytes:
    """Build the external Kyth client tag injected into a development page."""
    src = f"{control_url}/client.js?token={token}"
    attributes = {
        "src": src,
        "nonce": nonce,
        "data-kyth-control": control_url,
        "data-kyth-token": token,
        "data-kyth-generation": str(generation),
        "data-kyth-render-id": render_id,
    }
    rendered = " ".join(f'{name}="{html.escape(value, quote=True)}"' for name, value in attributes.items())
    return f"<script {rendered}></script>".encode()


def inject_script(body: bytes, script: bytes) -> bytes:
    """Insert a development script before body/html close tags when possible."""
    lowered = body.lower()
    for marker in (b"</body>", b"</html>"):
        index = lowered.rfind(marker)
        if index >= 0:
            return body[:index] + script + body[index:]
    return body + script


def rewrite_headers(
    headers: Iterable[tuple[bytes, bytes]],
    *,
    body_length: int,
    control_origin: str,
    nonce: str,
) -> list[tuple[bytes, bytes]]:
    """Update response metadata after development-only HTML body mutation."""
    rewritten: list[tuple[bytes, bytes]] = []
    saw_content_length = False

    for name, value in rewrite_cache_headers(headers):
        lowered = name.lower()
        if lowered == b"content-length":
            rewritten.append((name, str(body_length).encode()))
            saw_content_length = True
            continue
        if lowered in {b"content-security-policy", b"content-security-policy-report-only"}:
            rewritten.append((name, augment_csp(value, control_origin=control_origin, nonce=nonce)))
            continue
        rewritten.append((name, value))

    if not saw_content_length:
        rewritten.append((b"content-length", str(body_length).encode()))
    return rewritten


def augment_csp(value: bytes, *, control_origin: str, nonce: str) -> bytes:
    """Permit only Kyth's injected script and control connection in an existing CSP."""
    text = value.decode("latin-1")
    directives = _parse_csp(text)
    nonce_source = f"'nonce-{nonce}'"

    default_sources = directives.get("default-src")
    script_sources = directives.get("script-src")
    script_element_sources = directives.get("script-src-elem")
    connect_sources = directives.get("connect-src")

    if script_sources is not None:
        directives["script-src"] = _merge_sources(script_sources, nonce_source, control_origin)
    elif script_element_sources is None and default_sources is not None:
        directives["script-src"] = _merge_sources(default_sources, nonce_source, control_origin)

    if script_element_sources is not None:
        directives["script-src-elem"] = _merge_sources(script_element_sources, nonce_source, control_origin)

    if connect_sources is not None:
        directives["connect-src"] = _merge_sources(connect_sources, control_origin)
    elif default_sources is not None:
        directives["connect-src"] = _merge_sources(default_sources, control_origin)

    return _render_csp(directives).encode("latin-1")


def _parse_csp(value: str) -> dict[str, list[str]]:
    directives: dict[str, list[str]] = {}
    for raw_directive in value.split(";"):
        parts = raw_directive.strip().split()
        if parts:
            directives[parts[0].lower()] = parts[1:]
    return directives


def _merge_sources(existing: list[str], *additional: str) -> list[str]:
    sources = [source for source in existing if source != "'none'"]
    for source in additional:
        if source not in sources:
            sources.append(source)
    return sources


def _render_csp(directives: dict[str, list[str]]) -> str:
    return "; ".join(" ".join((name, *sources)) if sources else name for name, sources in directives.items())
