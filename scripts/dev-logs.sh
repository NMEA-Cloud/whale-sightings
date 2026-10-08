#!/usr/bin/env bash
# Follows the live logs of everything scripts/dev-up.sh started — both compose projects,
# including any opt-in profiles that are running — interleaved, each line prefixed with its
# container name. Ctrl-C stops watching; the containers keep running.
#
# Usage: ./scripts/dev-logs.sh [app|infra]
#   (no argument)  both projects
#   app            just the app project (service, clients, peer-service, connector, ...)
#   infra          just the infra project (step-ca, Hydra, login-consent, dns, cert-renewer)
set -euo pipefail

cd "$(dirname "$0")/.."

APP=(docker compose --profile '*' logs -f --tail 50)
INFRA=(docker compose -f infra/docker-compose.yml logs -f --tail 50)

case "${1:-both}" in
  app) exec "${APP[@]}" ;;
  infra) exec "${INFRA[@]}" ;;
  both)
    # Both in the background, stopped together on Ctrl-C.
    trap 'kill 0' INT TERM
    "${APP[@]}" &
    "${INFRA[@]}" &
    wait
    ;;
  *)
    echo "Usage: $0 [app|infra]" >&2
    exit 1
    ;;
esac
