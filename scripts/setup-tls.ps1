# Generates a locally-trusted TLS cert for the service using step-ca, so
# browsers/curl/etc. validate it with no warnings or -k/--insecure flags.
# Safe to re-run; each developer runs this once per machine.
#
# Pass extra hostnames/IPs to also cover clients on other machines, e.g. this
# machine's LAN IP:
#   .\scripts\setup-tls.ps1 192.168.1.23
# See "TLS for remote clients" in the README for the full flow (the other
# machine also needs to trust this machine's step-ca CA).
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ExtraNames = @()
)

$ErrorActionPreference = "Stop"

Set-Location (Join-Path $PSScriptRoot "..")

if (-not (Get-Command step -ErrorAction SilentlyContinue)) {
    Write-Error @"
step is not installed. Install it, then re-run this script:
  choco install step-cli
  (or: scoop install step)
  (or: https://smallstep.com/docs/step-cli/installation)
"@
}

# step-ca (unlike mkcert) is a live server, not an offline CLI - it has to be up before we can
# bootstrap trust or request a cert from it.
Write-Host "Starting step-ca..."
docker compose -f infra/docker-compose.yml up -d step-ca | Out-Null

Write-Host "Waiting for step-ca to be ready..."
for ($i = 0; $i -lt 15; $i++) {
    docker compose -f infra/docker-compose.yml exec -T step-ca step ca health --ca-url https://localhost:9000 `
        --root /home/step/certs/root_ca.crt *> $null
    if ($LASTEXITCODE -eq 0) { break }
    Start-Sleep -Seconds 2
}

$RootFingerprint = (docker compose -f infra/docker-compose.yml exec -T step-ca step certificate fingerprint /home/step/certs/root_ca.crt).Trim()

New-Item -ItemType Directory -Force -Path certs | Out-Null

# Writes ~/.step/config/defaults.json so later `step ca` commands don't need --ca-url/--root
# repeated. --force skips the "overwrite?" prompt on re-run - safe, since it's just pointing
# back at the same fingerprint each time, not trusting a new one blindly.
step ca bootstrap --ca-url https://localhost:9000 --fingerprint $RootFingerprint --force | Out-Null

# Unlike the bash version, this always re-runs the trust-store install rather than checking
# first - step certificate install is safe to re-run, just occasionally prompts for
# elevation again. (Windows cert-store lookups weren't verified here; if you find a reliable
# way to check first, patch this to skip the prompt on repeat runs like scripts/setup-tls.sh
# does.)
Write-Host "Installing step-ca's root certificate into the trust store..."
step certificate install "$HOME\.step\certs\root_ca.crt"

# "hydra", "mqtt", and "service" are always included: they're the fixed Docker-network
# hostnames login-consent/service/whale-alert-connector use to reach Hydra's admin API, the
# MQTT broker, and the service itself (docker-compose.yml's service names for them), not
# per-machine values. "service" specifically is what whale-alert-connector's
# INGEST_SERVICE_API_BASE (https://service:8000) connects to - without it here, the
# connector's TLS verification fails with a hostname mismatch. auth.dev.booth-boat.org/
# api.dev.wombat-sightings.org are also always included: they're Hydra's/service's fixed
# browser-facing identities (URLS_SELF_ISSUER, PUBLIC_API_BASE_URL - see
# docker-compose.yml/infra/docker-compose.yml), not per-machine values either. Omitting any of
# these here would silently break the OAuth2 login flow, MQTT TLS, or the whale-alert
# connector on the next cert re-issuance.
$Sans = @("--san", "localhost", "--san", "127.0.0.1", "--san", "::1", "--san", "hydra", `
    "--san", "mqtt", "--san", "service", "--san", "auth.dev.booth-boat.org", "--san", "api.dev.wombat-sightings.org")
foreach ($name in $ExtraNames) {
    $Sans += @("--san", $name)
}

# The provisioner password is read from the running container rather than duplicated here -
# it's the same dev-only placeholder set via DOCKER_STEPCA_INIT_PASSWORD in docker-compose.yml.
$PasswordFile = New-TemporaryFile
try {
    docker compose -f infra/docker-compose.yml exec -T step-ca cat /home/step/secrets/password | Set-Content -NoNewline $PasswordFile

    step ca certificate localhost certs/localhost.pem certs/localhost-key.pem `
        @Sans `
        --provisioner whale-sightings-admin `
        --password-file $PasswordFile `
        -f
} finally {
    Remove-Item $PasswordFile -ErrorAction SilentlyContinue
}

# Also copy the CA's root cert (not the intermediate's key, and not the root's key) itself, so
# containers that need to make outbound TLS calls to another step-ca-issued endpoint on the
# Docker network (e.g. login-consent calling Hydra's admin API) can trust it without disabling
# verification.
Copy-Item "$HOME\.step\certs\root_ca.crt" certs/rootCA.pem

Write-Host ""
Write-Host "TLS cert written to certs/. Run 'docker compose up --build' (app project) and"
Write-Host "'docker compose -f infra/docker-compose.yml up --build' (infra project) to pick it"
Write-Host "up. (scripts/dev-up.sh, which brings up both automatically, is bash-only for now.)"
Write-Host "(Existing running containers need a restart to pick up a re-issued cert.)"

if ($ExtraNames.Count -eq 0) {
    Write-Host ""
    Write-Host "This cert only covers localhost. To let a client on another machine connect"
    Write-Host "without a certificate warning, re-run with this machine's LAN IP or a resolvable"
    Write-Host "hostname (e.g. its mDNS/Bonjour '.local' name - see 'TLS for remote clients' in"
    Write-Host "the README for why that's nicer than an IP that changes with DHCP), e.g.:"
    Write-Host "  .\scripts\setup-tls.ps1 192.168.1.23"
    Write-Host "  .\scripts\setup-tls.ps1 whale-service.local"
    Write-Host "Then copy certs\rootCA.pem (never anything from the step-ca-data Docker volume)"
    Write-Host "to the other machine and trust it there - see 'TLS for remote clients' in the README."
}
