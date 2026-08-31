from __future__ import annotations

import time
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import httpx

from app.ingest.config import IngestSettings

# All four Whale Alert moderation statuses, in the shape its own API expects them
# (status[]=0&status[]=1&...) — see "Search - status all four" in the reference collection.
ALL_STATUSES = (0, 1, 2, 3)


@dataclass
class _CachedToken:
    access_token: str
    expires_at: float


class WhaleAlertClient:
    """The only file in this repo that ever makes a real HTTP call to Whale Alert's
    production API — every other piece of the connector talks to our own service instead.
    Authenticates via Whale Alert's own Group-Admin client-credentials flow: POST
    {base}/auth/token with a JSON body of client_id/client_secret (confirmed against a real
    saved response in the reference Postman collection — notably a JSON body, unlike our own
    Hydra's standard form-encoded token request in hydra_token_client.py)."""

    def __init__(self, settings: IngestSettings, client: httpx.Client) -> None:
        self._settings = settings
        self._client = client
        self._cached: _CachedToken | None = None

    def _get_token(self) -> str:
        if self._cached is not None and time.monotonic() < self._cached.expires_at:
            return self._cached.access_token

        response = self._client.post(
            f"{self._settings.whale_alert_api_base_url}/auth/token",
            json={
                "client_id": self._settings.whale_alert_client_id,
                "client_secret": self._settings.whale_alert_client_secret,
            },
        )
        response.raise_for_status()
        body = response.json()
        self._cached = _CachedToken(
            access_token=body["access_token"],
            expires_at=time.monotonic() + body["expires_in"] - 60,
        )
        return self._cached.access_token

    def search_sightings(
        self, *, statuses: tuple[int, ...], bbox: str, start: str, end: str, page: int, per_page: int = 100
    ) -> dict[str, Any]:
        """One page of GET /sightings. `start`/`end` are plain YYYY-MM-DD dates, matching
        the reference collection's date-range example — Whale Alert's `created` field has
        no timezone marker in any reviewed example, so day-granularity here is deliberately
        coarse; day-boundary edge cases are covered by the lookback window's overlap with
        the previous cycle, not by sub-day precision in this query."""
        token = self._get_token()
        params = [("status[]", status) for status in statuses] + [
            ("bbox", bbox),
            ("start", start),
            ("end", end),
            ("page", page),
            ("per_page", per_page),
        ]
        response = self._client.get(
            f"{self._settings.whale_alert_api_base_url}/sightings",
            params=params,
            headers={"Authorization": f"Bearer {token}"},
        )
        response.raise_for_status()
        return response.json()

    def iter_all_sightings(
        self, *, statuses: tuple[int, ...], bbox: str, start: str, end: str
    ) -> Iterator[dict[str, Any]]:
        """Pages through every result across the full `pages` count the first response
        reports."""
        page = 1
        while True:
            body = self.search_sightings(statuses=statuses, bbox=bbox, start=start, end=end, page=page)
            yield from body["results"]
            if page >= body["pages"]:
                return
            page += 1
