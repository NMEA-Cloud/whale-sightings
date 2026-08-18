#!/usr/bin/env bash
# Generates a locally-trusted TLS cert for the service using step-ca, so
# browsers/curl/etc. validate it with no warnings or -k/--insecure flags.
# Safe to re-run; each developer runs this once per machine.
#
# Pass extra hostnames/IPs to also cover clients on other machines, e.g. this
# machine's LAN IP:
#   ./scripts/setup-tls.sh 192.168.1.23
# See "TLS for remote clients" in the README for the full flow (the other
# machine also needs to trust this machine's step-ca CA).
set -euo pipefail

cd "$(dirname "$0")/.."

if ! command -v step >/dev/null 2>&1; then
  echo "step is not installed. Install it, then re-run this script:" >&2
  echo "  macOS:        brew install step" >&2
  echo "  Other:        https://smallstep.com/docs/step-cli/installation" >&2
  exit 1
fi

# step-ca lives in the infra ("booth-boat") project, not this one — see
# infra/docker-compose.yml's header comment for why they're split.
INFRA_COMPOSE=(docker compose -f infra/docker-compose.yml)

# step-ca (unlike mkcert) is a live server, not an offline CLI — it has to be up before we can
# bootstrap trust or request a cert from it.
echo "Starting step-ca..."
"${INFRA_COMPOSE[@]}" up -d step-ca >/dev/null

echo "Waiting for step-ca to be ready..."
for _ in $(seq 1 15); do
  if "${INFRA_COMPOSE[@]}" exec -T step-ca step ca health --ca-url https://localhost:9000 \
      --root /home/step/certs/root_ca.crt >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

ROOT_FINGERPRINT="$("${INFRA_COMPOSE[@]}" exec -T step-ca \
  step certificate fingerprint /home/step/certs/root_ca.crt)"

mkdir -p certs

# Writes ~/.step/config/defaults.json so later `step ca` commands don't need --ca-url/--root
# repeated. --force skips the "overwrite?" prompt on re-run — safe, since it's just pointing
# back at the same fingerprint each time, not trusting a new one blindly.
step ca bootstrap --ca-url https://localhost:9000 --fingerprint "$ROOT_FINGERPRINT" --force >/dev/null

# The system-trust install needs sudo — only do it if this exact CA isn't already trusted, so
# re-running this script doesn't prompt for a password every time.
if ! security find-certificate -Z -a /Library/Keychains/System.keychain 2>/dev/null \
    | grep -qi "$ROOT_FINGERPRINT"; then
  echo "Installing step-ca's root certificate into the system trust store (needs sudo)..."
  sudo step certificate install ~/.step/certs/root_ca.crt
fi

# "hydra" is always included: it's the fixed Docker-network hostname login-consent uses to
# reach Hydra's admin API (docker-compose.yml's service name for it), not a per-machine value.
# auth.dev.booth-boat.org/api.dev.wombat-sightings.org are also always included: they're
# Hydra's/service's fixed browser-facing identities (URLS_SELF_ISSUER, PUBLIC_API_BASE_URL —
# see docker-compose.yml/infra/docker-compose.yml), not per-machine values either. Omitting
# them here would silently break the OAuth2 login flow on the next cert re-issuance.
SANS=(--san localhost --san 127.0.0.1 --san ::1 --san hydra \
  --san auth.dev.booth-boat.org --san api.dev.wombat-sightings.org)
for host in "$@"; do
  SANS+=(--san "$host")
done

# The provisioner password is read from the running container rather than duplicated here —
# it's the same dev-only placeholder set via DOCKER_STEPCA_INIT_PASSWORD in docker-compose.yml.
PASSWORD_FILE="$(mktemp)"
trap 'rm -f "$PASSWORD_FILE"' EXIT
"${INFRA_COMPOSE[@]}" exec -T step-ca cat /home/step/secrets/password > "$PASSWORD_FILE"

step ca certificate localhost certs/localhost.pem certs/localhost-key.pem \
  "${SANS[@]}" \
  --provisioner whale-sightings-admin \
  --password-file "$PASSWORD_FILE" \
  -f

# Also copy the CA's root cert (not the intermediate's key, and not the root's key) itself, so
# containers that need to make outbound TLS calls to another step-ca-issued endpoint on the
# Docker network (e.g. login-consent calling Hydra's admin API) can trust it without disabling
# verification.
cp ~/.step/certs/root_ca.crt certs/rootCA.pem

echo
echo "TLS cert written to certs/. Run 'docker compose up --build' (app project) and"
echo "'docker compose -f infra/docker-compose.yml up --build' (infra project) — or just"
echo "./scripts/dev-up.sh, which brings up both — to pick it up."
echo "(Existing running containers need a restart to pick up a re-issued cert.)"

if [ "$#" -eq 0 ]; then
  echo
  echo "This cert only covers localhost. To let a client on another machine connect"
  echo "without a certificate warning, re-run with this machine's LAN IP or a resolvable"
  echo "hostname (e.g. its mDNS/Bonjour '.local' name — see 'TLS for remote clients' in"
  echo "the README for why that's nicer than an IP that changes with DHCP), e.g.:"
  echo "  ./scripts/setup-tls.sh 192.168.1.23"
  echo "  ./scripts/setup-tls.sh whale-service.local"
  echo "Then copy certs/rootCA.pem (never the step-ca-data volume's private key) to the other"
  echo "machine and trust it there — see 'TLS for remote clients' in the README."
fi
