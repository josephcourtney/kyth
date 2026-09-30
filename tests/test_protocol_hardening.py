from __future__ import annotations

import json
from typing import TYPE_CHECKING, cast

import pytest

from kyth.control.app import MAX_REQUEST_BODY
from kyth.injection import reporting
from kyth.injection.html import SESSION_STORAGE_KEYS, SESSION_TOKEN_KEY, augment_csp, browser_script
from kyth.model import FileBatch, FileEvent, FileOperation, RenderRecord, SourceVersion
from kyth.process.manager import ChildProcess
from kyth.watcher import BatchDeduplicator

if TYPE_CHECKING:
    from multiprocessing.connection import Connection
    from multiprocessing.process import BaseProcess
    from pathlib import Path


class _AliveProcess:
    pid = 1234
    exitcode = None

    def is_alive(self) -> bool:
        return True


class _ReadinessConnection:
    def poll(self, _timeout: float) -> bool:
        return False


class _BrokenControlConnection:
    def send(self, _value: object) -> None:
        msg = "child pipe closed"
        raise BrokenPipeError(msg)


@pytest.mark.unit
@pytest.mark.small
def test_browser_bootstrap_resets_persistent_state_before_loading_client() -> None:
    source = browser_script(
        control_url="http://127.0.0.1:9001",
        token="session-token",  # ruff: ignore[hardcoded-password-func-arg]
        generation=1,
        render_id="render-id",
        nonce="nonce",
    ).decode()

    assert SESSION_TOKEN_KEY in source
    assert 'const t="session-token"' in source
    for key in SESSION_STORAGE_KEYS:
        assert key in source
    assert "sessionStorage.removeItem" in source
    assert source.index(SESSION_TOKEN_KEY) < source.index("data-kyth-control")


@pytest.mark.unit
@pytest.mark.small
def test_generation_update_normalizes_broken_control_pipe() -> None:
    manager = ChildProcess()
    manager._process = cast("BaseProcess", _AliveProcess())
    manager._readiness = cast("Connection", _ReadinessConnection())
    manager._control = cast("Connection", _BrokenControlConnection())

    with pytest.raises(RuntimeError, match="before generation update was sent") as exc_info:
        manager.set_generation(8, timeout=1.0)

    assert isinstance(exc_info.value.__cause__, BrokenPipeError)


@pytest.mark.unit
@pytest.mark.small
def test_csp_duplicate_directives_keep_first_occurrence_in_each_policy() -> None:
    policy = b"script-src 'none'; script-src *; connect-src 'self', default-src 'none'; default-src *"

    augmented = augment_csp(
        policy,
        control_origin="http://127.0.0.1:9001",
        nonce="abc",
    ).decode()
    first, second = augmented.split(", ", maxsplit=1)

    assert "script-src 'nonce-abc' http://127.0.0.1:9001" in first
    assert "connect-src 'self' http://127.0.0.1:9001" in first
    assert "*" not in first
    assert "default-src 'none'" in second
    assert "script-src 'nonce-abc' http://127.0.0.1:9001" in second
    assert "connect-src http://127.0.0.1:9001" in second
    assert "*" not in second


@pytest.mark.integration
@pytest.mark.medium
def test_batch_deduplicator_uses_final_filesystem_state_for_conflicting_events(tmp_path: Path) -> None:
    output = tmp_path / "output.html"
    output.write_text("ready", encoding="utf-8")
    output.unlink()
    noisy = FileBatch.from_events([
        FileEvent(output, FileOperation.MODIFIED),
        FileEvent(output, FileOperation.DELETED),
    ])

    filtered = BatchDeduplicator().filter(noisy)

    assert filtered.events == (FileEvent(output, FileOperation.DELETED),)


@pytest.mark.unit
@pytest.mark.small
def test_provenance_sender_budget_matches_control_plane_limit() -> None:
    assert reporting.MAX_REPORT_BODY_BYTES == MAX_REQUEST_BODY


@pytest.mark.unit
@pytest.mark.small
def test_oversized_provenance_is_bounded_and_marked_incomplete() -> None:
    dependencies = tuple(
        SourceVersion(
            f"/project/templates/{index:03d}-{'x' * 180}.html",
            index,
            123,
            index + 1,
            2,
            index + 3,
        )
        for index in range(512)
    )
    record = RenderRecord(
        render_id="render-1",
        generation=7,
        dependencies=dependencies,
        complete=True,
        adapter="jinja",
    )

    body = reporting._render_body(record)
    payload = json.loads(body)

    assert len(body.encode()) <= reporting.MAX_REPORT_BODY_BYTES
    assert payload["complete"] is False
    assert 0 < len(payload["dependencies"]) < len(dependencies)
