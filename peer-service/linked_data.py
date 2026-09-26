"""Reading a whale-sightings sighting as linked data — pure functions, no I/O, unit-testable
in isolation (see tests/test_linked_data.py).

Everything here works on the *expanded* JSON-LD form, where every property is a full IRI,
and reads properties by IRI only — never by the JSON key names the service happens to use.
The service could rename any key (updating only its own @context) and this code would keep
working unchanged: that decoupling is the point of consuming the data as JSON-LD rather than
as plain JSON. The one thing shared with the service is its vocabulary namespace, NS.
"""

from __future__ import annotations

from typing import Any, Callable

NS = "https://schema.nmea.org/whale-sightings#"


def first(node: dict[str, Any] | None, iri: str) -> dict[str, Any] | None:
    """The first value of property `iri` on an expanded node, or None. Expanded JSON-LD
    always wraps property values in a list of value/node objects."""
    if not node:
        return None
    values = node.get(iri)
    return values[0] if values else None


def _value(entry: dict[str, Any] | None) -> Any:
    return entry.get("@value") if entry else None


def summarize(expanded: list[dict[str, Any]]) -> dict[str, Any]:
    """What this peer understands about one sighting, from its expanded JSON-LD form."""
    [node] = expanded
    report = first(node, NS + "sighting")
    geometry = first(first(report, NS + "location"), NS + "geometry")
    taxon = first(report, NS + "species_uri")
    return {
        "id": node.get("@id"),
        "species": _value(first(report, NS + "species")),
        "taxon": taxon.get("@id") if taxon else None,
        "origin": _value(first(first(node, NS + "source"), NS + "sourceType")),
        # A JSON literal (@type @json) — the GeoJSON [lon, lat] array exactly as sent.
        "position": _value(first(geometry, NS + "coordinates")),
        "observed_at": _value(first(first(geometry, NS + "properties"), NS + "datetime")),
    }


class CachingContextLoader:
    """A pyld document loader that fetches each @context URL once and serves it from memory
    afterwards — every sighting references the same context document, so there's no reason
    to refetch it per event. `fetch(url) -> dict` does the actual network call, injected so
    this stays I/O-free and testable."""

    def __init__(self, fetch: Callable[[str], dict[str, Any]]) -> None:
        self._fetch = fetch
        self._cache: dict[str, dict[str, Any]] = {}

    def __call__(self, url: str, options: dict[str, Any] | None = None) -> dict[str, Any]:
        if url not in self._cache:
            self._cache[url] = self._fetch(url)
        return {
            "contentType": "application/ld+json",
            "contextUrl": None,
            "documentUrl": url,
            "document": self._cache[url],
        }
