// Update this if the service isn't running on http://localhost:8000 (e.g. after AWS deployment).
const API_BASE = "http://localhost:8000";

const OBSERVER_ID_PLACEHOLDER = "https://example.org/users/anonymous-observer";

const form = document.getElementById("sighting-form");
const formStatus = document.getElementById("form-status");
const listStatus = document.getElementById("list-status");
const refreshButton = document.getElementById("refresh-button");
const sightingsBody = document.getElementById("sightings-body");
const latitudeInput = document.getElementById("latitude");
const longitudeInput = document.getElementById("longitude");
const locateButton = document.getElementById("locate-button");
const datetimeInput = document.getElementById("datetime");
const nowButton = document.getElementById("now-button");
const sinceHoursFilterInput = document.getElementById("since-hours-filter");
const clearFilterButton = document.getElementById("clear-filter-button");

// Default view roughly covers the sample data's area (Puget Sound) until real
// sightings load and fitBounds() takes over.
const DEFAULT_MAP_CENTER = [47.7262, -122.645];
const DEFAULT_MAP_ZOOM = 9;

let map;
let markersLayer;

function initMap() {
  map = L.map("map").setView(DEFAULT_MAP_CENTER, DEFAULT_MAP_ZOOM);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
  }).addTo(map);
  markersLayer = L.layerGroup().addTo(map);
}

function updateMapMarkers(records) {
  markersLayer.clearLayers();

  const points = [];
  for (const record of records) {
    const { sighting } = record;
    const [lon, lat] = sighting.location.geometry.coordinates;
    points.push([lat, lon]);

    const when = new Date(sighting.location.geometry.properties.datetime).toLocaleString();
    const name = sighting.name ? ` (${escapeHtml(sighting.name)})` : "";
    L.marker([lat, lon])
      .bindPopup(
        `<strong>${escapeHtml(sighting.species)}</strong>${name}<br>` +
        `${escapeHtml(sighting.status)} — ${when}<br>` +
        `${escapeHtml(sighting.comments ?? "")}`
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

async function loadSightings() {
  // Clear any error from a previous load attempt so it doesn't linger after this one succeeds.
  setListStatus("", false);

  const sinceHours = sinceHoursFilterInput.value;
  const url = sinceHours
    ? `${API_BASE}/sightings?since_hours=${encodeURIComponent(sinceHours)}`
    : `${API_BASE}/sightings`;

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
  }
  updateMapMarkers(records);
}

// Delete is only exposed here for iteration 1 convenience. Once auth exists, this
// action should move to an admin-only client rather than staying on the public one.
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

clearFilterButton.addEventListener("click", () => {
  sinceHoursFilterInput.value = "";
  loadSightings().catch((error) => setListStatus(error.message, true));
});

locateButton.addEventListener("click", () => {
  populateLocationFields();
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

initMap();
loadSightings().catch((error) => setListStatus(error.message, true));
populateLocationFields();
populateDatetimeField();
