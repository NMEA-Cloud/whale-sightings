import asyncio
import time
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from app.auth import require_admin
from app.deps import get_mqtt_publisher, get_store
from app.models import SightingCreate, SightingRecord, SightingStats
from app.mqtt import MqttPublisher
from app.store.base import SightingStore

router = APIRouter()

# How often GET /sightings/poll re-checks the store while waiting for a match. An internal
# implementation detail of that one endpoint, not a per-deployment setting, so it's a plain
# constant here rather than a Settings field.
_POLL_INTERVAL_SECONDS = 0.5


def _location_filter_or_none(
    lat: float | None, lon: float | None, radius_nm: float | None
) -> tuple[float, float, float] | None:
    """Validate the lat/lon/radius_nm all-or-nothing trio shared by GET /sightings and
    GET /sightings/poll. Returns (lat, lon, radius_nm) if all three are given, None if
    none are, and raises 400 if only some are."""
    params = (lat, lon, radius_nm)
    if not any(p is not None for p in params):
        return None
    if not all(p is not None for p in params):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="lat, lon, and radius_nm must all be provided together",
        )
    return lat, lon, radius_nm


@router.post("/sightings", response_model=SightingRecord, status_code=status.HTTP_201_CREATED)
def create_sighting(
    payload: SightingCreate,
    store: SightingStore = Depends(get_store),
    mqtt: MqttPublisher = Depends(get_mqtt_publisher),
) -> SightingRecord:
    record = store.create(payload)
    mqtt.publish("created", str(record.id))
    return record


@router.get("/sightings", response_model=list[SightingRecord])
def list_sightings(
    since_hours: float | None = Query(default=None, gt=0, description="Only return sightings from the last N hours"),
    lat: float | None = Query(default=None, ge=-90, le=90, description="Latitude of the search center"),
    lon: float | None = Query(default=None, ge=-180, le=180, description="Longitude of the search center"),
    radius_nm: float | None = Query(default=None, gt=0, description="Search radius in nautical miles"),
    store: SightingStore = Depends(get_store),
) -> list[SightingRecord]:
    location_filter = _location_filter_or_none(lat, lon, radius_nm)

    if location_filter is not None:
        filter_lat, filter_lon, filter_radius_nm = location_filter
        records = store.list_within_radius(filter_lon, filter_lat, filter_radius_nm)
    elif since_hours is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=since_hours)
        records = store.list_since(cutoff)
    else:
        records = store.list_all()

    if location_filter is not None and since_hours is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=since_hours)
        records = [
            r for r in records if r.sighting.location.geometry.properties.datetime >= cutoff
        ]

    return records


# Declared before the "/sightings/{sighting_id}" path param route (same reasoning as
# "/sightings/stats" below) so these literal paths are never mistakenly parsed as a
# sighting id.
@router.get("/sightings/poll", response_model=list[SightingRecord])
async def poll_sightings(
    since: datetime = Query(..., description="Only return sightings strictly after this instant"),
    lat: float | None = Query(default=None, ge=-90, le=90, description="Latitude of the search center"),
    lon: float | None = Query(default=None, ge=-180, le=180, description="Longitude of the search center"),
    radius_nm: float | None = Query(default=None, gt=0, description="Search radius in nautical miles"),
    timeout_seconds: float = Query(
        default=25.0, gt=0, le=55, description="Max seconds to hold the request open waiting for a match"
    ),
    store: SightingStore = Depends(get_store),
) -> list[SightingRecord] | Response:
    """Long-poll endpoint: holds the connection open, re-checking the store every
    _POLL_INTERVAL_SECONDS, until there's a sighting newer than `since` (200, with the
    match(es)) or timeout_seconds elapses (204, empty). The client is expected to advance
    `since` to the newest match's datetime and immediately re-request on either outcome —
    that repeated-request loop from the client is what makes this "long polling".

    Deliberately independent of the MQTT publish path (see mqtt.py) — this re-checks the
    store directly rather than subscribing to the same events service publishes, so it's a
    self-contained example of the pull-based pattern, not layered on the push-based one.

    async def + asyncio.sleep rather than sync def + time.sleep: every other route in this
    file is sync def, which Starlette runs in its shared threadpool — a sync long-poll route
    would pin one of those threads for up to timeout_seconds, and a handful of concurrent
    long-poll clients would exhaust the pool and start blocking every other route. async def
    holds nothing while waiting. Note the store client itself (redis-py) is still sync, so
    each loop iteration's store call briefly blocks the event loop — negligible for local
    Valkey, and simpler than introducing a second, async-flavored store client for one route.
    """
    location_filter = _location_filter_or_none(lat, lon, radius_nm)

    deadline = time.monotonic() + timeout_seconds
    while True:
        if location_filter is not None:
            filter_lat, filter_lon, filter_radius_nm = location_filter
            records = store.list_within_radius(filter_lon, filter_lat, filter_radius_nm)
        else:
            records = store.list_since(since)

        # list_since()/list_within_radius() are inclusive (>=); filter strictly here so a
        # client that advances its cursor to a matched record's exact datetime doesn't keep
        # re-matching that same record forever.
        matched = [r for r in records if r.sighting.location.geometry.properties.datetime > since]
        if matched:
            return matched

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return Response(status_code=status.HTTP_204_NO_CONTENT)
        await asyncio.sleep(min(_POLL_INTERVAL_SECONDS, remaining))


# Declared before the "/sightings/{sighting_id}" path param route so a literal
# "/sightings/stats" is never mistakenly captured as a sighting id.
@router.get("/sightings/stats", response_model=SightingStats)
def get_sighting_stats(store: SightingStore = Depends(get_store)) -> SightingStats:
    return store.stats()


@router.get("/sightings/{sighting_id}", response_model=SightingRecord)
def get_sighting(
    sighting_id: UUID,
    store: SightingStore = Depends(get_store),
) -> SightingRecord:
    record = store.get(sighting_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sighting not found")
    return record


# Admin-only — see app/auth.py. Every other route in this file stays open to any client.
@router.delete("/sightings/{sighting_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_sighting(
    sighting_id: UUID,
    store: SightingStore = Depends(get_store),
    mqtt: MqttPublisher = Depends(get_mqtt_publisher),
    _claims: dict = Depends(require_admin),
) -> None:
    if not store.delete(sighting_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sighting not found")
    mqtt.publish("deleted", str(sighting_id))
