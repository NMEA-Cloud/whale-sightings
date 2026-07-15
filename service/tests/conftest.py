import fakeredis
import pytest
from fastapi.testclient import TestClient

from app.deps import get_mqtt_publisher, get_store
from app.main import create_app
from app.mqtt import MqttPublisher
from app.store.valkey_store import ValkeySightingStore


class FakeMqttPublisher(MqttPublisher):
    """Records publish() calls instead of talking to a real broker."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def publish(self, event, sighting_id: str) -> None:
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
def client(store, mqtt_publisher):
    app = create_app()
    app.dependency_overrides[get_store] = lambda: store
    app.dependency_overrides[get_mqtt_publisher] = lambda: mqtt_publisher
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
