import httpx
from fastapi.testclient import TestClient

from app.main import create_app
from tests.test_sightings_sse import _RealServer


def _preflight(app, origin: str):
    with TestClient(app) as client:
        return client.options(
            "/sightings",
            headers={"Origin": origin, "Access-Control-Request-Method": "GET"},
        )


def test_cors_allows_origin_matching_regex(monkeypatch):
    monkeypatch.setenv("CORS_ORIGIN_REGEX", r"^http://192\.168\.0\.\d{1,3}:8080$")
    app = create_app()

    response = _preflight(app, "http://192.168.0.42:8080")

    assert response.headers["access-control-allow-origin"] == "http://192.168.0.42:8080"


def test_cors_rejects_origin_matching_neither_list_nor_regex(monkeypatch):
    monkeypatch.setenv("CORS_ORIGIN_REGEX", r"^http://192\.168\.0\.\d{1,3}:8080$")
    app = create_app()

    response = _preflight(app, "http://evil.example.com")

    assert "access-control-allow-origin" not in response.headers


def test_cors_still_allows_exact_list_when_regex_is_unset():
    app = create_app()

    response = _preflight(app, "http://localhost:8080")

    assert response.headers["access-control-allow-origin"] == "http://localhost:8080"


def test_cors_allows_sse_accept_header_on_simple_request():
    # Accept: text/event-stream doesn't trigger a CORS preflight (it's one of the "simple
    # request" allowed headers), so this asserts on the real GET response's CORS headers
    # rather than an OPTIONS preflight like the tests above. Needs a real server (see
    # _RealServer's docstring in test_sightings_sse.py) — the SSE response never completes
    # on its own, and httpx's in-process ASGITransport (what TestClient uses) can't return
    # anything for a request until the whole ASGI app call finishes, so a plain TestClient
    # request here would hang forever.
    app = create_app()
    with _RealServer(app) as base_url, httpx.Client(timeout=5) as client:
        with client.stream(
            "GET", f"{base_url}/sightings", headers={"Origin": "http://localhost:8080", "Accept": "text/event-stream"}
        ) as response:
            assert response.headers["access-control-allow-origin"] == "http://localhost:8080"
