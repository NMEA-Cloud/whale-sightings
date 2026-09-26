"""handle_event() against a mocked service (httpx.MockTransport): the follow-the-link ->
expand -> understand path peer-service runs for every live-sync event."""

from __future__ import annotations

import asyncio
import json
import logging

import httpx

import main
from linked_data import CachingContextLoader
from tests.sighting_samples import CANONICAL_ID, LINK, fixture_fetch, sighting


def _run(message: str, handler) -> list[httpx.Request]:
    seen: list[httpx.Request] = []

    def recording(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(recording)) as client:
            await main.handle_event(message, client, CachingContextLoader(fixture_fetch))

    asyncio.run(go())
    return seen


def test_created_event_follows_link_and_logs_what_it_understood(caplog):
    caplog.set_level(logging.INFO, logger="peer-service")

    seen = _run(
        json.dumps({"event": "created", "sighting": LINK}),
        lambda request: httpx.Response(200, json=sighting()),
    )

    assert [str(r.url) for r in seen] == [LINK]
    assert seen[0].headers["accept"] == "application/ld+json"
    assert (
        f"Understood created {CANONICAL_ID}: Orcinus orca "
        "(urn:lsid:marinespecies.org:taxname:137102), source=peer, at (47.7260, -122.6450), "
        "observed 2026-09-26T15:00:00Z"
    ) in caplog.text


def test_deleted_event_fetches_nothing(caplog):
    caplog.set_level(logging.INFO, logger="peer-service")

    seen = _run(json.dumps({"event": "deleted", "sighting": LINK}), lambda request: httpx.Response(500))

    assert seen == []
    assert f"Live-sync: deleted {LINK}" in caplog.text


def test_fetch_failure_is_logged_not_raised(caplog):
    seen = _run(json.dumps({"event": "updated", "sighting": LINK}), lambda request: httpx.Response(404))

    assert len(seen) == 1
    assert f"Couldn't understand updated event for {LINK}" in caplog.text


def test_unrecognized_message_is_logged_not_raised(caplog):
    seen = _run("not json", lambda request: httpx.Response(500))

    assert seen == []
    assert "Unrecognized live-sync message: not json" in caplog.text
