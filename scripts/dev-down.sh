#!/usr/bin/env bash
# Tears down what scripts/dev-up.sh started: stops both docker compose projects (including
# any opt-in profiles). Safe to re-run.
#
# Usage: ./scripts/dev-down.sh [--clear-data]
#   --clear-data   Also FLUSHALL the Valkey store before stopping containers — every
#                  sighting (local, peer, and whale_alert) and the whale-alert-connector's
#                  "retired" bookkeeping are gone for good. Omitted by default: data
#                  persists in the valkey-data volume (docker-compose.yml) across
#                  dev-up.sh/dev-down.sh cycles. Reach for this when leftover data from a
#                  previous session (e.g. whale_alert sightings from earlier
#                  connector/mock testing) is confusing rather than useful.
set -euo pipefail

CLEAR_DATA=false
for arg in "$@"; do
  case "$arg" in
    --clear-data) CLEAR_DATA=true ;;
    *)
      echo "Unknown argument: $arg" >&2
      echo "Usage: $0 [--clear-data]" >&2
      exit 1
      ;;
  esac
done

cd "$(dirname "$0")/.."

if [ "$CLEAR_DATA" = true ]; then
  echo "Clearing the Valkey store (--clear-data)..."
  # Must run before `docker compose down` below, while valkey is still up to exec into.
  docker compose exec -T valkey valkey-cli FLUSHALL || true
fi

echo "Stopping docker compose (app and infra projects)..."
# --profile '*' matters here: a plain `docker compose down` only tears down services with no
# profile (or profiles matching COMPOSE_PROFILES) — a dev-up.sh run started with
# --with-whale-alert (or whale-alert-mock brought up separately) leaves those containers
# running otherwise, orphaned from this teardown.
docker compose --profile '*' down || true
docker compose -f infra/docker-compose.yml down || true

echo "Stopped."
