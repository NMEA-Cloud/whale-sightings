import fakeredis
import pytest
from fastapi.testclient import TestClient

from app.deps import get_store
from app.main import create_app
from app.store.valkey_store import ValkeySightingStore


@pytest.fixture
def fake_redis_client():
    return fakeredis.FakeStrictRedis(decode_responses=True)


@pytest.fixture
def store(fake_redis_client):
    return ValkeySightingStore(fake_redis_client)


@pytest.fixture
def client(store):
    app = create_app()
    app.dependency_overrides[get_store] = lambda: store
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
