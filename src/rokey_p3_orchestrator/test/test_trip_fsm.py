"""입력 순서 → 명령 순서 표. ADR 0001 이 요구하는 L1 이다."""

import pytest

from rokey_p3_orchestrator import trip_fsm as fsm
from rokey_p3_orchestrator.dispenser_inventory import DispenserInventory, Slot

ORDER = 'ord-0001'
PATIENT = '1001'
BED = 'bed_a1'
ITEM = 'drug-amox'
#: 기본 request() 의 REQUEST_ACCEPTED detail(표시용 한 줄 JSON)
SINGLE_DETAIL = ('{"mode":0,"destination_id":"bed_a1",'
                 '"orders":[{"order_id":"ord-0001","patient_id":"1001","item_id":"drug-amox"}]}')


def request(mode=fsm.MODE_SINGLE, orders=None):
    return {
        'request_id': 'r001-0001',
        'mode': mode,
        'destination_id': BED,
        'orders': [{'order_id': ORDER, 'patient_id': PATIENT, 'item_id': ITEM}]
                  if orders is None else orders,
    }


def belt(occupied=False, at_end=False, order_id=''):
    return {'occupied': occupied, 'at_end': at_end, 'order_id': order_id}


def make(inventory=None, **config):
    machine = fsm.TripFsm(config=fsm.TripConfig(**config), inventory=inventory,
                          patient_beds={PATIENT: BED, '1002': 'bed_a2'})
    machine.tick(0.0)
    machine.state_update(fsm.AT_HOME, True, True)
    machine.state_update(fsm.BASE_STOPPED, True, True)
    machine.state_update(fsm.BELT, belt(), True)
    return machine


def events(commands):
    return [c.event for c in commands if isinstance(c, fsm.Emit)]


def run_one_lap(machine, collected):
    """1인 배송 정상 한 바퀴. 각 단계의 명령을 collected 에 이어 붙인다."""
    collected += machine.request(request())
    collected += machine.result(fsm.GO_TO_ZONE, fsm.ACCEPTED)
    collected += machine.result(fsm.GO_TO_ZONE, fsm.ARRIVED)
    collected += machine.result(fsm.DISPENSE, fsm.ACCEPTED)
    collected += machine.state_update(fsm.BELT, belt(True, True, ORDER), True)
    collected += machine.result(fsm.PICK_POUCH, fsm.ACCEPTED)
    collected += machine.state_update(fsm.BELT, belt(), True)
    collected += machine.result(fsm.PICK_POUCH, fsm.OK)
    collected += machine.result(fsm.GO_TO_ZONE, fsm.ACCEPTED)
    collected += machine.result(fsm.GO_TO_ZONE, fsm.ARRIVED)
    collected += machine.result(fsm.SCAN_TAG, fsm.ACCEPTED)
    collected += machine.result(fsm.SCAN_TAG, fsm.OK, {'tag_id': 'pt-1001'})
    collected += machine.result(fsm.PICK_POUCH, fsm.ACCEPTED)
    collected += machine.result(fsm.PICK_POUCH, fsm.OK)
    collected += machine.result(fsm.GO_TO_ZONE, fsm.ACCEPTED)
    collected += machine.result(fsm.GO_TO_ZONE, fsm.ARRIVED)
    return collected


# 정상 한 바퀴 ------------------------------------------------------------

def test_one_lap_emits_the_contract_2_6_order():
    commands = run_one_lap(make(), [])
    assert events(commands) == [
        'REQUEST_ACCEPTED', 'AMR_DOCKED_LOAD', 'LOAD_DONE', 'DEPARTED', 'ARRIVED',
        'AUTH_OK', 'CABINET_LOCKED', 'ORDER_DONE', 'RETURNED', 'DOCKED',
    ]


def test_one_lap_command_sequence():
    machine = make()
    commands = run_one_lap(machine, [])
    assert commands == [
        fsm.Emit('REQUEST_ACCEPTED', 'r001-0001', detail=SINGLE_DETAIL),
        fsm.OrderState(ORDER, 'ACCEPTED'),
        fsm.SendGoal(fsm.GO_TO_ZONE, {'zone_id': 'load'}),
        fsm.Emit('AMR_DOCKED_LOAD', 'r001-0001'),
        fsm.Call(fsm.DISPENSE, {'request_id': 'r001-0001', 'order_id': ORDER}),
        fsm.OrderState(ORDER, 'DISPENSED'),
        fsm.SendGoal(fsm.PICK_POUCH, {'order_id': ORDER, 'source': 'BELT', 'target_slot': 0}),
        fsm.OrderState(ORDER, 'LOADED'),
        fsm.Emit('LOAD_DONE', 'r001-0001'),
        fsm.SendGoal(fsm.GO_TO_ZONE, {'zone_id': BED}),
        fsm.Emit('DEPARTED', 'r001-0001'),
        fsm.Emit('ARRIVED', 'r001-0001'),
        fsm.SendGoal(fsm.SCAN_TAG, {'kind': 'patient', 'zone_id': BED}),
        fsm.Emit('AUTH_OK', 'r001-0001'),
        fsm.SendGoal(fsm.PICK_POUCH, {'order_id': ORDER, 'source': 'DECK', 'target_slot': -1,
                                      'zone_id': BED}),
        fsm.Emit('CABINET_LOCKED', 'r001-0001', ORDER),
        fsm.OrderState(ORDER, 'DELIVERED'),
        fsm.Emit('ORDER_DONE', 'r001-0001', ORDER),
        fsm.SendGoal(fsm.GO_TO_ZONE, {'zone_id': 'dock_1'}),
        fsm.Emit('RETURNED', 'r001-0001'),
        fsm.Emit('DOCKED', 'r001-0001'),
        fsm.Finish(True),
    ]
    assert machine.state == fsm.IDLE
    assert not machine.busy


def test_urgent_emits_arriving_once_and_only_when_close():
    machine = fsm.TripFsm(patient_beds={PATIENT: BED})
    machine.tick(0.0)
    for name, value in ((fsm.AT_HOME, True), (fsm.BASE_STOPPED, True)):
        machine.state_update(name, value, True)
    machine.state_update(fsm.BELT, belt(), True)
    machine.request(request(mode=fsm.MODE_URGENT))
    machine.result(fsm.GO_TO_ZONE, fsm.ACCEPTED)
    machine.result(fsm.GO_TO_ZONE, fsm.ARRIVED)
    machine.result(fsm.DISPENSE, fsm.ACCEPTED)
    machine.state_update(fsm.BELT, belt(True, True, ORDER), True)
    machine.result(fsm.PICK_POUCH, fsm.OK)
    machine.result(fsm.GO_TO_ZONE, fsm.ACCEPTED)
    assert machine.state == fsm.TRANSIT
    assert machine.feedback(fsm.GO_TO_ZONE, 9.0) == []
    assert events(machine.feedback(fsm.GO_TO_ZONE, 2.0)) == ['ARRIVING']
    assert machine.feedback(fsm.GO_TO_ZONE, 1.0) == []


# 조제실 구간만 (pharmacy_only) --------------------------------------------

def test_pharmacy_only_lap_input_to_command_table():
    """일정 P2 1차 시연: 요청 → 배출 → 픽 → 적재 → 도크 복귀. 정거장으로 가지 않는다."""
    machine = make(pharmacy_only=True)
    rid = 'r001-0001'
    assert machine.request(request()) == [
        fsm.Emit('REQUEST_ACCEPTED', rid, detail=SINGLE_DETAIL),
        fsm.OrderState(ORDER, 'ACCEPTED'),
        fsm.SendGoal(fsm.GO_TO_ZONE, {'zone_id': 'load'}),
    ]
    assert machine.result(fsm.GO_TO_ZONE, fsm.ACCEPTED) == []
    assert machine.result(fsm.GO_TO_ZONE, fsm.ARRIVED) == [
        fsm.Emit('AMR_DOCKED_LOAD', rid),
        fsm.Call(fsm.DISPENSE, {'request_id': rid, 'order_id': ORDER}),
    ]
    assert machine.result(fsm.DISPENSE, fsm.ACCEPTED) == [fsm.OrderState(ORDER, 'DISPENSED')]
    assert machine.state_update(fsm.BELT, belt(True, True, ORDER), True) == [
        fsm.SendGoal(fsm.PICK_POUCH, {'order_id': ORDER, 'source': 'BELT', 'target_slot': 0}),
    ]
    assert machine.result(fsm.PICK_POUCH, fsm.ACCEPTED) == []
    assert machine.state_update(fsm.BELT, belt(), True) == []
    assert machine.state_update(fsm.AT_HOME, False, True) == []      # 팔이 홈을 떠났다
    # 적재 끝. 주문은 at_home 을 기다리지 않고 닫는다. 그래서 ORDER_DONE 이 ARM_HOME 보다 앞이다.
    assert machine.result(fsm.PICK_POUCH, fsm.OK) == [
        fsm.OrderState(ORDER, 'LOADED'),
        fsm.Emit('LOAD_DONE', rid),
        fsm.OrderState(ORDER, 'HOLD_RETURN', 'pharmacy_only'),
        fsm.Emit('ORDER_DONE', rid, ORDER),
    ]
    assert machine.state == fsm.RETURNING
    assert machine.state_update(fsm.AT_HOME, True, True) == [
        fsm.SendGoal(fsm.GO_TO_ZONE, {'zone_id': 'dock_1'}),
    ]
    assert machine.result(fsm.GO_TO_ZONE, fsm.ACCEPTED) == [fsm.Emit('RETURNED', rid)]
    assert machine.result(fsm.GO_TO_ZONE, fsm.ARRIVED) == [
        fsm.Emit('DOCKED', rid),
        fsm.Finish(False),      # 모든 주문이 DELIVERED 가 아니다. 주장은 false 가 맞다
    ]
    assert machine.order_states() == {ORDER: 'HOLD_RETURN'}
    assert machine.order_reasons() == {ORDER: 'pharmacy_only'}
    assert machine.state == fsm.IDLE


def test_pharmacy_only_blocked_belt_takes_the_same_branch():
    """벨트 막힘도 LOAD_DONE 뒤 같은 분기로 간다. 실은 것은 HOLD_RETURN, 못 나온 것은 ABORT."""
    machine = make(pharmacy_only=True)
    orders = [{'order_id': ORDER, 'patient_id': PATIENT, 'item_id': ITEM},
              {'order_id': 'ord-0002', 'patient_id': '1002', 'item_id': ITEM}]
    machine.request(request(mode=fsm.MODE_BATCH_ROOM, orders=orders))
    machine.result(fsm.GO_TO_ZONE, fsm.ACCEPTED)
    machine.result(fsm.GO_TO_ZONE, fsm.ARRIVED)
    machine.result(fsm.DISPENSE, fsm.ACCEPTED)
    machine.state_update(fsm.BELT, belt(True, True, ORDER), True)
    machine.state_update(fsm.BELT, belt(), True)
    machine.result(fsm.PICK_POUCH, fsm.OK)
    machine.result(fsm.DISPENSE, fsm.ACCEPTED)
    machine.state_update(fsm.BELT, belt(occupied=True), True)
    assert machine.tick(25.0) == [
        fsm.OrderState('ord-0002', 'ABORT', 'belt_timeout'),
        fsm.Emit('ORDER_DONE', 'r001-0001', 'ord-0002'),
        fsm.Emit('LOAD_DONE', 'r001-0001'),
        fsm.OrderState(ORDER, 'HOLD_RETURN', 'pharmacy_only'),
        fsm.Emit('ORDER_DONE', 'r001-0001', ORDER),
        fsm.SendGoal(fsm.GO_TO_ZONE, {'zone_id': 'dock_1'}),
    ]


# guard = 인터락 ----------------------------------------------------------

def test_no_goal_while_at_home_is_unknown():
    machine = fsm.TripFsm(patient_beds={PATIENT: BED})
    machine.tick(0.0)
    machine.state_update(fsm.BELT, belt(), True)
    commands = machine.request(request())
    assert [c for c in commands if isinstance(c, fsm.SendGoal)] == []
    assert machine.state == fsm.DISPATCHING


def test_stale_at_home_is_not_permission():
    machine = fsm.TripFsm(patient_beds={PATIENT: BED})
    machine.tick(0.0)
    machine.state_update(fsm.BELT, belt(), True)
    machine.request(request())
    assert machine.state_update(fsm.AT_HOME, True, False) == []
    commands = machine.state_update(fsm.AT_HOME, True, True)
    assert commands == [fsm.SendGoal(fsm.GO_TO_ZONE, {'zone_id': 'load'})]


def test_belt_pick_waits_for_base_stopped():
    machine = make()
    machine.state_update(fsm.BASE_STOPPED, False, True)
    machine.request(request())
    machine.result(fsm.GO_TO_ZONE, fsm.ACCEPTED)
    machine.result(fsm.GO_TO_ZONE, fsm.ARRIVED)
    machine.result(fsm.DISPENSE, fsm.ACCEPTED)
    assert machine.state_update(fsm.BELT, belt(True, True, ORDER), True) == []
    commands = machine.state_update(fsm.BASE_STOPPED, True, True)
    assert commands == [fsm.SendGoal(fsm.PICK_POUCH,
                                     {'order_id': ORDER, 'source': 'BELT', 'target_slot': 0})]


def test_scan_tag_waits_for_base_stopped():
    """계약 5절의 팔 동작 guard 는 PickPouch 와 ScanTag 둘 다다."""
    machine = make()
    machine.request(request())
    machine.result(fsm.GO_TO_ZONE, fsm.ACCEPTED)
    machine.result(fsm.GO_TO_ZONE, fsm.ARRIVED)
    machine.result(fsm.DISPENSE, fsm.ACCEPTED)
    machine.state_update(fsm.BELT, belt(True, True, ORDER), True)
    machine.state_update(fsm.BELT, belt(), True)
    machine.result(fsm.PICK_POUCH, fsm.OK)
    machine.result(fsm.GO_TO_ZONE, fsm.ACCEPTED)
    # 도착 직후에는 아직 정지 신호가 안 왔을 수 있다.
    machine.state_update(fsm.BASE_STOPPED, False, True)
    commands = machine.result(fsm.GO_TO_ZONE, fsm.ARRIVED)
    assert events(commands) == ['ARRIVED']
    assert [c for c in commands if isinstance(c, fsm.SendGoal)] == []
    assert machine.state == fsm.AUTHENTICATING
    resumed = machine.state_update(fsm.BASE_STOPPED, True, True)
    assert resumed == [fsm.SendGoal(fsm.SCAN_TAG, {'kind': 'patient', 'zone_id': BED})]


def test_belt_pick_waits_for_the_matching_order_id():
    machine = make()
    machine.request(request())
    machine.result(fsm.GO_TO_ZONE, fsm.ACCEPTED)
    machine.result(fsm.GO_TO_ZONE, fsm.ARRIVED)
    machine.result(fsm.DISPENSE, fsm.ACCEPTED)
    assert machine.state_update(fsm.BELT, belt(True, True, 'ord-9999'), True) == []
    assert machine.state == fsm.WAIT_BELT


# 실패 → 종료 상태 ---------------------------------------------------------

def test_dispense_rejected_three_times_aborts_the_order():
    machine = make()
    machine.request(request())
    machine.result(fsm.GO_TO_ZONE, fsm.ACCEPTED)
    machine.result(fsm.GO_TO_ZONE, fsm.ARRIVED)
    for attempt in range(2):
        assert machine.result(fsm.DISPENSE, fsm.REJECTED, {'message': 'not_ready'}) == []
        machine.tick(10.0 * (attempt + 1))
    commands = machine.result(fsm.DISPENSE, fsm.REJECTED, {'message': 'not_ready'})
    assert fsm.OrderState(ORDER, 'ABORT', 'not_ready') in commands
    assert 'ORDER_DONE' in events(commands)


def test_dropped_pouch_aborts_without_retry():
    machine = make()
    machine.request(request())
    machine.result(fsm.GO_TO_ZONE, fsm.ACCEPTED)
    machine.result(fsm.GO_TO_ZONE, fsm.ARRIVED)
    machine.result(fsm.DISPENSE, fsm.ACCEPTED)
    machine.state_update(fsm.BELT, belt(True, True, ORDER), True)
    machine.state_update(fsm.BELT, belt(), True)
    commands = machine.result(fsm.PICK_POUCH, fsm.DROPPED)
    assert fsm.OrderState(ORDER, 'ABORT', 'dropped') in commands
    assert machine.order_states()[ORDER] == 'ABORT'


@pytest.mark.parametrize('outcome', ['grasp_failed', 'qr_mismatch', 'rejected_interlock'])
def test_failed_belt_pick_is_retried_once_then_aborts(outcome):
    machine = make()
    machine.request(request())
    machine.result(fsm.GO_TO_ZONE, fsm.ACCEPTED)
    machine.result(fsm.GO_TO_ZONE, fsm.ARRIVED)
    machine.result(fsm.DISPENSE, fsm.ACCEPTED)
    machine.state_update(fsm.BELT, belt(True, True, ORDER), True)
    retry = machine.result(fsm.PICK_POUCH, outcome)
    assert retry == [fsm.SendGoal(fsm.PICK_POUCH,
                                  {'order_id': ORDER, 'source': 'BELT', 'target_slot': 0})]
    commands = machine.result(fsm.PICK_POUCH, outcome)
    assert fsm.OrderState(ORDER, 'ABORT', outcome) in commands


def test_auth_mismatch_holds_the_order_and_returns():
    machine = make()
    run = []
    machine.request(request())
    machine.result(fsm.GO_TO_ZONE, fsm.ACCEPTED)
    machine.result(fsm.GO_TO_ZONE, fsm.ARRIVED)
    machine.result(fsm.DISPENSE, fsm.ACCEPTED)
    machine.state_update(fsm.BELT, belt(True, True, ORDER), True)
    machine.result(fsm.PICK_POUCH, fsm.OK)
    machine.result(fsm.GO_TO_ZONE, fsm.ACCEPTED)
    machine.result(fsm.GO_TO_ZONE, fsm.ARRIVED)
    run += machine.result(fsm.SCAN_TAG, fsm.OK, {'tag_id': 'pt-9999'})
    assert events(run)[:2] == ['AUTH_FAIL', 'ORDER_DONE']
    assert fsm.OrderState(ORDER, 'HOLD_RETURN', 'auth_mismatch') in run
    run += machine.result(fsm.GO_TO_ZONE, fsm.ACCEPTED)
    run += machine.result(fsm.GO_TO_ZONE, fsm.ARRIVED)
    assert fsm.Finish(False) in run


def test_unreadable_tag_is_retried_once():
    machine = make()
    machine.request(request())
    machine.result(fsm.GO_TO_ZONE, fsm.ACCEPTED)
    machine.result(fsm.GO_TO_ZONE, fsm.ARRIVED)
    machine.result(fsm.DISPENSE, fsm.ACCEPTED)
    machine.state_update(fsm.BELT, belt(True, True, ORDER), True)
    machine.result(fsm.PICK_POUCH, fsm.OK)
    machine.result(fsm.GO_TO_ZONE, fsm.ACCEPTED)
    machine.result(fsm.GO_TO_ZONE, fsm.ARRIVED)
    retry = machine.result(fsm.SCAN_TAG, fsm.UNREADABLE)
    assert retry == [fsm.SendGoal(fsm.SCAN_TAG, {'kind': 'patient', 'zone_id': BED})]
    commands = machine.result(fsm.SCAN_TAG, fsm.UNREADABLE)
    assert events(commands)[0] == 'AUTH_FAIL'
    assert machine.order_states()[ORDER] == 'HOLD_RETURN'


def test_go_to_zone_rejected_twice_aborts_orders_not_yet_loaded():
    """HOLD_RETURN 은 상판에 실은 주문만이다. 적재 위치에도 못 간 주문은 같은 reason 으로 ABORT."""
    machine = make()
    machine.request(request())
    assert machine.result(fsm.GO_TO_ZONE, fsm.REJECTED) == []
    machine.tick(1.0)
    assert machine.state == fsm.DISPATCHING     # 5 s 전에는 다시 보내지 않는다
    resend = machine.tick(6.0)
    assert resend == [fsm.SendGoal(fsm.GO_TO_ZONE, {'zone_id': 'load'})]
    commands = machine.result(fsm.GO_TO_ZONE, fsm.REJECTED)
    assert fsm.OrderState(ORDER, 'ABORT', 'goto_rejected') in commands
    assert machine.order_states() == {ORDER: 'ABORT'}


def test_transit_timeout_holds_the_order():
    machine = make()
    machine.request(request())
    machine.result(fsm.GO_TO_ZONE, fsm.ACCEPTED)
    machine.result(fsm.GO_TO_ZONE, fsm.ARRIVED)
    machine.result(fsm.DISPENSE, fsm.ACCEPTED)
    machine.state_update(fsm.BELT, belt(True, True, ORDER), True)
    machine.result(fsm.PICK_POUCH, fsm.OK)
    machine.result(fsm.GO_TO_ZONE, fsm.ACCEPTED)
    commands = machine.result(fsm.GO_TO_ZONE, fsm.NOT_ARRIVED)
    assert fsm.OrderState(ORDER, 'HOLD_RETURN', 'transit_not_arrived') in commands


def test_belt_timeout_aborts_and_blocked_belt_stops_the_rest():
    machine = make(belt_timeout_s=20.0)
    machine.request(request())
    machine.result(fsm.GO_TO_ZONE, fsm.ACCEPTED)
    machine.result(fsm.GO_TO_ZONE, fsm.ARRIVED)
    machine.result(fsm.DISPENSE, fsm.ACCEPTED)
    machine.state_update(fsm.BELT, belt(occupied=True), True)
    commands = machine.tick(25.0)
    assert fsm.OrderState(ORDER, 'ABORT', 'belt_timeout') in commands
    assert 'LOAD_DONE' in events(commands)


BATCH = [{'order_id': ORDER, 'patient_id': PATIENT, 'item_id': ITEM},
         {'order_id': 'ord-0002', 'patient_id': '1002', 'item_id': ITEM}]


def test_give_up_holds_loaded_orders_and_aborts_the_rest():
    """실은 주문 1 + 미배출 1 에서 포기하면 HOLD_RETURN / ABORT 로 나뉜다.

    지금 입력으로는 이 조합에서 포기 경로(_give_up_all)에 닿지 않는다. 출발은 미배출이 없을 때만
    하기 때문이다. 경로가 생겨도 규칙이 지켜지도록 내부 함수를 직접 불러 고정해 둔다.
    """
    machine = make()
    machine.request(request(mode=fsm.MODE_BATCH_ROOM, orders=BATCH))
    machine.result(fsm.GO_TO_ZONE, fsm.ACCEPTED)
    machine.result(fsm.GO_TO_ZONE, fsm.ARRIVED)
    machine.result(fsm.DISPENSE, fsm.ACCEPTED)
    machine.state_update(fsm.BELT, belt(True, True, ORDER), True)
    machine.result(fsm.PICK_POUCH, fsm.OK)
    assert machine.order_states() == {ORDER: 'LOADED', 'ord-0002': 'ACCEPTED'}
    assert machine._give_up_all('goto_rejected') == [
        fsm.OrderState(ORDER, 'HOLD_RETURN', 'goto_rejected'),
        fsm.Emit('ORDER_DONE', 'r001-0001', ORDER),
        fsm.OrderState('ord-0002', 'ABORT', 'goto_rejected'),
        fsm.Emit('ORDER_DONE', 'r001-0001', 'ord-0002'),
    ]


def test_failed_belt_pick_leaves_the_pouch_and_blocks_the_rest():
    """픽이 두 번 실패한 봉투가 벨트에 남으면 치울 주체가 없다. 기다리지 않고 남은 주문을 닫고 떠난다."""
    machine = make()
    machine.request(request(mode=fsm.MODE_BATCH_ROOM, orders=BATCH))
    machine.result(fsm.GO_TO_ZONE, fsm.ACCEPTED)
    machine.result(fsm.GO_TO_ZONE, fsm.ARRIVED)
    machine.result(fsm.DISPENSE, fsm.ACCEPTED)
    machine.state_update(fsm.BELT, belt(True, True, ORDER), True)
    machine.result(fsm.PICK_POUCH, 'grasp_failed')                   # 1회 재시도
    commands = machine.result(fsm.PICK_POUCH, 'grasp_failed')        # 벨트는 여전히 occupied
    assert commands == [
        fsm.OrderState(ORDER, 'ABORT', 'grasp_failed'),
        fsm.Emit('ORDER_DONE', 'r001-0001', ORDER),
        fsm.OrderState('ord-0002', 'ABORT', 'belt_blocked'),
        fsm.Emit('ORDER_DONE', 'r001-0001', 'ord-0002'),
        fsm.Emit('LOAD_DONE', 'r001-0001'),
        fsm.SendGoal(fsm.GO_TO_ZONE, {'zone_id': 'dock_1'}),          # 실은 것이 없어 바로 복귀
    ]
    later = machine.tick(1.0)
    assert [c for c in commands + later if isinstance(c, fsm.Call)] == []
    assert machine.state == fsm.RETURNING


def test_successful_pick_is_not_a_blocked_belt():
    """픽 결과가 벨트 신호보다 먼저 와도 그 주문은 LOADED 라 막힘이 아니다. 벨트가 비면 다음을 배출한다."""
    machine = make()
    machine.request(request(mode=fsm.MODE_BATCH_ROOM, orders=BATCH))
    machine.result(fsm.GO_TO_ZONE, fsm.ACCEPTED)
    machine.result(fsm.GO_TO_ZONE, fsm.ARRIVED)
    machine.result(fsm.DISPENSE, fsm.ACCEPTED)
    machine.state_update(fsm.BELT, belt(True, True, ORDER), True)
    assert machine.result(fsm.PICK_POUCH, fsm.OK) == [fsm.OrderState(ORDER, 'LOADED')]
    assert machine.state_update(fsm.BELT, belt(), True) == [
        fsm.Call(fsm.DISPENSE, {'request_id': 'r001-0001', 'order_id': 'ord-0002'}),
    ]


def test_trip_limit_closes_open_orders_with_timeout():
    machine = make(trip_limit_s=100.0)
    machine.request(request())
    machine.result(fsm.GO_TO_ZONE, fsm.ACCEPTED)
    commands = machine.tick(200.0)
    assert fsm.OrderState(ORDER, 'TIMEOUT', 'trip_limit') in commands
    assert machine.state == fsm.RETURNING


# 리셋과 이전 epoch --------------------------------------------------------

def test_reset_closes_the_trip_announces_the_barrier_and_calls_the_service_after_cancel():
    """barrier v2: 끊긴 주문 종료 → Finish → RESET_BEGIN → Cancel. /sim/reset 은 goal 이 종결된 뒤다."""
    machine = make()
    [load] = [c for c in machine.request(request()) if isinstance(c, fsm.SendGoal)]
    commands = machine.reset(2)
    assert commands == [
        fsm.OrderState(ORDER, 'ABORT', 'reset_interrupted'),
        fsm.Emit('ORDER_DONE', 'r001-0001', ORDER),
        fsm.Finish(False, True),
        fsm.Emit('RESET_BEGIN'),
        fsm.Cancel(fsm.GO_TO_ZONE),
    ]
    assert machine.state == fsm.RESETTING
    assert machine.result(fsm.GO_TO_ZONE, fsm.CANCELED, token=load.token) == [fsm.Call(fsm.RESET, {'epoch': 2})]


def test_results_from_the_old_epoch_are_dropped_while_resetting():
    machine = make()
    machine.request(request())
    machine.reset(2)
    assert machine.result(fsm.GO_TO_ZONE, fsm.ARRIVED) == []
    assert machine.state == fsm.RESETTING


def test_reset_done_returns_to_idle():
    machine = make()
    [load] = [c for c in machine.request(request()) if isinstance(c, fsm.SendGoal)]
    machine.reset(2)
    machine.result(fsm.GO_TO_ZONE, fsm.CANCELED, token=load.token)
    commands = machine.result(fsm.RESET, fsm.OK)
    assert commands == [fsm.ReloadStores(), fsm.Emit('RESET_DONE')]
    assert machine.state == fsm.IDLE
    assert machine.accepts(request())


# 수락 조건과 재고 ---------------------------------------------------------

def test_second_request_is_refused_while_a_trip_runs():
    machine = make()
    machine.request(request())
    assert not machine.accepts(request())
    assert machine.request(request()) == []


def test_empty_order_list_is_refused():
    machine = make()
    assert machine.request(request(orders=[])) == []


def test_refusal_names_the_running_trip_and_its_state():
    machine = make()
    assert machine.refusal(request()) is None
    machine.request(request())
    reason = machine.refusal(request())
    assert reason.startswith('진행 중 트립이 있다')
    assert machine.state in reason and 'r001-0001' in reason


def test_refusal_names_orders_whose_bed_is_unknown():
    machine = make()
    orders = [{'order_id': ORDER, 'patient_id': PATIENT, 'item_id': ITEM},
              {'order_id': 'ord-0003', 'patient_id': '1003', 'item_id': ITEM}]
    body = request(mode=fsm.MODE_BATCH_ROOM, orders=orders)
    reason = machine.refusal(body)
    assert not machine.accepts(body)
    assert reason.startswith('정거장을 만들 수 없다') and 'ord-0003' in reason and 'ord-0001' not in reason


def test_refusal_for_batch_ward_without_destination_and_multi_order_single():
    machine = make()
    ward = request(mode=fsm.MODE_BATCH_WARD)
    ward['destination_id'] = ''
    assert 'destination_id' in machine.refusal(ward)
    two = [{'order_id': ORDER, 'patient_id': PATIENT, 'item_id': ITEM},
           {'order_id': 'ord-0002', 'patient_id': '1002', 'item_id': ITEM}]
    assert '2개' in machine.refusal(request(orders=two))
    assert machine.refusal(request(orders=[])) == 'orders 가 비었다'


def test_batch_room_makes_one_stop_per_bed():
    machine = make()
    orders = [{'order_id': ORDER, 'patient_id': PATIENT, 'item_id': ITEM},
              {'order_id': 'ord-0002', 'patient_id': '1002', 'item_id': ITEM}]
    machine.request(request(mode=fsm.MODE_BATCH_ROOM, orders=orders))
    assert [stop.zone_id for stop in machine.stops()] == ['bed_a1', 'bed_a2']
    assert [stop.tag_id for stop in machine.stops()] == ['pt-1001', 'pt-1002']


def test_batch_ward_makes_one_station_stop():
    machine = make()
    orders = [{'order_id': ORDER, 'patient_id': PATIENT, 'item_id': ITEM}]
    body = request(mode=fsm.MODE_BATCH_WARD, orders=orders)
    body['destination_id'] = 'station_a'
    machine.request(body)
    assert machine.stops() == (fsm.Stop('station_a', 'station', 'st-station_a', (ORDER,)),)


# 묶음: 정거장마다 이동·인증 (계약 2.6 "ARRIVED 부터 ORDER_DONE 까지를 침상마다 반복") ----------

def load(machine, body, drop=()):
    """요청 → 적재. drop 에 든 주문은 벨트 픽에서 떨어뜨려 ABORT 한다. 첫 출발 goal 까지의 명령을 돌려준다."""
    out = machine.request(body)
    out += machine.result(fsm.GO_TO_ZONE, fsm.ACCEPTED)
    out += machine.result(fsm.GO_TO_ZONE, fsm.ARRIVED)
    for row in body['orders']:
        order_id = row['order_id']
        out += machine.result(fsm.DISPENSE, fsm.ACCEPTED)
        out += machine.state_update(fsm.BELT, belt(True, True, order_id), True)
        out += machine.result(fsm.PICK_POUCH, fsm.ACCEPTED)
        out += machine.state_update(fsm.BELT, belt(), True)
        out += machine.result(fsm.PICK_POUCH, fsm.DROPPED if order_id in drop else fsm.OK)
    return out


def arrive_and_scan(machine, tag_id):
    """출발 goal 수락 → 도착 → ScanTag 결과. 인증 뒤 첫 명령까지 돌려준다."""
    out = machine.result(fsm.GO_TO_ZONE, fsm.ACCEPTED)
    out += machine.result(fsm.GO_TO_ZONE, fsm.ARRIVED)
    out += machine.result(fsm.SCAN_TAG, fsm.ACCEPTED)
    out += machine.result(fsm.SCAN_TAG, fsm.OK, {'tag_id': tag_id})
    return out


def deliver(machine, outcome=fsm.OK):
    out = machine.result(fsm.PICK_POUCH, fsm.ACCEPTED)
    return out + machine.result(fsm.PICK_POUCH, outcome)


def goals(commands, action):
    return [c.goal for c in commands if isinstance(c, fsm.SendGoal) and c.action == action]


def test_batch_room_moves_and_authenticates_at_every_bed():
    machine = make()
    run = load(machine, request(mode=fsm.MODE_BATCH_ROOM, orders=BATCH))
    run += arrive_and_scan(machine, 'pt-1001')
    run += deliver(machine)
    run += arrive_and_scan(machine, 'pt-1002')
    run += deliver(machine)
    run += machine.result(fsm.GO_TO_ZONE, fsm.ACCEPTED)
    run += machine.result(fsm.GO_TO_ZONE, fsm.ARRIVED)
    assert events(run) == [
        'REQUEST_ACCEPTED', 'AMR_DOCKED_LOAD', 'LOAD_DONE',
        'DEPARTED', 'ARRIVED', 'AUTH_OK', 'CABINET_LOCKED', 'ORDER_DONE',
        'DEPARTED', 'ARRIVED', 'AUTH_OK', 'CABINET_LOCKED', 'ORDER_DONE',
        'RETURNED', 'DOCKED',
    ]
    assert goals(run, fsm.GO_TO_ZONE) == [{'zone_id': z} for z in ('load', 'bed_a1', 'bed_a2', 'dock_1')]
    assert goals(run, fsm.SCAN_TAG) == [{'kind': 'patient', 'zone_id': 'bed_a1'},
                                        {'kind': 'patient', 'zone_id': 'bed_a2'}]
    assert machine.order_states() == {ORDER: 'DELIVERED', 'ord-0002': 'DELIVERED'}
    assert fsm.Finish(True) in run


def test_batch_room_first_bed_done_sends_the_next_move_not_the_next_pick():
    """이전 코드는 여기서 GoToZone·ScanTag 없이 ord-0002 의 PickPouch(DECK) 를 보냈다(ADR 0001 대조 1)."""
    machine = make()
    load(machine, request(mode=fsm.MODE_BATCH_ROOM, orders=BATCH))
    arrive_and_scan(machine, 'pt-1001')
    commands = deliver(machine)
    assert commands == [
        fsm.Emit('CABINET_LOCKED', 'r001-0001', ORDER),
        fsm.OrderState(ORDER, 'DELIVERED'),
        fsm.Emit('ORDER_DONE', 'r001-0001', ORDER),
        fsm.SendGoal(fsm.GO_TO_ZONE, {'zone_id': 'bed_a2'}),
    ]
    picks = arrive_and_scan(machine, 'pt-1002')
    assert goals(picks, fsm.PICK_POUCH) == [{'order_id': 'ord-0002', 'source': 'DECK',
                                            'target_slot': -1, 'zone_id': 'bed_a2'}]


def test_batch_room_auth_failure_at_first_bed_still_visits_the_second():
    machine = make()
    load(machine, request(mode=fsm.MODE_BATCH_ROOM, orders=BATCH))
    commands = arrive_and_scan(machine, 'pt-9999')
    assert fsm.OrderState(ORDER, 'HOLD_RETURN', 'auth_mismatch') in commands
    assert goals(commands, fsm.PICK_POUCH) == []
    assert goals(commands, fsm.GO_TO_ZONE) == [{'zone_id': 'bed_a2'}]
    picks = arrive_and_scan(machine, 'pt-1002')
    assert goals(picks, fsm.PICK_POUCH) == [{'order_id': 'ord-0002', 'source': 'DECK',
                                            'target_slot': -1, 'zone_id': 'bed_a2'}]


def test_batch_room_dropped_pouch_at_first_bed_still_moves_before_the_next_pick():
    machine = make()
    load(machine, request(mode=fsm.MODE_BATCH_ROOM, orders=BATCH))
    arrive_and_scan(machine, 'pt-1001')
    commands = deliver(machine, fsm.DROPPED)
    assert fsm.OrderState(ORDER, 'ABORT', 'dropped') in commands
    assert goals(commands, fsm.PICK_POUCH) == []
    assert goals(commands, fsm.GO_TO_ZONE) == [{'zone_id': 'bed_a2'}]


def test_batch_room_skips_a_bed_whose_order_was_not_loaded():
    first_lost = make()
    departure = load(first_lost, request(mode=fsm.MODE_BATCH_ROOM, orders=BATCH), drop=(ORDER,))
    assert goals(departure, fsm.GO_TO_ZONE)[-1] == {'zone_id': 'bed_a2'}

    second_lost = make()
    load(second_lost, request(mode=fsm.MODE_BATCH_ROOM, orders=BATCH), drop=('ord-0002',))
    arrive_and_scan(second_lost, 'pt-1001')
    commands = deliver(second_lost)
    assert goals(commands, fsm.GO_TO_ZONE) == [{'zone_id': 'dock_1'}]
    assert second_lost.state == fsm.RETURNING


def test_batch_room_two_orders_for_one_bed_authenticate_once():
    machine = make()
    same_bed = [{'order_id': ORDER, 'patient_id': PATIENT, 'item_id': ITEM},
                {'order_id': 'ord-0002', 'patient_id': PATIENT, 'item_id': ITEM}]
    run = load(machine, request(mode=fsm.MODE_BATCH_ROOM, orders=same_bed))
    run += arrive_and_scan(machine, 'pt-1001')
    run += deliver(machine)
    run += deliver(machine)
    assert goals(run, fsm.SCAN_TAG) == [{'kind': 'patient', 'zone_id': 'bed_a1'}]
    assert [g['order_id'] for g in goals(run, fsm.PICK_POUCH) if g['source'] == 'DECK'] == [ORDER, 'ord-0002']
    assert goals(run, fsm.GO_TO_ZONE)[-1] == {'zone_id': 'dock_1'}


def test_batch_ward_authenticates_the_station_once_and_places_every_order():
    machine = make()
    body = request(mode=fsm.MODE_BATCH_WARD, orders=BATCH)
    body['destination_id'] = 'station_a'
    run = load(machine, body)
    run += arrive_and_scan(machine, 'st-station_a')
    run += deliver(machine)
    run += deliver(machine)
    run += machine.result(fsm.GO_TO_ZONE, fsm.ACCEPTED)
    run += machine.result(fsm.GO_TO_ZONE, fsm.ARRIVED)
    assert goals(run, fsm.GO_TO_ZONE) == [{'zone_id': z} for z in ('load', 'station_a', 'dock_1')]
    assert goals(run, fsm.SCAN_TAG) == [{'kind': 'station', 'zone_id': 'station_a'}]
    assert events(run).count('AUTH_OK') == 1 and events(run).count('ORDER_DONE') == 2
    assert fsm.Finish(True) in run


def test_empty_dispenser_aborts_the_order_and_asks_for_a_refill():
    inventory = DispenserInventory([
        Slot(ITEM, 0, 'lot-a', '2027-01-01', 0),
        Slot(ITEM, 1, 'lot-b', '2027-02-01', 0),
    ])
    machine = make(inventory=inventory)
    machine.request(request())
    machine.result(fsm.GO_TO_ZONE, fsm.ACCEPTED)
    commands = machine.result(fsm.GO_TO_ZONE, fsm.ARRIVED)
    assert [c for c in commands if isinstance(c, fsm.Call)] == []
    assert fsm.OrderState(ORDER, 'ABORT', 'out_of_stock') in commands
    assert 'LOAD_DONE' in events(commands)


def test_dispenser_events_carry_the_dispenser_robot_id():
    inventory = DispenserInventory([
        Slot(ITEM, 0, 'lot-a', '2027-01-01', 1),
        Slot(ITEM, 1, 'lot-b', '2027-02-01', 0),
    ])
    machine = make(inventory=inventory)
    machine.request(request())
    machine.result(fsm.GO_TO_ZONE, fsm.ACCEPTED)
    commands = machine.result(fsm.GO_TO_ZONE, fsm.ARRIVED)
    assert commands == [
        fsm.Emit('AMR_DOCKED_LOAD', 'r001-0001'),                      # 노드의 robot_id(amr_1)
        fsm.Emit('DISPENSER_PAUSED', 'r001-0001', ORDER, 'dispenser'),
        fsm.Emit('REFILL_REQUESTED', 'r001-0001', ORDER, 'dispenser'),
        fsm.Call(fsm.DISPENSE, {'request_id': 'r001-0001', 'order_id': ORDER}),
    ]


def test_stock_is_taken_once_even_when_dispense_is_retried():
    inventory = DispenserInventory([
        Slot(ITEM, 0, 'lot-a', '2027-01-01', 5),
        Slot(ITEM, 1, 'lot-b', '2027-02-01', 5),
    ])
    machine = make(inventory=inventory)
    machine.request(request())
    machine.result(fsm.GO_TO_ZONE, fsm.ACCEPTED)
    machine.result(fsm.GO_TO_ZONE, fsm.ARRIVED)
    machine.result(fsm.DISPENSE, fsm.REJECTED, {'message': 'not_ready'})
    machine.tick(5.0)
    assert inventory.active_slot(ITEM).count == 4


@pytest.mark.parametrize('mode', [fsm.MODE_SINGLE, fsm.MODE_URGENT])
def test_single_and_urgent_take_exactly_one_order(mode):
    machine = make()
    orders = [{'order_id': ORDER, 'patient_id': PATIENT, 'item_id': ITEM},
              {'order_id': 'ord-0002', 'patient_id': '1002', 'item_id': ITEM}]
    assert machine.request(request(mode=mode, orders=orders)) == []


def test_orders_beyond_the_deck_slots_are_aborted():
    machine = make(deck_slots=1)
    orders = [{'order_id': ORDER, 'patient_id': PATIENT, 'item_id': ITEM},
              {'order_id': 'ord-0002', 'patient_id': PATIENT, 'item_id': ITEM}]
    machine.request(request(mode=fsm.MODE_BATCH_ROOM, orders=orders))
    machine.result(fsm.GO_TO_ZONE, fsm.ACCEPTED)
    machine.result(fsm.GO_TO_ZONE, fsm.ARRIVED)
    machine.result(fsm.DISPENSE, fsm.ACCEPTED)
    machine.state_update(fsm.BELT, belt(True, True, ORDER), True)
    machine.state_update(fsm.BELT, belt(), True)        # 봉투가 벨트를 떠났다
    machine.result(fsm.PICK_POUCH, fsm.OK)              # 첫 봉투가 칸 0 을 쓴다
    machine.result(fsm.DISPENSE, fsm.ACCEPTED)
    commands = machine.state_update(fsm.BELT, belt(True, True, 'ord-0002'), True)
    assert fsm.OrderState('ord-0002', 'ABORT', 'deck_full') in commands


# REQUEST_ACCEPTED detail(표시용) ----------------------------------------------

def test_request_accepted_detail_is_a_compact_one_line_json_of_the_request():
    """관제 화면이 모드·환자·약품을 보여 준다. 키 순서 고정, 공백 없음, 한글 그대로. 판정·지표는 읽지 않는다."""
    import json

    machine = make()
    urgent = dict(request(mode=fsm.MODE_URGENT),
                  orders=[{'order_id': ORDER, 'patient_id': '환자-1001', 'item_id': ITEM}])
    [accepted] = [c for c in machine.request(urgent) if isinstance(c, fsm.Emit)]
    assert accepted.detail == ('{"mode":1,"destination_id":"bed_a1","orders":'
                               '[{"order_id":"ord-0001","patient_id":"환자-1001","item_id":"drug-amox"}]}')
    assert list(json.loads(accepted.detail)) == ['mode', 'destination_id', 'orders']

    orders = [{'order_id': f'ord-{n:04d}', 'patient_id': str(1000 + n), 'item_id': ITEM} for n in range(1, 5)]
    batch = {'request_id': 'r001-0002', 'mode': fsm.MODE_BATCH_WARD, 'destination_id': 'station_a', 'orders': orders}
    assert json.loads(fsm.request_summary(batch)) == {'mode': 3, 'destination_id': 'station_a', 'orders': orders}
    assert '\n' not in fsm.request_summary(batch) and ' ' not in fsm.request_summary(batch)
    modes = (fsm.MODE_SINGLE, fsm.MODE_URGENT, fsm.MODE_BATCH_ROOM, fsm.MODE_BATCH_WARD)
    assert [fsm.MODE_VALUES[m] for m in modes] == [0, 1, 2, 3]            # DeliveryRequest.msg 상수 값


# 관측 guard(opt-in, 계약 11.3·11.6) -------------------------------------------------------------

def observed(order_id='', occupancy=1, zone=0, motion=0, applied=2, epoch=1):
    return {'epoch': epoch, 'seq': 1, 'order_id': order_id, 'occupancy': occupancy, 'pouch_zone': zone,
            'pouch_motion': motion, 'belt_command_applied': applied}


AT_END = {'occupancy': 2, 'zone': fsm.ZONE_END, 'motion': fsm.MOTION_STOPPED, 'applied': fsm.APPLIED_STOP}


def guarded():
    """관측 guard 를 켜고 ord-0001 을 배출해 벨트 끝(기존 at_end)까지 온 FSM. 관측은 아직 빈 벨트다."""
    machine = make(observation_guard=True)
    machine.state_update(fsm.BELT_OBSERVATION, observed(), True)
    machine.state_update(fsm.ARM_CLEARANCE, {'epoch': 1, 'seq': 1, 'clearance': fsm.CLEARANCE_CLEAR}, True)
    machine.request(request(mode=fsm.MODE_BATCH_ROOM, orders=BATCH))
    machine.result(fsm.GO_TO_ZONE, fsm.ACCEPTED)
    machine.result(fsm.GO_TO_ZONE, fsm.ARRIVED)
    machine.result(fsm.DISPENSE, fsm.ACCEPTED)
    return machine


def pick_goals(commands):
    return [c for c in commands if isinstance(c, fsm.SendGoal) and c.action == fsm.PICK_POUCH]


@pytest.mark.parametrize('seen', [
    None,                                              # 관측 없음(신선하지 않음)
    observed('ord-0001', occupancy=2, zone=1, motion=fsm.MOTION_STOPPED),     # 벨트 중간에 끼여 멈춤
    observed('ord-0001', **{**AT_END, 'motion': 1}),                          # 종단이지만 아직 움직임
    observed('ord-0001', **{**AT_END, 'applied': 1}),                         # STOP 이 적용되지 않음
    observed('ord-0009', **AT_END),                                           # 다른 주문의 봉투
    observed('ord-0001', **AT_END, epoch=0),                                  # 다른 epoch
])
def test_guard_withholds_the_belt_pick_until_the_observation_says_settled_at_the_end(seen):
    machine = guarded()
    if seen is not None:
        machine.state_update(fsm.BELT_OBSERVATION, seen, True)
    else:
        machine.state_update(fsm.BELT_OBSERVATION, observed('ord-0001', **AT_END), False)
    assert pick_goals(machine.state_update(fsm.BELT, belt(True, True, ORDER), True)) == []
    assert machine.state == fsm.PICKING_BELT
    machine.tick(1.0)
    assert machine.wait_reason() is not None


def test_guard_sends_the_belt_pick_once_the_observation_agrees():
    machine = guarded()
    machine.state_update(fsm.BELT, belt(True, True, ORDER), True)
    goals = pick_goals(machine.state_update(fsm.BELT_OBSERVATION, observed(ORDER, **AT_END), True))
    assert [g.goal for g in goals] == [{'order_id': ORDER, 'source': 'BELT', 'target_slot': 0}]


def test_guard_holds_the_next_dispense_while_the_arm_is_in_the_corridor():
    machine = guarded()
    machine.state_update(fsm.BELT_OBSERVATION, observed(ORDER, **AT_END), True)
    machine.state_update(fsm.BELT, belt(True, True, ORDER), True)
    machine.state_update(fsm.ARM_CLEARANCE, {'epoch': 1, 'seq': 2, 'clearance': 2}, True)       # INTRUDING
    machine.state_update(fsm.BELT_OBSERVATION, observed(), True)
    machine.state_update(fsm.BELT, belt(), True)
    assert machine.result(fsm.PICK_POUCH, fsm.OK) == [fsm.OrderState(ORDER, 'LOADED')]
    machine.tick(1.0)
    assert '팔 통로' in machine.wait_reason()[1]
    calls = machine.state_update(fsm.ARM_CLEARANCE, {'epoch': 1, 'seq': 3, 'clearance': fsm.CLEARANCE_CLEAR}, True)
    assert calls == [fsm.Call(fsm.DISPENSE, {'request_id': 'r001-0001', 'order_id': 'ord-0002'})]


def test_without_the_guard_observations_change_nothing():
    """기본(guard 꺼짐)은 관측이 없어도 기존 규칙대로 픽 goal 을 낸다. 시연 경로 불변."""
    machine = make()
    machine.request(request(mode=fsm.MODE_BATCH_ROOM, orders=BATCH))
    machine.result(fsm.GO_TO_ZONE, fsm.ACCEPTED)
    machine.result(fsm.GO_TO_ZONE, fsm.ARRIVED)
    machine.result(fsm.DISPENSE, fsm.ACCEPTED)
    assert pick_goals(machine.state_update(fsm.BELT, belt(True, True, ORDER), True))


def test_deck_full_uses_the_configured_slot_count():
    """상판 자리 수는 장면마다 다르다. 통짜 트레이는 셋이다(시뮬 #445).

    기본 5 로 두고 자리가 셋인 상판에 넷째 주문을 실으면, FSM 은 `deck_slot_4` 로 놓으라고
    시키고 그 프레임이 없어 **놓는 자리에서** 실패한다. 여기서 `deck_full` 로 닫아야 한다.
    """
    assert fsm.TripConfig().deck_slots == 5
    assert fsm.TripConfig(deck_slots=3).deck_slots == 3


# 도크 복귀 실패 재시도(작전 카드, 회차133) ---------------------------------------------

def _start_return_leg():
    """배송까지 끝내고 도크 복귀 goal 이 수락된 상태의 기계."""
    machine = make()
    machine.request(request())
    for step in (
        (fsm.GO_TO_ZONE, fsm.ACCEPTED), (fsm.GO_TO_ZONE, fsm.ARRIVED), (fsm.DISPENSE, fsm.ACCEPTED)):
        machine.result(*step)
    machine.state_update(fsm.BELT, belt(True, True, ORDER), True)
    machine.result(fsm.PICK_POUCH, fsm.ACCEPTED)
    machine.state_update(fsm.BELT, belt(), True)
    machine.result(fsm.PICK_POUCH, fsm.OK)
    machine.result(fsm.GO_TO_ZONE, fsm.ACCEPTED)
    machine.result(fsm.GO_TO_ZONE, fsm.ARRIVED)
    machine.result(fsm.SCAN_TAG, fsm.ACCEPTED)
    machine.result(fsm.SCAN_TAG, fsm.OK, {'tag_id': 'pt-1001'})
    machine.result(fsm.PICK_POUCH, fsm.ACCEPTED)
    machine.result(fsm.PICK_POUCH, fsm.OK)
    machine.result(fsm.GO_TO_ZONE, fsm.ACCEPTED)
    assert machine.state == fsm.RETURNING
    return machine


def test_a_failed_return_is_retried_with_growing_waits_then_given_up():
    """회차133: 복귀 Nav2 목표 ABORTED 뒤 트립이 도크 밖에서 닫혀 AMR 이 600 s 넘게 섰다."""
    machine = _start_return_leg()
    waits = []
    now = 0.0
    for _attempt in range(3):
        commands = machine.result(fsm.GO_TO_ZONE, fsm.NOT_ARRIVED)
        assert machine.state == fsm.RETURNING
        assert any(isinstance(c, fsm.Note) and '재시도' in c.text for c in commands)
        [alert] = [c for c in commands if isinstance(c, fsm.Alert)]    # 관제 웹 알림(/p3/alerts)
        assert alert.kind == 'DOCK_RETRY' and alert.detail.startswith(f'{_attempt + 1}/3 ')
        assert not any(isinstance(c, fsm.Finish) for c in commands)
        # 기다리는 동안은 안 보내고, 때가 되면 도크로 다시 보낸다.
        waits.append(machine._retry_at - now)
        assert not [c for c in machine.tick(machine._retry_at - 0.01) if isinstance(c, fsm.SendGoal)]
        now = machine._retry_at
        resent = [c for c in machine.tick(now) if isinstance(c, fsm.SendGoal)]
        assert resent == [fsm.SendGoal(fsm.GO_TO_ZONE, {'zone_id': 'dock_1'})]
        machine.result(fsm.GO_TO_ZONE, fsm.ACCEPTED)
    assert waits == pytest.approx([10.0, 20.0, 40.0])
    commands = machine.result(fsm.GO_TO_ZONE, fsm.NOT_ARRIVED)
    assert any(isinstance(c, fsm.Note) and c.level == 'error' and '포기' in c.text for c in commands)
    assert [c.kind for c in commands if isinstance(c, fsm.Alert)] == ['DOCK_GIVEUP']
    assert [c.success for c in commands if isinstance(c, fsm.Finish)] == [False]
    assert machine.state == fsm.IDLE


def test_a_retry_that_arrives_docks_normally():
    machine = _start_return_leg()
    machine.result(fsm.GO_TO_ZONE, fsm.TIMED_OUT)
    machine.tick(machine._retry_at)
    machine.result(fsm.GO_TO_ZONE, fsm.ACCEPTED)
    commands = machine.result(fsm.GO_TO_ZONE, fsm.ARRIVED)
    assert fsm.Emit('DOCKED', 'r001-0001') in commands
    assert machine.state == fsm.IDLE


def test_a_canceled_return_is_not_retried():
    """취소는 리셋·정지다 — 다시 보내지 않는다(예전과 같다)."""
    machine = _start_return_leg()
    commands = machine.result(fsm.GO_TO_ZONE, fsm.CANCELED)
    assert any(isinstance(c, fsm.Finish) for c in commands)
    assert not any(isinstance(c, fsm.Alert) for c in commands)
    assert machine.state == fsm.IDLE


def test_alert_kinds_are_the_ones_the_web_topic_accepts():
    """trip_fsm 은 ROS 없이 돈다 — kind 를 글자로 적으므로 `/p3/alerts` 형식과 어긋나지 않는지 본다."""
    from rokey_p3_navigation import alerts
    import inspect
    source = inspect.getsource(fsm)
    for kind in ('DOCK_RETRY', 'DOCK_GIVEUP'):
        assert f"Alert('{kind}'" in source
        assert kind in alerts.KINDS


# 도크 = 적재 자리(병원 B안, 재범 9/29 "도크에서 AMR 이 이동하지 않고 그 자리에서 바로 파지") -------------------

def test_when_the_load_is_the_dock_the_trip_loads_without_moving():
    machine = make(load_at_dock=True)
    commands = machine.request(request())
    assert not [c for c in commands if isinstance(c, fsm.SendGoal) and c.action == fsm.GO_TO_ZONE]
    assert fsm.Emit(fsm.EVENT_AMR_DOCKED_LOAD, 'r001-0001') in commands
    assert [c.service for c in commands if isinstance(c, fsm.Call)] == [fsm.DISPENSE]
    assert machine.state == fsm.DOCKED_LOAD


def test_an_undocked_amr_still_redocks_first_and_then_loads_in_place():
    machine = make(load_at_dock=True)
    machine._undocked = True
    commands = machine.request(request())
    [goal] = [c for c in commands if isinstance(c, fsm.SendGoal)]
    assert goal.goal == {'zone_id': 'dock_1'}
    machine.result(fsm.GO_TO_ZONE, fsm.ACCEPTED)
    commands = machine.result(fsm.GO_TO_ZONE, fsm.ARRIVED)
    assert not [c for c in commands if isinstance(c, fsm.SendGoal)]
    assert fsm.Emit(fsm.EVENT_AMR_DOCKED_LOAD, 'r001-0001') in commands
    assert machine.state == fsm.DOCKED_LOAD


def test_the_default_still_drives_to_the_load_zone():
    commands = make().request(request())
    assert [c.goal for c in commands if isinstance(c, fsm.SendGoal)] == [{'zone_id': 'load'}]


def test_load_is_dock_compares_the_two_zone_poses():
    same = {'zones': {'load': {'x': -8.995, 'y': 4.686, 'yaw': -1.571},
                      'dock_1': {'x': -8.995, 'y': 4.686, 'yaw': -1.5708}}}
    apart = {'zones': {'load': {'x': -8.995, 'y': 4.686, 'yaw': -1.571},
                       'dock_1': {'x': -7.272, 'y': 4.784, 'yaw': -1.571}}}
    assert fsm.load_is_dock(same, 'load', 'dock_1')
    assert not fsm.load_is_dock(apart, 'load', 'dock_1')
    assert not fsm.load_is_dock({'zones': {'load': {'x': 0, 'y': 0, 'yaw': 0}}}, 'load', 'dock_1')
    assert not fsm.load_is_dock(None, 'load', 'dock_1')


@pytest.mark.parametrize('dispense_first', [True, False])
def test_dispatch_and_dispense_start_together_and_join(dispense_first):
    m = make(dispense_while_dispatching=True)
    commands = m.request(request())
    assert any(isinstance(c, fsm.SendGoal) and c.action == fsm.GO_TO_ZONE for c in commands)
    calls = [c for c in commands if isinstance(c, fsm.Call) and c.service == fsm.DISPENSE]
    assert len(calls) == 1
    m.result(fsm.GO_TO_ZONE, fsm.ACCEPTED)
    if dispense_first:
        m.result(fsm.DISPENSE, fsm.ACCEPTED, token=calls[0].token)
        m.state_update(fsm.BELT, belt(True, True, ORDER), True)
        assert m.state == fsm.DISPATCHING
        commands = m.result(fsm.GO_TO_ZONE, fsm.ARRIVED)
    else:
        commands = m.result(fsm.GO_TO_ZONE, fsm.ARRIVED)
        assert not any(isinstance(c, fsm.Call) for c in commands)
        assert m.state == fsm.DOCKED_LOAD
        m.result(fsm.DISPENSE, fsm.ACCEPTED, token=calls[0].token)
        commands = m.state_update(fsm.BELT, belt(True, True, ORDER), True)
    assert m.state == fsm.PICKING_BELT
    assert any(isinstance(c, fsm.SendGoal) and c.action == fsm.PICK_POUCH for c in commands)


def test_dispatch_dispense_failure_does_not_interrupt_movement():
    m = make(dispense_while_dispatching=True)
    m.request(request())
    m.result(fsm.DISPENSE, fsm.REJECTED, {'message': 'busy'})
    assert m.state == fsm.DISPATCHING
    m.result(fsm.GO_TO_ZONE, fsm.ARRIVED)
    assert m.state == fsm.DOCKED_LOAD
    m.tick(m.config.dispense_retry_delay_s + 1)
    assert m._dispense_calls == 2


def test_dispatch_stale_or_occupied_belt_does_not_early_dispense():
    for value, fresh in [(belt(True, False, 'old'), True), (belt(), False)]:
        m = make(dispense_while_dispatching=True)
        m.state_update(fsm.BELT, value, fresh)
        commands = m.request(request())
        assert not any(isinstance(c, fsm.Call) and c.service == fsm.DISPENSE for c in commands)
        assert any(isinstance(c, fsm.SendGoal) for c in commands)


def test_dispatch_failure_never_starts_pick_for_early_pouch():
    m = make(dispense_while_dispatching=True)
    commands = m.request(request())
    token = next(c.token for c in commands if isinstance(c, fsm.Call) and c.service == fsm.DISPENSE)
    m.result(fsm.GO_TO_ZONE, fsm.TIMEOUT)
    commands = m.result(fsm.DISPENSE, fsm.ACCEPTED, token=token)
    commands += m.state_update(fsm.BELT, belt(True, True, ORDER), True)
    assert not any(isinstance(c, fsm.SendGoal) and c.action == fsm.PICK_POUCH for c in commands)


@pytest.mark.parametrize('tag,valid', [('1001', True), ('pt-1001', True),
                                      ('1002', False), ('st-1001', False), ('', False)])
def test_camera_patient_id_contract_and_legacy_sim_id(tag, valid):
    m = make()
    m.request(request())
    m._goto(fsm.AUTHENTICATING)
    commands = m.result(fsm.SCAN_TAG, fsm.OK, {'tag_id': tag})
    assert (fsm.EVENT_AUTH_OK in events(commands)) is valid
    assert (fsm.EVENT_AUTH_FAIL in events(commands)) is not valid
