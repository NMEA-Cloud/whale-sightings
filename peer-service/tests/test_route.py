import pytest

import math
import random

from route import (
    AREAS,
    METERS_PER_DEGREE_LAT,
    ROCKWALL_TX_POLYGON,
    ROUTES,
    PolygonWanderer,
    interpolate,
    jitter,
    point_in_polygon,
    position_source,
    segment_inside,
    segments_cross,
)

# On the equator, cos(mean_lat) == 1, so distance along longitude reduces to plain
# subtraction — makes the expected positions below easy to verify by hand. Deliberately
# unequal segment lengths (1, 2, 3 units, wrapping) so these tests actually distinguish
# distance-weighted interpolation from the old equal-share-per-waypoint behavior — under
# the old scheme these same `t` values would land on entirely different positions.
WAYPOINTS = [(0.0, 0.0), (0.0, 10.0), (0.0, 30.0)]
# Segment lengths: (0,0)->(0,10) = 10, (0,10)->(0,30) = 20, (0,30)->(0,0) wrap = 30.
# Total = 60, so cumulative boundaries are at t = 10/60, 30/60, 60/60 = 1/6, 1/2, 1.


def test_interpolate_at_t_zero_returns_first_waypoint():
    assert interpolate(WAYPOINTS, 0.0) == (0.0, 0.0)


def test_interpolate_weights_by_distance_not_waypoint_count():
    # Midpoint of segment 0 ([0, 1/6)): halfway from (0,0) to (0,10).
    assert interpolate(WAYPOINTS, 1 / 12) == pytest.approx((0.0, 5.0))
    # Midpoint of segment 1 ([1/6, 1/2)): halfway from (0,10) to (0,30). Under the old
    # equal-share scheme, t=1/3 would instead land exactly on waypoint 1, (0.0, 10.0).
    assert interpolate(WAYPOINTS, 1 / 3) == pytest.approx((0.0, 20.0))
    # Midpoint of segment 2 ([1/2, 1)), which wraps from (0,30) back to (0,0).
    assert interpolate(WAYPOINTS, 3 / 4) == pytest.approx((0.0, 15.0))


def test_interpolate_is_periodic():
    assert interpolate(WAYPOINTS, 0.25) == interpolate(WAYPOINTS, 1.25)


def test_interpolate_handles_negative_t():
    assert interpolate(WAYPOINTS, -0.75) == pytest.approx(interpolate(WAYPOINTS, 0.25))


def test_interpolate_rejects_empty_waypoints():
    with pytest.raises(ValueError):
        interpolate([], 0.5)


def test_interpolate_single_waypoint_returns_it_regardless_of_t():
    assert interpolate([(1.0, 2.0)], 0.9) == (1.0, 2.0)


def test_interpolate_handles_coincident_waypoints_without_dividing_by_zero():
    # Every waypoint at the same point means every segment has zero length — falls back to
    # equal shares rather than raising a ZeroDivisionError.
    same_point = [(5.0, 5.0), (5.0, 5.0), (5.0, 5.0)]
    assert interpolate(same_point, 0.5) == (5.0, 5.0)


@pytest.mark.parametrize("profile", sorted(ROUTES | AREAS))
def test_every_profile_builds_a_position_source_that_yields_positions(profile):
    positions = position_source(profile, random.Random(1), jitter_meters=40)

    lat, lon = positions.next_position()

    assert -90 <= lat <= 90 and -180 <= lon <= 180


def test_unknown_profile_is_rejected():
    with pytest.raises(RuntimeError, match="Unknown LOCATION_PROFILE 'nowhere'"):
        position_source("nowhere", random.Random(1), jitter_meters=40)


def _meters_between(a, b):
    """Same flat-earth conversion jitter() itself uses."""
    dy = (b[0] - a[0]) * METERS_PER_DEGREE_LAT
    dx = (b[1] - a[1]) * METERS_PER_DEGREE_LAT * math.cos(math.radians(a[0]))
    return math.hypot(dx, dy)


# Both LOCATION_PROFILE latitudes (Puget Sound, Lake Ray Hubbard), so the longitude
# scaling (which depends on latitude) is exercised at each.
@pytest.mark.parametrize("point", [(47.7, -122.45), (32.8, -96.5)])
def test_jitter_stays_within_max_meters(point):
    rng = random.Random(1)
    for _ in range(1000):
        assert _meters_between(point, jitter(point, 40, rng)) <= 40 + 1e-6


@pytest.mark.parametrize("max_meters", [0, -5])
def test_jitter_disabled_returns_point_unchanged(max_meters):
    assert jitter((32.8, -96.5), max_meters, random.Random(1)) == (32.8, -96.5)


def test_jitter_is_deterministic_for_a_seed_and_varies_between_draws():
    first = [jitter((32.8, -96.5), 40, random.Random(7)) for _ in range(3)]
    assert first[0] == first[1] == first[2]

    rng = random.Random(7)
    draws = [jitter((32.8, -96.5), 40, rng) for _ in range(100)]
    assert len(set(draws)) == 100


def test_jitter_spreads_over_the_whole_disk():
    # Uniform over the disk's area puts ~75% of points beyond half the radius and ~25%
    # within it — a missing sqrt (bunched at the center) or a circle-only bug (all at
    # max_meters) would fail one side of this.
    point = (32.8, -96.5)
    rng = random.Random(3)
    distances = [_meters_between(point, jitter(point, 40, rng)) for _ in range(2000)]
    inner = sum(d < 20 for d in distances) / len(distances)
    assert 0.18 < inner < 0.32
    assert max(distances) > 35


# --- polygon areas -----------------------------------------------------------------------

SQUARE = [(0.0, 0.0), (0.0, 1.0), (1.0, 1.0), (1.0, 0.0)]
# A "U": two arms (lon 0-1 and lon 2-3) joined along the bottom (lat 0-1); the notch between
# the arms (lon 1-2, lat 1-3) is outside. Written as (lon, lat) for readability, then flipped
# to this module's (lat, lon) order.
U_SHAPE = [(lat, lon) for lon, lat in [(0, 0), (3, 0), (3, 3), (2, 3), (2, 1), (1, 1), (1, 3), (0, 3)]]


def test_point_in_polygon_square():
    assert point_in_polygon((0.5, 0.5), SQUARE)
    assert not point_in_polygon((1.5, 0.5), SQUARE)
    assert not point_in_polygon((0.5, -0.01), SQUARE)
    assert point_in_polygon((0.99, 0.99), SQUARE)


def test_point_in_polygon_concave_notch_is_outside():
    assert point_in_polygon((2.5, 0.5), U_SHAPE)  # left arm
    assert point_in_polygon((2.5, 2.5), U_SHAPE)  # right arm
    assert point_in_polygon((0.5, 1.5), U_SHAPE)  # bottom bar
    assert not point_in_polygon((2.5, 1.5), U_SHAPE)  # the notch


def test_segment_between_arms_is_not_inside_even_though_both_ends_are():
    left_arm, right_arm = (2.5, 0.5), (2.5, 2.5)

    assert point_in_polygon(left_arm, U_SHAPE) and point_in_polygon(right_arm, U_SHAPE)
    assert not segment_inside(left_arm, right_arm, U_SHAPE)
    assert segment_inside((0.5, 0.5), (0.5, 2.5), U_SHAPE)  # along the bottom bar is fine


def test_rockwall_polygon_is_a_valid_outline_of_the_lake():
    polygon = ROCKWALL_TX_POLYGON
    n = len(polygon)
    assert n >= 3
    # Every vertex is around Lake Ray Hubbard — catches a typo or swapped lat/lon.
    for lat, lon in polygon:
        assert 32.7 < lat < 33.0 and -96.6 < lon < -96.4
    # No edge crosses another (non-adjacent) edge.
    for i in range(n):
        for j in range(i + 2, n):
            if i == 0 and j == n - 1:
                continue  # adjacent via the wrap-around
            a, b = polygon[i], polygon[(i + 1) % n]
            c, d = polygon[j], polygon[(j + 1) % n]
            assert not segments_cross(a, b, c, d), f"edges {i} and {j} cross"


def _meters(a, b):
    dy = (b[0] - a[0]) * METERS_PER_DEGREE_LAT
    dx = (b[1] - a[1]) * METERS_PER_DEGREE_LAT * math.cos(math.radians((a[0] + b[0]) / 2))
    return math.hypot(dx, dy)


@pytest.fixture(scope="module")
def rockwall_track():
    wanderer = PolygonWanderer(ROCKWALL_TX_POLYGON, random.Random(42))
    return [wanderer.next_position() for _ in range(5000)]


def test_wanderer_never_leaves_the_lake(rockwall_track):
    for point in rockwall_track:
        assert point_in_polygon(point, ROCKWALL_TX_POLYGON)
    for a, b in zip(rockwall_track, rockwall_track[1:]):
        assert segment_inside(a, b, ROCKWALL_TX_POLYGON)


def test_wanderer_steps_are_at_most_the_step_length(rockwall_track):
    for a, b in zip(rockwall_track, rockwall_track[1:]):
        assert _meters(a, b) <= 450 + 1


def test_wanderer_never_repeats_a_position(rockwall_track):
    assert len(set(rockwall_track)) == len(rockwall_track)


def test_wanderer_covers_both_ends_of_the_lake(rockwall_track):
    lats = [lat for lat, _ in rockwall_track]
    assert min(lats) < 32.83  # the southern end, near the dam
    assert max(lats) > 32.94  # the northern arm


def test_wanderer_is_deterministic_for_a_seed():
    first = PolygonWanderer(ROCKWALL_TX_POLYGON, random.Random(7))
    second = PolygonWanderer(ROCKWALL_TX_POLYGON, random.Random(7))

    assert [first.next_position() for _ in range(20)] == [second.next_position() for _ in range(20)]


# --- resuming a previous run ---------------------------------------------------------------

# Open water in the basin north of I-30, with room to keep heading north.
PREVIOUS, LAST = (32.896, -96.495), (32.900, -96.495)


def test_wanderer_resumes_from_last_position_without_repeating_it():
    wanderer = PolygonWanderer(ROCKWALL_TX_POLYGON, random.Random(1), resume_from=[PREVIOUS, LAST])

    first = wanderer.next_position()

    assert wanderer.resumed
    assert first != LAST
    assert _meters(LAST, first) <= 450 + 1
    assert segment_inside(LAST, first, ROCKWALL_TX_POLYGON)


def test_wanderer_resumes_heading_the_way_it_was_going():
    # PREVIOUS -> LAST heads due north; the first gentle turn is at most 45 degrees off it.
    wanderer = PolygonWanderer(ROCKWALL_TX_POLYGON, random.Random(1), resume_from=[PREVIOUS, LAST])

    first = wanderer.next_position()

    dy = first[0] - LAST[0]
    dx = (first[1] - LAST[1]) * math.cos(math.radians(LAST[0]))
    assert abs(math.degrees(math.atan2(dx, dy))) <= 45 + 1e-6


def test_wanderer_ignores_a_last_position_outside_the_polygon():
    puget_sound = (47.7, -122.45)  # e.g. left over from a different LOCATION_PROFILE
    wanderer = PolygonWanderer(ROCKWALL_TX_POLYGON, random.Random(1), resume_from=[puget_sound])

    first = wanderer.next_position()

    assert not wanderer.resumed
    assert point_in_polygon(first, ROCKWALL_TX_POLYGON)


def test_route_profiles_always_restart_at_the_beginning():
    positions = position_source("puget-sound", random.Random(1), jitter_meters=0, resume_from=[(48.2, -122.85)])

    assert positions.next_position() == ROUTES["puget-sound"][0]
