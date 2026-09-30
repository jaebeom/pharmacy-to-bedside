"""zones.yaml 이 주행을 시작해도 되는 상태인가. ROS 를 import 하지 않는다. 계약 v1 2.2절·3절.

`zones.py` 는 형식만 본다. 공차 0 이나 NaN 도 숫자라서 통과하고, fleet 은 그런 zone 으로 가는 goal 도
받아서 주행한 뒤에야 `out_of_tolerance` 로 실패한다. 이 모듈은 실행 전에 막을 이유를 모은다.

- 공차(`tol_xy`, `tol_yaw`)는 양수·유한이어야 한다. 0 은 아직 안 정한 값이다(`docking.docked`).
- 좌표는 유한이어야 한다. **좌표 0 은 거부하지 않는다.** 원점도 유효한 자리다.
  좌표가 채워졌는지는 이 파일만으로 알 수 없어서 `unverified` 로 따로 보고한다(manifest 가 필요하다).
- 필수 zone 은 인자로 받는다. 기본값은 잠정이다.

fleet 에는 아직 연결하지 않았다. 판정만 있다.
"""

import math
from collections import namedtuple

#: 잠정. 계약 v1 의 단일 AMR(`amr_1`) 범위에서 조제실 구간이 쓰는 zone 이다.
DEFAULT_REQUIRED_ZONES = ('load', 'dock_1')
#: 계약 3절: `map` 은 유일한 world 프레임이다.
REQUIRED_FRAME = 'map'
#: 좌표가 채워졌는지는 revision·manifest 가 있어야 판별된다. 0 을 미설정으로 추측하지 않는다.
COORDINATES_UNVERIFIED = '좌표 설정 여부는 판별 불가 — manifest 필요'

#: `blocking` 이 비어야 준비된 것이다. `unverified` 는 이 검사로 확인하지 못한 항목이다.
Readiness = namedtuple('Readiness', ('blocking', 'unverified'))


def _finite(value):
    return math.isfinite(value)


def _pose_reasons(pose, where):
    return [f'{where}.{name} 이 유한하지 않다: {value!r}'
            for name, value in pose._asdict().items() if not _finite(value)]


def zone_reasons(zone):
    """zone 하나가 주행·도킹 판정에 준비됐는가. 막는 이유 목록(빈 목록 = 준비). DockingState 도 이 함수를 쓴다."""
    where = f'zones.{zone.zone_id}'
    reasons = [f'{where}.{name} 이 유한하지 않다: {value!r}'
               for name, value in (('x', zone.x), ('y', zone.y), ('yaw', zone.yaw))
               if not _finite(value)]
    for name, value in (('tol_xy', zone.tol_xy), ('tol_yaw', zone.tol_yaw)):
        if not _finite(value) or value <= 0.0:
            reasons.append(f'{where}.{name} 이 양의 유한값이 아니다: {value!r}')
    for name in ('cabinet', 'tag'):
        pose = getattr(zone, name)
        if pose is not None:
            reasons.extend(_pose_reasons(pose, f'{where}.{name}'))
    return reasons


def check_zones(zones, required=DEFAULT_REQUIRED_ZONES):
    """`zones.parse_zones` 결과를 보고 `Readiness` 를 돌려준다.

    `required` 는 반드시 있어야 하는 zone ID 들이다. 빈 목록이면 필수 검사를 하지 않는다.
    """
    blocking = []
    if zones.frame != REQUIRED_FRAME:
        blocking.append(f'frame 이 {REQUIRED_FRAME} 가 아니다: {zones.frame!r}')
    for zone_id in required:
        if zone_id not in zones.zones:
            blocking.append(f'필수 zone {zone_id} 가 없다')
    for zone_id in sorted(zones.zones):
        blocking.extend(zone_reasons(zones.zones[zone_id]))
    for name in sorted(zones.pharmacy):
        blocking.extend(_pose_reasons(zones.pharmacy[name], f'pharmacy.{name}'))
    return Readiness(blocking=blocking, unverified=[COORDINATES_UNVERIFIED])


def is_ready(zones, required=DEFAULT_REQUIRED_ZONES):
    """막을 이유가 없는가. `unverified` 는 보지 않는다."""
    return not check_zones(zones, required).blocking
