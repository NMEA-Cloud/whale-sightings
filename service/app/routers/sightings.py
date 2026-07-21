from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.deps import get_mqtt_publisher, get_store
from app.models import SightingCreate, SightingRecord, SightingStats
from app.mqtt import MqttPublisher
from app.store.base import SightingStore

router = APIRouter()


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
    location_params = (lat, lon, radius_nm)
    has_location_filter = any(p is not None for p in location_params)
    if has_location_filter and not all(p is not None for p in location_params):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="lat, lon, and radius_nm must all be provided together",
        )

    if has_location_filter:
        records = store.list_within_radius(lon, lat, radius_nm)
    elif since_hours is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=since_hours)
        records = store.list_since(cutoff)
    else:
        records = store.list_all()

    if has_location_filter and since_hours is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=since_hours)
        records = [
            r for r in records if r.sighting.location.geometry.properties.datetime >= cutoff
        ]

    return records


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


# No auth yet (see roadmap: OAuth2/OIDC is future work) — once it lands, this route
# should be restricted to privileged/admin users rather than left open to any client.
@router.delete("/sightings/{sighting_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_sighting(
    sighting_id: UUID,
    store: SightingStore = Depends(get_store),
    mqtt: MqttPublisher = Depends(get_mqtt_publisher),
) -> None:
    if not store.delete(sighting_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sighting not found")
    mqtt.publish("deleted", str(sighting_id))
