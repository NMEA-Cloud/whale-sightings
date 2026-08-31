import httpx

from app.ingest.config import IngestSettings
from app.ingest.hydra_token_client import HydraTokenClient
from app.ingest.service_client import ServiceClient


def make_settings(**overrides) -> IngestSettings:
    return IngestSettings(
        whale_alert_client_id="wa-id",
        whale_alert_client_secret="wa-secret",
        ingest_hydra_client_id="hydra-id",
        ingest_hydra_client_secret="hydra-secret",
        **overrides,
    )


def _make_client(handler) -> tuple[ServiceClient, httpx.Client]:
    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    settings = make_settings()
    token_client = HydraTokenClient(settings, http_client)
    return ServiceClient(settings, http_client, token_client), http_client


def test_get_by_source_returns_none_on_404():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    service, _ = _make_client(handler)

    assert service.get_by_source("116308") is None


def test_get_by_source_sends_no_auth_header():
    seen_headers = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen_headers.update(request.headers)
        return httpx.Response(200, json={"id": "abc"})

    service, _ = _make_client(handler)
    service.get_by_source("116308")

    assert "authorization" not in seen_headers


def test_create_sends_bearer_token_from_hydra():
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/oauth2/token"):
            return httpx.Response(200, json={"access_token": "svc-tok", "expires_in": 900})
        requests.append(request)
        return httpx.Response(201, json={"id": "new-1"})

    service, _ = _make_client(handler)
    result = service.create({"sighting": {}})

    assert result == {"id": "new-1"}
    assert requests[0].headers["authorization"] == "Bearer svc-tok"


def test_delete_treats_404_as_success():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/oauth2/token"):
            return httpx.Response(200, json={"access_token": "svc-tok", "expires_in": 900})
        return httpx.Response(404)

    service, _ = _make_client(handler)

    service.delete("00000000-0000-0000-0000-000000000000")  # must not raise
