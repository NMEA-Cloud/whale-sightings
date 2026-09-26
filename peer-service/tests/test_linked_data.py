from pyld import jsonld

from linked_data import NS, CachingContextLoader, summarize
from tests.sighting_samples import CANONICAL_ID, fixture_fetch, sighting

EXPECTED = {
    "id": CANONICAL_ID,
    "species": "Orcinus orca",
    "taxon": "urn:lsid:marinespecies.org:taxname:137102",
    "origin": "peer",
    "position": [-122.645, 47.726],
    "observed_at": "2026-09-26T15:00:00Z",
}


def _expand(doc):
    return jsonld.expand(doc, {"documentLoader": CachingContextLoader(fixture_fetch)})


def test_summarize_reads_every_field_from_expanded_sighting():
    assert summarize(_expand(sighting())) == EXPECTED


def test_taxon_is_none_without_species_uri():
    doc = sighting()
    del doc["sighting"]["species_uri"]

    assert summarize(_expand(doc))["taxon"] is None


def test_position_keeps_lon_lat_order():
    doc = sighting()
    doc["sighting"]["location"]["geometry"]["coordinates"] = [10.0, 10.0]

    assert summarize(_expand(doc))["position"] == [10.0, 10.0]


def test_same_data_under_different_json_keys_is_understood_identically():
    """The point of reading by IRI: a producer using entirely different JSON key names, but
    a context mapping them to the same IRIs, means exactly the same thing to this peer."""
    renamed = {
        "@context": {
            "@version": 1.1,
            "ns": NS,
            "report": "ns:sighting",
            "where": "ns:location",
            "shape": "ns:geometry",
            "coords": {"@id": "ns:coordinates", "@type": "@json"},
            "props": "ns:properties",
            "when": {"@id": "ns:datetime", "@type": "http://www.w3.org/2001/XMLSchema#dateTime"},
            "latinName": "ns:species",
            "taxonLink": {"@id": "ns:species_uri", "@type": "@id"},
            "provenance": "ns:source",
            "kind": "ns:sourceType",
        },
        "@id": CANONICAL_ID,
        "report": {
            "where": {"shape": {"coords": [-122.645, 47.726], "props": {"when": "2026-09-26T15:00:00Z"}}},
            "latinName": "Orcinus orca",
            "taxonLink": "urn:lsid:marinespecies.org:taxname:137102",
        },
        "provenance": {"kind": "peer"},
    }

    assert summarize(jsonld.expand(renamed)) == EXPECTED


def test_loader_fetches_each_context_once():
    calls = []

    def counting_fetch(url):
        calls.append(url)
        return fixture_fetch(url)

    loader = CachingContextLoader(counting_fetch)
    first = loader("https://service:8000/contexts/sighting.jsonld")
    second = loader("https://service:8000/contexts/sighting.jsonld")

    assert calls == ["https://service:8000/contexts/sighting.jsonld"]
    assert first["document"] == second["document"]
    assert first["documentUrl"] == "https://service:8000/contexts/sighting.jsonld"
