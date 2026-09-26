from __future__ import annotations

import asyncio
import json
import logging
from abc import ABC, abstractmethod
from typing import AsyncIterator, Literal

logger = logging.getLogger(__name__)

Event = Literal["created", "updated", "deleted"]


class SseBroadcaster(ABC):
    @abstractmethod
    def broadcast(self, event: Event, sighting_id: str) -> None: ...


class ConnectionSseBroadcaster(SseBroadcaster):
    """Pushes create/update/delete events to every currently-connected Server-Sent Events
    client — a fourth live-sync mechanism alongside PahoMqttPublisher's broker-mediated push,
    ConnectionWsBroadcaster's direct WebSocket push, and /sightings/poll's client-driven
    polling. Unlike a WebSocket, an SSE connection has no persistent bidirectional handle to
    push through directly — each connected client is instead represented by an asyncio.Queue
    that its own streaming response reads from.

    Each event's `sighting` link is built from that subscriber's own request base URL —
    same reasoning as ConnectionWsBroadcaster: it's a link to follow, so it must be
    reachable by the caller that received it.
    """

    def __init__(self) -> None:
        # queue -> the base URL its subscriber's request came in on
        self._queues: dict[asyncio.Queue[str], str] = {}
        # broadcast() is called from create_sighting/update_moderation_status/delete_sighting,
        # which are sync def and run in Starlette's threadpool — a different thread, not the
        # event loop. Capturing the loop here (constructed in lifespan, itself already running
        # on it) is what lets broadcast() safely hand work back to it — same reasoning as
        # ConnectionWsBroadcaster.
        self._loop = asyncio.get_running_loop()

    def subscribe(self, base_url: str) -> asyncio.Queue[str]:
        queue: asyncio.Queue[str] = asyncio.Queue()
        self._queues[queue] = base_url.rstrip("/")
        return queue

    def unsubscribe(self, queue: asyncio.Queue[str]) -> None:
        self._queues.pop(queue, None)

    def broadcast(self, event: Event, sighting_id: str) -> None:
        # call_soon_threadsafe (not run_coroutine_threadsafe) is enough here: queue.put_nowait
        # is synchronous and non-blocking, so there's no awaitable work to schedule per
        # connection the way ConnectionWsBroadcaster's send_text() needs.
        for queue, base in list(self._queues.items()):
            payload = json.dumps({"event": event, "sighting": f"{base}/sightings/{sighting_id}"})
            self._loop.call_soon_threadsafe(queue.put_nowait, payload)

    async def event_stream(self, base_url: str) -> AsyncIterator[str]:
        queue = self.subscribe(base_url)
        try:
            # A comment line (ignored by EventSource's onmessage, per the SSE spec) that gives
            # both a real client and a test a deterministic "the stream is open and this
            # connection is registered" signal to wait for before triggering/expecting events —
            # closes the narrow gap between "headers sent" and "subscribe() has run" during
            # which a same-instant broadcast could otherwise be missed.
            yield ": connected\n\n"
            while True:
                payload = await queue.get()
                yield f"data: {payload}\n\n"
        finally:
            # Runs on cancellation too (StreamingResponse cancels this generator's task when
            # the client disconnects — see list_sightings' SSE branch for why a plain
            # try/finally, with no except, is the correct cleanup here).
            self.unsubscribe(queue)
