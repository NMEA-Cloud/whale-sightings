from datetime import datetime, timezone

from app.models import ModerationStatus, SightingRecord, SightingSourceType


def _legacy_record_json() -> dict:
    """A hand-written record shaped exactly like data written before `source` and
    `moderation_status` existed — no such keys at all, not just null values."""
    when = datetime(2026, 1, 1, tzinfo=timezone.utc).isoformat()
    return {
        "id": "11111111-1111-1111-1111-111111111111",
        "created_at": when,
        "sighting": {
            "location": {
                "geometry": {
                    "type": "Point",
                    "coordinates": [-122.645, 47.726],
                    "properties": {"datetime": when},
                }
            },
            "status": "alive",
            "comments": None,
            "type": "wombat",
            "species": "Greater Pacific Wombat",
            "name": None,
            "method": "manual-report",
        },
        "observer": {
            "id": "https://example.org/users/anonymous-observer",
            "location": {
                "geometry": {
                    "type": "Point",
                    "coordinates": [-122.645, 47.726],
                    "properties": {"datetime": when},
                }
            },
        },
        "images": [],
    }


def test_legacy_record_missing_source_backfills_to_local_with_no_moderation_status():
    record = SightingRecord.model_validate(_legacy_record_json())

    assert record.source.type == SightingSourceType.LOCAL
    assert record.source.peer_id is None
    assert record.source.upstream_id is None
    assert record.moderation_status is None
