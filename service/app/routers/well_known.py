from fastapi import APIRouter

from app.config import get_settings

router = APIRouter()


@router.get("/.well-known/oauth-protected-resource")
def oauth_protected_resource() -> dict[str, object]:
    settings = get_settings()
    return {
        "resource": settings.public_api_base_url,
        "authorization_servers": [settings.oauth_issuer_url],
        "bearer_methods_supported": ["header"],
        # The client_credentials scopes this resource server actually grants and checks
        # (see require_scope in app/auth.py) — "openid" was a stale leftover from an
        # earlier draft and doesn't correspond to anything this API checks.
        "scopes_supported": ["sightings:ingest", "peer:write"],
    }
