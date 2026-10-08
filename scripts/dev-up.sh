#!/usr/bin/env bash
# Starts the full dev environment in the background, then returns to the prompt. Watch the
# logs with ./scripts/dev-logs.sh; stop everything with ./scripts/dev-down.sh.
#
# Starts things in order and checks each stage, so a failure is reported here instead of
# leaving containers silently stuck: pre-flight checks (shared network, the .env files the
# chosen options need, valid compose config) -> the infra project (retried if a first start
# stops part-way; its dns container is optional) -> wait for Hydra -> the app project.
# Safe to re-run: it rebuilds the images built from this repo and restarts their containers
# (picking up code changes, e.g. after a git pull); data in the volumes is kept.
#
# Requires scripts/setup-tls.sh to have been run at least once. The infra project's
# cert-renewer container tolerates being started before that — it waits quietly for certs/
# to be populated — but TLS won't work end-to-end until it has.
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

# --- 3. The app project.

echo "Building and starting the app project..."
"${APP_COMPOSE[@]}" up -d --build || fail "the app project didn't start (see the error above)."

# --- 4. Report.

echo
"${INFRA_COMPOSE[@]}" ps --format 'table {{.Service}}\t{{.Status}}'
echo
"${APP_COMPOSE[@]}" ps --format 'table {{.Service}}\t{{.Status}}'
echo
if [ "$WITH_WHALE_ALERT" = true ]; then
  echo "whale-alert-connector is included (--with-whale-alert)."
fi
if [ "$WITH_WHALE_ALERT_MOCK" = true ]; then
  echo "whale-alert-mock is included (--with-whale-alert-mock)."
fi
if [ "$WITH_PEER_SERVICE" = true ]; then
  echo "peer-service is included (--with-peer-service)."
fi
echo "Everything is up. Watch the logs with ./scripts/dev-logs.sh (Ctrl-C stops watching,"
echo "not the containers). Stop everything with ./scripts/dev-down.sh"
