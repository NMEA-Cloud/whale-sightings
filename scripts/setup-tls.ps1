# Generates a locally-trusted TLS cert for the service using mkcert, so
# browsers/curl/etc. validate it with no warnings or -k/--insecure flags.
# Safe to re-run; each developer runs this once per machine.
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
mkcert -cert-file certs/localhost.pem -key-file certs/localhost-key.pem localhost 127.0.0.1 "::1"

Write-Host ""
Write-Host "TLS cert written to certs/. Run 'docker compose up --build' to pick it up."
