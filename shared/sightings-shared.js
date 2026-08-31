// Shared between client-mqtt/app.js and client-long-poll/app.js — loaded via a plain
// <script> tag before either (classic scripts, no modules, same mechanism config.js →
// app.js already relies on), so everything declared here is a global both app.js files can
// use. This holds the code that's agnostic to *how* a client learns something changed —
// rendering, the report form, filters, lookup, delete. Each client's own app.js stays small
// and holds only its live-sync mechanism (MQTT subscribe vs. long-poll loop), which is the
// part actually worth reading client-to-client.
//
// Both index.html files must use identical element IDs for everything referenced below.

// Overridable via config.js (copy config.example.js — see README) for pointing this
// client at a service on another machine. Falls back to localhost if config.js isn't
// present. The service is TLS-only — run scripts/setup-tls.sh (or .ps1) once so
// whatever cert it serves is trusted.
const config = window.WHALE_SIGHTINGS_CONFIG ?? {};
const API_BASE = config.apiBase ?? "https://localhost:8000";

const OBSERVER_ID_PLACEHOLDER = "https://example.org/users/anonymous-observer";

const form = document.getElementById("sighting-form");
const formStatus = document.getElementById("form-status");
const listStatus = document.getElementById("list-status");
const lookupIdInput = document.getElementById("lookup-id");
const lookupButton = document.getElementById("lookup-button");
const lookupStatus = document.getElementById("lookup-status");
const lookupDetails = document.getElementById("lookup-details");
const lookupResult = document.getElementById("lookup-result");
const refreshButton = document.getElementById("refresh-button");
const sightingsBody = document.getElementById("sightings-body");
const latitudeInput = document.getElementById("latitude");
const longitudeInput = document.getElementById("longitude");
const locateButton = document.getElementById("locate-button");
const datetimeInput = document.getElementById("datetime");
const nowButton = document.getElementById("now-button");
const sinceHoursFilterInput = document.getElementById("since-hours-filter");
const clearFilterButton = document.getElementById("clear-filter-button");
const radiusNmFilterInput = document.getElementById("radius-nm-filter");
const radiusLatFilterInput = document.getElementById("radius-lat-filter");
const radiusLonFilterInput = document.getElementById("radius-lon-filter");
const locateFilterButton = document.getElementById("locate-filter-button");
const pickLocationButton = document.getElementById("pick-location-button");
const pickFilterLocationButton = document.getElementById("pick-filter-location-button");

// Default view roughly covers the sample data's area (Puget Sound) until real
// sightings load and fitBounds() takes over.
const DEFAULT_MAP_CENTER = [47.7262, -122.645];
const DEFAULT_MAP_ZOOM = 9;

let map;
let markersLayer;

// Which lat/lon fields the next map click should fill: "form", "filter", or null while inactive.
let pickTarget = null;

function updatePickButtons() {
  pickLocationButton.textContent = pickTarget === "form" ? "Click the map..." : "Pick on map";
  pickLocationButton.classList.toggle("active", pickTarget === "form");
  pickFilterLocationButton.textContent = pickTarget === "filter" ? "Click the map..." : "Pick on map";
  pickFilterLocationButton.classList.toggle("active", pickTarget === "filter");
  map.getContainer().classList.toggle("picking", pickTarget !== null);
}

// Clicking the same target's button again cancels picking instead of re-arming it.
function togglePickTarget(target) {
  pickTarget = pickTarget === target ? null : target;
  updatePickButtons();
}

function initMap() {
  map = L.map("map").setView(DEFAULT_MAP_CENTER, DEFAULT_MAP_ZOOM);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
  }).addTo(map);
  markersLayer = L.layerGroup().addTo(map);

  map.on("click", (event) => {
    if (pickTarget === "form") {
      latitudeInput.value = event.latlng.lat;
      longitudeInput.value = event.latlng.lng;
      setFormStatus("Location set from the map. Edit it above if needed.", false);
    } else if (pickTarget === "filter") {
      radiusLatFilterInput.value = event.latlng.lat;
      radiusLonFilterInput.value = event.latlng.lng;
    } else {
      return;
    }
    pickTarget = null;
    updatePickButtons();
  });
}

// One consistent visual language across all three map clients, for every marker
// (including existing local ones) — not just a special treatment for new sources.
const SOURCE_COLORS = { local: "#2563eb", peer: "#d97706", whale_alert: "#0d9488" };

function sourceMarkerIcon(sourceType) {
  const color = SOURCE_COLORS[sourceType] ?? SOURCE_COLORS.local;
  return L.divIcon({
    className: "",
    html: `<span style="display:block;width:14px;height:14px;border-radius:50%;background:${color};border:2px solid white;box-shadow:0 0 2px rgba(0,0,0,0.6);"></span>`,
    iconSize: [14, 14],
    iconAnchor: [7, 7],
  });
}

function updateMapMarkers(records) {
  markersLayer.clearLayers();

  const points = [];
  for (const record of records) {
    const { sighting } = record;
    const [lon, lat] = sighting.location.geometry.coordinates;
    points.push([lat, lon]);

    const sourceType = record.source?.type ?? "local";
    const when = new Date(sighting.location.geometry.properties.datetime).toLocaleString();
    const name = sighting.name ? ` (${escapeHtml(sighting.name)})` : "";
    L.marker([lat, lon], { icon: sourceMarkerIcon(sourceType) })
      .bindPopup(
        `<strong>${escapeHtml(sighting.species)}</strong>${name}<br>` +
        `${escapeHtml(sighting.status)} — ${when}<br>` +
        `${escapeHtml(sighting.comments ?? "")}<br>` +
        `Source: ${escapeHtml(sourceType)}`
      )
      .addTo(markersLayer);
  }

  if (points.length > 0) {
    map.fitBounds(points, { padding: [20, 20], maxZoom: 14 });
  }
}

function getCurrentPosition() {
  return new Promise((resolve, reject) => {
    if (!navigator.geolocation) {
      reject(new Error("Geolocation is not supported by this browser."));
      return;
    }
    navigator.geolocation.getCurrentPosition(resolve, reject);
  });
}

// Pre-fills the latitude/longitude fields from the browser's current position, but
// leaves them as plain editable inputs so the user can correct them before submitting.
async function populateLocationFields() {
  setFormStatus("Detecting your location...", false);
  try {
    const position = await getCurrentPosition();
    latitudeInput.value = position.coords.latitude;
    longitudeInput.value = position.coords.longitude;
    setFormStatus("Location detected. Edit it above if needed.", false);
  } catch (error) {
    setFormStatus(`Could not detect location automatically (${error.message}). Enter it manually.`, true);
  }
}

// datetime-local inputs take a timezone-less "YYYY-MM-DDTHH:mm:ss" string interpreted
// as local time, so build that from the parts rather than using toISOString() (which is UTC).
function toDatetimeLocalValue(date) {
  const pad = (n) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
}

// Pre-fills the datetime field with the current time, but leaves it editable so the
// user can correct it before submitting (e.g. reporting a sighting after the fact).
function populateDatetimeField() {
  datetimeInput.value = toDatetimeLocalValue(new Date());
}

function buildLocation(longitude, latitude, isoDatetime) {
  return {
    geometry: {
      type: "Point",
      coordinates: [longitude, latitude],
      properties: { datetime: isoDatetime },
    },
  };
}

function setFormStatus(message, isError) {
  formStatus.textContent = message;
  formStatus.className = `status ${isError ? "error" : "success"}`;
}

function setListStatus(message, isError) {
  listStatus.textContent = message;
  listStatus.className = `status ${isError ? "error" : "success"}`;
}

function setLookupStatus(message, isError) {
  lookupStatus.textContent = message;
  lookupStatus.className = `status ${isError ? "error" : "success"}`;
}

async function lookupSighting() {
  const id = lookupIdInput.value.trim();
  lookupDetails.hidden = true;
  lookupResult.textContent = "";
  if (!id) {
    setLookupStatus("Enter a sighting ID.", true);
    return;
  }

  setLookupStatus("Looking up...", false);
  try {
    const response = await fetch(`${API_BASE}/sightings/${id}`);
    if (response.status === 404) {
      setLookupStatus("No sighting found with that ID.", true);
      return;
    }
    if (!response.ok) {
      throw new Error(`Lookup failed (${response.status})`);
    }
    const record = await response.json();
    setLookupStatus("", false);
    lookupResult.textContent = JSON.stringify(record, null, 2);
    lookupDetails.hidden = false;
    lookupDetails.open = true;
  } catch (error) {
    setLookupStatus(error.message, true);
  }
}

// Reads the three radius filter fields: null if none are filled (no location filter),
// {radiusNm, radiusLat, radiusLon} if all three are, throws if only some are. A separate
// function (not inlined in loadSightings) because the long-poll client's poll loop needs
// the exact same radius params, and each call site turns a thrown error into its own
// status message.
function readRadiusFilter() {
  const radiusNm = radiusNmFilterInput.value;
  const radiusLat = radiusLatFilterInput.value;
  const radiusLon = radiusLonFilterInput.value;

  const fields = [radiusNm, radiusLat, radiusLon];
  const anyField = fields.some((value) => value !== "");
  const allFields = fields.every((value) => value !== "");

  if (!anyField) {
    return null;
  }
  if (!allFields) {
    throw new Error("Fill in radius, latitude, and longitude together to filter by location.");
  }
  return { radiusNm, radiusLat, radiusLon };
}

async function loadSightings() {
  // Clear any error from a previous load attempt so it doesn't linger after this one succeeds.
  setListStatus("", false);

  let radiusFilter;
  try {
    radiusFilter = readRadiusFilter();
  } catch (error) {
    setListStatus(error.message, true);
    return;
  }

  const sinceHours = sinceHoursFilterInput.value;

  const params = new URLSearchParams();
  if (sinceHours) {
    params.set("since_hours", sinceHours);
  }
  if (radiusFilter) {
    params.set("radius_nm", radiusFilter.radiusNm);
    params.set("lat", radiusFilter.radiusLat);
    params.set("lon", radiusFilter.radiusLon);
  }
  const query = params.toString();
  const url = query ? `${API_BASE}/sightings?${query}` : `${API_BASE}/sightings`;

  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Failed to load sightings (${response.status})`);
  }
  const sightings = await response.json();
  renderSightings(sightings);
}

function renderSightings(records) {
  sightingsBody.innerHTML = "";
  for (const record of records) {
    const { sighting } = record;
    const [lon, lat] = sighting.location.geometry.coordinates;
    const row = document.createElement("tr");
    row.className = "sighting-row";
    row.innerHTML = `
      <td>${new Date(sighting.location.geometry.properties.datetime).toLocaleString()}</td>
      <td>${escapeHtml(sighting.species)}</td>
      <td>${escapeHtml(sighting.name ?? "")}</td>
      <td>${escapeHtml(sighting.status)}</td>
      <td>${escapeHtml(sighting.method)}</td>
      <td>${lat.toFixed(4)}, ${lon.toFixed(4)}</td>
      <td>${escapeHtml(sighting.comments ?? "")}</td>
      <td><button class="delete-button" data-id="${record.id}" type="button">Delete</button></td>
    `;
    sightingsBody.appendChild(row);

    const idRow = document.createElement("tr");
    idRow.className = "sighting-id-row";
    idRow.innerHTML = `<td colspan="8">ID: ${escapeHtml(record.id)}</td>`;
    sightingsBody.appendChild(idRow);
  }
  updateMapMarkers(records);
}

// Deliberately unauthenticated — DELETE /sightings/{id} requires an admin bearer token
// (see service/app/auth.py), so this always fails with a 401. Left on both clients on
// purpose, as a working demo of the same endpoint succeeding from the admin client and
// being rejected here.
async function deleteSighting(id) {
  const response = await fetch(`${API_BASE}/sightings/${id}`, { method: "DELETE" });
  if (!response.ok) {
    throw new Error(`Delete failed (${response.status})`);
  }
}

function escapeHtml(value) {
  const div = document.createElement("div");
  div.textContent = value;
  return div.innerHTML;
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();

  try {
    // The latitude/longitude inputs are required with min/max, so the browser has
    // already validated them by the time this handler runs.
    const latitude = Number(latitudeInput.value);
    const longitude = Number(longitudeInput.value);

    // The datetime input is required, so the browser has already validated it's
    // present; it's local time with no timezone, so parse it as such via `new Date`.
    const isoDatetime = new Date(datetimeInput.value).toISOString();
    const location = buildLocation(longitude, latitude, isoDatetime);

    const payload = {
      sighting: {
        location,
        status: document.getElementById("status").value,
        comments: document.getElementById("comments").value || null,
        type: document.getElementById("type").value,
        species: document.getElementById("species").value,
        name: document.getElementById("name").value || null,
        method: document.getElementById("method").value,
      },
      observer: {
        id: OBSERVER_ID_PLACEHOLDER,
        location,
      },
      images: [],
    };

    const response = await fetch(`${API_BASE}/sightings`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      const detail = await response.text();
      throw new Error(`Submit failed (${response.status}): ${detail}`);
    }

    const created = await response.json();
    lookupIdInput.value = created.id;

    form.reset();
    setFormStatus("Sighting submitted.", false);
    await loadSightings().catch((error) => setListStatus(error.message, true));
    await populateLocationFields();
    populateDatetimeField();
  } catch (error) {
    setFormStatus(error.message, true);
  }
});

refreshButton.addEventListener("click", () => {
  loadSightings().catch((error) => setListStatus(error.message, true));
});

lookupButton.addEventListener("click", () => {
  lookupSighting();
});

clearFilterButton.addEventListener("click", () => {
  sinceHoursFilterInput.value = "";
  radiusNmFilterInput.value = "";
  radiusLatFilterInput.value = "";
  radiusLonFilterInput.value = "";
  loadSightings().catch((error) => setListStatus(error.message, true));
});

locateButton.addEventListener("click", () => {
  populateLocationFields();
});

pickLocationButton.addEventListener("click", () => {
  togglePickTarget("form");
});

pickFilterLocationButton.addEventListener("click", () => {
  togglePickTarget("filter");
});

locateFilterButton.addEventListener("click", async () => {
  try {
    const position = await getCurrentPosition();
    radiusLatFilterInput.value = position.coords.latitude;
    radiusLonFilterInput.value = position.coords.longitude;
  } catch (error) {
    setListStatus(`Could not detect location automatically (${error.message}).`, true);
  }
});

nowButton.addEventListener("click", () => {
  populateDatetimeField();
});

sightingsBody.addEventListener("click", async (event) => {
  const button = event.target.closest(".delete-button");
  if (!button) {
    return;
  }
  if (!confirm("Delete this sighting?")) {
    return;
  }
  try {
    await deleteSighting(button.dataset.id);
    await loadSightings();
  } catch (error) {
    setListStatus(error.message, true);
  }
});
