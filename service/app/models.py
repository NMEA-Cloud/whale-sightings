from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator, model_validator


class SightingStatus(str, Enum):
    ALIVE = "alive"
    DEAD = "dead"
    DISTRESSED = "distressed"
    UNKNOWN = "unknown"


class SightingMethod(str, Enum):
    MANUAL_REPORT = "manual-report"
    OTHER = "other"


class GeoJSONPointProperties(BaseModel):
    datetime: datetime


class GeoJSONPoint(BaseModel):
    type: str = "Point"
    # GeoJSON order: (longitude, latitude)
    coordinates: tuple[float, float]
    properties: GeoJSONPointProperties

    @field_validator("coordinates")
    @classmethod
    def validate_coordinates(cls, value: tuple[float, float]) -> tuple[float, float]:
        lon, lat = value
        if not (-180.0 <= lon <= 180.0):
            raise ValueError(f"longitude {lon} out of range [-180, 180]")
        if not (-90.0 <= lat <= 90.0):
            raise ValueError(f"latitude {lat} out of range [-90, 90]")
        return value


class Location(BaseModel):
    geometry: GeoJSONPoint


class SightingData(BaseModel):
    location: Location
    status: SightingStatus
    comments: str | None = None
    type: str
    species: str
    name: str | None = None
    method: SightingMethod


class Observer(BaseModel):
    id: str
    location: Location


class SightingCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sighting: SightingData
    observer: Observer
    images: list[str] = []


class SightingRecord(BaseModel):
    id: UUID
    # Server-assigned, set once at insertion — distinct from sighting.location.geometry
    # .properties.datetime, which is the user-editable, backdatable "when was this
    # observed" field (the report form explicitly supports reporting after the fact).
    # GET /sightings/poll's cursor is based on this field for exactly that reason: a
    # backdated sighting is still new data the instant it's created.
    created_at: datetime
    sighting: SightingData
    observer: Observer
    images: list[str] = []

    @model_validator(mode="before")
    @classmethod
    def _backfill_created_at_for_legacy_records(cls, data: Any) -> Any:
        """Records written to the store before this field existed have no created_at in
        their stored JSON. Rather than fail every read of a pre-existing deployment's data
        (turning GET /sightings into a hard 500 the moment one legacy record is hydrated),
        approximate it from the sighting's own reported datetime — not the true original
        insertion time (that's unrecoverable), but enough to keep old data readable."""
        if isinstance(data, dict) and data.get("created_at") is None:
            try:
                data = {
                    **data,
                    "created_at": data["sighting"]["location"]["geometry"]["properties"]["datetime"],
                }
            except (KeyError, TypeError):
                pass
        return data


class SightingStats(BaseModel):
    count: int
    oldest: SightingRecord | None
    newest: SightingRecord | None


class SightingDeletion(BaseModel):
    """A tombstone: just enough to let a long-poll client know a sighting is gone and
    advance its cursor past the deletion, without needing the deleted record's own data."""

    id: UUID
    deleted_at: datetime


class PollResult(BaseModel):
    """GET /sightings/poll's response body: the created and deleted sightings since the
    poll's `since` cursor. A client advances its cursor past the latest created_at/
    deleted_at seen in either list, then treats a non-empty response as a "something
    changed" signal to re-run its normal filtered load — see client-long-poll/app.js."""

    created: list[SightingRecord] = []
    deleted: list[SightingDeletion] = []
