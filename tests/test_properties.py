from __future__ import annotations

import json
import string
from pathlib import Path, PurePosixPath

import pytest
from hypothesis import given
from hypothesis import strategies as st
from hypothesis.stateful import RuleBasedStateMachine, invariant, rule

from kyth.changes import classify_batch
from kyth.control.sse import encode_sse
from kyth.control.views import ViewRegistry
from kyth.invalidation import BrowserActionKind, decide_browser_updates
from kyth.model import BrowserResource, BrowserResourceKind, FileBatch, FileEvent, FileOperation
from kyth.protocol import ControlEvent
from kyth.provenance import direct_document_relative_path, direct_resource_relative_path

pytestmark = [
    pytest.mark.unit,
    pytest.mark.small,
    pytest.mark.property_based,
]

_COMPONENT = st.text(alphabet=string.ascii_lowercase, min_size=1, max_size=8)
_VIEW_ID = st.text(alphabet=string.ascii_lowercase, min_size=1, max_size=8)
_OPERATION = st.sampled_from(tuple(FileOperation))


_EVENTS = st.lists(st.tuples(_COMPONENT, _OPERATION), max_size=20)
_VIEW_MEMBERSHIP = st.dictionaries(_VIEW_ID, st.booleans(), min_size=1, max_size=8)


@given(_EVENTS)
def test_file_batch_canonicalization_is_order_and_duplicate_independent(
    raw_events: list[tuple[str, FileOperation]],
) -> None:
    events = [FileEvent(Path(name), operation) for name, operation in raw_events]
    expected = FileBatch.from_events(events)
    duplicated_reversed = list(reversed(events)) + events

    assert FileBatch.from_events(duplicated_reversed) == expected
    assert expected.events == tuple(
        sorted(set(events), key=lambda event: (event.path.as_posix(), event.operation.value))
    )


@given(_EVENTS, _EVENTS, _EVENTS)
def test_file_batch_merge_is_associative(
    first: list[tuple[str, FileOperation]],
    second: list[tuple[str, FileOperation]],
    third: list[tuple[str, FileOperation]],
) -> None:
    def batch(raw: list[tuple[str, FileOperation]]) -> FileBatch:
        return FileBatch.from_events([FileEvent(Path(name), operation) for name, operation in raw])

    a = batch(first)
    b = batch(second)
    c = batch(third)

    assert a.merged(b).merged(c) == a.merged(b.merged(c))


@given(_EVENTS)
def test_change_classification_partitions_every_path_exactly_once(
    raw_events: list[tuple[str, FileOperation]],
) -> None:
    events = [FileEvent(Path(name), operation) for name, operation in raw_events]
    changes = classify_batch(FileBatch.from_events(events))
    restart = set(changes.restart_paths)
    browser = set(changes.browser_paths)
    other = set(changes.other_paths)

    assert restart.isdisjoint(browser)
    assert restart.isdisjoint(other)
    assert browser.isdisjoint(other)
    assert restart | browser | other == set(changes.batch.paths)


@given(active=st.sets(_VIEW_ID, max_size=8))
def test_unknown_browser_dependency_is_conservative(active: set[str]) -> None:
    unknown = Path("unknown.bin")

    decision = decide_browser_updates(
        (unknown,),
        known_outputs=(),
        output_views={},
        known_render_sources=(),
        render_source_views={},
        complete_render_view_ids=(),
        deferred_source_views={},
        known_resources=(),
        resource_views={},
        complete_resource_view_ids=active,
        active_view_ids=active,
    )

    assert [(action.view_id, action.kind) for action in decision.actions] == [
        (view_id, BrowserActionKind.RELOAD) for view_id in sorted(active)
    ]
    assert decision.current_view_ids == ()


@given(_VIEW_MEMBERSHIP)
def test_known_direct_output_partitions_affected_and_current_views(
    membership: dict[str, bool],
) -> None:
    active = set(membership)
    affected = {view_id for view_id, is_affected in membership.items() if is_affected}
    changed = Path("changed.html")
    other = Path("other.html")
    unaffected = active - affected

    decision = decide_browser_updates(
        (changed,),
        known_outputs={changed, other},
        output_views={
            changed: tuple(sorted(affected)),
            other: tuple(sorted(unaffected)),
        },
        known_render_sources=(),
        render_source_views={},
        complete_render_view_ids=(),
        deferred_source_views={},
        known_resources=(),
        resource_views={},
        complete_resource_view_ids=(),
        active_view_ids=active,
    )

    assert {action.view_id for action in decision.actions} == affected
    assert all(action.kind is BrowserActionKind.RELOAD for action in decision.actions)
    assert set(decision.current_view_ids) == unaffected


@given(_VIEW_MEMBERSHIP)
def test_known_stylesheet_update_accounts_for_every_complete_view(
    membership: dict[str, bool],
) -> None:
    active = set(membership)
    affected = {view_id for view_id, is_affected in membership.items() if is_affected}
    stylesheet = Path("site.css")
    resource_views = {
        view_id: (
            BrowserResource(
                url=f"http://127.0.0.1/{view_id}/site.css",
                kind=BrowserResourceKind.STYLESHEET,
            ),
        )
        for view_id in affected
    }

    decision = decide_browser_updates(
        (stylesheet,),
        known_outputs=(),
        output_views={},
        known_render_sources=(),
        render_source_views={},
        complete_render_view_ids=(),
        deferred_source_views={},
        known_resources={stylesheet},
        resource_views={stylesheet: resource_views},
        complete_resource_view_ids=active,
        active_view_ids=active,
    )

    assert {action.view_id for action in decision.actions} == affected
    assert all(action.kind is BrowserActionKind.CSS_UPDATE for action in decision.actions)
    assert set(decision.current_view_ids) == active - affected


@given(
    initial=st.integers(min_value=0, max_value=1000),
    updates=st.lists(st.integers(min_value=0, max_value=1000), max_size=30),
)
def test_view_generation_never_regresses(initial: int, updates: list[int]) -> None:
    registry = ViewRegistry(inactivity_timeout=10.0, clock=lambda: 1.0)
    registry.register(
        view_id="view",
        url="http://127.0.0.1/",
        generation=initial,
    )

    for generation in updates:
        registry.set_generation(("view",), generation)

    view = registry.get("view")
    assert view is not None
    assert view.generation == max([initial, *updates])


@given(
    generation=st.integers(min_value=0, max_value=2**31 - 1),
    reason=st.text(alphabet=string.ascii_letters + string.digits + "-_", max_size=40),
)
def test_sse_encoding_round_trips_event_payload(generation: int, reason: str) -> None:
    encoded = encode_sse(ControlEvent.reload(generation, reason=reason)).decode()
    lines = encoded.splitlines()

    assert lines[0] == f"id: {generation}"
    assert lines[1] == "event: reload"
    payload = json.loads(lines[2].removeprefix("data: "))
    assert payload == {
        "generation": generation,
        "data": {"reason": reason},
    }


@given(segments=st.lists(_COMPONENT, min_size=1, max_size=6))
def test_direct_document_url_mapping_preserves_normalized_segments(segments: list[str]) -> None:
    relative = "/".join(segments)
    url = f"http://127.0.0.1/{relative}.html?preview=1#section"

    assert direct_document_relative_path(url) == PurePosixPath(f"{relative}.html")


@given(segments=st.lists(_COMPONENT, max_size=5))
def test_direct_resource_url_mapping_rejects_encoded_parent_traversal(segments: list[str]) -> None:
    prefix = "/".join(segments)
    path = f"{prefix}/" if prefix else ""
    traversal = "%2e%2e"
    url = f"http://127.0.0.1/{path}{traversal}/site.css"

    assert direct_resource_relative_path(url) is None


class ViewRegistryStateMachine(RuleBasedStateMachine):
    """Reference-model arbitrary browser registration/generation interleavings."""

    def __init__(self) -> None:
        super().__init__()
        self.registry = ViewRegistry(inactivity_timeout=10.0, clock=lambda: 1.0)
        self.expected: dict[str, tuple[int, str]] = {}

    @rule(
        view_id=_VIEW_ID,
        generation=st.integers(min_value=0, max_value=20),
        url_component=_COMPONENT,
    )
    def register(self, view_id: str, generation: int, url_component: str) -> None:
        url = f"http://127.0.0.1/{url_component}"
        current = self.expected.get(view_id)
        self.registry.register(
            view_id=view_id,
            url=url,
            generation=generation,
        )
        if current is None or generation >= current[0]:
            self.expected[view_id] = (generation, url)

    @rule(
        view_id=_VIEW_ID,
        generation=st.integers(min_value=0, max_value=20),
    )
    def mark_current(self, view_id: str, generation: int) -> None:
        self.registry.set_generation((view_id,), generation)
        current = self.expected.get(view_id)
        if current is not None and generation >= current[0]:
            self.expected[view_id] = (generation, current[1])

    @rule(view_id=_VIEW_ID)
    def ensure(self, view_id: str) -> None:
        self.registry.ensure(view_id)
        self.expected.setdefault(view_id, (0, ""))

    @rule(view_id=_VIEW_ID)
    def touch(self, view_id: str) -> None:
        self.registry.touch(view_id)

    @invariant()
    def implementation_matches_reference_model(self) -> None:
        actual = {
            view.view_id: (view.generation, view.url)
            for view in self.registry.snapshot()
        }
        assert actual == self.expected


TestViewRegistryStateMachine = ViewRegistryStateMachine.TestCase
