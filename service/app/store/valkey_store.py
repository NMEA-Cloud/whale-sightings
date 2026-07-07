import logging
from uuid import UUID, uuid4

from redis import Redis

from app.models import SightingCreate, SightingRecord
from app.store.base import SightingStore

logger = logging.getLogger(__name__)

SIGHTING_KEY_PREFIX = "sighting:"
BY_TIME_KEY = "sightings:by_time"
GEO_KEY = "sightings:geo"


class ValkeySightingStore(SightingStore):
    def __init__(self, client: Redis):
        self._client = client

    def create(self, payload: SightingCreate) -> SightingRecord:
        record = SightingRecord(
            id=uuid4(),
            sighting=payload.sighting,
            observer=payload.observer,
            images=payload.images,
        )
        record_id = str(record.id)
        lon, lat = record.sighting.location.geometry.coordinates
        score = record.sighting.location.geometry.properties.datetime.timestamp()

        pipe = self._client.pipeline(transaction=True)
        pipe.set(f"{SIGHTING_KEY_PREFIX}{record_id}", record.model_dump_json())
        pipe.zadd(BY_TIME_KEY, {record_id: score})
        # Valkey/Redis GEO commands only accept latitude in [-85.05112878, 85.05112878],
        # narrower than GeoJSON's [-90, 90]. Skip-and-log rather than fail the whole write.
        pipe.geoadd(GEO_KEY, [lon, lat, record_id])
        results = pipe.execute(raise_on_error=False)

        geoadd_result = results[2]
        if isinstance(geoadd_result, Exception):
            logger.warning(
                "GEOADD skipped for sighting %s (lon=%s, lat=%s): %s",
                record_id, lon, lat, geoadd_result,
            )

        return record

    def list_all(self) -> list[SightingRecord]:
        ids = self._client.zrevrange(BY_TIME_KEY, 0, -1)
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
