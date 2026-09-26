from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.jsonld import CONTEXT_PATH, JSONLD_MEDIA_TYPE, SIGHTING_CONTEXT

router = APIRouter()


@router.get(CONTEXT_PATH, include_in_schema=False)
def sighting_context() -> JSONResponse:
    """Unauthenticated, like the root discovery document — a JSON-LD processor fetches this
    on its own to interpret any sighting response's "@context" reference."""
    return JSONResponse({"@context": SIGHTING_CONTEXT}, media_type=JSONLD_MEDIA_TYPE)
