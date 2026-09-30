"""해제 뒤 칸 안착 확인의 순수 판정. ROS 를 import 하지 않는다. 계약 v1 11.4절(제안) A1 최소안.

arm 이 goal 의 놓을 곳 하나(`deck_slot_<N>` 또는 보관함)만 판정한다.
- 놓을 곳 프레임의 원점은 **물체가 놓이는 윗면의 중심**이다(재범 결정 23번, 계약 3절 #284). z 가 위다.
- 칸 상자는 그 프레임에서 x ∈ (−sx/2, sx/2), y ∈ (−sy/2, sy/2), z ∈ [0, sz] 이다.
  가장자리에 걸친 검출은 안착으로 보지 않는다
  (확인 쪽 fail-closed: 벽 위에 걸친 봉투를 "칸 안"이라고 하지 않는다).
- 쓰는 검출: 해제 명령 뒤 stamp, QR == goal `order_id`, 위치를 이미지 stamp 의 TF 로 놓을 곳 프레임에 옮긴 것.
- 상자 치수는 기본값이 없다. 미설정이면 확인할 수 없다.
"""

import math
from collections import namedtuple

Candidate = namedtuple('Candidate', ('order_id', 'stamp_s', 'point'))   # point = 놓을 곳 프레임의 (x, y, z) 또는 None


def box_problem(box):
    """상자 (sx, sy, sz) 를 쓸 수 없으면 이유, 쓸 수 있으면 ''."""
    if box is None:
        return '칸 상자 치수 미설정'
    try:
        values = [float(value) for value in box]
    except (TypeError, ValueError):
        return '칸 상자 치수가 숫자가 아니다'
    if len(values) != 3 or not all(math.isfinite(v) and v > 0.0 for v in values):
        return '칸 상자 치수(3개, 양수) 미설정'
    return ''


def inside_box(point, box):
    """놓을 곳 프레임의 점이 칸 상자 안인가. 가장자리는 밖이다."""
    if point is None or not all(math.isfinite(float(v)) for v in point):
        return False
    x, y, z = (float(v) for v in point)
    sx, sy, sz = (float(v) for v in box)
    return abs(x) < sx / 2.0 and abs(y) < sy / 2.0 and 0.0 <= z <= sz


def placement_confirmed(candidates, order_id, released_at_s, box):
    """(확인했나, 이유). 해제 뒤 stamp·같은 주문·칸 상자 안인 검출이 하나라도 있으면 확인이다."""
    problem = box_problem(box)
    if problem:
        return False, problem
    if not order_id:
        return False, 'goal order_id 가 비었다'
    seen = {'old': 0, 'other_order': 0, 'no_pose': 0, 'outside': 0}
    for candidate in candidates:
        if candidate.stamp_s is None or candidate.stamp_s < released_at_s:
            seen['old'] += 1
        elif candidate.order_id != order_id:
            seen['other_order'] += 1
        elif candidate.point is None:
            seen['no_pose'] += 1
        elif not inside_box(candidate.point, box):
            seen['outside'] += 1
        else:
            return True, ''
    counted = ', '.join(f'{key}={value}' for key, value in seen.items() if value)
    return False, f'칸 안에서 {order_id} 를 못 봤다({counted or "검출 없음"})'


def dependency_problem(enabled, gripper_observation):
    """안착 확인은 해제 확인(GripperState)이 먼저다. 안착 확인만 켜고 state 를 안 켜면 기동을 거부한다."""
    if enabled and gripper_observation != 'state':
        return 'placement_check_enabled 는 gripper_observation=state 가 필요하다(해제 확인이 먼저다, 계약 11.4·11.6)'
    return ''


# ---- 한 정거장에 봉투 여럿 (재범 9/25: 병실 묶음 → 그 방 테이블 하나에 n 봉투) --------------------------

#: 같은 테이블에 놓는 봉투 사이 간격(m, 놓을 곳 프레임 x). 봉투 긴 변 0.10 + 틈 0.05.
STOP_SLOT_SPACING = 0.15


def stop_slot_offset(index, spacing=STOP_SLOT_SPACING):
    """정거장 안 `index` 번째 봉투의 x 비킴(m): 0, +s, −s, +2s, −2s … 첫 봉투는 가운데(예전과 같다)."""
    if index <= 0:
        return 0.0
    step = (index + 1) // 2
    return spacing * step * (1.0 if index % 2 else -1.0)


class StopSlots:
    """한 정거장(같은 보관함 프레임)에서 주문마다 칸 번호. 같은 주문의 재시도는 같은 칸이다.

    상판 칸(`deck_slot_*`)에 싣는 goal 이 오면 새 트립이라 비운다. 다른 보관함 프레임이 오면 새 정거장이라 비운다.
    침상은 정거장마다 봉투 하나라 늘 0 번(가운데) — 동작이 예전과 같다.
    """

    def __init__(self):
        self.frame = None
        self.orders = []

    def index_for(self, frame, order_id, deck):
        if deck:
            self.frame, self.orders = None, []
            return 0
        if frame != self.frame:
            self.frame, self.orders = frame, []
        if order_id not in self.orders:
            self.orders.append(order_id)
        return self.orders.index(order_id)
