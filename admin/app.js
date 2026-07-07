// Update this if the service isn't running on http://localhost:8000 (e.g. after AWS deployment).
const API_BASE = "http://localhost:8000";

const OBSERVER_ID_PLACEHOLDER = "https://example.org/users/anonymous-observer";

const statCount = document.getElementById("stat-count");
const statOldest = document.getElementById("stat-oldest");
const statNewest = document.getElementById("stat-newest");
const statsStatus = document.getElementById("stats-status");
const refreshStatsButton = document.getElementById("refresh-stats-button");
const scenarioButtonsContainer = document.getElementById("scenario-buttons");
const scenarioStatus = document.getElementById("scenario-status");
const clearAllButton = document.getElementById("clear-all-button");
const clearStatus = document.getElementById("clear-status");

function setStatus(element, message, isError) {
  element.textContent = message;
  element.className = `status ${isError ? "error" : "success"}`;
}

function formatSightingSummary(record) {
  if (!record) {
    return "–";
  }
  const when = new Date(record.sighting.location.geometry.properties.datetime).toLocaleString();
  const name = record.sighting.name ? ` (${record.sighting.name})` : "";
  return `${when} — ${record.sighting.species}${name}`;
}

async function refreshStats() {
  setStatus(statsStatus, "", false);
  const response = await fetch(`${API_BASE}/sightings/stats`);
  if (!response.ok) {
    throw new Error(`Failed to load stats (${response.status})`);
  }
  const stats = await response.json();
  statCount.textContent = stats.count;
  statOldest.textContent = formatSightingSummary(stats.oldest);
  statNewest.textContent = formatSightingSummary(stats.newest);
}

function isoOffset(hoursAgo) {
  return new Date(Date.now() - hoursAgo * 60 * 60 * 1000).toISOString();
}

function buildSighting({ lon, lat, hoursAgo, status, type, species, name, method, comments }) {
  const location = {
    geometry: {
      type: "Point",
      coordinates: [lon, lat],
      properties: { datetime: isoOffset(hoursAgo) },
    },
  };
  return {
    sighting: { location, status, comments, type, species, name: name ?? null, method },
    observer: { id: OBSERVER_ID_PLACEHOLDER, location },
    images: [],
  };
}

// Canned demo scenarios. Each entry just needs a label and a build() returning an
// array of sighting payloads — edit this list or add your own for specific demos.
// Coordinates are around the Puget Sound / San Juan Islands whale-watching region.
const SCENARIOS = [
  {
    id: "single-recent",
    label: "Single recent sighting",
    build: () => [
      buildSighting({
        lon: -122.3762, lat: 47.3888, hoursAgo: 0,
        status: "alive", type: "orca", species: "Orcinus orca", name: "J27",
        method: "manual-report", comments: "Breaching near the Point Robinson ferry lane.",
      }),
    ],
  },
  {
    id: "pod-san-juan",
    label: "Pod near San Juan Islands",
    build: () => [
      buildSighting({ lon: -123.1524, lat: 48.5165, hoursAgo: 0.1, status: "alive", type: "orca", species: "Orcinus orca", name: "J1", method: "manual-report", comments: "Traveling south past Lime Kiln Point." }),
      buildSighting({ lon: -123.148, lat: 48.514, hoursAgo: 0.15, status: "alive", type: "orca", species: "Orcinus orca", name: "J2", method: "manual-report", comments: "Same pod, trailing J1." }),
      buildSighting({ lon: -123.156, lat: 48.519, hoursAgo: 0.2, status: "alive", type: "orca", species: "Orcinus orca", name: "K12", method: "manual-report", comments: "K-Pod member, spy-hopping." }),
      buildSighting({ lon: -123.16, lat: 48.522, hoursAgo: 0.3, status: "alive", type: "orca", species: "Orcinus orca", name: "L25", method: "manual-report", comments: "L-Pod matriarch sighted with a calf." }),
    ],
  },
  {
    id: "distressed-alert",
    label: "Distressed whale alert",
    build: () => [
      buildSighting({
        lon: -122.3421, lat: 47.6062, hoursAgo: 0,
        status: "distressed", type: "gray whale", species: "Eschrichtius robustus", name: null,
        method: "manual-report", comments: "Entangled in fishing gear near Elliott Bay, needs assistance.",
      }),
    ],
  },
  {
    id: "historical-spread",
    label: "Historical spread (past 2 weeks)",
    build: () => [
      buildSighting({ lon: -122.3762, lat: 47.3888, hoursAgo: 1, status: "alive", type: "orca", species: "Orcinus orca", name: "J27", method: "manual-report", comments: "Within the last day." }),
      buildSighting({ lon: -122.4443, lat: 47.2529, hoursAgo: 30, status: "alive", type: "humpback whale", species: "Megaptera novaeangliae", name: null, method: "manual-report", comments: "Feeding near Tacoma Narrows." }),
      buildSighting({ lon: -122.51, lat: 47.75, hoursAgo: 72, status: "unknown", type: "minke whale", species: "Balaenoptera acutorostrata", name: null, method: "other", comments: "Reported by a passing ferry." }),
      buildSighting({ lon: -122.66, lat: 47.98, hoursAgo: 168, status: "alive", type: "orca", species: "Orcinus orca", name: "K12", method: "manual-report", comments: "One week ago, Whidbey Island." }),
      buildSighting({ lon: -123.05, lat: 48.35, hoursAgo: 240, status: "dead", type: "gray whale", species: "Eschrichtius robustus", name: null, method: "manual-report", comments: "Stranded, ten days ago." }),
      buildSighting({ lon: -123.1524, lat: 48.5165, hoursAgo: 336, status: "alive", type: "orca", species: "Orcinus orca", name: "L25", method: "manual-report", comments: "Two weeks ago, San Juan Islands." }),
    ],
  },
];

async function loadScenario(scenario) {
  setStatus(scenarioStatus, `Loading "${scenario.label}"...`, false);
  const payloads = scenario.build();

  for (const payload of payloads) {
    const response = await fetch(`${API_BASE}/sightings`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!response.ok) {
      const detail = await response.text();
      throw new Error(`Failed to create a sighting (${response.status}): ${detail}`);
    }
  }

  setStatus(scenarioStatus, `Loaded ${payloads.length} sighting(s) from "${scenario.label}".`, false);
  await refreshStats();
}

function renderScenarioButtons() {
  for (const scenario of SCENARIOS) {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = scenario.label;
    button.addEventListener("click", () => {
      loadScenario(scenario).catch((error) => setStatus(scenarioStatus, error.message, true));
    });
    scenarioButtonsContainer.appendChild(button);
  }
}

async function clearAllSightings() {
  setStatus(clearStatus, "Clearing...", false);

  const listResponse = await fetch(`${API_BASE}/sightings`);
  if (!listResponse.ok) {
    throw new Error(`Failed to load sightings (${listResponse.status})`);
  }
  const sightings = await listResponse.json();

  for (const record of sightings) {
    const deleteResponse = await fetch(`${API_BASE}/sightings/${record.id}`, { method: "DELETE" });
    if (!deleteResponse.ok) {
      throw new Error(`Failed to delete sighting ${record.id} (${deleteResponse.status})`);
    }
  }

  setStatus(clearStatus, `Deleted ${sightings.length} sighting(s).`, false);
  await refreshStats();
}

refreshStatsButton.addEventListener("click", () => {
  refreshStats().catch((error) => setStatus(statsStatus, error.message, true));
});

clearAllButton.addEventListener("click", () => {
  if (!confirm("Delete ALL sightings? This cannot be undone.")) {
    return;
  }
  clearAllSightings().catch((error) => setStatus(clearStatus, error.message, true));
});

renderScenarioButtons();
refreshStats().catch((error) => setStatus(statsStatus, error.message, true));
