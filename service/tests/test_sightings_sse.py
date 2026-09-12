import json
import socket
import threading
import time

import httpx
import uvicorn

from app.auth import require_admin, require_admin_or_ingest
from app.deps import get_mqtt_publisher, get_store
from app.main import create_app
from tests.test_sightings_api import sample_payload_dict


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class _RealServer:
    """Serves the app over a real TCP socket via uvicorn, in a background thread.

    Needed specifically for testing the SSE branch: httpx's in-process ASGITransport
    (used everywhere else in this suite, e.g. via TestClient) awaits the whole ASGI app
    call to completion before returning a response at all — fine for a normal
    request/response endpoint, but it means it can never hand back a response for a
    stream that's still open, so it can't exercise a route that, by design, never
    completes on its own. A real socket doesn't have that limitation: the OS delivers
    bytes to the reading client as they're written, independent of whether the
    server-side handler has returned. Confirmed by direct experimentation before writing
    this — not assumed.
    """

    def __init__(self, app) -> None:
        self.port = _free_port()
        config = uvicorn.Config(app, host="127.0.0.1", port=self.port, log_level="warning")
        self.server = uvicorn.Server(config)
        self.thread = threading.Thread(target=self.server.run, daemon=True)

    def __enter__(self) -> str:
        self.thread.start()
        while not self.server.started:
            time.sleep(0.01)
        return f"http://127.0.0.1:{self.port}"

    def __exit__(self, *exc_info: object) -> None:
        self.server.should_exit = True
        self.thread.join(timeout=5)


def _make_app(store, mqtt_publisher):
    """Deliberately does NOT override get_sse_broadcaster like the shared conftest.py
    fixture does — these tests need the real ConnectionSseBroadcaster so the GET
    /sightings SSE branch and create_sighting/delete_sighting share one broadcaster
    instance (app.state.sse_broadcaster), since that's the actual thing under test here.
    Same reasoning as test_sightings_ws.py's own local client fixture."""
    app = create_app()
    app.dependency_overrides[get_store] = lambda: store
    app.dependency_overrides[get_mqtt_publisher] = lambda: mqtt_publisher
    app.dependency_overrides[require_admin] = lambda: {"sub": "test-admin", "ext": {"role": "admin"}}
    app.dependency_overrides[require_admin_or_ingest] = lambda: {"sub": "test-admin", "ext": {"role": "admin"}}
    return app


def test_sse_client_receives_created_and_deleted_events(store, mqtt_publisher):
    app = _make_app(store, mqtt_publisher)

    with _RealServer(app) as base_url, httpx.Client(timeout=5) as client:
        with client.stream("GET", f"{base_url}/sightings", headers={"Accept": "text/event-stream"}) as response:
            assert response.status_code == 200
            assert response.headers["content-type"].startswith("text/event-stream")

            lines = response.iter_lines()
            # The initial ": connected" comment line (plus its blank-line terminator) is
            # the deterministic "stream is open and registered" signal — must be
            # consumed before triggering a mutation, or a same-instant broadcast could be
            # missed. See sse.py's event_stream() docstring.
            assert next(lines) == ": connected"
            assert next(lines) == ""

            create_response = client.post(f"{base_url}/sightings", json=sample_payload_dict())
            body = create_response.json()
            # The broadcaster builds links from settings.public_api_base_url (a fixed
            # default), not from this request's own base_url — matches
            # test_sightings_ws.py's identical hardcoded expectation.
            resource_url = f"https://localhost:8000/sightings/{body['id']}"
            assert next(lines) == f"data: {json.dumps({'event': 'created', 'sighting': resource_url})}"
            assert next(lines) == ""

            client.delete(f"{base_url}/sightings/{body['id']}")
            assert next(lines) == f"data: {json.dumps({'event': 'deleted', 'sighting': resource_url})}"
            assert next(lines) == ""

    app.dependency_overrides.clear()


def test_get_sightings_without_sse_accept_is_unaffected(store, mqtt_publisher):
    app = _make_app(store, mqtt_publisher)

    with _RealServer(app) as base_url, httpx.Client(timeout=5) as client:
        response = client.get(f"{base_url}/sightings")

    app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert isinstance(response.json(), list)
