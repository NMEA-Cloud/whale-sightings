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
# endpoint path beyond this root — see main.py's discover().
API_BASE = os.environ.get("API_BASE", "https://localhost:8000")

# Our own Hydra — client_credentials, scope peer:write. See scripts/register-hydra-peer-client.sh.
HYDRA_TOKEN_URL = os.environ.get("HYDRA_TOKEN_URL", "https://localhost:4444/oauth2/token")
HYDRA_AUDIENCE = os.environ.get("HYDRA_AUDIENCE", "https://api.dev.wombat-sightings.org:8000")
PEER_CLIENT_ID = _require_env("PEER_CLIENT_ID")
PEER_CLIENT_SECRET = _require_env("PEER_CLIENT_SECRET")

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
