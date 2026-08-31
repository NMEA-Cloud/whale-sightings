from abc import ABC, abstractmethod
from datetime import datetime
from uuid import UUID

from app.models import (
    ModerationStatus,
    SightingCreate,
    SightingDeletion,
    SightingRecord,
    SightingSource,
    SightingSourceType,
    SightingStats,
)


class SightingStore(ABC):
    @abstractmethod
    def create(
        self,
        payload: SightingCreate,
        source: SightingSource | None = None,
        moderation_status: ModerationStatus | None = None,
    ) -> SightingRecord:
        """Persist a new sighting and return the record with its assigned id. `source` and
        `moderation_status` default to a local, unmoderated sighting when omitted — existing
        store.create(payload) call sites are unaffected."""

    @abstractmethod
    def update(self, record: SightingRecord) -> SightingRecord | None:
        """Replace an existing sighting in place (re-deriving every index exactly as
        create() does from a fresh record) and return it, or None if its id doesn't
        exist."""

    @abstractmethod
    def get_by_source(self, source_type: SightingSourceType, upstream_id: str) -> SightingRecord | None:
        """Return the sighting tagged with this source type and upstream id, or None —
        the dedup/correlation lookup an ingestion process needs across poll cycles,
        without scanning every sighting."""

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
