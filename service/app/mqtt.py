from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from typing import Literal

import paho.mqtt.client as mqtt

logger = logging.getLogger(__name__)

Event = Literal["created", "deleted"]


class MqttPublisher(ABC):
    @abstractmethod
    def publish(self, event: Event, sighting_id: str) -> None: ...


class PahoMqttPublisher(MqttPublisher):
    def __init__(self, host: str, port: int, topic: str) -> None:
        self._topic = topic
        self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        # A local/docker-network broker accepts connections in milliseconds; capping
        # this well below the 5s default keeps close() fast if the broker is
        # unreachable (e.g. under pytest), since loop_stop() has to wait out any
        # in-flight connect attempt before its thread can join.
        self._client.connect_timeout = 1.0
        # Non-blocking, non-raising even if the broker isn't reachable (e.g. under
        # pytest) — the network thread retries in the background; publish() on a
        # disconnected client just silently no-ops instead of raising.
        self._client.connect_async(host, port)
        self._client.loop_start()

    def _on_connect(self, client, userdata, flags, reason_code, properties=None) -> None:
        logger.info("Connected to MQTT broker (rc=%s)", reason_code)

    def _on_disconnect(self, client, userdata, flags, reason_code, properties=None) -> None:
        logger.warning("Disconnected from MQTT broker (rc=%s)", reason_code)

    def publish(self, event: Event, sighting_id: str) -> None:
        self._client.publish(self._topic, json.dumps({"event": event, "id": sighting_id}), qos=0)

    def close(self) -> None:
        # disconnect() first so a background reconnect-in-progress (e.g. no broker
        # reachable, as under pytest) is cancelled before loop_stop() joins the
        # network thread — the reverse order left loop_stop() waiting out the
        # in-flight reconnect backoff on every test teardown.
        self._client.disconnect()
        self._client.loop_stop()
