// Basic smoke test: the scaffolded counter-app test no longer applies since main.dart was
// replaced with the actual app. This just confirms the app builds and shows its home screen.

import "package:flutter/material.dart";
import "package:flutter_test/flutter_test.dart";

import "package:client_mobile/main.dart";

void main() {
  testWidgets("App shows the sightings list screen", (WidgetTester tester) async {
    await tester.pumpWidget(const WhaleSightingsApp());
    // Lets the initial fetchSightings() call settle (it has no server to talk to in a
    // widget test, so it fails and shows an inline error — that's fine, this test only
    // checks the screen itself renders).
    await tester.pump();

    expect(find.text("Whale Sightings"), findsOneWidget);
    expect(find.byIcon(Icons.add), findsOneWidget);
  });
}
