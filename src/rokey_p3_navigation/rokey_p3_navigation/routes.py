"""zone 사이의 고정 waypoint 목록을 읽는다. ROS 를 import 하지 않는다.

좌표를 코드에 박지 않으려고 둔 파일이다. 형식은 `zones.yaml` 과 같은 규칙을 따른다.

- 프레임은 `map` 하나다(계약 3절).
- zone ID 는 `zones.yaml` 에 있는 것만 쓴다. 없는 ID 는 거부한다.
- waypoint 는 `map` 기준 `(x, y)` 다. yaw 는 두지 않는다. 중간에서는 yaw 를 바꾸지 않기 때문이다.
- **월드마다 다른 파일이다.** 빈월드 값은 임시이고 심월드에서는 값만 바뀐다. 파일은 장면 매개변수에서 만든다.

```yaml
schema_version: 1
frame: map
routes:
  - {from: dock_1, to: load, waypoints: [[1.0, 0.0], [2.5, 0.0]]}
```

waypoint 가 빈 목록이면 "곧장 간다"는 뜻이고, 그 쌍을 적지 않은 것과 같다.
없는 쌍은 `waypoints()` 가 빈 튜플을 돌려준다.
"""

import math
from collections import namedtuple

import yaml

SCHEMA_VERSION = 1
REQUIRED_FRAME = 'map'

#: `pairs` 는 {(from, to): ((x, y), ...)}.
Routes = namedtuple('Routes', ('frame', 'pairs'))


class RoutesError(ValueError):
    """routes 파일을 받아들일 수 없다."""


def _point(value, where):
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise RoutesError(f'{where}: waypoint 는 [x, y] 여야 한다: {value!r}')
    for item in value:
        if isinstance(item, bool) or not isinstance(item, (int, float)) or not math.isfinite(item):
            raise RoutesError(f'{where}: 좌표가 유한한 숫자가 아니다: {value!r}')
    return (float(value[0]), float(value[1]))


def parse_routes(document, zones):
    """읽어 들인 매핑을 검사해 `Routes` 로 만든다. `zones` 는 `zones.parse_zones` 결과다."""
    if not isinstance(document, dict):
        raise RoutesError('routes 파일이 맵이 아니다')
    if document.get('schema_version') != SCHEMA_VERSION:
        raise RoutesError(f'schema_version 이 {SCHEMA_VERSION} 가 아니다: '
                          f'{document.get("schema_version")!r}')
    frame = document.get('frame')
    if frame != REQUIRED_FRAME:
        raise RoutesError(f'frame 이 {REQUIRED_FRAME} 가 아니다: {frame!r}')
    rows = document.get('routes') or []
    if not isinstance(rows, list):
        raise RoutesError('routes 는 목록이어야 한다')

    pairs = {}
    for index, row in enumerate(rows):
        where = f'routes[{index}]'
        if not isinstance(row, dict):
            raise RoutesError(f'{where}: 맵이어야 한다')
        source, target = row.get('from'), row.get('to')
        for zone_id in (source, target):
            if zone_id not in zones.zones:
                raise RoutesError(f'{where}: zones.yaml 에 없는 zone {zone_id!r}')
        if source == target:
            raise RoutesError(f'{where}: from 과 to 가 같다 ({source})')
        if (source, target) in pairs:
            raise RoutesError(f'{where}: 같은 쌍이 두 번 있다 ({source} → {target})')
        points = row.get('waypoints')
        if not isinstance(points, list):
            raise RoutesError(f'{where}: waypoints 는 목록이어야 한다')
        pairs[(source, target)] = tuple(_point(point, where) for point in points)
    return Routes(frame=frame, pairs=pairs)


def load_routes(path, zones):
    """routes 파일을 읽어 `Routes` 로 만든다."""
    with open(path, encoding='utf-8') as handle:
        return parse_routes(yaml.safe_load(handle), zones)


def waypoints(routes, source, target):
    """`source` → `target` 의 waypoint. 없으면 빈 튜플(곧장 간다)."""
    if routes is None:
        return ()
    return routes.pairs.get((source, target), ())


def staging_point(routes, source, target):
    """Nav2 로 먼저 보낼 **접근점** = `source` → `target` 경로의 마지막 waypoint. 없으면 None.

    병원 경로표(`routes.hospital.yaml`)는 마지막 waypoint 를 정차 자리 앞 **제자리 회전이 되는 트인 점**으로
    만든다(sim `hospital_nav.approach_point`). `nav2_final_approach` 가 켜지면 fleet 는 Nav2 로 그 점까지 가서
    yaw 를 맞추고, 고정물 옆 0.05 m 에 서는 정차 자리까지의 마지막 구간은 waypoint 추종기로 붙는다
    (9/23 병원 L3: Nav2 footprint 1.10 × 0.90 로는 그 정차 자리에 들어갈 궤적이 없어 0.56 m 앞에서 섰다).
    """
    path = waypoints(routes, source, target)
    return path[-1] if path else None


#: 떠날 때 먼저 접근점으로 물러나는 zone 종류. 병상 정차 자리는 협탁 옆 0.05 m 라 어느 쪽으로 떠나도 스친다.
#: 도크(9/25 벽 앞): 몸체 중심↔벽 0.566 m 가 회전 반경(받침 포함) 0.638 보다 작다 — 도크에서 제자리로 돌면 모듈이나
#: 벽에 닿는다. 회차77(6812ee5, #240 5820319699): dock_1 → load 첫 회전에서 ArmRiser ↔ SM_SideTable_02a_74 접촉.
DEPART_BY_SLIDE_KINDS = ('bed', 'dock')
#: 물러나는 길의 상한(m). 병원 접근점은 정차 자리에서 0.3–0.5 m 다. 먼 점으로 방향 고정 옆걸음을 하지 않는다.
DEPART_MAX_M = 1.0


def departure_point(routes, here, target, pose, near):
    """`here` 정차 자리에서 `target` 으로 떠나기 전에 **방향 고정 옆걸음으로 물러날 점**. 필요 없으면 None.

    도착의 거울이다. 들어올 때 접근점에서 돌고 옆걸음으로 들어왔으니(`staging_point`), 나갈 때도 같은 길로
    접근점까지 물러난 뒤 Nav2 에 넘긴다. 9/24 50b658a 10건: bed_b1 배달 14 s 뒤 bed_b2 로 떠나는 첫 움직임에서
    몸체가 D5 협탁 모서리에 닿았다(touch 2) — 정차 자리는 협탁과 x 로 5.5 cm 이고 몸체가 협탁 y 범위와 겹친다.

    `here` 는 `zones.Zone`, `pose` 는 지금 `(x, y, yaw)`. 정차 자리에서 `near` 안에 있을 때만이다 — 다른 데서
    끝난 뒤(실패·리셋)에는 물러날 길을 모른다. 접근점은 `target → here` 경로의 마지막 waypoint 다.
    """
    if routes is None or here is None or pose is None or here.kind not in DEPART_BY_SLIDE_KINDS:
        return None
    if here.zone_id == target or math.hypot(pose[0] - here.x, pose[1] - here.y) > near:
        return None
    point = staging_point(routes, target, here.zone_id)
    if point is None or math.hypot(point[0] - here.x, point[1] - here.y) > DEPART_MAX_M:
        return None
    return point


def has_pair(routes, source, target):
    """그 쌍이 **표에 적혀 있는가**. 빈 목록과 쌍 없음을 가르는 자리다.

    `waypoints()` 는 둘 다 빈 튜플을 돌려준다 — 가는 방법이 같기 때문이다. 그러나 뜻이 다르다.
    빈 목록은 "곧장 가도 된다고 따져 봤다" 이고, 쌍 없음은 **"아무도 안 따져 봤다"** 다.
    부르는 쪽은 뒤쪽을 조용히 넘기면 안 된다(시뮬 9/21: 쌍 9개가 빠져 병동까지 대각선이 될 뻔했다).
    """
    return routes is not None and (source, target) in routes.pairs
