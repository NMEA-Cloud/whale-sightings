import asyncio
import json

from app.sse import ConnectionSseBroadcaster


def test_broadcast_sends_event_and_resource_url():
    async def _run():
        broadcaster = ConnectionSseBroadcaster()
        queue = broadcaster.subscribe("https://localhost:8000/")

        broadcaster.broadcast("created", "abc-123")
        payload = await queue.get()

        assert payload == json.dumps({"event": "created", "sighting": "https://localhost:8000/sightings/abc-123"})

    asyncio.run(_run())


def test_each_subscriber_gets_a_link_built_from_its_own_base_url():
    async def _run():
        broadcaster = ConnectionSseBroadcaster()
        internal = broadcaster.subscribe("https://service:8000/")
        external = broadcaster.subscribe("https://api.example.org:8000/")

        broadcaster.broadcast("updated", "abc-123")

        assert json.loads(await internal.get())["sighting"] == "https://service:8000/sightings/abc-123"
        assert json.loads(await external.get())["sighting"] == "https://api.example.org:8000/sightings/abc-123"

    asyncio.run(_run())


def test_unsubscribed_queue_receives_nothing():
    async def _run():
        broadcaster = ConnectionSseBroadcaster()
        queue = broadcaster.subscribe("https://localhost:8000/")
        broadcaster.unsubscribe(queue)

        broadcaster.broadcast("created", "abc-123")
        # Give the event loop a turn to run any (incorrectly) scheduled callback.
        await asyncio.sleep(0)

        assert queue.empty()

    asyncio.run(_run())
