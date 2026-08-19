// Live-sync mechanism for this client: a direct WebSocket connection to the service itself
// (service/app/routers/sightings.py's sightings_ws) — no broker in between, unlike the MQTT
// client's mosquitto broker. Everything else (rendering, the report form, filters, lookup,
// delete) lives in shared/sightings-shared.js, loaded before this file — see that file's
// header comment.

// wss:// — the service only accepts HTTPS. Works fine from this client even though it's
// itself served over plain http: wss:// from an http:// page isn't blocked as mixed content
// (only the reverse, an https:// page loading ws://, is) — same situation as the MQTT client.
const WS_URL = config.wsUrl ?? "wss://localhost:8000/sightings/ws";
const RECONNECT_DELAY_MS = 3000;

// Live-sync: any create/delete from any open tab re-triggers this tab's normal filtered
// load, so the table/map refresh without duplicating filtering or merge logic here — same
// pattern as the MQTT client's on("message") handler.
//
// Unlike mqtt.js (what the MQTT client uses), the native WebSocket API doesn't reconnect on
// its own after the connection drops — the setTimeout(connectWs, ...) in the "close" handler
// below is the hand-rolled equivalent of what a pub/sub library gives you for free. That
// tradeoff (simpler server, no broker to run — but the client has to handle its own
// reconnection) is the whole point of this client existing alongside the MQTT one.
function connectWs() {
  const ws = new WebSocket(WS_URL);

  ws.addEventListener("message", () => {
    loadSightings().catch((error) => setListStatus(error.message, true));
  });

  ws.addEventListener("error", (error) => {
    console.error("WebSocket error:", error);
  });

  ws.addEventListener("close", () => {
    setTimeout(connectWs, RECONNECT_DELAY_MS);
  });
}

initMap();
loadSightings().catch((error) => setListStatus(error.message, true));
populateLocationFields();
populateDatetimeField();
connectWs();
