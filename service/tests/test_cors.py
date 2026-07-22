from fastapi.testclient import TestClient

from app.main import create_app


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
