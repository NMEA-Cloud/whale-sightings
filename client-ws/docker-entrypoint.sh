#!/bin/sh
# Templates config.js from env vars at container start (not baked in at build time), so the
# same image works for dev vs. booth by just changing environment, not rebuilding — see
# docker-compose.yml/docker-compose.override.yml for the values used.
set -eu

cat > /app/config.js <<EOF
window.WHALE_SIGHTINGS_CONFIG = {
  apiBase: "${API_BASE}",
  wsUrl: "${WS_URL}",
};
EOF

# python3 -m http.server has no built-in TLS support, so this wraps it in a small inline
# HTTPS server instead — needed once this is opened over anything but localhost, which
# browsers treat as a secure context regardless of scheme, an exception that doesn't extend
# to a LAN hostname like this project's dev domains or a Raspberry Pi's mDNS name.
# Geolocation (used by the report form's auto-fill) requires a secure context. Reuses the
# same shared step-ca-issued cert every other TLS-serving container in this project already
# mounts (certs/localhost.pem/-key.pem) — its SANs already cover whatever hostname this is
# opened with (see scripts/setup-tls.sh), so no separate cert is needed here.
cat > /tmp/serve_https.py <<'PYEOF'
import http.server
import ssl

httpd = http.server.HTTPServer(("0.0.0.0", 8083), http.server.SimpleHTTPRequestHandler)
ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
ctx.load_cert_chain("/certs/localhost.pem", "/certs/localhost-key.pem")
httpd.socket = ctx.wrap_socket(httpd.socket, server_side=True)
httpd.serve_forever()
PYEOF
exec python3 /tmp/serve_https.py
