from fastapi import APIRouter
from fastapi.responses import RedirectResponse

router = APIRouter()


@router.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    # No real landing page — send a browser somewhere with an actual <title> (Swagger UI's)
    # instead of a bare 404 JSON body, which left the browser tab just showing "localhost:8000".
    return RedirectResponse("/docs")


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
