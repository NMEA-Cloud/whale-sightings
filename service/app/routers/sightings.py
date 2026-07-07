from fastapi import APIRouter, Depends, status

from app.deps import get_store
from app.models import SightingCreate, SightingRecord
from app.store.base import SightingStore

router = APIRouter()


@router.post("/sightings", response_model=SightingRecord, status_code=status.HTTP_201_CREATED)
def create_sighting(payload: SightingCreate, store: SightingStore = Depends(get_store)) -> SightingRecord:
    return store.create(payload)


@router.get("/sightings", response_model=list[SightingRecord])
def list_sightings(store: SightingStore = Depends(get_store)) -> list[SightingRecord]:
    return store.list_all()
