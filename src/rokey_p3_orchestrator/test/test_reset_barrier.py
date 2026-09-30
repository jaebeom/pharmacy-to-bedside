"""리셋 barrier v2. 끊긴 주문 종료 → RESET_BEGIN → drain → /sim/reset → 재고 다시 읽기·RESET_DONE.
실패는 멈춘 채 닫힌다.

테스트 이름은 PR #61 설계(B1-B3, R1, G5)를 그대로 쓴다. FSM 표와, orchestrator_node 의 메서드를 빌린 Harness
(test_goal_tokens 의 가짜 클라이언트·future)를 함께 본다.
"""

import types

import test_goal_tokens as gt
import test_server_wait as sw

from rokey_p3_orchestrator import refill_planner as rp
from rokey_p3_orchestrator import trip_fsm as fsm
from rokey_p3_orchestrator.dispenser_inventory import load_inventory

orch = sw.orch

ORDER = gt.ORDER
REQUEST = gt.REQUEST
RID = 'r001-0001'
DISPENSER = {'items': {gt.ITEM: [{'slot': 'a', 'lot_id': 'x', 'expiry': '2027-01-01', 'count': 5},
                                 {'slot': 'b', 'lot_id': 'y', 'expiry': '2027-02-01', 'count': 5}]}}


def calls(commands):
    return [c for c in commands if isinstance(c, fsm.Call)]


def events(commands):
    return [c for c in commands if isinstance(c, fsm.Emit)]


def notes(commands, level):
    return [c for c in commands if isinstance(c, fsm.Note) and c.level == level]


def harness(orch, machine=None):
    """test_goal_tokens 의 Harness 에 리셋 경로 메서드를 더 빌려 붙인다."""
    node = gt.harness(orch, machine)
    node._db = None                          # pharmacy_db 기본 꺼짐
    for name in ('_on_reset', '_drain_for_reset', '_reload_stores', '_stamp'):
        setattr(node, name, getattr(orch.OrchestratorNode, name).__get__(node))
    node.get_clock = lambda: types.SimpleNamespace(
        now=lambda: types.SimpleNamespace(nanoseconds=0, to_msg=lambda: None))
    return node


def dispatching_with_goal(**config):
    """적재 위치로 가는 goal 이 수락된 트립."""
    machine = gt.trip(**config)
    [load] = gt.goals(machine.request(REQUEST))
    machine.result(fsm.GO_TO_ZONE, fsm.ACCEPTED, token=load.token)
    return machine, load


# B1 ----------------------------------------------------------------------------

def test_reset_waits_for_all_terminals(orch):
    # FSM: 트립 goal 과 보충 goal 이 둘 다 종결돼야 /sim/reset 을 부른다.
    machine, load = dispatching_with_goal()
    refill = fsm.Token(1, 'refill', 7)
    entry = machine.reset(2, now_sim=10.0, now_wall=0.0, drain=[(fsm.GO_TO_ZONE, load.token), (rp.REFILL, refill)])
    assert calls(entry) == []
    assert {c.token for c in entry if isinstance(c, fsm.Cancel)} == {load.token, refill}
    assert machine.terminated(load.token) == []
    assert machine.result(fsm.GO_TO_ZONE, fsm.ACCEPTED, token=refill) == []     # 수락은 종결이 아니다
    assert calls(machine.terminated(refill)) == [fsm.Call(fsm.RESET, {'epoch': 2})]

    # 노드: goal 표의 token 을 drain 으로 넘기고, 이전 epoch 결과도 종결로 알린다.
    node = harness(orch, gt.trip())
    node._refill = rp.RefillPlanner(None, epoch=1)
    node._run(node._fsm.request(REQUEST))
    [(_, response)] = node._action_clients[fsm.GO_TO_ZONE].sent
    [trip_token] = list(node._goals)
    trip_handle = gt._Handle()
    response.resolve(trip_handle)                                   # 수락된 트립 goal
    refill_token = fsm.Token(1, 'refill', 1)
    node._goals[refill_token] = orch.GoalEntry(rp.REFILL)           # 보냈지만 수락 전인 보충 goal
    node._sim_reset.ready = True

    reply = node._on_reset(types.SimpleNamespace(epoch=0), types.SimpleNamespace(ok=None, message=''))
    assert reply.ok and node._epoch == 2
    assert trip_handle.cancel_calls == 1 and node._goals[refill_token].cancel_requested
    assert node._sim_reset.calls == []

    trip_handle.result_future.resolve(gt.result_of(orch, orch.GoalStatus.STATUS_CANCELED, arrived=False, message=''))
    assert node._sim_reset.calls == []                              # 보충 goal 이 아직이다
    refill_handle = gt._Handle()
    node._on_goal_response(rp.REFILL, refill_token, types.SimpleNamespace(result=lambda: refill_handle))
    assert refill_handle.cancel_calls == 1                          # 늦은 수락 즉시 cancel
    assert node._sim_reset.calls == []
    refill_handle.result_future.resolve(gt.result_of(orch, orch.GoalStatus.STATUS_CANCELED, success=False, lot_id=''))
    [reset_request] = node._sim_reset.calls
    assert reset_request.epoch == 2


# B2 ----------------------------------------------------------------------------

def test_reset_failure_and_deadline_fail_closed(orch):
    # false → failed. RESET_DONE 없음, Deliver 거부, 자동 재시도 없음. 새 리셋으로 복구.
    machine = gt.trip()
    [begin, call] = machine.reset(2, now_wall=0.0)
    assert begin == fsm.Emit('RESET_BEGIN') and call == fsm.Call(fsm.RESET, {'epoch': 2})
    failed = machine.result(fsm.RESET, fsm.FAILED, {'message': 'not_ready'}, token=call.token)
    assert len(notes(failed, 'error')) == 1 and events(failed) == []
    assert machine.barrier_failed and not machine.accepts(REQUEST)
    assert machine.tick(1.0, 100.0) == []
    retry = machine.reset(3, now_wall=200.0)
    assert [e.event for e in events(retry)] == ['RESET_BEGIN'] and events(retry)[0].epoch == 3
    [call3] = calls(retry)
    assert call3.request == {'epoch': 3}
    assert machine.result(fsm.RESET, fsm.OK, token=call.token) == []    # 실패한 barrier 의 늦은 ok 는 버린다
    done = machine.result(fsm.RESET, fsm.OK, token=call3.token)
    assert done == [fsm.ReloadStores(), fsm.Emit('RESET_DONE')]
    assert machine.state == fsm.IDLE and machine.accepts(REQUEST)

    # 30 s 무응답 → failed.
    machine = gt.trip()
    machine.reset(2, now_wall=0.0)
    assert machine.tick(0.0, 29.9) == []
    assert len(notes(machine.tick(0.0, 30.0), 'error')) == 1 and machine.barrier_failed

    # 서비스 예외 → failed(노드).
    node = harness(orch, gt.trip())
    node._refill = rp.RefillPlanner(None, epoch=1)
    node._sim_reset.ready = True
    node._on_reset(types.SimpleNamespace(epoch=0), types.SimpleNamespace(ok=None, message=''))
    token = node._fsm._expected[fsm.RESET]

    def raising():
        raise RuntimeError('service died')

    node._on_service(fsm.RESET, token, types.SimpleNamespace(result=raising))
    assert node._fsm.barrier_failed


# B3 ----------------------------------------------------------------------------

def test_clock_pause_does_not_stop_barrier_deadlines():
    machine, load = dispatching_with_goal(cancel_wait_s=10.0, reset_timeout_s=30.0)
    machine.reset(2, now_sim=50.0, now_wall=0.0)
    assert calls(machine.tick(50.0, 5.0)) == []                    # sim 은 멈춰 있다
    assert machine.reset(3, now_sim=50.0, now_wall=8.0) == []       # 중복 리셋은 합류. 상한·epoch 그대로
    assert machine.epoch == 2
    timeout = machine.tick(50.0, 10.0)
    assert len(notes(timeout, 'warning')) == 1 and calls(timeout) == [fsm.Call(fsm.RESET, {'epoch': 2})]
    assert machine.reset(3, now_sim=50.0, now_wall=39.0) == []      # reset_wait 에도 합류
    assert machine.tick(50.0, 39.9) == []
    assert len(notes(machine.tick(50.0, 40.0), 'error')) == 1 and machine.barrier_failed

    # drain 을 상한으로 넘긴 barrier 가 성공하면 RESET_DONE detail 에 남는다.
    machine, load = dispatching_with_goal()
    machine.reset(2, now_sim=50.0, now_wall=0.0)
    [call] = calls(machine.tick(50.0, 10.0))
    done = machine.result(fsm.RESET, fsm.OK, token=call.token)
    assert done[-1] == fsm.Emit('RESET_DONE', detail='drain_timeout')


# R1 ----------------------------------------------------------------------------

def test_reset_terminal_snapshot_precedes_new_epoch(orch, monkeypatch):
    # FSM: 실은 주문 하나는 끊겨 닫히고, 이미 닫힌 주문은 덮지 않는다.
    machine = gt.trip()
    batch = dict(REQUEST, mode=fsm.MODE_BATCH_ROOM,
                 orders=REQUEST['orders'] + [{'order_id': 'ord-0002', 'patient_id': gt.PATIENT, 'item_id': gt.ITEM}])
    machine.request(batch)
    load = machine._expected[fsm.GO_TO_ZONE]
    machine.result(fsm.GO_TO_ZONE, fsm.ARRIVED, token=load)
    machine.result(fsm.DISPENSE, fsm.ACCEPTED)
    machine.state_update(fsm.BELT, {'occupied': True, 'at_end': True, 'order_id': ORDER}, True)
    machine.state_update(fsm.BELT, {'occupied': False, 'at_end': False, 'order_id': ''}, True)
    machine.result(fsm.PICK_POUCH, fsm.OK)                          # ORDER 적재
    for attempt in range(3):                                        # ord-0002 배출 거부 3회 → ABORT
        machine.tick(10.0 * (attempt + 1), 0.0)
        machine.result(fsm.DISPENSE, fsm.REJECTED, {'message': 'not_ready'})
    assert machine.order_states() == {ORDER: 'LOADED', 'ord-0002': 'ABORT'}

    out = machine.reset(2, now_sim=77.5, now_wall=0.0)
    closed, done, finish, begin = out[0], out[1], out[2], out[3]
    assert closed == fsm.OrderState(ORDER, 'ABORT', 'reset_interrupted')
    assert (closed.request_id, closed.stamp) == (RID, 77.5)
    assert done == fsm.Emit('ORDER_DONE', RID, ORDER) and (done.epoch, done.stamp) == (1, 77.5)
    assert finish == fsm.Finish(False, True)
    assert begin == fsm.Emit('RESET_BEGIN') and (begin.epoch, begin.stamp) == (2, 77.5)
    assert [c.order_id for c in out if isinstance(c, fsm.OrderState)] == [ORDER]      # ord-0002 는 안 덮는다

    # 노드: snapshot 을 그대로 발행한다(epoch 가 이미 2 로 올라간 뒤에도).
    published = []

    class Message:
        def __init__(self):
            self.header = types.SimpleNamespace(stamp=None)

    monkeypatch.setattr(orch, 'Event', Message)
    monkeypatch.setattr(orch, 'OrderStatus', Message)
    monkeypatch.setattr(orch, 'Time', lambda nanoseconds: types.SimpleNamespace(to_msg=lambda: nanoseconds))
    monkeypatch.setattr(orch, 'ORDER_STATE_VALUES', {'ABORT': 'ABORT'})
    node = harness(orch)
    node._emit = orch.OrchestratorNode._emit.__get__(node)
    node._publish_order = orch.OrchestratorNode._publish_order.__get__(node)
    node._robot_id = 'amr_1'
    node._epoch = 2
    node._status = {}
    node._event_pub = types.SimpleNamespace(publish=published.append)
    node._status_pub = types.SimpleNamespace(publish=published.append)
    node._fsm = types.SimpleNamespace(request_id='')                 # 트립은 이미 비워졌다
    node._run(out[:2] + [out[3]])
    status, order_done, reset_begin = published
    assert (status.request_id, status.header.stamp) == (RID, 77_500_000_000)
    assert (order_done.name, order_done.request_id, order_done.epoch, order_done.header.stamp) == (
        'ORDER_DONE', RID, 1, 77_500_000_000)
    assert (reset_begin.name, reset_begin.epoch, reset_begin.robot_id) == ('RESET_BEGIN', 2, 'amr_1')


# G5 ----------------------------------------------------------------------------

def returning_after_delivery(**config):
    """1인 배송을 보관함까지 끝내고 복귀 goal 을 막 보낸 트립."""
    machine = gt.trip(**config)
    machine.request(REQUEST)
    token = machine._expected[fsm.GO_TO_ZONE]
    machine.result(fsm.GO_TO_ZONE, fsm.ACCEPTED, token=token)
    machine.result(fsm.GO_TO_ZONE, fsm.ARRIVED, token=token)
    machine.result(fsm.DISPENSE, fsm.ACCEPTED)
    machine.state_update(fsm.BELT, {'occupied': True, 'at_end': True, 'order_id': ORDER}, True)
    machine.state_update(fsm.BELT, {'occupied': False, 'at_end': False, 'order_id': ''}, True)
    machine.result(fsm.PICK_POUCH, fsm.OK)
    token = machine._expected[fsm.GO_TO_ZONE]
    machine.result(fsm.GO_TO_ZONE, fsm.ACCEPTED, token=token)
    machine.result(fsm.GO_TO_ZONE, fsm.ARRIVED, token=token)
    machine.result(fsm.SCAN_TAG, fsm.OK, {'tag_id': 'pt-1001'})
    machine.result(fsm.PICK_POUCH, fsm.OK)
    assert machine.state == fsm.RETURNING and machine.order_states() == {ORDER: 'DELIVERED'}
    return machine


def test_return_rejection_never_marks_lap_success():
    machine = returning_after_delivery()
    dock = machine._expected[fsm.GO_TO_ZONE]
    assert machine.result(fsm.GO_TO_ZONE, fsm.REJECTED, token=dock) == []      # 계약 5절: 5 s 뒤 1회 더
    machine.tick(1.0, 1.0)
    [again] = gt.goals(machine.tick(6.0, 6.0))
    assert again.goal == {'zone_id': 'dock_1'}
    final = machine.result(fsm.GO_TO_ZONE, fsm.REJECTED, token=again.token)
    assert final == [fsm.Finish(False)] and 'DOCKED' not in [e.event for e in events(final)]

    # 도착 못 함도 성공이 아니다(주문이 전부 DELIVERED 여도). 재시도(회차133)는 끄고 끝을 본다.
    machine = returning_after_delivery(return_max_retries=0)
    dock = machine._expected[fsm.GO_TO_ZONE]
    machine.result(fsm.GO_TO_ZONE, fsm.ACCEPTED, token=dock)
    final = machine.result(fsm.GO_TO_ZONE, fsm.NOT_ARRIVED, token=dock)
    assert [c for c in final if isinstance(c, fsm.Finish)] == [fsm.Finish(False)]     # 앞에 '복귀 포기' 줄이 붙는다


def test_reload_stores_reads_the_file_only_after_reset_ok(orch, monkeypatch):
    """재고·선반·사용 표 초기화는 /sim/reset ok 뒤다. 진입 때는 그대로 둔다."""
    document = DISPENSER
    monkeypatch.setattr(orch, 'read_yaml', lambda path: document)
    node = harness(orch, gt.trip())
    node._dispenser_path = 'dispenser.yaml'
    before = load_inventory(document)
    node._fsm.inventory = before
    node._refill = rp.RefillPlanner(before, epoch=1)
    node._used_requests = {RID}
    node._used_orders = {ORDER}
    node._sim_reset.ready = True
    node._on_reset(types.SimpleNamespace(epoch=0), types.SimpleNamespace(ok=None, message=''))
    assert node._fsm.inventory is before and node._used_requests == {RID}
    token = node._fsm._expected[fsm.RESET]
    node._on_service(fsm.RESET, token, types.SimpleNamespace(result=lambda: types.SimpleNamespace(ok=True, message='')))
    assert node._fsm.inventory is not before and node._refill.inventory is node._fsm.inventory
    assert node._used_requests == set() and node._used_orders == set()


def test_drain_timeout_forgets_unterminated_goals(orch, monkeypatch):
    """drain 상한을 넘긴 goal 은 goal 표에서 뺀다. 다음 리셋이 그 goal 을 또 10 s 기다리지 않는다."""
    wall = types.SimpleNamespace(now=0.0)
    monkeypatch.setattr(orch, 'time', types.SimpleNamespace(monotonic=lambda: wall.now))
    monkeypatch.setattr(orch, 'read_yaml', lambda path: DISPENSER)
    node = harness(orch, gt.trip(cancel_wait_s=10.0))
    node._dispenser_path = 'dispenser.yaml'
    node._refill = rp.RefillPlanner(None, epoch=1)
    node._used_requests, node._used_orders = set(), set()
    node._sim_reset.ready = True
    node._run(node._fsm.request(REQUEST))
    [(_, response)] = node._action_clients[fsm.GO_TO_ZONE].sent
    [trip_token] = list(node._goals)
    trip_handle = gt._Handle()
    response.resolve(trip_handle)                                   # 수락됐지만 결과가 안 온다
    refill_token = fsm.Token(1, 'refill', 1)
    node._goals[refill_token] = orch.GoalEntry(rp.REFILL)           # 수락 응답도 안 온다

    node._on_reset(types.SimpleNamespace(epoch=0), types.SimpleNamespace(ok=None, message=''))
    wall.now = 9.9
    node._run(node._fsm.tick(0.0, wall.now))
    assert node._sim_reset.calls == [] and set(node._goals) == {trip_token, refill_token}
    wall.now = 10.0
    node._run(node._fsm.tick(0.0, wall.now))
    assert len(node._sim_reset.calls) == 1
    assert node._goals == {}                                        # 종결이 안 온 두 goal 을 표에서 뺐다

    # 뺀 goal 이 늦게 수락되면 곧바로 cancel 하고 표에 다시 넣지 않는다. 늦은 결과도 표를 안 바꾼다.
    refill_handle = gt._Handle()
    node._on_goal_response(rp.REFILL, refill_token, types.SimpleNamespace(result=lambda: refill_handle))
    assert refill_handle.cancel_calls == 1 and node._goals == {}
    trip_handle.result_future.resolve(gt.result_of(orch, orch.GoalStatus.STATUS_CANCELED, arrived=False, message=''))
    assert node._goals == {}

    token = node._fsm._expected[fsm.RESET]
    node._on_service(fsm.RESET, token, types.SimpleNamespace(result=lambda: types.SimpleNamespace(ok=True, message='')))
    assert node._fsm.state == fsm.IDLE

    # 다음 리셋: 기다릴 goal 이 없으니 wall 이 흐르지 않아도 곧바로 /sim/reset 이다.
    node._on_reset(types.SimpleNamespace(epoch=0), types.SimpleNamespace(ok=None, message=''))
    assert len(node._sim_reset.calls) == 2 and node._epoch == 3


def test_reset_server_discovery_uses_the_whole_reset_timeout(orch, monkeypatch):
    """/sim/reset 서버가 늦게 보여도 reset_timeout_s(30 s wall) 안이면 barrier 가 끝난다. 넘으면 그때 failed."""
    wall = types.SimpleNamespace(now=0.0)
    monkeypatch.setattr(orch, 'time', types.SimpleNamespace(monotonic=lambda: wall.now))
    monkeypatch.setattr(orch, 'read_yaml', lambda path: DISPENSER)

    def barrier():
        node = harness(orch, gt.trip())
        node._server_wait = orch.ServerWait(10.0)
        node._dispenser_path = 'dispenser.yaml'
        node._refill = rp.RefillPlanner(None, epoch=1)
        node._used_requests, node._used_orders = set(), set()
        node._sim_reset.ready = False
        wall.now = 0.0
        node._on_reset(types.SimpleNamespace(epoch=0), types.SimpleNamespace(ok=None, message=''))
        return node

    def tick(node, now):
        wall.now = now
        node._flush_waiting()
        node._run(node._fsm.tick(0.0, now))

    # 서버가 25 s 에 보인다: server_wait_s(10 s) 를 넘었어도 거부하지 않고 부른다.
    node = barrier()
    tick(node, 10.0)
    assert not node._fsm.barrier_failed and node._sim_reset.calls == []
    node._sim_reset.ready = True
    tick(node, 25.0)
    assert len(node._sim_reset.calls) == 1
    token = node._fsm._expected[fsm.RESET]
    node._on_service(fsm.RESET, token, types.SimpleNamespace(result=lambda: types.SimpleNamespace(ok=True, message='')))
    assert node._fsm.state == fsm.IDLE

    # 끝내 안 보이면 30 s 에 failed. 호출은 나가지 않는다.
    node = barrier()
    tick(node, 29.9)
    assert not node._fsm.barrier_failed
    tick(node, 30.0)
    assert node._fsm.barrier_failed and node._sim_reset.calls == []
    assert node._server_wait.tokens() == ()


def test_reset_always_raises_the_epoch_by_one(orch):
    """계약 4절: 리셋마다 +1. 요청의 epoch 는 쓰지 않고 응답 message 에 실제 epoch 를 적는다."""
    node = harness(orch, gt.trip())
    node._refill = rp.RefillPlanner(None, epoch=1)
    node._sim_reset.ready = True
    reply = node._on_reset(types.SimpleNamespace(epoch=7), types.SimpleNamespace(ok=None, message=''))
    assert node._epoch == 2 and node._fsm.epoch == 2
    assert reply.ok and reply.message.startswith('epoch=2 ') and 'epoch=7' in reply.message
    [call] = node._sim_reset.calls
    assert call.epoch == 2
