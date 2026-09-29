#!/usr/bin/env bash
# Starts the full dev environment, then opens a tmux session to watch it — one window each
# for the app project's and the infra ("whale-auth") project's live logs, and a free shell
# (with service/.venv activated, if it exists). Works from any terminal app (tmux owns the
# panes, not the surrounding app).
#
# Starts things in order and checks each stage, so a failure is reported here instead of
# leaving containers silently stuck: pre-flight checks (shared network, the .env files the
# chosen options need, valid compose config) -> the infra project (retried if a first start
# stops part-way; its dns container is optional) -> wait for Hydra -> the app project.
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
# The infra project's cert-renewer container (added for automatic TLS renewal) tolerates
# being started before setup-tls.sh has ever run — it just waits quietly for certs/ to be
# populated — so this isn't a hard ordering requirement, just a reminder that TLS won't
# actually work end-to-end until that first run happens.
#
# Usage: ./scripts/dev-up.sh [--with-whale-alert] [--with-whale-alert-mock] [--with-peer-service]
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
#   --with-peer-service       Also start peer-service, a simulated second system that only
#                              ever talks to this repo's own service/Hydra — see the README.
#                              Requires peer-service/.env (copy peer-service/.env.example)
#                              and its Hydra client (scripts/register-hydra-peer-client.sh)
#                              to already be set up. Omitted by default.
set -euo pipefail

WITH_WHALE_ALERT=false
WITH_WHALE_ALERT_MOCK=false
WITH_PEER_SERVICE=false
for arg in "$@"; do
  case "$arg" in
    --with-whale-alert) WITH_WHALE_ALERT=true ;;
    --with-whale-alert-mock) WITH_WHALE_ALERT_MOCK=true ;;
    --with-peer-service) WITH_PEER_SERVICE=true ;;
    *)
      echo "Unknown argument: $arg" >&2
      echo "Usage: $0 [--with-whale-alert] [--with-whale-alert-mock] [--with-peer-service]" >&2
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
if [ "$WITH_PEER_SERVICE" = true ]; then
  PROFILE_ARGS+=(--profile peer-service)
fi
APP_COMPOSE=(docker compose ${PROFILE_ARGS[@]+"${PROFILE_ARGS[@]}"})
INFRA_COMPOSE=(docker compose -f infra/docker-compose.yml)

fail() {
  echo >&2
  echo "dev-up: $*" >&2
  exit 1
}

# --- 1. Pre-flight: catch everything that would otherwise make a compose project fail to
# start partway, before starting anything. A compose project that hits an error part-way
# through `up` leaves the rest of its containers stuck in "Created", which is easy to miss.

if ! docker network inspect whale-sightings-net >/dev/null 2>&1; then
  echo "Creating the shared Docker network whale-sightings-net..."
  docker network create whale-sightings-net >/dev/null
fi

if [ "$WITH_PEER_SERVICE" = true ] && [ ! -f peer-service/.env ]; then
  fail "--with-peer-service needs peer-service/.env (copy peer-service/.env.example, then fill in
the ID/secret printed by ./scripts/register-hydra-peer-client.sh). Or leave the option off."
fi
if [ "$WITH_WHALE_ALERT" = true ] && [ ! -f service/.env.whale-alert-connector ]; then
  fail "--with-whale-alert needs service/.env.whale-alert-connector (copy the .example next to it,
then fill in the Whale Alert credentials and the ID/secret printed by
./scripts/register-hydra-ingest-client.sh). Or leave the option off."
fi

"${APP_COMPOSE[@]}" config -q || fail "the app project's compose config is invalid (see the error
above) — often a typo in docker-compose.override.yml."
"${INFRA_COMPOSE[@]}" config -q || fail "the infra project's compose config is invalid (see above)."

# --- 2. Infra first. The app project's service fetches Hydra's signing keys, and
# peer-service/whale-alert-connector need Hydra to log in, so Hydra has to be up first.

echo "Building and starting the infra project (step-ca, Hydra, login-consent)..."
INFRA_CORE=(step-ca hydra login-consent cert-renewer)
"${INFRA_COMPOSE[@]}" up -d --build "${INFRA_CORE[@]}" || true

infra_running() {
  local running
  running="$("${INFRA_COMPOSE[@]}" ps --status running --services 2>/dev/null)"
  for svc in "${INFRA_CORE[@]}"; do
    grep -qx "$svc" <<<"$running" || return 1
  done
}

# A first start can stop part-way (a slow machine, a one-off hiccup) — a second `up -d`
# reliably finishes it, so retry a few times before giving up.
for attempt in 1 2 3; do
  infra_running && break
  echo "Some infra containers didn't start — retrying ($attempt/3)..."
  sleep 3
  "${INFRA_COMPOSE[@]}" up -d "${INFRA_CORE[@]}" || true
done
if ! infra_running; then
  "${INFRA_COMPOSE[@]}" ps -a >&2
  fail "the infra project didn't come up (see container states above; logs with
docker compose -f infra/docker-compose.yml logs hydra-migrate hydra login-consent)."
fi

# dns (dnsmasq) is started separately and is optional: it binds port 53, which something else
# on the host may already hold, and a failure there must not take Hydra down with it. Clients
# that resolve the dev hostnames another way (hosts file, the booth router) don't need it.
if ! "${INFRA_COMPOSE[@]}" up -d dns; then
  echo "WARNING: the dns container couldn't start (usually: port 53 is already in use on this" >&2
  echo "machine). Everything else is running; clients must resolve the dev hostnames another" >&2
  echo "way (hosts file / router DNS). See what holds port 53 with: sudo ss -lunp | grep ':53 '" >&2
fi

echo "Waiting for Hydra to be ready..."
for _ in $(seq 1 45); do
  if curl -skf https://localhost:4444/health/ready >/dev/null 2>&1; then
    break
  fi
  sleep 2
done
curl -skf https://localhost:4444/health/ready >/dev/null 2>&1 \
  || fail "Hydra is running but not ready after 90s — check: docker compose -f infra/docker-compose.yml logs hydra"

# --- 3. The app project. Detached, so an error is printed here rather than disappearing with
# a tmux window.

echo "Building and starting the app project..."
"${APP_COMPOSE[@]}" up -d --build || fail "the app project didn't start (see the error above)."

# --- 4. tmux: live logs for each project plus a free shell. Logs rather than a foreground
# `up`, so a window never closes just because a container stopped.

tmux new-session -d -s "$SESSION" -n docker -c "$REPO_ROOT" "${APP_COMPOSE[*]} logs -f --tail 50"
# Keep a window's last output visible if its process ever exits, instead of the window
# silently vanishing.
tmux set-option -t "$SESSION" remain-on-exit on
tmux new-window -t "$SESSION" -n infra -c "$REPO_ROOT" "${INFRA_COMPOSE[*]} logs -f --tail 50"
tmux new-window -t "$SESSION" -n shell -c "$REPO_ROOT"
# Only for machines that run the service's tests locally (see the README) — absent elsewhere.
if [ -f service/.venv/bin/activate ]; then
  tmux send-keys -t "$SESSION:shell" "source service/.venv/bin/activate" Enter
fi

tmux select-window -t "$SESSION:docker"

echo "Started tmux session '$SESSION': docker | infra | shell"
if [ "$WITH_WHALE_ALERT" = true ]; then
  echo "whale-alert-connector is included (--with-whale-alert)."
fi
if [ "$WITH_WHALE_ALERT_MOCK" = true ]; then
  echo "whale-alert-mock is included (--with-whale-alert-mock)."
fi
if [ "$WITH_PEER_SERVICE" = true ]; then
  echo "peer-service is included (--with-peer-service)."
fi
echo "Switch windows with Ctrl-b <number>, detach with Ctrl-b d."
echo "Tear down with ./scripts/dev-down.sh"

attach_or_switch
