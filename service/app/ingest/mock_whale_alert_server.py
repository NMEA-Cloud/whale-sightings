"""A small FastAPI app faking just enough of Whale Alert's real API shape to exercise
service/app/ingest/ against, without ever touching the real production service. Seeded from
real, already-saved, PII-redacted example records (see the local reference Postman
collection) rather than either fabricated-from-scratch data or a fresh call to production.

Runnable standalone: `python -m app.ingest.mock_whale_alert_server` (uvicorn on MOCK_PORT,
default 9100), or via docker-compose.yml's own "whale-alert-mock" profile — deliberately
separate from the connector's "whale-alert" profile so the two toggle independently. Point
the real connector at it by setting WHALE_ALERT_API_BASE_URL to this server's address
instead of the real Whale Alert base URL — no code branch needed anywhere else.

This is the one piece of the whole Whale Alert integration safe to run and verify directly —
it's a local fake, not the real production service.
"""

from __future__ import annotations

import copy
import math
import os
import uuid
from datetime import datetime
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request, status

MOCK_CLIENT_ID = os.environ.get("MOCK_CLIENT_ID", "mock-client-id")
MOCK_CLIENT_SECRET = os.environ.get("MOCK_CLIENT_SECRET", "mock-client-secret")
MOCK_PORT = int(os.environ.get("MOCK_PORT", "9100"))

app = FastAPI(title="Whale Alert (mock)")

# One real, saved, PII-redacted example per moderation status — ids/field values verified
# against the local reference Postman collection, never a fresh call to production.
REAL_EXAMPLES: list[dict[str, Any]] = [
    {  # moderated=0 (Unreviewed) — outside the default Puget Sound bbox (Panama)
        "id": 116308,
        "created": "2026-08-03 14:13:00",
        "species": "No especificado",
        "species_id": "unknown_whale",
        "number": 1,
        "lat": 8.97974,
        "lng": -79.5109,
        "moderated": 0,
        "source": "mobile_app",
        "comments": "test panama",
        "animal_status": "Live",
    },
    {  # moderated=1 (Confirmed) — outside the default bbox (west of -123.3)
        "id": 116315,
        "created": "2026-08-03 15:33:00",
        "species": "Humpback",
        "species_id": "humpback_whale",
        "number": 1,
        "lat": 50.86575,
        "lng": -127.52036,
        "moderated": 1,
        "source": "mobile_app",
        "comments": "",
        "animal_status": "Live",
    },
    {  # moderated=2 (Unconfirmed) — inside the default Puget Sound bbox
        "id": 116184,
        "created": "2026-08-01 17:41:07",
        "species": "Pacific White-sided Dolphin",
        "species_id": "pacific_white_sided_dolphin",
        "number": 1,
        "lat": 48.53962,
        "lng": -122.95828,
        "moderated": 2,
        "source": "mobile_app",
        "comments": "",
        "animal_status": "Live",
    },
    {  # moderated=3 (Deleted) — outside the default bbox (near 0,0)
        "id": 112793,
        "created": "2026-08-29 09:42:00",
        "species": "Unspecified",
        "species_id": "unknown_whale",
        "number": 2,
        "lat": 0.4284,
        "lng": 0.3656,
        "moderated": 3,
        "source": "API",
        "comments": "Traveling north",
        "animal_status": "Live",
    },
]

# Templated from the real examples above (same field shape) but with new ids and,
# deliberately, coordinates inside the default Puget Sound bbox — 3 of the 4 real examples
# above fall outside it, so without these a default-configured connector run against this
# mock would never find anything in-region to create.
SYNTHESIZED_SIBLINGS: list[dict[str, Any]] = [
    {
        "id": 900001,
        "created": "2026-08-30 09:00:00",
        "species": "Orca",
        "species_id": "orca_killer_whale",
        "number": 3,
        "lat": 47.65,
        "lng": -122.35,
        "moderated": 0,
        "source": "mobile_app",
        "comments": "Pod near Seattle waterfront",
        "animal_status": "Live",
    },
    {
        "id": 900002,
        "created": "2026-08-26 11:15:00",
        "species": "Gray Whale",
        "species_id": "gray_whale",
        "number": 1,
        "lat": 48.52,
        "lng": -122.9,
        "moderated": 0,
        "source": "mobile_app",
        "comments": "Feeding near San Juan Islands",
        "animal_status": "Live",
    },
    {
        "id": 900003,
        "created": "2026-08-20 08:30:00",
        "species": "Minke Whale",
        "species_id": "minke_whale",
        "number": 1,
        "lat": 47.9,
        "lng": -122.5,
        "moderated": 0,
        "source": "API",
        "comments": "Reported by ferry crew",
        "animal_status": "Live",
    },
]

_ALL_TEMPLATES = REAL_EXAMPLES + SYNTHESIZED_SIBLINGS
_fixtures: dict[int, dict[str, Any]] = {record["id"]: copy.deepcopy(record) for record in _ALL_TEMPLATES}

_current_token: str | None = None


def _parse_bbox(bbox: str) -> tuple[float, float, float, float]:
    west, south, east, north = (float(part) for part in bbox.split(","))
    return west, south, east, north


@app.post("/auth/token")
async def auth_token(request: Request) -> dict[str, Any]:
    """Matches the real example's response shape exactly (see the reference collection's
    saved "POST auth/token" response) — a JSON body of client_id/client_secret in, a bearer
    token good for expires_in seconds out."""
    body = await request.json()
    if body.get("client_id") != MOCK_CLIENT_ID or body.get("client_secret") != MOCK_CLIENT_SECRET:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid client credentials")

    global _current_token
    _current_token = uuid.uuid4().hex
    return {
        "access_token": _current_token,
        "token_type": "Bearer",
        "expires_in": 3600,
        "scope": "sightings:moderate sightings:read sightings:write",
        "scopes": ["sightings:moderate", "sightings:read", "sightings:write"],
        "groups": [1],
    }


def _require_bearer(request: Request) -> None:
    auth_header = request.headers.get("Authorization", "")
    scheme, _, token = auth_header.partition(" ")
    if scheme.lower() != "bearer" or not token or token != _current_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing or invalid bearer token")


@app.get("/sightings")
async def search_sightings(
    request: Request,
    bbox: str = Query(...),
    start: str = Query(...),
    end: str = Query(...),
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=200),
) -> dict[str, Any]:
    """Supports exactly the query params whale_alert_client.py actually sends
    (status[]/bbox/start/end/page/per_page) — the real API also accepts sort/dir/etc, but
    the connector never sends those, so this mock doesn't implement them."""
    _require_bearer(request)

    # status[] is a repeated param ("status[]=0&status[]=1&..."); FastAPI can't declare it
    # as a typed parameter above since "[]" isn't a valid Python identifier, so it's read
    # straight off the raw query params instead.
    statuses = {int(value) for value in request.query_params.getlist("status[]")}

    west, south, east, north = _parse_bbox(bbox)
    start_date = datetime.strptime(start, "%Y-%m-%d").date()
    end_date = datetime.strptime(end, "%Y-%m-%d").date()

    matched = []
    for record in _fixtures.values():
        if statuses and record["moderated"] not in statuses:
            continue
        if not (west <= record["lng"] <= east and south <= record["lat"] <= north):
            continue
        created_date = datetime.strptime(record["created"], "%Y-%m-%d %H:%M:%S").date()
        if not (start_date <= created_date <= end_date):
            continue
        matched.append(record)

    matched.sort(key=lambda r: r["created"], reverse=True)

    total = len(matched)
    pages = max(1, math.ceil(total / per_page))
    page_results = matched[(page - 1) * per_page : page * per_page]

    return {
        "success": True,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": pages,
        "results": [copy.deepcopy(record) for record in page_results],
    }


@app.post("/_mock/advance")
async def advance() -> dict[str, Any]:
    """Not part of Whale Alert's real API — a test-driver-only endpoint. Advances every
    fixture's `moderated` value by one step, capped at 3 (Deleted), so a test can exercise
    the connector's update-detection path (PATCH .../moderation, then DELETE) without
    waiting for real-world moderation to happen — a real captured example is a static
    snapshot and can't demonstrate a transition on its own."""
    changed = []
    for record in _fixtures.values():
        if record["moderated"] < 3:
            record["moderated"] += 1
            changed.append({"id": record["id"], "moderated": record["moderated"]})
    return {"changed": changed}


@app.post("/_mock/reset")
async def reset() -> dict[str, str]:
    """Not part of Whale Alert's real API — restores every fixture to its original
    moderated value, so a test suite can start from a known state without restarting the
    process."""
    global _fixtures
    _fixtures = {record["id"]: copy.deepcopy(record) for record in _ALL_TEMPLATES}
    return {"status": "reset"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=MOCK_PORT)
