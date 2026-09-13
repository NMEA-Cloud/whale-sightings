// Hardcoded, not a config-file/env-var indirection like the web clients' config.js —
// that mechanism exists because those clients are built once into a Docker image and need
// runtime reconfiguration without a rebuild. A flutter run/Xcode-launched app doesn't have
// that constraint. Revisit if a later branch needs to point at a non-localhost backend (e.g.
// a physical device over LAN — deliberately out of scope for this Simulator-only branch).
import "dart:convert";

import "package:http/http.dart" as http;

import "sighting.dart";

const String apiBase = "https://localhost:8000";

Future<SightingRecord> createSighting(Sighting sighting) async {
  final response = await http.post(
    Uri.parse("$apiBase/sightings"),
    headers: {"Content-Type": "application/json"},
    body: jsonEncode(sighting.toRequestJson()),
  );
  if (response.statusCode != 201) {
    throw Exception("Submit failed (${response.statusCode}): ${response.body}");
  }
  return SightingRecord.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
}

Future<List<SightingRecord>> fetchSightings() async {
  // No query params — matches the web clients' unfiltered "load everything" default
  // (store.list_all() server-side). No filter UI in this v1 scope.
  final response = await http.get(Uri.parse("$apiBase/sightings"));
  if (response.statusCode != 200) {
    throw Exception("Failed to load sightings (${response.statusCode}): ${response.body}");
  }
  final records = jsonDecode(response.body) as List<dynamic>;
  return records
      .map((record) => SightingRecord.fromJson(record as Map<String, dynamic>))
      .toList();
}
