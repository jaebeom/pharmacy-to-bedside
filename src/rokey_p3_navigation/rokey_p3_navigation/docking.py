"""도킹·정지·출발 판정. ROS 를 import 하지 않는다. 계약 v1 2.2절·5절·7절.

fleet 노드가 쓰는 판정만 모았다. 시각·TF·토픽은 노드가 넣어 준다.
"""

import math

from rokey_p3_navigation.base_kinematics import wrap_angle

#: 계약 7절: 적재 위치·도크는 120 s, 그 밖(병동)은 180 s.
LOAD_DOCK_KINDS = ('load', 'dock')


def pose_error(current, target):
    """`(x, y, yaw)` 두 개의 평면 거리와 각 차이(접은 절대값)."""
    distance = math.hypot(current[0] - target[0], current[1] - target[1])
    return distance, abs(wrap_angle(current[2] - target[2]))


def docked(current, target, tol_xy, tol_yaw):
    """허용오차 안인가.

    허용오차 0 은 **아직 안 정한 값**이므로 언제나 거짓이다.
    zones.yaml 뼈대의 0 을 그대로 두면 도착이 성립하지 않는다(9/19 도킹 오차 측정 뒤 채운다).
    """
    if tol_xy <= 0.0 or tol_yaw <= 0.0:
        return False
    distance, angle = pose_error(current, target)
    return distance <= tol_xy and angle <= tol_yaw


def speed_is_quiet(linear_speed, angular_speed, linear_tol, angular_tol):
    """odom 속도가 정지 판정 문턱(계약 2.2절 0.02 m/s, 0.02 rad/s) 아래인가."""
    return abs(linear_speed) < linear_tol and abs(angular_speed) < angular_tol


def base_stopped(has_active_goal, quiet_for, quiet_hold):
    """`/amr_1/base/stopped`: 활성 goal 이 없고 속도가 `quiet_hold` 이상 조용했는가.

    `quiet_for` 는 문턱 아래로 머문 시간(s)이고, 문턱을 넘으면 부르는 쪽이 0 으로 되돌린다.
    """
    return not has_active_goal and quiet_for >= quiet_hold


def observation_fresh(age_s, timeout_s):
    """관측이 heartbeat 문턱 안에 왔는가. 한 번도 없거나 문턱을 넘으면 거짓.

    `timeout_s` 는 호출 쪽이 이미 가진 값이다. 여기서 문턱을 만들지 않는다.
    """
    if age_s is None or timeout_s is None:
        return False
    return 0.0 <= float(age_s) <= float(timeout_s)


def settle_ok(quiet_for, quiet_hold, odom_age_s, odom_timeout_s):
    """도착에 쓰는 정지. **지금** fresh 한 odom 구간에서 `quiet_hold` 이상 조용했는가.

    과거 누적만 있고 odom 이 끊긴 상태는 도착이 아니다. `base/stopped` 가 발행을 멈추는
    문턱(`odom_timeout_s`)과 같다.
    """
    return observation_fresh(odom_age_s, odom_timeout_s) and quiet_for >= quiet_hold


def departure_allowed(at_home, age_s, max_age_s):
    """계약 5절 출발 인터락: `arm/at_home` 이 true 이고 `max_age_s` 이내 수신.

    한 번도 못 받았으면 `age_s` 가 None 이다. unknown 은 허가가 아니다.
    """
    if at_home is None or age_s is None:
        return False
    return bool(at_home) and 0.0 <= age_s <= max_age_s


def goal_timeout_s(kind, load_dock_s, ward_s):
    """계약 7절의 `GoToZone` 제한 시간(sim). 구역 종류로 고른다."""
    return load_dock_s if kind in LOAD_DOCK_KINDS else ward_s
