# Generates a locally-trusted TLS cert for the service using mkcert, so
# browsers/curl/etc. validate it with no warnings or -k/--insecure flags.
# Safe to re-run; each developer runs this once per machine.
#
# Pass extra hostnames/IPs to also cover clients on other machines, e.g. this
# machine's LAN IP:
#   .\scripts\setup-tls.ps1 192.168.1.23
# See "TLS for remote clients" in the README for the full flow (the other
# machine also needs to trust this machine's mkcert CA).
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ExtraNames = @()
)

$ErrorActionPreference = "Stop"

Set-Location (Join-Path $PSScriptRoot "..")

if (-not (Get-Command mkcert -ErrorAction SilentlyContinue)) {
    Write-Error @"
mkcert is not installed. Install it, then re-run this script:
  choco install mkcert
  (or: scoop bucket add extras && scoop install mkcert)
  (or: https://github.com/FiloSottile/mkcert#installation)
"@
}

# Creates (or reuses) a local CA and installs it into the OS/browser trust
# stores. Nothing here is committed to git or shared between machines.
mkcert -install

New-Item -ItemType Directory -Force -Path certs | Out-Null
# "hydra" is always included: it's the fixed Docker-network hostname login-consent uses to
# reach Hydra's admin API (docker-compose.yml's service name for it), not a per-machine value.
mkcert -cert-file certs/localhost.pem -key-file certs/localhost-key.pem localhost 127.0.0.1 "::1" hydra @ExtraNames

# Also copy the CA cert (not the key) itself, so containers that need to make outbound TLS
# calls to another mkcert-issued endpoint on the Docker network (e.g. login-consent calling
# Hydra's admin API) can trust it without disabling verification.
Copy-Item (Join-Path (mkcert -CAROOT) "rootCA.pem") certs/rootCA.pem

Write-Host ""
Write-Host "TLS cert written to certs/. Run 'docker compose up --build' to pick it up."

if ($ExtraNames.Count -eq 0) {
    Write-Host ""
    Write-Host "This cert only covers localhost. To let a client on another machine connect"
    Write-Host "without a certificate warning, re-run with this machine's LAN IP, e.g.:"
    Write-Host "  .\scripts\setup-tls.ps1 192.168.1.23"
    Write-Host "Then copy `$(mkcert -CAROOT)\rootCA.pem (never rootCA-key.pem) to the other"
    Write-Host "machine and trust it there - see 'TLS for remote clients' in the README."
}
