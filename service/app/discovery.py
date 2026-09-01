"""HATEOAS discovery document and JSON-LD-flavored response annotation.

The root document (build_root_document) is what a peer service is meant to fetch instead
of hardcoding endpoint paths — sibling in spirit to well_known.py's
GET /.well-known/oauth-protected-resource: same plain-JSON, unauthenticated style, no
hosted @context document. annotate_record wraps an already-persisted SightingRecord with
@id/@type/_links for individual sighting responses, without adding request-time-only
fields to SightingRecord itself — that keeps the Valkey-persisted shape clean.
"""

from __future__ import annotations

from typing import Any

from app.config import Settings
from app.models import SightingRecord, SightingSourceType

# WoRMS (World Register of Marine Species) AphiaID URIs for the species names appearing in
# this project's own demo data (client-admin's SCENARIOS, and whatever peer-service
# generates later) — pointing at an already-authoritative external vocabulary is real
# semantic interop; hosting a private enumeration of our own (the pattern Whale Alert
# appears to use for some lookups) would just reproduce a private convention under a
# JSON-LD label. Only `species` (the scientific name) gets this — `type` (a casual bucket
# like "orca"/"gray whale") isn't a species-identity claim. Verified against WoRMS directly
# (marinespecies.org/rest/AphiaRecordsByMatchNames), not guessed.
SPECIES_CONTEXT: dict[str, str] = {
    "Orcinus orca": "urn:lsid:marinespecies.org:taxname:137102",
    "Eschrichtius robustus": "urn:lsid:marinespecies.org:taxname:137112",
    "Balaenoptera acutorostrata": "urn:lsid:marinespecies.org:taxname:137087",
    "Megaptera novaeangliae": "urn:lsid:marinespecies.org:taxname:137092",
}


def _ws_url(base_url: str, path: str) -> str:
    """https://host/... -> wss://host/... (or http -> ws) — for the one link in the
    discovery document that isn't a plain HTTP(S) URL."""
    if base_url.startswith("https://"):
        return "wss://" + base_url[len("https://") :] + path
    if base_url.startswith("http://"):
        return "ws://" + base_url[len("http://") :] + path
    return base_url + path  # defensive fallback; not expected with real settings


def build_root_document(base_url: str, settings: Settings) -> dict[str, Any]:
    """`base_url` is derived from the actual incoming request (see health.py's root route),
    not a fixed setting — a caller reaching this service via a different address than its
    canonical public one (e.g. a same-host peer container using the Docker-internal
    "service" hostname instead of the browser-facing one) needs links built from the
    address that actually worked for it, or the links it gets back are simply unreachable
    for that caller. `settings` is still needed for the one non-HTTP link (mqtt:broker),
    which is Docker-internal-only regardless of how this HTTP request arrived."""
    base = base_url.rstrip("/")
    return {
        "@context": {"@vocab": "https://schema.org/"},
        "@type": "Service",
        "name": "Whale Sightings",
        "_links": {
            "self": {"href": f"{base}/"},
            "sightings:create": {"href": f"{base}/sightings", "method": "POST"},
            "sightings:list": {"href": f"{base}/sightings", "method": "GET"},
            "sightings:poll": {"href": f"{base}/sightings/poll", "method": "GET"},
            "sightings:stats": {"href": f"{base}/sightings/stats", "method": "GET"},
            "sightings:by-source": {
                "href": f"{base}/sightings/by-source/{{source_type}}/{{upstream_id}}",
                "method": "GET",
                "templated": True,
            },
            "sightings:live-sync": {"href": _ws_url(base, "/sightings/ws")},
            "oauth:protected-resource": {"href": f"{base}/.well-known/oauth-protected-resource"},
            "docs": {"href": f"{base}/docs"},
            # Not an HTTP link — a same-host peer container needs the broker's own
            # host/port/topic to subscribe directly, already Docker-internal values.
            "mqtt:broker": {"host": settings.mqtt_host, "port": settings.mqtt_port, "topic": settings.mqtt_topic},
        },
    }


def annotate_record(record: SightingRecord, base_url: str, can_delete: bool) -> dict[str, Any]:
    base = base_url.rstrip("/")
    self_href = f"{base}/sightings/{record.id}"

    body: dict[str, Any] = record.model_dump(mode="json")

    species_uri = SPECIES_CONTEXT.get(record.sighting.species)
    if species_uri:
        body["sighting"]["species_uri"] = species_uri

    body["@id"] = self_href
    body["@type"] = "Event"  # schema.org's closest fit for a point-in-time observation

    links: dict[str, Any] = {"self": {"href": self_href}}
    if can_delete:
        links["delete"] = {"href": self_href, "method": "DELETE"}
    body["_links"] = links

    return body


def can_delete_record(record: SightingRecord) -> bool:
    """Only local sightings get a `delete` link — mirrors delete_sighting's own
    source-based restriction (see routers/sightings.py) rather than duplicating authority
    over it. Peer sightings (source.type == "peer") deliberately get no delete link either,
    ahead of Phase B's server-side enforcement of that same rule."""
    return record.source.type == SightingSourceType.LOCAL
