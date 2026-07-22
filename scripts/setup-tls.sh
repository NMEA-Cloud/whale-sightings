#!/usr/bin/env bash
# Generates a locally-trusted TLS cert for the service using mkcert, so
# browsers/curl/etc. validate it with no warnings or -k/--insecure flags.
# Safe to re-run; each developer runs this once per machine.
#
# Pass extra hostnames/IPs to also cover clients on other machines, e.g. this
# machine's LAN IP:
#   ./scripts/setup-tls.sh 192.168.1.23
# See "TLS for remote clients" in the README for the full flow (the other
# machine also needs to trust this machine's mkcert CA).
set -euo pipefail

cd "$(dirname "$0")/.."

if ! command -v mkcert >/dev/null 2>&1; then
  echo "mkcert is not installed. Install it, then re-run this script:" >&2
  echo "  macOS:        brew install mkcert" >&2
  echo "  Debian/Ubuntu: sudo apt install mkcert" >&2
  echo "  Other:        https://github.com/FiloSottile/mkcert#installation" >&2
  exit 1
fi

# Creates (or reuses) a local CA and installs it into the OS/browser trust
# stores. Nothing here is committed to git or shared between machines.
mkcert -install

mkdir -p certs
mkcert -cert-file certs/localhost.pem -key-file certs/localhost-key.pem localhost 127.0.0.1 ::1 "$@"

echo
echo "TLS cert written to certs/. Run 'docker compose up --build' to pick it up."

if [ "$#" -eq 0 ]; then
  echo
  echo "This cert only covers localhost. To let a client on another machine connect"
  echo "without a certificate warning, re-run with this machine's LAN IP, e.g.:"
  echo "  ./scripts/setup-tls.sh 192.168.1.23"
  echo "Then copy \$(mkcert -CAROOT)/rootCA.pem (never rootCA-key.pem) to the other"
  echo "machine and trust it there — see 'TLS for remote clients' in the README."
fi
