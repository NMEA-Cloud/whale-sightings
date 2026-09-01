#!/usr/bin/env bash
# Registers (or re-registers) an OAuth2 client_credentials client with Hydra for the
# peer-service demo — same shape as register-hydra-ingest-client.sh (client ID/secret pair,
# no redirect URI, no user ever logs in with it), just a different scope. Safe to re-run —
# any existing client with the same ID is deleted first, and Hydra prints a freshly
# generated secret every time (it never stores or reveals the old one).
#
# Usage: ./scripts/register-hydra-peer-client.sh [api-base]
#   ./scripts/register-hydra-peer-client.sh                                  # current dev defaults
#   ./scripts/register-hydra-peer-client.sh https://192.168.1.23:8000
#
# Requires the hydra service from infra/docker-compose.yml to be running. Copy the printed
# client ID/secret into peer-service's own env config (see its README section) afterward —
# this script only registers the client, it doesn't write any file itself.
set -euo pipefail

cd "$(dirname "$0")/.."

API_BASE="${1:-https://api.dev.wombat-sightings.org:8000}"
CLIENT_ID="whale-sightings-peer"

docker compose -f infra/docker-compose.yml exec hydra hydra delete oauth2-client "$CLIENT_ID" \
  --endpoint https://hydra:4445 --skip-tls-verify >/dev/null 2>&1 || true

docker compose -f infra/docker-compose.yml exec hydra hydra create oauth2-client \
  --endpoint https://hydra:4445 --skip-tls-verify \
  --id "$CLIENT_ID" \
  --token-endpoint-auth-method client_secret_post \
  --audience "$API_BASE" \
  --grant-type client_credentials \
  --scope peer:write

echo
echo "Registered client '$CLIENT_ID' (client_credentials, scope: peer:write)."
echo "Copy the client ID and secret printed above into peer-service's own env config."
