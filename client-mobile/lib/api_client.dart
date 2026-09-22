// Hardcoded, not a config-file/env-var indirection like the web clients' config.js —
// that mechanism exists because those clients are built once into a Docker image and need
// runtime reconfiguration without a rebuild. A flutter run/Xcode-launched app doesn't have
// that constraint. Uses the dev hostname (not localhost) so the same apiBase works from both
// the iOS Simulator and a physical device on the LAN — this hostname is already covered by
// the TLS cert's fixed SANs (see scripts/setup-tls.sh) and mirrors auth.dart's own issuer
// hostname (auth.dev.whale-auth.org), which was already proven working from the Simulator.
// A physical device additionally needs the LAN's DNS to resolve this hostname to the right
// machine and the device to trust the CA root — see client-mobile/README.md's
// "Physical-device support" section.
import "dart:convert";

import "package:http/http.dart" as http;

import "auth.dart" as auth;
import "sighting.dart";

const String apiBase = "https://api.dev.whale-sightings.org:8000";

/// Thrown by deleteSighting() when there's no token, or the server rejects the one held —
/// callers should trigger auth.login() and let the user retry, not retry automatically
/// (matches client-admin/app.js's own deliberate no-auto-retry delete UX).
class SightingDeleteUnauthorizedException implements Exception {}

Future<SightingRecord> createSighting(Sighting sighting) async {
  final response = await http.post(
    Uri.parse("$apiBase/sightings"),
    headers: {"Content-Type": "application/json"},
    body: jsonEncode(sighting.toRequestJson()),
  );
  if (response.statusCode != 201) {
    throw Exception("Submit failed (${response.statusCode}): ${response.body}");
  }
  return SightingRecord.fromJson(
    jsonDecode(response.body) as Map<String, dynamic>,
  );
}

Future<List<SightingRecord>> fetchSightings() async {
  // No query params — matches the web clients' unfiltered "load everything" default
  // (store.list_all() server-side). No filter UI in this v1 scope.
  final response = await http.get(Uri.parse("$apiBase/sightings"));
  if (response.statusCode != 200) {
    throw Exception(
      "Failed to load sightings (${response.statusCode}): ${response.body}",
    );
  }
  final records = jsonDecode(response.body) as List<dynamic>;
  return records
      .map((record) => SightingRecord.fromJson(record as Map<String, dynamic>))
      .toList();
}

Future<void> deleteSighting(String id) async {
  final token = auth.accessToken;
  final response = await http.delete(
    Uri.parse("$apiBase/sightings/$id"),
    headers: token != null ? {"Authorization": "Bearer $token"} : {},
  );
  if (response.statusCode == 401) {
    throw SightingDeleteUnauthorizedException();
  }
  if (response.statusCode != 204) {
    throw Exception("Delete failed (${response.statusCode}): ${response.body}");
  }
}
