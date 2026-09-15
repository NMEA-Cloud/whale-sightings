// Wire shapes for the whale-sightings API — see service/app/models.py and
// service/app/discovery.py in the main repo for the authoritative contract.
//
// Every existing client (client-mqtt/, client-long-poll/, client-ws/, client-sse/) hardcodes
// this same fake observer identity, since there's no login in v1 — matched here for
// consistency across all clients.
const String observerIdPlaceholder =
    "https://example.org/users/anonymous-observer";

/// The report form's fields, plus what a list row needs to render. Flat fields here — the
/// nested GeoJSON location.geometry.coordinates/properties.datetime wire shape is only
/// reconstructed in toJson(), not mirrored in this object.
class Sighting {
  final double latitude;
  final double longitude;
  final DateTime datetime;
  final String status;
  final String type;
  final String species;
  final String? name;
  final String method;
  final String? comments;

  Sighting({
    required this.latitude,
    required this.longitude,
    required this.datetime,
    required this.status,
    required this.type,
    required this.species,
    this.name,
    required this.method,
    this.comments,
  });

  factory Sighting.fromJson(Map<String, dynamic> json) {
    final coordinates =
        json["location"]["geometry"]["coordinates"] as List<dynamic>;
    return Sighting(
      longitude: (coordinates[0] as num).toDouble(),
      latitude: (coordinates[1] as num).toDouble(),
      datetime: DateTime.parse(
        json["location"]["geometry"]["properties"]["datetime"] as String,
      ),
      status: json["status"] as String,
      type: json["type"] as String,
      species: json["species"] as String,
      name: json["name"] as String?,
      method: json["method"] as String,
      comments: json["comments"] as String?,
    );
  }

  Map<String, dynamic> _locationJson() => {
    "geometry": {
      "type": "Point",
      "coordinates": [longitude, latitude],
      "properties": {"datetime": datetime.toUtc().toIso8601String()},
    },
  };

  Map<String, dynamic> toRequestJson() => {
    "sighting": {
      "location": _locationJson(),
      "status": status,
      "comments": comments,
      "type": type,
      "species": species,
      "name": name,
      "method": method,
    },
    "observer": {"id": observerIdPlaceholder, "location": _locationJson()},
    "images": [],
  };
}

/// One element of GET /sightings — annotate_record()'s output. Only parses what the list
/// screen needs; @id/@type/_links/species_uri/observer/images/source/moderation_status are
/// all deliberately ignored (delete is out of scope for v1, same as every other field here).
class SightingRecord {
  final String id;
  final DateTime createdAt;
  final Sighting sighting;

  SightingRecord({
    required this.id,
    required this.createdAt,
    required this.sighting,
  });

  factory SightingRecord.fromJson(Map<String, dynamic> json) {
    return SightingRecord(
      id: json["id"] as String,
      createdAt: DateTime.parse(json["created_at"] as String),
      sighting: Sighting.fromJson(json["sighting"] as Map<String, dynamic>),
    );
  }
}
