"""L1: 벨트 통로 이탈 판정(순수). 기대 거리는 같은 FK 로 계산한 점에서 만든다. DH 가 USD 와 맞는지는 L3 다.

여기서 쓰는 통로 상자·반지름·공구 길이는 **시험용 기하**다. 실제 값이 아니다(미측정, SIM-2 D-S3).
"""

import math

import numpy as np
import pytest

from rokey_p3_manipulation import belt_lane_clearance as lane
from rokey_p3_manipulation import ur5_kinematics as kin

ZERO = (0.0,) * 6
POSE = (0.3, -1.2, 1.4, -1.6, -1.57, 0.2)
LIMITS = kin.UR5_JOINT_LIMITS
R = 0.05              # 시험용 반지름(모든 선분 같게)
TOOL = 0.10           # 시험용 공구 길이
FAR = 100.0


def config(**overrides):
    base = lane.LaneConfig(base_from_lane=np.eye(4), lower=(FAR, FAR, FAR), upper=(FAR + 1, FAR + 1, FAR + 1),
                           link_radii=(R,) * 6, tool_length=TOOL, tool_radius=R,
                           payload_size=(0.10, 0.07, 0.01), payload_center=(0.0, 0.0, 0.005))
    return base._replace(**overrides)


def judge(joints=ZERO, cfg=None, holding=False, age=0.1, max_age=1.0, limits=LIMITS):
    return lane.judge(joints, age, max_age, limits, config() if cfg is None else cfg, holding)


def points(joints, holding=False, cfg=None):
    """판정 대상 선분 끝점들(팔 베이스 프레임). 같은 FK·같은 공구 규칙."""
    cfg = config() if cfg is None else cfg
    frames = kin.link_frames(joints)
    flange = frames[-1]
    tcp = flange[:3, 3] + flange[:3, 2] * cfg.tool_length
    return [frame[:3, 3] for frame in frames] + [tcp], flange, tcp


# UNKNOWN -------------------------------------------------------------------------

@pytest.mark.parametrize('field', ['base_from_lane', 'lower', 'upper', 'link_radii', 'tool_length', 'tool_radius'])
def test_any_unset_geometry_is_unknown(field):
    result = judge(cfg=config(**{field: None}))
    assert result.state == lane.UNKNOWN and result.reason


@pytest.mark.parametrize('overrides', [
    {'lower': (0, 0, 1), 'upper': (1, 1, 1)},           # 빈 상자
    {'link_radii': (R,) * 5},                           # 개수
    {'link_radii': (R, R, R, R, R, 0.0)},               # 0 반지름은 미설정
    {'tool_radius': 0.0},
    {'tool_length': -0.01},
    {'base_from_lane': np.eye(3)},
    {'base_from_lane': np.full((4, 4), np.nan)},
    {'lower': (0.0, 0.0, math.inf)},
])
def test_invalid_geometry_is_unknown(overrides):
    assert judge(cfg=config(**overrides)).state == lane.UNKNOWN


def test_holding_needs_payload_geometry_but_empty_hand_does_not():
    for missing in ({'payload_size': None}, {'payload_center': None}, {'payload_size': (0.1, 0.0, 0.01)}):
        assert judge(cfg=config(**missing), holding=True).state == lane.UNKNOWN
        assert judge(cfg=config(**missing), holding=False).state == lane.CLEAR


def test_unknown_holding_is_never_clear():
    # 파지 여부를 모르면 파지물을 모른다. 링크·공구가 닿지 않아도 CLEAR 를 내지 않는다.
    result = judge(holding=None)
    assert result.state == lane.UNKNOWN and result.reason.startswith('파지 여부를 모른다')
    assert result.distance > 1.0                                      # 링크·공구 여유는 남긴다


def test_unknown_holding_with_links_inside_is_intruding():
    # 링크·공구가 이미 닿으면 파지물을 몰라도 INTRUDING 이다(파지물은 침범만 더한다).
    _pts, flange, _tcp = points(POSE)
    center = flange[:3, 3]
    inside = config(lower=tuple(center - 0.01), upper=tuple(center + 0.01), payload_size=None, payload_center=None)
    assert judge(joints=POSE, cfg=inside, holding=None).state == lane.INTRUDING


@pytest.mark.parametrize('joints, age, max_age', [
    (None, 0.1, 1.0),
    ((0.0,) * 5, 0.1, 1.0),
    ((0.0, 0.0, 0.0, 0.0, 0.0, math.nan), 0.1, 1.0),
    (ZERO, 1.5, 1.0),                                   # 오래됐다
    (ZERO, None, 1.0),                                  # age 모름
    (ZERO, -0.1, 1.0),
    (ZERO, 0.1, 0.0),                                   # 기준 미설정
])
def test_missing_or_stale_joints_are_unknown(joints, age, max_age):
    assert judge(joints=joints, age=age, max_age=max_age).state == lane.UNKNOWN


def test_joints_outside_limits_are_unknown():
    tight = tuple((-0.1, 0.1) for _ in range(6))
    assert judge(joints=POSE, limits=tight).state == lane.UNKNOWN
    assert judge(joints=POSE, limits=None).state == lane.UNKNOWN


def test_fresh_joints_at_the_age_limit_are_used():
    assert judge(age=1.0, max_age=1.0).state == lane.CLEAR


# CLEAR / INTRUDING -----------------------------------------------------------------

def test_far_lane_is_clear_with_a_positive_margin():
    result = judge(joints=POSE)
    assert result.state == lane.CLEAR and result.distance > 1.0


def test_lane_around_the_flange_is_intruding():
    _pts, flange, _tcp = points(POSE)
    center = flange[:3, 3]
    result = judge(joints=POSE, cfg=config(lower=tuple(center - 0.01), upper=tuple(center + 0.01)))
    assert result.state == lane.INTRUDING
    assert result.distance <= 0.0


@pytest.mark.parametrize('joints', [ZERO, POSE])
def test_boundary_contact_is_intruding_and_just_outside_is_clear(joints):
    # 모든 부분 아래에 넓은 상자를 둔다. 가장 낮은 끝점에서 반지름만큼 떨어진 윗면은 닿음이다.
    pts, _flange, _tcp = points(joints)
    low_z = min(p[2] for p in pts)
    touching = config(lower=(-FAR, -FAR, -FAR), upper=(FAR, FAR, low_z - R))
    outside = config(lower=(-FAR, -FAR, -FAR), upper=(FAR, FAR, low_z - R - 1e-4))
    assert judge(joints=joints, cfg=touching).state == lane.INTRUDING
    result = judge(joints=joints, cfg=outside)
    assert result.state == lane.CLEAR and result.distance == pytest.approx(1e-4, abs=1e-7)


def test_payload_is_checked_only_while_holding():
    # 빈손이면 닿지 않고, 파지물(TCP 에 붙은 상자)만 상자에 들어가는 배치.
    pts, _flange, tcp = points(POSE)
    cfg0 = config(payload_center=(0.0, 0.0, 0.30), payload_size=(0.02, 0.02, 0.02))
    frames = kin.link_frames(POSE)
    tcp_pose = frames[-1].copy()
    tcp_pose[:3, 3] = tcp
    payload = (tcp_pose @ np.array([0.0, 0.0, 0.30, 1.0]))[:3]
    cfg = cfg0._replace(lower=tuple(payload - 0.005), upper=tuple(payload + 0.005))
    assert min(np.linalg.norm(p - payload) for p in pts) > R + 0.05       # 선분 끝점은 멀다(시험 배치 확인)
    empty = judge(joints=POSE, cfg=cfg, holding=False)
    assert empty.state == lane.CLEAR
    held = judge(joints=POSE, cfg=cfg, holding=True)
    assert held.state == lane.INTRUDING and held.part == 'payload'


def test_lane_frame_transform_is_applied():
    # 같은 상자를 베이스 프레임에 바로 두든, 회전·이동한 통로 프레임에 두든 판정이 같다.
    _pts, flange, _tcp = points(POSE)
    center = flange[:3, 3]
    base_from_lane = kin.matrix_from_quaternion(0.0, 0.0, math.sin(0.35), math.cos(0.35), (0.4, -0.2, 0.1))
    center_lane = (kin.invert(base_from_lane) @ np.append(center, 1.0))[:3]
    inside = config(base_from_lane=base_from_lane, lower=tuple(center_lane - 0.01), upper=tuple(center_lane + 0.01))
    assert judge(joints=POSE, cfg=inside).state == lane.INTRUDING
    # 통로 프레임을 무시하면(단위행렬) 같은 좌표의 상자는 다른 곳이라 닿지 않는다.
    ignored = inside._replace(base_from_lane=np.eye(4))
    assert judge(joints=POSE, cfg=ignored).state == lane.CLEAR


def test_reported_part_names_cover_links_tool_and_payload():
    # 어디가 가장 가까운지 이름으로 남긴다(링크 6개, tool, payload).
    names = {part for part, *_rest in lane._parts(POSE, config(), True, kin.UR5_DH)}
    assert names == {'link_1', 'link_2', 'link_3', 'link_4', 'link_5', 'link_6', 'tool', 'payload'}
