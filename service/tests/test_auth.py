from datetime import datetime, timedelta, timezone

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from jwt import PyJWKClient

from app.deps import get_mqtt_publisher, get_store
from app.main import create_app
from tests.test_sightings_api import sample_payload_dict

ISSUER = "https://localhost:4444"
AUDIENCE = "https://localhost:8000"

_private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_public_key = _private_key.public_key()


def _make_token(
    *,
    role: str | None = "admin",
    audience: str = AUDIENCE,
    issuer: str = ISSUER,
    expired: bool = False,
) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "iss": issuer,
        "aud": audience,
        "sub": "admin",
        "iat": now,
        "exp": now - timedelta(minutes=1) if expired else now + timedelta(minutes=15),
    }
    if role is not None:
        payload["ext"] = {"role": role}
    return jwt.encode(payload, _private_key, algorithm="RS256")


class _FakeSigningKey:
    def __init__(self, key):
        self.key = key


@pytest.fixture(autouse=True)
def _fake_jwks(monkeypatch):
    # Mirrors how test_cors.py/test_sightings_api.py avoid hitting real Valkey/MQTT — this
    # avoids a real network call to Hydra's JWKS endpoint during tests.
    monkeypatch.setattr(
        PyJWKClient, "get_signing_key_from_jwt", lambda self, token: _FakeSigningKey(_public_key)
    )


@pytest.fixture
def auth_client(store, mqtt_publisher):
    app = create_app()
    app.dependency_overrides[get_store] = lambda: store
    app.dependency_overrides[get_mqtt_publisher] = lambda: mqtt_publisher
    # Deliberately no override for require_admin — this is what's under test here.
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_delete_without_token_returns_401_with_challenge(auth_client):
    response = auth_client.delete("/sightings/00000000-0000-0000-0000-000000000000")

    assert response.status_code == 401
    www_authenticate = response.headers["www-authenticate"]
    assert 'error="invalid_token"' in www_authenticate
    assert 'resource_metadata="https://localhost:8000/.well-known/oauth-protected-resource"' in www_authenticate


def test_delete_with_valid_admin_token_returns_204(auth_client):
    body = auth_client.post("/sightings", json=sample_payload_dict()).json()

    response = auth_client.delete(
        f"/sightings/{body['id']}", headers={"Authorization": f"Bearer {_make_token()}"}
    )

    assert response.status_code == 204


def test_delete_with_token_missing_admin_role_returns_403(auth_client):
    response = auth_client.delete(
        "/sightings/00000000-0000-0000-0000-000000000000",
        headers={"Authorization": f"Bearer {_make_token(role='viewer')}"},
    )

    assert response.status_code == 403
    assert 'error="insufficient_scope"' in response.headers["www-authenticate"]


def test_delete_with_expired_token_returns_401(auth_client):
    response = auth_client.delete(
        "/sightings/00000000-0000-0000-0000-000000000000",
        headers={"Authorization": f"Bearer {_make_token(expired=True)}"},
    )

    assert response.status_code == 401
    assert 'error="invalid_token"' in response.headers["www-authenticate"]


def test_delete_with_wrong_audience_returns_401(auth_client):
    response = auth_client.delete(
        "/sightings/00000000-0000-0000-0000-000000000000",
        headers={"Authorization": f"Bearer {_make_token(audience='https://example.org')}"},
    )

    assert response.status_code == 401


def test_post_and_get_routes_remain_unauthenticated(auth_client):
    create_response = auth_client.post("/sightings", json=sample_payload_dict())
    assert create_response.status_code == 201

    assert auth_client.get("/sightings").status_code == 200
    assert auth_client.get("/sightings/stats").status_code == 200
