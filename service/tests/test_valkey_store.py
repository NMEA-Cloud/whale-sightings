import uuid
from datetime import datetime, timedelta, timezone

from app.models import (
    GeoJSONPoint,
    GeoJSONPointProperties,
    Location,
    Observer,
    ModerationStatus,
    SightingCreate,
    SightingData,
    SightingMethod,
    SightingRecord,
    SightingSource,
    SightingSourceType,
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
    assert record.created_at is not None
    assert fake_redis_client.get(f"sighting:{record.id}") is not None
    assert fake_redis_client.zscore("sightings:by_time", str(record.id)) is not None
    assert fake_redis_client.zscore("sightings:by_created_at", str(record.id)) is not None


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


def test_list_created_since_excludes_records_before_cutoff(store):
    record = store.create(make_payload())

    cutoff = record.created_at + timedelta(seconds=1)

    assert store.list_created_since(cutoff) == []


def test_list_created_since_includes_record_at_cutoff(store):
    record = store.create(make_payload())

    records = store.list_created_since(record.created_at)

    assert [r.id for r in records] == [record.id]


def test_list_created_since_includes_backdated_sighting_that_list_since_would_exclude(store):
    # The key distinction this store method exists for: list_since() filters on the
    # sighting's own (backdatable) reported datetime, list_created_since() on when the
    # record was actually inserted — a sighting reported as "spotted an hour ago" is still
    # brand new data right now.
    backdated_when = datetime.now(timezone.utc) - timedelta(hours=1)
    record = store.create(make_payload(when=backdated_when))

    cutoff = datetime.now(timezone.utc) - timedelta(minutes=1)

    assert store.list_since(cutoff) == []
    assert [r.id for r in store.list_created_since(cutoff)] == [record.id]


def test_list_all_backfills_created_at_for_legacy_records_missing_it(store, fake_redis_client):
    # Regression test: a real teammate pulled main onto a Valkey volume containing sightings
    # written before created_at existed, and GET /sightings 500'd because _hydrate() couldn't
    # deserialize them. Simulate that by writing a pre-created_at record straight into the
    # store, bypassing store.create() (which always sets created_at on new records).
    legacy_id = str(uuid.uuid4())
    when = datetime(2026, 1, 1, tzinfo=timezone.utc)
    legacy_json = (
        '{"id": "%s", "sighting": {"location": {"geometry": {"type": "Point", '
        '"coordinates": [-122.645, 47.726], "properties": {"datetime": "%s"}}}, '
        '"status": "alive", "comments": null, "type": "wombat", "species": "Greater Pacific Wombat", '
        '"name": null, "method": "manual-report"}, '
        '"observer": {"id": "https://example.org/users/anonymous-observer", '
        '"location": {"geometry": {"type": "Point", "coordinates": [-122.645, 47.726], '
        '"properties": {"datetime": "%s"}}}}, "images": []}'
    ) % (legacy_id, when.isoformat(), when.isoformat())
    fake_redis_client.set(f"sighting:{legacy_id}", legacy_json)
    fake_redis_client.zadd("sightings:by_time", {legacy_id: when.timestamp()})

    records = store.list_all()

    assert len(records) == 1
    assert records[0].created_at == when


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
    assert fake_redis_client.zscore("sightings:by_created_at", str(record.id)) is None
    assert fake_redis_client.zscore("sightings:geo", str(record.id)) is None
    assert store.list_all() == []


def test_delete_returns_false_for_unknown_id(store):
    assert store.delete(uuid.uuid4()) is False


def test_delete_records_tombstone(store, fake_redis_client):
    record = store.create(make_payload())

    store.delete(record.id)

    assert fake_redis_client.zscore("sightings:by_deleted_at", str(record.id)) is not None


def test_delete_of_unknown_id_leaves_no_tombstone(store):
    unknown_id = uuid.uuid4()

    store.delete(unknown_id)

    cutoff = datetime.now(timezone.utc) - timedelta(minutes=1)
    assert store.list_deleted_since(cutoff) == []


def test_list_deleted_since_excludes_deletions_before_cutoff(store):
    record = store.create(make_payload())
    store.delete(record.id)

    cutoff = datetime.now(timezone.utc) + timedelta(seconds=1)

    assert store.list_deleted_since(cutoff) == []


def test_list_deleted_since_includes_deletion_at_cutoff(store):
    record = store.create(make_payload())
    store.delete(record.id)
    [deletion] = store.list_deleted_since(datetime.now(timezone.utc) - timedelta(seconds=1))

    at_cutoff = store.list_deleted_since(deletion.deleted_at)

    assert [d.id for d in at_cutoff] == [record.id]


def test_list_within_radius_excludes_far_away_records(store):
    # ~0.01 degrees of longitude at this latitude is roughly 0.4nm away.
    nearby_record = store.create(make_payload(lon=-122.655, lat=47.726))
    # +2 degrees of latitude is roughly 120nm away, well outside a 10nm search.
    far_record = store.create(make_payload(lon=-122.645, lat=49.726))

    records = store.list_within_radius(lon=-122.645, lat=47.726, radius_nm=10)

    assert [r.id for r in records] == [nearby_record.id]
    assert far_record.id not in [r.id for r in records]


def test_list_within_radius_newest_first(store):
    older = store.create(
        make_payload(lon=-122.645, lat=47.726, when=datetime(2026, 1, 1, tzinfo=timezone.utc))
    )
    newer = store.create(
        make_payload(lon=-122.646, lat=47.727, when=datetime(2026, 6, 1, tzinfo=timezone.utc))
    )

    records = store.list_within_radius(lon=-122.645, lat=47.726, radius_nm=10)

    assert [r.id for r in records] == [newer.id, older.id]


def test_create_defaults_to_local_source(store):
    record = store.create(make_payload())

    assert record.source.type == SightingSourceType.LOCAL


def test_create_tags_given_source(store):
    source = SightingSource(type=SightingSourceType.WHALE_ALERT, upstream_id="116308")

    record = store.create(make_payload(), source=source)

    assert record.source == source


def test_update_reindexes_record(store):
    record = store.create(make_payload())
    moderated = record.model_copy(update={"moderation_status": ModerationStatus.CONFIRMED})

    updated = store.update(moderated)

    assert updated.moderation_status == ModerationStatus.CONFIRMED
    assert store.get(record.id).moderation_status == ModerationStatus.CONFIRMED


def test_update_returns_none_for_unknown_id(store):
    payload = make_payload()
    unsaved_record = SightingRecord(
        id=uuid.uuid4(),
        created_at=datetime.now(timezone.utc),
        sighting=payload.sighting,
        observer=payload.observer,
    )

    assert store.update(unsaved_record) is None


def test_update_does_not_change_source_counts(store):
    record = store.create(make_payload())

    store.update(record.model_copy(update={"moderation_status": ModerationStatus.CONFIRMED}))

    assert store.stats().by_source[SightingSourceType.LOCAL] == 1


def test_get_by_source_found(store):
    source = SightingSource(type=SightingSourceType.WHALE_ALERT, upstream_id="116308")
    record = store.create(make_payload(), source=source)

    found = store.get_by_source(SightingSourceType.WHALE_ALERT, "116308")

    assert found.id == record.id


def test_get_by_source_not_found(store):
    assert store.get_by_source(SightingSourceType.WHALE_ALERT, "does-not-exist") is None


def test_create_increments_source_type_count(store):
    store.create(make_payload())
    store.create(make_payload(), source=SightingSource(type=SightingSourceType.WHALE_ALERT, upstream_id="1"))
    store.create(make_payload(), source=SightingSource(type=SightingSourceType.WHALE_ALERT, upstream_id="2"))

    by_source = store.stats().by_source

    assert by_source[SightingSourceType.LOCAL] == 1
    assert by_source[SightingSourceType.WHALE_ALERT] == 2
    assert by_source[SightingSourceType.PEER] == 0


def test_delete_decrements_source_type_count(store):
    record = store.create(
        make_payload(), source=SightingSource(type=SightingSourceType.WHALE_ALERT, upstream_id="1")
    )

    store.delete(record.id)

    assert store.stats().by_source[SightingSourceType.WHALE_ALERT] == 0


def test_delete_removes_source_lookup(store):
    record = store.create(
        make_payload(), source=SightingSource(type=SightingSourceType.WHALE_ALERT, upstream_id="1")
    )

    store.delete(record.id)

    assert store.get_by_source(SightingSourceType.WHALE_ALERT, "1") is None
