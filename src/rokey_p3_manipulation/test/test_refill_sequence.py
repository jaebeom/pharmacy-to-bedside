import math

import pytest

from rokey_p3_manipulation import refill_sequence as seq

POSES = {
    'shelf_approach': [0.1] * 6,
    'shelf_grasp': [0.2] * 6,
    'slot_a_approach': [0.3] * 6,
    'slot_a_insert': [0.4] * 6,
    'slot_b_approach': [0.5] * 6,
    'slot_b_insert': [0.6] * 6,
}


def test_plan_follows_the_contract_order_for_slot_a():
    steps = seq.plan_refill(seq.SLOT_A, POSES)
    assert [step.phase for step in steps] == list(seq.PHASES)
    assert steps[1].gripper == seq.GRIP_CLOSE and steps[1].joints == (0.2,) * 6
    assert steps[4].gripper == seq.GRIP_OPEN and steps[4].joints == (0.4,) * 6
    assert steps[3].joints == steps[5].joints == (0.3,) * 6
    assert [step.gripper for step in steps if step.phase not in ('grasp', 'insert')] == [None] * 4


def test_plan_uses_slot_b_poses_for_slot_b():
    steps = seq.plan_refill(seq.SLOT_B, POSES)
    assert steps[3].joints == (0.5,) * 6
    assert steps[4].joints == (0.6,) * 6


def test_carrying_phases_are_between_grasp_and_release():
    phases = list(seq.PHASES)
    grasp, insert = phases.index('grasp'), phases.index('insert')
    assert all(grasp < phases.index(phase) <= insert for phase in seq.CARRYING_PHASES)


def test_unknown_slot_is_rejected():
    with pytest.raises(seq.RefillPlanError):
        seq.slot_letter(2)
    with pytest.raises(seq.RefillPlanError):
        seq.plan_refill(7, POSES)


def test_missing_or_short_waypoint_is_rejected():
    short = dict(POSES, slot_b_insert=[0.0] * 5)
    with pytest.raises(seq.RefillPlanError):
        seq.plan_refill(seq.SLOT_B, short)
    missing = {key: value for key, value in POSES.items() if key != 'shelf_grasp'}
    with pytest.raises(seq.RefillPlanError):
        seq.plan_refill(seq.SLOT_A, missing)
    with pytest.raises(seq.RefillPlanError):
        seq.check_joints('x', ['a'] * 6)


def test_interpolate_ends_exactly_on_goal_and_respects_step():
    points = seq.interpolate([0.0] * 6, [1.0, 0.0, 0.0, 0.0, 0.0, 0.0], 0.3)
    assert len(points) == math.ceil(1.0 / 0.3)
    assert points[-1] == (1.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    assert all(b[0] - a[0] <= 0.3 + 1e-9 for a, b in zip(points, points[1:], strict=False))
    assert seq.interpolate([0.5] * 6, [0.5] * 6, 0.1) == [(0.5,) * 6]


def test_at_pose_and_clamp():
    assert seq.at_pose([0.0, 0.04], [0.0, 0.0], 0.05)
    assert not seq.at_pose([0.0, 0.06], [0.0, 0.0], 0.05)
    assert not seq.at_pose(None, [0.0], 0.05)
    assert seq.clamp([3.0, -3.0], [(-1.0, 1.0), (-1.0, 1.0)]) == (1.0, -1.0)


# 관절 한계 ------------------------------------------------------------------------

def test_default_limits_follow_the_m0609_asset():
    """sim README(9/17 USD)·마클2 master02 자산: joint_3 ±150°, 나머지 ±360°."""
    limits = seq.M0609_JOINT_LIMITS
    assert limits[2] == pytest.approx((-2.618, 2.618), abs=1e-3)
    assert all(pair == pytest.approx((-6.2832, 6.2832), abs=1e-4) for index, pair in enumerate(limits) if index != 2)


def test_joint_6_teach_values_two_pi_apart_are_all_inside_the_limits():
    """teach 값의 joint_6 은 실행마다 2π 갈린다(마클2). 셋 다 정상 통과해야 한다."""
    for joint_6 in (3.7457, -2.5352, -3.7749):
        assert seq.limit_violation((0.6, 0.2, 1.1, 0.0, 1.8, joint_6), seq.M0609_JOINT_LIMITS) is None


def test_limit_violation_reports_the_first_joint_and_keeps_the_boundary_inside():
    limits = seq.M0609_JOINT_LIMITS
    assert seq.limit_violation((0.0, 0.0, 2.7, 0.0, 0.0, 7.0), limits) == (2, 2.7, limits[2][0], limits[2][1])
    assert seq.limit_violation((0.0, 0.0, limits[2][1], 0.0, 0.0, -limits[5][1]), limits) is None


def test_plan_limit_violation_checks_the_slot_poses_in_order_and_home():
    poses = dict(POSES)
    poses['slot_a_insert'] = [0.4, 0.4, 2.8, 0.4, 0.4, 0.4]
    limits = seq.M0609_JOINT_LIMITS
    assert seq.plan_limit_violation(seq.SLOT_A, poses, [0.0] * 6, limits)[:3] == ('slot_a_insert_joints', 2, 2.8)
    assert seq.plan_limit_violation(seq.SLOT_B, poses, [0.0] * 6, limits) is None          # slot_a 자세는 안 쓴다
    home = [0.0, 0.0, -3.0, 0.0, 0.0, 0.0]
    assert seq.plan_limit_violation(seq.SLOT_B, poses, home, limits)[:3] == ('home_joint_positions', 2, -3.0)

