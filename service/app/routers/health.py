from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, RedirectResponse

from app.config import get_settings
from app.discovery import build_root_document
from app.jsonld import negotiated_json, wants_jsonld

router = APIRouter()


@router.get("/", include_in_schema=False, response_model=None)
def root(request: Request) -> RedirectResponse | JSONResponse:
    # A browser (or anything else not explicitly asking for JSON) gets sent somewhere with
    # an actual <title> (Swagger UI's) instead of a bare 404 JSON body, which left the
    # browser tab just showing "localhost:8000". A caller that does ask for JSON — a peer
    # service discovering this API's capabilities instead of hardcoding endpoint paths —
    # gets the root discovery document instead — as application/ld+json if that's what it
    # asked for (a JSON-LD client's natural Accept header), plain application/json otherwise.
    if "application/json" in request.headers.get("accept", "") or wants_jsonld(request):
        return negotiated_json(build_root_document(str(request.base_url), get_settings()), request)
    return RedirectResponse("/docs")


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
