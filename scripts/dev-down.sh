#!/usr/bin/env bash
# Tears down what scripts/dev-up.sh started: stops the docker compose stack, interrupts the
# two static file servers, deactivates the venv in the shell window, then kills the tmux
# session. Safe to re-run.
set -euo pipefail

cd "$(dirname "$0")/.."
SESSION="whale-sightings"

if ! command -v tmux >/dev/null 2>&1 || ! tmux has-session -t "$SESSION" 2>/dev/null; then
  echo "No '$SESSION' tmux session running — nothing to tear down."
  exit 0
fi

echo "Stopping docker compose..."
docker compose down

echo "Stopping admin/client static servers..."
tmux send-keys -t "$SESSION:admin" C-c
tmux send-keys -t "$SESSION:client" C-c

echo "Deactivating venv in the shell window..."
tmux send-keys -t "$SESSION:shell" C-c
tmux send-keys -t "$SESSION:shell" "deactivate" Enter

sleep 1
tmux kill-session -t "$SESSION"

echo "Session '$SESSION' torn down."
