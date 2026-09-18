from __future__ import annotations

import json
from queue import Queue
from threading import Lock

from kyth.protocol import ControlEvent

SubscriberQueue = Queue[ControlEvent | None]


class EventBroker:
    """Fan out control events to all connected SSE subscribers."""

    def __init__(self) -> None:
        """Create an empty event fan-out broker."""
        self._lock = Lock()
        self._subscribers: set[SubscriberQueue] = set()
        self._closed = False

    def subscribe(self) -> SubscriberQueue:
        subscriber: SubscriberQueue = Queue()
        with self._lock:
            if self._closed:
                subscriber.put(None)
            else:
                self._subscribers.add(subscriber)
        return subscriber

    def unsubscribe(self, subscriber: SubscriberQueue) -> None:
        with self._lock:
            self._subscribers.discard(subscriber)

    def publish(self, event: ControlEvent) -> None:
        with self._lock:
            subscribers = tuple(self._subscribers)
        for subscriber in subscribers:
            subscriber.put(event)

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            subscribers = tuple(self._subscribers)
            self._subscribers.clear()
        for subscriber in subscribers:
            subscriber.put(None)


def encode_sse(event: ControlEvent) -> bytes:
    payload = json.dumps(
        {"generation": event.generation, "data": event.data},
        separators=(",", ":"),
        sort_keys=True,
    )
    return f"id: {event.generation}\nevent: {event.kind.value}\ndata: {payload}\n\n".encode()
