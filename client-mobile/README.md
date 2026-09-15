# client_mobile

The native mobile client for [whale-sightings](../README.md) — a Flutter/iOS app, alongside
the repo's static web clients (`client-mqtt/`, `client-long-poll/`, `client-ws/`,
`client-sse/`, `client-admin/`). Unlike those, it isn't built or served via Docker — it's a
normal Flutter app you run directly with `flutter run`/Xcode.

**v1 scope (current):** report a sighting, view the list (with pull-to-refresh and automatic
live-sync via Server-Sent Events — see "Live-sync" below), and delete a sighting after OAuth2
PKCE login (see the root README's "OAuth2 login for the admin client"). Target is the **iOS
Simulator only** for now; physical-device support needs a LAN-reachable TLS cert (see the
root README's "TLS for remote clients" section) and hasn't been set up for this client yet.

## Prerequisites

1. The backend running — from the repo root: `./scripts/dev-up.sh` (or plain
   `docker compose up --build`). This app talks to `https://localhost:8000` directly; it
   doesn't go through Docker itself.
2. An iOS Simulator, booted.
3. **The Simulator must trust this project's local dev CA** (see below) — the service is
   HTTPS-only, and without this every request fails with a TLS handshake error.

## Trusting the local dev CA in the Simulator

The repo's `scripts/setup-tls.sh` (run once, from the repo root, before any of this) writes
`certs/rootCA.pem` — the CA root every client should trust. The Simulator has its own
separate trust store from the host Mac, so it needs to be told about this CA explicitly:

```
xcrun simctl keychain booted add-root-cert /path/to/whale-sightings/certs/rootCA.pem
```

This installs *and* trusts it as a root in one step, targeting whichever Simulator is
currently booted. It's per-Simulator-instance — repeat this after erasing a Simulator
("Erase All Content and Settings") or creating a new one.

To verify it worked: with the backend running, `xcrun simctl openurl booted
https://localhost:8000/health` should load cleanly in the Simulator's Safari with no
certificate warning.

## Running

```
flutter pub get
flutter run -d <device-id-or-name>
```

(`flutter devices` lists available targets, including booted Simulators.)

Geolocation pre-fills the report form's latitude/longitude — grant location access when
prompted. On a fresh Simulator with no location ever configured, geolocation resolves to a
hardcoded Apple default (`37.785834, -122.406417`, downtown San Francisco), not the host
Mac's real location. To simulate a specific spot instead:

```
xcrun simctl location booted set <lat>,<lon>
```

## Live-sync

The list screen live-updates via Server-Sent Events on the existing `GET /sightings`
endpoint (`Accept: text/event-stream`), the same mechanism `client-sse/` uses — see
`lib/sse_client.dart`. No setup beyond the steps above; it rides the same
`https://localhost:8000` connection and TLS trust as every other request this app makes.
