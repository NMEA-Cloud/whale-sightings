# client_mobile

The native mobile client for [whale-sightings](../README.md) — a Flutter/iOS app, alongside
the repo's static web clients (`client-mqtt/`, `client-long-poll/`, `client-ws/`,
`client-sse/`, `client-admin/`). Unlike those, it isn't built or served via Docker — it's a
normal Flutter app you run directly with `flutter run`/Xcode.

**v1 scope (current):** report a sighting, view the list (with pull-to-refresh and automatic
live-sync via Server-Sent Events — see "Live-sync" below), and delete a sighting after OAuth2
PKCE login (see the root README's "OAuth2 login for the admin client"). The app talks to
`https://api.dev.whale-sightings.org:8000` (see `lib/api_client.dart`) rather than
`localhost`, so the same code path works from the **iOS Simulator** and, once the extra
setup in "Physical-device support" below is done, a **physical device**. Physical-device
support is documented but not yet verified end-to-end — see that section.

## Prerequisites

1. The backend running — from the repo root: `./scripts/dev-up.sh` (or plain
   `docker compose up --build`). This app doesn't go through Docker itself; it just needs
   the backend's `https://api.dev.whale-sightings.org:8000` reachable (see "TLS setup" and
   "Infra project" in the root README for how that hostname resolves).
2. An iOS Simulator, booted (or a physical device — see "Physical-device support" below).
3. **Your target must trust this project's local dev CA** (see below) — the service is
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
https://api.dev.whale-sightings.org:8000/health` should load cleanly in the Simulator's
Safari with no certificate warning.

## Physical-device support

The app itself needs no per-target configuration (see "v1 scope" above) — what a physical
device additionally needs, beyond what the Simulator gets for free, is for the LAN to
resolve `api.dev.whale-sightings.org`/`auth.dev.whale-auth.org` to the right machine, and
for the device to trust the CA root. This hasn't been verified end-to-end yet (tracked
separately, pending an infra host change — see the root README's dnsmasq section), but the
procedure is:

1. **Device and the machine running `infra/docker-compose.yml` must be on the same LAN.**
2. **Confirm `dnsmasq/whale-sightings.conf` resolves both dev hostnames to that machine's
   real LAN IP**, not `127.0.0.1` — see that file's comment for why, and restart the infra
   project's `dns` service after editing it. (Whoever is running the infra project owns
   keeping this current — it's not something client-mobile itself can fix.)
3. **Point the device's Wi-Fi DNS at that same LAN IP**: Settings → Wi-Fi → (i) next to the
   network → Configure DNS → Manual → add the IP. Manual, per-device, one-time — nothing to
   script here.
4. **Install and fully trust `certs/rootCA.pem` on the device** — different mechanism than
   the Simulator's `simctl keychain` one-liner above. Get the file onto the device (AirDrop,
   or serve it and open the link in Safari), install the resulting profile via Settings →
   General → VPN & Device Management, then switch it to full trust via Settings → General →
   About → Certificate Trust Settings.
5. Verify: `https://api.dev.whale-sightings.org:8000/health` should load in the device's
   Safari with no certificate warning.
6. `flutter run -d <device-id>`, same as the Simulator (see "Running" below).

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
`lib/sse_client.dart`. No setup beyond the steps above; it rides the same `apiBase`
connection and TLS trust as every other request this app makes.
