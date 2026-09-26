"""Checks that the JSON-LD this API emits actually means what it says when run through a real
JSON-LD processor (pyld) — not just that the @-keys are present. The failure mode being
guarded against is silent: a key with no context mapping is simply dropped on expansion,
and a plain JSON array is treated as an unordered set once converted to RDF."""

import json

import pytest
from pyld import jsonld

from app.config import Settings
from app.discovery import annotate_record, build_root_document
from app.jsonld import CONTEXT_PATH, JSONLD_MEDIA_TYPE, SIGHTING_CONTEXT, VOCAB
from app.models import GeoJSONPoint, GeoJSONPointProperties, Location, SightingSource, SightingSourceType
from tests.test_discovery import make_record
from tests.test_sightings_api import sample_payload_dict

BASE = "https://example.org:8000"
NS = VOCAB


def _local_loader(url, options=None):
    """Serves SIGHTING_CONTEXT for the context URL without any network access."""
    assert url.endswith(CONTEXT_PATH), url
    return {
        "contentType": JSONLD_MEDIA_TYPE,
        "contextUrl": None,
        "documentUrl": url,
        "document": {"@context": SIGHTING_CONTEXT},
    }


def _client_loader(client):
    """Fetches the context through the app itself, so the test exercises the published
    context document rather than the Python constant behind it."""

    def load(url, options=None):
        response = client.get(url)
        assert response.status_code == 200
        return {
            "contentType": response.headers["content-type"],
            "contextUrl": None,
            "documentUrl": url,
            "document": response.json(),
        }

    return load


def _expand(doc, loader=_local_loader):
    return jsonld.expand(doc, {"documentLoader": loader})


def _quads(doc, loader=_local_loader) -> list[str]:
    return jsonld.to_rdf(doc, {"format": "application/n-quads", "documentLoader": loader}).splitlines()


def _predicates(node) -> set[str]:
    """Every property IRI used anywhere in an expanded document."""
    found: set[str] = set()
    if isinstance(node, list):
        for item in node:
            found |= _predicates(item)
    elif isinstance(node, dict):
        for key, value in node.items():
            if not key.startswith("@"):
                found.add(key)
                found |= _predicates(value)
    return found


def _json_literals(quads: list[str], predicate: str) -> list:
    """Parses the rdf:JSON literals for one predicate back into Python values."""
    values = []
    for quad in quads:
        if f"<{predicate}>" in quad:
            literal = quad.split(f"<{predicate}> ", 1)[1].rsplit("^^", 1)[0]
            values.append(json.loads(json.loads(literal)))
    return values


def _annotated(record=None):
    return annotate_record(record or make_record(), BASE, BASE, can_delete=True)


# --- unit: the context itself ---------------------------------------------------------------


def test_expansion_keeps_every_field():
    record = make_record(species="Orcinus orca")
    record.sighting.comments = "Thar she blows!"
    record.sighting.name = "J-pod"
    record.images = ["https://example.org/img/1.jpg"]
    record.source = SightingSource(type=SightingSourceType.PEER, peer_id="peer-1", upstream_id="u-1")

    predicates = _predicates(_expand(_annotated(record)))

    expected_local_names = {
        "id", "created_at", "sighting", "location", "geometry", "coordinates", "geometryType",
        "properties", "datetime", "status", "comments", "animalType", "species", "species_uri",
        "name", "method", "observer", "images", "source", "sourceType", "peer_id", "upstream_id",
        "_links",
    }  # fmt: skip
    assert predicates == {NS + name for name in expected_local_names}


def test_record_has_sighting_type_and_canonical_id():
    [node] = _expand(_annotated())

    assert node["@type"] == [NS + "Sighting"]
    assert node["@id"] == f"{BASE}/sightings/11111111-1111-1111-1111-111111111111"


@pytest.mark.parametrize("coordinates", [(-122.645, 47.726), (45.0, 45.0), (0.0, 0.0)])
def test_coordinates_keep_order_and_duplicates_in_rdf(coordinates):
    record = make_record()
    when = record.sighting.location.geometry.properties.datetime
    record.sighting.location = Location(
        geometry=GeoJSONPoint(coordinates=coordinates, properties=GeoJSONPointProperties(datetime=when))
    )

    values = _json_literals(_quads(_annotated(record)), NS + "coordinates")

    assert list(coordinates) in values


def test_three_type_keys_map_to_distinct_predicates():
    [node] = _expand(_annotated())
    sighting = node[NS + "sighting"][0]
    geometry = sighting[NS + "location"][0][NS + "geometry"][0]
    source = node[NS + "source"][0]

    assert sighting[NS + "animalType"] == [{"@value": "orca"}]
    assert geometry[NS + "geometryType"] == [{"@value": "Point"}]
    assert source[NS + "sourceType"] == [{"@value": "local"}]
    assert NS + "type" not in _predicates(node)


def test_species_uri_is_a_link_not_a_string():
    [node] = _expand(_annotated(make_record(species="Orcinus orca")))

    assert node[NS + "sighting"][0][NS + "species_uri"] == [{"@id": "urn:lsid:marinespecies.org:taxname:137102"}]


def test_observer_is_a_named_node():
    [node] = _expand(_annotated())

    assert node[NS + "observer"][0]["@id"] == "https://example.org/users/anonymous-observer"


def test_timestamps_are_typed_datetimes():
    [node] = _expand(_annotated())

    assert node[NS + "created_at"][0]["@type"] == "http://www.w3.org/2001/XMLSchema#dateTime"


def test_root_document_expands_links_as_json_literal():
    doc = build_root_document(BASE, Settings())

    [node] = jsonld.expand(doc)

    assert node["@type"] == [NS + "Service"]
    assert node[NS + "_links"][0]["@type"] == "@json"
    assert node[NS + "_links"][0]["@value"]["sightings:create"]["scope"] == "peer:write"


# --- integration: through the running app ---------------------------------------------------


def test_context_endpoint_serves_the_context(client):
    response = client.get(CONTEXT_PATH)

    assert response.status_code == 200
    assert response.headers["content-type"] == JSONLD_MEDIA_TYPE
    assert response.json() == {"@context": SIGHTING_CONTEXT}


def test_created_sighting_expands_with_the_published_context(client):
    created = client.post("/sightings", json=sample_payload_dict(), headers={"Accept": JSONLD_MEDIA_TYPE})
    assert created.status_code == 201
    assert created.headers["content-type"] == JSONLD_MEDIA_TYPE
    sighting_id = created.json()["id"]

    fetched = client.get(f"/sightings/{sighting_id}", headers={"Accept": JSONLD_MEDIA_TYPE})

    assert fetched.headers["content-type"] == JSONLD_MEDIA_TYPE
    [node] = _expand(fetched.json(), loader=_client_loader(client))
    assert node["@type"] == [NS + "Sighting"]
    assert node[NS + "sighting"][0][NS + "species"] == [{"@value": "Greater Pacific Wombat"}]
    assert node[NS + "observer"][0]["@id"] == "https://example.org/users/anonymous-observer"


def test_list_elements_each_expand(client):
    client.post("/sightings", json=sample_payload_dict())
    client.post("/sightings", json=sample_payload_dict())

    response = client.get("/sightings", headers={"Accept": JSONLD_MEDIA_TYPE})

    assert response.headers["content-type"] == JSONLD_MEDIA_TYPE
    body = response.json()
    assert len(body) == 2
    for element in body:
        [node] = _expand(element, loader=_client_loader(client))
        assert node["@type"] == [NS + "Sighting"]


def test_plain_json_clients_see_unchanged_shape(client):
    client.post("/sightings", json=sample_payload_dict())

    response = client.get("/sightings", headers={"Accept": "application/json"})

    assert response.headers["content-type"] == "application/json"
    [record] = response.json()
    for key in ("id", "created_at", "sighting", "observer", "images", "source", "moderation_status", "_links"):
        assert key in record
    assert record["sighting"]["type"] == "wombat"
    assert record["source"]["type"] == "local"
    assert record["sighting"]["location"]["geometry"]["coordinates"] == [-122.64504694316724, 47.72618676380336]
