"""주문 종료 상태. 시나리오 5절과 같은 네 이름. ROS 를 import 하지 않는다."""

SUCCESS = 'SUCCESS'
HOLD_RETURN = 'HOLD_RETURN'
ABORT = 'ABORT'
TIMEOUT = 'TIMEOUT'

TERMINAL_STATES = (SUCCESS, HOLD_RETURN, ABORT, TIMEOUT)


def is_terminal(state):
    """주문이 끝난 상태인가."""
    return state in TERMINAL_STATES


def trip_succeeded(order_states):
    """트립 성공 = 요청의 모든 주문이 SUCCESS. 부분 배송은 성공이 아니다."""
    states = list(order_states)
    return bool(states) and all(s == SUCCESS for s in states)
