import uuid
from datetime import datetime, timezone

from app.models import (
    GeoJSONPoint,
    GeoJSONPointProperties,
    Location,
    Observer,
    SightingCreate,
    SightingData,
    SightingMethod,
    SightingStatus,
)


def make_payload(lon: float = -122.645, lat: float = 47.726, when: datetime | None = None) -> SightingCreate:
    when = when or datetime.now(timezone.utc)
    location = Location(
        geometry=GeoJSONPoint(coordinates=(lon, lat), properties=GeoJSONPointProperties(datetime=when))
    )
    return SightingCreate(
        sighting=SightingData(
            location=location,
            status=SightingStatus.ALIVE,
            comments="Thar she blows!",
            type="wombat",
            species="Greater Pacific Wombat",
            name="LB-Whale",
            method=SightingMethod.MANUAL_REPORT,
        ),
        observer=Observer(id="https://example.org/users/anonymous-observer", location=location),
        images=[],
    )


def test_create_assigns_id_and_populates_indexes(store, fake_redis_client):
    record = store.create(make_payload())

    assert record.id is not None
    assert fake_redis_client.get(f"sighting:{record.id}") is not None
    assert fake_redis_client.zscore("sightings:by_time", str(record.id)) is not None


def test_list_all_newest_first(store):
    older_record = store.create(make_payload(when=datetime(2026, 1, 1, tzinfo=timezone.utc)))
    newer_record = store.create(make_payload(when=datetime(2026, 6, 1, tzinfo=timezone.utc)))

    records = store.list_all()

    assert [r.id for r in records] == [newer_record.id, older_record.id]


def test_list_since_excludes_records_before_cutoff(store):
    old_record = store.create(make_payload(when=datetime(2026, 1, 1, tzinfo=timezone.utc)))
    new_record = store.create(make_payload(when=datetime(2026, 6, 1, tzinfo=timezone.utc)))

    cutoff = datetime(2026, 3, 1, tzinfo=timezone.utc)
    records = store.list_since(cutoff)

    assert [r.id for r in records] == [new_record.id]
    assert old_record.id not in [r.id for r in records]


def test_list_since_includes_record_exactly_at_cutoff(store):
    cutoff = datetime(2026, 3, 1, tzinfo=timezone.utc)
    record = store.create(make_payload(when=cutoff))

    records = store.list_since(cutoff)

    assert [r.id for r in records] == [record.id]


def test_stats_on_empty_store(store):
    stats = store.stats()

    assert stats.count == 0
    assert stats.oldest is None
    assert stats.newest is None


def test_stats_with_single_record(store):
    record = store.create(make_payload())

    stats = store.stats()

    assert stats.count == 1
    assert stats.oldest.id == record.id
    assert stats.newest.id == record.id


def test_stats_with_multiple_records(store):
    oldest_record = store.create(make_payload(when=datetime(2026, 1, 1, tzinfo=timezone.utc)))
    store.create(make_payload(when=datetime(2026, 3, 1, tzinfo=timezone.utc)))
    newest_record = store.create(make_payload(when=datetime(2026, 6, 1, tzinfo=timezone.utc)))

    stats = store.stats()

    assert stats.count == 3
    assert stats.oldest.id == oldest_record.id
    assert stats.newest.id == newest_record.id


def test_get_returns_none_for_unknown_id(store):
    assert store.get(uuid.uuid4()) is None


def test_delete_removes_record_and_indexes(store, fake_redis_client):
    record = store.create(make_payload())

    deleted = store.delete(record.id)

    assert deleted is True
    assert fake_redis_client.get(f"sighting:{record.id}") is None
    assert fake_redis_client.zscore("sightings:by_time", str(record.id)) is None
    assert fake_redis_client.zscore("sightings:geo", str(record.id)) is None
    assert store.list_all() == []


def test_delete_returns_false_for_unknown_id(store):
    assert store.delete(uuid.uuid4()) is False
