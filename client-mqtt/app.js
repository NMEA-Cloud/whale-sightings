// Live-sync mechanism for this client: MQTT over WebSockets. Everything else (rendering,
// the report form, filters, lookup, delete) lives in shared/sightings-shared.js, loaded
// before this file — see that file's header comment.

// The service publishes here on every sighting create/delete, so any open tab can
// live-refresh its list. Plain ws:// is fine — this client is itself served over plain
// http, so there's no mixed-content restriction to work around.
const MQTT_WS_URL = config.mqttWsUrl ?? "ws://localhost:9001";
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
