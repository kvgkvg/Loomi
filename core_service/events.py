"""In-process lifecycle event bus for the single-core MVP runtime."""

import asyncio
from collections import deque


class EventBus:
    def __init__(self):
        # ponytail: retain only the latest demo events; add durable replay if reconnect history matters.
        self._events = deque(maxlen=100)
        self._subscribers = set()

    async def publish(self, event: dict) -> None:
        self._events.append(event)
        for subscriber in tuple(self._subscribers):
            subscriber.put_nowait(event)

    def clear(self) -> None:
        self._events.clear()

    async def subscribe(self):
        queue = asyncio.Queue()
        backlog = tuple(self._events)
        self._subscribers.add(queue)
        try:
            for event in backlog:
                yield event
            while True:
                yield await queue.get()
        finally:
            self._subscribers.discard(queue)


events = EventBus()
