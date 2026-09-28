"""Where peer-service's simulated moving pod goes — pure functions, no I/O, unit-testable in
isolation (see tests/test_route.py). Two kinds of LOCATION_PROFILE:

- A waypoint route (ROUTES): the pod follows a hand-verified loop via interpolate(), with a
  small random offset per sighting (jitter()).
- An area (AREAS): the pod wanders freely inside a polygon outlining open water
  (PolygonWanderer), each sighting a short step from the last.

position_source() picks the right one for a profile."""

from __future__ import annotations

import bisect
import math
import random

Waypoint = tuple[float, float]  # (lat, lon)

# A there-and-back route through the San Juan Islands and south into Puget Sound — the same
# general area client-admin's own demo scenarios use, so a peer-service sighting looks at home
# next to them on a map. Deliberately uneven: the first few waypoints sit within a few tenths
# of a nautical mile of each other (Lime Kiln Point), while the rest span tens of miles down
# through the Sound — interpolate() below accounts for that, not this list.
#
# Every point, AND every straight segment between consecutive points (not just their
# endpoints), was checked against OpenStreetMap by hand to confirm it stays in open water —
# whales don't come ashore, and this list is short and static enough that hand-verification
# beats pulling in a geo-classification dependency. That ruled out a naive "waypoint 1 ->
# waypoint 2 -> ... -> loop back to 1" shape: a straight line between two water points can
# still cut across an intervening island or peninsula (e.g. San Juan Island itself, or the
# Kitsap Peninsula between Puget Sound and the San Juans), and the return leg from Puget Sound
# straight back to the San Juans is exactly such a case. So instead of a single loop, this is a
# real out-and-back: it follows the open channel south (Haro Strait -> Strait of Juan de Fuca
# -> Admiralty Inlet -> Puget Sound) and then retraces the same verified-clear corridor back
# north, rather than a shortcut over land. Checking only each segment's midpoint isn't enough
# either — a segment can clear both its endpoint neighborhoods and its exact midpoint while
# still clipping a headland at some other point along it (this happened once already, with
# Whidbey Island's Admiralty Head/Fort Casey between the two points nearest it below — hence
# that specific extra waypoint pulling the line further offshore before it turns toward Fort
# Casey State Park). Four pinch points needed a specific detour, not just a straight shot
# between two open-water points: San Juan Island's own coastline (hence the cluster near Lime
# Kiln sits offshore, not on it), Whidbey Island's Admiralty Head, Indian/Marrowstone Islands
# narrowing Admiralty Inlet's entrance (routed east of them, past Fort Casey), and the Kitsap
# Peninsula's Point No Point/Hansville tip narrowing Puget Sound's entrance (routed east of it,
# not a direct line south from Admiralty Inlet).
PUGET_SOUND_WAYPOINTS: list[Waypoint] = [
    # Outbound: San Juan Islands -> Strait of Juan de Fuca -> Admiralty Inlet -> Puget Sound
    (48.516, -123.18),
    (48.513, -123.19),
    (48.519, -123.156),
    (48.522, -123.16),
    (48.35, -123.05),
    (48.20, -122.85),
    (48.155, -122.70),
    (48.14, -122.63),
    (47.98, -122.66),
    (47.93, -122.48),
    (47.85, -122.50),
    (47.70, -122.45),
    # Return: retrace the same open-water corridor back north
    (47.85, -122.50),
    (47.93, -122.48),
    (47.98, -122.66),
    (48.14, -122.63),
    (48.155, -122.70),
    (48.20, -122.85),
    (48.35, -123.05),
]

# Lake Ray Hubbard (Rockwall, TX — the trade-show venue's local lake): an outline of its open
# water, supplied by the project owner as (lat, lon) vertices in order around the perimeter.
# The pod wanders anywhere inside it (PolygonWanderer) rather than following a fixed route,
# so the only thing that has to be right about the lake's shape is this outline itself.
ROCKWALL_TX_POLYGON: list[Waypoint] = [
    (32.801670636029755, -96.49546347099154),
    (32.80856564748744, -96.52509812570078),
    (32.82333081711253, -96.53516692930376),
    (32.85887151645536, -96.53221852405925),
    (32.86853824595756, -96.50537024788387),
    (32.891697348858614, -96.51053597877258),
    (32.92031461173164, -96.50006230031669),
    (32.94297987926426, -96.51363207594133),
    (32.97729160248317, -96.50004852490305),
    (32.97518358155846, -96.48321541872562),
    (32.960569462940335, -96.48808916171697),
    (32.943721908469065, -96.50049132820399),
    (32.93739997236853, -96.48558223162752),
    (32.91351784900801, -96.4745753417717),
    (32.89983346930533, -96.4889926514224),
    (32.87700764257871, -96.49348742490017),
    (32.853872031047906, -96.4965942956694),
    (32.836905653393764, -96.51231303124236),
    (32.82766437443781, -96.51063964475692),
    (32.81113922050193, -96.49369195490858),
]

# Keyed by LOCATION_PROFILE (config.py). A profile is either a waypoint route or an area —
# see position_source(), which main.py calls once at startup.
ROUTES: dict[str, list[Waypoint]] = {
    "puget-sound": PUGET_SOUND_WAYPOINTS,
}
AREAS: dict[str, list[Waypoint]] = {
    "rockwall-tx": ROCKWALL_TX_POLYGON,
}


def _distance(a: Waypoint, b: Waypoint) -> float:
    """A flat-earth approximation — not haversine-precise, but plenty good at this scale,
    and only ever used to weight segments against each other, never as a real distance."""
    lat1, lon1 = a
    lat2, lon2 = b
    mean_lat = math.radians((lat1 + lat2) / 2)
    dlat = lat2 - lat1
    dlon = (lon2 - lon1) * math.cos(mean_lat)
    return math.hypot(dlat, dlon)


def _segment_boundaries(waypoints: list[Waypoint]) -> list[float]:
    """Cumulative fraction of the total route length at the end of each segment — e.g.
    [0.2, 0.5, 1.0] for three segments whose real lengths are in a 2:3:5 ratio. This is what
    makes interpolate() advance at a roughly constant real-world speed: a segment between
    two nearby waypoints gets a proportionally small share of `t`, instead of the same
    1/len(waypoints) share every other segment gets regardless of how physically long it
    is (the bug this was written to fix — see the README/commit history if curious)."""
    n = len(waypoints)
    lengths = [_distance(waypoints[i], waypoints[(i + 1) % n]) for i in range(n)]
    total = sum(lengths)
    if total == 0:
        return [(i + 1) / n for i in range(n)]  # coincident waypoints — equal shares is the only sane fallback
    cumulative = []
    running = 0.0
    for length in lengths:
        running += length
        cumulative.append(running / total)
    cumulative[-1] = 1.0  # avoid a sub-1.0 final boundary from float rounding
    return cumulative


def interpolate(waypoints: list[Waypoint], t: float) -> Waypoint:
    """Maps t (any real number; only the fractional part matters) to a position along the
    closed loop through waypoints — linearly interpolated between consecutive points,
    weighted by each segment's real-world distance (see _segment_boundaries) so equal steps
    in t cover roughly equal real distance regardless of how the waypoints happen to be
    spaced. Wraps from the last point back to the first so the route repeats indefinitely."""
    if not waypoints:
        raise ValueError("waypoints must be non-empty")
    if len(waypoints) == 1:
        return waypoints[0]

    n = len(waypoints)
    boundaries = _segment_boundaries(waypoints)
    frac_t = t % 1.0

    i = min(bisect.bisect_right(boundaries, frac_t), n - 1)
    segment_start = boundaries[i - 1] if i > 0 else 0.0
    segment_span = boundaries[i] - segment_start
    local_frac = (frac_t - segment_start) / segment_span if segment_span > 0 else 0.0

    lat1, lon1 = waypoints[i]
    lat2, lon2 = waypoints[(i + 1) % n]
    return (lat1 + (lat2 - lat1) * local_frac, lon1 + (lon2 - lon1) * local_frac)


METERS_PER_DEGREE_LAT = 111_320.0


def jitter(point: Waypoint, max_meters: float, rng: random.Random) -> Waypoint:
    """A point picked uniformly at random within `max_meters` of `point` — so repeated laps
    of a deterministic route (and restarts, which begin again at t=0) don't post sightings
    at exactly the same coordinates, stacking map pins on top of each other.

    The route's waypoints and the straight segments between them were hand-checked to stay
    in open water (see the route comments above), but this moves a point sideways off that
    line — so `max_meters` must stay well under the narrowest channel's clearance from shore.

    Flat-earth meters-to-degrees conversion, same approximation _distance() uses — plenty
    good at tens of meters. `max_meters <= 0` disables it. `rng` is injected so tests can be
    deterministic."""
    if max_meters <= 0:
        return point
    lat, lon = point
    # sqrt keeps points evenly spread over the disk's area rather than bunched at its center.
    r = max_meters * math.sqrt(rng.random())
    theta = 2 * math.pi * rng.random()
    dlat = (r * math.sin(theta)) / METERS_PER_DEGREE_LAT
    dlon = (r * math.cos(theta)) / (METERS_PER_DEGREE_LAT * math.cos(math.radians(lat)))
    return (lat + dlat, lon + dlon)


def point_in_polygon(point: Waypoint, polygon: list[Waypoint]) -> bool:
    """Ray casting (even-odd rule). Works directly in degrees: only inside/outside matters
    here, not distance, so no projection is needed at this scale."""
    lat, lon = point
    inside = False
    n = len(polygon)
    for i in range(n):
        lat1, lon1 = polygon[i]
        lat2, lon2 = polygon[(i + 1) % n]
        if (lat1 > lat) != (lat2 > lat):
            crossing_lon = lon1 + (lat - lat1) * (lon2 - lon1) / (lat2 - lat1)
            if lon < crossing_lon:
                inside = not inside
    return inside


def _orientation(a: Waypoint, b: Waypoint, c: Waypoint) -> float:
    return (b[1] - a[1]) * (c[0] - a[0]) - (b[0] - a[0]) * (c[1] - a[1])


def segments_cross(a: Waypoint, b: Waypoint, c: Waypoint, d: Waypoint) -> bool:
    """Whether segment a-b properly crosses segment c-d (touching endpoints don't count —
    irrelevant with random float positions)."""
    return (_orientation(a, b, c) * _orientation(a, b, d) < 0) and (
        _orientation(c, d, a) * _orientation(c, d, b) < 0
    )


def segment_inside(a: Waypoint, b: Waypoint, polygon: list[Waypoint]) -> bool:
    """Both ends inside AND the straight line between them crosses no edge — so a step can't
    jump across a peninsula even when both of its ends are in open water."""
    if not (point_in_polygon(a, polygon) and point_in_polygon(b, polygon)):
        return False
    n = len(polygon)
    return not any(segments_cross(a, b, polygon[i], polygon[(i + 1) % n]) for i in range(n))


def _offset(point: Waypoint, meters: float, heading: float) -> Waypoint:
    """`meters` from `point` in compass direction `heading` (radians, 0 = north) — same
    flat-earth conversion jitter() uses."""
    lat, lon = point
    dlat = meters * math.cos(heading) / METERS_PER_DEGREE_LAT
    dlon = meters * math.sin(heading) / (METERS_PER_DEGREE_LAT * math.cos(math.radians(lat)))
    return (lat + dlat, lon + dlon)


def _heading(a: Waypoint, b: Waypoint) -> float:
    """Compass direction (radians, 0 = north) from a to b — the inverse of _offset()."""
    dy = b[0] - a[0]
    dx = (b[1] - a[1]) * math.cos(math.radians(a[0]))
    return math.atan2(dx, dy)


def random_point_in_polygon(polygon: list[Waypoint], rng: random.Random) -> Waypoint:
    """Uniform over the polygon's area, by rejection sampling its bounding box."""
    lats = [p[0] for p in polygon]
    lons = [p[1] for p in polygon]
    for _ in range(10_000):
        candidate = (rng.uniform(min(lats), max(lats)), rng.uniform(min(lons), max(lons)))
        if point_in_polygon(candidate, polygon):
            return candidate
    raise ValueError("couldn't find a point inside the polygon — is it degenerate?")


class RouteWalker:
    """A waypoint-route profile: interpolate() along the loop, one step per call, with
    jitter() applied to each position."""

    def __init__(
        self, waypoints: list[Waypoint], rng: random.Random, jitter_meters: float, steps_per_waypoint: int = 4
    ) -> None:
        self._waypoints = waypoints
        self._rng = rng
        self._jitter_meters = jitter_meters
        # steps_per_waypoint positions generated per waypoint, so consecutive sightings trace
        # a smoothly moving pod rather than jumping waypoint to waypoint.
        self._step = 1.0 / (len(waypoints) * steps_per_waypoint)
        self._t = 0.0

    def next_position(self) -> Waypoint:
        point = jitter(interpolate(self._waypoints, self._t), self._jitter_meters, self._rng)
        self._t += self._step
        return point


class PolygonWanderer:
    """An area profile: each call moves the pod about `step_meters` in a gently curving
    direction, never leaving the polygon (every step's straight line is checked, not just its
    endpoint). No jitter: positions never repeat, and an offset could push a point outside
    the outline.

    `resume_from` (oldest first) continues a previous run instead of starting at a random
    point: the pod steps on from the last position, heading the way it was going (from the
    one before it). Ignored if the last position isn't inside this polygon — e.g. left over
    from a different LOCATION_PROFILE."""

    MAX_TURN = math.radians(45)
    GENTLE_TRIES = 8  # tries at a gentle turn from the current heading before any direction
    TRIES_PER_STEP_SIZE = 24
    MIN_STEP_METERS = 25.0

    def __init__(
        self,
        polygon: list[Waypoint],
        rng: random.Random,
        step_meters: float = 450.0,
        resume_from: list[Waypoint] | None = None,
    ) -> None:
        self._polygon = polygon
        self._rng = rng
        self._step_meters = step_meters
        self._heading = rng.uniform(0, 2 * math.pi)
        last = resume_from[-1] if resume_from else None
        self.resumed = last is not None and point_in_polygon(last, polygon)
        if self.resumed:
            # Already posted by the previous run — step on from it rather than repeating it.
            self._position = last
            self._started = True
            if len(resume_from) >= 2:
                self._heading = _heading(resume_from[-2], last)
        else:
            self._position = random_point_in_polygon(polygon, rng)
            self._started = False

    def next_position(self) -> Waypoint:
        if not self._started:
            self._started = True
            return self._position

        step = self._step_meters
        while step >= self.MIN_STEP_METERS:
            for attempt in range(self.TRIES_PER_STEP_SIZE):
                if attempt < self.GENTLE_TRIES:
                    heading = self._heading + self._rng.uniform(-self.MAX_TURN, self.MAX_TURN)
                else:
                    heading = self._rng.uniform(0, 2 * math.pi)  # boxed in: try any direction
                candidate = _offset(self._position, step, heading)
                if segment_inside(self._position, candidate, self._polygon):
                    self._position, self._heading = candidate, heading
                    return candidate
            step /= 2
        # Nowhere to go even at the minimum step (shouldn't happen for a sane outline) — stay
        # put rather than leave the polygon.
        return self._position


def check_profile(profile: str) -> None:
    if profile not in ROUTES and profile not in AREAS:
        raise RuntimeError(f"Unknown LOCATION_PROFILE {profile!r}; expected one of {sorted(ROUTES | AREAS)}")


def position_source(
    profile: str, rng: random.Random, jitter_meters: float, resume_from: list[Waypoint] | None = None
) -> RouteWalker | PolygonWanderer:
    """The pod's movement for a LOCATION_PROFILE — main.py calls this once at startup and
    then next_position() for every sighting. `resume_from` (this peer's most recent posted
    positions, oldest first) lets an area profile continue where the previous run left off;
    waypoint routes always restart at their beginning (an out-and-back route passes most
    points twice, so a position alone can't say which way the pod was going)."""
    check_profile(profile)
    if profile in ROUTES:
        return RouteWalker(ROUTES[profile], rng, jitter_meters)
    return PolygonWanderer(AREAS[profile], rng, resume_from=resume_from)
