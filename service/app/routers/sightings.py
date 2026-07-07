from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.deps import get_store
from app.models import SightingCreate, SightingRecord
from app.store.base import SightingStore

router = APIRouter()


@router.post("/sightings", response_model=SightingRecord, status_code=status.HTTP_201_CREATED)
def create_sighting(payload: SightingCreate, store: SightingStore = Depends(get_store)) -> SightingRecord:
    return store.create(payload)


@router.get("/sightings", response_model=list[SightingRecord])
def list_sightings(
    since_hours: float | None = Query(default=None, gt=0, description="Only return sightings from the last N hours"),
    store: SightingStore = Depends(get_store),
) -> list[SightingRecord]:
    if since_hours is None:
        return store.list_all()
    cutoff = datetime.now(timezone.utc) - timedelta(hours=since_hours)
    return store.list_since(cutoff)


# No auth yet (see roadmap: OAuth2/OIDC is future work) — once it lands, this route
# should be restricted to privileged/admin users rather than left open to any client.
@router.delete("/sightings/{sighting_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_sighting(sighting_id: UUID, store: SightingStore = Depends(get_store)) -> None:
    if not store.delete(sighting_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sighting not found")
