#!/usr/bin/env bash
# Registers (or re-registers) an OAuth2 client_credentials client with Hydra for
# machine-to-machine ingestion (e.g. the whale-alert-connector) — distinct from
# register-hydra-client.sh's admin client, which uses browser-based authorization_code+PKCE
# and has no secret. This one authenticates with a client ID/secret pair and has no redirect
# URI, no user ever logs in with it. Safe to re-run — any existing client with the same ID is
# deleted first, and Hydra prints a freshly generated secret every time (it never stores or
# reveals the old one).
#
# Usage: ./scripts/register-hydra-ingest-client.sh [api-base]
#   ./scripts/register-hydra-ingest-client.sh                                  # current dev defaults
#   ./scripts/register-hydra-ingest-client.sh https://192.168.1.23:8000
#
# Requires the hydra service from infra/docker-compose.yml to be running. Copy the printed
# client ID/secret into service/.env.whale-alert-connector (gitignored) afterward — this
# script only registers the client, it doesn't write any file itself.
set -euo pipefail

cd "$(dirname "$0")/.."

API_BASE="${1:-https://api.dev.wombat-sightings.org:8000}"
CLIENT_ID="whale-sightings-ingest"

docker compose -f infra/docker-compose.yml exec hydra hydra delete oauth2-client "$CLIENT_ID" \
  --endpoint https://hydra:4445 --skip-tls-verify >/dev/null 2>&1 || true

docker compose -f infra/docker-compose.yml exec hydra hydra create oauth2-client \
  --endpoint https://hydra:4445 --skip-tls-verify \
  --id "$CLIENT_ID" \
  --token-endpoint-auth-method client_secret_post \
  --audience "$API_BASE" \
  --grant-type client_credentials \
  --scope sightings:ingest

echo
echo "Registered client '$CLIENT_ID' (client_credentials, scope: sightings:ingest)."
echo "Copy the client ID and secret printed above into service/.env.whale-alert-connector."
