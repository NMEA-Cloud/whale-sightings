from abc import ABC, abstractmethod
from datetime import datetime
from uuid import UUID

from app.models import SightingCreate, SightingDeletion, SightingRecord, SightingStats


class SightingStore(ABC):
    @abstractmethod
    def create(self, payload: SightingCreate) -> SightingRecord:
        """Persist a new sighting and return the record with its assigned id."""

    @abstractmethod
    def list_all(self) -> list[SightingRecord]:
        """Return all sightings, newest first."""

    @abstractmethod
    def stats(self) -> SightingStats:
        """Return the total count plus the oldest and newest sightings by datetime."""

    @abstractmethod
    def list_since(self, cutoff: datetime) -> list[SightingRecord]:
        """Return sightings whose datetime is at or after cutoff, newest first."""

    @abstractmethod
    def list_created_since(self, cutoff: datetime) -> list[SightingRecord]:
        """Return sightings created at or after cutoff (server-assigned creation time,
        not the sighting's own reported datetime), newest first."""

    @abstractmethod
    def list_within_radius(self, lon: float, lat: float, radius_nm: float) -> list[SightingRecord]:
        """Return sightings within radius_nm nautical miles of (lon, lat), newest first."""

    @abstractmethod
    def list_deleted_since(self, cutoff: datetime) -> list[SightingDeletion]:
        """Return tombstones for sightings deleted at or after cutoff, newest first. The
        deleted record's own data isn't available (it's gone) — just enough (id,
        deleted_at) for a poller to notice and advance its cursor."""

    @abstractmethod
    def get(self, sighting_id: UUID) -> SightingRecord | None:
        """Return a single sighting by id, or None if it doesn't exist."""

    @abstractmethod
    def delete(self, sighting_id: UUID) -> bool:
        """Delete a sighting by id. Return True if it existed and was deleted."""
