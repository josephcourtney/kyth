from __future__ import annotations

import json
from queue import Empty, Full, Queue
from threading import Lock
from typing import TYPE_CHECKING

from kyth.protocol import ControlEvent

if TYPE_CHECKING:
    from collections.abc import Collection

DEFAULT_SUBSCRIBER_QUEUE_SIZE = 32

SubscriberQueue = Queue[ControlEvent | None]


class EventBroker:
    """Fan out control events to all or selected connected browser views."""

    def __init__(self, *, subscriber_queue_size: int = DEFAULT_SUBSCRIBER_QUEUE_SIZE) -> None:
        """Create an empty event fan-out broker."""
        if subscriber_queue_size <= 0:
            msg = "subscriber queue size must be positive"
            raise ValueError(msg)
        self._subscriber_queue_size = subscriber_queue_size
        self._lock = Lock()
        self._subscribers: dict[SubscriberQueue, str] = {}
        self._closed = False

    def subscribe(self, view_id: str) -> SubscriberQueue:
        subscriber: SubscriberQueue = Queue(maxsize=self._subscriber_queue_size)
        with self._lock:
            if self._closed:
                subscriber.put_nowait(None)
            else:
                self._subscribers[subscriber] = view_id
        return subscriber

    def unsubscribe(self, subscriber: SubscriberQueue) -> None:
        with self._lock:
            self._subscribers.pop(subscriber, None)

    def publish(self, event: ControlEvent, *, view_ids: Collection[str] | None = None) -> None:
        targets = None if view_ids is None else set(view_ids)
        with self._lock:
            subscribers = tuple(self._subscribers.items())
        for subscriber, view_id in subscribers:
            if targets is None or view_id in targets:
                self._publish_to_subscriber(subscriber, event)

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            subscribers = tuple(self._subscribers)
            self._subscribers.clear()
        for subscriber in subscribers:
            _terminate_subscriber(subscriber)

    def _publish_to_subscriber(self, subscriber: SubscriberQueue, event: ControlEvent) -> None:
        try:
            subscriber.put_nowait(event)
        except Full:
            with self._lock:
                self._subscribers.pop(subscriber, None)
            _terminate_subscriber(subscriber)


def _terminate_subscriber(subscriber: SubscriberQueue) -> None:
    while True:
        try:
            subscriber.get_nowait()
        except Empty:
            break
    subscriber.put_nowait(None)


def encode_sse(event: ControlEvent) -> bytes:
    payload = json.dumps(
        {"generation": event.generation, "data": event.data},
        separators=(",", ":"),
        sort_keys=True,
    )
    return f"id: {event.generation}\nevent: {event.kind.value}\ndata: {payload}\n\n".encode()
