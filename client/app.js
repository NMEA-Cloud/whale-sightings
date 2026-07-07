// Update this if the service isn't running on http://localhost:8000 (e.g. after AWS deployment).
const API_BASE = "http://localhost:8000";

const OBSERVER_ID_PLACEHOLDER = "https://example.org/users/anonymous-observer";

const form = document.getElementById("sighting-form");
const formStatus = document.getElementById("form-status");
const refreshButton = document.getElementById("refresh-button");
const sightingsBody = document.getElementById("sightings-body");

function getCurrentPosition() {
  return new Promise((resolve, reject) => {
    if (!navigator.geolocation) {
      reject(new Error("Geolocation is not supported by this browser."));
      return;
    }
    navigator.geolocation.getCurrentPosition(resolve, reject);
  });
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
  formStatus.className = isError ? "error" : "success";
}

async function loadSightings() {
  const response = await fetch(`${API_BASE}/sightings`);
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
  setFormStatus("Getting your location...", false);

  try {
    const position = await getCurrentPosition();
    const isoDatetime = new Date().toISOString();
    const location = buildLocation(
      position.coords.longitude,
      position.coords.latitude,
      isoDatetime
    );

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
    await loadSightings();
  } catch (error) {
    setFormStatus(error.message, true);
  }
});

refreshButton.addEventListener("click", () => {
  loadSightings().catch((error) => setFormStatus(error.message, true));
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
    setFormStatus(error.message, true);
  }
});

loadSightings().catch((error) => setFormStatus(error.message, true));
