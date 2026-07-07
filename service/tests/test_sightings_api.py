from datetime import datetime, timedelta, timezone


def sample_payload_dict() -> dict:
    return {
        "sighting": {
            "location": {
                "geometry": {
                    "type": "Point",
                    "coordinates": [-122.64504694316724, 47.72618676380336],
                    "properties": {"datetime": "2026-07-07T16:18:04.113Z"},
                }
            },
            "status": "alive",
            "comments": "Thar she blows!",
            "type": "wombat",
            "species": "Greater Pacific Wombat",
            "name": "LB-Whale",
            "method": "manual-report",
        },
        "observer": {
            "id": "https://example.org/users/anonymous-observer",
            "location": {
                "geometry": {
                    "type": "Point",
                    "coordinates": [-122.64504694316724, 47.72618676380336],
                    "properties": {"datetime": "2026-07-07T16:18:04.113Z"},
                }
            },
        },
        "images": [],
    }


def test_create_sighting_returns_201_with_id(client):
    response = client.post("/sightings", json=sample_payload_dict())

    assert response.status_code == 201
    body = response.json()
    assert "id" in body
    assert body["sighting"]["species"] == "Greater Pacific Wombat"

    # Confirm it's retrievable via GET before cleaning it up via DELETE.
    assert any(r["id"] == body["id"] for r in client.get("/sightings").json())

    delete_response = client.delete(f"/sightings/{body['id']}")
    assert delete_response.status_code == 204
    assert client.get("/sightings").json() == []


def test_create_sighting_rejects_unknown_fields(client):
    payload = sample_payload_dict()
    payload["id"] = "should-not-be-allowed"

    response = client.post("/sightings", json=payload)

    assert response.status_code == 422


def test_list_sightings_newest_first(client):
    first = sample_payload_dict()
    first["sighting"]["location"]["geometry"]["properties"]["datetime"] = "2026-01-01T00:00:00Z"

    second = sample_payload_dict()
    second["sighting"]["location"]["geometry"]["properties"]["datetime"] = "2026-06-01T00:00:00Z"

    first_id = client.post("/sightings", json=first).json()["id"]
    second_id = client.post("/sightings", json=second).json()["id"]

    response = client.get("/sightings")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    assert body[0]["sighting"]["location"]["geometry"]["properties"]["datetime"].startswith("2026-06-01")

    # GET is confirmed working above; now clean up via the delete endpoint.
    assert client.delete(f"/sightings/{first_id}").status_code == 204
    assert client.delete(f"/sightings/{second_id}").status_code == 204
    assert client.get("/sightings").json() == []


def test_delete_unknown_sighting_returns_404(client):
    response = client.delete("/sightings/00000000-0000-0000-0000-000000000000")

    assert response.status_code == 404


def test_list_sightings_since_hours_filters_older_records(client):
    recent = sample_payload_dict()
    recent["sighting"]["location"]["geometry"]["properties"]["datetime"] = (
        datetime.now(timezone.utc) - timedelta(hours=2)
    ).isoformat()

    old = sample_payload_dict()
    old["sighting"]["location"]["geometry"]["properties"]["datetime"] = (
        datetime.now(timezone.utc) - timedelta(hours=100)
    ).isoformat()

    recent_id = client.post("/sightings", json=recent).json()["id"]
    old_id = client.post("/sightings", json=old).json()["id"]

    response = client.get("/sightings", params={"since_hours": 24})

    assert response.status_code == 200
    assert [r["id"] for r in response.json()] == [recent_id]

    # Clean up.
    assert client.delete(f"/sightings/{recent_id}").status_code == 204
    assert client.delete(f"/sightings/{old_id}").status_code == 204


def test_list_sightings_rejects_non_positive_since_hours(client):
    response = client.get("/sightings", params={"since_hours": 0})

    assert response.status_code == 422
