"""레일 teach 경로의 여유 거리(오프라인). ROS 도 Isaac 도 import 하지 않는다. 노드는 쓰지 않는다.

#144 명목 FK 로 링크 좌표계를 구하고, 링크 collision 형상의 bbox(링크 좌표계, `config/m0609_collision.yaml`, 마클2 가
master02 자산에서 읽음)를 월드의 방향 있는 박스(OBB)로 놓아 조제실 스테이지의 고정 박스(선반·조제기·투입구)까지
최소 거리를 잰다. teach 경로(`config/m0609_rail_teach.yaml`)를 레일 이동과 함께 촘촘히 샘플링한다.

- 거리는 OBB 와 박스 사이 최소 거리다(볼록 이차계획을 좌표 하강으로 푼다). 겹치면 0 이다(깊이는 재지 않는다).
- collision 은 convexHull 이고 bbox 는 그것을 감싼다. 그래서 표의 거리는 실제 여유보다 작거나 같다(보수적).
  캡슐(bbox 를 감싸는 선분 + 반지름)은 더 보수적이라 쓰지 않았다. link_2 가 선반판과 8.6 cm 겹친다고 나왔는데 실습3
  기록은 impulse 0 근접뿐이었다(9/18 대조).
- 스테이지 박스는 `sim/standalone/p3sim/layout.py` `default_layout()` 을 main 7453b3d 에서 돌린 값을 옮겼다
  (`STAGE_BOXES`). 테스트가 저장소 checkout 에서 layout.py 와 다시 대조한다.
- 베이스(base_link) 월드 = (rail_x, 0.30 + rail_y, 0.60 + rail_z), 회전 없음
  (Simu 9/18, layout.py rail_origin·carriage_height).
  rail_z 는 장면 v2 의 3축 레일만 있다(2축이면 0).
"""

import math
from collections import namedtuple

from rokey_p3_manipulation import m0609_kinematics as kin
from rokey_p3_manipulation import refill_sequence as seq

#: 레일 원점(월드)과 받침 높이. layout.py default_layout: rail_origin (0, 0.30, 0), carriage_height 0.6.
BASE_ORIGIN = (0.0, 0.30, 0.60)

Box = namedtuple('Box', ('name', 'center', 'size'))
#: link 는 'base_link', 'link_1'..'link_6' 또는 'canister'(잡은 동안, TCP 좌표계). low·high 는 그 좌표계의 bbox.
LinkBox = namedtuple('LinkBox', ('link', 'name', 'low', 'high'))
Hit = namedtuple('Hit', ('phase', 'link', 'distance', 'box', 'point'))

#: layout.py default_layout() 결과(main 7453b3d, 9/18). 이름·중심·크기(m, 월드 축 정렬).
STAGE_BOXES = (
    Box('ShelfBack', (-0.55, 1.08, 0.525), (1.5, 0.02, 1.05)),
    Box('ShelfSideLeft', (-1.31, 0.91, 0.525), (0.02, 0.32, 1.05)),
    Box('ShelfSideRight', (0.21, 0.91, 0.525), (0.02, 0.32, 1.05)),
    Box('ShelfBoard0', (-0.55, 0.91, 0.29), (1.5, 0.32, 0.02)),
    Box('ShelfBoard1', (-0.55, 0.91, 0.54), (1.5, 0.32, 0.02)),
    Box('ShelfBoard2', (-0.55, 0.91, 0.79), (1.5, 0.32, 0.02)),
    Box('DispenserBody', (1.0, 1.0, 0.8), (0.7, 0.6, 1.6)),
    Box('DispenserLedge', (1.0, 0.615, 0.84), (0.26, 0.17, 0.02)),
    Box('InletAFloor', (0.94, 0.58, 0.855), (0.1, 0.1, 0.01)),
    Box('InletAWallXMinus', (0.895, 0.58, 0.91), (0.01, 0.1, 0.12)),
    Box('InletAWallXPlus', (0.985, 0.58, 0.91), (0.01, 0.1, 0.12)),
    Box('InletAWallYMinus', (0.94, 0.535, 0.91), (0.1, 0.01, 0.12)),
    Box('InletAWallYPlus', (0.94, 0.625, 0.91), (0.1, 0.01, 0.12)),
    Box('InletBFloor', (1.06, 0.58, 0.855), (0.1, 0.1, 0.01)),
    Box('InletBWallXMinus', (1.015, 0.58, 0.91), (0.01, 0.1, 0.12)),
    Box('InletBWallXPlus', (1.105, 0.58, 0.91), (0.01, 0.1, 0.12)),
    Box('InletBWallYMinus', (1.06, 0.535, 0.91), (0.1, 0.01, 0.12)),
    Box('InletBWallYPlus', (1.06, 0.625, 0.91), (0.1, 0.01, 0.12)),
)
LINKS = ('base_link', 'link_1', 'link_2', 'link_3', 'link_4', 'link_5', 'link_6')


def obb_box_distance(center, axes, half, box, iterations=200, tolerance=1e-10):
    """방향 있는 박스(중심, 단위 축 셋, 반길이 셋)와 축 정렬 박스 사이 최소 거리와 그때 OBB 쪽 점.

    min |c + Σ u_i a_i − y|², |u_i| ≤ h_i, y ∈ 박스. 볼록이고 제약이 좌표마다 따로라 좌표 하강(각 좌표는 닫힌 꼴로
    잘라 낸다)이 전역 최소로 간다. 겹치면 0.
    """
    low = [c - s / 2.0 for c, s in zip(box.center, box.size, strict=True)]
    high = [c + s / 2.0 for c, s in zip(box.center, box.size, strict=True)]
    u = [0.0, 0.0, 0.0]
    x = list(center)
    previous = math.inf
    for _ in range(iterations):
        y = [min(max(v, lo), hi) for v, lo, hi in zip(x, low, high, strict=True)]
        for i, (axis, h) in enumerate(zip(axes, half, strict=True)):
            residual = [xv - u[i] * av - yv for xv, av, yv in zip(x, axis, y, strict=True)]
            value = min(max(-sum(r * a for r, a in zip(residual, axis, strict=True)), -h), h)
            x = [r + value * a + yv for r, a, yv in zip(residual, axis, y, strict=True)]
            u[i] = value
        y = [min(max(v, lo), hi) for v, lo, hi in zip(x, low, high, strict=True)]
        squared = sum((xv - yv) ** 2 for xv, yv in zip(x, y, strict=True))
        if previous - squared < tolerance:
            break
        previous = squared
    return math.sqrt(squared), tuple(x)


def link_frames(joints, tcp_offset):
    """링크 좌표계 {이름: (위치, 쿼터니언 xyzw)}. 베이스 좌표계 기준. m0609_kinematics.chain 과 같은 순서로 곱한다.

    'tcp' 는 link_6 에서 tcp_offset(link_6 좌표) 만큼 간 점이고 자세는 link_6 과 같다.
    """
    joints = kin.finite(joints, 6)
    p, q = (0.0, 0.0, 0.0), (0.0, 0.0, 0.0, 1.0)
    frames = {'base_link': (p, q)}
    for index, (theta, (translation, _), fixed) in enumerate(
            zip(joints, kin._ORIGINS, kin._ORIGIN_QUATS, strict=True), 1):
        p = kin.add(p, kin.rotate(q, translation))
        q = kin.unit(kin.quat_mul(kin.quat_mul(q, fixed), kin.axis_angle((0.0, 0.0, 1.0), theta)), 4)
        frames[f'link_{index}'] = (p, q)
    frames['tcp'] = (kin.add(p, kin.rotate(q, tcp_offset)), q)
    return frames


def base_position(rail, origin=BASE_ORIGIN):
    """베이스 월드 위치. rail 은 (x, y) 또는 (x, y, z)(장면 v2 의 3축 레일, z 는 위가 양수, Simu 9/18)."""
    return (origin[0] + rail[0], origin[1] + rail[1], origin[2] + (rail[2] if len(rail) > 2 else 0.0))


def link_boxes_world(joints, rail, link_boxes, tcp_offset, carrying, base_origin=BASE_ORIGIN):
    """링크 bbox 를 월드 OBB (link, name, 중심, 축 셋, 반길이 셋) 로. carrying 이 아니면 'canister' 는 뺀다."""
    frames = link_frames(joints, tcp_offset)
    base = base_position(rail, base_origin)
    out = []
    for item in link_boxes:
        if item.link == 'canister' and not carrying:
            continue
        p, q = frames['tcp' if item.link == 'canister' else item.link]
        local = tuple((lo + hi) / 2.0 for lo, hi in zip(item.low, item.high, strict=True))
        center = kin.add(base, kin.add(p, kin.rotate(q, local)))
        axes = tuple(kin.rotate(q, e) for e in ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)))
        half = tuple((hi - lo) / 2.0 for lo, hi in zip(item.low, item.high, strict=True))
        out.append((item.link, item.name, center, axes, half))
    return out


def sample_path(teach, letter, joint_step=0.01, rail_step=0.01):
    """teach 한 바퀴를 (phase, joints, rail, carrying) 점으로. 노드와 같은 순서다.

    시작은 홈·레일 홈. 팔 단계는 관절 직선(노드의 동기화 사다리꼴도 같은 길이다), 레일 단계는 레일 직선.
    끝에 노드의 결과 전 복귀(retreat 는 접힌 자세라 레일 홈 → 팔 홈)를 'home_rail'·'home_arm' 으로 붙인다.
    carrying 은 grasp(닫기) 뒤부터 release(열기) 전까지다.
    """
    arm, rail, carrying = teach.home_joints, teach.home_rail, False
    points = []
    for step in teach.slots[letter]:
        if step.rail is not None:
            for r in [rail] + seq.interpolate(rail, step.rail, rail_step):
                points.append((step.phase, arm, r, carrying))
            rail = step.rail
        elif step.joints is not None:
            for j in [arm] + seq.interpolate(arm, step.joints, joint_step):
                points.append((step.phase, j, rail, carrying))
            arm = step.joints
        if step.gripper == seq.GRIP_CLOSE:
            carrying = True
        elif step.gripper == seq.GRIP_OPEN:
            carrying = False
    for r in [rail] + seq.interpolate(rail, teach.home_rail, rail_step):
        points.append(('home_rail', arm, r, carrying))
    for j in [arm] + seq.interpolate(arm, teach.home_joints, joint_step):
        points.append(('home_arm', j, teach.home_rail, carrying))
    return points


def clearance_table(points, link_boxes, tcp_offset, boxes=STAGE_BOXES, base_origin=BASE_ORIGIN):
    """(phase, link) 마다 가장 가까운 스테이지 박스. 반환은 Hit 목록(단계 순서, 링크 순서).

    멀리 있는 박스는 경계구로 먼저 걸러 낸다(OBB 경계구와 박스 사이 거리가 지금 최솟값보다 크면 건너뛴다).
    """
    return _table(points, link_boxes, tcp_offset, boxes, base_origin, None)


def worst_clearance(points, link_boxes, tcp_offset, boxes, base_origin=BASE_ORIGIN, stop_below=None):
    """경로 전체에서 가장 가까운 한 곳(Hit). 여러 링크·단계 중 최솟값만 필요할 때 쓴다(계획).

    가지치기를 전체 최솟값으로 해 clearance_table 보다 빠르다. stop_below 를 주면 그보다 가까운 곳을 찾는 즉시
    멈춘다(그 후보는 어차피 뽑히지 않는다). 없으면 Hit(distance=inf).
    """
    hits = _table(points, link_boxes, tcp_offset, boxes, base_origin, stop_below)
    return min(hits, key=lambda h: h.distance) if hits else Hit('', '', math.inf, '', None)


def _table(points, link_boxes, tcp_offset, boxes, base_origin, stop_below):
    """clearance_table·worst_clearance 본체. stop_below 가 None 이면 칸별, 아니면 전체 최솟값으로 가지친다."""
    global_min = stop_below is not None
    best = {}
    order = []
    for phase, joints, rail, carrying in points:
        for link, _, center, axes, half in link_boxes_world(joints, rail, link_boxes, tcp_offset, carrying,
                                                            base_origin):
            key = ('', '') if global_min else (phase, link)
            if key not in best:
                order.append(key)
                best[key] = Hit(phase, link, math.inf, '', None)
            reach = math.hypot(*half)
            for box in boxes:
                gap = math.sqrt(sum(max(abs(c - bc) - s / 2.0, 0.0) ** 2
                                    for c, bc, s in zip(center, box.center, box.size, strict=True)))
                if gap - reach >= best[key].distance:
                    continue
                distance, point = obb_box_distance(center, axes, half, box)
                if distance < best[key].distance:
                    best[key] = Hit(phase, link, distance, box.name, point)
                    if global_min and distance < stop_below:
                        return [best[key]]
    return [best[key] for key in order]


def load_collision(data):
    """collision yaml({'tcp_offset': [3], 'boxes': [{link, name, min, max}]})을 (tcp_offset, LinkBox 들)로."""
    tcp_offset = tuple(float(v) for v in data['tcp_offset'])
    items = []
    for raw in data['boxes']:
        link = str(raw['link'])
        if link not in LINKS + ('canister',):
            raise ValueError(f'모르는 링크 {link}')
        low, high = tuple(float(v) for v in raw['min']), tuple(float(v) for v in raw['max'])
        if not all(h > lo for lo, h in zip(low, high, strict=True)):
            raise ValueError(f'{link} {raw.get("name")}: min < max 여야 한다')
        items.append(LinkBox(link, str(raw.get('name', link)), low, high))
    return tcp_offset, tuple(items)


def format_table(hits, warn_below=0.02):
    """마크다운 표. 여유가 warn_below 보다 작으면 굵게."""
    lines = ['| 단계 | 링크 | 최소 거리 m | 상대 물체 | 가까운 점 (x, y, z) |', '| --- | --- | --- | --- | --- |']
    for hit in hits:
        distance = f'{hit.distance:.3f}'
        if hit.distance < warn_below:
            distance = f'**{distance}**'
        where = ', '.join(f'{v:.3f}' for v in hit.point)
        lines.append(f'| {hit.phase} | {hit.link} | {distance} | {hit.box} | ({where}) |')
    return '\n'.join(lines)


def main(argv=None):
    """`python3 -m rokey_p3_manipulation.clearance <teach.yaml> <collision.yaml> [a|b ...]` → 슬롯마다 마크다운 표."""
    import sys

    import yaml
    args = sys.argv[1:] if argv is None else argv
    if len(args) < 2:
        print(main.__doc__)
        return 2
    with open(args[0], encoding='utf-8') as handle:
        teach = seq.load_rail_teach(yaml.safe_load(handle))
    with open(args[1], encoding='utf-8') as handle:
        tcp_offset, link_boxes = load_collision(yaml.safe_load(handle))
    for letter in args[2:] or seq.RAIL_SLOTS:
        print(f'### slot {letter}\n')
        print(format_table(clearance_table(sample_path(teach, letter), link_boxes, tcp_offset)))
        print()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
