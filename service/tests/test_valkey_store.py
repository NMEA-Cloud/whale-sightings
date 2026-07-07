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


def test_get_returns_none_for_unknown_id(store):
    import uuid

    assert store.get(uuid.uuid4()) is None
