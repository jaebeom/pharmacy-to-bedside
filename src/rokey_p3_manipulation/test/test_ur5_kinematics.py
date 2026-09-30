"""L1: UR5 정기구학·역기구학. ROS 없이 돈다."""

import math

import numpy as np
import pytest

from rokey_p3_manipulation import ur5_kinematics as kin

from rokey_p3_manipulation.ur5_kinematics import (
    UR5_DH,
    UR5_JOINT_LIMITS,
    at_pose,
    clamp_to_limits,
    facing_pose,
    invert,
    forward_kinematics,
    interpolate_joint_path,
    jacobian,
    matrix_from_quaternion,
    nearest_wrapped,
    solve_ik,
    top_down_pose,
    within_limits,
    yaw_of,
)

# 왕복 시험용 자세. 특이점(팔을 완전히 편 자세, 손목 정렬)을 피한 값이다.
SAMPLE_JOINTS = (
    (0.0, -1.2, 1.1, -1.4, -1.5, 0.3),
    (0.7, -0.9, 1.6, -2.0, -1.5, -0.8),
    (-1.1, -1.7, 2.0, -1.0, 1.2, 1.9),
    (2.4, -2.2, 1.3, -0.7, -0.9, -2.5),
    (-2.0, -0.5, 0.8, -1.9, 1.7, 0.6),
)


def test_dh_table_is_the_ur5_standard_table():
    assert len(UR5_DH) == 6
    assert [round(row[0], 6) for row in UR5_DH] == [0.089159, 0.0, 0.0, 0.10915, 0.09465, 0.0823]
    assert [round(row[1], 6) for row in UR5_DH] == [0.0, -0.425, -0.39225, 0.0, 0.0, 0.0]


def test_forward_kinematics_is_a_rigid_transform():
    for joints in SAMPLE_JOINTS:
        matrix = forward_kinematics(joints)
        rotation = matrix[:3, :3]
        assert np.allclose(rotation @ rotation.T, np.eye(3), atol=1e-9)
        assert abs(np.linalg.det(rotation) - 1.0) < 1e-9
        assert np.allclose(matrix[3], [0.0, 0.0, 0.0, 1.0])
        # 어떤 자세도 링크 길이 합보다 멀리 가지 않는다.
        assert np.linalg.norm(matrix[:3, 3]) <= 0.425 + 0.39225 + 0.10915 + 0.09465 + 0.0823 + 0.089159


def test_jacobian_matches_finite_difference():
    joints = np.asarray(SAMPLE_JOINTS[1], dtype=float)
    analytic = jacobian(joints)
    delta = 1e-6
    for index in range(6):
        shifted = joints.copy()
        shifted[index] += delta
        numeric = (forward_kinematics(shifted)[:3, 3] - forward_kinematics(joints)[:3, 3]) / delta
        assert np.allclose(analytic[:3, index], numeric, atol=1e-5)


def test_ik_round_trip_reproduces_the_forward_kinematics_pose():
    """정기구학 왕복 오차: FK(q) 를 목표로 풀고 다시 FK 를 해서 같은 자세인지 본다."""
    for joints in SAMPLE_JOINTS:
        target = forward_kinematics(joints)
        seed = np.asarray(joints, dtype=float) + 0.25
        result = solve_ik(target, seed)
        assert result.ok, f'수렴 실패: {joints} 위치오차 {result.position_error}'
        assert within_limits(result.joints)
        reached = forward_kinematics(result.joints)
        assert np.linalg.norm(reached[:3, 3] - target[:3, 3]) < 1e-4
        assert np.linalg.norm(reached[:3, :3] - target[:3, :3]) < 1e-4


def test_ik_picks_the_solution_nearest_the_seed():
    joints = np.asarray(SAMPLE_JOINTS[0], dtype=float)
    target = forward_kinematics(joints)
    near = solve_ik(target, joints + 0.05)
    assert near.ok
    assert np.max(np.abs(near.joints - joints)) < 0.05 + 1e-3
    # 시드가 바뀌면 같은 목표라도 그 시드에 가까운 해(2pi 만큼 돌아간 같은 자세)가 나온다.
    other = solve_ik(target, joints - np.array([0.0, 0.0, 0.0, 0.0, 0.0, 2.0 * math.pi]))
    assert other.ok
    assert abs(other.joints[5] - (joints[5] - 2.0 * math.pi)) < 1e-3


def test_ik_reports_failure_for_an_unreachable_target():
    target = top_down_pose((3.0, 0.0, 0.5), 0.0)
    result = solve_ik(target, (0.0, -1.2, 1.1, -1.4, -1.5, 0.0))
    assert not result.ok
    assert result.position_error > 1e-3


def test_ik_respects_tight_joint_limits():
    limits = ((-0.4, 0.4),) + tuple(UR5_JOINT_LIMITS[1:])
    joints = (0.2, -1.2, 1.1, -1.4, -1.5, 0.3)
    result = solve_ik(forward_kinematics(joints), (0.0, -1.0, 1.0, -1.4, -1.5, 0.0), limits=limits)
    assert within_limits(result.joints, limits)


def test_clamp_and_wrap_stay_inside_limits():
    assert clamp_to_limits((10.0, 0.0, 0.0, 0.0, 0.0, 0.0))[0] == UR5_JOINT_LIMITS[0][1]
    wrapped = nearest_wrapped((3.0, 0.0, 0.0, 0.0, 0.0, 0.0), (-3.2, 0.0, 0.0, 0.0, 0.0, 0.0))
    assert abs(wrapped[0] - (3.0 - 2.0 * math.pi)) < 1e-9
    assert within_limits(wrapped)


def test_at_pose_is_the_at_home_rule():
    home = (0.0, -1.2, 1.1, -1.4, -1.5, 0.0)
    assert at_pose((0.04, -1.21, 1.09, -1.4, -1.5, 0.0), home, 0.05)
    assert not at_pose((0.06, -1.2, 1.1, -1.4, -1.5, 0.0), home, 0.05)
    assert not at_pose(None, home, 0.05)
    assert not at_pose((0.0, 0.0), home, 0.05)


def test_interpolated_path_ends_on_the_goal_and_keeps_steps_small():
    path = interpolate_joint_path((0.0,) * 6, (1.0, -0.5, 0.0, 0.0, 0.0, 0.0), max_step=0.1)
    assert len(path) == 10
    assert np.allclose(path[-1], (1.0, -0.5, 0.0, 0.0, 0.0, 0.0))
    previous = np.zeros(6)
    for point in path:
        assert np.max(np.abs(point - previous)) <= 0.1 + 1e-9
        previous = point


def test_top_down_pose_points_the_tool_down():
    matrix = top_down_pose((0.4, -0.2, 0.3), math.pi / 4.0)
    assert np.allclose(matrix[:3, 2], (0.0, 0.0, -1.0), atol=1e-9)
    assert np.allclose(matrix[:3, 3], (0.4, -0.2, 0.3))
    assert abs(yaw_of(matrix) - math.pi / 4.0) < 1e-9


def test_quaternion_conversion_matches_a_known_rotation():
    matrix = matrix_from_quaternion(0.0, 0.0, math.sin(math.pi / 4.0), math.cos(math.pi / 4.0), (1.0, 2.0, 3.0))
    assert np.allclose(matrix[:3, :3], ((0.0, -1.0, 0.0), (1.0, 0.0, 0.0), (0.0, 0.0, 1.0)), atol=1e-9)
    assert np.allclose(matrix[:3, 3], (1.0, 2.0, 3.0))


def test_facing_pose_looks_back_at_the_frame():
    tag = top_down_pose((0.5, 0.0, 0.8), 0.0)   # +z 가 아래를 보는 프레임
    view = facing_pose(tag, 0.2)
    # 카메라는 태그의 +z 쪽 0.2 m 에 서서 태그를 마주본다.
    assert np.allclose(view[:3, 3], (0.5, 0.0, 0.6), atol=1e-9)
    assert np.allclose(view[:3, 2], -tag[:3, 2], atol=1e-9)


def test_invert_is_the_rigid_inverse():
    pose = top_down_pose((0.3, -0.1, 0.5), 0.7)
    assert np.allclose(invert(pose) @ pose, np.eye(4), atol=1e-12)


# 자산 한계 (9/20 L3) ------------------------------------------------------------

def test_asset_limits_are_narrower_than_the_spec_at_the_elbow():
    # Isaac 자산의 elbow 는 ±π 다(ur5.urdf·dof 줄, 9/20 실습12). 나머지는 제원과 같다.
    assert kin.UR5_ASSET_LIMITS[2] == pytest.approx((-math.pi, math.pi))
    for index in (0, 1, 3, 4, 5):
        assert kin.UR5_ASSET_LIMITS[index] == kin.UR5_JOINT_LIMITS[index]
    assert kin.UR5_ASSET_LIMITS[2][1] < kin.UR5_JOINT_LIMITS[2][1]


def test_limits_are_intersected_never_widened():
    # 호출부가 자산보다 넓은 한계를 줘도 넓어지지 않는다(M0609 와 같은 규칙).
    wide = tuple((-10.0, 10.0) for _ in range(6))
    assert kin.intersect_limits(wide) == kin.UR5_ASSET_LIMITS
    assert kin.intersect_limits(kin.UR5_JOINT_LIMITS) == kin.UR5_ASSET_LIMITS
    # 더 좁게 주는 것은 막지 않는다.
    narrow = tuple((-0.5, 0.5) for _ in range(6))
    assert kin.intersect_limits(narrow) == narrow
    # 한쪽만 넓은 경우도 그 쪽만 좁힌다.
    mixed = ((-0.2, 10.0),) + kin.UR5_JOINT_LIMITS[1:]
    assert kin.intersect_limits(mixed)[0] == pytest.approx((-0.2, 2.0 * math.pi))
    # 자산 한계를 모르는 관절은 요청을 그대로 쓴다.
    unknown = (None,) + kin.UR5_ASSET_LIMITS[1:]
    assert kin.intersect_limits(wide, unknown)[0] == (-10.0, 10.0)


def test_elbow_solutions_beyond_the_asset_limit_are_refused():
    # 제원 표로 풀면 (π, 2π] 의 elbow 해가 "합법" 이 된다. 자산 한계에서는 아니다.
    beyond = (0.0, -1.0, math.pi + 0.3, 0.0, 0.0, 0.0)
    assert kin.within_limits(beyond, kin.UR5_JOINT_LIMITS)
    assert not kin.within_limits(beyond, kin.UR5_ASSET_LIMITS)
    clamped = kin.clamp_to_limits(beyond, kin.UR5_ASSET_LIMITS)
    assert clamped[2] == pytest.approx(math.pi)


def test_nearest_wrapped_stays_inside_the_asset_limit():
    # 2π 배수 후보 중 자산 한계 밖은 고르지 않는다. PhysX 가 조용히 자르는 값이라서다.
    joints = (0.0, 0.0, -math.pi + 0.2, 0.0, 0.0, 0.0)
    reference = (0.0, 0.0, math.pi - 0.2, 0.0, 0.0, 0.0)
    wrapped = kin.nearest_wrapped(joints, reference, kin.UR5_ASSET_LIMITS)
    assert kin.within_limits(wrapped, kin.UR5_ASSET_LIMITS)


@pytest.mark.parametrize('yaw', [-2.5, 0.0, 2.5])
def test_suction_ik_keeps_last_joint_and_ignores_qr_yaw(yaw):
    seed = np.array([2.907216, -1.155645, 1.402267, 1.324175, 1.570796, 1.336419])
    wrist = float(seed[-1])
    for height in [0.2, 0.15, 0.1]:
        target = top_down_pose([0.47, 0.0, height], yaw)
        result = kin.solve_suction_ik(target, seed, wrist)
        assert result.ok
        assert result.joints[-1] == wrist
        actual = forward_kinematics(result.joints)
        assert np.linalg.norm(actual[:3, 3] - target[:3, 3]) < 1e-5
        assert np.linalg.norm(actual[:3, 2] - target[:3, 2]) < 1e-5
        seed = result.joints


def test_suction_ik_rejects_unreachable_position():
    target = top_down_pose([10.0, 0.0, 0.1], 0.0)
    seed = np.array([2.907216, -1.155645, 1.402267, 1.324175, 1.570796, 1.336419])
    result = kin.solve_suction_ik(target, seed, float(seed[-1]))
    assert not result.ok
    assert result.joints[-1] == seed[-1]
