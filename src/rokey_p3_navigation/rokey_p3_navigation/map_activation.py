"""map_server 활성화 감시의 판단. ROS 를 import 하지 않는다.

회차133(85b583c, master01, #240 5848721883·5853335533·5853347491): 기동 1초 안에 map_server 가 지도를
읽은 뒤 이 줄이 났다 — `failed to send response to /amr_1/map_server/change_state (timeout): client will
not receive response`. configure 응답이 DDS 에서 lifecycle_manager_localization 에 닿지 못했다. 관리자는
그 뒤로 로그가 없고(멈춤) map_server 는 active 가 되지 못해 지도를 한 번도 내지 않았다. 전역 코스트맵은
5 m 기본 격자로 남아 로봇이 범위 밖이었고, 주문 뒤 dock_1·load Nav2 목표가 ABORTED 됐다. 같은 장비 정상
회차(155)는 Read map 뒤 0.006 s 안에 Activating → bond → Managed nodes are active.

그래서 map_server 를 따로 본다: `wait_s` 가 지나도 active 가 아니면 map_server 에 **직접** configure/activate
를 보낸다. 관리자가 멈춰 있어도 된다. 정상이면 아무것도 하지 않는다.
"""

#: lifecycle_msgs/msg/State 의 id.
UNCONFIGURED = 1
INACTIVE = 2
ACTIVE = 3
#: lifecycle_msgs/msg/Transition 의 id.
CONFIGURE = 1
ACTIVATE = 3

#: 관리자에게 먼저 맡기는 시간(s, 벽시계). 정상 회차는 기동 1 s 안에 active 다(155). 고른 값이다.
WAIT_S = 20.0
#: 직접 보내는 전이 횟수 상한. 넘으면 포기하고 한 줄 남긴다.
MAX_TRANSITIONS = 4


def next_transition(state_id, elapsed_s, wait_s=WAIT_S):
    """지금 map_server 상태 → 보낼 전이 id 또는 None.

    active 면 None(할 일 없음). `wait_s` 전이면 None(관리자에게 맡긴다). 그 뒤 unconfigured 면 CONFIGURE,
    inactive 면 ACTIVATE. 전이 중·finalized 같은 다른 상태는 건드리지 않는다(None).
    """
    if state_id == ACTIVE or elapsed_s < wait_s:
        return None
    if state_id == UNCONFIGURED:
        return CONFIGURE
    if state_id == INACTIVE:
        return ACTIVATE
    return None


#: 서비스 응답을 기다리는 상한(s, 벽시계). 넘으면 그 호출을 버리고 상태를 다시 본다. **감시 자신도 응답 유실에 멈추면
#: 안 된다** — 고치려는 고장이 바로 그 유실이다(통합검증 #743 5854169997).
PENDING_TIMEOUT_S = 5.0
#: 응답 시한 초과를 이만큼 겪으면 포기하고 한 줄 남긴다.
MAX_TIMEOUTS = 10


def pending_expired(started_s, now_s, timeout_s=PENDING_TIMEOUT_S):
    """기다리는 호출이 시한을 넘었나. 기다리는 것이 없으면(started None) False."""
    return started_s is not None and now_s - started_s >= timeout_s
