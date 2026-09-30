import math

from rokey_p3_navigation.docking import (
    base_stopped,
    departure_allowed,
    docked,
    goal_timeout_s,
    observation_fresh,
    pose_error,
    settle_ok,
    speed_is_quiet,
)

TOL_XY = 0.05
TOL_YAW = 0.05
AT_DOCK = (1.0, 2.0, 0.5)


def test_pose_error_is_planar_distance_and_folded_angle():
    distance, angle = pose_error((1.0, 1.0, math.pi - 0.1), (0.0, 1.0, -math.pi + 0.1))
    assert abs(distance - 1.0) < 1e-9
    assert abs(angle - 0.2) < 1e-9


def test_docked_inside_both_tolerances():
    assert docked((1.04, 2.0, 0.5), AT_DOCK, TOL_XY, TOL_YAW)


def test_not_docked_when_only_one_tolerance_is_met():
    assert not docked((1.06, 2.0, 0.5), AT_DOCK, TOL_XY, TOL_YAW)
    assert not docked((1.0, 2.0, 0.56), AT_DOCK, TOL_XY, TOL_YAW)


def test_diagonal_offset_uses_the_distance_not_each_axis():
    # x, y 각각은 0.04 로 안쪽이지만 거리는 0.0566 이라 밖이다.
    assert not docked((1.04, 2.04, 0.5), AT_DOCK, TOL_XY, TOL_YAW)


def test_tolerance_zero_is_never_docked():
    # zones.yaml 뼈대의 0 은 "아직 안 정함" 이다. 9/19 측정 전에는 도착이 성립하지 않는다.
    assert not docked(AT_DOCK, AT_DOCK, 0.0, TOL_YAW)
    assert not docked(AT_DOCK, AT_DOCK, TOL_XY, 0.0)


def test_speed_threshold_is_exclusive():
    assert speed_is_quiet(0.019, 0.019, 0.02, 0.02)
    assert not speed_is_quiet(0.02, 0.0, 0.02, 0.02)
    assert not speed_is_quiet(0.0, 0.02, 0.02, 0.02)
    assert speed_is_quiet(-0.01, -0.01, 0.02, 0.02)


def test_stopped_needs_no_goal_and_the_full_hold():
    assert base_stopped(False, 0.5, 0.5)
    assert base_stopped(False, 1.2, 0.5)
    assert not base_stopped(False, 0.49, 0.5)
    assert not base_stopped(True, 10.0, 0.5)


def test_stale_odom_cannot_settle_even_when_quiet_and_on_target():
    # N1: 캐시 자세가 목표이고 quiet 누적이 있어도 odom age 100 s 는 도착이 아니다.
    # 100 은 합성값이다. 문턱은 기존 odom_timeout_s(1.0)를 그대로 쓴다.
    assert not settle_ok(quiet_for=10.0, quiet_hold=0.5, odom_age_s=100.0, odom_timeout_s=1.0)
    assert not settle_ok(quiet_for=10.0, quiet_hold=0.5, odom_age_s=None, odom_timeout_s=1.0)
    assert settle_ok(quiet_for=0.5, quiet_hold=0.5, odom_age_s=0.1, odom_timeout_s=1.0)


def test_observation_fresh_matches_the_stopped_heartbeat_window():
    assert observation_fresh(0.0, 1.0)
    assert observation_fresh(1.0, 1.0)
    assert not observation_fresh(1.0001, 1.0)
    assert not observation_fresh(None, 1.0)
    assert not observation_fresh(-0.1, 1.0)


def test_departure_needs_a_fresh_true():
    assert departure_allowed(True, 0.3, 1.0)
    assert departure_allowed(True, 1.0, 1.0)
    assert not departure_allowed(True, 1.2, 1.0)
    assert not departure_allowed(False, 0.0, 1.0)


def test_departure_rejects_unknown():
    assert not departure_allowed(None, None, 1.0)
    assert not departure_allowed(None, 0.1, 1.0)
    assert not departure_allowed(True, None, 1.0)


def test_goal_timeout_by_zone_kind():
    assert goal_timeout_s('load', 120.0, 180.0) == 120.0
    assert goal_timeout_s('dock', 120.0, 180.0) == 120.0
    assert goal_timeout_s('bed', 120.0, 180.0) == 180.0
    assert goal_timeout_s('station', 120.0, 180.0) == 180.0
