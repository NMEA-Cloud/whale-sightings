"""Shared sample data for the linked-data tests. SIGHTING_CONTEXT_DOC is a copy of the
service's published context (service/app/jsonld.py, served at /contexts/sighting.jsonld) —
peer-service is a standalone deployable and can't import service code, so it's duplicated
here as a fixture. If the service's context changes, regenerate
tests/fixtures/sighting-context.jsonld from it."""

import copy
import json
from pathlib import Path

SIGHTING_CONTEXT_DOC = json.loads((Path(__file__).parent / "fixtures" / "sighting-context.jsonld").read_text())

CONTEXT_URL = "https://service:8000/contexts/sighting.jsonld"
LINK = "https://service:8000/sightings/11111111-1111-1111-1111-111111111111"
CANONICAL_ID = "https://api.dev.whale-sightings.org:8000/sightings/11111111-1111-1111-1111-111111111111"

_LOCATION = {
    "geometry": {
        "type": "Point",
        "coordinates": [-122.645, 47.726],
        "properties": {"datetime": "2026-09-26T15:00:00Z"},
    }
}

# A sighting exactly as GET /sightings/{id} returns it with Accept: application/ld+json.
SIGHTING = {
    "id": "11111111-1111-1111-1111-111111111111",
    "created_at": "2026-09-26T15:00:01Z",
    "sighting": {
        "location": _LOCATION,
        "status": "alive",
        "comments": None,
        "type": "orca",
        "species": "Orcinus orca",
        "name": None,
        "method": "other",
        "species_uri": "urn:lsid:marinespecies.org:taxname:137102",
    },
    "observer": {"id": "https://example.org/peer-service/observer", "location": _LOCATION},
    "images": [],
    "source": {"type": "peer", "peer_id": "peer-client", "upstream_id": None},
    "moderation_status": None,
    "@context": CONTEXT_URL,
    "@id": CANONICAL_ID,
    "@type": "Sighting",
    "_links": {"self": {"href": LINK}},
}


def sighting(**sighting_overrides) -> dict:
    doc = copy.deepcopy(SIGHTING)
    doc["sighting"].update(sighting_overrides)
    return doc


def fixture_fetch(url: str) -> dict:
    assert url == CONTEXT_URL, url
    return SIGHTING_CONTEXT_DOC
