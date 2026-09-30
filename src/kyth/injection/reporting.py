from __future__ import annotations

import asyncio
import http.client
import json
import logging
from http import HTTPStatus
from typing import TYPE_CHECKING
from urllib.parse import urlencode, urlsplit

if TYPE_CHECKING:
    from kyth.model import RenderRecord, SourceVersion

logger = logging.getLogger(__name__)

REPORT_TIMEOUT_SECONDS = 1.0
MAX_REPORT_BODY_BYTES = 64 * 1024


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
    body = _render_body(record)
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


def _render_body(record: RenderRecord, *, max_bytes: int = MAX_REPORT_BODY_BYTES) -> str:
    """Serialize provenance, truncating only precision when the HTTP budget is exceeded."""
    payload = _render_payload(record)
    body = _encode_payload(payload)
    if len(body.encode()) <= max_bytes:
        return body

    dependencies = list(payload["dependencies"])
    data_dependencies = list(payload["data_dependencies"])
    payload["complete"] = False
    payload["dependencies"] = []
    payload["data_dependencies"] = []
    body = _encode_payload(payload)

    # Preserve a balanced prefix of ordinary and data dependencies. A skipped
    # oversized item does not prevent later, smaller entries from fitting.
    for index in range(max(len(dependencies), len(data_dependencies))):
        for key, values in (
            ("dependencies", dependencies),
            ("data_dependencies", data_dependencies),
        ):
            if index >= len(values):
                continue
            selected = payload[key]
            if not isinstance(selected, list):
                msg = f"internal provenance payload field {key!r} is not a list"
                raise TypeError(msg)
            selected.append(values[index])
            candidate = _encode_payload(payload)
            if len(candidate.encode()) <= max_bytes:
                body = candidate
            else:
                selected.pop()

    return body


def _encode_payload(payload: dict[str, object]) -> str:
    return json.dumps(payload, separators=(",", ":"), sort_keys=True)


def _source_payload(source: SourceVersion) -> dict[str, object]:
    return {
        "path": source.path,
        "mtime_ns": source.mtime_ns,
        "size": source.size,
        "ctime_ns": source.ctime_ns,
        "device": source.device,
        "inode": source.inode,
    }


def _render_payload(record: RenderRecord) -> dict[str, object]:
    return {
        "render_id": record.render_id,
        "generation": record.generation,
        "complete": record.complete,
        "adapter": record.adapter,
        "data_dependencies": [
            {
                "identity": dependency.identity,
                **_source_payload(dependency.source),
            }
            for dependency in record.data_dependencies
        ],
        "dependencies": [_source_payload(dependency) for dependency in record.dependencies],
    }
