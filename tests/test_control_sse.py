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


@pytest.mark.unit
@pytest.mark.small
def test_event_broker_disconnects_slow_subscriber_on_overflow() -> None:
    broker = EventBroker(subscriber_queue_size=1)
    subscriber = broker.subscribe("slow")
    first = ControlEvent.reload(1, reason="first")
    second = ControlEvent.reload(2, reason="second")

    broker.publish(first)
    broker.publish(second)

    assert subscriber.get_nowait() is None
    broker.publish(ControlEvent.reload(3, reason="ignored"))
    with pytest.raises(Empty):
        subscriber.get_nowait()


@pytest.mark.unit
@pytest.mark.small
def test_event_broker_close_replaces_pending_events_with_disconnect() -> None:
    broker = EventBroker(subscriber_queue_size=1)
    subscriber = broker.subscribe("view")
    broker.publish(ControlEvent.reload(1, reason="pending"))

    broker.close()

    assert subscriber.get_nowait() is None


@pytest.mark.unit
@pytest.mark.small
def test_event_broker_rejects_nonpositive_queue_size() -> None:
    with pytest.raises(ValueError, match="subscriber queue size must be positive"):
        EventBroker(subscriber_queue_size=0)
