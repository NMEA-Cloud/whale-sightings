import pytest
from fastapi.testclient import TestClient

from app.ingest import mock_whale_alert_server as mock_server

PUGET_SOUND_BBOX = "-123.3,47.0,-122.0,48.8"
WIDE_DATE_RANGE = {"start": "2020-01-01", "end": "2030-01-01"}


@pytest.fixture(autouse=True)
def reset_fixtures():
    # Every test gets a fresh copy of the seeded fixtures/token, regardless of what a
    # previous test mutated via /_mock/advance.
    mock_server._fixtures = {r["id"]: dict(r) for r in mock_server._ALL_TEMPLATES}
    mock_server._current_token = None
    yield


@pytest.fixture
def client():
    return TestClient(mock_server.app)


def _authed_get(client, **params):
    token = client.post(
        "/auth/token", json={"client_id": mock_server.MOCK_CLIENT_ID, "client_secret": mock_server.MOCK_CLIENT_SECRET}
    ).json()["access_token"]
    return client.get("/sightings", params=params, headers={"Authorization": f"Bearer {token}"})


def test_auth_token_accepts_configured_credentials(client):
    response = client.post(
        "/auth/token", json={"client_id": mock_server.MOCK_CLIENT_ID, "client_secret": mock_server.MOCK_CLIENT_SECRET}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "Bearer"
    assert body["expires_in"] == 3600
    assert "sightings:read" in body["scope"]


def test_auth_token_rejects_wrong_credentials(client):
    response = client.post("/auth/token", json={"client_id": "wrong", "client_secret": "wrong"})

    assert response.status_code == 401


def test_sightings_requires_bearer_token(client):
    response = client.get(
        "/sightings", params={"bbox": PUGET_SOUND_BBOX, "status[]": [0], **WIDE_DATE_RANGE}
    )

    assert response.status_code == 401


def test_sightings_rejects_stale_token_after_reauth(client):
    old_token = client.post(
        "/auth/token", json={"client_id": mock_server.MOCK_CLIENT_ID, "client_secret": mock_server.MOCK_CLIENT_SECRET}
    ).json()["access_token"]
    # A fresh /auth/token call rotates the single "current" token — the old one no longer works.
    client.post("/auth/token", json={"client_id": mock_server.MOCK_CLIENT_ID, "client_secret": mock_server.MOCK_CLIENT_SECRET})

    response = client.get(
        "/sightings",
        params={"bbox": PUGET_SOUND_BBOX, "status[]": [0], **WIDE_DATE_RANGE},
        headers={"Authorization": f"Bearer {old_token}"},
    )

    assert response.status_code == 401


def test_sightings_filters_by_bbox(client):
    response = _authed_get(client, bbox=PUGET_SOUND_BBOX, **{"status[]": [0, 1, 2, 3]}, **WIDE_DATE_RANGE)

    assert response.status_code == 200
    ids = {r["id"] for r in response.json()["results"]}
    # 116184 (Puget Sound) and the three synthesized in-region siblings are inside the box;
    # 116308 (Panama), 116315 (west of -123.3), and 112793 (near 0,0) are outside it.
    assert ids == {116184, 900001, 900002, 900003}


def test_sightings_filters_by_status(client):
    response = _authed_get(client, bbox="-180,-90,180,90", **{"status[]": [3]}, **WIDE_DATE_RANGE)

    assert [r["id"] for r in response.json()["results"]] == [112793]


def test_sightings_filters_by_date_range(client):
    response = _authed_get(
        client, bbox="-180,-90,180,90", **{"status[]": [0, 1, 2, 3]}, start="2026-08-29", end="2026-08-29"
    )

    assert [r["id"] for r in response.json()["results"]] == [112793]


def test_sightings_paginates(client):
    response = _authed_get(client, bbox="-180,-90,180,90", **{"status[]": [0, 1, 2, 3]}, per_page=2, page=1, **WIDE_DATE_RANGE)

    body = response.json()
    assert body["total"] == 7
    assert body["pages"] == 4
    assert len(body["results"]) == 2


def test_sightings_response_shape_matches_real_example():
    client = TestClient(mock_server.app)
    response = _authed_get(client, bbox="-180,-90,180,90", **{"status[]": [0]}, **WIDE_DATE_RANGE)

    body = response.json()
    assert set(body.keys()) == {"success", "total", "page", "per_page", "pages", "results"}
    result = next(r for r in body["results"] if r["id"] == 116308)
    assert result == mock_server.REAL_EXAMPLES[0]


def test_advance_increments_moderated_capped_at_three():
    initial = mock_server._fixtures[116184]["moderated"]
    assert initial == 2

    client = TestClient(mock_server.app)
    first = client.post("/_mock/advance").json()
    second = client.post("/_mock/advance").json()

    assert {"id": 116184, "moderated": 3} in first["changed"]
    assert not any(c["id"] == 116184 for c in second["changed"])  # already at the cap


def test_reset_restores_original_moderated_values():
    client = TestClient(mock_server.app)
    client.post("/_mock/advance")
    assert mock_server._fixtures[116184]["moderated"] == 3

    client.post("/_mock/reset")

    assert mock_server._fixtures[116184]["moderated"] == 2
