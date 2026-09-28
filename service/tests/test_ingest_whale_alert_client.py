import json

import httpx

from app.ingest.config import IngestSettings
import pytest

from app.ingest import whale_alert_client
from app.ingest.whale_alert_client import ALL_STATUSES, TOKEN_RENEWAL_MARGIN_SECONDS, WhaleAlertClient


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


def test_search_sightings_sends_status_array_bbox_test_flag_and_bearer_token():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/auth/token"):
            return _token_response()
        assert request.headers["authorization"] == "Bearer wa-tok"
        assert request.url.params.get_list("status[]") == ["0", "1", "2", "3"]
        assert request.url.params["bbox"] == "-123.3,47.0,-122.0,48.8"
        assert request.url.params["start"] == "2026-08-01"
        assert request.url.params["end"] == "2026-08-31"
        # Normal *and* test sightings — see INCLUDE_TEST_SIGHTINGS.
        assert request.url.params["test"] == "1"
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


def _search(wa_client):
    return wa_client.search_sightings(statuses=ALL_STATUSES, bbox="x", start="2026-08-01", end="2026-08-31", page=1)


_PAGE = {"success": True, "total": 0, "page": 1, "per_page": 100, "pages": 1, "results": []}


def test_search_retries_once_with_a_fresh_token_after_401():
    tokens_issued = []
    searches = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/auth/token"):
            token = f"tok-{len(tokens_issued) + 1}"
            tokens_issued.append(token)
            return httpx.Response(200, json={"access_token": token, "expires_in": 3600})
        searches.append(request.headers["authorization"])
        # Whale Alert has already expired the first token, whatever our clock says.
        if request.headers["authorization"] == "Bearer tok-1":
            return httpx.Response(401)
        return httpx.Response(200, json=_PAGE)

    wa_client = WhaleAlertClient(make_settings(), httpx.Client(transport=httpx.MockTransport(handler)))

    assert _search(wa_client) == _PAGE
    assert tokens_issued == ["tok-1", "tok-2"]
    assert searches == ["Bearer tok-1", "Bearer tok-2"]


def test_search_raises_when_a_fresh_token_is_also_rejected():
    searches = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/auth/token"):
            return _token_response()
        searches.append(request)
        return httpx.Response(401)

    wa_client = WhaleAlertClient(make_settings(), httpx.Client(transport=httpx.MockTransport(handler)))

    with pytest.raises(httpx.HTTPStatusError):
        _search(wa_client)
    assert len(searches) == 2  # one retry, not a loop


def test_cached_token_is_renewed_five_minutes_before_expiry(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(whale_alert_client.time, "monotonic", lambda: now[0])
    token_requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        token_requests.append(request)
        return httpx.Response(200, json={"access_token": f"tok-{len(token_requests)}", "expires_in": 3600})

    wa_client = WhaleAlertClient(make_settings(), httpx.Client(transport=httpx.MockTransport(handler)))

    assert wa_client._get_token() == "tok-1"
    now[0] += 3600 - TOKEN_RENEWAL_MARGIN_SECONDS - 1  # just inside the renewal margin
    assert wa_client._get_token() == "tok-1"
    now[0] += 2  # past it
    assert wa_client._get_token() == "tok-2"
    assert TOKEN_RENEWAL_MARGIN_SECONDS == 300
