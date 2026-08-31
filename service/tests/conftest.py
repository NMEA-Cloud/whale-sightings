import fakeredis
import pytest
from fastapi.testclient import TestClient

from app.auth import require_admin, require_admin_or_ingest
from app.deps import get_mqtt_publisher, get_store, get_ws_broadcaster
from app.main import create_app
from app.mqtt import MqttPublisher
from app.store.valkey_store import ValkeySightingStore
from app.ws import WsBroadcaster


class FakeMqttPublisher(MqttPublisher):
    """Records publish() calls instead of talking to a real broker."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def publish(self, event, sighting_id: str) -> None:
        self.calls.append((event, sighting_id))


class FakeWsBroadcaster(WsBroadcaster):
    """Records broadcast() calls instead of pushing to real WebSocket connections."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def broadcast(self, event, sighting_id: str) -> None:
        self.calls.append((event, sighting_id))


@pytest.fixture
def fake_redis_client():
    return fakeredis.FakeStrictRedis(decode_responses=True)


@pytest.fixture
def store(fake_redis_client):
    return ValkeySightingStore(fake_redis_client)


@pytest.fixture
def mqtt_publisher():
    return FakeMqttPublisher()


@pytest.fixture
def ws_broadcaster():
    return FakeWsBroadcaster()


@pytest.fixture
def client(store, mqtt_publisher, ws_broadcaster):
    app = create_app()
    app.dependency_overrides[get_store] = lambda: store
    app.dependency_overrides[get_mqtt_publisher] = lambda: mqtt_publisher
    app.dependency_overrides[get_ws_broadcaster] = lambda: ws_broadcaster
    # Auth is exercised on its own in test_auth.py — every other test in this suite predates
    # auth and shouldn't need a real token just to call DELETE. delete_sighting depends on
    # require_admin_or_ingest (not require_admin directly) — it calls require_admin() as a
    # plain function, not via Depends(), so overriding require_admin alone wouldn't reach
    # it. Both are overridden so a direct require_admin dependency elsewhere would also stay
    # bypassed. No scp/scope claim here, matching plain admin-bypass semantics: an ingest-
    # scope-specific test needs test_auth.py's own tokens instead.
    app.dependency_overrides[require_admin] = lambda: {"sub": "test-admin", "ext": {"role": "admin"}}
    app.dependency_overrides[require_admin_or_ingest] = lambda: {"sub": "test-admin", "ext": {"role": "admin"}}
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
