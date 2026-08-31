from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.models import (
    GeoJSONPoint,
    GeoJSONPointProperties,
    Location,
    ModerationStatus,
    Observer,
    SightingCreate,
    SightingData,
    SightingMethod,
    SightingStatus,
)

# Whale Alert doesn't expose any observer identity safe to republish — its `email`/
# `submitter_name`/`submitter_user_id` fields are real PII (redacted even in our own saved
# reference examples), and this service publishes sighting data unauthenticated/publicly.
# No Whale Alert PII is ever forwarded here; source_upstream_id (Whale Alert's own numeric
# id, set below) is what carries correlation, not this placeholder.
WHALE_ALERT_OBSERVER_ID = "https://seereportsave.org/whalealert/observers/anonymous"

# Only "Live" and "entangled" have been seen in reviewed real examples (see the reference
# collection's report_type=dead_entangled example for the latter) — the rest of this mapping
# is a best-effort guess at plausible values, not confirmed against real data. Matched
# case-insensitively since casing is inconsistent even between these two ("Live" vs
# "entangled").
_ANIMAL_STATUS_MAP: dict[str, SightingStatus] = {
    "live": SightingStatus.ALIVE,
    "dead": SightingStatus.DEAD,
    "deceased": SightingStatus.DEAD,
    "entangled": SightingStatus.DISTRESSED,
    "distressed": SightingStatus.DISTRESSED,
    "injured": SightingStatus.DISTRESSED,
}


def _map_status(animal_status: str | None) -> SightingStatus:
    """Falls back to UNKNOWN (an existing, legitimate value in our own enum) for anything
    unrecognized, rather than raising — an unrecognized status shouldn't block ingesting an
    otherwise-good sighting."""
    if animal_status is None:
        return SightingStatus.UNKNOWN
    return _ANIMAL_STATUS_MAP.get(animal_status.strip().lower(), SightingStatus.UNKNOWN)


def _parse_created(created: str) -> datetime:
    """Whale Alert's `created` timestamp ("YYYY-MM-DD HH:MM:SS") carries no timezone marker
    in any reviewed example. Assumed UTC here, but this is explicitly UNCONFIRMED (see the
    plan's Context section) until checked against a live poll — revisit if ingested
    sightings appear offset by whatever Whale Alert's actual server timezone turns out to
    be."""
    naive = datetime.strptime(created, "%Y-%m-%d %H:%M:%S")
    return naive.replace(tzinfo=timezone.utc)


def to_sighting_create(wa_result: dict[str, Any], moderation_status: ModerationStatus) -> SightingCreate:
    """Maps one result from Whale Alert's GET /sightings into our own SightingCreate shape.
    Two deliberate, known mapping gaps — Whale Alert's schema simply doesn't carry this
    data, not an oversight:
    - `species` ends up as Whale Alert's own free-text common name (e.g. "Killer Whale
      (Orca)"), not a scientific binomial the way our own local demo data uses that field —
      Whale Alert has no Latin-name field to draw from instead.
    - `images` is always empty. No reviewed example shows a populated `photo` value, and
      redistributing Whale Alert's own hosted photos raises a content-provenance question
      this plan hasn't addressed — deferred, not forgotten.
    """
    when = _parse_created(wa_result["created"])
    location = Location(
        geometry=GeoJSONPoint(
            coordinates=(wa_result["lng"], wa_result["lat"]),
            properties=GeoJSONPointProperties(datetime=when),
        )
    )
    sighting = SightingData(
        location=location,
        status=_map_status(wa_result.get("animal_status")),
        comments=wa_result.get("comments") or None,
        # species_id is a short slug (e.g. "humpback_whale", "orca_killer_whale") — the
        # closest Whale Alert equivalent to our own casual "type" bucket convention
        # (e.g. "orca", "gray whale"; see client-admin's demo SCENARIOS).
        type=wa_result["species_id"].replace("_", " "),
        species=wa_result["species"],
        name=None,
        # Whale Alert's own `source` field ("mobile_app"/"API") always means a real report
        # was filed by or on behalf of an observer — closer to our own "manual-report" than
        # "other".
        method=SightingMethod.MANUAL_REPORT,
    )
    observer = Observer(id=WHALE_ALERT_OBSERVER_ID, location=location)
    return SightingCreate(
        sighting=sighting,
        observer=observer,
        images=[],
        source_upstream_id=str(wa_result["id"]),
        source_moderation_status=moderation_status,
    )


_MODERATED_MAP: dict[int, ModerationStatus] = {
    0: ModerationStatus.UNREVIEWED,
    1: ModerationStatus.CONFIRMED,
    2: ModerationStatus.UNCONFIRMED,
}


def wa_status_to_moderation_status(moderated: int) -> ModerationStatus | None:
    """Maps Whale Alert's `moderated` integer (0/1/2/3) to our ModerationStatus, or None as
    the "this needs a real DELETE, not a PATCH" sentinel for 3 (Deleted) — our own
    ModerationStatus deliberately has no DELETED member (see models.py)."""
    if moderated == 3:
        return None
    try:
        return _MODERATED_MAP[moderated]
    except KeyError:
        raise ValueError(f"Unrecognized Whale Alert moderated value: {moderated!r}") from None
