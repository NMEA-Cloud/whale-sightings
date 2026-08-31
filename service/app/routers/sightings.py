import asyncio
import time
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, WebSocket, WebSocketDisconnect, status

from app.auth import require_admin_or_ingest, require_ingest, token_scopes, try_require_ingest
from app.config import get_settings
from app.deps import get_mqtt_publisher, get_store, get_ws_broadcaster, get_ws_broadcaster_ws
from app.models import (
    ModerationUpdate,
    PollResult,
    SightingCreate,
    SightingRecord,
    SightingSource,
    SightingSourceType,
    SightingStats,
)
from app.mqtt import MqttPublisher
from app.store.base import SightingStore
from app.ws import WsBroadcaster, origin_allowed

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
    ws: WsBroadcaster = Depends(get_ws_broadcaster),
    ingest_claims: dict | None = Depends(try_require_ingest),
) -> SightingRecord:
    # An ingest-authenticated caller (the whale-alert-connector) tags its own source —
    # never trusted from the request body, only from the token, so a caller can't spoof a
    # different source_upstream_id claiming to be an existing sighting's owner. Any other
    # caller (the public report form, no token at all) keeps today's plain local behavior.
    source = None
    if ingest_claims is not None:
        source = SightingSource(type=SightingSourceType.WHALE_ALERT, upstream_id=payload.source_upstream_id)
    moderation_status = payload.source_moderation_status if ingest_claims is not None else None

    record = store.create(payload, source=source, moderation_status=moderation_status)
    mqtt.publish("created", str(record.id))
    ws.broadcast("created", str(record.id))
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
@router.get("/sightings/poll", response_model=PollResult)
async def poll_sightings(
    since: datetime = Query(..., description="Only return sightings created/deleted strictly after this instant"),
    lat: float | None = Query(default=None, ge=-90, le=90, description="Latitude of the search center"),
    lon: float | None = Query(default=None, ge=-180, le=180, description="Longitude of the search center"),
    radius_nm: float | None = Query(default=None, gt=0, description="Search radius in nautical miles"),
    timeout_seconds: float = Query(
        default=25.0, gt=0, le=55, description="Max seconds to hold the request open waiting for a match"
    ),
    store: SightingStore = Depends(get_store),
) -> PollResult | Response:
    """Long-poll endpoint: holds the connection open, re-checking the store every
    _POLL_INTERVAL_SECONDS, until there's a sighting *created or deleted* after `since`
    (200, with a PollResult naming the match(es)) or timeout_seconds elapses (204, empty).
    The client is expected to advance `since` past the newest created_at/deleted_at seen and
    immediately re-request on either outcome — that repeated-request loop from the client is
    what makes this "long polling".

    Filters on created_at (server-assigned, see models.py), not the sighting's own reported
    datetime — those are different questions. A sighting reported as "spotted 20 minutes
    ago" (the report form allows backdating) is still brand new data the instant it's
    created, and a client polling since page-load needs to see it immediately, not never
    (its own datetime being in the past would make it look like it isn't "new"). since_hours
    on GET /sightings above answers the other, legitimately different question — "what did
    people see recently" — which does mean the sighting's own datetime.

    `deleted` carries only tombstones (id + deleted_at, see SightingDeletion) — the deleted
    record's own data is gone, so there's nothing else to report. A location filter only
    narrows `created` (list_within_radius has real coordinates to check); `deleted` is
    reported unfiltered in that case since a removed record's location is no longer known.
    That can trigger a client's refetch for a deletion outside its filtered view, which is
    harmless — the client only ever treats this response as a "something changed" signal
    and reloads its own filtered view (see client-long-poll/app.js), never renders `deleted`
    directly.

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
            records = store.list_created_since(since)

        # list_created_since()/list_within_radius()/list_deleted_since() are inclusive
        # (>=); filter strictly here so a client that advances its cursor to a matched
        # entry's exact created_at/deleted_at doesn't keep re-matching it forever.
        matched_created = [r for r in records if r.created_at > since]
        matched_deleted = [d for d in store.list_deleted_since(since) if d.deleted_at > since]
        if matched_created or matched_deleted:
            return PollResult(created=matched_created, deleted=matched_deleted)

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return Response(status_code=status.HTTP_204_NO_CONTENT)
        await asyncio.sleep(min(_POLL_INTERVAL_SECONDS, remaining))


@router.websocket("/sightings/ws")
async def sightings_ws(
    websocket: WebSocket,
    ws: WsBroadcaster = Depends(get_ws_broadcaster_ws),
) -> None:
    """Live-sync endpoint: direct push over a plain WebSocket, no broker in between — the
    counterpart to the MQTT-mediated push in mqtt.py and the pull-based /sightings/poll
    above. A connected client just receives a `{"event": ..., "sighting": ...}` message
    (see ConnectionWsBroadcaster) whenever create_sighting/delete_sighting call broadcast();
    it never needs to send anything itself, so this only reads to detect disconnection.

    Starlette doesn't apply CORSMiddleware to the WebSocket handshake — origin_allowed()
    does the equivalent check by hand before accepting the connection.
    """
    settings = get_settings()
    if not origin_allowed(websocket.headers.get("origin"), settings.cors_origin_list, settings.cors_origin_regex):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await ws.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        ws.disconnect(websocket)


# Declared before the "/sightings/{sighting_id}" path param route so a literal
# "/sightings/stats" is never mistakenly captured as a sighting id.
@router.get("/sightings/stats", response_model=SightingStats)
def get_sighting_stats(store: SightingStore = Depends(get_store)) -> SightingStats:
    return store.stats()


@router.get("/sightings/by-source/{source_type}/{upstream_id}", response_model=SightingRecord)
def get_sighting_by_source(
    source_type: SightingSourceType,
    upstream_id: str,
    store: SightingStore = Depends(get_store),
) -> SightingRecord:
    """Unauthenticated read (same posture as GET /sightings/{id}) — the dedup/correlation
    lookup an ingestion process (e.g. whale-alert-connector) calls over plain HTTP, like
    everything else it does, to decide whether a given upstream record is already known."""
    record = store.get_by_source(source_type, upstream_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sighting not found")
    return record


@router.get("/sightings/{sighting_id}", response_model=SightingRecord)
def get_sighting(
    sighting_id: UUID,
    store: SightingStore = Depends(get_store),
) -> SightingRecord:
    record = store.get(sighting_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sighting not found")
    return record


@router.patch("/sightings/{sighting_id}/moderation", response_model=SightingRecord)
def update_moderation_status(
    sighting_id: UUID,
    payload: ModerationUpdate,
    store: SightingStore = Depends(get_store),
    mqtt: MqttPublisher = Depends(get_mqtt_publisher),
    ws: WsBroadcaster = Depends(get_ws_broadcaster),
    _claims: dict = Depends(require_ingest),
) -> SightingRecord:
    """Ingest-only. Narrow by design (see ModerationUpdate) — a sighting's moderation
    status only makes sense for a Whale-Alert-sourced record, hence the 409 below rather
    than silently accepting it for a local/peer sighting."""
    record = store.get(sighting_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sighting not found")
    if record.source.type != SightingSourceType.WHALE_ALERT:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Moderation status only applies to Whale Alert-sourced sightings",
        )

    updated_record = record.model_copy(update={"moderation_status": payload.moderation_status})
    store.update(updated_record)
    mqtt.publish("updated", str(sighting_id))
    ws.broadcast("updated", str(sighting_id))
    return updated_record


# Admin (browser) or ingest (machine, e.g. whale-alert-connector) — see app/auth.py. Every
# other route in this file stays open to any client.
@router.delete("/sightings/{sighting_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_sighting(
    sighting_id: UUID,
    store: SightingStore = Depends(get_store),
    mqtt: MqttPublisher = Depends(get_mqtt_publisher),
    ws: WsBroadcaster = Depends(get_ws_broadcaster),
    claims: dict = Depends(require_admin_or_ingest),
) -> None:
    record = store.get(sighting_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sighting not found")

    # Each source's owner is the only one who may delete its own records — checked directly
    # against the token's own scopes (not "which dependency succeeded" — require_admin_or_
    # ingest tries require_admin first), so this applies to any token carrying the ingest
    # scope, even one that also happens to carry admin role.
    #  - An ingest-scoped caller may only delete records it itself owns — a compromised or
    #    buggy ingest credential can't touch local or peer sightings.
    #  - Conversely, a human admin may not delete Whale Alert-sourced records — Whale Alert
    #    is the single source of truth for its own data; this service only relays it, and
    #    an admin-initiated delete would just get silently resurrected by the connector's
    #    next poll cycle anyway (it has no way to distinguish "deleted here" from "not yet
    #    ingested"), so refusing it up front is more honest than a delete that doesn't stick.
    is_ingest = "sightings:ingest" in token_scopes(claims)
    is_whale_alert = record.source.type == SightingSourceType.WHALE_ALERT
    if is_ingest and not is_whale_alert:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Ingest credentials may only delete Whale Alert-sourced sightings",
        )
    if is_whale_alert and not is_ingest:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Whale Alert-sourced sightings can only be deleted by the ingest connector",
        )

    store.delete(sighting_id)
    mqtt.publish("deleted", str(sighting_id))
    ws.broadcast("deleted", str(sighting_id))
