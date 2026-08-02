from contextlib import asynccontextmanager
from html import escape

from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse, RedirectResponse

from app.config import get_settings
from app.hydra_admin import HydraAdminClient


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    app.state.hydra = HydraAdminClient(settings.hydra_admin_url, settings.hydra_admin_ca_bundle_path)
    yield


app = FastAPI(title="Whale Sightings Login/Consent", lifespan=lifespan)


def _login_page(login_challenge: str, error: str | None = None) -> str:
    error_html = f'<p class="error">{error}</p>' if error else ""
    return f"""<!doctype html>
<html>
<head><title>Sign in</title></head>
<body>
  <h1>Whale Sightings admin sign in</h1>
  {error_html}
  <form method="post" action="/login">
    <input type="hidden" name="login_challenge" value="{escape(login_challenge)}">
    <label>Username <input type="text" name="username" autofocus required></label>
    <label>Password <input type="password" name="password" required></label>
    <button type="submit">Sign in</button>
  </form>
</body>
</html>"""


@app.get("/login", response_class=HTMLResponse)
def get_login(login_challenge: str) -> HTMLResponse:
    login_request = app.state.hydra.get_login_request(login_challenge)
    if login_request.get("skip"):
        result = app.state.hydra.accept_login_request(login_challenge, subject=login_request["subject"])
        return RedirectResponse(result["redirect_to"], status_code=302)
    return HTMLResponse(_login_page(login_challenge))


@app.post("/login", response_class=HTMLResponse)
def post_login(
    login_challenge: str = Form(...), username: str = Form(...), password: str = Form(...)
) -> HTMLResponse:
    settings = get_settings()
    if username == settings.admin_username and password == settings.admin_password:
        result = app.state.hydra.accept_login_request(login_challenge, subject=username)
        return RedirectResponse(result["redirect_to"], status_code=302)

    app.state.hydra.reject_login_request(login_challenge)
    return HTMLResponse(_login_page(login_challenge, error="Invalid username or password"), status_code=401)


@app.get("/consent")
def get_consent(consent_challenge: str) -> RedirectResponse:
    # Single trusted admin client — no grant screen, just echo back what was requested.
    consent_request = app.state.hydra.get_consent_request(consent_challenge)
    result = app.state.hydra.accept_consent_request(
        consent_challenge,
        grant_scope=consent_request.get("requested_scope", []),
        grant_access_token_audience=consent_request.get("requested_access_token_audience", []),
    )
    return RedirectResponse(result["redirect_to"], status_code=302)
