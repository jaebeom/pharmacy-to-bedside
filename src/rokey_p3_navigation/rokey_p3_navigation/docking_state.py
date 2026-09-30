"""`/amr_1/base/docked`(`DockingState`) 판정. ROS 를 import 하지 않는다. 계약 v1 11.6.

뜻은 "마지막으로 수락한 GoToZone 의 목표 zone 의 `tol_xy`·`tol_yaw` 안에 있음"이다.
`base/stopped` 의 뜻은 바꾸지 않는다.
정지 여부는 이 판정에 들어가지 않는다. 팔은 `base/stopped` 와 이것을 함께 본다.

판정 순서(앞의 것이 이긴다):
1. 첫 `RESET_DONE` 전(epoch 모름) → UNKNOWN
2. GoToZone goal 활성(주행 중) → NOT_DOCKED
3. 목표 zone 없음(수락한 goal 이 없거나 `RESET_DONE` 으로 비움) → UNKNOWN
4. zone 이 readiness 기준으로 준비되지 않음(`readiness.zone_reasons` — fleet 과 같은 함수) → UNKNOWN
5. `map`→`base_link` 자세 없음(TF 조회 실패) → UNKNOWN
6. odom 이 `odom_timeout_s`(wall) 넘게 없음 → UNKNOWN
7. AMCL 이 오래됨. 문턱(`amcl_max_age_s`)은 L3 측정 뒤 정한다.
   문턱이 양의 유한값이 아니면(미정) 판정할 수 없으므로 UNKNOWN 이다. 문턱을 추측해 채우지 않는다.
8. 공차 안이면 DOCKED, 아니면 NOT_DOCKED

`docking.docked` 는 쓰지 않는다. 공차가 NaN 이면 그 함수는 거짓(NOT_DOCKED)을 내므로, 준비 여부를 4에서 먼저 거른다.
"""

import math
from collections import namedtuple

from rokey_p3_navigation.docking import pose_error
from rokey_p3_navigation.readiness import zone_reasons

#: `DockingState.msg` 의 상수와 같은 값이다.
UNKNOWN = 0
DOCKED = 1
NOT_DOCKED = 2

#: 계약 11.6 공통 규칙: 리셋 전의 epoch 는 1 이다.
EPOCH_BEFORE_RESET = 1

#: `error_xy`·`error_yaw` 는 모르면 NaN 이다.
Judgement = namedtuple('Judgement', ('docking', 'error_xy', 'error_yaw', 'reason'))


def _positive(value):
    return value is not None and math.isfinite(value) and value > 0.0


def judge(*, epoch_known, goal_active, zone, pose, odom_age_s, odom_timeout_s, amcl_age_s, amcl_max_age_s):
    """`Judgement` 를 돌려준다. `zone` 은 `zones.Zone` 이거나 None, `pose` 는 (x, y, yaw) 이거나 None."""
    errors = (math.nan, math.nan)
    if zone is not None and pose is not None and all(math.isfinite(v) for v in (zone.x, zone.y, zone.yaw)):
        errors = pose_error(pose, (zone.x, zone.y, zone.yaw))
    if not epoch_known:
        return Judgement(UNKNOWN, *errors, '첫 RESET_DONE 전')
    if goal_active:
        return Judgement(NOT_DOCKED, *errors, 'GoToZone 주행 중')
    if zone is None:
        return Judgement(UNKNOWN, math.nan, math.nan, '목표 zone 없음')
    reasons = zone_reasons(zone)
    if reasons:
        return Judgement(UNKNOWN, *errors, reasons[0])
    if pose is None:
        return Judgement(UNKNOWN, math.nan, math.nan, 'map → base_link TF 없음')
    if odom_age_s is None or not odom_age_s <= odom_timeout_s:
        return Judgement(UNKNOWN, *errors, f'odom 이 {odom_timeout_s:g} s 넘게 없다')
    if not _positive(amcl_max_age_s):
        return Judgement(UNKNOWN, *errors, 'AMCL 신선도 문턱 미정(L3 측정 뒤)')
    if amcl_age_s is None or not amcl_age_s <= amcl_max_age_s:
        return Judgement(UNKNOWN, *errors, f'AMCL 이 {amcl_max_age_s:g} s 넘게 오래됐다')
    inside = errors[0] <= zone.tol_xy and errors[1] <= zone.tol_yaw
    return Judgement(DOCKED if inside else NOT_DOCKED, *errors, None)


class SeqCounter:
    """판정에 쓴 odom stamp 가 sim time 으로 앞으로 갔을 때만 +1. epoch 가 바뀌면 0 부터."""

    def __init__(self):
        self._epoch = None
        self._stamp = None
        self.value = 0

    def advance(self, epoch, odom_stamp):
        if epoch != self._epoch:
            self._epoch, self._stamp, self.value = epoch, None, 0
        if odom_stamp is not None and (self._stamp is None or odom_stamp > self._stamp):
            self._stamp = odom_stamp
            self.value += 1
        return self.value
