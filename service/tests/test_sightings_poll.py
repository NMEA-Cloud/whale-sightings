from datetime import datetime, timedelta, timezone

from tests.test_sightings_api import sample_payload_dict

# Matches sample_payload_dict()'s fixed sighting datetime ("2026-07-07T16:18:04.113Z").
SAMPLE_DATETIME = datetime(2026, 7, 7, 16, 18, 4, 113000, tzinfo=timezone.utc)


def test_poll_returns_immediately_on_existing_match(client):
    body = client.post("/sightings", json=sample_payload_dict()).json()

    since = (SAMPLE_DATETIME - timedelta(hours=1)).isoformat()
    response = client.get("/sightings/poll", params={"since": since, "timeout_seconds": 5})

    assert response.status_code == 200
    assert [r["id"] for r in response.json()] == [body["id"]]

    client.delete(f"/sightings/{body['id']}")


def test_poll_times_out_with_204_when_nothing_matches(client):
    since = datetime.now(timezone.utc).isoformat()

    response = client.get("/sightings/poll", params={"since": since, "timeout_seconds": 1})

    assert response.status_code == 204
    assert response.content == b""


def test_poll_combines_radius_filter(client):
    nearby = sample_payload_dict()
    nearby["sighting"]["location"]["geometry"]["coordinates"] = [-122.655, 47.726]
    nearby["observer"]["location"]["geometry"]["coordinates"] = [-122.655, 47.726]

    far = sample_payload_dict()
    far["sighting"]["location"]["geometry"]["coordinates"] = [-122.645, 49.726]
    far["observer"]["location"]["geometry"]["coordinates"] = [-122.645, 49.726]

    nearby_id = client.post("/sightings", json=nearby).json()["id"]
    far_id = client.post("/sightings", json=far).json()["id"]

    since = (SAMPLE_DATETIME - timedelta(hours=1)).isoformat()
    response = client.get(
        "/sightings/poll",
        params={"since": since, "lat": 47.726, "lon": -122.645, "radius_nm": 10, "timeout_seconds": 5},
    )

    assert response.status_code == 200
    assert [r["id"] for r in response.json()] == [nearby_id]

    client.delete(f"/sightings/{nearby_id}")
    client.delete(f"/sightings/{far_id}")


def test_poll_rejects_partial_location_params(client):
    response = client.get(
        "/sightings/poll",
        params={"since": SAMPLE_DATETIME.isoformat(), "lat": 47.726, "timeout_seconds": 1},
    )

    assert response.status_code == 400


def test_poll_cursor_is_exclusive_not_inclusive(client):
    body = client.post("/sightings", json=sample_payload_dict()).json()
    matched_datetime = body["sighting"]["location"]["geometry"]["properties"]["datetime"]

    # Polling again with since set to the exact datetime just matched should NOT re-match
    # it — list_since()/list_within_radius() are inclusive (>=), but the poll endpoint
    # post-filters strictly (>) so an advancing client cursor doesn't loop on the same record.
    response = client.get("/sightings/poll", params={"since": matched_datetime, "timeout_seconds": 1})

    assert response.status_code == 204

    client.delete(f"/sightings/{body['id']}")
