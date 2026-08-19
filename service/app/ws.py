from __future__ import annotations

import asyncio
import json
import logging
import re
from abc import ABC, abstractmethod
from typing import Literal

from fastapi import WebSocket

logger = logging.getLogger(__name__)

Event = Literal["created", "deleted"]


class WsBroadcaster(ABC):
    @abstractmethod
    def broadcast(self, event: Event, sighting_id: str) -> None: ...


class ConnectionWsBroadcaster(WsBroadcaster):
    """Pushes create/delete events directly to every currently-connected WebSocket client —
    no external broker involved, unlike PahoMqttPublisher's broker-mediated push. Deliberately
    independent of both the MQTT publish path and /sightings/poll (see that endpoint's
    docstring) — a third, self-contained example of a live-sync mechanism, this one
    demonstrating direct push with no pub/sub infrastructure needed.
    """

    def __init__(self, base_url: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._connections: set[WebSocket] = set()
        # connect()/disconnect() run directly on the event loop (the /sightings/ws route is
        # async def), but broadcast() is called from create_sighting/delete_sighting, which
        # are sync def and run in Starlette's threadpool — a different thread, not the event
        # loop. run_coroutine_threadsafe is the supported way to schedule async work onto a
        # specific loop from another thread; capturing it here (in the lifespan, itself
        # already running on that loop) is what makes that possible.
        self._loop = asyncio.get_running_loop()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections.add(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        self._connections.discard(websocket)

    def broadcast(self, event: Event, sighting_id: str) -> None:
        payload = json.dumps({"event": event, "sighting": f"{self._base_url}/sightings/{sighting_id}"})
        asyncio.run_coroutine_threadsafe(self._broadcast_async(payload), self._loop)

    async def _broadcast_async(self, payload: str) -> None:
        dead = []
        for connection in list(self._connections):
            try:
                await connection.send_text(payload)
            except Exception:
                dead.append(connection)
        for connection in dead:
            self._connections.discard(connection)


def origin_allowed(origin: str | None, cors_origin_list: list[str], cors_origin_regex: str | None) -> bool:
    """Same allow-list/regex CORSMiddleware applies to HTTP requests — Starlette doesn't
    apply CORSMiddleware to the WebSocket handshake at all, so this route checks Origin
    itself. A missing Origin header is allowed rather than rejected: non-browser clients
    (mosquitto_sub-style CLI tools, scripts) don't send one at all and aren't subject to the
    cross-site-hijacking threat model Origin-checking exists for in the first place — only a
    browser sends Origin, and only a present-but-disallowed Origin indicates a cross-site
    page trying to connect."""
    if origin is None:
        return True
    if origin in cors_origin_list:
        return True
    if cors_origin_regex and re.match(cors_origin_regex, origin):
        return True
    return False
