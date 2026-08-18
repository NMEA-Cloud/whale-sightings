# Whale Sightings

A whale-sighting tracking system: a FastAPI service (in Docker) backed by Valkey, paired
with a simple web client that runs outside the container. Both run locally for
development today; the service is intended to eventually deploy to AWS.

## Project layout

- `service/` — FastAPI application, persists sightings in Valkey, runs in Docker.
- `client-mqtt/` — vanilla HTML/CSS/JS public client, live-updated via MQTT over WebSockets, served by a plain static file server (no build step).
- `client-long-poll/` — same public client, live-updated via `GET /sightings/poll` long-polling instead of MQTT.
- `shared/` — rendering/form/filter JS shared by `client-mqtt/` and `client-long-poll/`; see "Serving the shared client code" below.
- `client-admin/` — vanilla HTML/CSS/JS admin client (stats + demo data loading), also static, no build step.
- `hydra/` — config for the self-hosted Ory Hydra OAuth2 authorization server.
- `login-consent/` — small FastAPI app serving Hydra's login/consent screens.
- `dnsmasq/` — config for the `dns` service (see `infra/docker-compose.yml`) that resolves
  the `dev.`-subdomain hostnames below.
- `docker-compose.yml` — the **app** project (Compose project name `wombat-sightings`): runs
  `service`, `valkey`, and `mqtt`. Neither client is containerized.
- `infra/docker-compose.yml` — the **infra** project (Compose project name `booth-boat`): runs
  `step-ca`, `hydra`, `login-consent`, and `dns`. Split into its own project so this rehearses
  the eventual move of this infrastructure onto a separate physical machine (a Raspberry Pi
  acting as a trade-show LAN router) — see that file's header comment. Joined to the app
  project via the `whale-sightings-net` external Docker network so `service` can still
  resolve `hydra` by name for JWKS fetches.

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) (with Compose) — runs the service, Valkey,
  and Mosquitto.
- [step CLI](https://smallstep.com/docs/step-cli/installation) — requests locally-trusted TLS
  certs from the project's step-ca container (see [TLS setup](#tls-setup-do-this-first)
  below).
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
`http://localhost:8080,http://localhost:8081,http://localhost:8082`. If you're running the
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
CORS_ORIGIN_REGEX=^http://192\.168\.0\.\d{1,3}:(8080|8081|8082)$
```

## Running the service

```bash
docker compose up --build
```

- Service: https://localhost:8000
- Health check: `curl https://localhost:8000/health`
- Valkey is exposed on `localhost:6379` for debugging with `valkey-cli`.
- The MQTT broker (Mosquitto) is exposed on `localhost:1883` (plain MQTT, e.g. for
  `mosquitto_sub`) and `localhost:9001` (MQTT-over-WebSockets, what the browser client
  uses) — see "Running the MQTT client" below.

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

Long-poll for new sightings — holds the connection open until there's a sighting newer
than `since`, or `timeout_seconds` elapses. `lat`/`lon`/`radius_nm` compose with it the
same way they do with `GET /sightings`. Returns `200` with the match(es) or `204` (empty)
on timeout — used by `client-long-poll/` instead of MQTT:

```bash
curl "https://localhost:8000/sightings/poll?since=2026-01-01T00:00:00Z&timeout_seconds=5"
```

Delete a sighting by id — requires an admin bearer token (see "OAuth2 login for the admin
client" below); a plain unauthenticated request gets a `401`:

```bash
curl -X DELETE https://localhost:8000/sightings/<id> \
  -H "Authorization: Bearer <access token>"
```

Get a single sighting by id:

```bash
curl https://localhost:8000/sightings/<id>
```

Get stats (count, oldest, newest sighting) — used by the admin client:

```bash
curl https://localhost:8000/sightings/stats
```

## Serving the shared client code

`client-mqtt/` and `client-long-poll/` (below) both load `shared/sightings-shared.js` — the
rendering/form/filter code common to both, so only each client's own live-sync mechanism
(MQTT vs. long-polling) needs reading to see what's different between them. A plain
`python3 -m http.server` can only serve files inside the directory it's rooted at, so this
can't just be a relative `../shared/...` import from each client — it's served from its own
tiny static server instead, loaded cross-origin the same way the Leaflet/MQTT scripts
already are, from a CDN. Start it before either client:

```bash
cd shared
python3 -m http.server 8083
```

## Running the MQTT client

The client is a static site with no build step, and is not part of `docker-compose.yml`.
Run it with any static file server, e.g.:

```bash
cd client-mqtt
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

The client points at the service via `API_BASE` (defined in `shared/sightings-shared.js`)
and the MQTT broker via `MQTT_WS_URL` (defined in `client-mqtt/app.js`), with
`https://localhost:8000` / `ws://localhost:9001` as the defaults. To point this client at a
service running elsewhere (e.g. on another machine on your network), copy
`client-mqtt/config.example.js` to `client-mqtt/config.js` (gitignored, like `.env`) and
edit the values there — no need to touch either `app.js` itself.

### Try the live sync

Open `http://localhost:8080` in three browser tabs (or windows), each running the same
client. Submit a sighting in one tab — the other two update their table, count, and map
automatically within moments, with no manual refresh. Deleting a sighting in any tab
updates the others the same way. Filters set in a tab (time window / radius) are still
respected on each live refresh, same as a manual Refresh.

## Running the long-poll client

A second public client — same features as the MQTT one (report, lookup, filters, map), but
live-updated by repeatedly calling `GET /sightings/poll` instead of subscribing to MQTT. No
persistent connection, no broker — see the endpoint's docstring in
`service/app/routers/sightings.py` for how the long-held request itself works.

```bash
cd client-long-poll
python3 -m http.server 8082
```

Then open http://localhost:8082 (requires the shared static server from above to be
running too). Open your browser's Network tab and watch: each `GET /sightings/poll`
request stays pending for up to 25 seconds, resolving either with a match (as soon as one
exists) or `204` on timeout — either way, the client immediately issues the next one. No
WebSocket connection appears, unlike the MQTT client's tab.

Configured the same way as the MQTT client — copy `client-long-poll/config.example.js` to
`client-long-poll/config.js` to point it at a service elsewhere.

### Try the live sync, across both clients

Open the MQTT client (`http://localhost:8080`) and the long-poll client
(`http://localhost:8082`) side by side. Submit a sighting in either — it appears in both,
via two completely different mechanisms. Deleting works the same way. This is the whole
point of having both: same API, same UI, two different ways a client can find out
something changed.

## Running the admin client

The admin client is a separate static site (also no build step) for demo purposes: it
shows sighting counts plus the oldest/newest sighting, lets you load canned demo data
with one click, and can clear all sightings to reset between demos. Run it on a
different port than the public client:

```bash
cd client-admin
python3 -m http.server 8081
```

Then open http://localhost:8081. Like the public client, it points at the service via
`API_BASE` in `client-admin/app.js` (defaulting to `https://localhost:8000`), overridable the
same way — copy `client-admin/config.example.js` to `client-admin/config.js` and edit it. The canned
scenarios live in the `SCENARIOS` array in `client-admin/app.js` — edit or add to them for your
own demo needs.

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
  "images": []
}
```

Coordinates are in GeoJSON order: `[longitude, latitude]`.

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
   related, still-open follow-up.
8. **In progress**: moving the infra project (`infra/docker-compose.yml` — Hydra, step-ca,
   `dns`) onto a Raspberry Pi acting as the router for an ad hoc trade-show LAN. TLS
   (step-ca, **done**) and DNS (**done**) are usable in dev today; DHCP is planned for the
   same `dns` (dnsmasq) service but deliberately untested until the Pi hardware is available
   to try it against a real network interface, rather than risk conflicting with an existing
   router's DHCP server on a shared dev network.
