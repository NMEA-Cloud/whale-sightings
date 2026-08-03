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


def require_admin(request: Request) -> dict[str, Any]:
    settings = get_settings()

    auth_header = request.headers.get("Authorization", "")
    scheme, _, token = auth_header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise _unauthorized(settings, "Missing bearer token")

    jwks_client: PyJWKClient = request.app.state.jwks_client
    try:
        signing_key = jwks_client.get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=settings.oauth_expected_audience,
            issuer=settings.oauth_issuer_url,
        )
    except jwt.PyJWTError as exc:
        raise _unauthorized(settings, "Invalid or expired token") from exc

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
