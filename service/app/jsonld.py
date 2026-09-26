"""The JSON-LD context for this API's own responses, and Accept-based content negotiation
between application/json and application/ld+json.

The vocabulary is project-specific (https://whale-sightings.org/ns#) rather than Darwin
Core/schema.org: its IRIs only need to be globally unique and stable, not resolvable, and
no current peer (Whale Alert included) uses any shared vocabulary to align with yet. Every
term here maps an *existing* JSON key — nothing in a response body is renamed for JSON-LD's
sake, so clients reading plain keys (client-admin, the mobile client, the
whale-alert-connector) are unaffected.
"""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

VOCAB = "https://whale-sightings.org/ns#"

JSONLD_MEDIA_TYPE = "application/ld+json"

# Served by routers/contexts.py; referenced by URL from every annotated sighting (see
# discovery.py's annotate_record) rather than inlined, since GET /sightings is a bare array
# and an inlined context would repeat on every one of its elements.
CONTEXT_PATH = "/contexts/sighting.jsonld"

SIGHTING_CONTEXT: dict[str, Any] = {
    "@version": 1.1,
    "@vocab": VOCAB,
    "xsd": "http://www.w3.org/2001/XMLSchema#",
    "created_at": {"@type": "xsd:dateTime"},
    "deleted_at": {"@type": "xsd:dateTime"},
    "datetime": {"@type": "xsd:dateTime"},
    # JSON-LD treats a plain array as an unordered set of values: GeoJSON's positional
    # [lon, lat] would lose its order in RDF, and a point with lon == lat (e.g. [0, 0])
    # would collapse to a single value. A JSON literal keeps the array exactly as sent.
    # Only `coordinates`, not all of `geometry` — `properties.datetime` (the observation
    # time) lives inside the geometry too and should stay visible to the graph.
    "coordinates": {"@type": "@json"},
    "species_uri": {"@type": "@id"},
    "images": {"@type": "@id"},
    # HAL-style hypermedia controls: kept intact for clients, opaque to the graph.
    "_links": {"@type": "@json"},
    # Three unrelated `type` keys — the animal ("orca"), the GeoJSON geometry ("Point"),
    # and provenance ("local"/"peer"/"whale_alert") — given distinct predicates via
    # property-scoped contexts instead of renaming the keys.
    "sighting": {"@context": {"type": "animalType"}},
    "geometry": {"@context": {"type": "geometryType"}},
    "source": {"@context": {"type": "sourceType"}},
    # Every current producer sends an absolute IRI here (client-admin, the mobile client,
    # peer-service, the connector's WHALE_ALERT_OBSERVER_ID), making the observer a named
    # node. Not validated server-side — a non-IRI string would resolve as a relative IRI.
    "observer": {"@context": {"id": "@id"}},
}

ROOT_CONTEXT: dict[str, Any] = {
    "@version": 1.1,
    "@vocab": VOCAB,
    "_links": {"@type": "@json"},
}


def wants_jsonld(request: Request) -> bool:
    return JSONLD_MEDIA_TYPE in request.headers.get("accept", "")


def negotiated_json(body: Any, request: Request, status_code: int = 200) -> JSONResponse:
    """Same body either way — only the Content-Type differs, so a plain-JSON caller sees
    exactly what it always has."""
    media_type = JSONLD_MEDIA_TYPE if wants_jsonld(request) else "application/json"
    return JSONResponse(body, status_code=status_code, media_type=media_type)
