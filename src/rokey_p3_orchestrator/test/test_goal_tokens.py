"""goal token. 같은 epoch 안에서도 이전 goal 의 늦은 수락·결과가 현재 상태·handle·재고·선반을 못 바꾼다.

테스트 이름은 리셋 barrier v2 설계(PR #61 댓글) G1-G4 를 그대로 쓴다. 노드 배선은 orchestrator_node 의 메서드를
빌린 Harness 에 가짜 클라이언트·future 를 붙여 본다(test_server_wait 의 대역 모듈을 같이 쓴다).
"""

import threading
import types

import test_server_wait as sw

from rokey_p3_orchestrator import refill_planner as rp
from rokey_p3_orchestrator import trip_fsm as fsm
from rokey_p3_orchestrator.dispenser_inventory import SLOT_A, load_inventory

orch = sw.orch          # 같은 대역 fixture 를 이 모듈에서도 쓴다

ORDER = 'ord-0001'
PATIENT = '1001'
BED = 'bed_a1'
ITEM = 'drug-amox'
REQUEST = {'request_id': 'r001-0001', 'mode': fsm.MODE_SINGLE, 'destination_id': BED,
           'orders': [{'order_id': ORDER, 'patient_id': PATIENT, 'item_id': ITEM}]}


def trip(**config):
    machine = fsm.TripFsm(config=fsm.TripConfig(**config), patient_beds={PATIENT: BED})
    machine.tick(0.0, 0.0)
    machine.state_update(fsm.AT_HOME, True, True)
    machine.state_update(fsm.BASE_STOPPED, True, True)
    machine.state_update(fsm.BELT, {'occupied': False, 'at_end': False, 'order_id': ''}, True)
    return machine


def goals(commands):
    return [c for c in commands if isinstance(c, fsm.SendGoal)]


class _Future:
    """콜백을 모아 두었다가 resolve 때 부른다."""

    def __init__(self):
        self._callbacks = []

    def add_done_callback(self, callback):
        self._callbacks.append(callback)

    def resolve(self, value):
        for callback in self._callbacks:
            callback(types.SimpleNamespace(result=lambda value=value: value))


class _Handle:
    def __init__(self, accepted=True):
        self.accepted = accepted
        self.cancel_calls = 0
        self.result_future = _Future()

    def cancel_goal_async(self):
        self.cancel_calls += 1
        return _Future()

    def get_result_async(self):
        return self.result_future


class _ActionClient:
    def __init__(self, ready=True):
        self.ready = ready
        self.sent = []          # (goal, 응답 future)

    def server_is_ready(self):
        return self.ready

    def send_goal_async(self, goal, feedback_callback=None):
        future = _Future()
        self.sent.append((goal, future))
        return future


def harness(orch, machine=None):
    """노드의 goal·cancel·결과 경로만 빌린다. 이벤트·주문 상태·Deliver 결과 발행은 적기만 한다."""
    borrowed = ('_run', '_send_goal', '_build_goal', '_cancel', '_call', '_feed', '_hold', '_server_ready',
                '_flush_waiting', '_finish_unsent_cancels', '_on_feedback', '_on_goal_response', '_on_result',
                '_read_result', '_on_service', '_abandon_undrained', '_wait_limit', '_note', '_log_refill_overlap')
    node = type('Harness', (), {name: getattr(orch.OrchestratorNode, name) for name in borrowed})()
    node._lock = threading.RLock()
    node._epoch = 1
    node._goals = {}
    node._drain_tokens = []
    node._unsent_cancels = []
    node._action_clients = {name: _ActionClient() for name in (fsm.GO_TO_ZONE, fsm.PICK_POUCH, fsm.SCAN_TAG)}
    node._dispense = sw._ServiceClient()
    node._sim_reset = sw._ServiceClient()
    node._fsm = machine if machine is not None else sw._Fsm()
    node._server_wait = orch.ServerWait(10.0)
    node.published = []
    node._emit = node.published.append
    node._publish_order = node.published.append
    node._finish = node.published.append
    node.get_logger = lambda: sw._Logger()
    return node


def result_of(orch, status, **payload):
    return types.SimpleNamespace(status=status, result=types.SimpleNamespace(**payload))


# G1 ---------------------------------------------------------------------

def test_late_result_cannot_finish_replacement_goal(orch):
    # FSM: 트립 제한으로 적재 goal 을 cancel → 종결 뒤 복귀 goal. 이전 goal 의 늦은 ARRIVED 는 복귀를 못 끝낸다.
    machine = trip(trip_limit_s=100.0)
    [load] = goals(machine.request(REQUEST))
    assert machine.result(fsm.GO_TO_ZONE, fsm.ACCEPTED, token=load.token) == []
    limit = machine.tick(200.0, 0.0)
    assert fsm.Cancel(fsm.GO_TO_ZONE) in limit and goals(limit) == []      # 종결 전에는 대체 goal 이 없다
    [dock] = goals(machine.result(fsm.GO_TO_ZONE, fsm.CANCELED, token=load.token))
    assert dock.goal == {'zone_id': 'dock_1'} and dock.token != load.token
    assert machine.result(fsm.GO_TO_ZONE, fsm.ARRIVED, token=load.token) == []
    assert machine.state == fsm.RETURNING
    assert machine.result(fsm.GO_TO_ZONE, fsm.ACCEPTED, token=dock.token) == [fsm.Emit('RETURNED', 'r001-0001')]
    assert machine.result(fsm.GO_TO_ZONE, fsm.ARRIVED, token=dock.token) == [
        fsm.Emit('DOCKED', 'r001-0001'), fsm.Finish(False)]

    # 노드: 이전 goal 의 결과는 그 token 항목만 지운다. 같은 액션의 새 handle 은 남는다.
    node = harness(orch)
    old, new = fsm.Token(1, 'trip', 1), fsm.Token(1, 'trip', 2)
    node._goals = {old: orch.GoalEntry(fsm.GO_TO_ZONE, _Handle()), new: orch.GoalEntry(fsm.GO_TO_ZONE, _Handle())}
    future = _Future()
    future.add_done_callback(lambda f: node._on_result(fsm.GO_TO_ZONE, old, f))
    future.resolve(result_of(orch, orch.GoalStatus.STATUS_SUCCEEDED, arrived=True, message=''))
    assert list(node._goals) == [new]


# G2 ---------------------------------------------------------------------

def test_cancel_before_accept_waits_for_terminal(orch):
    """수락 전에 cancel → 늦은 수락 즉시 cancel. cancel 응답만으로는 대체 goal 을 안 보내고 결과(종결)를 기다린다."""
    machine = trip(trip_limit_s=100.0)
    node = harness(orch, machine)
    client = node._action_clients[fsm.GO_TO_ZONE]

    node._run(machine.request(REQUEST))
    [(load_goal, response)] = client.sent
    [load_token] = list(node._goals)

    node._run(machine.tick(200.0, 0.0))                 # 트립 제한 → Cancel. 아직 수락 응답 전이다
    assert node._goals[load_token].cancel_requested and node._goals[load_token].handle is None
    assert len(client.sent) == 1

    handle = _Handle(accepted=True)
    response.resolve(handle)                            # 늦은 수락
    assert handle.cancel_calls == 1                     # 받자마자 cancel
    assert len(client.sent) == 1                        # cancel 응답은 종결이 아니다
    node._run(machine.tick(201.0, 1.0))
    assert len(client.sent) == 1 and load_token in node._goals

    handle.result_future.resolve(result_of(orch, orch.GoalStatus.STATUS_CANCELED, arrived=False, message=''))
    assert load_token not in node._goals
    assert len(client.sent) == 2                        # 종결 뒤에야 복귀 goal
    assert client.sent[1][0].zone_id == 'dock_1'


def test_cancel_wait_gives_up_after_cancel_wait_s_wall(orch):
    machine = trip(trip_limit_s=100.0, cancel_wait_s=10.0)
    [load] = goals(machine.request(REQUEST))
    machine.result(fsm.GO_TO_ZONE, fsm.ACCEPTED, token=load.token)
    assert goals(machine.tick(200.0, 0.0)) == []
    assert goals(machine.tick(201.0, 9.9)) == []
    assert [g.goal for g in goals(machine.tick(202.0, 10.0))] == [{'zone_id': 'dock_1'}]


# G3 ---------------------------------------------------------------------

def test_server_wait_cancel_drops_only_matching_token(orch):
    node = harness(orch)
    client = node._action_clients[fsm.GO_TO_ZONE]
    client.ready = False
    first = fsm.SendGoal(fsm.GO_TO_ZONE, {'zone_id': 'load'}, token=fsm.Token(1, 'trip', 1))
    second = fsm.SendGoal(fsm.GO_TO_ZONE, {'zone_id': 'dock_1'}, token=fsm.Token(1, 'trip', 2))
    node._run([first, second])
    node._run([fsm.Cancel(fsm.GO_TO_ZONE, token=first.token)])
    assert node._server_wait.tokens() == (second.token,)
    assert list(node._goals) == [second.token]
    client.ready = True
    node._finish_unsent_cancels()
    node._flush_waiting()
    assert [goal.zone_id for goal, _ in client.sent] == ['dock_1']
    assert node._fsm.results == [(fsm.GO_TO_ZONE, fsm.CANCELED, {})]     # 보내지 않은 goal 은 대기에서 빼면 종결


# G4 ---------------------------------------------------------------------

SHELF = {
    'items': {ITEM: [{'slot': 'a', 'lot_id': 'lot-amox-01', 'expiry': '2027-03-31', 'count': 0},
                     {'slot': 'b', 'lot_id': 'lot-amox-02', 'expiry': '2027-09-30', 'count': 2}]},
    'shelf': {ITEM: [{'lot_id': 'lot-amox-03', 'expiry': '2028-03-31', 'count': 5},
                     {'lot_id': 'lot-amox-04', 'expiry': '2028-09-30', 'count': 5}]},
}


def test_late_refill_result_cannot_consume_shelf():
    inventory = load_inventory(SHELF)
    planner = rp.RefillPlanner(inventory, rp.ShelfSource(lambda: inventory), retry_delay_s=5.0, timeout_s=90.0)
    inventory.take(ITEM)
    [first] = goals(planner.tick(0.0))
    planner.result(fsm.ACCEPTED, 0.1, token=first.token)
    timed_out = planner.tick(90.0)
    assert fsm.Cancel(rp.REFILL) in timed_out
    assert goals(planner.tick(95.0)) == []                        # cancel 한 goal 이 끝나기 전에는 재시도 없음

    assert planner.result(fsm.OK, 96.0, {'lot_id': 'late'}, token=first.token) == []     # 이전 goal 의 늦은 성공
    assert inventory.shelf_peek(ITEM).lot_id == 'lot-amox-03'
    assert [s.count for s in inventory.slots(ITEM) if s.slot == SLOT_A] == [0]
    [retry] = goals(planner.tick(96.1))
    assert retry.token != first.token

    planner.result(fsm.OK, 120.0, token=retry.token)
    assert inventory.shelf_peek(ITEM).lot_id == 'lot-amox-04'
    assert [s.lot_id for s in inventory.slots(ITEM) if s.slot == SLOT_A] == ['lot-amox-03']

    # 종결 대기가 wall 상한으로 끝나 재시도가 나간 뒤에 온 늦은 성공도 재고·선반을 안 바꾼다.
    inventory = load_inventory(SHELF)
    planner = rp.RefillPlanner(inventory, rp.ShelfSource(lambda: inventory), retry_delay_s=5.0, timeout_s=90.0,
                               cancel_wait_s=10.0)
    inventory.take(ITEM)
    [first] = goals(planner.tick(0.0, now_wall=0.0))
    planner.tick(90.0, now_wall=90.0)
    [retry] = goals(planner.tick(95.0, now_wall=100.0))
    assert planner.result(fsm.OK, 101.0, {'lot_id': 'late'}, token=first.token) == []
    assert inventory.shelf_peek(ITEM).lot_id == 'lot-amox-03'
    planner.result(fsm.OK, 120.0, token=retry.token)
    assert inventory.shelf_peek(ITEM).lot_id == 'lot-amox-04'


# wrapper status ------------------------------------------------------------

def test_canceled_or_aborted_status_is_never_read_as_success(orch):
    node = harness(orch)
    status = orch.GoalStatus
    goto = types.SimpleNamespace(arrived=True, message='')
    pick = types.SimpleNamespace(outcome='ok', success=True)
    refill = types.SimpleNamespace(success=True, lot_id='x')
    assert node._read_result(fsm.GO_TO_ZONE, status.STATUS_SUCCEEDED, goto)[0] == fsm.ARRIVED
    assert node._read_result(fsm.GO_TO_ZONE, status.STATUS_ABORTED, goto)[0] == fsm.NOT_ARRIVED
    assert node._read_result(fsm.GO_TO_ZONE, status.STATUS_CANCELED, goto)[0] == fsm.CANCELED
    assert node._read_result(fsm.PICK_POUCH, status.STATUS_ABORTED, pick)[0] == fsm.TIMED_OUT
    assert node._read_result(rp.REFILL, status.STATUS_ABORTED, refill)[0] == rp.FAILED
