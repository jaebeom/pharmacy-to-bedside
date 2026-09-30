"""조제실 장면 v2 의 재고·기하 읽기와 한 번의 보충 계획. ROS 도 Isaac 도 import 하지 않는다.

스테이지(Simu 9/18)가 `/m0609/shelf/inventory`(std_msgs/String JSON, reliable + transient_local)로 칸·수납·장애물을
알린다. 치수는 전부 거기서 읽는다(세준 실제 USD 로 옮기면 바뀐다). 이 모듈은 그 JSON 을 `Scene` 으로 바꾸고,
item 하나를 넣는 계획(레일 3축 + 팔 관절 단계)을 만든다.

잡기는 모두 **앞 접근**이다: 공구 +z = 월드 +y(선반 안쪽), 공구 +x = 월드 +x(손가락이 x 로 닫힌다).
- 위에서 잡은 모듈은 +y 구멍에 밀어 넣을 수 없다. 닫힌 손가락 폭(±0.053)이 구멍(±0.04)보다 넓어 앞면에 닿는다.
  앞에서 뒤쪽 절반을 잡으면 손가락이 구멍 밖에 남는다(Simu 권고).
- 원통은 윗부분을 앞에서 잡는다. 수납통에 중심이 테두리 아래로 들어가도 손가락은 테두리 위에 있다.
- 약통을 쥔 채 공구 자세를 바꾸지 않는다(잡은 뒤에는 약통이 link_6 에 붙는다).

순서(레일은 팔이 접힌 자세일 때만 움직인다):
  홈 → 레일(칸 앞) → 칸 앞 → 파지 → 들기 → 빼기 → 접힘(fold) → 레일(수납 앞) → 수납 앞 → 넣기 → 놓기 → 물러나기
  → (노드 복귀: 접힌 자세면 레일 홈 → 팔 홈)
"""

import json
import math
from collections import namedtuple

from rokey_p3_manipulation import clearance as C
from rokey_p3_manipulation import m0609_kinematics as kin
from rokey_p3_manipulation import pick_plan as P
from rokey_p3_manipulation import refill_sequence as seq

#: 공구 +z = 월드 +y, 공구 +x = 월드 +x(x 축 −90° 회전). xyzw.
FRONT = (-math.sqrt(0.5), 0.0, 0.0, math.sqrt(0.5))

CellV2 = namedtuple('CellV2', ('cell_id', 'kind', 'item_id', 'present', 'access', 'center', 'size'))
Target = namedtuple('TargetV2', ('kind', 'point', 'axis', 'data'))
Scene = namedtuple('Scene', ('cells', 'targets', 'obstacles', 'items', 'rail_names', 'rail_limits', 'base_origin',
                             'rail_parts'), defaults=((),))
#: 레일 부품(재고 JSON `rail.parts`). center 는 레일 (0, 0, 0) 일 때의 월드 축 정렬 bbox 중심, moves 는 그 부품을 옮기는
#: 레일 축('x'·'y'·'z'). 스테이지에서 대부분 collision 없는 visual 이라 Isaac 은 팔이 뚫고 지나가는 것을 막지 않는다
#: (실습7-a 재범 관찰 "M0609 가 베이스 레일을 관통"). 계획에서 장애물로 본다.
RailPart = namedtuple('RailPart', ('name', 'center', 'size', 'moves'))
#: 계획 매개변수. 거리 m, 각 rad. 기본값은 v2 첫판(Simu 9/18 임시 치수)에 맞춘 우리 선택값이다.
#: 레일 후보는 목표 기준 상대값 (뒤 back, 옆 side, 높이 차 dz) 다: 베이스 = 목표 − 공구 방향 × back + 옆 방향 × side,
#: 베이스 z = 목표 z − dz. 좌표를 하드코딩하지 않는다. 한계 밖이면 한계로 자른다.
Params = namedtuple('Params', (
    'approach',        # 칸·수납 앞에서 기다리는 거리(공구 방향 반대쪽으로)
    'lift',            # 파지 뒤 들어 올리는 높이
    'cylinder_grip',   # 원통: 윗면에서 이만큼 아래를 잡는다
    'module_grip',     # 모듈: 중심에서 이만큼 앞(−y)을 잡는다(뒤쪽 절반)
    'round_sink',      # 원형: 약통 중심이 테두리 아래로 이만큼 들어간 곳에서 놓는다
    'module_push',     # 모듈: 약통 중심이 앞면을 이만큼 넘은 곳에서 놓는다
    'hover',           # 수납 위·앞에서 테두리·앞면과 띄우는 여유
    'retreat',         # 놓은 뒤 공구 반대 방향으로 물러나는 거리
    'min_clearance',   # 팔·그리퍼 여유가 이보다 작으면 그 칸을 건너뛴다
    'canister_min',    # 잡은 약통의 여유 기준(수납에 들어가며 벽과 1 cm 안쪽이 정상이라 따로 둔다)
    'rail_pick',       # 선반 칸 레일 후보 [(back, side, dz)]: 목표에서 공구 반대로 back, 옆으로 side,
                       # 베이스 z = 목표 z − dz
    'rail_round',      # 원형 수납 후보 [(yaw, (back, side, dz))]
    'rail_module',     # 모듈 구멍 후보 [(back, side, dz)]
    'rail_limit_margin',  # 레일 목표가 한계에서 이만큼 안쪽이어야 후보가 된다(밖이면 자르지 않고 뺀다)
    'min_reach',       # 어깨(link_2 원점)에서 목표까지 이보다 가까운 레일 자세는 뺀다(자기 충돌 모델이 없다)
    'max_rail_tries',  # 구간마다 여유까지 계산하는 레일 후보 수 상한(IK 가 안 되는 후보는 세지 않는다)
    # --- 아래 넷은 `rail_select=PREFERRED_FIRST` 에서만 읽는다. 기본 모드와 guarded `module_path.plan_module` 은
    # 건드리지 않는다(둘 다 위 `rail_pick`·`rail_module` 만 읽는다). 그래서 기본 동작이 글자 그대로 같다.
    'rail_pick_extra',    # 새 모드에서 더 보는 선반 칸 후보
    'rail_module_extra',  # 새 모드에서 더 보는 모듈 구멍 후보
    'rail_round_extra',   # 새 모드에서 더 보는 원형 수납 후보 [(yaw, (back, side, dz))]
    'min_elbow_sin',   # 작업 자세의 sin|q3| 하한(0 = 끄기). 팔꿈치 조건의 대리값이고 90°에서 1 로 가장 좋다.
                       # 새 모드에서만 건다(작전 9/21 (b)). 기존 gate 를 낮추는 것이 아니라 **더 거는 것**이다.
    # --- 아래는 모든 모드에서 읽는다.
    'module_grip_up',  # 모듈: 중심에서 이만큼 위를 잡는다(작전 결정 9/23, 손 카메라가 약통 QR 을 보게)
), defaults=((), (), (), 0.0, 0.0))
#: cylinder_grip 0.02·round_sink 0.01: 손가락(공구 y 반폭 0.015)이 수납통 테두리보다 1.5 cm 위에 남는다
#: (9/18 계산: 0.03·0.02 면 손가락이 테두리에 닿았다). module_grip 0.04: 놓을 때 손가락 끝이 앞면 2 cm 밖이다.
#: module_grip_up 0.03(작전 결정 9/23): 모듈 가운데를 잡으면 M0609 손 카메라(잡는 점 0.0483 m 아래)가 선반면
#: 2.2 cm 위까지 내려와 약통 QR 이 선반 앞 가로보에 가렸다(94f19fb 손 카메라 영상, 3/3 unreadable).
#: 0.03 위를 잡으면 카메라가 선반면 5.2 cm 위로, 읽히던 원통 칸과 같은 높이가 된다.
DEFAULT_PARAMS = Params(approach=0.20, lift=0.03, cylinder_grip=0.02, module_grip=0.04, round_sink=0.01,
                        module_push=0.02, hover=0.04, retreat=0.12, min_clearance=0.01, canister_min=0.0,
                        rail_pick=((0.50, -0.15, 0.30), (0.50, 0.15, 0.30), (0.45, 0.15, 0.30), (0.45, -0.15, 0.30),
                                   (0.40, 0.15, 0.35), (0.40, -0.15, 0.35)),
                        # 원형은 (공구 yaw, 후보). 세운 원통이라 yaw(월드 z 축, 0 = 공구가 +y)에 무관하다.
                        # 앞 둘은 빈월드에서 쓰던 값이고, 뒤 넷(yaw 0)은 병원에서 더한 것이다. 병원 기준
                        # 투입구는 실습37 자리보다 −x 0.30·+y 0.10 안쪽이라(#496 결정: 투입구를 옮기지 않는다)
                        # 앞 둘로는 원통 칸 아홉이 전부 `넣기(round)` 에서 떨어졌다(9/23 회차, 9/18칸).
                        # 오프라인 전수 확인: 기준 자리에서 앞 둘은 불통과, yaw 0 을 더하면 통과한다.
                        # 뽑히는 것은 `(0.0, (0.40, 0.0, 0.35))` 이고 레일 (-4.75, -0.035, 0.41),
                        # 여유 0.011 m, 한계까지 0.065 m 다 — 후보 432개 격자의 답과 같다.
                        # 형상을 건드리지 않는 **경로** 수정이다(재범 9/22: 경로가 실패하면 형상을 유지한 채 고친다).
                        rail_round=((-math.pi / 4, (0.40, 0.0, 0.35)), (-math.pi / 4, (0.45, 0.0, 0.30)),
                                    (0.0, (0.40, 0.0, 0.35)), (0.0, (0.45, 0.0, 0.30)),
                                    (0.0, (0.40, 0.0, 0.30)), (0.0, (0.45, 0.0, 0.35))),
                        rail_module=((0.35, 0.15, 0.30), (0.35, -0.15, 0.30)),
                        rail_limit_margin=0.05, min_reach=0.40, max_rail_tries=8, module_grip_up=0.03)
#: 레일 자세 고르기 방식. `FIRST_FEASIBLE` 이 지금 동작이고 기본값이다(도달이 짧은 후보부터 시험해 처음
#: 통과한 것). 기존 hard gate 는 어느 모드에서나 같다 — 기준을 하나도 낮추지 않는다.
FIRST_FEASIBLE = 'first_feasible'
#: 첫 통과에서 멈추는 것은 그대로 두고 **후보 순서만** 오프라인 결과의 선호 순서로 바꾼다(작전 9/21 안 ⓓ).
#: 칸당 평가 수가 기본 모드와 같아 기동 캐시가 기준선 근처에 머문다. hard gate 는 기동 때 전부 돈다 —
#: 오프라인 결과를 믿고 건너뛰는 것이 아니라 **순서만 힌트**다.
PREFERRED_FIRST = 'preferred_first'
RAIL_SELECT = (FIRST_FEASIBLE, PREFERRED_FIRST)
#: 새 모드에서만 더 보는 후보. G1 후보표(#388)에서 지금 선택을 네 축에서 지배한 옆 ±0.30 계열과 그 부호 대칭이다.
#: 기동 캐시 시간이 1부→2부 전환에 그대로 더해지므로 **작게** 둔다(작전 9/21). 값은 관측에서 나온 것이고
#: 합격선이 아니다.
#: 뒤 0.45-0.65 가 들어간 것은 전체 격자에서 **뒤가 길수록** 통과가 늘고(뒤 0.40 은 4개, 0.55-0.60 은 53개씩)
#: 이긴 후보가 거기 몰려 있었기 때문이다. 옆 부호는 대칭으로 둔다 — 양 끝 칸에서는 바깥쪽이 레일 한계로
#: 떨어지고(시뮬 G0-3: 바깥 여유 0.25 m) 안쪽만 남는다. 떨어지는 것은 gate 가 하므로 목록은 대칭이어도 된다.
#: 실제로 뽑히는 것은 원통 칸의 `(0.65, -0.15, 0.30)` 과 모듈 칸의 `(0.60, 0.60, 0.40)` 둘뿐이고, 나머지 둘은
#: 옆 부호 대칭이다(장면이 좌우로 뒤집혀도 같은 자리가 있게). 뒤 0.45 이하를 넣지 않은 것은 전체 격자에서
#: **뒤 0.45 아래가 절벽**이기 때문이다(뒤 0.40 통과 4개 대 0.55-0.60 각 53개).
#: `min_elbow_sin` 0.50 은 **절대 하한**이다(신전·접힘 양쪽으로 30° 안쪽을 쓰지 않는다는 뜻).
#: 지금 동작의 작업 자세 sin|q3| 최솟값은 **0.5423**(|q3| 147.2°, 깊게 접힌 쪽)인데, 그 값을 그대로 gate 로
#: 걸면 **그 값을 만든 자세 자신이 걸려** 원통 칸 다섯이 안 풀린다. 그래서 절대 하한을 쓰고, 0.5423 은
#: 관측으로 기록한다 — 지금 자세가 이미 경계에 있다는 뜻이다(#388).
PREFERRED_PARAMS = DEFAULT_PARAMS._replace(
    rail_pick_extra=((0.65, -0.15, 0.30), (0.65, 0.15, 0.30),
                     (0.60, 0.60, 0.40), (0.60, -0.60, 0.40)),
    min_elbow_sin=0.50)
#: 후보는 9/18 오프라인 전수 탐색(Simu 6543ec4 장면: 뒤 0.35-0.90 × 옆 0·±0.15 × 높이 차 −0.2..0.4 를 도달 순으로)에서
#: 칸 종류·수납마다 **처음 통과한(도달이 가장 짧은)** 자세와 옆 부호만 바꾼 것이다. 실행 중에는 이 후보들을
#: 다시 도달 순으로 시험해 처음 통과한 것을 쓴다(기동 캐시를 3분 안에 끝내려고 격자를 줄였다).
#: 통과 자세는 베이스가 약통보다 30-35 cm 낮다.
#: 받침 0.30 장면에서 바닥 선반 아랫단(약통 z 0.36)은 전수 탐색에서도 통과 자세가 없었다(link_2 ↔ 승강판·선반 판).
#: 받침 0.55 장면(Simu c40c3f3, 재범 결정)에서는 이 후보 그대로 16칸 모두 통과한다(9/18).
#: 레일 자세 고르기(재범 9/18 실습7-a: "레일이 먼저 로봇이 집을 수 있는 최적 위치로 가고",
#: "베이스가 알약 위치·홈 자세보다 낮게, 가장 짧게"): 격자 후보를 **어깨 → 목표 거리가 짧은 순**으로 시험해
#: 처음 제약을 모두 만족하는 것을 쓴다.
#: 제약은 레일 한계 여유(rail_limit_margin), IK, 여유 거리(min_clearance, 레일 부품 포함), 최소 도달(min_reach).
#: cylinder_grip 0.02·round_sink 0.01: 손가락(공구 y 반폭 0.015)이 수납통 테두리보다 1.5 cm 위에 남는다
#: (9/18 계산: 0.03·0.02 면 손가락이 테두리에 닿았다). module_grip 0.04: 놓을 때 손가락 끝이 앞면 2 cm 밖이다.
#: rail_limit_margin 0.05: 9/17 한계 목표(rail_y 0.30)가 0.28 에서 멈춰 시한 초과(2 cm 부족), 실습7-a 모듈 넣기 목표
#: x 1.150(상한 1.20 의 5 cm 안)·z 0.576(상한 0.60 의 2.4 cm 안)에서 넣을 때 레일이 x 1.2000·z 0.48 로 튕겼다.
#: 한계 가까운 목표는 드라이브 여유가 없어 밀리면 되돌리지 못한다(판단). 그래서 5 cm 안쪽만 쓴다.
#: min_reach 0.40: 팔을 다 접는 자세는 자기 충돌을 모델에서 안 보므로 피한다(판단, 값은 우리 선택).
#: 어깨 = 베이스 + link_2 원점(관절 0 에서 z 0.1345).
SHOULDER_HEIGHT = 0.1345


class SceneError(ValueError):
    """재고 JSON 이 모자라거나 틀렸다."""


def _vec(values, size, where):
    try:
        out = tuple(float(v) for v in values)
    except (TypeError, ValueError) as error:
        raise SceneError(f'{where}: 숫자 {size}개가 아니다') from error
    if len(out) != size:
        raise SceneError(f'{where}: 숫자 {size}개가 아니다({len(out)})')
    return out


def parse_inventory(text, rail_names=('rail_x', 'rail_y', 'rail_z'),
                    rail_limits=((-1.2, 1.2), (-0.10, 0.33), (0.0, 0.40)), base_origin=(0.0, 0.30, 0.60)):
    """재고 JSON 문자열 → Scene. JSON 에 `rail`·`items` 가 있으면 그것을 쓰고, 없으면 인자(노드 파라미터)를 쓴다."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as error:
        raise SceneError(f'JSON 이 아니다: {error}') from error
    if data.get('scene') != 'v2':
        raise SceneError(f"scene 이 v2 가 아니다({data.get('scene')!r})")
    rail = data.get('rail') or {}
    names = tuple(rail.get('names', rail_names))
    limits = tuple(_vec(pair, 2, 'rail.limits') for pair in rail.get('limits', rail_limits))
    origin = _vec(rail.get('origin', base_origin), 3, 'rail.origin')
    if len(names) != 3 or len(limits) != 3:
        raise SceneError('레일은 3축이다(rail_x, rail_y, rail_z)')
    items = {str(k): str(v) for k, v in (data.get('items') or {}).items()}
    cells = []
    for raw in data.get('cells', ()):
        where = f"cells[{raw.get('cell')}]"
        kind = str(raw.get('type', ''))
        size = raw.get('size') or {}
        if kind == 'cylinder':
            dims = (float(size['diameter']), float(size['diameter']), float(size['height']))
        else:
            dims = (float(size['x']), float(size['y']), float(size['z']))
        item = str(raw.get('item', ''))
        if item and item not in items:
            items[item] = kind
        cells.append(CellV2(str(raw['cell']), kind, item, bool(raw.get('present', False)), str(raw.get('access', '')),
                            _vec(raw['pose']['xyz'], 3, where), dims))
    targets = {}
    for name, raw in (data.get('targets') or {}).items():
        if name == 'round':
            targets['cylinder'] = Target('round', _vec(raw['center'], 3, 'targets.round.center'),
                                         _vec(raw['axis'], 3, 'targets.round.axis'), dict(raw))
        elif name == 'module':
            targets['module'] = Target('module', _vec(raw['entry_center'], 3, 'targets.module.entry_center'),
                                       _vec(raw['axis'], 3, 'targets.module.axis'), dict(raw))
    obstacles = tuple(C.Box(str(o['name']), _vec(o['center'], 3, o['name']), _vec(o['size'], 3, o['name']))
                      for o in data.get('obstacles', ()))
    parts = tuple(RailPart(str(p['name']), _vec(p['center'], 3, p['name']), _vec(p['size'], 3, p['name']),
                           tuple(str(axis) for axis in p.get('moves', ()))) for p in rail.get('parts', ()))
    for part in parts:
        if not set(part.moves) <= {'x', 'y', 'z'}:
            raise SceneError(f'rail.parts {part.name}: moves 는 x·y·z 중에서다({part.moves})')
    if not cells or not targets:
        raise SceneError('칸이나 수납 위치가 없다')
    return Scene(tuple(cells), targets, obstacles, items, names, limits, origin, parts)


def kind_of(scene, item_id):
    """item → 약통 종류. items 표에 없으면 None."""
    return scene.items.get(item_id)


def tool_quat(yaw):
    """앞 접근 자세를 월드 z 축으로 yaw 만큼 돌린 쿼터니언(xyzw). 공구 +z 는 수평이다."""
    return kin.quat_mul(kin.axis_angle((0.0, 0.0, 1.0), yaw), FRONT)


def tool_direction(yaw):
    """공구 +z(접근 방향)의 월드 벡터. yaw 0 이면 +y."""
    return kin.rotate(tool_quat(yaw), (0.0, 0.0, 1.0))


def _along(point, direction, distance):
    return tuple(p + d * distance for p, d in zip(point, direction, strict=True))


def pick_points(cell, params):
    """칸에서 잡기까지의 TCP 월드 점(앞 접근, yaw 0). (phase, 점) 목록과 잡는 점."""
    x, y, z = cell.center
    if cell.kind == 'cylinder':
        grip = (x, y, z + cell.size[2] / 2.0 - params.cylinder_grip)
    else:
        grip = (x, y - params.module_grip, z + params.module_grip_up)
    front = (grip[0], grip[1] - params.approach, grip[2])
    lifted = (grip[0], grip[1], grip[2] + params.lift)
    out = (front[0], front[1], lifted[2])
    return [('shelf_front', front), ('grasp_pose', grip), ('lift', lifted), ('pull_out', out)], grip


def place_points(cell, target, grip, params, yaw=0.0):
    """수납까지의 TCP 월드 점. grip 은 잡은 점(약통 중심 → TCP 차를 그대로 쓴다). 모듈은 yaw 0 만 된다.

    반환: [(phase, 점)], 물러난 점. 원형은 수납 위로 와서 수직으로 넣고, 모듈은 구멍 앞에서 +y 로 민다.
    """
    offset = tuple(g - c for g, c in zip(grip, cell.center, strict=True))       # 약통 중심 → TCP
    direction = tool_direction(yaw)
    if target.kind == 'round':
        rim = target.point                               # 테두리 높이의 중심
        release = tuple(c + o for c, o in zip((rim[0], rim[1], rim[2] - params.round_sink), offset, strict=True))
        above = (release[0], release[1], rim[2] + cell.size[2] / 2.0 + offset[2] + params.hover)
        front = _along(above, direction, -params.approach)
        back = _along(above, direction, -params.retreat)
        return [('inlet_front', front), ('above_inlet', above), ('insert', release)], back
    entry = target.point                                 # 구멍 입구 중심(앞면)
    release = tuple(c + o for c, o in zip((entry[0], entry[1] + params.module_push, entry[2]), offset,
                                          strict=True))
    front = (release[0], entry[1] - cell.size[1] / 2.0 - params.hover + offset[1], release[2])
    back = (release[0], release[1] - params.retreat, release[2])
    return [('inlet_front', front), ('insert', release)], back


def rail_for(point, candidate, yaw, scene, margin):
    """목표 점·레일 후보(back, side, dz)·공구 yaw → (rail_x, rail_y, rail_z). 한계에서 margin 안쪽이 아니면 None.

    한계로 자르지 않는다. 잘린 목표는 계획한 베이스 위치가 아니고, 한계에 붙어 밀리면 되돌리지 못한다(실습7-a).
    """
    back, side, dz = candidate
    direction = tool_direction(yaw)
    lateral = (direction[1], -direction[0], 0.0)          # 공구 방향의 오른쪽(수평)
    base = tuple(p - d * back + s * side for p, d, s in zip(point, direction, lateral, strict=True))
    wanted = (base[0] - scene.base_origin[0], base[1] - scene.base_origin[1], point[2] - dz - scene.base_origin[2])
    if any(not lo + margin - 1e-9 <= v <= hi - margin + 1e-9 for v, (lo, hi) in zip(wanted, scene.rail_limits,
                                                                                      strict=True)):
        return None
    return wanted


def rail_candidates(point, yaw, scene, params, offsets, by_reach=True):
    """목표 점 하나의 레일 후보 [(도달 m, rail)]. 한계 여유·최소 도달을 못 채우면 뺀다.

    `by_reach` 가 참이면 어깨 → 목표 거리가 짧은 순이다(지금 동작). 거짓이면 **준 순서 그대로** 둔다 —
    `PREFERRED_FIRST` 가 오프라인 선호 순서를 그대로 쓰려고 그렇게 부른다. 거르는 조건은 둘이 같다.
    """
    out, seen = [], set()
    for offset in offsets:
        rail = rail_for(point, offset, yaw, scene, params.rail_limit_margin)
        if rail is None:
            continue
        key = tuple(round(v, 4) for v in rail)
        if key in seen:
            continue
        seen.add(key)
        base = C.base_position(rail, scene.base_origin)
        reach = math.dist((base[0], base[1], base[2] + SHOULDER_HEIGHT), point)
        if reach >= params.min_reach:
            out.append((reach, rail))
    return sorted(out) if by_reach else out


def rail_margin(rail, scene):
    """레일 자세가 한계에서 떨어진 최소 거리(m)."""
    return min(min(v - lo, hi - v) for v, (lo, hi) in zip(rail, scene.rail_limits, strict=True))


def obstacles_at(scene, rail):
    """레일 자세 rail 에서의 장애물: 고정 장애물 + 레일 부품(moves 축만큼 옮김)."""
    moved = []
    for part in scene.rail_parts:
        shift = tuple(rail[i] if axis in part.moves else 0.0 for i, axis in enumerate('xyz'))
        center = tuple(c + s for c, s in zip(part.center, shift, strict=True))
        # 바닥(z 0) 아래는 자른다. 승강 기둥(LiftColumn)은 낮은 rail_z 에서 받침 안·바닥 아래로 들어간다(Simu 9/18).
        low, high = center[2] - part.size[2] / 2.0, center[2] + part.size[2] / 2.0
        if high <= 0.0:
            continue
        low = max(low, 0.0)
        moved.append(C.Box(part.name, (center[0], center[1], (low + high) / 2.0),
                           (part.size[0], part.size[1], high - low)))
    return tuple(scene.obstacles) + tuple(moved)


def rail_moves(name, start, end, tolerance=1e-3):
    """레일 한 번 이동을 단계로 나눈다(실습7-a 재범: 레일이 "최적 위치로 구분지어" 가는 것이 보이게).

    올라갈 때는 z 먼저 → x·y, 내려갈 때는 x·y 먼저 → z. 움직이지 않는 단계는 뺀다.
    """
    start, end = tuple(start), tuple(end)
    if len(end) < 3:
        return [seq.Step(name, None, None, end)]
    lift = (start[0], start[1], end[2])
    travel = (end[0], end[1], start[2])
    order = [(f'{name}_z', lift), (f'{name}_xy', end)] if end[2] > start[2] else \
        [(f'{name}_xy', travel), (f'{name}_z', end)]
    steps, current = [], start
    for phase, point in order:
        if max(abs(a - b) for a, b in zip(point, current, strict=True)) > tolerance:
            steps.append(seq.Step(phase, None, None, point))
            current = point
    return steps


def to_base(point, rail, scene):
    base = C.base_position(rail, scene.base_origin)
    return tuple(p - b for p, b in zip(point, base, strict=True))


#: 잡은 약통을 재지 않을 자기 수납의 장애물 이름 머리. 수납통 벽은 회전 조각의 축 정렬 bbox 라(Simu) 안쪽 원을
#: 파고든다. 약통이 들어가는 것은 치수(`fits`)로 따로 본다. 팔·그리퍼는 이 박스도 모두 잰다.
OWN_TARGET_PREFIXES = {'round': ('RoundBin',), 'module': ('DispenserFront',)}


def fits(cell, target, margin=0.0):
    """약통이 수납에 들어가는 치수인가. round: 지름 < 안지름, module: 단면(x, z) < 구멍 열림."""
    if target.kind == 'round':
        return cell.size[0] + 2 * margin < float(target.data['inner_diameter'])
    opening = target.data['opening']
    return cell.size[0] + 2 * margin < float(opening['x']) and cell.size[2] + 2 * margin < float(opening['z'])


def quick_ik(model, points, rail, scene, seeds, yaw=0.0):
    """앞 몇 개 시드로만 풀어 본다. 레일 후보를 싸게 거르려고다(여유 계산은 비싸다)."""
    orientation = tool_quat(yaw)
    targets = [P.Target(phase, rail, kin.Pose(to_base(p, rail, scene), orientation)) for phase, p in points]
    return any(P.solve_chain(model, targets, seed) is not None for seed in seeds)


def elbow_condition(joints):
    """작업 자세들의 `sin|q3|` 최솟값. 팔꿈치 조건의 **대리값**이다(자코비안 조건수가 아니다).

    팔꿈치 특이점은 완전 신전(q3 → 0)과 완전 접힘(q3 → π) **양쪽**에 있고, 조건은 대략 sin|q3| 에 비례해
    90°에서 가장 좋다. 그래서 |q3| 자체가 아니라 sin 을 본다 — |q3| 로 보면 "많이 접힌 자세" 가 좋아 보이는데
    그쪽도 특이점이다(작전 9/21 정정).
    """
    return min((abs(math.sin(j[2])) for j in joints), default=float('inf'))


def plan_leg(model, points, rail, scene, link_boxes, tcp_offset, seeds, params, carrying, fold, yaw=0.0,
             joint_step=0.03, own_target=None, min_elbow_sin=0.0):
    """한 레일 위치에서 점 목록을 푼다. 관절 경로(접힌 자세 → 점들 → 접힌 자세)의 여유가 가장 큰 해(Selection).

    잡은 약통은 기준이 따로다(`canister_min`). 비교를 한 숫자로 하려고 약통 여유에 두 기준의 차를 더한다.
    """
    orientation = tool_quat(yaw)
    targets = [P.Target(phase, rail, kin.Pose(to_base(p, rail, scene), orientation)) for phase, p in points]

    def clearance_of(path, stop_below=-math.inf):
        # Filter each IK solution before clearance ranking/pruning. Rejecting only
        # the winner would discard valid solutions at the same rail position.
        if min_elbow_sin > 0.0 and elbow_condition(path) < min_elbow_sin:
            return -math.inf, 'elbow condition'
        # 접힌 자세 → 점들 → 접힌 자세. 구간 끝에 접힌 자세로 돌아가 레일을 옮긴다.
        route = [tuple(fold)] + list(path) + [tuple(fold)]
        full = [route[0]]
        for a, b in zip(route, route[1:], strict=False):
            full += seq.interpolate(a, b, joint_step)
        samples = [('x', j, rail, carrying) for j in full]
        everything = obstacles_at(scene, rail)
        shift = params.min_clearance - params.canister_min
        # base_link 은 승강판 위에 붙어 있어 레일 부품과는 재지 않는다. 나머지 링크는 레일 부품도 잰다(관통 방지).
        arm = [b for b in link_boxes if b.link not in ('canister', 'base_link')]
        worst = C.worst_clearance(samples, arm, tcp_offset, everything, scene.base_origin, stop_below)
        worst_value = worst.distance
        if worst_value >= stop_below:
            hit = C.worst_clearance(samples, [b for b in link_boxes if b.link == 'base_link'], tcp_offset,
                                    scene.obstacles, scene.base_origin, stop_below)
            if hit.distance < worst_value:
                worst, worst_value = hit, hit.distance
        if carrying and worst_value >= stop_below:
            skip = OWN_TARGET_PREFIXES.get(own_target, ())
            boxes = [o for o in everything if not o.name.startswith(skip)]
            hit = C.worst_clearance(samples, [b for b in link_boxes if b.link == 'canister'], tcp_offset, boxes,
                                    scene.base_origin, stop_below - shift)
            if hit.distance + shift < worst_value:
                worst, worst_value = hit, hit.distance + shift
        z = worst.point[2] if worst.point is not None else float('nan')
        return worst_value, f'{worst.link}-{worst.box} {worst.distance:.3f} z {z:.2f}'

    return P.select(model, targets, seeds, clearance_of, params.min_clearance)


def plan_refill(model, scene, cell, link_boxes, tcp_offset, seeds, params, fold, home_rail=(0.0, 0.0, 0.0),
                place_cache=None, rail_select=FIRST_FEASIBLE):
    """칸 하나 → (Step 목록, 설명, 최소 여유 m). 못 풀면 (None, 이유, None).

    fold 는 레일을 움직여도 되는 접힌 자세(보통 홈)다. 각 구간 끝에 fold 로 돌아와 레일을 옮긴다.
    레일 자세는 구간(잡기·넣기)마다 한 번 정한다: 어깨 → 목표 거리가 짧은 후보부터 시험해 처음 통과한 것.
    한 레일 자세 안에서는 IK 시드 해 중 여유가 가장 큰 것을 쓴다.
    넣기 구간은 칸 위치와 무관하다(약통 종류·크기·잡은 점만 본다). place_cache(dict)를 주면 종류마다 한 번만 푼다.
    """
    if rail_select not in RAIL_SELECT:
        # 모르는 값을 새 모드로 취급하지 않는다. 오타가 조용히 동작을 바꾸면 안 된다.
        raise SceneError(f'rail_select 는 {RAIL_SELECT} 중에서다({rail_select!r})')
    target = scene.targets.get(cell.kind)
    if target is None:
        return None, f'{cell.kind} 수납 위치가 없다', None
    if not fits(cell, target):
        return None, f'{cell.cell_id}: 약통 치수 {cell.size} 가 {target.kind} 수납에 안 들어간다', None
    pick, grip = pick_points(cell, params)

    preferred = rail_select == PREFERRED_FIRST
    elbow_min = params.min_elbow_sin if preferred else 0.0
    offsets = params.rail_pick_extra + params.rail_pick if preferred else params.rail_pick
    ordered = rail_candidates(grip, 0.0, scene, params, offsets, by_reach=not preferred)
    tried = 0
    failure = ''
    legs = None
    for reach, rail in ordered:
        if tried >= params.max_rail_tries:
            break
        if preferred:
            outbound_steps, outbound, reason = checked_rail_moves(
                'rail_to_shelf', home_rail, rail, scene, link_boxes, tcp_offset, params, fold, carrying=False)
            if outbound < params.min_clearance:
                failure = f'레일 출발 경로: {reason}'
                continue
        if not quick_ik(model, pick, rail, scene, seeds[:4]):
            continue
        tried += 1
        selection = plan_leg(model, pick, rail, scene, link_boxes, tcp_offset, seeds, params, False, fold,
                             min_elbow_sin=elbow_min)
        if not selection.candidate:
            continue
        picked = (rail, selection.candidate, pick, reach)
        placed, failure, transfer, transfer_steps, return_steps = _place_leg(
            model, scene, cell, target, grip, link_boxes, tcp_offset,
            seeds, params, fold, home_rail, rail, place_cache, rail_select)
        if placed is not None:
            legs = (picked, placed)
            rail_min = min(outbound, transfer) if preferred else math.inf
            break
        if not preferred:
            return None, f'{cell.cell_id}: {failure}', None
    if legs is None:
        return None, (f'{cell.cell_id}: 잡기 — 레일 후보 {tried}/{len(ordered)}곳'
                      f'(한계 {params.rail_limit_margin} m 안쪽·도달 {params.min_reach} m 이상)'
                      '에서 풀리지 않거나 여유 부족' + (f'; {failure}' if failure else '')), None
    (pick_rail, pick_sol, pick_pts, pick_reach), (place_rail, place_sol, place_pts, place_reach) = legs
    # 레일은 구간마다 한 번 정한 자세로 간 뒤 그 구간(잡기·넣기)이 끝날 때까지 움직이지 않는다.
    steps = list(outbound_steps) if preferred else rail_moves('rail_to_shelf', home_rail, pick_rail)
    steps += [seq.Step(phase, joints, None) for (phase, _), joints in zip(pick_pts[:2], pick_sol.joints[:2],
                                                                          strict=True)]
    steps.append(seq.Step('grasp', None, seq.GRIP_CLOSE))
    steps += [seq.Step(phase, joints, None) for (phase, _), joints in zip(pick_pts[2:], pick_sol.joints[2:],
                                                                          strict=True)]
    steps.append(seq.Step('fold', tuple(fold), None))
    steps += transfer_steps if preferred else rail_moves('rail_to_inlet', pick_rail, place_rail)
    place_named = place_pts[:-1]
    steps += [seq.Step(phase, joints, None) for (phase, _), joints in zip(place_named, place_sol.joints[:-1],
                                                                          strict=True)]
    steps.append(seq.Step('release', None, seq.GRIP_OPEN))
    steps.append(seq.Step('retreat', place_sol.joints[-1], None))
    steps.append(seq.Step('fold_back', tuple(fold), None))
    if preferred:
        steps += return_steps
    clearance = min(pick_sol.clearance, place_sol.clearance, rail_min)
    rails = (f'레일 잡기 {tuple(round(v, 3) for v in pick_rail)}(도달 {pick_reach:.3f}, 한계까지 '
             f'{rail_margin(pick_rail, scene):.3f}) 넣기 {tuple(round(v, 3) for v in place_rail)}'
             f'(도달 {place_reach:.3f}, '
             f'한계까지 {rail_margin(place_rail, scene):.3f})')
    if preferred:
        rails += f', 레일 이동 여유 {rail_min:.3f} m'
    return steps, f'여유 {clearance:.3f} m (잡기 {pick_sol.worst}, 넣기 {place_sol.worst}), {rails}', clearance


def _place_leg(model, scene, cell, target, grip, link_boxes, tcp_offset, seeds, params, fold,
               home_rail, pick_rail, place_cache, rail_select):
    """Cache a place leg only for the transfer origin that was checked."""
    preferred = rail_select == PREFERRED_FIRST
    offset = tuple(round(g - c, 6) for g, c in zip(grip, cell.center, strict=True))
    key = (target.kind, cell.kind, cell.size, offset, rail_select)
    if preferred:
        key += (tuple(pick_rail), tuple(home_rail))
    if place_cache is not None and key in place_cache:
        return place_cache[key]
    round_offsets = params.rail_round_extra + params.rail_round if preferred else params.rail_round
    module_offsets = params.rail_module_extra + params.rail_module if preferred else params.rail_module
    if target.kind == 'round':
        by_yaw = {}
        for yaw, candidate in round_offsets:
            by_yaw.setdefault(yaw, []).append(candidate)
    else:
        by_yaw = {0.0: list(module_offsets)}
    options = []
    for yaw, offsets in by_yaw.items():
        place, back = place_points(cell, target, grip, params, yaw)
        points = place + [('retreat', back)]
        options += [(reach, index, yaw, rail, points) for index, (reach, rail) in
                    enumerate(rail_candidates(place[-1][1], yaw, scene, params, offsets, not preferred))]
    if not preferred:
        options.sort(key=lambda o: (o[0], o[1]))
    tried = 0
    result = None
    reason = ''
    for reach, _, yaw, rail, points in options:
        if tried >= params.max_rail_tries:
            break
        transfer = math.inf
        transfer_steps, return_steps = [], []
        if preferred:
            transfer_steps, loaded, reason = checked_rail_moves(
                'rail_to_inlet', pick_rail, rail, scene, link_boxes, tcp_offset, params, fold, carrying=True)
            if loaded < params.min_clearance:
                continue
            return_steps, unloaded, reason = checked_rail_moves(
                'rail_home', rail, home_rail, scene, link_boxes, tcp_offset, params, fold, carrying=False)
            if unloaded < params.min_clearance:
                continue
            transfer = min(loaded, unloaded)
        # The fixed-rail arm solution is independent of the pickup origin. Reuse
        # that expensive IK result, but never reuse an unchecked transfer route.
        solution_key = ('place_solution', *key[:5], rail, yaw)
        selection = place_cache.get(solution_key) if preferred and place_cache is not None else None
        if selection is None:
            if not quick_ik(model, points, rail, scene, seeds[:4], yaw):
                continue
            selection = plan_leg(model, points, rail, scene, link_boxes, tcp_offset, seeds, params, True, fold, yaw,
                                 own_target=target.kind, min_elbow_sin=params.min_elbow_sin if preferred else 0.0)
            if preferred and place_cache is not None:
                place_cache[solution_key] = selection
        tried += 1
        if selection.candidate:
            result = ((rail, selection.candidate, points, reach), '', transfer, transfer_steps, return_steps)
            break
    if result is None:
        why = f'넣기({target.kind}) — 후보 {tried}/{len(options)}곳에서 풀리지 않거나 여유 부족'
        if preferred and reason:
            why += f'; 레일 경로: {reason}'
        result = (None, why, None, [], [])
    if place_cache is not None:
        place_cache[key] = result
    return result


def checked_rail_moves(name, start, end, scene, link_boxes, tcp_offset, params, fold, carrying):
    """Try the direct route, then bounded raised routes; check every segment."""
    direct = rail_moves(name, start, end)
    routes = [direct]
    height = max(start[2], end[2])
    ceiling = scene.rail_limits[2][1] - params.rail_limit_margin
    while height < ceiling - 1e-9:
        height = min(height + 0.10, ceiling)
        raised_start, raised_end = (*start[:2], height), (*end[:2], height)
        routes.append(rail_moves(f'{name}_raise', start, raised_start)
                      + rail_moves(f'{name}_cross', raised_start, raised_end)
                      + rail_moves(f'{name}_lower', raised_end, end))
    for steps in routes:
        value, reason = rail_clearance(start, end, scene, link_boxes, tcp_offset, params, fold, carrying,
                                       steps=steps)
        if value >= params.min_clearance:
            return steps, value, reason
    return [], value, reason


def rail_clearance(start, end, scene, link_boxes, tcp_offset, params, fold, carrying, rail_step=0.01, steps=None):
    """Check the folded arm/payload along the executor's Z/XY segments (metres).

    Rail parts move at every sample. Payload contact exemptions used for insertion
    do not apply in transit: require at least the arm clearance for the payload.
    This is sampled model clearance, not a physical safety certificate.
    """
    points = [tuple(start)]
    current = tuple(start)
    for step in rail_moves('transfer', start, end) if steps is None else steps:
        points.extend(seq.interpolate(current, step.rail, rail_step))
        current = step.rail
    arm = [box for box in link_boxes if box.link not in ('canister', 'base_link')]
    base = [box for box in link_boxes if box.link == 'base_link']
    payload = [box for box in link_boxes if box.link == 'canister'] if carrying else []
    worst, reason = math.inf, ''
    shift = params.min_clearance - max(params.canister_min, params.min_clearance)
    for rail in points:
        sample = [('transfer', fold, rail, carrying)]
        obstacles = obstacles_at(scene, rail)
        for boxes, environment, adjustment in ((arm, obstacles, 0.0), (base, scene.obstacles, 0.0),
                                                (payload, obstacles, shift)):
            hit = C.worst_clearance(sample, boxes, tcp_offset, environment, scene.base_origin,
                                    params.min_clearance - adjustment)
            value = hit.distance + adjustment
            if value < worst:
                worst = value
                reason = f'{hit.link}-{hit.box} {hit.distance:.3f} m at {tuple(round(v, 3) for v in rail)}'
            if worst < params.min_clearance:
                return worst, reason
    return worst, reason


def scene_signature(scene):
    """계획에 영향을 주는 장면 부분(장애물·수납·레일). 칸의 있음/없음은 들어가지 않는다(재배치는 같은 자리다)."""
    return repr((scene.obstacles, sorted((k, v.kind, v.point, v.axis, sorted(v.data.items(), key=str))
                                          for k, v in scene.targets.items()),
                 scene.rail_names, scene.rail_limits, scene.base_origin, scene.rail_parts))


def cell_key(cell):
    """칸 계획이 달라지는 칸 값(종류·중심·크기)."""
    return (cell.kind, cell.center, cell.size)


PlanEntry = namedtuple('PlanEntry', ('steps', 'why', 'clearance', 'seconds'))


class PlanCache:
    """칸별 계획 캐시. 장면(장애물·수납·레일)이 바뀌면 전부 버리고, 칸의 종류·중심·크기가 바뀌면 그 칸만 다시 푼다.

    스레드 잠금은 부르는 쪽이 한다. 못 푼 칸(steps None)도 이유와 함께 넣어 두어 다시 풀지 않는다.
    레일 고르기 방식(`rail_select`)이 다르면 같은 장면이라도 다른 후보를 고르므로 **캐시가 그 값을 들고 있다.**
    `scene_signature` 에는 넣지 않는다 — 그 문자열은 guarded 경로와 `steps.scene_signature` 로도 흘러가므로
    장면만 말해야 한다(작전 9/21).
    """

    def __init__(self, rail_select=FIRST_FEASIBLE):
        self._signature = None
        self._select = rail_select
        self._plans = {}
        self.legs = {}          # 넣기 구간 캐시(plan_refill 의 place_cache). 장면이 바뀌면 같이 비운다

    @property
    def rail_select(self):
        return self._select

    def refresh(self, scene, rail_select=None):
        """장면이나 고르기 방식이 바뀌었으면 비운다. 비웠으면 True."""
        signature = scene_signature(scene)
        select = self._select if rail_select is None else rail_select
        if signature == self._signature and select == self._select:
            return False
        self._select = select
        self._signature = signature
        self._plans = {}
        self.legs = {}
        return True

    def get(self, scene, cell):
        entry = self._plans.get(cell.cell_id)
        if entry is None or entry[0] != cell_key(cell) or scene_signature(scene) != self._signature:
            return None
        return entry[1]

    def put(self, scene, cell, entry):
        if scene_signature(scene) == self._signature:
            self._plans[cell.cell_id] = (cell_key(cell), entry)

    def load_plans(self, scene, plans):
        """파일에서 읽은 {칸: (cell_key, PlanEntry)} 를 넣는다. (넣은 수, 칸 수).

        지금 장면의 칸과 `cell_key` 가 같은 것만 넣는다 — 파일 키가 같아도 여기서 한 번 더 본다.
        이미 들어 있는 칸은 건드리지 않는다.
        """
        loaded = 0
        for cell in scene.cells:
            found = (plans or {}).get(cell.cell_id)
            if found is None or cell.cell_id in self._plans or found[0] != cell_key(cell):
                continue
            self.put(scene, cell, found[1])
            loaded += self.get(scene, cell) is not None
        return loaded, len(scene.cells)

    def plans(self):
        """저장용 사본 {칸: (cell_key, PlanEntry)}."""
        return dict(self._plans)

    def missing(self, scene):
        return [c for c in scene.cells if self.get(scene, c) is None]

    def entries(self):
        return {cid: entry for cid, (_, entry) in self._plans.items()}


#: v2 REFILL_DONE.detail 의 필드(작전 9/18 결정, 백엔드 #176 이 같은 이름으로 읽는다). 바꾸면 작전·백엔드에 먼저 알린다.
DETAIL_FIELDS = ('item', 'slot', 'kind', 'cell', 'target', 'seed', 'draw', 'clearance')


def refill_done_detail(item, slot, kind, cell, target, seed, draw, clearance, lot=''):
    """장면 v2 의 REFILL_DONE.detail: compact JSON 한 줄. 계약 2.6절: detail 은 판정에 쓰지 않는 메모다.

    slot 은 'a'·'b', target 은 'round'·'module', clearance 는 계획의 최소 여유(m, 소수 넷째 자리). lot 은 있을 때만.
    ROS 없이 import 된다(백엔드 왕복 테스트용).
    """
    detail = {'item': str(item), 'slot': str(slot), 'kind': str(kind), 'cell': str(cell), 'target': str(target),
              'seed': int(seed), 'draw': int(draw), 'clearance': round(float(clearance), 4)}
    if lot:
        detail['lot'] = str(lot)
    return json.dumps(detail, ensure_ascii=False, separators=(',', ':'))
