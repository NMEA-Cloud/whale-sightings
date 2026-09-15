import "dart:async";

import "package:flutter/material.dart";
import "package:flutter_map/flutter_map.dart";
import "package:latlong2/latlong.dart";

import "api_client.dart";
import "auth.dart" as auth;
import "map_config.dart";
import "report_screen.dart";
import "sighting.dart";
import "sse_client.dart" as sse;

class ListScreen extends StatefulWidget {
  const ListScreen({super.key});

  @override
  State<ListScreen> createState() => _ListScreenState();
}

class _ListScreenState extends State<ListScreen> {
  List<SightingRecord> _sightings = [];
  String? _errorMessage;
  StreamSubscription<void>? _sseSubscription;

  @override
  void initState() {
    super.initState();
    _loadSightings();
    sse.start();
    _sseSubscription = sse.events.listen((_) => _loadSightings());
  }

  @override
  void dispose() {
    _sseSubscription?.cancel();
    sse.stop(); // fire-and-forget — dispose() can't be async
    super.dispose();
  }

  Future<void> _loadSightings() async {
    try {
      final sightings = await fetchSightings();
      if (!mounted) return;
      setState(() {
        _sightings = sightings;
        _errorMessage = null;
      });
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _errorMessage = error.toString();
      });
    }
  }

  Future<void> _openReportScreen() async {
    final reported = await Navigator.push<bool>(
      context,
      MaterialPageRoute(builder: (_) => const ReportScreen()),
    );
    if (reported == true) {
      await _loadSightings();
    }
  }

  Future<void> _handleDelete(SightingRecord record) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text("Delete this sighting?"),
        content: Text(record.sighting.species),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text("Cancel"),
          ),
          TextButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text("Delete"),
          ),
        ],
      ),
    );
    if (confirmed != true) return;

    try {
      await deleteSighting(record.id);
      await _loadSightings();
    } on SightingDeleteUnauthorizedException {
      try {
        await auth.login();
        setState(() {
          _errorMessage = "Signed in — tap delete again to finish.";
        });
      } catch (error) {
        setState(() {
          _errorMessage = error.toString();
        });
      }
    } catch (error) {
      setState(() {
        _errorMessage = error.toString();
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text("Whale Sightings"),
        actions: [
          IconButton(icon: const Icon(Icons.add), onPressed: _openReportScreen),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: _loadSightings,
        child: Column(
          children: [
            SizedBox(
              height: 240,
              child: FlutterMap(
                options: const MapOptions(
                  initialCenter: defaultMapCenter,
                  initialZoom: defaultMapZoom,
                ),
                children: [
                  basemapTileLayer(),
                  MarkerLayer(
                    markers: _sightings
                        .map(
                          (record) => Marker(
                            point: LatLng(
                              record.sighting.latitude,
                              record.sighting.longitude,
                            ),
                            child: const Icon(
                              Icons.location_on,
                              color: Colors.red,
                            ),
                          ),
                        )
                        .toList(),
                  ),
                ],
              ),
            ),
            if (_errorMessage != null)
              Padding(
                padding: const EdgeInsets.all(8),
                child: Text(
                  _errorMessage!,
                  style: const TextStyle(color: Colors.red),
                ),
              ),
            Expanded(
              child: ListView.builder(
                itemCount: _sightings.length,
                itemBuilder: (context, index) {
                  final record = _sightings[index];
                  final sighting = record.sighting;
                  return ListTile(
                    title: Text(
                      "${sighting.species}${sighting.name != null ? ' (${sighting.name})' : ''}",
                    ),
                    subtitle: Text(
                      "${sighting.datetime} · ${sighting.status} · ${sighting.method}\n"
                      "${sighting.latitude.toStringAsFixed(4)}, ${sighting.longitude.toStringAsFixed(4)}"
                      "${sighting.comments != null ? '\n${sighting.comments}' : ''}",
                    ),
                    isThreeLine: true,
                    trailing: IconButton(
                      icon: const Icon(Icons.delete),
                      onPressed: () => _handleDelete(record),
                    ),
                  );
                },
              ),
            ),
          ],
        ),
      ),
    );
  }
}
