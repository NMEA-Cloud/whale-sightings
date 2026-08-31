from __future__ import annotations

from typing import Any

import httpx

from app.ingest.config import IngestSettings
from app.ingest.hydra_token_client import HydraTokenClient


class ServiceClient:
    """Everything the connector does against our own service — always real HTTP, exactly
    like every other client in this repo. Writes go through the same create/update/notify
    path a human-submitted sighting does, rather than writing to Valkey directly, so MQTT/WS
    subscribers see whale-alert-connector activity live like anything else."""

    def __init__(self, settings: IngestSettings, client: httpx.Client, token_client: HydraTokenClient) -> None:
        self._settings = settings
        self._client = client
        self._token_client = token_client

    def _auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token_client.get_token()}"}

    def get_by_source(self, upstream_id: str) -> dict[str, Any] | None:
        # Unauthenticated — GET /sightings/by-source/... has the same open posture as
        # GET /sightings/{id} (see routers/sightings.py).
        response = self._client.get(
            f"{self._settings.ingest_service_api_base}/sightings/by-source/whale_alert/{upstream_id}"
        )
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json()

    def create(self, payload: dict[str, Any]) -> dict[str, Any]:
        response = self._client.post(
            f"{self._settings.ingest_service_api_base}/sightings", json=payload, headers=self._auth_headers()
        )
        response.raise_for_status()
        return response.json()

    def update_moderation(self, sighting_id: str, moderation_status: str) -> dict[str, Any]:
        response = self._client.patch(
            f"{self._settings.ingest_service_api_base}/sightings/{sighting_id}/moderation",
            json={"moderation_status": moderation_status},
            headers=self._auth_headers(),
        )
        response.raise_for_status()
        return response.json()

    def delete(self, sighting_id: str) -> None:
        response = self._client.delete(
            f"{self._settings.ingest_service_api_base}/sightings/{sighting_id}", headers=self._auth_headers()
        )
        if response.status_code == 404:
            return
        response.raise_for_status()
