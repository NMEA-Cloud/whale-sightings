"""fetch_recent_positions(): finding this peer's own previous track so a restart can continue
it (see route.PolygonWanderer's resume_from)."""

from __future__ import annotations

import logging

import httpx

import config
import main

LIST_URL = "https://service:8000/sightings"


def _record(created_at: str, lat: float, lon: float, source: dict) -> dict:
    return {
        "created_at": created_at,
        "sighting": {"location": {"geometry": {"type": "Point", "coordinates": [lon, lat]}}},
        "source": source,
    }


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_returns_own_most_recent_positions_oldest_first():
    own = {"type": "peer", "peer_id": config.PEER_CLIENT_ID}
    records = [
        _record("2026-09-28T14:05:00Z", 32.85, -96.50, own),
        _record("2026-09-28T14:06:00Z", 32.86, -96.50, {"type": "peer", "peer_id": "some-other-peer"}),
        _record("2026-09-28T14:03:00Z", 32.83, -96.50, own),
        _record("2026-09-28T14:07:00Z", 32.87, -96.50, {"type": "local"}),
        _record("2026-09-28T14:04:00Z", 32.84, -96.50, own),
    ]  # deliberately out of order

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == LIST_URL
        return httpx.Response(200, json=records)

    with _client(handler) as client:
        assert main.fetch_recent_positions(client, LIST_URL) == [(32.84, -96.50), (32.85, -96.50)]


def test_returns_nothing_when_this_peer_has_no_sightings():
    with _client(lambda request: httpx.Response(200, json=[])) as client:
        assert main.fetch_recent_positions(client, LIST_URL) == []


def test_failure_means_a_fresh_start_not_a_crash(caplog):
    with _client(lambda request: httpx.Response(500)) as client:
        assert main.fetch_recent_positions(client, LIST_URL) == []
    assert "starting fresh" in caplog.text
