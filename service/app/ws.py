from __future__ import annotations

import asyncio
import json
import logging
import re
from abc import ABC, abstractmethod
from typing import Literal

from fastapi import WebSocket

logger = logging.getLogger(__name__)

Event = Literal["created", "updated", "deleted"]


class WsBroadcaster(ABC):
    @abstractmethod
    def broadcast(self, event: Event, sighting_id: str) -> None: ...


class ConnectionWsBroadcaster(WsBroadcaster):
    """Pushes create/delete events directly to every currently-connected WebSocket client —
    no external broker involved, unlike PahoMqttPublisher's broker-mediated push. Deliberately
    independent of both the MQTT publish path and /sightings/poll (see that endpoint's
    docstring) — a third, self-contained example of a live-sync mechanism, this one
    demonstrating direct push with no pub/sub infrastructure needed.

    Each event's `sighting` link is built from that connection's own address, not the
    canonical PUBLIC_API_BASE_URL — it's a link a consumer is meant to follow, so it follows
    the same rule as `_links` (see discovery.py): reachable by the caller that received it.
    A same-host peer on the Docker-internal `service` hostname can't resolve the canonical
    one. The sighting's identity (its `@id`) stays canonical in the resource itself.
    """

    def __init__(self) -> None:
        # connection -> the HTTP(S) base it connected through, e.g. "https://service:8000"
        self._connections: dict[WebSocket, str] = {}
        # connect()/disconnect() run directly on the event loop (the /sightings/ws route is
        # async def), but broadcast() is called from create_sighting/delete_sighting, which
        # are sync def and run in Starlette's threadpool — a different thread, not the event
        # loop. run_coroutine_threadsafe is the supported way to schedule async work onto a
        # specific loop from another thread; capturing it here (in the lifespan, itself
        # already running on that loop) is what makes that possible.
        self._loop = asyncio.get_running_loop()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections[websocket] = http_base_url(str(websocket.base_url))

    def disconnect(self, websocket: WebSocket) -> None:
        self._connections.pop(websocket, None)

    def broadcast(self, event: Event, sighting_id: str) -> None:
        asyncio.run_coroutine_threadsafe(self._broadcast_async(event, sighting_id), self._loop)

    async def _broadcast_async(self, event: Event, sighting_id: str) -> None:
        dead = []
        for connection, base in list(self._connections.items()):
            payload = json.dumps({"event": event, "sighting": f"{base}/sightings/{sighting_id}"})
            try:
                await connection.send_text(payload)
            except Exception:
                dead.append(connection)
        for connection in dead:
            self._connections.pop(connection, None)


def http_base_url(ws_base_url: str) -> str:
    """wss://host/ -> https://host (or ws -> http): the address a WebSocket client connected
    through, as the HTTP base its sighting links need."""
    base = ws_base_url.rstrip("/")
    if base.startswith("wss://"):
        return "https://" + base[len("wss://") :]
    if base.startswith("ws://"):
        return "http://" + base[len("ws://") :]
    return base


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
