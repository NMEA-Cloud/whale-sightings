from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator


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
    sighting: SightingData
    observer: Observer
    images: list[str] = []


class SightingStats(BaseModel):
    count: int
    oldest: SightingRecord | None
    newest: SightingRecord | None
