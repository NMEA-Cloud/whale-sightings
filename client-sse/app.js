// Live-sync mechanism for this client: Server-Sent Events on the service's existing GET
// /sightings endpoint (service/app/routers/sightings.py's list_sightings) — content
// negotiation, not a new URL or a broker. The browser's EventSource API sends
// "Accept: text/event-stream" automatically, which is what switches the endpoint from its
// normal JSON snapshot to a live push stream server-side (see app/sse.py). Everything else
// (rendering, the report form, filters, lookup, delete) lives in shared/sightings-shared.js,
// loaded before this file — see that file's header comment.

const es = new EventSource(`${API_BASE}/sightings`);

// Live-sync: any create/update/delete re-triggers this tab's normal filtered load, so the
// table/map refresh without duplicating filtering or merge logic here — same pattern as the
// WebSocket and MQTT clients' message handlers. The initial ": connected" comment line the
// server sends on connect is invisible to onmessage (SSE comment lines never fire it), so no
// special handling is needed for it here.
es.onmessage = () => {
  loadSightings().catch((error) => setListStatus(error.message, true));
};

es.onerror = (error) => {
  console.error("SSE error:", error);
  // Unlike client-ws's raw WebSocket, EventSource reconnects on its own (with the browser's
  // built-in backoff) after a dropped connection — there's no hand-rolled reconnect loop to
  // write here. That's the flip side of client-ws/app.js's own comment about its reconnect
  // tradeoff: this client has neither a broker to run nor reconnection code to maintain.
};

initMap();
loadSightings().catch((error) => setListStatus(error.message, true));
populateLocationFields();
populateDatetimeField();
