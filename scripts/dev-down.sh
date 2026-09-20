#!/usr/bin/env bash
# Tears down what scripts/dev-up.sh started: stops both docker compose projects, deactivates
# the venv in the shell window, then kills the tmux session. Safe to re-run, and always
# finishes the teardown even if some of these steps don't apply — e.g. a window already
# closed on its own (docker compose exiting closes its window by default) shouldn't stop the
# rest of teardown from running, so each step below is individually tolerant of failure.
#
# Stopping the containers does NOT depend on the tmux session still existing. dev-up.sh's
# docker compose processes run as the foreground job in a tmux pane, but the containers
# themselves are managed by dockerd and keep running under it even if tmux itself dies
# abnormally (a sleeping/restarted machine or a crashed tmux server doesn't necessarily give
# those panes' child processes a chance to shut their containers down first). This used to be
# gated behind `tmux has-session`, so an already-dead tmux session made this script print
# "nothing to tear down" while the containers it started kept running indefinitely — the
# actual teardown always runs now; the tmux session is a separate, optional cleanup step.
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
SESSION="whale-sightings"

if [ "$CLEAR_DATA" = true ]; then
  echo "Clearing the Valkey store (--clear-data)..."
  # Must run before `docker compose down` below, while valkey is still up to exec into.
  docker compose exec -T valkey valkey-cli FLUSHALL || true
fi

echo "Stopping docker compose (app and infra projects)..."
# --profile '*' matters here: a plain `docker compose down` only tears down services with no
# profile (or profiles matching COMPOSE_PROFILES) — a dev-up.sh run started with
# --with-whale-alert (or whale-alert-mock brought up separately) leaves those containers
# running otherwise, orphaned from this teardown and from the tmux session it just killed.
docker compose --profile '*' down || true
docker compose -f infra/docker-compose.yml down || true

if command -v tmux >/dev/null 2>&1 && tmux has-session -t "$SESSION" 2>/dev/null; then
  echo "Deactivating venv in the shell window..."
  tmux send-keys -t "$SESSION:shell" C-c 2>/dev/null || true
  tmux send-keys -t "$SESSION:shell" "deactivate" Enter 2>/dev/null || true

  sleep 1
  tmux kill-session -t "$SESSION" 2>/dev/null || true
  echo "Session '$SESSION' torn down."
else
  echo "No '$SESSION' tmux session running — containers stopped, nothing else to tear down."
fi
