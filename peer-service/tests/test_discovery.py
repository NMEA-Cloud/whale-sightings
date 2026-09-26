"""discover() -> discover_auth() -> discover_with_retry() against a mocked whale-sightings
service and a mocked Hydra (httpx.MockTransport) — the whole bootstrap chain peer-service
runs at startup, with no hardcoded endpoint beyond config.API_BASE."""

from __future__ import annotations

import httpx
import pytest

import config
import main

API_BASE = "https://api.example.org:8000"
ISSUER = "https://auth.example.org:4444"

ROOT_DOCUMENT = {
    "@context": {"@vocab": "https://whale-sightings.org/ns#"},
    "@type": "Service",
    "_links": {
        "self": {"href": f"{API_BASE}/"},
        # Deliberately not "/sightings" — proves the href is read from the document, not
        # assumed.
        "sightings:create": {"href": f"{API_BASE}/v2/reports", "method": "POST", "scope": "peer:write"},
        "sightings:live-sync": {"href": "wss://api.example.org:8000/v2/reports/ws"},
        "oauth:protected-resource": {"href": f"{API_BASE}/.well-known/oauth-protected-resource"},
    },
}

PROTECTED_RESOURCE = {"resource": API_BASE, "authorization_servers": [ISSUER]}

OIDC_METADATA = {"issuer": ISSUER, "token_endpoint": f"{ISSUER}/oauth2/token"}


def make_handler(requests_seen: list[httpx.Request], internal_base: str | None = None):
    oidc_host = internal_base or ISSUER

    def handler(request: httpx.Request) -> httpx.Response:
        requests_seen.append(request)
        url = str(request.url)
        if url in (API_BASE, f"{API_BASE}/"):
            return httpx.Response(200, json=ROOT_DOCUMENT)
        if url == f"{API_BASE}/.well-known/oauth-protected-resource":
            return httpx.Response(200, json=PROTECTED_RESOURCE)
        if url == f"{oidc_host}/.well-known/openid-configuration":
            return httpx.Response(200, json=OIDC_METADATA)
        return httpx.Response(404)

    return handler


@pytest.fixture(autouse=True)
def _config(monkeypatch):
    monkeypatch.setattr(config, "API_BASE", API_BASE)
    monkeypatch.setattr(config, "HYDRA_INTERNAL_BASE_URL", None)


def test_discover_reads_links_by_rel_and_asks_for_jsonld():
    seen: list[httpx.Request] = []
    with httpx.Client(transport=httpx.MockTransport(make_handler(seen))) as client:
        discovered = main.discover(client)

    assert discovered == {
        "create": f"{API_BASE}/v2/reports",
        "create_scope": "peer:write",
        "live_sync": "wss://api.example.org:8000/v2/reports/ws",
        "protected_resource": f"{API_BASE}/.well-known/oauth-protected-resource",
    }
    assert seen[0].headers["accept"] == "application/ld+json, application/json"


def test_discover_auth_follows_protected_resource_to_token_endpoint():
    seen: list[httpx.Request] = []
    with httpx.Client(transport=httpx.MockTransport(make_handler(seen))) as client:
        auth = main.discover_auth(client, f"{API_BASE}/.well-known/oauth-protected-resource")

    assert auth == {"token_url": f"{ISSUER}/oauth2/token", "audience": API_BASE}
    assert [str(r.url) for r in seen] == [
        f"{API_BASE}/.well-known/oauth-protected-resource",
        f"{ISSUER}/.well-known/openid-configuration",
    ]


def test_discover_auth_rewrites_to_internal_hydra_address(monkeypatch):
    internal = "http://hydra:4444"
    monkeypatch.setattr(config, "HYDRA_INTERNAL_BASE_URL", internal)
    seen: list[httpx.Request] = []
    with httpx.Client(transport=httpx.MockTransport(make_handler(seen, internal_base=internal))) as client:
        auth = main.discover_auth(client, f"{API_BASE}/.well-known/oauth-protected-resource")

    # Scheme and host swapped for the internal address; Hydra's own path kept.
    assert auth["token_url"] == "http://hydra:4444/oauth2/token"
    assert str(seen[1].url) == f"{internal}/.well-known/openid-configuration"


def test_discover_with_retry_retries_until_service_is_up(monkeypatch):
    sleeps: list[float] = []
    monkeypatch.setattr(main.time, "sleep", sleeps.append)
    seen: list[httpx.Request] = []
    healthy = make_handler(seen)
    attempts = {"count": 0}

    def flaky(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        if attempts["count"] <= 2:
            raise httpx.ConnectError("service still starting", request=request)
        return healthy(request)

    with httpx.Client(transport=httpx.MockTransport(flaky)) as client:
        discovered = main.discover_with_retry(client)

    assert sleeps == [3, 3]
    assert discovered["create"] == f"{API_BASE}/v2/reports"
    assert discovered["token_url"] == f"{ISSUER}/oauth2/token"
    assert discovered["audience"] == API_BASE
