// Copy this file to config.js (gitignored, like .env) and edit for your environment —
// e.g. point at the service's LAN IP instead of localhost to use this client from another
// machine. If config.js doesn't exist, app.js falls back to the localhost defaults below.
window.WHALE_SIGHTINGS_CONFIG = {
  apiBase: "https://localhost:8000",
  mqttWsUrl: "ws://localhost:9001",
};
