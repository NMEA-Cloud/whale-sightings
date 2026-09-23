#!/usr/bin/env bash
# Rewrites dnsmasq/whale-sightings.conf's two address= records to this machine's *current*
# LAN IP, then restarts the dns container to pick it up. Run this once after joining a new
# network (new venue, new WiFi, a DHCP lease renewal that changed the address) — not part of
# every dev-up.sh run, since most days the IP hasn't changed.
#
# This machine's copy of dnsmasq/whale-sightings.conf is a deliberate per-machine local file
# (like certs/, which setup-tls.sh generates) — its address= values aren't meant to be synced
# from another machine's checkout. See the comment inside that file, and
# [[infra-migration-to-raspberry-pi]] in project memory, for why.
#
# Doesn't touch TLS certs: the cert's SANs cover the dev hostnames themselves (fixed, not
# per-IP) plus this machine's mDNS name, so a changed LAN IP alone doesn't require reissuing
# anything — only the DNS *answer* needs updating.
#
# Safe to re-run; idempotent.
set -euo pipefail

cd "$(dirname "$0")/.."

CONF="dnsmasq/whale-sightings.conf"

if [ ! -f "$CONF" ]; then
  echo "$CONF not found — run this from a checkout that has it." >&2
  exit 1
fi

# Asks the kernel which source IP it would use to reach the internet — reliably picks the
# primary outbound interface even when multiple are up (e.g. both wlan0 and eth0), unlike
# `hostname -I`, which just lists every address on every interface with no indication of
# which one anything would actually route through.
NEW_IP="$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{for (i=1;i<=NF;i++) if ($i=="src") print $(i+1)}')"

if [ -z "$NEW_IP" ]; then
  echo "Couldn't determine this machine's LAN IP (no default route?). Check networking and try again." >&2
  exit 1
fi

sed -i -E \
  -e "s|(address=/auth\.dev\.whale-auth\.org/)[0-9.]+|\1${NEW_IP}|" \
  -e "s|(address=/api\.dev\.whale-sightings\.org/)[0-9.]+|\1${NEW_IP}|" \
  "$CONF"

echo "dnsmasq/whale-sightings.conf now points both dev hostnames at ${NEW_IP}."

if docker compose -f infra/docker-compose.yml ps --status running --services 2>/dev/null | grep -qx dns; then
  echo "Restarting dns container to pick it up..."
  docker compose -f infra/docker-compose.yml restart dns >/dev/null
  echo "Done."
else
  echo "dns container isn't running yet — it'll pick this up whenever the infra project starts."
fi

echo
echo "Client devices on this network (browsers, client-mobile) need their own DNS pointed at"
echo "${NEW_IP} to resolve the dev hostnames — see client-mobile/README.md's"
echo "\"Physical-device support\" section and the root README's \"TLS for remote clients\"."
