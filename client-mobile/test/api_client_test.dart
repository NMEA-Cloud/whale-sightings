// Regression guard: apiBase must stay a dev hostname, not silently revert to localhost —
// see api_client.dart's header comment for why (a physical device's "localhost" is itself,
// not the machine running the backend).

import "package:flutter_test/flutter_test.dart";

import "package:client_mobile/api_client.dart";

void main() {
  test("apiBase points at the dev hostname, not localhost", () {
    expect(apiBase, "https://api.dev.whale-sightings.org:8000");
  });
}
