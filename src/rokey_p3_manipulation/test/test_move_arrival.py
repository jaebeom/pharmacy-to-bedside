"""이동 도달 확인 — 움직임 실패를 흡착 실패로 보고하지 않는다(실습29b).

29b 에서 팔이 조제실 벽에 막혀 경로의 45% 지점(`shoulder_pan −2.7577`)에 섰다. 그런데
`move_to` 가 개루프라 궤적점을 다 내보낸 뒤 **도달을 보지 않고 성공**을 돌려줬고, 노드는
흡착을 켜고 `grasp_failed (holding=false)` 로 닫았다. **움직임 실패가 흡착 실패로 보고되어**
원인 규명이 두 시간 동안 엉뚱한 곳(흡착·검출)을 봤다.

`outcome` 은 계약 2.3절의 일곱 개 밖으로 나가지 않는다 — `timeout` 을 쓴다.
"""

import numpy as np
import test_reset_fence as rf

nodes = rf.nodes

NAMES = ('shoulder_pan_joint', 'shoulder_lift_joint', 'elbow_joint',
         'wrist_1_joint', 'wrist_2_joint', 'wrist_3_joint')
# 실습29b: 홈, 팔이 실제로 선 자세, 그리고 명령한 목표.
HOME = (-1.6901, 1.1323, -2.1219, -0.5817, -1.5706, 3.0222)
STUCK = (-2.7577, 1.0480, -1.9758, -0.6488, -1.5725, 1.8312)
GOAL = (-4.0725, 1.0732, -1.6891, -0.9549, -1.5708, 0.7043)


def test_arrival_problem_is_none_when_every_joint_is_inside(nodes):
    arm, _ = nodes
    near = tuple(v + 0.04 for v in GOAL)
    assert arm.arrival_problem(NAMES, GOAL, near, 0.05) is None


def test_arrival_problem_names_the_worst_joint(nodes):
    """29b 를 그대로 넣으면 `shoulder_pan` 이 1.31 rad 남았다고 말해야 한다."""
    arm, _ = nodes
    problem = arm.arrival_problem(NAMES, GOAL, STUCK, 0.05)
    assert problem is not None
    assert 'shoulder_pan_joint' in problem
    assert '1.3148' in problem          # |-4.0725 - (-2.7577)|


def test_arrival_problem_ignores_a_smaller_gap_on_another_joint(nodes):
    """제일 많이 남은 관절을 고른다 — 여러 개가 남았을 때 한 줄로 갈려야 한다."""
    arm, _ = nodes
    actual = list(GOAL)
    actual[1] += 0.30
    actual[5] -= 0.90
    problem = arm.arrival_problem(NAMES, GOAL, actual, 0.05)
    assert 'wrist_3_joint' in problem


def test_home_would_not_have_been_flagged(nodes):
    """홈에 실제로 가 있으면 문제가 없다고 해야 한다 — 거짓 경보가 나면 못 쓴다."""
    arm, _ = nodes
    assert arm.arrival_problem(NAMES, HOME, HOME, 0.05) is None


def test_move_result_is_falsy_but_carries_the_reason(nodes):
    """거짓으로만 쓰던 호출부(`move_home`·`run_scan_tag`)가 그대로 돌아야 한다."""
    arm, _ = nodes
    assert bool(arm.MoveResult(True)) is True
    failed = arm.MoveResult(False, arm.perm.OUTCOME_TIMEOUT, '이동 미도달: x')
    assert not failed
    assert failed.outcome == arm.perm.OUTCOME_TIMEOUT


def test_arrival_failure_uses_a_contract_outcome(nodes):
    """새 outcome 을 만들지 않는다 — 계약 2.3절의 일곱 개 안이어야 한다(.action 은 재범 소유)."""
    arm, _ = nodes
    allowed = {arm.perm.OUTCOME_OK, arm.perm.OUTCOME_NOT_DETECTED, arm.perm.OUTCOME_QR_MISMATCH,
               arm.perm.OUTCOME_GRASP_FAILED, arm.perm.OUTCOME_DROPPED, arm.perm.OUTCOME_TIMEOUT,
               arm.perm.OUTCOME_REJECTED_INTERLOCK}
    assert arm.perm.OUTCOME_TIMEOUT in allowed
    assert arm.MoveResult(False, arm.perm.OUTCOME_TIMEOUT, 'x').outcome in allowed


def test_ik_failure_keeps_the_old_outcome(nodes):
    """도달 확인이 아닌 기존 실패(IK·취소)는 예전처럼 호출부가 정한다 — 동작이 안 바뀐다."""
    arm, _ = nodes
    plain = arm.MoveResult(False)
    assert plain.outcome is None
    assert (plain.outcome or arm.perm.OUTCOME_GRASP_FAILED) == arm.perm.OUTCOME_GRASP_FAILED


def test_straight_joint_path_from_home_to_goal_leaves_the_endpoints_clear(nodes):
    """29b 의 기하: 양 끝은 벽 밖인데 사이가 벽 안이다.

    이 시험은 `move_to` 가 **경로를 검사하지 않는다**는 사실을 못 박는다. 도달 확인은
    그 사실을 없애 주지 않는다 — 막힌 것을 늦지 않게 **알려 줄** 뿐이다.
    """
    arm, _ = nodes
    kin = arm.kin
    base = np.array([3.25, 0.55, 0.90])
    rot = kin.rotation_z(np.pi)                      # arm_base_frame_convention: base_link
    wall_inner_x = 2.75                              # wall_x 2.7, 두께 0.10

    def min_x(joints):
        return min((base + rot @ frame[:3, 3])[0] for frame in kin.link_frames(np.array(joints)))

    assert min_x(HOME) > wall_inner_x
    assert min_x(GOAL) > wall_inner_x
    midpoint = [(a + b) / 2.0 for a, b in zip(HOME, GOAL, strict=True)]
    assert min_x(midpoint) < wall_inner_x            # 사이가 벽 안이다


# 경유 자세 (lap3: 위팔이 제 상판 3번 칸 벽까지 0.010 m) ------------------------

LAP3_HOME = (-0.000353, -1.288208, 1.319242, -0.000031, 1.570801, 0.0)
LAP3_VIA = (0.0, -2.0, 0.6, -1.7, 1.5708, 0.0)
LAP3_POUCH = (0.7030, -0.0485, 0.4188)     # 검출, ur_arm_base_link 기준


def test_via_is_off_by_default(nodes):
    """기본은 끔 = 지금 동작(직선 한 구간). 켜지 않은 경로는 한 톨도 안 바뀐다."""
    arm, _ = nodes
    node = type('Via', (), {'move_via': arm.ArmNode.move_via})()
    node._via = None
    assert node.move_via() .ok is True


def test_via_steers_ik_to_the_branch_whose_path_is_clear(nodes):
    """lap3 은 가지가 문제였다 — 경유 자세가 씨앗이 되어 어느 가지로 풀릴지를 바꾼다.

    `solve_ik` 는 **현재 자세에 가장 가까운** 해를 고른다(규칙 3·4). 노드는 pan −3.04 가지로
    풀어 위팔이 상판을 쓸었고, 홈/경유에서 풀면 pan +0.09 가지가 나온다.
    """
    arm, _ = nodes
    kin = arm.kin
    limits = kin.intersect_limits(kin.UR5_JOINT_LIMITS)
    target = kin.top_down_pose(np.array(LAP3_POUCH), 0.0)
    from_via = kin.solve_ik(target, np.array(LAP3_VIA), home=np.array(LAP3_HOME), limits=limits)
    assert from_via.ok
    assert abs(from_via.joints[0] - 0.0866) < 0.01          # 경로가 비는 가지
    # 실제로 lap3 에서 나온 가지(pan ≈ −3.04)는 이것과 π 만큼 다르다.
    assert abs(abs(from_via.joints[0] - (-3.0421)) - np.pi) < 0.02
