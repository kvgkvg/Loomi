import asyncio

from core_service.events import EventBus


def test_publish_reaches_subscriber_on_its_event_loop():
    async def exercise():
        bus = EventBus()
        stream = bus.subscribe()
        pending = asyncio.create_task(anext(stream))
        await asyncio.sleep(0)

        event = {"type": "capture_started", "commit_sha": "abc"}
        await bus.publish(event)

        assert await pending == event
        await stream.aclose()

    asyncio.run(exercise())
