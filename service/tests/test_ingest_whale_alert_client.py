import json

import httpx

from app.ingest.config import IngestSettings
from app.ingest.whale_alert_client import ALL_STATUSES, WhaleAlertClient


def make_settings(**overrides) -> IngestSettings:
    return IngestSettings(
        whale_alert_client_id="wa-id",
        whale_alert_client_secret="wa-secret",
        ingest_hydra_client_id="hydra-id",
        ingest_hydra_client_secret="hydra-secret",
        **overrides,
    )


def _token_response() -> httpx.Response:
    return httpx.Response(200, json={"access_token": "wa-tok", "expires_in": 3600})


def test_get_token_posts_json_body_not_form_encoded():
    # Confirmed against a real saved example (see mapping.py's module docstring): Whale
    # Alert's own /auth/token expects a JSON body, unlike our own Hydra's standard
    # form-encoded token request (see test_ingest_hydra_token_client.py).
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return _token_response()

    client = httpx.Client(transport=httpx.MockTransport(handler))
    wa_client = WhaleAlertClient(make_settings(), client)

    token = wa_client._get_token()

    assert token == "wa-tok"
    assert requests[0].headers["content-type"] == "application/json"
    assert json.loads(requests[0].content) == {"client_id": "wa-id", "client_secret": "wa-secret"}


def test_search_sightings_sends_status_array_bbox_and_bearer_token():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/auth/token"):
            return _token_response()
        assert request.headers["authorization"] == "Bearer wa-tok"
        assert request.url.params.get_list("status[]") == ["0", "1", "2", "3"]
        assert request.url.params["bbox"] == "-123.3,47.0,-122.0,48.8"
        assert request.url.params["start"] == "2026-08-01"
        assert request.url.params["end"] == "2026-08-31"
        return httpx.Response(
            200,
            json={"success": True, "total": 1, "page": 1, "per_page": 100, "pages": 1, "results": [{"id": 1}]},
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    wa_client = WhaleAlertClient(make_settings(), client)

    body = wa_client.search_sightings(
        statuses=ALL_STATUSES,
        bbox="-123.3,47.0,-122.0,48.8",
        start="2026-08-01",
        end="2026-08-31",
        page=1,
    )

    assert body["results"] == [{"id": 1}]


def test_iter_all_sightings_paginates_through_every_page():
    seen_pages = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/auth/token"):
            return _token_response()
        page = int(request.url.params["page"])
        seen_pages.append(page)
        return httpx.Response(
            200,
            json={
                "success": True,
                "total": 2,
                "page": page,
                "per_page": 1,
                "pages": 2,
                "results": [{"id": page}],
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    wa_client = WhaleAlertClient(make_settings(), client)

    results = list(
        wa_client.iter_all_sightings(statuses=ALL_STATUSES, bbox="x", start="2026-08-01", end="2026-08-31")
    )

    assert [r["id"] for r in results] == [1, 2]
    assert seen_pages == [1, 2]
