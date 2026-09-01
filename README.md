# Whale Sightings

A whale-sighting tracking system: a FastAPI service backed by Valkey, paired with three
static web clients — all running in Docker. Everything runs locally for development today;
the service is intended to eventually deploy to AWS.

## Project layout

- `service/` — FastAPI application, persists sightings in Valkey, runs in Docker.
  `service/app/ingest/` — the Whale Alert connector and its local mock server, both opt-in
  (see "Whale Alert connector" below); the main FastAPI app never imports this package.
- `client-mqtt/` — vanilla HTML/CSS/JS public client, live-updated via MQTT over WebSockets, runs in Docker.
- `client-long-poll/` — same public client, live-updated via `GET /sightings/poll` long-polling instead of MQTT.
- `client-ws/` — same public client, live-updated via a direct WebSocket connection to the service (`GET /sightings/ws`) instead of MQTT or long-polling.
- `shared/` — rendering/form/filter JS shared by `client-mqtt/`, `client-long-poll/`, and `client-ws/`, copied into each's image at build time — see "Running the clients" below.
- `client-admin/` — vanilla HTML/CSS/JS admin client (stats + demo data loading), also runs in Docker.
- `peer-service/` — a simulated second system demonstrating HATEOAS discovery — plain async
  Python, no FastAPI, no shared code with `service/`. See "peer-service" below.
- `hydra/` — config for the self-hosted Ory Hydra OAuth2 authorization server.
- `login-consent/` — small FastAPI app serving Hydra's login/consent screens.
- `dnsmasq/` — config for the `dns` service (see `infra/docker-compose.yml`) that resolves
  the `dev.`-subdomain hostnames below.
- `docker-compose.yml` — the **app** project (Compose project name `wombat-sightings`): runs
  `service`, `valkey`, `mqtt`, all four static clients, and `peer-service`, plus two opt-in,
  profile-gated services — `whale-alert-connector` and `whale-alert-mock` (see "Whale Alert
  connector" below).
- `infra/docker-compose.yml` — the **infra** project (Compose project name `booth-boat`): runs
  `step-ca`, `hydra`, `login-consent`, and `dns`. Split into its own project so this rehearses
  the eventual move of this infrastructure onto a separate physical machine (a Raspberry Pi
  acting as a trade-show LAN router) — see that file's header comment. Joined to the app
  project via the `whale-sightings-net` external Docker network so `service` can still
  resolve `hydra` by name for JWKS fetches.

## Ports

| Port | Service | Host | Project | Notes |
|---|---|---|---|---|
| 6379 | `valkey` | localhost | app | Redis protocol |
| 8883 | `mqtt` | localhost | app | MQTT, TLS required (`mqtts`) |
| 9001 | `mqtt` | localhost | app | MQTT over WebSockets |
| 8000 | `service` | api.dev.wombat-sightings.org | app | HTTPS (FastAPI) — also reachable at localhost:8000 |
| 8080 | `client-admin` | localhost | app | HTTP |
| 8081 | `client-mqtt` | localhost | app | HTTP |
| 8082 | `client-long-poll` | localhost | app | HTTP |
| 8083 | `client-ws` | localhost | app | HTTP |
| 9100 | `whale-alert-mock` | localhost | app | HTTP, opt-in (`whale-alert-mock` profile — see "Whale Alert connector") |
| 9000 | `step-ca` | localhost | infra | HTTPS (CA API) |
| 53 | `dns` | localhost | infra | DNS, tcp + udp |
| 4444 | `hydra` | auth.dev.booth-boat.org | infra | HTTPS, public (OAuth2/OIDC endpoints, discovery doc) — also reachable at localhost:4444 |
| 4445 | `hydra` | localhost | infra | HTTPS, admin (login/consent request management) |
| 4446 | `login-consent` | auth.dev.booth-boat.org | infra | HTTPS — also reachable at localhost:4446 |

"app" = `docker-compose.yml` (project `wombat-sightings`); "infra" = `infra/docker-compose.yml`
(project `booth-boat`) — see "Project layout" above.

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) (with Compose) — runs the service, Valkey,
  and Mosquitto.
- [step CLI](https://smallstep.com/docs/step-cli/installation) — requests locally-trusted TLS
  certs from the project's step-ca container (see [TLS setup](#tls-setup-do-this-first)
  below).
- Python 3.9+ on your host machine, as `python3` — only needed if you want to run a static
  client directly instead of via Docker (see "Running the clients" below). Not required to
  just run everything via `docker compose`; the service and clients run on Python 3.12 inside
  their containers regardless of what's installed on the host.
- Python **3.10+** if you plan to run the service or its tests outside Docker (e.g. for
  local development in `service/`) — the code uses `X | None` union syntax (PEP 604),
  which isn't supported on 3.9. On macOS, Apple's bundled `python3` is 3.9, so you'll
  likely need `brew install python@3.12` (or similar) and create the venv with that
  binary specifically, e.g. `python3.12 -m venv .venv`.

## TLS setup (do this first)

The service only accepts HTTPS — clients and `curl` need a certificate they'll actually
trust, not a self-signed one that throws warnings. Certs are issued by
[step-ca](https://smallstep.com/docs/step-ca/) — a small CA server that runs as part of the
infra project (`infra/docker-compose.yml`) — which installs its root into your OS/browser
trust stores, then issues a cert covering `localhost`, `hydra`, and the two hostnames below,
signed by it. Nothing here is committed to git or shared between machines — every developer
runs this once:

```bash
# Install the step CLI first if you don't have it: brew install step / see https://smallstep.com/docs/step-cli/installation
docker network create whale-sightings-net    # one-time: shared network, see "Infra project" below
./scripts/setup-tls.sh    # or scripts/setup-tls.ps1 on Windows PowerShell
```

This writes `certs/localhost.pem` and `certs/localhost-key.pem` (gitignored). Re-run it any
time; it's idempotent — running containers need a restart afterward to pick up a re-issued
cert. `docker-compose.yml`/`infra/docker-compose.yml` mount `certs/` into the relevant
containers, and `uvicorn` (both in Docker and when run directly, see below) is configured to
use them.

### Infra project (Hydra, login-consent, step-ca)

`hydra` and `login-consent` (plus `step-ca`) live in a separate Compose project,
`infra/docker-compose.yml` — see that file's header comment for why. It's joined to the app
project (`docker-compose.yml`) via the `whale-sightings-net` external Docker network created
above, so `service` can still resolve `hydra` by name for JWKS fetches. Bring it up alongside
the app project with `./scripts/dev-up.sh`, or independently with
`docker compose -f infra/docker-compose.yml up --build`.

Hydra and the service identify themselves as `auth.dev.booth-boat.org` and
`api.dev.wombat-sightings.org` respectively (not `localhost`) — this is what
`scripts/setup-tls.sh` issues certs for by default. Since these aren't real public DNS names,
the infra project runs a `dns` service (dnsmasq — see `dnsmasq/whale-sightings.conf` for the
actual records) that answers for them and forwards everything else upstream normally. Point
your machine's resolver at it — on macOS, a scoped resolver (so only these two domains go
through it, not all DNS on the machine) via `/etc/resolver/`:

```bash
sudo mkdir -p /etc/resolver
sudo sh -c 'printf "nameserver 127.0.0.1\nport 53\n" > /etc/resolver/booth-boat.org'
sudo sh -c 'printf "nameserver 127.0.0.1\nport 53\n" > /etc/resolver/wombat-sightings.org'
```

(On Windows/Linux, or if the `dns` container runs on a different machine on the LAN, point
that platform's resolver/DNS settings at wherever it's reachable instead.) A real DHCP+DNS
setup for the trade-show LAN (the same dnsmasq container will likely grow a `dhcp-range=`)
is planned for when the Raspberry Pi hardware is available to test it against a real network
interface — see the roadmap.

The client apps themselves (`client-admin` etc.) are unaffected by any of this — they still
talk to the service via whatever `apiBase` is configured in their own `config.js`
(`localhost` by default) and discover the actual issuer/audience dynamically at login time —
see "OAuth2 login for the
admin client" below.

Browsers trust the result with no warnings. On Windows, `curl` uses the Schannel TLS
backend, which hard-fails when it can't check a certificate's revocation status — locally
issued certs have no CRL/OCSP endpoint to check, so plain `curl https://localhost:8000/...`
will error with `CRYPT_E_NO_REVOCATION_CHECK`. Add `--ssl-no-revoke` to `curl` calls on
Windows (not needed on macOS/Linux, and not an issue for browsers, which soft-fail instead).

### TLS for remote clients

The default cert only covers `localhost`/`127.0.0.1`/`::1`, so a client on another machine
(pointed at the service's address via its `config.js` — see "Running the MQTT client" below)
will still hit a certificate error even once it can reach the service. Two things are needed
to fix that:

1. **Reissue the cert with an extra name covering how remote clients will reach this
   machine**, on the machine running the service. Either a LAN IP:

   ```bash
   ./scripts/setup-tls.sh 192.168.1.23    # use this machine's actual LAN IP
   ```

   or a resolvable hostname — e.g. this machine's mDNS/Bonjour name, which every other
   device on the LAN can already resolve with no DNS server or config of its own (macOS and
   iOS support this out of the box; Linux via `avahi`, usually preinstalled; Windows needs
   Bonjour installed, e.g. bundled with iTunes, or a standalone installer). Find or set the
   name in System Settings → General → Sharing → "Local hostname" on macOS, or check
   `hostname` on Linux (avahi advertises it as `<hostname>.local` by default):

   ```bash
   ./scripts/setup-tls.sh whale-service.local
   ```

   A hostname is worth the extra step over an IP: it keeps working after DHCP hands out a
   new lease, so you're not re-running this and every client's `config.js` every time that
   happens. It only resolves on the local network, though — if `.local` names don't resolve
   on your setup (some conference/guest WiFi blocks the multicast traffic mDNS relies on),
   fall back to the LAN IP.

2. **Get the other machine to trust your step-ca root.** `scripts/setup-tls.sh` already
   writes it to `certs/rootCA.pem` — copy just that file to the other machine (never
   anything from the `step-ca-data` Docker volume, which holds the CA's private key; anyone
   holding that key can mint certs any of your trusting devices will accept for any domain).
   On the other machine, import `rootCA.pem` directly into the OS/browser trust store
   (Keychain Access on macOS, `certmgr`/Group Policy on Windows, `update-ca-certificates`
   plus each browser's own store on Linux — Firefox in particular keeps its own NSS store
   separate from the OS). The other machine doesn't need the `step` CLI or step-ca itself
   installed — it's only ever trusting a cert here, not issuing one.

This only covers the REST API's TLS trust — see "CORS for remote clients" below for the
other piece.

### CORS for remote clients

Even with a trusted cert, the service will still reject cross-origin requests from a
remote client until its origin is added to `CORS_ORIGINS`. Which file to edit depends on
how you're running the service:

- **Via Docker (the default — `docker compose up --build`):** edit `CORS_ORIGINS` directly
  in `docker-compose.yml`. It does **not** read `.env`.
- **Running the service directly (see "Running the service outside Docker" below):** edit
  `CORS_ORIGINS` in your `.env` file instead.

Either way, add the remote client's actual origin (scheme + host + port it's served from),
e.g. `http://192.168.1.23:8080` or, using a resolvable hostname as set up above,
`http://whale-service.local:8080`, as an extra comma-separated entry alongside the existing
`http://localhost:8080,http://localhost:8081,http://localhost:8082,http://localhost:8083`. If you're running the
service via Docker, remember it needs a rebuild (`docker compose up --build`) to pick up
the change, same as any other edit to `docker-compose.yml`.

**Hostname case gotcha:** browsers always send the `Origin` header lowercased, but
`CORS_ORIGINS` is matched with an exact, case-sensitive string comparison — so an entry
like `http://Whale-Service.local:8080` (e.g. pasted straight from `scutil --get
LocalHostName` on macOS, which capitalizes it) will never match and every request gets
silently rejected. The failure is confusing because it doesn't look like a CORS error: the
service logs a normal `200`, but the browser blocks the response before it reaches your
code, so `fetch()` just throws a generic `Failed to fetch` with nothing more specific.
Always lowercase the hostname in `CORS_ORIGINS` (and it doesn't hurt to lowercase it in
`config.js`/`setup-tls.sh` too, for consistency), regardless of how your OS capitalizes it.

If you want to allow clients from anywhere on a LAN subnet rather than enumerating each
machine's IP, set `CORS_ORIGIN_REGEX` instead (or in addition) — it's matched against the
`Origin` header alongside `CORS_ORIGINS`, e.g.:

```
CORS_ORIGIN_REGEX=^http://192\.168\.0\.\d{1,3}:(8080|8081|8082|8083)$
```

## Running the service

```bash
docker compose up --build
```

- Service: https://localhost:8000
- Health check: `curl https://localhost:8000/health`
- Valkey is exposed on `localhost:6379` for debugging with `valkey-cli`.
- The MQTT broker (Mosquitto) requires TLS on both `localhost:8883` (native MQTT protocol,
  `mqtts` — e.g. `mosquitto_sub -p 8883 --cafile certs/rootCA.pem ...`; 8883 is the
  IANA-standard TLS port, what most MQTT client tools default to) and `localhost:9001`
  (MQTT-over-WebSockets, `wss://`, what the browser client uses) — see "The MQTT client"
  below.

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

Long-poll for created or deleted sightings — holds the connection open until there's a
sighting created, or a sighting deleted, after `since`, or `timeout_seconds` elapses.
`lat`/`lon`/`radius_nm` compose with it the same way they do with `GET /sightings` (only
narrowing `created` — a deleted record's location is no longer known, so `deleted` is
reported unfiltered). Returns `200` with `{"created": [...], "deleted": [...]}` (tombstones
only — `id`/`deleted_at`, no sighting data) or `204` (empty) on timeout — used by
`client-long-poll/` instead of MQTT. Doesn't report moderation-status changes (the `updated`
event MQTT/WebSocket clients get from `PATCH .../moderation` — see "Whale Alert connector"
below); `client-long-poll` won't show a Whale Alert moderation change until reloaded, same
category of gap as the delete one used to be:

```bash
curl "https://localhost:8000/sightings/poll?since=2026-01-01T00:00:00Z&timeout_seconds=5"
```

Delete a sighting by id — requires an admin bearer token (see "OAuth2 login for the admin
client" below) or an ingest-scoped one (see "Whale Alert connector" below); a plain
unauthenticated request gets a `401`. An ingest credential specifically may only delete
`whale_alert`-sourced records (`403` otherwise) — a compromised or buggy connector can't
touch local or peer sightings:

```bash
curl -X DELETE https://localhost:8000/sightings/<id> \
  -H "Authorization: Bearer <access token>"
```

Get a single sighting by id:

```bash
curl https://localhost:8000/sightings/<id>
```

Look up a sighting by its source and that source's own id — unauthenticated, same posture as
the endpoint above. This is the dedup/correlation lookup an ingestion process (e.g. the
Whale Alert connector, below) uses to decide whether it's already seen a given upstream
record:

```bash
curl https://localhost:8000/sightings/by-source/whale_alert/<upstream-id>
```

Update a sighting's moderation status — ingest-scoped bearer token required (see "Whale
Alert connector" below); 404 if the sighting doesn't exist, 409 if it isn't
`whale_alert`-sourced:

```bash
curl -X PATCH https://localhost:8000/sightings/<id>/moderation \
  -H "Authorization: Bearer <ingest access token>" \
  -H "Content-Type: application/json" \
  -d '{"moderation_status": "confirmed"}'
```

Get stats (count, oldest, newest sighting, plus a per-source breakdown) — used by the admin
client:

```bash
curl https://localhost:8000/sightings/stats
```

## Running the clients

All four static clients (`client-mqtt/`, `client-long-poll/`, `client-ws/`, `client-admin/`)
build and run as part of `docker-compose.yml` — `docker compose up --build` (or
`./scripts/dev-up.sh`) brings them up along with everything else, no separate
static-file-server steps needed. `client-mqtt`/`client-long-poll`/`client-ws` also get
`shared/sightings-shared.js` — the rendering/form/filter code common to all three — copied
into their image at build time (see their Dockerfiles), so only each client's own live-sync
mechanism (MQTT, long-polling, or a direct WebSocket) needs reading to see what's different
between them.

Each client's `config.js` is templated from environment variables (`API_BASE` and, for
`client-mqtt`/`client-ws`, `MQTT_WS_URL`/`WS_URL`) at container start (see e.g.
`client-mqtt/docker-entrypoint.sh`) rather than a file you copy and edit by hand — to point a
client at a service running elsewhere, edit the relevant service's `environment:` block in
`docker-compose.yml` (or an override file, same pattern `docker-compose.override.yml` already
uses for `CORS_ORIGINS`) and restart; no rebuild needed, since the same image just gets
different environment.

(For quick edits without rebuilding, any client can still be run directly —
`cd client-mqtt && python3 -m http.server 8081`, etc. `client-mqtt`/`client-long-poll`/
`client-ws` need `shared/sightings-shared.js` copied alongside `index.html` first, since that
normally happens at Docker build time; without a `config.js` created by hand from
`config.example.js`, `app.js` falls back to its hardcoded `localhost` defaults.)

### The MQTT client

Open http://localhost:8081. The form auto-fills location/time via the browser Geolocation API
(`http://localhost` is treated as a secure context, so this works without HTTPS locally — AWS
deployment will need HTTPS for Geolocation to keep working).

The list of sightings can be filtered to the last N hours and/or to within a radius (in
nautical miles) of a point — "Use current location" fills in the radius filter's
latitude/longitude, same as the report form. The list is also plotted on a map
(Leaflet + OpenStreetMap tiles, loaded from a CDN) with a pin per sighting — the map
re-fits itself to whatever sightings are currently loaded whenever the list changes.

The list, count, and map also live-refresh automatically: the service publishes to the
Mosquitto broker whenever any client creates or deletes a sighting, and every open
client subscribes over MQTT-over-WebSockets (`wss://localhost:9001`) and re-runs its
current filtered query on each notification. The manual Refresh button still works too.

### Try the live sync

Open `http://localhost:8081` in three browser tabs (or windows), each running the same
client. Submit a sighting in one tab — the other two update their table, count, and map
automatically within moments, with no manual refresh. Deleting a sighting in any tab
updates the others the same way. Filters set in a tab (time window / radius) are still
respected on each live refresh, same as a manual Refresh.

### The long-poll client

A second public client — same features as the MQTT one (report, lookup, filters, map), but
live-updated by repeatedly calling `GET /sightings/poll` instead of subscribing to MQTT. No
persistent connection, no broker — see the endpoint's docstring in
`service/app/routers/sightings.py` for how the long-held request itself works.

Open http://localhost:8082. Open your browser's Network tab and watch: each
`GET /sightings/poll` request stays pending for up to 25 seconds, resolving either with a
match (as soon as one exists) or `204` on timeout — either way, the client immediately issues
the next one. No WebSocket connection appears, unlike the MQTT client's tab.

### The WebSocket client

A third live-sync mechanism: a direct WebSocket connection to the service itself
(`GET /sightings/ws` — see `service/app/routers/sightings.py`'s `sightings_ws` and
`app/ws.py`'s `ConnectionWsBroadcaster`), no broker in between at all — unlike `client-mqtt`,
which depends on the Mosquitto broker to relay events. Same report/lookup/filter/map features
as the other two.

Open http://localhost:8083. Both `created` and `deleted` events push immediately, same as the
MQTT client and, since `GET /sightings/poll` now reports both, the long-poll client too.
One real difference worth noting in the code: the native WebSocket API (unlike the `mqtt.js`
library the MQTT client uses) doesn't reconnect on its own after a dropped connection —
`client-ws/app.js`'s `connectWs()` has to do that by hand. That tradeoff (no broker to run,
but the client owns its own reconnect logic) is the point of this client existing alongside
the MQTT one.

### Try the live sync, across all three clients

Open the MQTT client (`http://localhost:8081`), the long-poll client
(`http://localhost:8082`), and the WebSocket client (`http://localhost:8083`) side by side.
Submit a sighting in any one — it appears in all three, via three completely different
mechanisms. Deleting works the same way in all three now too. This is the whole point of
having all three: same API, same UI, three different ways a client can find out something
changed.

### The admin client

A separate static site for demo purposes: it shows sighting counts plus the oldest/newest
sighting, lets you load canned demo data with one click, and can clear all sightings to
reset between demos. Open http://localhost:8080. The canned scenarios live in the
`SCENARIOS` array in `client-admin/app.js` — edit or add to them for your own demo needs.

Deleting sightings (individually or via "Clear all sightings") requires signing in — see
the next section. Stats and demo-data loading don't; those stay open to any client, same
as the public client.

## OAuth2 login for the admin client

The infra project (`infra/docker-compose.yml` — see "Infra project" above) runs a
self-hosted Ory Hydra (the OAuth2 authorization server) plus a small `login-consent` app for
its login screen. One extra one-time step registers the admin client with Hydra:

```bash
./scripts/register-hydra-client.sh
```

Safe to re-run any time; it deletes and re-creates the client. Re-run it if you change
where the admin client or the service is served from (pass the admin origin and API base
as arguments — see the script's header comment). Hydra rejects an authorize request whose
requested audience isn't in the client's registered list, so this must stay in sync with
`service`'s `OAUTH_EXPECTED_AUDIENCE` in `docker-compose.yml` — a mismatch here shows up as
a generic "the OAuth 2.0 Authorization request must be aborted" (or, more specifically,
"Requested audience ... has not been whitelisted") error during login, not a build/connection
failure.

With that done, clicking "Clear all sightings" in the admin client with no active session
redirects to a login screen (`admin`/`change-me` by default — see `ADMIN_USERNAME`/
`ADMIN_PASSWORD` in `infra/docker-compose.yml`), then redirects back once you're signed in. The
delete you clicked is **not** retried automatically — click it again once you're back,
and it succeeds this time. This two-step flow is deliberate: it's what makes the
authorization boundary visible in a demo, rather than hiding it behind an automatic retry.

The access token lives only in an in-memory JS variable in the admin client (never
`localStorage`/`sessionStorage`), so a page reload loses it and the next delete attempt
repeats the login redirect. The public client's delete button is intentionally left
unauthenticated — clicking it still sends a plain `DELETE` with no token, which now gets
rejected with a `401`, demonstrating that only the admin client can actually delete.

### Forcing a fresh login for a demo

Reloading the admin page clears its in-memory token, but Hydra itself also remembers a
successful login for `LOGIN_REMEMBER_SECONDS` (`login-consent`'s setting in
`docker-compose.yml`, defaults to `3600` = 1 hour). Within that window, a reload-then-click
still redirects through Hydra, but Hydra replies `skip: true` and `login-consent`
auto-accepts — so the delete works, but you never see the login form itself, which makes
for a less convincing demo.

To force the actual form to reappear immediately, revoke the remembered session directly:

```bash
curl -sk -X DELETE "https://localhost:4445/admin/oauth2/auth/sessions/login?subject=admin"
```

Or lower `LOGIN_REMEMBER_SECONDS` in `docker-compose.yml` (e.g. to `60`) if you'd rather
the form reappear on its own shortly after each login, without running that command every
time.

## Whale Alert connector

`whale-alert-connector` polls the real [Whale Alert](https://whalealert.org/) service,
publishes what it finds as sightings on this service (tagged `source.type: "whale_alert"`),
and tracks Whale Alert's own moderation lifecycle (`Unreviewed`/`Confirmed`/`Unconfirmed`/
`Deleted`) as updates to the same record rather than duplicate creates — a `Deleted` upstream
sighting becomes a real `DELETE` here, not a fourth `moderation_status` value. It's
**opt-in**: a plain `docker compose up` or `./scripts/dev-up.sh` never runs it, never talks
to Whale Alert, and never needs Whale Alert credentials.

`service/app/ingest/whale_alert_client.py` is the only file in this repo that ever makes a
real HTTP call to Whale Alert's production API. Everything else in `service/app/ingest/` —
`hydra_token_client.py`, `service_client.py`, `mapping.py`, `poller.py` — only ever talks to
this service or our own Hydra.

### One-time setup

1. Register a separate Hydra client for the connector — distinct from the admin client's
   browser-based login, this one authenticates with a client ID/secret pair
   (`client_credentials` grant, `sightings:ingest` scope), no browser or redirect involved:

   ```bash
   ./scripts/register-hydra-ingest-client.sh
   ```

   Safe to re-run (deletes and re-creates the client, printing a fresh secret each time).
   Copy the printed client ID/secret for the next step.

2. Copy the connector's env template and fill it in:

   ```bash
   cp service/.env.whale-alert-connector.example service/.env.whale-alert-connector
   ```

   - `WHALE_ALERT_CLIENT_ID`/`WHALE_ALERT_CLIENT_SECRET` — the Whale Alert Group-Admin API
     credential you already hold. This is a completely separate credential from the Hydra
     one below; **Claude/an AI assistant should never be asked to supply, use, or call this
     credential against the real Whale Alert API** — that's this repo's standing rule for
     this integration.
   - `INGEST_HYDRA_CLIENT_ID`/`INGEST_HYDRA_CLIENT_SECRET` — the ID/secret printed by step 1.

   This file is gitignored (`service/.env.whale-alert-connector` matches `.env.*` in
   `.gitignore`) — only the `.example` template is committed.

### Running it

Standalone (just the connector plus its real dependencies — valkey, service, hydra):

```bash
docker compose --profile whale-alert up --build whale-alert-connector
```

Or as part of the full dev stack:

```bash
./scripts/dev-up.sh --with-whale-alert
```

Either way, watch its logs for a full poll cycle (`docker compose logs -f
whale-alert-connector`); real Whale Alert sightings within `WHALE_ALERT_BBOX` (defaults to
greater Puget Sound plus the San Juan Islands) should appear as teal pins with `Source:
whale_alert` in any map client (see "Source-aware map pins" below), and the admin client's
stats panel should show a non-zero Whale Alert count.

### Startup options at a glance

`--with-whale-alert` and `--with-whale-alert-mock` just control which **containers** start.
What the connector actually talks to is decided separately, by `WHALE_ALERT_API_BASE_URL` in
`service/.env.whale-alert-connector` (defaults to the real API). The two flags are
independent and can technically be passed together, but there's no real use for that beyond
the mock-testing row below — the connector only ever has one configured target, so running
both containers doesn't mean "talks to both."

| Command | Connector running? | Mock running? | Connector's target | What you'll see |
|---|---|---|---|---|
| `./scripts/dev-up.sh` | No | No | — | Local sightings only, as blue dots. No Whale Alert data at all. |
| `./scripts/dev-up.sh --with-whale-alert-mock` | No | Yes | — | Same as above — the mock just sits there; nothing polls it without the connector also running. Useful for poking at it directly with `curl`. |
| `./scripts/dev-up.sh --with-whale-alert` | Yes | No | Real Whale Alert (default `WHALE_ALERT_API_BASE_URL`) | Real Whale Alert sightings as teal dots. Needs real credentials in `.env.whale-alert-connector`. |
| `./scripts/dev-up.sh --with-whale-alert --with-whale-alert-mock`, `.env.whale-alert-connector`'s `WHALE_ALERT_API_BASE_URL` set to `http://whale-alert-mock:9100` (see "Testing safely against a local mock" below) | Yes | Yes | The local mock | The mock's fixture sightings as teal dots — safe to repeat. `POST http://localhost:9100/_mock/advance` to watch moderation updates/deletes happen. |

Everything above composes with `docker compose --profile ... up --build`/`down` too, if you'd
rather skip `dev-up.sh`/`dev-down.sh` and drive Compose directly — the profiles are exactly
`whale-alert` and `whale-alert-mock`, same names either way. `./scripts/dev-down.sh` tears
down both regardless of which flags brought them up (it runs `docker compose --profile '*'
down`, not a plain `down`, specifically so nothing gets orphaned).

### Testing safely against a local mock

`whale-alert-mock` (`service/app/ingest/mock_whale_alert_server.py`) fakes just enough of
Whale Alert's real API shape — `POST /auth/token`, `GET /sightings` — to exercise the
connector end-to-end without ever touching production. Seeded from real, already-saved,
PII-redacted example records, plus a few synthesized siblings placed inside the default
bbox so there's something in-region to create. This is the one piece of the whole
integration safe to run and iterate on directly, including by an AI assistant, since it's a
local fake, not Whale Alert's production service.

```bash
docker compose --profile whale-alert-mock up --build whale-alert-mock
```

Point the connector at it instead of the real API — in `service/.env.whale-alert-connector`:

```
WHALE_ALERT_API_BASE_URL=http://whale-alert-mock:9100
WHALE_ALERT_CLIENT_ID=mock-client-id
WHALE_ALERT_CLIENT_SECRET=mock-client-secret
```

`whale-alert-mock` has its own profile (`whale-alert-mock`), deliberately separate from the
connector's (`whale-alert`), so the two toggle independently — bring up either alone, or
both together (`docker compose --profile whale-alert --profile whale-alert-mock up --build`).
`POST http://localhost:9100/_mock/advance` steps every fixture's moderation status forward
one notch (capped at Deleted) between poll cycles — real captured examples are static
snapshots and can't demonstrate a transition on their own, so this is what lets you actually
watch the connector's `PATCH .../moderation` and `DELETE` paths fire, not just its create
path. `POST http://localhost:9100/_mock/reset` restores the original fixture data.

### How it decides what to do

Whale Alert's API has no "last modified" field to cursor forward from — only `created`
(submission time) — so instead of an incremental cursor, every poll cycle re-scans a fixed
trailing window (`WHALE_ALERT_LOOKBACK_DAYS`, default 14) across all four moderation
statuses, filtered by `WHALE_ALERT_BBOX`. For each result: look it up via `GET
/sightings/by-source/whale_alert/{id}`; not found → create; found with a different mapped
status → `PATCH .../moderation`; mapped to Deleted → `DELETE`, plus a permanent note in a
Valkey set (`ingest:whale_alert:retired`) so that upstream id is never recreated on a later
cycle once it's gone.

### Source-aware map pins

Every sighting's marker on `client-mqtt`/`client-long-poll`/`client-ws`'s map is now a small
colored dot instead of a default pin, keyed by `source.type`: blue for `local`, amber for
`peer`, teal for `whale_alert` — and each popup gains a `Source: ...` line. `client-admin`'s
stats panel shows a Local/Peer/Whale Alert breakdown alongside the existing count/oldest/
newest.

## peer-service

`peer-service` is a simulated second system, built to demonstrate this API describing
itself rather than a client needing to know its shape in advance. On startup it fetches
this service's root document (`GET /` with `Accept: application/json` — see "Data model"
below for a hint of the shape, or just curl it) and reads `sightings:create`/
`sightings:live-sync` straight out of `_links` — it never hardcodes `/sightings` or
`/sightings/ws`. It then runs two things at once:

- **Generates sightings** for a simulated moving pod, walking a small fixed set of
  waypoints (`peer-service/route.py`) and posting one interpolated position every
  `GENERATE_INTERVAL_SECONDS`. No `source` field in the payload — the service derives
  `source.type: "peer"` and `source.peer_id` purely from the bearer token's own claims (see
  "Whale Alert connector" above for the same anti-spoofing pattern), so peer-service can't
  self-declare an identity any more than the Whale Alert connector can.
- **Subscribes to live-sync** (the same WebSocket `client-ws` uses) and logs every
  `created`/`updated`/`deleted` event it receives — including its own posted sightings,
  since the broadcaster doesn't exclude the connection that caused the event. Reconnects on
  a dropped connection with a fixed delay, mirroring `client-ws/app.js`'s own hand-rolled
  reconnect exactly.

No FastAPI, no host port — its container logs are the demo surface
(`docker compose logs -f peer-service`). It's opt-in, like `whale-alert-connector` and
`whale-alert-mock` (`profiles: ["peer-service"]`) — a plain `docker compose up`/
`./scripts/dev-up.sh` skips it, so its Hydra client doesn't need to already be registered
just to bring up the rest of the stack.

### One-time setup

Register its Hydra client (`client_credentials`, `peer:write` scope — the same shape as the
Whale Alert connector's ingest client, just a different scope):

```bash
./scripts/register-hydra-peer-client.sh
```

Safe to re-run (deletes and re-creates the client, printing a fresh secret each time). Then
copy the printed client ID/secret into `peer-service/.env`:

```bash
cp peer-service/.env.example peer-service/.env
```

This file is gitignored — only `.env.example` is committed. These credentials only ever
authenticate to this repo's own service and Hydra, never a third party.

### Running it

```bash
docker compose --profile peer-service up --build
```

or as part of the full dev stack:

```bash
./scripts/dev-up.sh --with-peer-service
```

Either way, watch its logs for a discovery fetch, periodic "Posted sighting" lines, and a
"Connected to live-sync" line (`docker compose logs -f peer-service`); its sightings should
appear as amber dots in any map client (see "Source-aware map pins" above), and
`client-admin`'s stats panel should show a non-zero Peer count. `client-admin`'s "Clear all
sightings" leaves peer sightings in place, same as Whale Alert ones — there's no formal
peer-registration/delete-authority subsystem yet (an intentional follow-on), so peer data is
treated as permanent for this demo
regardless of who's asking.

### Running it standalone, on a second machine

Since all of its config is env-var driven (`peer-service/config.py`), running it on a
second LAN machine — pointed at the first machine's real `dev.` hostnames instead of
Docker-internal names — needs no new compose file or tooling, just a different invocation:

```bash
docker build -t peer-service ./peer-service
docker run --rm \
  -e API_BASE=https://api.dev.wombat-sightings.org:8000 \
  -e HYDRA_TOKEN_URL=https://auth.dev.booth-boat.org:4444/oauth2/token \
  -e HYDRA_AUDIENCE=https://api.dev.wombat-sightings.org:8000 \
  -e PEER_CLIENT_ID=<from the registration script> \
  -e PEER_CLIENT_SECRET=<from the registration script> \
  -v /path/to/rootCA.pem:/rootCA.pem:ro \
  -e CA_BUNDLE_PATH=/rootCA.pem \
  peer-service
```

Three manual prerequisites on that second machine, same as any remote client (see "TLS for
remote clients" and "Infra project" above): its resolver needs to reach the `dev.` hostnames
(either point it at the `dns` service or add host-file entries), it needs to trust the
step-ca root (`rootCA.pem`, copied out of band — never anything from the `step-ca-data`
Docker volume), and it needs the Hydra client ID/secret copied out of band too (never
committed, same as the local `.env` file).

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
  "created_at": "server-assigned, set once at insertion",
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
  "images": [],
  "source": {
    "type": "local | peer | whale_alert",
    "peer_id": "which peer deployment reported this (peer sightings only) | null",
    "upstream_id": "that source's own id for this sighting, e.g. Whale Alert's numeric id | null"
  },
  "moderation_status": "unreviewed | confirmed | unconfirmed | null"
}
```

Coordinates are in GeoJSON order: `[longitude, latitude]`.

`source` defaults to `{"type": "local", "peer_id": null, "upstream_id": null}` for anything
submitted through the public report form or `POST /sightings` without an ingest-scoped
bearer token. `whale_alert`-sourced records (see "Whale Alert connector" below) are the only
ones with a non-null `moderation_status`, tracking Whale Alert's own moderation lifecycle —
there's deliberately no `"deleted"` value here; a Whale Alert sighting moving to its
"Deleted" state maps to a real `DELETE /sightings/{id}` instead (restricted to
`whale_alert`-sourced records for an ingest-authenticated caller — see below).

`created_at` is distinct from `sighting.location.geometry.properties.datetime`: the latter
is user-editable and backdatable (the report form supports "reporting a sighting after the
fact"), the former is set once, server-side, at insertion and never changes. `since_hours`
on `GET /sightings` filters on the sighting's own datetime — "what did people see
recently." `GET /sightings/poll` filters on `created_at` — "what's new in the database" —
since a backdated sighting is still brand-new data the instant it's created.

## Roadmap

This project is being built in stages:

1. **Done**: collect sightings via a form, persist in Valkey, list all sightings, delete a
   sighting, and show them on a map.
2. **Done**: filter sightings by time window (`since_hours`, both in the API and the client).
3. **Done**: filter sightings by location — within Y nautical miles of a point
   (`lat`/`lon`/`radius_nm`, both in the API and the client), composable with the time
   filter. Filtering within an arbitrary defined region is still future work.
4. Optionally swap or offer a PostgreSQL storage backend behind the same storage interface.
5. **Done (partial)**: OAuth2/OIDC via a self-hosted Ory Hydra now gates
   `DELETE /sightings/{id}` to admin-only (see "OAuth2 login for the admin client" above).
   The public client's `POST`/observer identity is untouched — replacing the placeholder
   observer id with an authenticated identity is still future work.
6. Deploy the service to AWS.
7. **Done**: a second public client (`client-long-poll/`) demonstrating long-polling
   (`GET /sightings/poll`) as an alternative to `client-mqtt/`'s push-based live sync —
   same API, same UI, two different mechanisms for a client to learn something changed.
   MQTT topic segmentation (so a client can subscribe to only what it cares about) is a
   related, still-open follow-up. **Done**: `/sightings/poll` reports both newly *created*
   sightings and tombstones for newly *deleted* ones (a `PollResult` with `created`/`deleted`
   lists — see its docstring), so `client-long-poll` now reflects deletions live too, the
   same as `client-mqtt`/`client-ws`.
8. **In progress**: moving the infra project (`infra/docker-compose.yml` — Hydra, step-ca,
   `dns`) onto a Raspberry Pi acting as the router for an ad hoc trade-show LAN. TLS
   (step-ca, **done**) and DNS (**done**) are usable in dev today; DHCP is planned for the
   same `dns` (dnsmasq) service but deliberately untested until the Pi hardware is available
   to try it against a real network interface, rather than risk conflicting with an existing
   router's DHCP server on a shared dev network.
9. **Done**: a third public client (`client-ws/`) demonstrating a direct WebSocket connection
   to the service (`GET /sightings/ws`) as a third live-sync mechanism alongside
   `client-mqtt/`'s broker-mediated push and `client-long-poll/`'s pull-based polling — no
   broker involved at all, at the cost of the client having to handle its own reconnection
   (unlike `mqtt.js`, the native WebSocket API doesn't do that for you). Reflects both
   creates and deletes live, same as `client-mqtt`.
10. **Done**: real ingestion from [Whale Alert](https://whalealert.org/) — see "Whale Alert
    connector" above. A generic three-way `source` (`local`/`peer`/`whale_alert`) and a
    `require_scope()` OAuth2 dependency factory (alongside the existing admin-role check)
    were built as part of this, so a later peer-service demo can reuse both rather than
    re-deriving them. Known gaps, left deliberately for now: `GET /sightings/poll`
    (long-poll) doesn't reflect a Whale Alert moderation-status change, only creates/deletes
    (see its docs above); Whale Alert's own polling is a fixed 14-day re-scan every cycle
    rather than an incremental cursor, since its API has no "last modified" field to cursor
    from.
11. **Done**: a simulated peer-service demo (`peer-service/`), showing JSON-LD + HATEOAS
    discovery — a second container generating moving-pod sightings, discovering this
    service's capabilities from its root document instead of hardcoding endpoints,
    authenticating via Hydra client-credentials, and subscribing to live-sync. Along the
    way, the root document's and every sighting's own `_links`/`@id` were switched from a
    fixed `public_api_base_url` setting to the actual incoming request's own base URL — a
    same-host peer container reaching the service via its Docker-internal name got back
    links built for the browser-facing hostname instead, which it can't resolve. A formal
    peer-registration/webhook-push subsystem, and real delete authority over a peer's own
    data, remain intentional follow-ons — peer sightings are permanent (undeletable via this
    API) for this demo.
