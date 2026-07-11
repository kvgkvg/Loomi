import asyncio

from core_service.events import EventBus


def test_publish_is_available_to_queue_and_subscriber():
    async def exercise():
        bus = EventBus()
        stream = bus.subscribe()
        pending = asyncio.create_task(anext(stream))
        await asyncio.sleep(0)

        event = {"type": "capture_started", "commit_sha": "abc"}
        bus.publish(event)

        assert bus.pop() == event
        assert await pending == event
        await stream.aclose()

    asyncio.run(exercise())
