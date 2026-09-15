// Live-sync for the list screen — Server-Sent Events on the existing GET /sightings
// endpoint (Accept: text/event-stream), the same mechanism client-sse/app.js uses. Flat
// top-level module, matching auth.dart's style: one ongoing piece of app state plus
// functions that manage it.
import "dart:async";
import "dart:convert";

import "package:flutter/foundation.dart" show debugPrint;
import "package:http/http.dart" as http;

import "api_client.dart" show apiBase;

// Matches client-ws/app.js's RECONNECT_DELAY_MS precedent — Dart's streamed http request
// has no native reconnect the way browsers' EventSource does, so this is hand-rolled here.
const Duration _reconnectDelay = Duration(milliseconds: 3000);

http.Client? _client;
bool _closed = true;
Timer? _reconnectTimer;
Completer<void>? _reconnectCompleter;
final StreamController<void> _events = StreamController<void>.broadcast();

/// Emits whenever the server reports a sighting changed — the event's own payload is never
/// parsed, matching client-sse/app.js's onmessage: firing at all is the only signal that
/// matters, callers just re-trigger a full refetch.
Stream<void> get events => _events.stream;

void start() {
  if (!_closed) return; // idempotent — don't stack a second loop
  _closed = false;
  unawaited(_connectLoop());
}

Future<void> stop() async {
  _closed = true;
  _reconnectTimer?.cancel(); // forces a sleeping reconnect delay to unblock
  _reconnectTimer = null;
  if (_reconnectCompleter case final completer? when !completer.isCompleted) {
    completer.complete();
  }
  _client?.close(); // forces the in-flight `await for` below to unblock
  _client = null;
}

Future<void> _connectLoop() async {
  while (!_closed) {
    final client = http.Client();
    _client = client;
    try {
      await _connectOnce(client);
    } catch (error) {
      // Mirrors client-sse/app.js's onerror: log only, never surface to the UI —
      // reconnecting here is routine/expected, not a user-facing failure.
      debugPrint("SSE error: $error");
    } finally {
      client.close();
      if (identical(_client, client)) _client = null;
    }
    if (_closed) break;
    await _reconnectDelayFuture();
  }
}

// A cancelable stand-in for Future.delayed(_reconnectDelay) — stop() needs to unblock this
// immediately (not just let it expire) so a caller awaiting stop() (e.g. a widget's dispose())
// doesn't leave a live Timer running past its own lifetime, which flutter_test's
// TestWidgetsFlutterBinding asserts against as a leaked pending timer.
Future<void> _reconnectDelayFuture() {
  final completer = Completer<void>();
  _reconnectCompleter = completer;
  _reconnectTimer = Timer(_reconnectDelay, () {
    if (!completer.isCompleted) completer.complete();
  });
  return completer.future;
}

Future<void> _connectOnce(http.Client client) async {
  final request = http.Request("GET", Uri.parse("$apiBase/sightings"))
    ..headers["Accept"] = "text/event-stream";
  final response = await client.send(request);

  final lines = response.stream
      .transform(utf8.decoder)
      .transform(const LineSplitter());
  await for (final line in lines) {
    if (_closed) break;
    if (line.startsWith("data: ")) {
      _events.add(null);
    }
    // The blank separator line and the leading ": connected" comment line both fall
    // through here and are ignored — this server (service/app/sse.py) only ever sends
    // these two line shapes, so no more general SSE parsing (event:/id: fields,
    // multi-line data:) is needed.
  }
  // Falling out here (server closed the stream) is treated the same as an error above —
  // _connectLoop delays and retries either way.
}
