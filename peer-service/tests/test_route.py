import pytest

from route import interpolate

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
