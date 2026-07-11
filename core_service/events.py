"""In-process lifecycle event bus for the single-core MVP runtime."""

import asyncio
from collections import deque


class EventBus:
    def __init__(self):
        # ponytail: retain only the latest demo events; add durable replay if reconnect history matters.
        self._events = deque(maxlen=100)
        self._subscribers = set()

    def publish(self, event: dict) -> None:
        self._events.append(event)
        for subscriber in tuple(self._subscribers):
            subscriber.put_nowait(event)

    def pop(self):
        return self._events.popleft() if self._events else None

    async def subscribe(self):
        queue = asyncio.Queue()
        self._subscribers.add(queue)
        try:
            while True:
                yield await queue.get()
        finally:
            self._subscribers.discard(queue)


events = EventBus()
