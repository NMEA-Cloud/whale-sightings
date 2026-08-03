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
        "scopes_supported": ["openid"],
    }
