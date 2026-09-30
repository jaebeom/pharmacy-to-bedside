"""M0609 보충 동작의 순수 로직. ROS·numpy 없이 돈다.

계약 [배송 한 바퀴 v1](../../../docs/architecture/delivery-contract-v1.md) 2.3절 `/m0609/refill`:
`pharmacy/shelf` 의 캐니스터를 `pharmacy/dispenser_slot_a` 또는 `_b` 에 장착한다.

v0 는 레일 없는 고정 스테이지에서 관절 공간 waypoint 를 그대로 잇는다.
`m0609_arm` 은 실행 중 FK·IK 솔버를 호출하지 않는다. waypoint 6개는 노드 파라미터이고
**마스터에서 티칭**한다. Isaac `selfdemo` 는 현장 URDF·robot description 으로 Lula IK 를
사용해 teach 후보를 만들지만, 이 ROS 실행 경로와는 분리되어 있다.
"""

import math
from collections import namedtuple

#: `DispenserSlot.SLOT_A` / `SLOT_B`. 인터페이스 상수와 같은 값이다.
SLOT_A = 0
SLOT_B = 1
DOF = 6

GRIP_CLOSE = 'close'
GRIP_OPEN = 'open'

#: 실행 순서. 이름은 `Refill` feedback.phase 로 나간다.
PHASES = ('to_shelf', 'grasp', 'lift', 'to_slot', 'insert', 'retreat')
#: 캐니스터를 쥔 채 움직이는 단계. 이 동안 holding 이 false 가 되면 낙하다.
CARRYING_PHASES = ('lift', 'to_slot', 'insert')
#: M0609 자산의 관절 한계(rad). 노드 파라미터 `joint_limits_low/high` 의 기본값이다.
#: 출처: sim README 의 USD 관절 한계(9/17, Simu)와 마클2 가 master02 자산에서 읽은 dof 한계.
#: `joint_3` ±150°, 나머지 ±360°. teach 값의 `joint_6` 은 실행마다 2π 갈려(3.7457, -2.5352, -3.7749) 모두 ±2π 안이다.
M0609_JOINT_LIMITS = tuple(
    (-math.radians(150.0), math.radians(150.0)) if index == 2 else (-2.0 * math.pi, 2.0 * math.pi)
    for index in range(DOF))
#: 노드 파라미터 `<key>_joints` 여섯 개.
POSE_KEYS = ('shelf_approach', 'shelf_grasp',
             'slot_a_approach', 'slot_a_insert', 'slot_b_approach', 'slot_b_insert')

#: `rail` 은 레일 단계의 목표(2개)다. 그때 `joints` 는 None 이고 팔은 그대로 있는다. 레일을 안 쓰면 늘 None.
#: 레일 teach 의 잡기·놓기 단계는 `joints` 도 `rail` 도 None 이고 그리퍼만 바꾼다.
#: `tolerance` 는 그 팔 단계의 도착 허용오차(rad)다. None 이면 노드의 `waypoint_tolerance_rad`.
Step = namedtuple('Step', ('phase', 'joints', 'gripper', 'rail', 'tolerance'), defaults=(None, None))


class RefillPlanError(ValueError):
    """goal 또는 waypoint 파라미터가 틀렸다."""


def slot_letter(slot):
    """0 → 'a', 1 → 'b'. 다른 값은 goal 거부 사유다."""
    if slot == SLOT_A:
        return 'a'
    if slot == SLOT_B:
        return 'b'
    raise RefillPlanError(f'slot={slot!r} 은 SLOT_A(0) 또는 SLOT_B(1) 이어야 한다')


def check_joints(name, values, dof=DOF):
    """관절값 목록을 float 튜플로. 개수가 다르거나 숫자가 아니면 RefillPlanError."""
    try:
        joints = tuple(float(value) for value in values)
    except (TypeError, ValueError) as error:
        raise RefillPlanError(f'{name}: 숫자 {dof}개 목록이어야 한다 ({values!r})') from error
    if len(joints) != dof:
        raise RefillPlanError(f'{name}: 관절 {dof}개여야 한다. {len(joints)}개를 받았다')
    return joints


def plan_refill(slot, poses):
    """슬롯 하나의 보충 순서. `poses` 는 POSE_KEYS → 관절값 6개.

    선반 접근 → 잡기(닫기) → 들기 → 슬롯 접근 → 삽입(열기) → 후퇴. 후퇴는 슬롯 접근 자세다.
    홈 복귀는 이 순서 밖에서 노드가 한다(성공·실패는 결과 전, 취소는 결과 뒤).
    """
    letter = slot_letter(slot)
    missing = [key for key in POSE_KEYS if key not in poses]
    if missing:
        raise RefillPlanError(f'waypoint 파라미터가 없다: {missing}')
    checked = {key: check_joints(key, poses[key]) for key in POSE_KEYS}
    approach = checked[f'slot_{letter}_approach']
    insert = checked[f'slot_{letter}_insert']
    return [
        Step('to_shelf', checked['shelf_approach'], None),
        Step('grasp', checked['shelf_grasp'], GRIP_CLOSE),
        Step('lift', checked['shelf_approach'], None),
        Step('to_slot', approach, None),
        Step('insert', insert, GRIP_OPEN),
        Step('retreat', approach, None),
    ]


def limit_violation(joints, limits):
    """한계 밖의 첫 관절 (index, 값, low, high). 모두 안이면 None. 경계값은 안으로 본다."""
    for index, (value, (low, high)) in enumerate(zip(joints, limits, strict=True)):
        if not float(low) <= float(value) <= float(high):
            return index, float(value), float(low), float(high)
    return None


def plan_limit_violation(slot, poses, home, limits):
    """이 슬롯 보충이 갈 자세(실행 순서, 마지막은 홈) 중 한계 밖의 첫 것.

    (파라미터 이름, index, 값, low, high) 또는 None.
    """
    letter = slot_letter(slot)
    names = ('shelf_approach', 'shelf_grasp', f'slot_{letter}_approach', f'slot_{letter}_insert')
    targets = [(f'{name}_joints', check_joints(name, poses[name])) for name in names]
    targets.append(('home_joint_positions', check_joints('home_joint_positions', home)))
    for name, joints in targets:
        violation = limit_violation(joints, limits)
        if violation is not None:
            return (name, *violation)
    return None


def at_pose(joints, reference, tolerance):
    """모든 관절이 tolerance(rad) 이내인가."""
    if joints is None or reference is None or len(joints) != len(reference):
        return False
    return all(abs(float(a) - float(b)) <= tolerance for a, b in zip(joints, reference, strict=True))


def interpolate(start, goal, max_step):
    """관절 공간 직선 보간. 마지막 점은 goal 그대로다. 움직임이 없으면 goal 하나."""
    start = tuple(float(value) for value in start)
    goal = tuple(float(value) for value in goal)
    if len(start) != len(goal):
        raise RefillPlanError(f'보간 시작·목표 길이가 다르다 ({len(start)} vs {len(goal)})')
    largest = max((abs(g - s) for s, g in zip(start, goal, strict=True)), default=0.0)
    count = max(1, math.ceil(largest / max(1e-6, max_step)))
    points = []
    for index in range(1, count + 1):
        ratio = index / count
        points.append(tuple(s + (g - s) * ratio for s, g in zip(start, goal, strict=True)))
    points[-1] = goal
    return points


def trapezoid_points(start, goal, max_speed, max_accel, period):
    """동기화 사다리꼴 궤적 점. 모든 축이 같이 출발해 같이 도착하고, 축마다 속도·가속 한계를 넘지 않는다.

    진행률 s(0→1)를 가속·등속·감속으로 움직인다. s 의 속도·가속 상한은 축마다 (한계 ÷ 이동량) 중 가장 작은 값이다.
    가장 빡빡한 축이 한계에 닿는다. 짧은 이동은 등속 없이 삼각형이다.
    점은 `period` 초 간격이고 마지막 점은 goal 그대로다.
    움직임이 없으면 goal 하나다.
    """
    start = tuple(float(value) for value in start)
    goal = tuple(float(value) for value in goal)
    if not len(start) == len(goal) == len(max_speed) == len(max_accel):
        raise RefillPlanError('사다리꼴: 시작·목표·속도·가속 길이가 다르다')
    if not all(v > 0.0 for v in max_speed) or not all(a > 0.0 for a in max_accel) or not period > 0.0:
        raise RefillPlanError('사다리꼴: 속도·가속·주기는 양수여야 한다')
    moving = [(abs(g - s), v, a) for s, g, v, a in zip(start, goal, max_speed, max_accel, strict=True)
              if abs(g - s) > 1e-12]
    if not moving:
        return [goal]
    speed = min(v / d for d, v, _ in moving)
    accel = min(a / d for d, _, a in moving)
    ramp = speed / accel
    if speed * ramp >= 1.0:                      # 최고 속도에 닿기 전에 반을 지난다: 삼각형
        ramp = math.sqrt(1.0 / accel)
        speed = accel * ramp
        cruise = 0.0
    else:
        cruise = (1.0 - speed * ramp) / speed
    total = 2.0 * ramp + cruise

    def progress(t):
        if t < ramp:
            return 0.5 * accel * t * t
        if t < ramp + cruise:
            return 0.5 * accel * ramp * ramp + speed * (t - ramp)
        rest = max(0.0, total - t)
        return 1.0 - 0.5 * accel * rest * rest

    points = []
    count = max(1, math.ceil(total / period - 1e-9))
    for index in range(1, count + 1):
        ratio = progress(min(total, index * period))
        points.append(tuple(s + (g - s) * ratio for s, g in zip(start, goal, strict=True)))
    points[-1] = goal
    return points


def peak_speed(points, period, position_of):
    """이웃한 점 사이 `position_of`(예: FK 의 TCP 위치) 이동 ÷ period 의 최댓값."""
    positions = [position_of(point) for point in points]
    return max((math.dist(a, b) / period for a, b in zip(positions, positions[1:], strict=False)), default=0.0)


def clamp(joints, limits):
    """관절 한계로 자른다. limits 는 (low, high) 쌍의 목록."""
    return tuple(min(max(float(value), float(low)), float(high))
                 for value, (low, high) in zip(joints, limits, strict=True))


# ---- 레일(조제실 스테이지, `rail_enabled`) ---------------------------------------------------------

#: 레일 관절 수(rail_x, rail_y, m).
RAIL_DOF = 2
#: teach 의 슬롯 키. `slot_letter` 값과 같다.
RAIL_SLOTS = ('a', 'b')

RailTeach = namedtuple('RailTeach', ('home_joints', 'home_rail', 'safe_phases', 'slots'))


def load_rail_teach(data):
    """레일 teach(yaml 을 읽은 dict)를 검사해 `RailTeach` 로. 틀리면 RefillPlanError.

    모양: `home: {joints: [6], rail: [2]}`, `rail_safe_phases: [phase, ...]`,
    `slots: {a: [step, ...], b: [step, ...]}`. step 은 `{phase, rail: [2]}`(레일만), `{phase, joints: [6]}`
    (팔만) 또는 `{phase, gripper: close|open}`(그리퍼만)이고, 팔 단계에는 `gripper` 를 붙일 수 있다(도착 뒤).
    팔 단계에는 `tolerance_rad`(도착 허용오차, 양수)를 줄 수 있다. 투입구 바로 위처럼 여유가 적은 자세다.
    """
    if not isinstance(data, dict):
        raise RefillPlanError('레일 teach 는 dict 여야 한다')
    home = data.get('home') or {}
    home_joints = check_joints('home.joints', home.get('joints', ()))
    home_rail = check_joints('home.rail', home.get('rail', ()), RAIL_DOF)
    safe = tuple(str(phase) for phase in data.get('rail_safe_phases') or ())
    slots = data.get('slots') or {}
    plans = {}
    for letter in RAIL_SLOTS:
        if letter not in slots:
            raise RefillPlanError(f'레일 teach 에 slots.{letter} 가 없다')
        plans[letter] = _rail_steps(letter, slots[letter], home_joints, safe)
    return RailTeach(home_joints, home_rail, safe, plans)


def _rail_steps(letter, raw_steps, home_joints, safe_phases, rail_dof=RAIL_DOF):
    """한 슬롯의 단계 목록을 Step 으로. 레일 단계는 팔이 접힌 자세(홈 또는 safe_phases)에 있을 때만 둔다."""
    steps = []
    arm_phase, arm_joints = 'home', home_joints
    closed = False
    for index, raw in enumerate(raw_steps or ()):
        where = f'slots.{letter}[{index}]'
        if not isinstance(raw, dict) or not raw.get('phase'):
            raise RefillPlanError(f'{where}: phase 가 있는 dict 여야 한다')
        phase = str(raw['phase'])
        rail = raw.get('rail')
        joints = raw.get('joints')
        gripper = raw.get('gripper')
        tolerance = raw.get('tolerance_rad')
        if tolerance is not None:
            if joints is None:
                raise RefillPlanError(f'{where} {phase}: tolerance_rad 는 팔 단계에만 둔다')
            tolerance = check_joints(f'{where}.tolerance_rad', [tolerance], 1)[0]
            if not tolerance > 0.0:
                raise RefillPlanError(f'{where} {phase}: tolerance_rad 는 양수여야 한다 ({tolerance})')
        if rail is not None and joints is not None:
            raise RefillPlanError(f'{where} {phase}: 레일과 팔을 한 단계에서 같이 움직이지 않는다')
        if gripper not in (None, GRIP_CLOSE, GRIP_OPEN):
            raise RefillPlanError(f'{where} {phase}: gripper 는 close 또는 open 이다 ({gripper!r})')
        if rail is None and joints is None and gripper is None:
            raise RefillPlanError(f'{where} {phase}: 할 일이 없다')
        if rail is not None:
            if gripper is not None:
                raise RefillPlanError(f'{where} {phase}: 레일 단계에서는 그리퍼를 바꾸지 않는다')
            if arm_phase != 'home' and arm_phase not in safe_phases:
                raise RefillPlanError(
                    f'{where} {phase}: 팔이 {arm_phase} 자세다. 레일은 홈·{list(safe_phases)} 자세에서만 움직인다')
            steps.append(Step(phase, None, None, check_joints(f'{where}.rail', rail, rail_dof)))
            continue
        if joints is not None:
            arm_joints = check_joints(f'{where}.joints', joints)
            arm_phase = phase
        if gripper == GRIP_OPEN and not closed:
            raise RefillPlanError(f'{where} {phase}: 잡기 전에 놓는다')
        closed = closed or gripper == GRIP_CLOSE
        steps.append(Step(phase, None if joints is None else arm_joints, gripper, None, tolerance))
    grippers = [step.gripper for step in steps if step.gripper is not None]
    if grippers != [GRIP_CLOSE, GRIP_OPEN]:
        raise RefillPlanError(f'slots.{letter}: 그리퍼는 close 한 번 뒤 open 한 번이어야 한다 ({grippers})')
    return tuple(steps)


def validate_plan(steps, home_joints, safe_phases, rail_dof):
    """실행 중 만든 계획(Step 목록, 장면 v2)을 teach 와 같은 규칙으로 검사한다. 통과하면 Step 튜플을 돌려준다.

    레일은 접힌 자세(홈·safe_phases) 뒤에만, 레일과 팔을 한 단계에서 같이 움직이지 않는다, close 한 번 뒤 open 한 번.
    """
    raw = []
    for step in steps:
        item = {'phase': step.phase}
        if step.rail is not None:
            item['rail'] = list(step.rail)
        if step.joints is not None:
            item['joints'] = list(step.joints)
        if step.gripper is not None:
            item['gripper'] = step.gripper
        if step.tolerance is not None:
            item['tolerance_rad'] = step.tolerance
        raw.append(item)
    return _rail_steps('plan', raw, tuple(home_joints), tuple(safe_phases), rail_dof)


def rail_safe_poses(teach, letter):
    """레일이 움직여도 되는 팔 자세: 홈과 이 슬롯에서 rail_safe_phases 에 든 팔 단계의 관절값."""
    poses = [teach.home_joints]
    poses += [step.joints for step in teach.slots[letter]
              if step.joints is not None and step.phase in teach.safe_phases]
    return tuple(poses)


def arm_folded(joints, safe_poses, tolerance):
    """팔이 레일을 움직여도 되는 자세 중 하나에 tolerance(rad) 이내로 있나. 관절값이 없으면 False."""
    return any(at_pose(joints, pose, tolerance) for pose in safe_poses)


def rail_arm_targets(teach, letter):
    """이 슬롯 보충이 팔을 보낼 관절값(순서대로, 마지막은 홈)과 그 이름. 관절 한계 검사용."""
    targets = [(f'slots.{letter} {step.phase}', step.joints) for step in teach.slots[letter]
               if step.joints is not None]
    return targets + [('home.joints', teach.home_joints)]
