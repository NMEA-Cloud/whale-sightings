import pytest

import math
import random

from route import METERS_PER_DEGREE_LAT, ROUTES, interpolate, jitter

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


def test_all_profiles_have_nonempty_waypoints():
    # Purely structural — catches a forgotten placeholder or an import typo for a
    # LOCATION_PROFILE (main.py). Real-world geography (does a route actually stay in open
    # water) is verified by hand against OpenStreetMap, not something this can assert.
    for name, waypoints in ROUTES.items():
        assert waypoints, f"{name} route has no waypoints"


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
