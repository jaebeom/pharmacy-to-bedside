"""픽 허가 조건과 결과 값. 시나리오 단계 1 "픽", 계약 2.3·5절. ROS 를 import 하지 않는다.

unknown 은 ``None`` 으로 넘긴다. **unknown 은 허가가 아니다** (계약 5절:
"타임아웃은 진입 허가가 아니다. 조건이 unknown 이면 기다린다").
"""

# PickPouch 결과 outcome (계약 2.3절). 이 일곱 개 밖의 값을 쓰지 않는다.
OUTCOME_OK = 'ok'
OUTCOME_NOT_DETECTED = 'not_detected'
OUTCOME_QR_MISMATCH = 'qr_mismatch'
OUTCOME_GRASP_FAILED = 'grasp_failed'
OUTCOME_DROPPED = 'dropped'
OUTCOME_TIMEOUT = 'timeout'
OUTCOME_REJECTED_INTERLOCK = 'rejected_interlock'

OUTCOMES = (OUTCOME_OK, OUTCOME_NOT_DETECTED, OUTCOME_QR_MISMATCH, OUTCOME_GRASP_FAILED,
            OUTCOME_DROPPED, OUTCOME_TIMEOUT, OUTCOME_REJECTED_INTERLOCK)


def pick_allowed(belt_stopped, pouch_stopped, amr_docked):
    """셋이 모두 참일 때만 UR5 가 벨트 끝에서 집는다."""
    return bool(belt_stopped) and bool(pouch_stopped) and bool(amr_docked)


def belt_pick_allowed(base_stopped, belt_at_end, belt_order_id, goal_order_id):
    """계약 5절 `source=BELT` guard.

    시나리오의 세 조건을 계약 신호로 옮긴 것이다. 봉투가 끝 정지 위치에 서면 벨트를
    멈추므로(시나리오 1절) `BeltState.at_end` 하나가 "벨트 정지"와 "봉투 정지"를 같이 말한다.
    `base/stopped` 는 AMR 도킹 완료 겸 정지다. 여기에 벨트 위 봉투가 이 goal 의 주문인지까지 본다.
    """
    if not pick_allowed(belt_at_end, belt_at_end, base_stopped):
        return False
    return bool(goal_order_id) and belt_order_id == goal_order_id


def arm_motion_allowed(base_stopped):
    """계약 5절 팔 동작 공통 조건. `PickPouch` 와 `ScanTag` 가 같이 쓴다.

    `base/stopped` 가 true 이고 1.0 s 이내 수신이어야 한다. 1.0 s 판정은 노드가 하고
    여기에는 살아 있는 값이나 unknown(None) 이 온다.
    """
    return bool(base_stopped)


def deck_pick_allowed(base_stopped):
    """계약 5절 `source=DECK` guard. 상판에서 집을 때는 공통 조건만 본다."""
    return arm_motion_allowed(base_stopped)


def select_detection(order_ids, goal_order_id):
    """검출된 봉투 QR 목록에서 이 goal 의 봉투를 고른다. 반환은 (인덱스, outcome).

    - goal 의 주문이 있으면 그 인덱스와 `ok`. 같은 것이 여럿이면 배열 순서가 앞선 것.
    - 없고 다른 QR 이 읽힌 봉투가 있으면 `qr_mismatch` (검수 실패).
    - 읽힌 QR 이 하나도 없으면 `not_detected`.
    """
    for index, value in enumerate(order_ids):
        if value and value == goal_order_id:
            return index, OUTCOME_OK
    if any(value for value in order_ids):
        return None, OUTCOME_QR_MISMATCH
    return None, OUTCOME_NOT_DETECTED
