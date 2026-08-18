#!/bin/sh
# Templates config.js from env vars at container start (not baked in at build time), so the
# same image works for dev vs. booth by just changing environment, not rebuilding — see
# docker-compose.yml/docker-compose.override.yml for the values used.
set -eu

cat > /app/config.js <<EOF
window.WHALE_SIGHTINGS_CONFIG = {
  apiBase: "${API_BASE}",
  mqttWsUrl: "${MQTT_WS_URL}",
};
EOF

exec python3 -m http.server 8081 --directory /app
