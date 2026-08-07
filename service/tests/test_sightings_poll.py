from datetime import datetime, timedelta, timezone

from tests.test_sightings_api import sample_payload_dict


def _one_hour_ago_iso() -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()


def test_poll_returns_immediately_on_existing_match(client):
    body = client.post("/sightings", json=sample_payload_dict()).json()

    response = client.get(
        "/sightings/poll", params={"since": _one_hour_ago_iso(), "timeout_seconds": 5}
    )

    assert response.status_code == 200
    assert [r["id"] for r in response.json()] == [body["id"]]

    client.delete(f"/sightings/{body['id']}")


def test_poll_matches_backdated_sighting_by_creation_time_not_reported_datetime(client):
    # Regression test for a real bug found via manual testing: the report form allows
    # backdating ("spotted 20 minutes ago" — see admin's demo scenarios), and a poll
    # started after the sighting's own reported datetime but before it was actually
    # created must still see it. Filtering on the sighting's own datetime (instead of
    # created_at) made a backdated-but-brand-new sighting invisible to an in-progress poll.
    payload = sample_payload_dict()
    backdated = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
    payload["sighting"]["location"]["geometry"]["properties"]["datetime"] = backdated
    payload["observer"]["location"]["geometry"]["properties"]["datetime"] = backdated

    # since sits between the sighting's own (backdated) datetime and the real creation
    # moment about to happen below — a check based on the sighting's own datetime would
    # miss it, since that field is already "before since" by the time it's created.
    since = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    body = client.post("/sightings", json=payload).json()

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

    response = client.get(
        "/sightings/poll",
        params={
            "since": _one_hour_ago_iso(),
            "lat": 47.726,
            "lon": -122.645,
            "radius_nm": 10,
            "timeout_seconds": 5,
        },
    )

    assert response.status_code == 200
    assert [r["id"] for r in response.json()] == [nearby_id]

    client.delete(f"/sightings/{nearby_id}")
    client.delete(f"/sightings/{far_id}")


def test_poll_rejects_partial_location_params(client):
    response = client.get(
        "/sightings/poll",
        params={"since": _one_hour_ago_iso(), "lat": 47.726, "timeout_seconds": 1},
    )

    assert response.status_code == 400


def test_poll_cursor_is_exclusive_not_inclusive(client):
    body = client.post("/sightings", json=sample_payload_dict()).json()

    # Polling again with since set to the exact created_at just matched should NOT
    # re-match it — list_created_since()/list_within_radius() are inclusive (>=), but the
    # poll endpoint post-filters strictly (>) so an advancing client cursor doesn't loop on
    # the same record.
    response = client.get(
        "/sightings/poll", params={"since": body["created_at"], "timeout_seconds": 1}
    )

    assert response.status_code == 204

    client.delete(f"/sightings/{body['id']}")
