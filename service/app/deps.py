from fastapi import Request

from app.mqtt import MqttPublisher
from app.store.base import SightingStore


def get_store(request: Request) -> SightingStore:
    return request.app.state.store


def get_mqtt_publisher(request: Request) -> MqttPublisher:
    return request.app.state.mqtt_publisher
