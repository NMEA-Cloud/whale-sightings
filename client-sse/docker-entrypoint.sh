#!/bin/sh
# Templates config.js from env vars at container start (not baked in at build time), so the
# same image works for dev vs. booth by just changing environment, not rebuilding — see
# docker-compose.yml/docker-compose.override.yml for the values used. Only apiBase is
# needed here (unlike client-ws/client-mqtt) — SSE reuses GET /sightings itself via the
# Accept header, which EventSource sends automatically, so there's no second URL to
# template in.
set -eu

cat > /app/config.js <<EOF
window.WHALE_SIGHTINGS_CONFIG = {
  apiBase: "${API_BASE}",
};
EOF

exec python3 -m http.server 8084 --directory /app
