from abc import ABC, abstractmethod
from uuid import UUID

from app.models import SightingCreate, SightingRecord


class SightingStore(ABC):
    @abstractmethod
    def create(self, payload: SightingCreate) -> SightingRecord:
        """Persist a new sighting and return the record with its assigned id."""

    @abstractmethod
    def list_all(self) -> list[SightingRecord]:
        """Return all sightings, newest first."""

    @abstractmethod
    def get(self, sighting_id: UUID) -> SightingRecord | None:
        """Return a single sighting by id, or None if it doesn't exist."""
