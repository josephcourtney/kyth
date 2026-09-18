from __future__ import annotations

import asyncio
import http.client
import json
import logging
from http import HTTPStatus
from urllib.parse import urlencode, urlsplit

from kyth.model import RenderRecord

logger = logging.getLogger(__name__)

REPORT_TIMEOUT_SECONDS = 1.0


async def report_render_record(
    control_url: str,
    token: str,
    record: RenderRecord,
) -> None:
    """Report one render record without making provenance a request correctness dependency."""
    try:
        await asyncio.to_thread(_post_render_record, control_url, token, record)
    except (OSError, http.client.HTTPException):
        logger.debug("render provenance report failed", exc_info=True)


def _post_render_record(control_url: str, token: str, record: RenderRecord) -> None:
    parsed = urlsplit(control_url)
    if parsed.scheme != "http" or parsed.hostname is None or parsed.port is None:
        msg = f"unsupported control URL for render reporting: {control_url!r}"
        raise ValueError(msg)

    path = f"/renders?{urlencode({'token': token})}"
    body = json.dumps(_render_payload(record), separators=(",", ":"), sort_keys=True)
    connection = http.client.HTTPConnection(
        parsed.hostname,
        parsed.port,
        timeout=REPORT_TIMEOUT_SECONDS,
    )
    try:
        connection.request(
            "POST",
            path,
            body=body,
            headers={"Content-Type": "application/json"},
        )
        response = connection.getresponse()
        response.read()
        if response.status != HTTPStatus.OK:
            logger.debug("render provenance report rejected with HTTP %d", response.status)
    finally:
        connection.close()


def _render_payload(record: RenderRecord) -> dict[str, object]:
    return {
        "render_id": record.render_id,
        "generation": record.generation,
        "complete": record.complete,
        "adapter": record.adapter,
        "dependencies": [
            {
                "path": dependency.path,
                "mtime_ns": dependency.mtime_ns,
                "size": dependency.size,
            }
            for dependency in record.dependencies
        ],
    }
