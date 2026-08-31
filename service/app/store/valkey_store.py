import logging
from datetime import datetime, timezone
from uuid import UUID, uuid4

from redis import Redis

from app.models import (
    ModerationStatus,
    SightingCreate,
    SightingDeletion,
    SightingRecord,
    SightingSource,
    SightingSourceType,
    SightingStats,
)
from app.store.base import SightingStore

logger = logging.getLogger(__name__)

SIGHTING_KEY_PREFIX = "sighting:"
BY_TIME_KEY = "sightings:by_time"
BY_CREATED_KEY = "sightings:by_created_at"
GEO_KEY = "sightings:geo"
# Tombstones, kept indefinitely (mirrors BY_CREATED_KEY never being trimmed either) — a
# permanent record that a given id was deleted, since the sighting itself no longer exists
# to answer that question. See list_deleted_since().
BY_DELETED_KEY = "sightings:by_deleted_at"
# Hash: "{source_type}:{upstream_id}" -> record id. Only populated for sightings that carry
# an upstream_id (peer/whale_alert sources) — the dedup/correlation lookup an ingestion
# process needs across poll cycles. See get_by_source().
BY_SOURCE_KEY = "sightings:by_source_id"
# Hash: source type -> count. Kept in sync by create()/delete() via HINCRBY rather than
# computed on demand, since stats() is called far more often than sightings are written.
BY_SOURCE_TYPE_COUNT_KEY = "sightings:count_by_source_type"
NM_TO_KM = 1.852  # international nautical mile


def _source_hash_field(source_type: SightingSourceType, upstream_id: str) -> str:
    return f"{source_type.value}:{upstream_id}"


class ValkeySightingStore(SightingStore):
    def __init__(self, client: Redis):
        self._client = client

    def create(
        self,
        payload: SightingCreate,
        source: SightingSource | None = None,
        moderation_status: ModerationStatus | None = None,
    ) -> SightingRecord:
        record = SightingRecord(
            id=uuid4(),
            created_at=datetime.now(timezone.utc),
            sighting=payload.sighting,
            observer=payload.observer,
            images=payload.images,
            source=source or SightingSource(),
            moderation_status=moderation_status,
        )
        record_id = str(record.id)
        lon, lat = record.sighting.location.geometry.coordinates
        score = record.sighting.location.geometry.properties.datetime.timestamp()

        pipe = self._client.pipeline(transaction=True)
        pipe.set(f"{SIGHTING_KEY_PREFIX}{record_id}", record.model_dump_json())
        pipe.zadd(BY_TIME_KEY, {record_id: score})
        pipe.zadd(BY_CREATED_KEY, {record_id: record.created_at.timestamp()})
        # Valkey/Redis GEO commands only accept latitude in [-85.05112878, 85.05112878],
        # narrower than GeoJSON's [-90, 90]. Skip-and-log rather than fail the whole write.
        pipe.geoadd(GEO_KEY, [lon, lat, record_id])
        # Everything below is appended after the four ops geoadd_result indexes into below,
        # so that index stays valid regardless of whether BY_SOURCE_KEY is populated here.
        if record.source.upstream_id is not None:
            pipe.hset(BY_SOURCE_KEY, _source_hash_field(record.source.type, record.source.upstream_id), record_id)
        pipe.hincrby(BY_SOURCE_TYPE_COUNT_KEY, record.source.type.value, 1)
        results = pipe.execute(raise_on_error=False)

        geoadd_result = results[3]
        if isinstance(geoadd_result, Exception):
            logger.warning(
                "GEOADD skipped for sighting %s (lon=%s, lat=%s): %s",
                record_id, lon, lat, geoadd_result,
            )

        return record

    def update(self, record: SightingRecord) -> SightingRecord | None:
        record_id = str(record.id)
        if not self._client.exists(f"{SIGHTING_KEY_PREFIX}{record_id}"):
            return None

        lon, lat = record.sighting.location.geometry.coordinates
        score = record.sighting.location.geometry.properties.datetime.timestamp()

        # Mirrors create()'s pipeline (re-deriving every index from the given record) minus
        # the source-type count, which doesn't change for an in-place update.
        pipe = self._client.pipeline(transaction=True)
        pipe.set(f"{SIGHTING_KEY_PREFIX}{record_id}", record.model_dump_json())
        pipe.zadd(BY_TIME_KEY, {record_id: score})
        pipe.zadd(BY_CREATED_KEY, {record_id: record.created_at.timestamp()})
        pipe.geoadd(GEO_KEY, [lon, lat, record_id])
        if record.source.upstream_id is not None:
            pipe.hset(BY_SOURCE_KEY, _source_hash_field(record.source.type, record.source.upstream_id), record_id)
        results = pipe.execute(raise_on_error=False)

        geoadd_result = results[3]
        if isinstance(geoadd_result, Exception):
            logger.warning(
                "GEOADD skipped for sighting %s (lon=%s, lat=%s): %s",
                record_id, lon, lat, geoadd_result,
            )

        return record

    def get_by_source(self, source_type: SightingSourceType, upstream_id: str) -> SightingRecord | None:
        record_id = self._client.hget(BY_SOURCE_KEY, _source_hash_field(source_type, upstream_id))
        if record_id is None:
            return None
        return self.get(UUID(record_id))

    def list_all(self) -> list[SightingRecord]:
        ids = self._client.zrevrange(BY_TIME_KEY, 0, -1)
        return self._hydrate(ids)

    def list_since(self, cutoff: datetime) -> list[SightingRecord]:
        ids = self._client.zrevrangebyscore(BY_TIME_KEY, "+inf", cutoff.timestamp())
        return self._hydrate(ids)

    def list_created_since(self, cutoff: datetime) -> list[SightingRecord]:
        ids = self._client.zrevrangebyscore(BY_CREATED_KEY, "+inf", cutoff.timestamp())
        return self._hydrate(ids)

    def list_within_radius(self, lon: float, lat: float, radius_nm: float) -> list[SightingRecord]:
        ids = self._client.geosearch(
            GEO_KEY, longitude=lon, latitude=lat, radius=radius_nm * NM_TO_KM, unit="km"
        )
        records = self._hydrate(ids)
        records.sort(key=lambda r: r.sighting.location.geometry.properties.datetime, reverse=True)
        return records

    def stats(self) -> SightingStats:
        count = self._client.zcard(BY_TIME_KEY)
        oldest = self._hydrate(self._client.zrange(BY_TIME_KEY, 0, 0))
        newest = self._hydrate(self._client.zrevrange(BY_TIME_KEY, 0, 0))
        raw_counts = self._client.hgetall(BY_SOURCE_TYPE_COUNT_KEY)
        by_source = {
            source_type: int(raw_counts.get(source_type.value, 0)) for source_type in SightingSourceType
        }
        return SightingStats(
            count=count,
            oldest=oldest[0] if oldest else None,
            newest=newest[0] if newest else None,
            by_source=by_source,
        )

    def _hydrate(self, ids: list[str]) -> list[SightingRecord]:
        if not ids:
            return []
        keys = [f"{SIGHTING_KEY_PREFIX}{sighting_id}" for sighting_id in ids]
        raw_records = self._client.mget(keys)
        return [
            SightingRecord.model_validate_json(raw)
            for raw in raw_records
            if raw is not None
        ]

    def get(self, sighting_id: UUID) -> SightingRecord | None:
        raw = self._client.get(f"{SIGHTING_KEY_PREFIX}{sighting_id}")
        if raw is None:
            return None
        return SightingRecord.model_validate_json(raw)

    def delete(self, sighting_id: UUID) -> bool:
        record_id = str(sighting_id)
        # Fetched up front (not just inferred from the pipeline's delete count below) both
        # so a DELETE on an id that never existed doesn't leave a phantom tombstone behind
        # for list_deleted_since() to report, and so the record's own source is available
        # for the BY_SOURCE_KEY/count cleanup below without a second round-trip.
        record = self.get(sighting_id)
        if record is None:
            return False

        deleted_at = datetime.now(timezone.utc)
        pipe = self._client.pipeline(transaction=True)
        pipe.delete(f"{SIGHTING_KEY_PREFIX}{record_id}")
        pipe.zrem(BY_TIME_KEY, record_id)
        pipe.zrem(BY_CREATED_KEY, record_id)
        # GEOADD stores members in a sorted set under the hood, so ZREM removes them too.
        pipe.zrem(GEO_KEY, record_id)
        pipe.zadd(BY_DELETED_KEY, {record_id: deleted_at.timestamp()})
        if record.source.upstream_id is not None:
            pipe.hdel(BY_SOURCE_KEY, _source_hash_field(record.source.type, record.source.upstream_id))
        pipe.hincrby(BY_SOURCE_TYPE_COUNT_KEY, record.source.type.value, -1)
        results = pipe.execute()

        return bool(results[0])

    def list_deleted_since(self, cutoff: datetime) -> list[SightingDeletion]:
        entries = self._client.zrevrangebyscore(BY_DELETED_KEY, "+inf", cutoff.timestamp(), withscores=True)
        return [
            SightingDeletion(id=UUID(record_id), deleted_at=datetime.fromtimestamp(score, tz=timezone.utc))
            for record_id, score in entries
        ]
