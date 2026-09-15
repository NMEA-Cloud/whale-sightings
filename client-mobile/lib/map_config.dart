// Shared between list_screen.dart and report_screen.dart — the only two widgets that embed
// a map — so the basemap and default viewport stay identical without copy-pasting them.
import "package:flutter_map/flutter_map.dart";
import "package:latlong2/latlong.dart";

// Matches the web clients' DEFAULT_MAP_CENTER/DEFAULT_MAP_ZOOM (shared/sightings-shared.js).
const LatLng defaultMapCenter = LatLng(47.7262, -122.645);
const double defaultMapZoom = 9;

// Plain OpenStreetMap tiles for v1 — NOAA nautical chart parity is deliberately deferred
// (see README): the web clients' NOAA layer is a hand-rolled per-viewport image overlay,
// not a drop-in tile URL, so it doesn't belong in this basemap helper as-is.
TileLayer basemapTileLayer() {
  return TileLayer(
    urlTemplate: "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
    userAgentPackageName: "org.whalesightings.client_mobile",
  );
}
