#!/usr/bin/env bash
# Registers (or re-registers) the admin client's OAuth2 client with Hydra. Safe to re-run —
# any existing client with the same ID is deleted first. Re-run whenever the admin client's
# origin or the API's base URL changes (e.g. moving either to a LAN IP).
#
# Usage: ./scripts/register-hydra-client.sh [admin-origin] [api-base]
#   ./scripts/register-hydra-client.sh                                        # localhost dev defaults
#   ./scripts/register-hydra-client.sh http://192.168.1.23:8081 https://192.168.1.23:8000
#
# Requires the hydra service from docker-compose.yml to be running.
set -euo pipefail

cd "$(dirname "$0")/.."

ADMIN_ORIGIN="${1:-http://localhost:8081}"
API_BASE="${2:-https://localhost:8000}"
CLIENT_ID="whale-sightings-admin"

docker compose exec hydra hydra delete oauth2-client "$CLIENT_ID" \
  --endpoint https://hydra:4445 --skip-tls-verify >/dev/null 2>&1 || true

docker compose exec hydra hydra create oauth2-client \
  --endpoint https://hydra:4445 --skip-tls-verify \
  --id "$CLIENT_ID" \
  --token-endpoint-auth-method none \
  --redirect-uri "${ADMIN_ORIGIN}/callback.html" \
  --audience "$API_BASE" \
  --grant-type authorization_code \
  --response-type code \
  --scope openid

echo
echo "Registered client '$CLIENT_ID':"
echo "  redirect-uri: ${ADMIN_ORIGIN}/callback.html"
echo "  audience:     $API_BASE"
