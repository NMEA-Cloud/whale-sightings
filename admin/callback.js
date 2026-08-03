// Completes the PKCE authorization-code exchange started by triggerLogin() in app.js, then
// hands the access token back to index.html via a URL fragment — never Web Storage, see the
// accessToken comment in app.js — and redirects there. oauth.js (loaded first) provides
// CLIENT_ID.

const statusElement = document.getElementById("callback-status");

function setStatus(message, isError) {
  statusElement.textContent = message;
  statusElement.className = `status ${isError ? "error" : "success"}`;
}

async function completeLogin() {
  const params = new URLSearchParams(window.location.search);

  const error = params.get("error");
  if (error) {
    throw new Error(params.get("error_description") || error);
  }

  const code = params.get("code");
  const state = params.get("state");

  const expectedState = sessionStorage.getItem("oauth_state");
  const codeVerifier = sessionStorage.getItem("oauth_code_verifier");
  const tokenEndpoint = sessionStorage.getItem("oauth_token_endpoint");
  // Single-use regardless of outcome below.
  sessionStorage.removeItem("oauth_state");
  sessionStorage.removeItem("oauth_code_verifier");
  sessionStorage.removeItem("oauth_token_endpoint");

  if (!code || !state || !expectedState || !codeVerifier || !tokenEndpoint) {
    throw new Error("Missing login session state — go back and try the action again.");
  }
  if (state !== expectedState) {
    throw new Error("Login state mismatch — aborting (possible CSRF).");
  }

  const response = await fetch(tokenEndpoint, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      grant_type: "authorization_code",
      code,
      redirect_uri: `${window.location.origin}/callback.html`,
      client_id: CLIENT_ID,
      code_verifier: codeVerifier,
    }),
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(`Token exchange failed (${response.status}): ${detail}`);
  }
  const token = await response.json();

  window.location.assign(`${window.location.origin}/#access_token=${encodeURIComponent(token.access_token)}`);
}

completeLogin().catch((error) => setStatus(error.message, true));
