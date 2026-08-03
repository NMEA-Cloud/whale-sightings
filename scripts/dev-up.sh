#!/usr/bin/env bash
# Starts the full dev environment in a tmux session — one window each for docker compose,
# the admin static server, the client static server, and a free shell (with service/.venv
# activated). Works from any terminal app (tmux owns the panes, not the surrounding app).
# Safe to re-run: if the session already exists, this just attaches to it.
#
# Requires tmux (brew install tmux) and scripts/setup-tls.sh to have been run at least once.
set -euo pipefail

cd "$(dirname "$0")/.."
REPO_ROOT="$(pwd)"
SESSION="whale-sightings"

if ! command -v tmux >/dev/null 2>&1; then
  echo "tmux is not installed. Install it, then re-run this script:" >&2
  echo "  macOS:        brew install tmux" >&2
  echo "  Debian/Ubuntu: sudo apt install tmux" >&2
  exit 1
fi

if tmux has-session -t "$SESSION" 2>/dev/null; then
  echo "Session '$SESSION' is already running — attaching."
  exec tmux attach -t "$SESSION"
fi

tmux new-session -d -s "$SESSION" -n docker -c "$REPO_ROOT" "docker compose up --build"
tmux new-window -t "$SESSION" -n admin -c "$REPO_ROOT/admin" "python3 -m http.server 8081"
tmux new-window -t "$SESSION" -n client -c "$REPO_ROOT/client" "python3 -m http.server 8080"
tmux new-window -t "$SESSION" -n shell -c "$REPO_ROOT"
tmux send-keys -t "$SESSION:shell" "source service/.venv/bin/activate" Enter

tmux select-window -t "$SESSION:docker"

echo "Started tmux session '$SESSION': docker | admin | client | shell"
echo "Switch windows with Ctrl-b <number>, detach with Ctrl-b d."
echo "Tear down with ./scripts/dev-down.sh"

exec tmux attach -t "$SESSION"
