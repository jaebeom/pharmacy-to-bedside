"""`arm_base_frame_convention` — 기준 프레임 축과 DH 기준축의 관계(실습27b).

실습27b S2 에서 팔이 봉투에서 **1.25 m** 떨어진 곳을 집으려 했다. 원인은 IK 도 DH 도 아니고,
`amr_1/ur_arm_base_link`(UR URDF 의 `base_link`)와 표준 UR5 DH 표의 기준(`base`)이
z 축으로 180° 돌아 있는데 **아무도 그 관계를 적어 두지 않은 것**이었다.

아래 수치는 master02 실습27b 의 관측값이다. 값을 고쳐서 시험을 통과시키지 않는다.
"""

import math

import numpy as np
import pytest
import test_reset_fence as rf

nodes = rf.nodes

# 실습27b 관측(master02, `f6308b9`). 전부 `amr_1/ur_arm_base_link` 기준이다.
HOME = (-1.6901, 1.1323, -2.1219, -0.5817, -1.5706, 3.0222)
HOME_FLANGE = (0.050, -0.500, -0.050)     # tf 로 잰 홈 자세의 flange
POUCH = (-0.4445, 0.4426, -0.1450)        # S1 검출
MISS_M = 1.2537                           # 스테이지 `ur5 suction miss … nearest`


def test_base_convention_keeps_the_default_behaviour(nodes):
    """기본값 `base` 는 항등이다 — 기존 경로(시연·스텁)가 한 톨도 바뀌지 않는다."""
    arm, _ = nodes
    assert np.array_equal(arm.base_to_kinematic('base'), np.eye(4))


def test_unknown_convention_is_refused(nodes):
    """오타가 조용히 `base` 로 떨어지면 안 된다 — 증상이 1.25 m 빗나감이라 못 알아본다."""
    arm, _ = nodes
    with pytest.raises(KeyError):
        arm.base_to_kinematic('base_frame')


def test_plain_forward_kinematics_disagrees_with_the_measured_flange(nodes):
    """보정 없이 풀면 x·y 부호가 뒤집힌다. **이것이 27b 에서 실제로 일어난 일이다.**"""
    arm, _ = nodes
    raw = arm.kin.forward_kinematics(np.array(HOME))[:3, 3]
    assert np.allclose(raw, (-HOME_FLANGE[0], -HOME_FLANGE[1], HOME_FLANGE[2]), atol=1e-3)
    assert not np.allclose(raw, HOME_FLANGE, atol=1e-2)


def test_base_link_convention_matches_the_measured_flange(nodes):
    """`base_link` 보정을 넣으면 FK 가 실측 flange 와 맞는다(1 mm 안)."""
    arm, _ = nodes
    correction = arm.base_to_kinematic('base_link')
    tcp = correction[:3, :3] @ arm.kin.forward_kinematics(np.array(HOME))[:3, 3]
    assert np.allclose(tcp, HOME_FLANGE, atol=1e-3)


def test_uncorrected_target_lands_where_the_stage_measured_the_miss(nodes):
    """보정 없이 푼 해가 실제로 가는 자리가 스테이지가 잰 빗나감과 같다.

    이 시험이 원인 규명 자체다 — 다른 원인(DH 불일치·TF 지연·검출 오류)으로는
    **하필 x·y 가 뒤집힌 1.25 m** 가 나오지 않는다.
    """
    arm, _ = nodes
    kin = arm.kin
    yaw = 2.0 * math.atan2(-0.04579, 0.99895)
    target = kin.top_down_pose(np.array(POUCH), yaw)
    result = kin.solve_ik(target, np.array(HOME), home=np.array(HOME),
                          limits=kin.intersect_limits(kin.UR5_JOINT_LIMITS))
    assert result.ok
    actual = arm.base_to_kinematic('base_link')[:3, :3] @ kin.forward_kinematics(result.joints)[:3, 3]
    assert abs(float(np.linalg.norm(actual - np.array(POUCH))) - MISS_M) < 0.02


def test_corrected_target_reaches_the_pouch(nodes):
    """보정을 넣고 풀면 흡착 한계(0.04 m) 안으로 들어간다."""
    arm, _ = nodes
    kin = arm.kin
    correction = arm.base_to_kinematic('base_link')
    yaw = 2.0 * math.atan2(-0.04579, 0.99895)
    target = kin.top_down_pose(np.array(POUCH), yaw)
    result = kin.solve_ik(correction @ target, np.array(HOME), home=np.array(HOME),
                          limits=kin.intersect_limits(kin.UR5_JOINT_LIMITS))
    assert result.ok
    assert kin.within_limits(result.joints, kin.intersect_limits(kin.UR5_JOINT_LIMITS))
    actual = correction[:3, :3] @ kin.forward_kinematics(result.joints)[:3, 3]
    assert float(np.linalg.norm(actual - np.array(POUCH))) < 0.04


# 기동 자가 확인 (작전 지시: 값을 말로 맞추지 않는다) --------------------------
# 27b(받침대)·lap4(AMR 합본) 둘 다 ⑤ 가 프레임 180° 로 끊겼다. 세 번째를 안 쓰려고
# 팔이 기동 때 자기 FK 와 TF 를 대조해 스스로 고른다.

LAP4_FK = (0.7081, -0.0486, 0.4188)        # 보정 없이 푼 FK 위치
LAP4_TF_SAME = (0.7081, -0.0486, 0.4188)   # TF 가 같은 쪽 → convention=base
LAP4_TF_FLIPPED = (-0.7081, 0.0486, 0.4188)


def test_check_picks_base_when_tf_agrees_with_raw_fk(nodes):
    """AMR 합본: 스테이지가 내는 프레임에 Rz(pi) 가 이미 들어 있다 → 보정하지 않는다."""
    arm, _ = nodes
    got, text = arm.matching_convention(LAP4_FK, LAP4_TF_SAME)
    assert got == 'base', text


def test_check_picks_base_link_when_tf_is_flipped(nodes):
    """받침대 UR5: 프레임이 회전 0 이라 DH 기준으로 가려면 pi 를 돌려야 한다."""
    arm, _ = nodes
    got, text = arm.matching_convention(LAP4_FK, LAP4_TF_FLIPPED)
    assert got == 'base_link', text


def test_check_refuses_when_neither_fits(nodes):
    """둘 다 안 맞으면 고르지 않는다 — 프레임 이름·DH·자산이 틀린 것이라 거부해야 한다."""
    arm, _ = nodes
    got, _text = arm.matching_convention(LAP4_FK, (0.1, 0.2, 1.9))
    assert got is None


def test_check_refuses_when_both_look_close(nodes):
    """목표가 회전축 근처면 두 관례가 안 갈린다 — 그때도 고르지 않는다."""
    arm, _ = nodes
    got, _text = arm.matching_convention((0.01, 0.0, 0.4), (0.01, 0.0, 0.4))
    assert got is None


def test_wrist_link_frame_follows_the_asset_joint_names(nodes):
    """자산마다 접두가 다르다. `joint_names` 에서 파생해 따로 맞출 값을 늘리지 않는다."""
    arm, _ = nodes
    assert arm.wrist_link_frame('amr_1', list(arm.kin.UR5_JOINT_NAMES)) == 'amr_1/wrist_3_link'
    combined = ['ur_arm_shoulder_pan_joint', 'ur_arm_shoulder_lift_joint', 'ur_arm_elbow_joint',
                'ur_arm_wrist_1_joint', 'ur_arm_wrist_2_joint', 'ur_arm_wrist_3_joint']
    assert arm.wrist_link_frame('amr_1', combined) == 'amr_1/ur_arm_wrist_3_link'
