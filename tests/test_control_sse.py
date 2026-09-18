from queue import Empty

import pytest

from kyth.control.sse import EventBroker
from kyth.protocol import ControlEvent


@pytest.mark.unit
@pytest.mark.small
def test_event_broker_targets_selected_view_subscribers() -> None:
    broker = EventBroker()
    first = broker.subscribe("first")
    second = broker.subscribe("second")
    event = ControlEvent.reload(3, reason="known-direct-output")

    broker.publish(event, view_ids=("second",))

    with pytest.raises(Empty):
        first.get_nowait()
    assert second.get_nowait() == event
