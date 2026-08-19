from fastapi import Request, WebSocket

from app.mqtt import MqttPublisher
from app.store.base import SightingStore
from app.ws import WsBroadcaster


def get_store(request: Request) -> SightingStore:
    return request.app.state.store


def get_mqtt_publisher(request: Request) -> MqttPublisher:
    return request.app.state.mqtt_publisher


def get_ws_broadcaster(request: Request) -> WsBroadcaster:
    """For the HTTP routes (create/delete) that call broadcast() — see get_ws_broadcaster_ws
    for the /sightings/ws route itself, which needs the WebSocket-scoped equivalent instead;
    FastAPI's DI requires the param type to match the route's scope (Request vs. WebSocket)."""
    return request.app.state.ws_broadcaster


def get_ws_broadcaster_ws(websocket: WebSocket) -> WsBroadcaster:
    return websocket.app.state.ws_broadcaster
