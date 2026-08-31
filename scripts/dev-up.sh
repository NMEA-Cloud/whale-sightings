#!/usr/bin/env bash
# Starts the full dev environment in a tmux session — one window each for the app project's
# docker compose (which now also builds and serves all three static clients — see
# docker-compose.yml), the infra ("booth-boat") project's docker compose, and a free shell
# (with service/.venv activated). Works from any terminal app (tmux owns the panes, not the
# surrounding app).
# Safe to re-run: if the session is already running the compose stack, this just attaches to
# (or, if already inside tmux, switches to) it. If a stale session is lying around — e.g. a
# previous docker compose process died from a Docker Desktop restart or the machine
# sleeping, which by default silently closes that tmux window while the others live on — this
# tears it down and starts fresh rather than attaching you to a half-dead environment.
#
# Requires tmux (brew install tmux), scripts/setup-tls.sh to have been run at least once, and
# the shared external network the two compose projects join (one-time setup):
#   docker network create whale-sightings-net
#
# Usage: ./scripts/dev-up.sh [--with-whale-alert] [--with-whale-alert-mock]
#   --with-whale-alert        Also start whale-alert-connector (opt-in, real Whale Alert API
#                              calls by default — see the README). Requires
#                              service/.env.whale-alert-connector (copy
#                              service/.env.whale-alert-connector.example) and the Hydra
#                              ingest client (scripts/register-hydra-ingest-client.sh) to
#                              already be set up. Omitted by default — the connector stays off.
#   --with-whale-alert-mock   Also start whale-alert-mock, a local fake of Whale Alert's API
#                              safe to run without any real credentials — see the README.
#                              Combine with --with-whale-alert and point
#                              WHALE_ALERT_API_BASE_URL at it in .env.whale-alert-connector to
#                              have the connector actually talk to it; this flag only starts
#                              the mock container, it doesn't rewrite that env file for you.
set -euo pipefail

WITH_WHALE_ALERT=false
WITH_WHALE_ALERT_MOCK=false
for arg in "$@"; do
  case "$arg" in
    --with-whale-alert) WITH_WHALE_ALERT=true ;;
    --with-whale-alert-mock) WITH_WHALE_ALERT_MOCK=true ;;
    *)
      echo "Unknown argument: $arg" >&2
      echo "Usage: $0 [--with-whale-alert] [--with-whale-alert-mock]" >&2
      exit 1
      ;;
  esac
done

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
  # check the real thing rather than trusting tmux bookkeeping. Both projects need to be up.
  [ -n "$(docker compose ps --status running -q 2>/dev/null)" ] || return 1
  [ -n "$(docker compose -f infra/docker-compose.yml ps --status running -q 2>/dev/null)" ]
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

PROFILE_ARGS=()
if [ "$WITH_WHALE_ALERT" = true ]; then
  PROFILE_ARGS+=(--profile whale-alert)
fi
if [ "$WITH_WHALE_ALERT_MOCK" = true ]; then
  PROFILE_ARGS+=(--profile whale-alert-mock)
fi
DOCKER_UP_CMD="docker compose ${PROFILE_ARGS[*]-} up --build"

tmux new-session -d -s "$SESSION" -n docker -c "$REPO_ROOT" "$DOCKER_UP_CMD"
# If a window's process dies (either of the two, but this matters most for the two docker
# compose windows — see the header comment), keep the pane around showing its last output
# instead of the window silently vanishing, which is what made the stale-session case above
# hard to notice.
tmux set-option -t "$SESSION" remain-on-exit on
tmux new-window -t "$SESSION" -n infra -c "$REPO_ROOT" "docker compose -f infra/docker-compose.yml up --build"
tmux new-window -t "$SESSION" -n shell -c "$REPO_ROOT"
tmux send-keys -t "$SESSION:shell" "source service/.venv/bin/activate" Enter

tmux select-window -t "$SESSION:docker"

echo "Started tmux session '$SESSION': docker | infra | shell"
if [ "$WITH_WHALE_ALERT" = true ]; then
  echo "whale-alert-connector is included (--with-whale-alert)."
fi
if [ "$WITH_WHALE_ALERT_MOCK" = true ]; then
  echo "whale-alert-mock is included (--with-whale-alert-mock)."
fi
echo "Switch windows with Ctrl-b <number>, detach with Ctrl-b d."
echo "Tear down with ./scripts/dev-down.sh"

attach_or_switch
