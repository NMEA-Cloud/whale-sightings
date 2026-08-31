from urllib.parse import parse_qs

import httpx

from app.ingest.config import IngestSettings
from app.ingest.hydra_token_client import HydraTokenClient


def make_settings(**overrides) -> IngestSettings:
    return IngestSettings(
        whale_alert_client_id="wa-id",
        whale_alert_client_secret="wa-secret",
        ingest_hydra_client_id="hydra-id",
        ingest_hydra_client_secret="hydra-secret",
        **overrides,
    )


def test_get_token_posts_form_encoded_client_credentials_request():
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"access_token": "tok-1", "expires_in": 900})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    token_client = HydraTokenClient(make_settings(), client)

    token = token_client.get_token()

    assert token == "tok-1"
    assert len(requests) == 1
    body = parse_qs(requests[0].content.decode())
    assert body["grant_type"] == ["client_credentials"]
    assert body["client_id"] == ["hydra-id"]
    assert body["client_secret"] == ["hydra-secret"]
    assert body["scope"] == ["sightings:ingest"]
    assert body["audience"] == ["https://api.dev.wombat-sightings.org:8000"]


def test_get_token_caches_until_near_expiry():
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(200, json={"access_token": f"tok-{call_count}", "expires_in": 900})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    token_client = HydraTokenClient(make_settings(), client)

    first = token_client.get_token()
    second = token_client.get_token()

    assert first == second == "tok-1"
    assert call_count == 1


def test_get_token_re_fetches_after_expiry():
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        # Expires almost immediately (expires_in - 60s margin means this is already
        # "expired" from get_token()'s point of view on the very next call).
        return httpx.Response(200, json={"access_token": f"tok-{call_count}", "expires_in": 30})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    token_client = HydraTokenClient(make_settings(), client)

    first = token_client.get_token()
    second = token_client.get_token()

    assert first == "tok-1"
    assert second == "tok-2"
    assert call_count == 2
