from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from kyth.changes import classify_batch
from kyth.model import ChildState, ChildStatus, DevelopmentState, FileBatch, FileEvent, FileOperation
from kyth.supervisor import Supervisor, SupervisorConfig


class _PendingBatches:
    def __init__(self, batches: list[FileBatch | None]) -> None:
        self._batches = batches

    def start(self) -> None:
        pass

    def next_batch(self, timeout: float | None = None) -> FileBatch | None:
        return None

    def drain_pending(self) -> FileBatch | None:
        if not self._batches:
            return None
        return self._batches.pop(0)

    def close(self) -> None:
        pass


def _batch(path: str) -> FileBatch:
    return FileBatch.from_events([FileEvent(Path(path), FileOperation.MODIFIED)])


@pytest.mark.component
@pytest.mark.small
def test_restart_cycle_coalesces_pending_restart_changes() -> None:
    supervisor = Supervisor(SupervisorConfig("example:app"))
    source = _PendingBatches([
        _batch("/project/second.py").merged(_batch("/project/third.py")),
        None,
    ])

    with patch.object(supervisor, "restart_child", return_value=True) as restart:
        supervisor._handle_change_cycle(_batch("/project/first.py"), source)

    assert restart.call_count == 2


@pytest.mark.component
@pytest.mark.small
def test_browser_only_pending_changes_do_not_trigger_followup_restart() -> None:
    supervisor = Supervisor(SupervisorConfig("example:app"))
    source = _PendingBatches([_batch("/project/site.css")])

    with patch.object(supervisor, "restart_child", return_value=True) as restart:
        supervisor._handle_change_cycle(_batch("/project/app.py"), source)

    assert restart.call_count == 1


@pytest.mark.integration
@pytest.mark.medium
def test_manifest_source_change_is_deferred_until_generated_output_changes(tmp_path: Path) -> None:
    source_path = tmp_path / "content.md"
    output_path = tmp_path / "public" / "index.html"
    manifest_path = tmp_path / "kyth-manifest.json"
    output_path.parent.mkdir()
    source_path.write_text("source", encoding="utf-8")
    output_path.write_text("<html>old</html>", encoding="utf-8")
    manifest_path.write_text(
        json.dumps({
            "version": 1,
            "outputs": [
                {
                    "output": "public/index.html",
                    "sources": ["content.md"],
                }
            ],
        }),
        encoding="utf-8",
    )

    supervisor = Supervisor(
        SupervisorConfig(
            "example:app",
            watch_roots=(tmp_path,),
            manifest_paths=(manifest_path,),
        )
    )
    supervisor._generated.load_all()

    source_batch = FileBatch.from_events([
        FileEvent(source_path, FileOperation.MODIFIED),
    ])
    supervisor._generated.mark_sources_changed(source_batch.paths)
    source_changes = classify_batch(source_batch)

    assert supervisor._relevant_browser_paths(source_changes) == ()
    assert supervisor._generated.stale_outputs == frozenset({output_path.resolve()})

    deletion_batch = FileBatch.from_events([
        FileEvent(output_path, FileOperation.DELETED),
    ])
    deletion_changes = classify_batch(deletion_batch)
    assert supervisor._relevant_browser_paths(deletion_changes) == ()
    assert supervisor._generated.stale_outputs == frozenset({output_path.resolve()})

    output_batch = FileBatch.from_events([
        FileEvent(output_path, FileOperation.MODIFIED),
    ])
    output_changes = classify_batch(output_batch)
    relevant = supervisor._relevant_browser_paths(output_changes)
    supervisor._generated.mark_outputs_updated(relevant)

    assert relevant == (output_path,)
    assert supervisor._generated.stale_outputs == frozenset()


@pytest.mark.integration
@pytest.mark.medium
def test_restart_defers_view_until_stale_generated_output_is_ready(tmp_path: Path) -> None:
    source_path = tmp_path / "generator.py"
    output_path = tmp_path / "public" / "index.html"
    manifest_path = tmp_path / "kyth-manifest.json"
    output_path.parent.mkdir()
    source_path.write_text("SOURCE = 1", encoding="utf-8")
    output_path.write_text("<html>old</html>", encoding="utf-8")
    manifest_path.write_text(
        json.dumps({
            "version": 1,
            "outputs": [
                {
                    "output": "public/index.html",
                    "url": "/",
                    "sources": ["generator.py"],
                }
            ],
        }),
        encoding="utf-8",
    )

    supervisor = Supervisor(
        SupervisorConfig(
            "example:app",
            watch_roots=(tmp_path,),
            manifest_paths=(manifest_path,),
        )
    )
    with supervisor:
        supervisor._generated.load_all()
        control = supervisor._require_control()
        control.views.register(view_id="generated", url="http://127.0.0.1:8000/", generation=0)
        control.views.register(view_id="dynamic", url="http://127.0.0.1:8000/dynamic", generation=0)
        supervisor._generated.mark_sources_changed((source_path,))

        def start_ready(*, reload_browsers: bool, commit_control: bool = True) -> bool:
            assert not reload_browsers
            assert not commit_control
            supervisor.state = DevelopmentState(1, ChildState(ChildStatus.READY, pid=123))
            return True

        with (
            patch.object(supervisor, "_start_child", side_effect=start_ready),
            patch.object(control, "publish") as publish,
        ):
            supervisor._restart_for_change_cycle((source_path,))

        assert control.generation == 1
        assert control.views.get("generated").generation == 1
        assert control.views.get("dynamic").generation == 0
        assert publish.call_count == 2
        sync_call, reload_call = publish.call_args_list
        assert sync_call.args[0].kind.value == "sync"
        assert sync_call.kwargs["view_ids"] == ("generated",)
        assert reload_call.args[0].kind.value == "reload"
        assert reload_call.kwargs["view_ids"] == ("dynamic",)
        assert supervisor._generated.stale_outputs == frozenset({output_path.resolve()})


@pytest.mark.integration
@pytest.mark.medium
def test_generated_source_deferral_is_limited_to_dependent_outputs(tmp_path: Path) -> None:
    first_source = tmp_path / "first.py"
    second_source = tmp_path / "second.py"
    first_output = tmp_path / "public" / "first.html"
    second_output = tmp_path / "public" / "second.html"
    first_output.parent.mkdir()
    for path in (first_source, second_source, first_output, second_output):
        path.write_text("x", encoding="utf-8")
    manifest_path = tmp_path / "kyth-manifest.json"
    manifest_path.write_text(
        json.dumps({
            "version": 1,
            "outputs": [
                {"output": "public/first.html", "url": "/first", "sources": ["first.py"]},
                {"output": "public/second.html", "url": "/second", "sources": ["second.py"]},
            ],
        }),
        encoding="utf-8",
    )

    supervisor = Supervisor(SupervisorConfig("example:app", watch_roots=(tmp_path,), manifest_paths=(manifest_path,)))
    supervisor._generated.load_all()
    generated_output_views = {
        first_output.resolve(): ("first-view",),
        second_output.resolve(): ("second-view",),
    }

    deferred = supervisor._generated_source_views(generated_output_views)

    assert deferred[first_source.resolve()] == ("first-view",)
    assert deferred[second_source.resolve()] == ("second-view",)


@pytest.mark.component
@pytest.mark.small
def test_no_action_batch_records_explainable_change_report() -> None:
    supervisor = Supervisor(SupervisorConfig("example:app"))
    source = _PendingBatches([])

    supervisor._handle_change_cycle(_batch("/project/README.md"), source)

    report = supervisor.last_change_report
    assert report is not None
    assert report.changed_paths == (Path("/project/README.md"),)
    assert report.restart_requested is False
    assert report.restart_succeeded is None
    assert report.browser_actions == ()
    assert report.affected_view_ids == ()
    assert report.generation == 0
    assert report.reason == "no-action"
