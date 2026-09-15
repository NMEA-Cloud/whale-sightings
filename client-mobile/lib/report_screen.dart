import "package:flutter/material.dart";
import "package:flutter_map/flutter_map.dart";
import "package:geolocator/geolocator.dart";
import "package:latlong2/latlong.dart";

import "api_client.dart";
import "map_config.dart";
import "sighting.dart";

const List<String> _statusOptions = ["alive", "dead", "distressed", "unknown"];
const List<String> _methodOptions = ["manual-report", "other"];

class ReportScreen extends StatefulWidget {
  const ReportScreen({super.key});

  @override
  State<ReportScreen> createState() => _ReportScreenState();
}

class _ReportScreenState extends State<ReportScreen> {
  final _formKey = GlobalKey<FormState>();
  final _latitudeController = TextEditingController();
  final _longitudeController = TextEditingController();
  final _typeController = TextEditingController();
  final _speciesController = TextEditingController();
  final _nameController = TextEditingController();
  final _commentsController = TextEditingController();
  final _mapController = MapController();

  String _status = _statusOptions.first;
  String _method = _methodOptions.first;
  DateTime _datetime = DateTime.now();
  String? _statusMessage;
  bool _statusIsError = false;
  bool _submitting = false;

  @override
  void initState() {
    super.initState();
    _populateLocation();
  }

  @override
  void dispose() {
    _latitudeController.dispose();
    _longitudeController.dispose();
    _typeController.dispose();
    _speciesController.dispose();
    _nameController.dispose();
    _commentsController.dispose();
    super.dispose();
  }

  // Graceful degradation, matching shared/sightings-shared.js's populateLocationFields():
  // pre-fill from the device's location but leave the fields editable, and on any failure
  // just show an inline message rather than blocking the form.
  Future<void> _populateLocation() async {
    try {
      var permission = await Geolocator.checkPermission();
      if (permission == LocationPermission.denied) {
        permission = await Geolocator.requestPermission();
      }
      if (permission == LocationPermission.denied ||
          permission == LocationPermission.deniedForever) {
        throw Exception("Location permission denied");
      }
      if (!await Geolocator.isLocationServiceEnabled()) {
        throw Exception("Location services disabled");
      }
      final position = await Geolocator.getCurrentPosition();
      if (!mounted) return;
      setState(() {
        _latitudeController.text = position.latitude.toString();
        _longitudeController.text = position.longitude.toString();
      });
      _mapController.move(LatLng(position.latitude, position.longitude), 10);
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _statusMessage =
            "Could not detect location automatically. Enter it manually.";
        _statusIsError = true;
      });
    }
  }

  LatLng? get _pickedLocation {
    final lat = double.tryParse(_latitudeController.text);
    final lon = double.tryParse(_longitudeController.text);
    if (lat == null || lon == null) return null;
    return LatLng(lat, lon);
  }

  void _setLocation(LatLng point) {
    setState(() {
      _latitudeController.text = point.latitude.toStringAsFixed(6);
      _longitudeController.text = point.longitude.toStringAsFixed(6);
    });
  }

  // Explicit +/- buttons, not just pinch-to-zoom — the picker map otherwise captures drag
  // gestures for panning, which made it hard to tell "scroll the form" from "pan the map"
  // apart, and pinch itself doesn't translate well to a trackpad in the Simulator anyway.
  void _zoomBy(double delta) {
    final camera = _mapController.camera;
    _mapController.move(camera.center, camera.zoom + delta);
  }

  Future<void> _pickDatetime() async {
    final date = await showDatePicker(
      context: context,
      initialDate: _datetime,
      firstDate: DateTime(2000),
      lastDate: DateTime.now(),
    );
    if (date == null || !mounted) return;
    final time = await showTimePicker(
      context: context,
      initialTime: TimeOfDay.fromDateTime(_datetime),
    );
    if (time == null) return;
    setState(() {
      _datetime = DateTime(
        date.year,
        date.month,
        date.day,
        time.hour,
        time.minute,
      );
    });
  }

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate()) return;

    final sighting = Sighting(
      latitude: double.parse(_latitudeController.text),
      longitude: double.parse(_longitudeController.text),
      datetime: _datetime,
      status: _status,
      type: _typeController.text,
      species: _speciesController.text,
      name: _nameController.text.isEmpty ? null : _nameController.text,
      method: _method,
      comments: _commentsController.text.isEmpty
          ? null
          : _commentsController.text,
    );

    setState(() {
      _submitting = true;
      _statusMessage = null;
    });

    try {
      await createSighting(sighting);
      if (!mounted) return;
      Navigator.pop(context, true);
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _statusMessage = error.toString();
        _statusIsError = true;
        _submitting = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text("Report a sighting")),
      body: Form(
        key: _formKey,
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            TextFormField(
              controller: _latitudeController,
              decoration: const InputDecoration(labelText: "Latitude"),
              keyboardType: const TextInputType.numberWithOptions(
                decimal: true,
                signed: true,
              ),
              onChanged: (_) =>
                  setState(() {}), // keeps the picker map's marker in sync
              validator: (value) {
                final parsed = double.tryParse(value ?? "");
                if (parsed == null || parsed < -90 || parsed > 90) {
                  return "Enter a latitude between -90 and 90";
                }
                return null;
              },
            ),
            TextFormField(
              controller: _longitudeController,
              decoration: const InputDecoration(labelText: "Longitude"),
              keyboardType: const TextInputType.numberWithOptions(
                decimal: true,
                signed: true,
              ),
              onChanged: (_) =>
                  setState(() {}), // keeps the picker map's marker in sync
              validator: (value) {
                final parsed = double.tryParse(value ?? "");
                if (parsed == null || parsed < -180 || parsed > 180) {
                  return "Enter a longitude between -180 and 180";
                }
                return null;
              },
            ),
            const SizedBox(height: 8),
            const Text(
              "Tap the map to set the location",
              style: TextStyle(color: Colors.black54),
            ),
            const SizedBox(height: 4),
            SizedBox(
              height: 180,
              child: Stack(
                children: [
                  FlutterMap(
                    mapController: _mapController,
                    options: MapOptions(
                      initialCenter: _pickedLocation ?? defaultMapCenter,
                      initialZoom: _pickedLocation != null
                          ? 10
                          : defaultMapZoom,
                      onTap: (_, point) => _setLocation(point),
                    ),
                    children: [
                      basemapTileLayer(),
                      if (_pickedLocation != null)
                        MarkerLayer(
                          markers: [
                            Marker(
                              point: _pickedLocation!,
                              child: const Icon(
                                Icons.location_on,
                                color: Colors.red,
                              ),
                            ),
                          ],
                        ),
                    ],
                  ),
                  Positioned(
                    right: 8,
                    top: 8,
                    child: Column(
                      children: [
                        _MapZoomButton(
                          icon: Icons.add,
                          onPressed: () => _zoomBy(1),
                        ),
                        const SizedBox(height: 4),
                        _MapZoomButton(
                          icon: Icons.remove,
                          onPressed: () => _zoomBy(-1),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 12),
            ListTile(
              contentPadding: EdgeInsets.zero,
              title: const Text("Date/time"),
              subtitle: Text(_datetime.toString()),
              trailing: const Icon(Icons.edit),
              onTap: _pickDatetime,
            ),
            const SizedBox(height: 12),
            DropdownButtonFormField<String>(
              initialValue: _status,
              decoration: const InputDecoration(labelText: "Status"),
              items: _statusOptions
                  .map(
                    (value) =>
                        DropdownMenuItem(value: value, child: Text(value)),
                  )
                  .toList(),
              onChanged: (value) => setState(() => _status = value!),
            ),
            TextFormField(
              controller: _typeController,
              decoration: const InputDecoration(labelText: "Type"),
              validator: (value) =>
                  (value == null || value.isEmpty) ? "Required" : null,
            ),
            TextFormField(
              controller: _speciesController,
              decoration: const InputDecoration(labelText: "Species"),
              validator: (value) =>
                  (value == null || value.isEmpty) ? "Required" : null,
            ),
            TextFormField(
              controller: _nameController,
              decoration: const InputDecoration(labelText: "Name (optional)"),
            ),
            DropdownButtonFormField<String>(
              initialValue: _method,
              decoration: const InputDecoration(labelText: "Method"),
              items: _methodOptions
                  .map(
                    (value) =>
                        DropdownMenuItem(value: value, child: Text(value)),
                  )
                  .toList(),
              onChanged: (value) => setState(() => _method = value!),
            ),
            TextFormField(
              controller: _commentsController,
              decoration: const InputDecoration(labelText: "Comments"),
              maxLines: 3,
            ),
          ],
        ),
      ),
      // Pinned outside the scrollable form (not inside the ListView above) so it's always
      // visible without scrolling, regardless of how long the form grows — the picker map
      // pushed it below the fold when it lived inline. _formKey.currentState is a GlobalKey
      // lookup, so validate()/submit still work fine from outside the Form's own subtree.
      bottomNavigationBar: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              if (_statusMessage != null)
                Padding(
                  padding: const EdgeInsets.only(bottom: 8),
                  child: Text(
                    _statusMessage!,
                    style: TextStyle(
                      color: _statusIsError ? Colors.red : Colors.green,
                    ),
                  ),
                ),
              SizedBox(
                width: double.infinity,
                child: ElevatedButton(
                  onPressed: _submitting ? null : _submit,
                  child: _submitting
                      ? const SizedBox(
                          height: 16,
                          width: 16,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Text("Submit sighting"),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _MapZoomButton extends StatelessWidget {
  final IconData icon;
  final VoidCallback onPressed;

  const _MapZoomButton({required this.icon, required this.onPressed});

  @override
  Widget build(BuildContext context) {
    return Material(
      color: Colors.white,
      shape: const CircleBorder(),
      elevation: 2,
      child: IconButton(
        icon: Icon(icon, size: 20),
        onPressed: onPressed,
        constraints: const BoxConstraints.tightFor(width: 32, height: 32),
        padding: EdgeInsets.zero,
      ),
    );
  }
}
