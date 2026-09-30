"""L1. `refill_overlap` 줄 자체를 잠근다. 이 줄이 카드의 산출물이라 문구가 계약이다.

보충은 트립 FSM 밖에서 트립과 병렬로 돈다. "보충이 배송과 겹쳤나" 를 보려면 전에는 REFILL 줄과
DEPARTED→ARRIVED 줄의 시각을 사람이 맞춰 봐야 했다. 그래서 이 한 줄을 만들었다.

여기서 잠그는 것:
- 겹침 판정을 **로그가 직접 말한다**(`overlap=yes|no`). 읽는 사람이 상태 이름을 해석하지 않는다.
- 조제실에 서 있는 상태(`DOCKED_LOAD` 등)는 겹침이 아니다. `IDLE` 이 아닌 것과 같지 않다.
- `send` 는 실제로 나간 goal 하나에 한 줄이다(서버를 기다린 횟수만큼 찍히지 않는다).
- `done` 이 어느 품목의 결과인지 말한다.
"""
import threading
import types

import pytest
import test_server_wait as sw

from rokey_p3_orchestrator import refill_planner
from rokey_p3_orchestrator import trip_fsm as fsm

orch = sw.orch          # rclpy 가 없는 곳에서도 돌게 같은 대역 fixture 를 쓴다

ITEM = 'drug-amox'


class _Lines:
    """찍힌 줄을 그대로 모은다. `get_logger()` 자리에 그대로 놓는다."""

    def __init__(self):
        self.said = []
        self.warned = []

    def __call__(self):
        return self

    def info(self, text):
        self.said.append(text)

    def debug(self, text):
        self.said.append(text)

    def warn(self, text):
        self.warned.append(text)

    warning = warn

    def error(self, text):
        self.warned.append(text)


class _Client:
    def __init__(self, ready=True):
        self.ready = ready
        self.sent = []

    def server_is_ready(self):
        return self.ready

    def send_goal_async(self, goal, feedback_callback=None):
        self.sent.append(goal)
        return types.SimpleNamespace(add_done_callback=lambda _cb: None)


class _Fsm:
    def __init__(self, state=fsm.IDLE, stops_left=0):
        self.state = state
        self._left = stops_left

    def stops_left(self):
        return self._left


@pytest.fixture
def node(orch):
    borrowed = ('_send_goal', '_build_goal', '_log_refill_overlap', '_on_feedback', '_on_goal_response',
                '_on_result', '_read_result')
    harness = type('Harness', (), {n: getattr(orch.OrchestratorNode, n) for n in borrowed})()
    harness._lock = threading.RLock()
    harness._goals = {}
    harness._action_clients = {refill_planner.REFILL: _Client()}
    harness._fsm = _Fsm()
    harness.lines = _Lines()
    harness.get_logger = harness.lines
    harness._waiting = []
    harness._hold = lambda action, command: harness._waiting.append(command)
    harness.module = orch          # 대역이 들어간 orchestrator_node 모듈(GoalStatus 등)
    harness.fed = []
    harness._feed = lambda token, action, outcome, detail: harness.fed.append((token, outcome))
    return harness


def send(node, slot=1, item=ITEM, seq=1):
    command = refill_planner.SendGoal(refill_planner.REFILL, {'item_id': item, 'slot': slot},
                                      token=fsm.Token(epoch=1, owner='refill', seq=seq))
    node._send_goal(command)
    return command


def finish(node, command, status_name, success=True):
    """`_on_result` 를 실제로 탄다. 가짜 future 가 wrapper status 와 결과를 준다."""
    status = getattr(node.module.GoalStatus, status_name)
    result = types.SimpleNamespace(success=success, lot_id='lot-x')
    future = types.SimpleNamespace(result=lambda: types.SimpleNamespace(status=status, result=result))
    node._on_result(refill_planner.REFILL, command.token, future)


def test_the_line_says_whether_it_overlapped(node):
    node._fsm = _Fsm(fsm.TRANSIT, stops_left=2)
    send(node)
    assert node.lines.said == [
        f'refill_overlap send item={ITEM} overlap=yes trip=TRANSIT stops_left=2 slot=1']


def test_standing_in_the_pharmacy_is_not_an_overlap(node):
    """트립이 있어도 AMR 이 조제실에 있으면 보충이 배송을 늦추지 않는다 — `IDLE` 이 아닌 것과 다르다."""
    for state in (fsm.DOCKED_LOAD, fsm.WAIT_BELT, fsm.PICKING_BELT, fsm.RETURNING, fsm.RESETTING, fsm.IDLE):
        node.lines.said.clear()
        node._fsm = _Fsm(state)
        send(node)
        assert node.lines.said[0].split(' overlap=')[1].split()[0] == 'no', state


def test_every_delivery_state_counts_as_an_overlap(node):
    for state in fsm.DELIVERY_STATES:
        node.lines.said.clear()
        node._fsm = _Fsm(state)
        send(node)
        assert node.lines.said[0].split(' overlap=')[1].split()[0] == 'yes', state


def test_waiting_for_the_server_does_not_write_a_send_line(node):
    """`_hold` 로 돌아간 횟수만큼 찍히면 한 번 보충한 것이 여러 번으로 읽힌다."""
    node._action_clients[refill_planner.REFILL].ready = False
    send(node)
    send(node)
    assert node.lines.said == []
    assert len(node._waiting) == 2
    node._action_clients[refill_planner.REFILL].ready = True
    send(node)
    assert len(node.lines.said) == 1


def test_done_names_the_item_it_finished(node):
    command = send(node)
    node.lines.said.clear()
    node._fsm = _Fsm(fsm.DELIVERING, stops_left=1)
    finish(node, command, 'STATUS_SUCCEEDED')
    assert node.lines.said == [
        f'refill_overlap done item={ITEM} overlap=yes trip=DELIVERING stops_left=1 outcome=ok']
    assert node.fed == [(command.token, fsm.OK)]


def test_done_names_the_item_of_that_goal_even_after_another_send(node):
    """커서 #604 재검토 ③. 품목을 노드 필드 하나에 두면 다음 send 가 덮어써 앞 goal 의 결과가 뒤 품목으로 적혔다."""
    first = send(node, item='drug-amox', seq=1)
    second = send(node, item='drug-ibu', seq=2)
    node.lines.said.clear()
    finish(node, first, 'STATUS_SUCCEEDED')
    finish(node, second, 'STATUS_ABORTED', success=False)
    assert [line.split()[2] for line in node.lines.said] == ['item=drug-amox', 'item=drug-ibu']
    assert node.lines.said[0].endswith('outcome=ok')
    assert node.lines.said[1].endswith('outcome=failed')


def test_a_canceled_refill_still_gets_its_done_line(node):
    """취소도 결과다. 전에는 `_read_result` 가 로그 전에 return 해서 `send` 만 있고 `done` 이 없었다."""
    command = send(node)
    node.lines.said.clear()
    finish(node, command, 'STATUS_CANCELED')
    assert node.lines.said == [f'refill_overlap done item={ITEM} overlap=no trip=IDLE stops_left=0 outcome=canceled']
    assert node.fed == [(command.token, fsm.CANCELED)]


def test_a_broken_diagnostic_never_blocks_the_goal(node):
    """관측이 동작을 바꾸면 그것은 관측이 아니다. #604 CI 가 그 자리였다."""
    class Broken:
        state = fsm.TRANSIT

        def stops_left(self):
            raise RuntimeError('boom')

    node._fsm = Broken()
    send(node)
    assert len(node._action_clients[refill_planner.REFILL].sent) == 1   # goal 은 나갔다
    assert node.lines.said == []
    assert len(node.lines.warned) == 1 and 'boom' in node.lines.warned[0]


def test_a_logger_that_throws_blocks_neither_the_send_nor_the_result(node):
    """커서 #604 재검토 ②. 전에는 `stops_left` 만 try 안이고 `overlap=` 과 info 는 밖이었다 —
    info 가 던지면 `send_goal_async` 전에, `done` 에서는 `_feed` 전에 끊겼다."""
    class Throwing(_Lines):
        def info(self, text):
            raise RuntimeError('log sink down')

    node.lines = Throwing()
    node.get_logger = node.lines
    command = send(node)
    assert len(node._action_clients[refill_planner.REFILL].sent) == 1          # goal 은 나갔다
    finish(node, command, 'STATUS_SUCCEEDED')
    assert node.fed == [(command.token, fsm.OK)]                               # 결과도 FSM 으로 갔다
    assert len(node.lines.warned) == 2 and all('log sink down' in w for w in node.lines.warned)
