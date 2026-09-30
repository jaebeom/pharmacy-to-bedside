"""L1. M0609 명목 기구학. ROS·Isaac 없이 돈다.

P2(`ROKEY_P2_B2` `56d8246`)에서 옮긴 코드가 옮기는 과정에서 안 깨졌는지 본다.
기본값이 Isaac 자산과 맞는지는 여기서 못 본다. 그건 마스터 확인이다.
"""
import math

import pytest

from rokey_p3_manipulation import m0609_kinematics as kin

TOOL = kin.ToolTransform((0.0, 0.0, 0.15), (0.0, 0.0, 0.0, 1.0))
HOME = (0.0, 0.0, math.radians(90), 0.0, math.radians(90), 0.0)


def model():
    return kin.M0609(flange_to_tcp=TOOL)


def test_fk_then_ik_returns_the_same_joints():
    # 옮기면서 체인이나 야코비안이 깨졌으면 왕복이 안 닫힌다.
    m = model()
    target = m.fk(HOME)
    seed = tuple(q + math.radians(3) for q in HOME)
    solved = m.inverse(target, seed)
    assert max(abs(a - b) for a, b in zip(solved, HOME, strict=True)) < 1e-6
    assert math.dist(m.fk(solved).position_m, target.position_m) < 1e-6


def test_tcp_offset_moves_the_tip():
    # flange->TCP 가 무시되면 두 모델의 FK 가 같아진다. P3 그리퍼가 P2 와 달라서 중요하다.
    near = kin.M0609(flange_to_tcp=kin.ToolTransform((0.0, 0.0, 0.05), (0.0, 0.0, 0.0, 1.0)))
    far = kin.M0609(flange_to_tcp=kin.ToolTransform((0.0, 0.0, 0.25), (0.0, 0.0, 0.0, 1.0)))
    assert math.dist(near.fk(HOME).position_m, far.fk(HOME).position_m) == pytest.approx(0.20, abs=1e-9)


def test_joint_limits_are_intersected_never_widened():
    # 호출부가 URDF 보다 넓은 한계를 줘도 넓어지지 않는다.
    wide = tuple((-10.0, 10.0) for _ in range(6))
    m = kin.M0609(flange_to_tcp=TOOL, joint_limits_rad=wide)
    assert m.joint_limits_rad == kin.URDF_LIMITS_RAD
    with pytest.raises(kin.PlanError):
        m.check_limits((0.0, 0.0, math.radians(200), 0.0, 0.0, 0.0))


def test_ik_refuses_an_unreachable_target():
    # 도달 못 하는 목표에 0 이나 아무 값이나 돌려주면 안 된다.
    m = model()
    with pytest.raises(kin.PlanError):
        m.inverse(kin.Pose((5.0, 0.0, 0.0), (0.0, 0.0, 0.0, 1.0)), HOME)


def test_j5_singular_crossing_is_refused():
    # 손목 특이점을 건너뛰는 두 끝점은 각각은 멀쩡해도 사이가 위험하다.
    start = (0.0, 0.0, 0.0, 0.0, math.radians(-2), 0.0)
    end = (0.0, 0.0, 0.0, 0.0, math.radians(2), 0.0)
    with pytest.raises(kin.PlanError):
        kin.check_joint_segment(start, end)
    kin.check_joint_segment(start, (0.0, 0.0, 0.0, 0.0, math.radians(-6), 0.0))


def test_non_finite_input_is_refused():
    m = model()
    with pytest.raises(kin.PlanError):
        m.fk((0.0, 0.0, float('nan'), 0.0, 0.0, 0.0))
    with pytest.raises(kin.PlanError):
        kin.Pose((0.0, 0.0, float('inf')), (0.0, 0.0, 0.0, 1.0))


def test_module_imports_no_ros():
    # 계약 안내의 뼈대 규칙: 순수 모듈은 ROS 없이 테스트된다.
    source = (kin.__file__ or '')
    assert source.endswith('m0609_kinematics.py')
    with open(source, encoding='utf-8') as handle:
        text = handle.read()
    for forbidden in ('import rclpy', 'from rclpy', 'import isaacsim', 'from isaacsim'):
        assert forbidden not in text
