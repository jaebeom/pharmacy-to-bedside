"""문·통로를 로봇이 지나갈 수 있는가. ROS 를 import 하지 않는다.

`mock-hospital-world-integration-plan.md` 8절 "문 통과"의 식을 그대로 옮긴다.
문 법선(지나가는 방향)에 대해 yaw 만큼 틀어진 직사각형 footprint(폭 W, 길이 L)가 차지하는 폭은
`W·|cos(yaw)| + L·|sin(yaw)|` 이고, 여기에 양측 margin 과 오차 예산을 더한 값이 문의 유효 폭 이하여야 한다.

    필요한 폭 = W·|cos(yaw)| + L·|sin(yaw)| + 2 × margin + error_budget

- 모든 치수는 입력이다. 기본값이 없다. 하나라도 없거나(None) 유한하지 않거나 0 이하이면 `UNKNOWN` 이다.
  yaw 는 유한하기만 하면 된다(0 도 유효).
- **경계값은 막는다(fail-closed).** 필요한 폭이 문 폭과 같으면 `BLOCKED` 다. 여유가 0 인 통과를 허가하지 않는다.
- 원형 footprint(반지름 r)는 yaw 와 상관없이 `2r` 을 차지한다.
- inflation 은 입력으로 받지 않는다. inflation 은 costmap 의 비용장 조정이지 형상이 아니다(계획 8절).
- 적재물·팔 수납 상태에 따라 footprint 가 바뀌면 부르는 쪽이 다른 footprint 를 넘긴다. 이 모듈은 상태를 모른다.

연결하는 곳은 아직 없다. topology 스키마가 정해진 뒤 edge 의 문 폭 검사에 쓴다.
"""

import math
from collections import namedtuple

PASSABLE = 'passable'
BLOCKED = 'blocked'
UNKNOWN = 'unknown'

#: 직사각형. `width` 는 옆 폭(yaw 0 에서 문 폭 방향), `length` 는 앞뒤 길이. m.
Rectangle = namedtuple('Rectangle', ('width', 'length'))
#: 원. `radius` m.
Circle = namedtuple('Circle', ('radius',))

#: `required` 는 필요한 폭(m), `shortfall` 은 모자란 폭(m, 0 이상). UNKNOWN 이면 둘 다 None 이고 `reason` 이 있다.
Passage = namedtuple('Passage', ('verdict', 'required', 'shortfall', 'reason'))


def _positive(value):
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value) and value > 0.0)


def _footprint_reason(footprint):
    if isinstance(footprint, Rectangle):
        if not (_positive(footprint.width) and _positive(footprint.length)):
            return f'footprint 치수가 양의 유한값이 아니다: {footprint!r}'
        return None
    if isinstance(footprint, Circle):
        if not _positive(footprint.radius):
            return f'footprint 반지름이 양의 유한값이 아니다: {footprint!r}'
        return None
    return f'footprint 는 Rectangle 이나 Circle 이어야 한다: {footprint!r}'


def swept_width(footprint, yaw):
    """문 폭 방향으로 footprint 가 차지하는 폭(m). 입력 검사는 하지 않는다."""
    if isinstance(footprint, Circle):
        return 2.0 * footprint.radius
    return footprint.width * abs(math.cos(yaw)) + footprint.length * abs(math.sin(yaw))


def check_passage(footprint, yaw, margin, error_budget, door_width):
    """`Passage` 를 돌려준다. `margin` 은 한쪽 여유라 두 번 더한다."""
    reason = _footprint_reason(footprint)
    if reason is None and not (isinstance(yaw, (int, float)) and not isinstance(yaw, bool)
                               and math.isfinite(yaw)):
        reason = f'yaw 가 유한하지 않다: {yaw!r}'
    for name, value in (('margin', margin), ('error_budget', error_budget),
                        ('door_width', door_width)):
        if reason is None and not _positive(value):
            reason = f'{name} 이 양의 유한값이 아니다: {value!r}'
    if reason is not None:
        return Passage(UNKNOWN, None, None, reason)

    required = swept_width(footprint, yaw) + 2.0 * margin + error_budget
    shortfall = max(0.0, required - door_width)
    verdict = PASSABLE if required < door_width else BLOCKED
    return Passage(verdict, required, shortfall, None)
