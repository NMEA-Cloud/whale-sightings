"""peer-service: demonstrates HATEOAS discovery and JSON-LD-flavored data from a second,
independent system's point of view. On startup it discovers the whale-sightings service's
own capabilities from its root document instead of hardcoding endpoint paths, then runs two
concurrent loops: one generating sightings for a simulated moving pod along a fixed route,
the other staying subscribed to the service's live-sync WebSocket so it sees every other
create/update/delete happening on the service too — not just its own.

No FastAPI, no host port — this container's logs are the demo surface. Runnable standalone
on a second machine as well as via docker-compose.yml; see the README's "peer-service"
section for how.
"""

from __future__ import annotations

import asyncio
import logging
import ssl
import time
from datetime import datetime, timezone

import httpx
import websockets

import config
from route import WAYPOINTS, interpolate

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("peer-service")

# One additional interpolated position generated between each pair of waypoints, so
# consecutive posted sightings trace a smoothly moving pod rather than jumping waypoint to
# waypoint.
STEPS_PER_WAYPOINT = 4


class PeerTokenClient:
    """Mints and caches a client_credentials token from our own Hydra, scoped to
    peer:write — same shape as the whale-alert-connector's own token caching
    (service/app/ingest/hydra_token_client.py), kept separate here since peer-service is a
    standalone deployable unit sharing no code with service/."""

    def __init__(self, client: httpx.Client) -> None:
        self._client = client
        self._token: str | None = None
        self._expires_at: float = 0.0

    def get_token(self) -> str:
        if self._token is not None and time.monotonic() < self._expires_at:
            return self._token

        response = self._client.post(
            config.HYDRA_TOKEN_URL,
            data={
                "grant_type": "client_credentials",
                "client_id": config.PEER_CLIENT_ID,
                "client_secret": config.PEER_CLIENT_SECRET,
                "scope": "peer:write",
                "audience": config.HYDRA_AUDIENCE,
            },
        )
        response.raise_for_status()
        body = response.json()
        # Refresh 60s before actual expiry so a request never starts against a token that
        # expires mid-flight.
        self._token = body["access_token"]
        self._expires_at = time.monotonic() + body["expires_in"] - 60
        return self._token


def discover(client: httpx.Client) -> dict[str, str]:
    """Fetches the service's root discovery document and returns the two hrefs this
    service actually needs. Never hardcodes /sightings or /sightings/ws — if the service
    renamed either path tomorrow, only its own _links would need to change."""
    response = client.get(config.API_BASE, headers={"Accept": "application/json"})
    response.raise_for_status()
    links = response.json()["_links"]
    return {
        "create": links["sightings:create"]["href"],
        "live_sync": links["sightings:live-sync"]["href"],
    }


def discover_with_retry(client: httpx.Client) -> dict[str, str]:
    """The service container may still be starting up when this one does (docker-compose's
    depends_on only waits for the container to start, not for uvicorn to actually be
    accepting connections) — retry indefinitely with a fixed delay rather than crash on a
    slow-starting dependency."""
    while True:
        try:
            return discover(client)
        except httpx.HTTPError as exc:
            logger.warning("Discovery failed (%s) — retrying in 3s", exc)
            time.sleep(3)


def build_sighting_payload(lat: float, lon: float) -> dict:
    when = datetime.now(timezone.utc).isoformat()
    location = {
        "geometry": {
            "type": "Point",
            "coordinates": [lon, lat],
            "properties": {"datetime": when},
        }
    }
    return {
        "sighting": {
            "location": location,
            "status": "alive",
            "comments": "Reported by peer-service (simulated).",
            "type": "orca",
            "species": "Orcinus orca",
            "name": None,
            "method": "other",
        },
        "observer": {
            "id": "https://example.org/peer-service/observer",
            "location": location,
        },
        "images": [],
    }


async def generate_sightings(client: httpx.AsyncClient, token_client: PeerTokenClient, create_url: str) -> None:
    """Walks the waypoint route indefinitely, POSTing one interpolated sighting every
    GENERATE_INTERVAL_SECONDS. No source field in the payload at all — the service derives
    source.type="peer" and source.peer_id purely from the bearer token's own claims (see
    create_sighting in routers/sightings.py), the same anti-spoofing pattern the
    whale-alert-connector uses."""
    t = 0.0
    step = 1.0 / (len(WAYPOINTS) * STEPS_PER_WAYPOINT)
    while True:
        lat, lon = interpolate(WAYPOINTS, t)
        t += step
        payload = build_sighting_payload(lat, lon)
        try:
            response = await client.post(
                create_url, json=payload, headers={"Authorization": f"Bearer {token_client.get_token()}"}
            )
            response.raise_for_status()
            body = response.json()
            logger.info("Posted sighting %s at (%.4f, %.4f)", body["id"], lat, lon)
        except httpx.HTTPError:
            logger.exception("Failed to post sighting")
        await asyncio.sleep(config.GENERATE_INTERVAL_SECONDS)


async def subscribe_live_sync(ws_url: str) -> None:
    """Stays connected to the service's live-sync WebSocket for as long as this process
    runs, logging every created/updated/deleted event it receives — including this same
    process's own posted sightings, since the broadcaster doesn't exclude the connection
    that caused the event. Reconnects on drop with a fixed delay (see
    WS_RECONNECT_DELAY_SECONDS), mirroring client-ws/app.js's hand-rolled reconnect exactly,
    since neither the native WebSocket API nor the `websockets` library reconnects on its
    own."""
    ssl_context = ssl.create_default_context(cafile=config.CA_BUNDLE_PATH) if config.CA_BUNDLE_PATH else None
    while True:
        try:
            async with websockets.connect(ws_url, ssl=ssl_context) as ws:
                logger.info("Connected to live-sync at %s", ws_url)
                async for message in ws:
                    logger.info("Live-sync event: %s", message)
        except Exception:
            logger.exception("Live-sync connection dropped")
        await asyncio.sleep(config.WS_RECONNECT_DELAY_SECONDS)


async def main() -> None:
    verify = config.CA_BUNDLE_PATH or True
    with httpx.Client(verify=verify) as sync_client:
        links = discover_with_retry(sync_client)
        logger.info("Discovered links: %s", links)

        token_client = PeerTokenClient(sync_client)

        async with httpx.AsyncClient(verify=verify) as async_client:
            await asyncio.gather(
                generate_sightings(async_client, token_client, links["create"]),
                subscribe_live_sync(links["live_sync"]),
            )


if __name__ == "__main__":
    asyncio.run(main())
