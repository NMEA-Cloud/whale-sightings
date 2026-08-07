// Live-sync mechanism for this client: repeated GET /sightings/poll requests, each held
// open server-side (see service/app/routers/sightings.py's poll_sightings) until something
// changes or a timeout elapses. Everything else (rendering, the report form, filters,
// lookup, delete) lives in shared/sightings-shared.js, loaded before this file — see that
// file's header comment.

const POLL_TIMEOUT_SECONDS = 25; // must stay under the endpoint's own le=55 cap
const POLL_ERROR_RETRY_MS = 3000; // backoff after a network/HTTP error so a broken poll doesn't spin-loop

// Advances forward on every matched poll response — read by pollLoop() below, but not by
// loadSightings(), which is a full filtered reload independent of this cursor. since_hours
// filtering in the UI keeps working normally through that reload; it's just not what this
// cursor itself uses to detect new arrivals.
let sinceCursor = new Date().toISOString();

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function pollLoop() {
  while (true) {
    let radiusFilter;
    try {
      radiusFilter = readRadiusFilter();
    } catch (error) {
      setListStatus(error.message, true);
      await sleep(POLL_ERROR_RETRY_MS);
      continue;
    }

    const params = new URLSearchParams({ since: sinceCursor, timeout_seconds: String(POLL_TIMEOUT_SECONDS) });
    if (radiusFilter) {
      params.set("radius_nm", radiusFilter.radiusNm);
      params.set("lat", radiusFilter.radiusLat);
      params.set("lon", radiusFilter.radiusLon);
    }

    try {
      const response = await fetch(`${API_BASE}/sightings/poll?${params}`);

      if (response.status === 204) {
        continue; // no match — immediately re-issue the long-poll request
      }
      if (!response.ok) {
        throw new Error(`Poll failed (${response.status})`);
      }

      const matched = await response.json();
      for (const record of matched) {
        const matchedDatetime = record.sighting.location.geometry.properties.datetime;
        if (matchedDatetime > sinceCursor) {
          sinceCursor = matchedDatetime;
        }
      }

      // Mirrors the MQTT client's on("message") handler: don't render `matched` directly
      // (it's only the delta, not the full current filtered view) — treat it as a
      // "something changed" signal and re-run the normal filtered load, same as every
      // other refresh trigger.
      await loadSightings().catch((error) => setListStatus(error.message, true));
    } catch (error) {
      console.error("Poll error:", error);
      await sleep(POLL_ERROR_RETRY_MS);
    }
  }
}

initMap();
loadSightings().catch((error) => setListStatus(error.message, true));
populateLocationFields();
populateDatetimeField();
pollLoop();
