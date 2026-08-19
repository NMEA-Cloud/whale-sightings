// Live-sync mechanism for this client: MQTT over WebSockets. Everything else (rendering,
// the report form, filters, lookup, delete) lives in shared/sightings-shared.js, loaded
// before this file — see that file's header comment.

// The service publishes here on every sighting create/delete, so any open tab can
// live-refresh its list. wss:// (not ws://) since the broker requires TLS — see
// mosquitto/mosquitto.conf. Works fine from this client even though it's itself served over
// plain http: wss:// from an http:// page isn't blocked as mixed content (only the reverse,
// an https:// page loading ws://, is).
const MQTT_WS_URL = config.mqttWsUrl ?? "wss://localhost:9001";
const MQTT_TOPIC = "whale-sightings/updates";

// Live-sync: any create/delete from any open tab re-triggers this tab's normal filtered
// load, so the table/map refresh without duplicating filtering or merge logic here.
function connectMqtt() {
  const mqttClient = mqtt.connect(MQTT_WS_URL);

  mqttClient.on("connect", () => {
    mqttClient.subscribe(MQTT_TOPIC);
  });

  mqttClient.on("message", () => {
    loadSightings().catch((error) => setListStatus(error.message, true));
  });

  mqttClient.on("error", (error) => {
    console.error("MQTT connection error:", error);
  });
}

initMap();
loadSightings().catch((error) => setListStatus(error.message, true));
populateLocationFields();
populateDatetimeField();
connectMqtt();
