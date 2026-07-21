import json

from app.mqtt import PahoMqttPublisher


def test_publish_sends_event_and_resource_url(monkeypatch):
    publisher = PahoMqttPublisher("localhost", 1, "whale-sightings/updates", "https://localhost:8000/")
    calls = []
    monkeypatch.setattr(
        publisher._client, "publish", lambda topic, payload, qos: calls.append((topic, payload, qos))
    )

    publisher.publish("created", "abc-123")
    publisher.close()

    assert calls == [
        (
            "whale-sightings/updates",
            json.dumps({"event": "created", "sighting": "https://localhost:8000/sightings/abc-123"}),
            0,
        )
    ]
