"""Plain env-var configuration — no pydantic-settings dependency, keeping this container's
requirements.txt to just httpx + websockets. peer-service is a standalone deployable unit
(see the README for running it on a second machine entirely), so it doesn't share config
machinery with service/ either."""

import os


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"{name} environment variable is required")
    return value


# The whale-sightings service to discover and post sightings to. Never used to hardcode any
# endpoint path beyond this root — see main.py's discover(). Hydra's token endpoint, the
# audience to request, and the scope to request are all discovered from this same root
# document (and the OAuth metadata it links to) rather than configured here — see main.py's
# discover_auth(). That's everything BUT the client credentials themselves: an unauthenticated
# discovery endpoint can't hand out valid credentials without breaking the security model, so
# PEER_CLIENT_ID/SECRET stay pre-shared config (see scripts/register-hydra-peer-client.sh).
API_BASE = os.environ.get("API_BASE", "https://localhost:8000")

PEER_CLIENT_ID = _require_env("PEER_CLIENT_ID")
PEER_CLIENT_SECRET = _require_env("PEER_CLIENT_SECRET")

# Optional: where discover_auth() (main.py) actually connects for Hydra's OIDC metadata and
# token endpoint, when that differs from Hydra's own public issuer address. Needed for the
# default docker-compose.yml topology — Hydra's browser-facing issuer is a `dev.` LAN
# hostname this container's own DNS doesn't resolve to a reachable address, but it's
# reachable here as `hydra` on the Docker network — mirroring service/app/config.py's own
# OAUTH_JWKS_URL override for the identical reason. Unset (the default) uses the issuer's
# own address directly, which is correct for a standalone run on a real LAN machine, where
# that `dev.` hostname resolves for real (see the README's "Running it standalone" section).
HYDRA_INTERNAL_BASE_URL = os.environ.get("HYDRA_INTERNAL_BASE_URL")

GENERATE_INTERVAL_SECONDS = float(os.environ.get("GENERATE_INTERVAL_SECONDS", "30"))
# Fixed-delay reconnect (not exponential backoff) — mirrors client-ws/app.js's own
# hand-rolled WebSocket reconnect exactly, since the native WebSocket API (and the
# `websockets` library used here) doesn't reconnect on its own after a dropped connection.
WS_RECONNECT_DELAY_SECONDS = float(os.environ.get("WS_RECONNECT_DELAY_SECONDS", "3"))

# Trusted for both the Hydra/service HTTPS calls and the wss:// live-sync connection. None
# (the default) means the system's default trust store — used for a standalone run against
# a real, publicly-trusted TLS setup; docker-compose.yml sets this to the mounted step-ca
# root for the Docker-internal topology.
CA_BUNDLE_PATH = os.environ.get("CA_BUNDLE_PATH")
