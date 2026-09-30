"""UR5 팔·파지물이 벨트 통로 상자 밖에 있는가(`arm_clear_of_belt` 의 판정). ROS 를 import 하지 않는다.

계약 v1 11.3·11.6절(제안·미확정): 다음 배출 허가의 조건 하나가 `arm_clear_of_belt=CLEAR` 다.
arm 이 실측 관절 FK + 링크·파지물 vs 통로 상자로 판정하고, 상자 치수는 simulation 이 준다.
이 모듈은 판정만 한다. 노드 연결·토픽 발행은 새 메시지 타입이 생긴 뒤 별도 PR 에서 한다.

**L3 에서 FK↔TCP 대조 전에는 CLEAR 를 다음 배출 허가의 근거로 쓰지 않는다.**
FK 는 `ur5_kinematics.UR5_DH`(UR 공개 표준 DH)다. 시뮬 자산(USD)과 일치하는지 검증되지 않았다.

판정은 셋 중 하나다.
- `UNKNOWN`: 판정에 필요한 것이 하나라도 없다. 통로 상자, 링크 반지름, 공구 길이·반지름이 미설정인 경우다.
  파지 중인데 파지물 크기·위치가 미설정인 경우도 여기다.
  파지 여부를 모르면 링크·공구만 본다. 거기서 이미 닿으면 INTRUDING(파지물은 침범만 더한다), 아니면 UNKNOWN 이다.
  파지물을 모르는 채로 CLEAR 를 내지 않는다.
  관절값이 없거나, 오래됐거나(호출자가 넘기는 age), 개수가 틀리거나, 유한하지 않거나, 한계 밖인 경우도 UNKNOWN 이다.
  **기본값을 지어내지 않는다.** 미설정은 None 이다.
- `INTRUDING`: 어느 부분이든 통로 상자와 겹치거나 경계에 닿는다(경계는 fail-closed).
- `CLEAR`: 모든 부분이 상자 밖에 있고 거리가 0 보다 크다.

기하 근사(보수적이어야 하며 L3 에서 확인한다):
- 링크: DH 프레임 원점을 차례로 이은 선분 6개 + 반지름(`link_radii`, 6개). UR 의 DH 원점은 실제 링크 축과 옆으로
  어긋나 있다(어깨·팔꿈치 오프셋). 그래서 반지름에 그 오프셋까지 들어가야 한다.
- 공구: 플랜지(DH 끝)에서 공구 z 로 `tool_length` 만큼 뻗은 선분 + `tool_radius`. 그 끝이 TCP 다.
- 파지물: TCP 프레임에 붙은 상자(`payload_center` 중심, `payload_size` 크기, 축은 TCP 축).
- 통로 상자: 통로 프레임에서 축 정렬 상자 `[lower, upper]`. 통로 프레임은 SIM-2 초안의 벨트 좌표계다
  (x = 벨트 진행 방향 along, y = lateral, z = up). `base_from_lane` 은 팔 베이스 프레임에서 본 그 프레임의 4x4 다.
거리 계산은 `clearance.obb_box_distance`(M0609 여유 거리와 같은 함수)를 쓴다.
"""

import math
from collections import namedtuple

import numpy as np

from rokey_p3_manipulation import clearance
from rokey_p3_manipulation import ur5_kinematics as kin

UNKNOWN = 'UNKNOWN'
CLEAR = 'CLEAR'
INTRUDING = 'INTRUDING'

#: 이 거리(m) 이하로 가까우면 닿은 것으로 본다. 수치 오차 흡수용이다. 여유값이 아니다(여유는 상자에 넣는다).
CONTACT_EPSILON_M = 1e-9

LaneConfig = namedtuple('LaneConfig', (
    'base_from_lane',   # 4x4, 팔 베이스 프레임에서 본 통로 프레임
    'lower',            # 통로 프레임의 (along, lateral, up) 하한, m
    'upper',            # 상한, m
    'link_radii',       # DH 선분 6개의 반지름, m
    'tool_length',      # 플랜지 → TCP 거리(공구 z), m. 0 도 명시값이다
    'tool_radius',      # 공구 선분 반지름, m
    'payload_size',     # 파지물 상자 크기(TCP 축), m. 파지 중일 때만 필요
    'payload_center',   # 파지물 상자 중심(TCP 프레임), m. 파지 중일 때만 필요
), defaults=(None,) * 8)

Judgement = namedtuple('Judgement', ('state', 'reason', 'part', 'distance'))


def config_problem(config, holding):
    """판정에 쓸 수 없는 설정이면 이유 문자열, 쓸 수 있으면 ''."""
    if config is None:
        return '설정이 없다'
    if config.base_from_lane is None:
        return 'base_from_lane(4x4) 미설정'
    try:
        lane = np.asarray(config.base_from_lane, dtype=float)
    except (TypeError, ValueError):
        return 'base_from_lane 이 행렬이 아니다'
    if lane.shape != (4, 4) or not np.all(np.isfinite(lane)):
        return 'base_from_lane 이 유한한 4x4 가 아니다'
    lower, upper = _vector(config.lower, 3), _vector(config.upper, 3)
    if lower is None or upper is None:
        return '통로 상자 lower·upper(3개씩) 미설정'
    if not np.all(lower < upper):
        return f'통로 상자가 비었다(lower {lower.tolist()} ≥ upper {upper.tolist()})'
    radii = _vector(config.link_radii, 6)
    if radii is None or not np.all(radii > 0.0):
        return 'link_radii(6개, 양수) 미설정'
    if not _nonnegative(config.tool_length):
        return 'tool_length 미설정'
    if not _positive(config.tool_radius):
        return 'tool_radius 미설정'
    if holding:
        size = _vector(config.payload_size, 3)
        if size is None or not np.all(size > 0.0):
            return '파지 중인데 payload_size 미설정'
        if _vector(config.payload_center, 3) is None:
            return '파지 중인데 payload_center 미설정'
    return ''


def joints_problem(joints, age_s, max_age_s, limits):
    """관절값을 판정에 쓸 수 없으면 이유 문자열, 쓸 수 있으면 ''. age 는 호출자가 잰 수신 뒤 경과(s)다."""
    if joints is None:
        return '관절값 없음'
    values = _vector(joints, 6)
    if values is None:
        return '관절값이 6개가 아니거나 유한하지 않다'
    if age_s is None or max_age_s is None or not math.isfinite(age_s) or age_s < 0.0 or max_age_s <= 0.0:
        return '관절값 age 를 모른다'
    if age_s > max_age_s:
        return f'관절값이 오래됐다({age_s:.3f} s > {max_age_s:.3f} s)'
    if limits is None or len(limits) != 6:
        return '관절 한계 미설정'
    if not kin.within_limits(values, limits):
        return '관절값이 한계 밖이다'
    return ''


def judge(joints, age_s, max_age_s, limits, config, holding, dh=kin.UR5_DH):
    """관절값 → Judgement(state, reason, part, distance). distance 는 가장 가까운 부분의 여유(m)다.

    holding: True(파지 중) / False(빈손) / None(모름 → 링크·공구만 보고, 닿지 않으면 UNKNOWN).
    """
    problem = config_problem(config, bool(holding)) or joints_problem(joints, age_s, max_age_s, limits)
    if problem:
        return Judgement(UNKNOWN, problem, '', None)

    lane_box = _lane_box(config)
    lane_from_base = kin.invert(np.asarray(config.base_from_lane, dtype=float))
    worst_part, worst = '', math.inf
    for part, center, axes, half, radius in _parts(joints, config, holding, dh):
        center_l = (lane_from_base @ np.append(center, 1.0))[:3]
        axes_l = [lane_from_base[:3, :3] @ axis for axis in axes]
        distance, _point = clearance.obb_box_distance(tuple(center_l), [tuple(a) for a in axes_l], tuple(half),
                                                      lane_box)
        margin = distance - radius
        if margin < worst:
            worst_part, worst = part, margin
    if worst <= CONTACT_EPSILON_M:
        return Judgement(INTRUDING, f'{worst_part} 가 통로 상자에 닿는다', worst_part, worst)
    if holding is None:
        return Judgement(UNKNOWN, '파지 여부를 모른다. 링크·공구는 닿지 않지만 파지물을 모르면 CLEAR 가 아니다',
                         worst_part, worst)
    return Judgement(CLEAR, '', worst_part, worst)


def _parts(joints, config, holding, dh):
    """판정할 부분들: (이름, 중심, 단위 축 셋, 반길이 셋, 반지름). 선분은 반길이 (L/2, 0, 0) 상자다."""
    frames = kin.link_frames(joints, dh)
    parts = []
    for index, radius in enumerate(np.asarray(config.link_radii, dtype=float)):
        parts.append(_segment(f'link_{index + 1}', frames[index][:3, 3], frames[index + 1][:3, 3], radius))
    flange = frames[-1]
    tcp = flange.copy()
    tcp[:3, 3] = flange[:3, 3] + flange[:3, 2] * float(config.tool_length)
    parts.append(_segment('tool', flange[:3, 3], tcp[:3, 3], float(config.tool_radius)))
    if holding is True:
        center = (tcp @ np.append(np.asarray(config.payload_center, dtype=float), 1.0))[:3]
        axes = [tcp[:3, 0], tcp[:3, 1], tcp[:3, 2]]
        half = np.asarray(config.payload_size, dtype=float) / 2.0
        parts.append(('payload', center, axes, half, 0.0))
    return parts


def _segment(name, start, end, radius):
    start, end = np.asarray(start, dtype=float), np.asarray(end, dtype=float)
    vector = end - start
    length = float(np.linalg.norm(vector))
    axis = vector / length if length > 1e-12 else np.array([1.0, 0.0, 0.0])
    others = _perpendicular(axis)
    return (name, (start + end) / 2.0, [axis, *others], (length / 2.0, 0.0, 0.0), float(radius))


def _perpendicular(axis):
    helper = np.array([0.0, 0.0, 1.0]) if abs(axis[2]) < 0.9 else np.array([1.0, 0.0, 0.0])
    first = np.cross(axis, helper)
    first /= np.linalg.norm(first)
    return [first, np.cross(axis, first)]


def _lane_box(config):
    lower, upper = _vector(config.lower, 3), _vector(config.upper, 3)
    return clearance.Box('belt_lane', tuple((lower + upper) / 2.0), tuple(upper - lower))


def _vector(values, count):
    if values is None:
        return None
    try:
        array = np.asarray(values, dtype=float).reshape(-1)
    except (TypeError, ValueError):
        return None
    if array.size != count or not np.all(np.isfinite(array)):
        return None
    return array


def _positive(value):
    return value is not None and math.isfinite(float(value)) and float(value) > 0.0


def _nonnegative(value):
    return value is not None and math.isfinite(float(value)) and float(value) >= 0.0
