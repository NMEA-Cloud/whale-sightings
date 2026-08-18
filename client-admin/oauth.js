// Shared between app.js and callback.js — no build step here, so this just needs to load
// before either of them (see the <script> order in index.html / callback.html).

// Fixed, not deployment-specific: this is the client ID scripts/register-hydra-client.sh
// registers with Hydra, and doesn't change when the AS or API relocates — only the
// discovered authorization/token endpoints do (see triggerLogin() in app.js).
const CLIENT_ID = "whale-sightings-admin";

function base64UrlEncode(bytes) {
  let binary = "";
  for (const byte of bytes) {
    binary += String.fromCharCode(byte);
  }
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function randomPkceString() {
  const bytes = new Uint8Array(32);
  crypto.getRandomValues(bytes);
  return base64UrlEncode(bytes);
}

async function sha256Base64Url(value) {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(value));
  return base64UrlEncode(new Uint8Array(digest));
}

// Parses a WWW-Authenticate header's key="value" pairs, e.g.
// `Bearer error="invalid_token", resource_metadata="https://.../oauth-protected-resource"`.
function parseWwwAuthenticate(header) {
  const params = {};
  const pattern = /(\w+)="([^"]*)"/g;
  let match;
  while ((match = pattern.exec(header)) !== null) {
    params[match[1]] = match[2];
  }
  return params;
}
