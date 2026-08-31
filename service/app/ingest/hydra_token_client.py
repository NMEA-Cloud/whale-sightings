from __future__ import annotations

import time
from dataclasses import dataclass

import httpx

from app.ingest.config import IngestSettings


@dataclass
class _CachedToken:
    access_token: str
    expires_at: float  # a time.monotonic() deadline, not a wall-clock time


class HydraTokenClient:
    """Mints and caches a client_credentials token from our own Hydra instance, scoped to
    sightings:ingest — authenticates the connector's own calls to our service (see
    service_client.py). Not to be confused with whale_alert_client.py's token: that one
    authenticates to Whale Alert itself, via a different endpoint and a JSON body rather
    than this one's standard OAuth2 form-encoded token request."""

    def __init__(self, settings: IngestSettings, client: httpx.Client) -> None:
        self._settings = settings
        self._client = client
        self._cached: _CachedToken | None = None

    def get_token(self) -> str:
        if self._cached is not None and time.monotonic() < self._cached.expires_at:
            return self._cached.access_token

        response = self._client.post(
            self._settings.ingest_hydra_token_url,
            data={
                "grant_type": "client_credentials",
                "client_id": self._settings.ingest_hydra_client_id,
                "client_secret": self._settings.ingest_hydra_client_secret,
                "scope": "sightings:ingest",
                "audience": self._settings.ingest_hydra_audience,
            },
        )
        response.raise_for_status()
        body = response.json()
        # Refresh 60s before actual expiry so a request never starts against a token that
        # expires mid-flight.
        self._cached = _CachedToken(
            access_token=body["access_token"],
            expires_at=time.monotonic() + body["expires_in"] - 60,
        )
        return self._cached.access_token
