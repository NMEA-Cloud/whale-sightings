import pytest
from fastapi import WebSocketDisconnect
from fastapi.testclient import TestClient

from app.auth import require_admin, require_admin_or_ingest
from app.deps import get_mqtt_publisher, get_store
from app.main import create_app
from tests.test_sightings_api import sample_payload_dict


@pytest.fixture
def client(store, mqtt_publisher):
    """Deliberately does NOT override get_ws_broadcaster like the shared conftest.py
    fixture of the same name does — these tests need the real ConnectionWsBroadcaster so
    the /sightings/ws route and create_sighting/delete_sighting share one broadcaster
    instance (app.state.ws_broadcaster), since that's the actual thing under test here."""
    app = create_app()
    app.dependency_overrides[get_store] = lambda: store
    app.dependency_overrides[get_mqtt_publisher] = lambda: mqtt_publisher
    app.dependency_overrides[require_admin] = lambda: {"sub": "test-admin", "ext": {"role": "admin"}}
    app.dependency_overrides[require_admin_or_ingest] = lambda: {"sub": "test-admin", "ext": {"role": "admin"}}
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_ws_client_receives_created_and_deleted_events(client):
    with client.websocket_connect("/sightings/ws", headers={"Origin": "http://localhost:8080"}) as ws:
        body = client.post("/sightings", json=sample_payload_dict()).json()
        created_message = ws.receive_json()

        client.delete(f"/sightings/{body['id']}")
        deleted_message = ws.receive_json()

    resource_url = f"https://localhost:8000/sightings/{body['id']}"
    assert created_message == {"event": "created", "sighting": resource_url}
    assert deleted_message == {"event": "deleted", "sighting": resource_url}


def test_ws_rejects_disallowed_origin(client):
    # websocket_connect's __enter__ raises WebSocketDisconnect directly when the server
    # closes before completing the handshake, rather than yielding a session to receive
    # the close message from — this is that close, not a connection failure.
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect("/sightings/ws", headers={"Origin": "http://evil.example.com"}):
            pass

    assert exc_info.value.code == 1008


def test_ws_allows_missing_origin(client):
    # Non-browser clients (mosquitto_sub-style CLI tools, scripts) don't send an Origin
    # header at all and aren't subject to the cross-site-hijacking threat model
    # origin-checking exists for — only a *present but disallowed* Origin should be
    # rejected, not a missing one. See ws.origin_allowed()'s docstring.
    with client.websocket_connect("/sightings/ws") as ws:
        body = client.post("/sightings", json=sample_payload_dict()).json()
        message = ws.receive_json()

    assert message == {"event": "created", "sighting": f"https://localhost:8000/sightings/{body['id']}"}

    client.delete(f"/sightings/{body['id']}")
