from contextlib import asynccontextmanager
from html import escape

import httpx
from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from app.config import get_settings
from app.hydra_admin import HydraAdminClient

# Hydra returns one of these when a login/consent challenge has already been used or has
# aged out (e.g. a browser tab left open, or a reloaded/replayed /login or /consent URL) —
# distinct from a malformed or genuinely-missing challenge, which would be a real bug here
# worth a 500. See _expired_challenge_page() below for what the user sees instead.
_EXPIRED_CHALLENGE_STATUSES = {401, 404, 410}


def _expired_challenge_page() -> HTMLResponse:
    return HTMLResponse(
        """<!doctype html>
<html>
<head><title>Sign-in link expired</title></head>
<body>
  <h1>This sign-in link has expired</h1>
  <p class="error">
    It was already used, or sat open too long. Go back to the admin client and click
    "Clear all sightings" again to start over with a fresh one.
  </p>
</body>
</html>""",
        status_code=400,
    )


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
    try:
        login_request = app.state.hydra.get_login_request(login_challenge)
        if login_request.get("skip"):
            settings = get_settings()
            result = app.state.hydra.accept_login_request(
                login_challenge, subject=login_request["subject"], remember_for=settings.login_remember_seconds
            )
            return RedirectResponse(result["redirect_to"], status_code=302)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in _EXPIRED_CHALLENGE_STATUSES:
            return _expired_challenge_page()
        raise
    return HTMLResponse(_login_page(login_challenge))


@app.post("/login", response_class=HTMLResponse)
def post_login(
    login_challenge: str = Form(...), username: str = Form(...), password: str = Form(...)
) -> HTMLResponse:
    settings = get_settings()
    try:
        if username == settings.admin_username and password == settings.admin_password:
            result = app.state.hydra.accept_login_request(
                login_challenge, subject=username, remember_for=settings.login_remember_seconds
            )
            return RedirectResponse(result["redirect_to"], status_code=302)

        app.state.hydra.reject_login_request(login_challenge)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in _EXPIRED_CHALLENGE_STATUSES:
            return _expired_challenge_page()
        raise
    return HTMLResponse(_login_page(login_challenge, error="Invalid username or password"), status_code=401)


@app.get("/consent")
def get_consent(consent_challenge: str) -> Response:
    # Single trusted admin client — no grant screen, just echo back what was requested.
    try:
        consent_request = app.state.hydra.get_consent_request(consent_challenge)
        result = app.state.hydra.accept_consent_request(
            consent_challenge,
            grant_scope=consent_request.get("requested_scope", []),
            grant_access_token_audience=consent_request.get("requested_access_token_audience", []),
        )
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in _EXPIRED_CHALLENGE_STATUSES:
            return _expired_challenge_page()
        raise
    return RedirectResponse(result["redirect_to"], status_code=302)
