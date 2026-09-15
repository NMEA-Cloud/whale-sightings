#!/usr/bin/env bash
# Registers (or re-registers) the mobile client's OAuth2 client with Hydra. Safe to re-run —
# any existing client with the same ID is deleted first. Distinct client ID/redirect-uri from
# register-hydra-client.sh's whale-sightings-admin — Hydra clients are keyed by id and bound to
# a fixed redirect URI, and a native app has no web origin to reuse client-admin's
# http://localhost:8080/callback.html. Re-run if the API's base URL changes — Hydra rejects an
# authorize request whose audience isn't in the client's registered list (see
# register-hydra-client.sh's header comment for the same failure mode).
#
# Usage: ./scripts/register-hydra-mobile-client.sh [api-base]
#   ./scripts/register-hydra-mobile-client.sh                                  # current dev default
#   ./scripts/register-hydra-mobile-client.sh https://192.168.1.23:8000
#
# Requires the hydra service from infra/docker-compose.yml to be running.
set -euo pipefail

cd "$(dirname "$0")/.."

API_BASE="${1:-https://api.dev.wombat-sightings.org:8000}"
CLIENT_ID="whale-sightings-mobile"
REDIRECT_URI="com.andyfox.whalesightings.clientmobile:/oauth2redirect"

docker compose -f infra/docker-compose.yml exec hydra hydra delete oauth2-client "$CLIENT_ID" \
  --endpoint https://hydra:4445 --skip-tls-verify >/dev/null 2>&1 || true

docker compose -f infra/docker-compose.yml exec hydra hydra create oauth2-client \
  --endpoint https://hydra:4445 --skip-tls-verify \
  --id "$CLIENT_ID" \
  --token-endpoint-auth-method none \
  --redirect-uri "$REDIRECT_URI" \
  --audience "$API_BASE" \
  --grant-type authorization_code \
  --response-type code \
  --scope openid

echo
echo "Registered client '$CLIENT_ID':"
echo "  redirect-uri: $REDIRECT_URI"
echo "  audience:     $API_BASE"
