from datetime import datetime, timedelta, timezone

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import Depends
from fastapi.testclient import TestClient
from jwt import PyJWKClient

from app.auth import require_admin_or_ingest, require_ingest, try_require_ingest
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


def _make_ingest_token(
    *, scopes: list[str] | None = ["sightings:ingest"], expired: bool = False, scope_claim: str = "scp"
) -> str:
    # A client_credentials token, unlike _make_token's browser/consent-flow shape: no `ext`
    # claim at all (there's no login-consent step to stamp one). scope_claim="scp" (a JSON
    # array) matches what a real Ory Hydra JWT access token actually carries — confirmed by
    # minting one for real via scripts/register-hydra-ingest-client.sh and decoding it,
    # since RFC 9068's space-delimited `scope` string (scope_claim="scope") turned out not
    # to be what Hydra emits.
    now = datetime.now(timezone.utc)
    payload = {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "sub": "whale-sightings-ingest",
        "iat": now,
        "exp": now - timedelta(minutes=1) if expired else now + timedelta(minutes=15),
    }
    if scopes is not None:
        payload[scope_claim] = scopes if scope_claim == "scp" else " ".join(scopes)
    return jwt.encode(payload, _private_key, algorithm="RS256")


def _make_peer_token(*, scopes: list[str] | None = ["peer:write"], client_id: str = "whale-sightings-peer") -> str:
    # Same client_credentials shape as _make_ingest_token, but also sets `client_id` (a real
    # Hydra token carries this alongside `sub` for client_credentials grants — confirmed
    # against a real minted token) since create_sighting derives source.peer_id from it.
    now = datetime.now(timezone.utc)
    payload = {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "sub": client_id,
        "client_id": client_id,
        "iat": now,
        "exp": now + timedelta(minutes=15),
    }
    if scopes is not None:
        payload["scp"] = scopes
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


# require_scope()/require_ingest/try_require_ingest/require_admin_or_ingest aren't wired
# into any real route yet (that lands in Phase 4) — exercised here via test-only routes
# attached to the real app, so the JWKS/lifespan wiring matches how they'll actually run.
@pytest.fixture
def scope_test_client(store, mqtt_publisher):
    app = create_app()
    app.dependency_overrides[get_store] = lambda: store
    app.dependency_overrides[get_mqtt_publisher] = lambda: mqtt_publisher

    @app.get("/_test/require-ingest")
    def _require_ingest_route(claims: dict = Depends(require_ingest)):
        return claims

    @app.get("/_test/try-require-ingest")
    def _try_require_ingest_route(claims: dict | None = Depends(try_require_ingest)):
        return {"claims": claims}

    @app.get("/_test/require-admin-or-ingest")
    def _require_admin_or_ingest_route(claims: dict = Depends(require_admin_or_ingest)):
        return claims

    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_require_ingest_accepts_valid_ingest_scope(scope_test_client):
    response = scope_test_client.get(
        "/_test/require-ingest", headers={"Authorization": f"Bearer {_make_ingest_token()}"}
    )

    assert response.status_code == 200


def test_require_ingest_rejects_token_missing_the_scope(scope_test_client):
    response = scope_test_client.get(
        "/_test/require-ingest",
        headers={"Authorization": f"Bearer {_make_ingest_token(scopes=['sightings:read'])}"},
    )

    assert response.status_code == 403
    assert 'error="insufficient_scope"' in response.headers["www-authenticate"]


def test_require_ingest_rejects_missing_token(scope_test_client):
    response = scope_test_client.get("/_test/require-ingest")

    assert response.status_code == 401


def test_try_require_ingest_returns_none_without_a_token(scope_test_client):
    response = scope_test_client.get("/_test/try-require-ingest")

    assert response.status_code == 200
    assert response.json() == {"claims": None}


def test_try_require_ingest_returns_claims_with_a_valid_token(scope_test_client):
    response = scope_test_client.get(
        "/_test/try-require-ingest", headers={"Authorization": f"Bearer {_make_ingest_token()}"}
    )

    assert response.status_code == 200
    assert response.json()["claims"]["scp"] == ["sightings:ingest"]


def test_require_ingest_accepts_space_delimited_scope_string(scope_test_client):
    # Regression coverage for token_scopes()'s fallback: not every IdP necessarily matches
    # Hydra's `scp`-array shape — RFC 9068's plain `scope` string should also work.
    response = scope_test_client.get(
        "/_test/require-ingest",
        headers={
            "Authorization": f"Bearer {_make_ingest_token(scopes=['sightings:ingest'], scope_claim='scope')}"
        },
    )

    assert response.status_code == 200


def test_require_admin_or_ingest_accepts_admin_token(scope_test_client):
    response = scope_test_client.get(
        "/_test/require-admin-or-ingest", headers={"Authorization": f"Bearer {_make_token()}"}
    )

    assert response.status_code == 200


def test_require_admin_or_ingest_accepts_ingest_token(scope_test_client):
    response = scope_test_client.get(
        "/_test/require-admin-or-ingest", headers={"Authorization": f"Bearer {_make_ingest_token()}"}
    )

    assert response.status_code == 200


def test_require_admin_or_ingest_rejects_token_with_neither(scope_test_client):
    response = scope_test_client.get(
        "/_test/require-admin-or-ingest",
        headers={"Authorization": f"Bearer {_make_ingest_token(scopes=['sightings:read'])}"},
    )

    assert response.status_code == 403


# Phase 4: the ingest scope wired into real routes (create/moderation/delete/by-source),
# exercised against the real app (auth_client, no dependency overrides) rather than the
# test-only routes above.
def test_ingest_create_tags_source_and_moderation_status(auth_client):
    payload = sample_payload_dict()
    payload["source_upstream_id"] = "116308"
    payload["source_moderation_status"] = "confirmed"

    response = auth_client.post(
        "/sightings", json=payload, headers={"Authorization": f"Bearer {_make_ingest_token()}"}
    )

    assert response.status_code == 201
    body = response.json()
    assert body["source"] == {"type": "whale_alert", "peer_id": None, "upstream_id": "116308"}
    assert body["moderation_status"] == "confirmed"


def test_unauthenticated_create_ignores_source_fields(auth_client):
    # Anti-spoofing: source_upstream_id/source_moderation_status are only honored when the
    # caller actually authenticates via the ingest scope — a plain public-form POST can send
    # them (they're just optional fields on SightingCreate) but they're silently ignored.
    payload = sample_payload_dict()
    payload["source_upstream_id"] = "116308"
    payload["source_moderation_status"] = "confirmed"

    response = auth_client.post("/sightings", json=payload)

    assert response.status_code == 201
    body = response.json()
    assert body["source"]["type"] == "local"
    assert body["moderation_status"] is None


def test_get_by_source_not_found_returns_404(auth_client):
    response = auth_client.get("/sightings/by-source/whale_alert/does-not-exist")

    assert response.status_code == 404


def test_get_by_source_found_returns_record(auth_client):
    payload = sample_payload_dict()
    payload["source_upstream_id"] = "116308"
    created = auth_client.post(
        "/sightings", json=payload, headers={"Authorization": f"Bearer {_make_ingest_token()}"}
    ).json()

    response = auth_client.get("/sightings/by-source/whale_alert/116308")

    assert response.status_code == 200
    assert response.json()["id"] == created["id"]


def test_patch_moderation_updates_status_and_fires_updated_events(auth_client, mqtt_publisher):
    payload = sample_payload_dict()
    payload["source_upstream_id"] = "116308"
    created = auth_client.post(
        "/sightings", json=payload, headers={"Authorization": f"Bearer {_make_ingest_token()}"}
    ).json()

    with auth_client.websocket_connect("/sightings/ws", headers={"Origin": "http://localhost:8080"}) as ws:
        response = auth_client.patch(
            f"/sightings/{created['id']}/moderation",
            json={"moderation_status": "confirmed"},
            headers={"Authorization": f"Bearer {_make_ingest_token()}"},
        )
        ws_message = ws.receive_json()

    assert response.status_code == 200
    assert response.json()["moderation_status"] == "confirmed"
    assert ws_message["event"] == "updated"
    assert ("updated", created["id"]) in mqtt_publisher.calls


def test_patch_moderation_on_local_sighting_returns_409(auth_client):
    created = auth_client.post("/sightings", json=sample_payload_dict()).json()

    response = auth_client.patch(
        f"/sightings/{created['id']}/moderation",
        json={"moderation_status": "confirmed"},
        headers={"Authorization": f"Bearer {_make_ingest_token()}"},
    )

    assert response.status_code == 409


def test_patch_moderation_on_unknown_id_returns_404(auth_client):
    response = auth_client.patch(
        "/sightings/00000000-0000-0000-0000-000000000000/moderation",
        json={"moderation_status": "confirmed"},
        headers={"Authorization": f"Bearer {_make_ingest_token()}"},
    )

    assert response.status_code == 404


def test_patch_moderation_without_ingest_scope_returns_403(auth_client):
    created = auth_client.post(
        "/sightings",
        json={**sample_payload_dict(), "source_upstream_id": "116308"},
        headers={"Authorization": f"Bearer {_make_ingest_token()}"},
    ).json()

    response = auth_client.patch(
        f"/sightings/{created['id']}/moderation",
        json={"moderation_status": "confirmed"},
        headers={"Authorization": f"Bearer {_make_token()}"},
    )

    assert response.status_code == 403


def test_ingest_delete_on_non_whale_alert_record_returns_403(auth_client):
    created = auth_client.post("/sightings", json=sample_payload_dict()).json()

    response = auth_client.delete(
        f"/sightings/{created['id']}", headers={"Authorization": f"Bearer {_make_ingest_token()}"}
    )

    assert response.status_code == 403


def test_ingest_delete_on_whale_alert_record_returns_204(auth_client):
    payload = sample_payload_dict()
    payload["source_upstream_id"] = "116308"
    created = auth_client.post(
        "/sightings", json=payload, headers={"Authorization": f"Bearer {_make_ingest_token()}"}
    ).json()

    response = auth_client.delete(
        f"/sightings/{created['id']}", headers={"Authorization": f"Bearer {_make_ingest_token()}"}
    )

    assert response.status_code == 204


def test_admin_delete_on_whale_alert_record_returns_403(auth_client):
    # Whale Alert is the single source of truth for its own data — only the ingest
    # connector (acting on Whale Alert's own moderation status) may remove these, never a
    # human admin, since an admin-initiated delete would just get silently resurrected by
    # the connector's next poll cycle anyway.
    payload = sample_payload_dict()
    payload["source_upstream_id"] = "116308"
    created = auth_client.post(
        "/sightings", json=payload, headers={"Authorization": f"Bearer {_make_ingest_token()}"}
    ).json()

    response = auth_client.delete(
        f"/sightings/{created['id']}", headers={"Authorization": f"Bearer {_make_token()}"}
    )

    assert response.status_code == 403


def test_peer_create_tags_source_with_peer_id_from_token(auth_client):
    response = auth_client.post(
        "/sightings",
        json=sample_payload_dict(),
        headers={"Authorization": f"Bearer {_make_peer_token(client_id='whale-sightings-peer')}"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["source"] == {"type": "peer", "peer_id": "whale-sightings-peer", "upstream_id": None}


def test_peer_create_ignores_body_supplied_upstream_id(auth_client):
    # source_upstream_id/source_moderation_status are ingest-only fields — a peer caller
    # sending them shouldn't do anything (peer_id always comes from the token, never body).
    payload = sample_payload_dict()
    payload["source_upstream_id"] = "should-be-ignored"

    response = auth_client.post(
        "/sightings", json=payload, headers={"Authorization": f"Bearer {_make_peer_token()}"}
    )

    body = response.json()
    assert body["source"]["upstream_id"] is None


def test_peer_sourced_response_has_no_delete_link(auth_client):
    response = auth_client.post(
        "/sightings", json=sample_payload_dict(), headers={"Authorization": f"Bearer {_make_peer_token()}"}
    )

    assert "delete" not in response.json()["_links"]


def test_admin_delete_on_peer_record_returns_403(auth_client):
    created = auth_client.post(
        "/sightings", json=sample_payload_dict(), headers={"Authorization": f"Bearer {_make_peer_token()}"}
    ).json()

    response = auth_client.delete(
        f"/sightings/{created['id']}", headers={"Authorization": f"Bearer {_make_token()}"}
    )

    assert response.status_code == 403


def test_ingest_delete_on_peer_record_returns_403(auth_client):
    created = auth_client.post(
        "/sightings", json=sample_payload_dict(), headers={"Authorization": f"Bearer {_make_peer_token()}"}
    ).json()

    response = auth_client.delete(
        f"/sightings/{created['id']}", headers={"Authorization": f"Bearer {_make_ingest_token()}"}
    )

    assert response.status_code == 403


def test_peer_token_cannot_delete_any_sighting(auth_client):
    # require_admin_or_ingest doesn't accept a peer-scoped-only token at all — it's neither
    # an admin token (no ext.role) nor an ingest one (wrong scope) — so a bare peer token is
    # rejected before delete_sighting's own source-based checks ever run, even against a
    # perfectly ordinary local sighting.
    created = auth_client.post("/sightings", json=sample_payload_dict()).json()

    response = auth_client.delete(
        f"/sightings/{created['id']}", headers={"Authorization": f"Bearer {_make_peer_token()}"}
    )

    assert response.status_code == 403
