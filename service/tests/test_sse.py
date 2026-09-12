import asyncio
import json

from app.sse import ConnectionSseBroadcaster


def test_broadcast_sends_event_and_resource_url():
    async def _run():
        broadcaster = ConnectionSseBroadcaster("https://localhost:8000/")
        queue = broadcaster.subscribe()

        broadcaster.broadcast("created", "abc-123")
        payload = await queue.get()

        assert payload == json.dumps({"event": "created", "sighting": "https://localhost:8000/sightings/abc-123"})

    asyncio.run(_run())


def test_unsubscribed_queue_receives_nothing():
    async def _run():
        broadcaster = ConnectionSseBroadcaster("https://localhost:8000/")
        queue = broadcaster.subscribe()
        broadcaster.unsubscribe(queue)

        broadcaster.broadcast("created", "abc-123")
        # Give the event loop a turn to run any (incorrectly) scheduled callback.
        await asyncio.sleep(0)

        assert queue.empty()

    asyncio.run(_run())
