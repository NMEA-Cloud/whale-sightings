from abc import ABC, abstractmethod
from datetime import datetime
from uuid import UUID

from app.models import SightingCreate, SightingRecord, SightingStats


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
    def get(self, sighting_id: UUID) -> SightingRecord | None:
        """Return a single sighting by id, or None if it doesn't exist."""

    @abstractmethod
    def delete(self, sighting_id: UUID) -> bool:
        """Delete a sighting by id. Return True if it existed and was deleted."""
