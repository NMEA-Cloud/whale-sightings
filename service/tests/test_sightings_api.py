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

    client.post("/sightings", json=first)
    client.post("/sightings", json=second)

    response = client.get("/sightings")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    assert body[0]["sighting"]["location"]["geometry"]["properties"]["datetime"].startswith("2026-06-01")
