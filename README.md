# Whale Sightings

A whale-sighting tracking system: a FastAPI service (in Docker) backed by Valkey, paired
with a simple web client that runs outside the container. Both run locally for
development today; the service is intended to eventually deploy to AWS.

## Project layout

- `service/` — FastAPI application, persists sightings in Valkey, runs in Docker.
- `client/` — vanilla HTML/CSS/JS client, served by a plain static file server (no build step).
- `docker-compose.yml` — runs `service` + `valkey` only. The client is intentionally not containerized.

## Running the service

```bash
docker compose up --build
```

- Service: http://localhost:8000
- Health check: `curl http://localhost:8000/health`
- Valkey is exposed on `localhost:6379` for debugging with `valkey-cli`.

### Example requests

Create a sighting:

```bash
curl -X POST http://localhost:8000/sightings \
  -H "Content-Type: application/json" \
  -d '{
    "sighting": {
      "location": {
        "geometry": {
          "type": "Point",
          "coordinates": [-122.64504694316724, 47.72618676380336],
          "properties": { "datetime": "2026-07-07T16:18:04.113Z" }
        }
      },
      "status": "alive",
      "comments": "Thar she blows!",
      "type": "wombat",
      "species": "Greater Pacific Wombat",
      "name": "LB-Whale",
      "method": "manual-report"
    },
    "observer": {
      "id": "https://example.org/users/anonymous-observer",
      "location": {
        "geometry": {
          "type": "Point",
          "coordinates": [-122.64504694316724, 47.72618676380336],
          "properties": { "datetime": "2026-07-07T16:18:04.113Z" }
        }
      }
    },
    "images": []
  }'
```

List all sightings (newest first):

```bash
curl http://localhost:8000/sightings
```

List sightings from the last N hours (e.g. the last day):

```bash
curl "http://localhost:8000/sightings?since_hours=24"
```

Delete a sighting by id (not auth-protected yet — intended for privileged/admin use
once OAuth2/OIDC lands, see roadmap below):

```bash
curl -X DELETE http://localhost:8000/sightings/<id>
```

## Running the client

The client is a static site with no build step, and is not part of `docker-compose.yml`.
Run it with any static file server, e.g.:

```bash
cd client
python -m http.server 8080
```

Then open http://localhost:8080 in a browser. The form auto-fills location/time via the
browser Geolocation API (`http://localhost` is treated as a secure context, so this works
without HTTPS locally — AWS deployment will need HTTPS for Geolocation to keep working).

`client/app.js` points at the service via a hardcoded `API_BASE` constant — update it if
the service isn't running on `http://localhost:8000`.

## Running the service outside Docker (for development)

```bash
cd service
python -m venv .venv
.venv/Scripts/activate  # or source .venv/bin/activate on macOS/Linux
pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env  # sets VALKEY_HOST=localhost
uvicorn app.main:app --reload
```

## Running tests

```bash
cd service
pip install -r requirements.txt -r requirements-dev.txt
pytest
```

Tests use `fakeredis`, so no live Valkey instance is required.

## Data model

See `service/app/models.py` for the full schema. A sighting envelope has this shape:

```json
{
  "id": "server-assigned uuid",
  "sighting": {
    "location": { "geometry": { "type": "Point", "coordinates": [lon, lat], "properties": { "datetime": "..." } } },
    "status": "alive | dead | distressed | unknown",
    "comments": "free text",
    "type": "text",
    "species": "text",
    "name": "optional text",
    "method": "manual-report | other"
  },
  "observer": {
    "id": "observer identifier (placeholder until auth exists)",
    "location": { "geometry": "same shape as sighting.location" }
  },
  "images": []
}
```

Coordinates are in GeoJSON order: `[longitude, latitude]`.

## Roadmap

This project is being built in stages:

1. **Done**: collect sightings via a form, persist in Valkey, list all sightings, delete a sighting.
2. **Done**: filter sightings by time window (`since_hours`, both in the API and the client).
3. **Current**: filter sightings by location (within Y nautical miles of a point, or
   within a defined region) — the geo index maintained in the store today exists to
   make this additive.
4. Optionally swap or offer a PostgreSQL storage backend behind the same storage interface.
5. Add OAuth2 / OpenID Connect authentication, replacing the placeholder observer identity.
6. Deploy the service to AWS.
