"""Waypoints + interpolation for peer-service's simulated moving pod — pure functions, no
I/O, unit-testable in isolation (see tests/test_route.py)."""

from __future__ import annotations

import bisect
import math

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
WAYPOINTS: list[Waypoint] = [
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
