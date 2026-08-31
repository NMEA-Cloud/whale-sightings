import pytest

from app.ingest.mapping import WHALE_ALERT_OBSERVER_ID, to_sighting_create, wa_status_to_moderation_status
from app.models import ModerationStatus, SightingStatus

# Real, saved, PII-redacted example results from the reference Postman collection (one per
# moderation status) — see LONGPOLL_BUG_FIX_SUMMARY.md-style precedent of grounding designs
# in real captured data rather than fabricating shapes from scratch.
UNREVIEWED_RESULT = {
    "id": 116308,
    "created": "2026-08-03 14:13:00",
    "email": "redacted@example.com",
    "species": "No especificado",
    "species_id": "unknown_whale",
    "number": 1,
    "lat": 8.97974,
    "lng": -79.5109,
    "moderated": 0,
    "source": "mobile_app",
    "comments": "test panama",
    "animal_status": "Live",
}

CONFIRMED_RESULT = {
    "id": 116315,
    "created": "2026-08-03 15:33:00",
    "species": "Humpback",
    "species_id": "humpback_whale",
    "lat": 50.86575,
    "lng": -127.52036,
    "moderated": 1,
    "comments": "",
    "animal_status": "Live",
}

DEAD_ENTANGLED_RESULT = {
    "id": 113488,
    "created": "2026-07-03 14:43:00",
    "species": "Dwarf Sperm Whale",
    "species_id": "dwarf_sperm_whale",
    "lat": 0.2,
    "lng": 0.41667,
    "moderated": 1,
    "comments": "testingdemo",
    "animal_status": "entangled",
}


def test_to_sighting_create_maps_real_unreviewed_example():
    result = to_sighting_create(UNREVIEWED_RESULT, ModerationStatus.UNREVIEWED)

    assert result.source_upstream_id == "116308"
    assert result.source_moderation_status == ModerationStatus.UNREVIEWED
    assert result.sighting.species == "No especificado"
    assert result.sighting.type == "unknown whale"
    assert result.sighting.status == SightingStatus.ALIVE
    assert result.sighting.comments == "test panama"
    assert result.sighting.location.geometry.coordinates == (-79.5109, 8.97974)
    assert result.sighting.location.geometry.properties.datetime.isoformat() == "2026-08-03T14:13:00+00:00"
    assert result.observer.id == WHALE_ALERT_OBSERVER_ID
    assert result.images == []


def test_to_sighting_create_maps_humpback_example():
    result = to_sighting_create(CONFIRMED_RESULT, ModerationStatus.CONFIRMED)

    assert result.sighting.species == "Humpback"
    assert result.sighting.type == "humpback whale"
    assert result.source_moderation_status == ModerationStatus.CONFIRMED


def test_to_sighting_create_maps_empty_comments_to_none():
    result = to_sighting_create(CONFIRMED_RESULT, ModerationStatus.CONFIRMED)

    assert result.sighting.comments is None


def test_to_sighting_create_maps_entangled_status_to_distressed():
    result = to_sighting_create(DEAD_ENTANGLED_RESULT, ModerationStatus.CONFIRMED)

    assert result.sighting.status == SightingStatus.DISTRESSED


def test_to_sighting_create_falls_back_to_unknown_status_for_unrecognized_value():
    result = to_sighting_create({**UNREVIEWED_RESULT, "animal_status": "something-new"}, ModerationStatus.UNREVIEWED)

    assert result.sighting.status == SightingStatus.UNKNOWN


def test_to_sighting_create_falls_back_to_unknown_status_when_missing():
    result = to_sighting_create({k: v for k, v in UNREVIEWED_RESULT.items() if k != "animal_status"}, ModerationStatus.UNREVIEWED)

    assert result.sighting.status == SightingStatus.UNKNOWN


@pytest.mark.parametrize(
    "moderated, expected",
    [
        (0, ModerationStatus.UNREVIEWED),
        (1, ModerationStatus.CONFIRMED),
        (2, ModerationStatus.UNCONFIRMED),
    ],
)
def test_wa_status_to_moderation_status_maps_known_values(moderated, expected):
    assert wa_status_to_moderation_status(moderated) == expected


def test_wa_status_to_moderation_status_returns_none_for_deleted():
    assert wa_status_to_moderation_status(3) is None


def test_wa_status_to_moderation_status_rejects_unrecognized_value():
    with pytest.raises(ValueError, match="Unrecognized"):
        wa_status_to_moderation_status(99)


def test_to_sighting_create_json_dump_is_wire_safe():
    # This is the actual shape poller.py sends over HTTP (see ServiceClient.create) — enums
    # and datetimes must come out as plain JSON-safe strings, not Python objects.
    payload = to_sighting_create(UNREVIEWED_RESULT, ModerationStatus.UNREVIEWED).model_dump(mode="json")

    assert payload["source_moderation_status"] == "unreviewed"
    assert payload["sighting"]["status"] == "alive"
    assert payload["sighting"]["location"]["geometry"]["properties"]["datetime"] == "2026-08-03T14:13:00Z"
