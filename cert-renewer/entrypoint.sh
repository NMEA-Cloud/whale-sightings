#!/bin/sh
# Waits for an initial cert (scripts/setup-tls.sh must be run at least once — this container
# only *renews*, it can't perform first issuance) and for step-ca to be reachable, then hands
# off to `step ca renew --daemon`, which blocks forever, renewing certs/localhost.pem in
# place and running restart-consumers.sh after each successful renewal.
set -eu

CA_URL=https://step-ca:9000
ROOT=/certs/rootCA.pem
CRT=/certs/localhost.pem
KEY=/certs/localhost-key.pem

echo "[cert-renewer] Waiting for certs/ to contain an initial cert (run scripts/setup-tls.sh on any machine first)..."
while [ ! -f "$CRT" ] || [ ! -f "$KEY" ] || [ ! -f "$ROOT" ]; do
  sleep 5
done

echo "[cert-renewer] Waiting for step-ca to be healthy..."
while ! step ca health --ca-url "$CA_URL" --root "$ROOT" >/dev/null 2>&1; do
  sleep 5
done

echo "[cert-renewer] Starting renewal daemon for $CRT..."
# --force: step ca renew prompts before overwriting in normal (non-daemon) use — this stays
# unattended even though the --daemon examples in `step ca renew --help` don't show --force
# explicitly, since there's no TTY here to answer a prompt if one ever appeared.
# The outer loop restarts the daemon if it ever exits (e.g. an unhandled network blip),
# rather than letting the container exit — consistent with this repo having no `restart:`
# policy anywhere else.
while true; do
  step ca renew \
    --ca-url "$CA_URL" \
    --root "$ROOT" \
    --daemon \
    --force \
    --exec /restart-consumers.sh \
    "$CRT" "$KEY" || true
  echo "[cert-renewer] renew daemon exited unexpectedly — restarting in 10s..." >&2
  sleep 10
done
