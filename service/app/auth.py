import ssl
from typing import Any

import jwt
from fastapi import HTTPException, Request, status
from jwt import PyJWKClient

from app.config import Settings, get_settings


def build_jwks_client(settings: Settings) -> PyJWKClient:
    ssl_context = None
    if settings.oauth_ca_bundle_path:
        ssl_context = ssl.create_default_context(cafile=settings.oauth_ca_bundle_path)
    jwks_base_url = settings.oauth_jwks_url or settings.oauth_issuer_url
    return PyJWKClient(f"{jwks_base_url}/.well-known/jwks.json", ssl_context=ssl_context)


def _www_authenticate_header(settings: Settings, error: str, error_description: str) -> str:
    resource_metadata = f"{settings.public_api_base_url}/.well-known/oauth-protected-resource"
    return f'Bearer error="{error}", error_description="{error_description}", resource_metadata="{resource_metadata}"'


def _unauthorized(settings: Settings, error_description: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=error_description,
        headers={"WWW-Authenticate": _www_authenticate_header(settings, "invalid_token", error_description)},
    )


def _decode_bearer_token(request: Request, settings: Settings) -> dict[str, Any]:
    auth_header = request.headers.get("Authorization", "")
    scheme, _, token = auth_header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise _unauthorized(settings, "Missing bearer token")

    jwks_client: PyJWKClient = request.app.state.jwks_client
    try:
        signing_key = jwks_client.get_signing_key_from_jwt(token)
        return jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=settings.oauth_expected_audience,
            issuer=settings.oauth_issuer_url,
        )
    except jwt.PyJWTError as exc:
        raise _unauthorized(settings, "Invalid or expired token") from exc


def require_admin(request: Request) -> dict[str, Any]:
    settings = get_settings()
    claims = _decode_bearer_token(request, settings)

    if claims.get("ext", {}).get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required",
            headers={
                "WWW-Authenticate": _www_authenticate_header(
                    settings, "insufficient_scope", "Admin role required"
                )
            },
        )

    return claims


def token_scopes(claims: dict[str, Any]) -> set[str]:
    """Ory Hydra's JWT access tokens carry granted scopes as a `scp` array (confirmed
    against a real token minted by scripts/register-hydra-ingest-client.sh) rather than the
    space-delimited `scope` string RFC 9068 describes — support both so this keeps working
    if a differently-shaped IdP is ever swapped in."""
    scp = claims.get("scp")
    if isinstance(scp, list):
        return set(scp)
    scope = claims.get("scope")
    if isinstance(scope, str):
        return set(scope.split())
    return set()


def require_scope(required_scope: str):
    """Dependency factory for a caller whose token carries required_scope among its granted
    scopes (see token_scopes) — the machine-to-machine analogue of require_admin's
    `ext.role` check. A client_credentials token has no login-consent step to stamp an
    ext.role onto, but does carry whatever scope was granted at client registration (see
    scripts/register-hydra-ingest-client.sh)."""

    def _require_scope(request: Request) -> dict[str, Any]:
        settings = get_settings()
        claims = _decode_bearer_token(request, settings)

        if required_scope not in token_scopes(claims):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"'{required_scope}' scope required",
                headers={
                    "WWW-Authenticate": _www_authenticate_header(
                        settings, "insufficient_scope", f"'{required_scope}' scope required"
                    )
                },
            )

        return claims

    return _require_scope


require_ingest = require_scope("sightings:ingest")
require_peer = require_scope("peer:write")


def try_require_ingest(request: Request) -> dict[str, Any] | None:
    """Like require_ingest, but returns None instead of raising when no token, an invalid
    token, or a token missing the ingest scope is presented — lets create_sighting recognize
    an authenticated ingest caller while staying open-by-default for everyone else (the
    public report form sends no token at all)."""
    try:
        return require_ingest(request)
    except HTTPException:
        return None


def try_require_peer(request: Request) -> dict[str, Any] | None:
    """Like try_require_ingest, but for a peer-service caller (scope peer:write) instead of
    the ingest one — same open-by-default shape, since create_sighting has to recognize an
    authenticated peer without rejecting every other caller that sends no token at all."""
    try:
        return require_peer(request)
    except HTTPException:
        return None


def require_admin_or_ingest(request: Request) -> dict[str, Any]:
    """delete_sighting's dependency: an admin (browser, ext.role) or an ingest client
    (machine, scope) may attempt the delete. Route-level logic then restricts what an
    ingest-authenticated caller specifically is allowed to delete — see delete_sighting in
    routers/sightings.py."""
    try:
        return require_admin(request)
    except HTTPException:
        return require_ingest(request)
