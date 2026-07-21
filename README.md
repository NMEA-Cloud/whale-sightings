# Whale Sightings

A whale-sighting tracking system: a FastAPI service (in Docker) backed by Valkey, paired
with a simple web client that runs outside the container. Both run locally for
development today; the service is intended to eventually deploy to AWS.

## Project layout

- `service/` — FastAPI application, persists sightings in Valkey, runs in Docker.
- `client/` — vanilla HTML/CSS/JS public client, served by a plain static file server (no build step).
- `admin/` — vanilla HTML/CSS/JS admin client (stats + demo data loading), also static, no build step.
- `docker-compose.yml` — runs `service` + `valkey` only. Neither client is containerized.

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) (with Compose) — runs the service, Valkey,
  and Mosquitto.
- [mkcert](https://github.com/FiloSottile/mkcert) — issues locally-trusted TLS certs (see
  [TLS setup](#tls-setup-do-this-first) below).
- Python 3.9+ on your host machine, as `python3` — used to serve the static clients. Not
  required to just run everything via `docker compose`; the service itself runs on Python
  3.12 inside its container regardless of what's installed on the host.
- Python **3.10+** if you plan to run the service or its tests outside Docker (e.g. for
  local development in `service/`) — the code uses `X | None` union syntax (PEP 604),
  which isn't supported on 3.9. On macOS, Apple's bundled `python3` is 3.9, so you'll
  likely need `brew install python@3.12` (or similar) and create the venv with that
  binary specifically, e.g. `python3.12 -m venv .venv`.

## TLS setup (do this first)

The service only accepts HTTPS — clients and `curl` need a certificate they'll actually
trust, not a self-signed one that throws warnings. Certs are generated locally with
[mkcert](https://github.com/FiloSottile/mkcert), which creates a CA and installs it into
your OS/browser trust stores, then issues a `localhost` cert signed by it. Nothing here is
committed to git or shared between machines — every developer runs this once:

```bash
# Install mkcert first if you don't have it: brew install mkcert / choco install mkcert / see the mkcert README
./scripts/setup-tls.sh    # or scripts/setup-tls.ps1 on Windows PowerShell
```

This writes `certs/localhost.pem` and `certs/localhost-key.pem` (gitignored). Re-run it any
time; it's idempotent. `docker-compose.yml` mounts `certs/` into the service container, and
`uvicorn` (both in Docker and when run directly, see below) is configured to use them.

Browsers trust the result with no warnings. On Windows, `curl` uses the Schannel TLS
backend, which hard-fails when it can't check a certificate's revocation status — locally
issued certs have no CRL/OCSP endpoint to check, so plain `curl https://localhost:8000/...`
will error with `CRYPT_E_NO_REVOCATION_CHECK`. Add `--ssl-no-revoke` to `curl` calls on
Windows (not needed on macOS/Linux, and not an issue for browsers, which soft-fail instead).

## Running the service

```bash
docker compose up --build
```

- Service: https://localhost:8000
- Health check: `curl https://localhost:8000/health`
- Valkey is exposed on `localhost:6379` for debugging with `valkey-cli`.
- The MQTT broker (Mosquitto) is exposed on `localhost:1883` (plain MQTT, e.g. for
  `mosquitto_sub`) and `localhost:9001` (MQTT-over-WebSockets, what the browser client
  uses) — see "Running the client" below.

### Example requests

Create a sighting:

```bash
curl -X POST https://localhost:8000/sightings \
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
curl https://localhost:8000/sightings
```

List sightings from the last N hours (e.g. the last day):

```bash
curl "https://localhost:8000/sightings?since_hours=24"
```

List sightings within a radius (nautical miles) of a point — `lat`, `lon`, and
`radius_nm` must all be given together, and can be combined with `since_hours`:

```bash
curl "https://localhost:8000/sightings?lat=47.726&lon=-122.645&radius_nm=10"
```

Delete a sighting by id (not auth-protected yet — intended for privileged/admin use
once OAuth2/OIDC lands, see roadmap below):

```bash
curl -X DELETE https://localhost:8000/sightings/<id>
```

Get a single sighting by id:

```bash
curl https://localhost:8000/sightings/<id>
```

Get stats (count, oldest, newest sighting) — used by the admin client:

```bash
curl https://localhost:8000/sightings/stats
```

## Running the client

The client is a static site with no build step, and is not part of `docker-compose.yml`.
Run it with any static file server, e.g.:

```bash
cd client
python3 -m http.server 8080
```

Then open http://localhost:8080 in a browser. The form auto-fills location/time via the
browser Geolocation API (`http://localhost` is treated as a secure context, so this works
without HTTPS locally — AWS deployment will need HTTPS for Geolocation to keep working).

The list of sightings can be filtered to the last N hours and/or to within a radius (in
nautical miles) of a point — "Use current location" fills in the radius filter's
latitude/longitude, same as the report form. The list is also plotted on a map
(Leaflet + OpenStreetMap tiles, loaded from a CDN) with a pin per sighting — the map
re-fits itself to whatever sightings are currently loaded whenever the list changes.

The list, count, and map also live-refresh automatically: the service publishes to the
Mosquitto broker whenever any client creates or deletes a sighting, and every open
client subscribes over MQTT-over-WebSockets (`ws://localhost:9001`) and re-runs its
current filtered query on each notification. The manual Refresh button still works too.

`client/app.js` points at the service via a hardcoded `API_BASE` constant — update it if
the service isn't running on `https://localhost:8000`. The MQTT broker URL/topic are
similarly hardcoded as `MQTT_WS_URL`/`MQTT_TOPIC` in the same file.

### Try the live sync

Open `http://localhost:8080` in three browser tabs (or windows), each running the same
client. Submit a sighting in one tab — the other two update their table, count, and map
automatically within moments, with no manual refresh. Deleting a sighting in any tab
updates the others the same way. Filters set in a tab (time window / radius) are still
respected on each live refresh, same as a manual Refresh.

## Running the admin client

The admin client is a separate static site (also no build step) for demo purposes: it
shows sighting counts plus the oldest/newest sighting, lets you load canned demo data
with one click, and can clear all sightings to reset between demos. Run it on a
different port than the public client:

```bash
cd admin
python3 -m http.server 8081
```

Then open http://localhost:8081. Like the public client, it points at the service via
a hardcoded `API_BASE` constant in `admin/app.js`. The canned scenarios live in the
`SCENARIOS` array in that file — edit or add to them for your own demo needs.

This client has no authentication and is not meant to be exposed publicly — see the
roadmap below.

## Running the service outside Docker (for development)

Needs Python 3.10+ (see [Prerequisites](#prerequisites)) — use `python3.10`/`python3.12`/etc.
in place of `python3` below if that's not what `python3` resolves to on your machine.

```bash
cd service
python3 -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env  # sets VALKEY_HOST=localhost
uvicorn app.main:app --reload --ssl-certfile ../certs/localhost.pem --ssl-keyfile ../certs/localhost-key.pem
```

(Requires the [TLS setup](#tls-setup-do-this-first) step above to have been run first.)

## Running tests

Also needs Python 3.10+, same as above.

```bash
cd service
python3 -m venv .venv  # skip if you already created one above
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
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

1. **Done**: collect sightings via a form, persist in Valkey, list all sightings, delete a
   sighting, and show them on a map.
2. **Done**: filter sightings by time window (`since_hours`, both in the API and the client).
3. **Done**: filter sightings by location — within Y nautical miles of a point
   (`lat`/`lon`/`radius_nm`, both in the API and the client), composable with the time
   filter. Filtering within an arbitrary defined region is still future work.
4. Optionally swap or offer a PostgreSQL storage backend behind the same storage interface.
5. Add OAuth2 / OpenID Connect authentication, replacing the placeholder observer identity.
6. Deploy the service to AWS.
