from datetime import datetime, timezone

from app.discovery import SPECIES_CONTEXT, annotate_record, build_root_document, can_delete_record
from app.models import (
    GeoJSONPoint,
    GeoJSONPointProperties,
    Location,
    ModerationStatus,
    Observer,
    SightingData,
    SightingMethod,
    SightingRecord,
    SightingSource,
    SightingSourceType,
    SightingStatus,
)
from tests.test_auth import _fake_jwks  # noqa: F401 (autouse fixture: mocks JWKS lookups)
from tests.test_auth import _make_ingest_token, auth_client  # noqa: F401 (auth_client is a fixture)
from tests.test_sightings_api import sample_payload_dict


def make_record(species: str = "Orcinus orca", source: SightingSource | None = None, **overrides) -> SightingRecord:
    when = datetime(2026, 1, 1, tzinfo=timezone.utc)
    location = Location(
        geometry=GeoJSONPoint(coordinates=(-122.645, 47.726), properties=GeoJSONPointProperties(datetime=when))
    )
    return SightingRecord(
        id="11111111-1111-1111-1111-111111111111",
        created_at=when,
        sighting=SightingData(
            location=location,
            status=SightingStatus.ALIVE,
            comments=None,
            type="orca",
            species=species,
            name=None,
            method=SightingMethod.MANUAL_REPORT,
        ),
        observer=Observer(id="https://example.org/users/anonymous-observer", location=location),
        images=[],
        source=source or SightingSource(),
        **overrides,
    )


def test_build_root_document_links_include_key_endpoints():
    from app.config import Settings

    settings = Settings()

    doc = build_root_document("https://example.org:8000", settings)

    assert doc["_links"]["self"]["href"] == "https://example.org:8000/"
    assert doc["_links"]["sightings:create"] == {
        "href": "https://example.org:8000/sightings",
        "method": "POST",
        "scope": "peer:write",
    }
    assert doc["_links"]["sightings:by-source"]["templated"] is True
    assert doc["_links"]["sightings:live-sync"]["href"] == "wss://example.org:8000/sightings/ws"
    assert doc["_links"]["mqtt:broker"] == {
        "host": settings.mqtt_host,
        "port": settings.mqtt_port,
        "topic": settings.mqtt_topic,
    }


def test_annotate_record_sets_id_type_and_self_link():
    record = make_record()

    body = annotate_record(record, "https://example.org:8000", can_delete=True)

    assert body["@id"] == "https://example.org:8000/sightings/11111111-1111-1111-1111-111111111111"
    assert body["@type"] == "Event"
    assert body["_links"]["self"]["href"] == body["@id"]
    assert body["_links"]["delete"] == {"href": body["@id"], "method": "DELETE"}


def test_annotate_record_omits_delete_link_when_not_allowed():
    record = make_record()

    body = annotate_record(record, "https://example.org:8000", can_delete=False)

    assert "delete" not in body["_links"]


def test_annotate_record_adds_species_uri_for_known_species():
    record = make_record(species="Orcinus orca")

    body = annotate_record(record, "https://example.org:8000", can_delete=False)

    assert body["sighting"]["species_uri"] == SPECIES_CONTEXT["Orcinus orca"]


def test_annotate_record_omits_species_uri_for_unknown_species():
    record = make_record(species="Some Unlisted Whale")

    body = annotate_record(record, "https://example.org:8000", can_delete=False)

    assert "species_uri" not in body["sighting"]


def test_can_delete_record_true_for_local_only():
    local = make_record(source=SightingSource(type=SightingSourceType.LOCAL))
    whale_alert = make_record(source=SightingSource(type=SightingSourceType.WHALE_ALERT, upstream_id="1"))
    peer = make_record(source=SightingSource(type=SightingSourceType.PEER, peer_id="p1"))

    assert can_delete_record(local) is True
    assert can_delete_record(whale_alert) is False
    assert can_delete_record(peer) is False


def test_create_sighting_response_is_annotated(client):
    response = client.post("/sightings", json=sample_payload_dict())

    assert response.status_code == 201
    body = response.json()
    assert body["@type"] == "Event"
    assert body["_links"]["self"]["href"].endswith(f"/sightings/{body['id']}")
    assert body["_links"]["delete"]["method"] == "DELETE"

    client.delete(f"/sightings/{body['id']}")


def test_whale_alert_sourced_response_has_no_delete_link(auth_client):
    payload = sample_payload_dict()
    payload["source_upstream_id"] = "999999"

    response = auth_client.post(
        "/sightings", json=payload, headers={"Authorization": f"Bearer {_make_ingest_token()}"}
    )

    assert response.status_code == 201
    body = response.json()
    assert "delete" not in body["_links"]
