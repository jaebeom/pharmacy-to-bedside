import math

from rokey_p3_navigation.base_kinematics import (
    body_to_world_velocity,
    difference_velocity,
    odom_from_joints,
    wrap_angle,
    world_to_body_velocity,
    yaw_to_quaternion,
)

CLOSE = 1e-9


def test_yaw_zero_is_identity():
    assert body_to_world_velocity(0.3, -0.2, 0.1, 0.0) == (0.3, -0.2, 0.1)


def test_quarter_turn_maps_forward_to_world_y():
    dx, dy, dyaw = body_to_world_velocity(1.0, 0.0, 0.0, math.pi / 2.0)
    assert abs(dx) < CLOSE
    assert abs(dy - 1.0) < CLOSE
    assert dyaw == 0.0


def test_half_turn_reverses_both_axes():
    dx, dy, _ = body_to_world_velocity(0.4, 0.25, 0.0, math.pi)
    assert abs(dx + 0.4) < CLOSE
    assert abs(dy + 0.25) < CLOSE


def test_angular_velocity_is_not_rotated():
    for yaw in (0.0, 0.7, -2.5, math.pi):
        assert body_to_world_velocity(0.0, 0.0, 0.35, yaw)[2] == 0.35


def test_world_to_body_is_the_inverse():
    for yaw in (0.0, 0.3, 1.9, -2.7, math.pi):
        world = body_to_world_velocity(0.31, -0.17, 0.22, yaw)
        back = world_to_body_velocity(*world, yaw)
        for got, want in zip(back, (0.31, -0.17, 0.22), strict=True):
            assert abs(got - want) < CLOSE


def test_odom_keeps_joint_positions_as_they_are():
    pose, _ = odom_from_joints(2.5, -1.25, 0.0, 0.0, 0.0, 0.0)
    assert pose == (2.5, -1.25, 0.0)


def test_odom_twist_is_in_the_child_frame():
    # world 로 +y 로 움직이는데 로봇이 왼쪽(+90도)을 보고 있으면 전진 속도로 읽힌다.
    _, twist = odom_from_joints(0.0, 0.0, math.pi / 2.0, 0.0, 0.6, 0.0)
    assert abs(twist[0] - 0.6) < CLOSE
    assert abs(twist[1]) < CLOSE
    assert twist[2] == 0.0


def test_odom_yaw_is_wrapped():
    pose, _ = odom_from_joints(0.0, 0.0, 3.0 * math.pi, 0.0, 0.0, 0.0)
    assert abs(pose[2] - math.pi) < 1e-9 or abs(pose[2] + math.pi) < 1e-9


def test_wrap_angle_folds_to_half_open_interval():
    assert abs(wrap_angle(0.0)) < CLOSE
    assert abs(wrap_angle(2.0 * math.pi) - 0.0) < 1e-9
    assert abs(wrap_angle(-3.0 * math.pi / 2.0) - math.pi / 2.0) < 1e-9


def test_difference_velocity_needs_a_positive_step():
    assert difference_velocity((0.0, 0.0, 0.0), (1.0, 1.0, 1.0), 0.0) == (0.0, 0.0, 0.0)
    assert difference_velocity((0.0, 0.0, 0.0), (1.0, 1.0, 1.0), -0.1) == (0.0, 0.0, 0.0)


def test_difference_velocity_takes_the_short_way_round():
    dx, dy, dyaw = difference_velocity((0.0, 0.0, math.pi - 0.05),
                                       (0.5, -0.5, -math.pi + 0.05), 0.5)
    assert abs(dx - 1.0) < CLOSE
    assert abs(dy + 1.0) < CLOSE
    assert abs(dyaw - 0.2) < 1e-9


def test_quaternion_is_a_z_rotation():
    x, y, z, w = yaw_to_quaternion(math.pi / 2.0)
    assert x == 0.0 and y == 0.0
    assert abs(z - math.sqrt(0.5)) < CLOSE
    assert abs(w - math.sqrt(0.5)) < CLOSE
    assert abs(z * z + w * w - 1.0) < CLOSE
