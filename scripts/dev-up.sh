#!/usr/bin/env bash
# Starts the full dev environment in a tmux session — one window each for docker compose,
# the admin static server, the shared-client-code static server, the MQTT client static
# server, and a free shell (with service/.venv activated). Works from any terminal app
# (tmux owns the panes, not the surrounding app).
# Safe to re-run: if the session is already running the compose stack, this just attaches to
# (or, if already inside tmux, switches to) it. If a stale session is lying around — e.g. a
# previous docker compose process died from a Docker Desktop restart or the machine
# sleeping, which by default silently closes that tmux window while the others live on — this
# tears it down and starts fresh rather than attaching you to a half-dead environment.
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

# tmux refuses to attach into a session from a shell that's already inside one ("sessions
# should be nested with care") — switch-client is the equivalent move in that case.
attach_or_switch() {
  if [ -n "${TMUX:-}" ]; then
    exec tmux switch-client -t "$SESSION"
  else
    exec tmux attach -t "$SESSION"
  fi
}

session_is_healthy() {
  tmux has-session -t "$SESSION" 2>/dev/null || return 1
  # A session existing doesn't mean docker compose is actually still running inside it —
  # check the real thing rather than trusting tmux bookkeeping.
  [ -n "$(docker compose ps --status running -q 2>/dev/null)" ]
}

if tmux has-session -t "$SESSION" 2>/dev/null; then
  if session_is_healthy; then
    echo "Session '$SESSION' is already running — attaching."
    attach_or_switch
  else
    echo "Session '$SESSION' exists but the compose stack isn't running (stale) — recreating it."
    tmux kill-session -t "$SESSION"
  fi
fi

tmux new-session -d -s "$SESSION" -n docker -c "$REPO_ROOT" "docker compose up --build"
# If a window's process dies (any of the four, but this matters most for docker compose —
# see the header comment), keep the pane around showing its last output instead of the
# window silently vanishing, which is what made the stale-session case above hard to notice.
tmux set-option -t "$SESSION" remain-on-exit on
tmux new-window -t "$SESSION" -n admin -c "$REPO_ROOT/admin" "python3 -m http.server 8081"
tmux new-window -t "$SESSION" -n shared -c "$REPO_ROOT/shared" "python3 -m http.server 8083"
tmux new-window -t "$SESSION" -n client-mqtt -c "$REPO_ROOT/client-mqtt" "python3 -m http.server 8080"
tmux new-window -t "$SESSION" -n shell -c "$REPO_ROOT"
tmux send-keys -t "$SESSION:shell" "source service/.venv/bin/activate" Enter

tmux select-window -t "$SESSION:docker"

echo "Started tmux session '$SESSION': docker | admin | shared | client-mqtt | shell"
echo "Switch windows with Ctrl-b <number>, detach with Ctrl-b d."
echo "Tear down with ./scripts/dev-down.sh"

attach_or_switch
