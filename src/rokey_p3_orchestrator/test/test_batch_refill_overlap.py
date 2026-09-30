"""묶음(병실) 트립과 보충이 겹칠 때의 **현행 동작**을 고정한다. L1(순수 FSM + 재고).

9/20 새벽 확정 대본 실행에서는 앞 보충으로 재고가 있어서 이 경우가 나오지 않았다(#240).
9/21 시연에서 나올 수 있으므로 지금 코드가 무엇을 하는지 먼저 적어 둔다. 제품 코드는 바꾸지 않는다.

여기서 고정하는 것:
- 묶음 도중 한 품목이 임계에 닿으면 `REFILL_REQUESTED` 만 나가고 배출은 그대로 이어진다(기다리지 않는다).
- 묶음의 다음 주문이 재고 0 이면 그 주문만 `ABORT out_of_stock` 이고 트립은 이어진다.
- 같은 트립 도중에 보충이 끝나면 다음 주문이 그대로 배출된다.
"""

import pytest

from rokey_p3_orchestrator import trip_fsm as fsm
from rokey_p3_orchestrator.dispenser_inventory import DispenserInventory, Slot

ITEM = 'drug-amox'
FIRST = 'ord-0001'
SECOND = 'ord-0002'
BATCH = [{'order_id': FIRST, 'patient_id': '1001', 'item_id': ITEM},
         {'order_id': SECOND, 'patient_id': '1002', 'item_id': ITEM}]


def belt(occupied=False, at_end=False, order_id=''):
    return {'occupied': occupied, 'at_end': at_end, 'order_id': order_id}


def inventory(count_a, threshold=1):
    return DispenserInventory([Slot(ITEM, 0, 'lot-a', '2027-01-01', count_a),
                               Slot(ITEM, 1, 'lot-b', '2027-02-01', 0)],
                              refill_threshold=threshold)


def machine_with(stock, threshold=1):
    store = inventory(stock, threshold)
    machine = fsm.TripFsm(config=fsm.TripConfig(), inventory=store,
                          patient_beds={'1001': 'bed_a1', '1002': 'bed_a1'})
    machine.tick(0.0)
    machine.state_update(fsm.AT_HOME, True, True)
    machine.state_update(fsm.BASE_STOPPED, True, True)
    machine.state_update(fsm.BELT, belt(), True)
    return machine, store


def start_batch(machine):
    """묶음 요청 → 조제실 도착. 첫 주문의 배출 명령까지 나온 상태로 만든다."""
    commands = machine.request({'request_id': 'r001-0001', 'mode': fsm.MODE_BATCH_ROOM,
                                'destination_id': 'bed_a1', 'orders': BATCH})
    commands += machine.result(fsm.GO_TO_ZONE, fsm.ACCEPTED)
    commands += machine.result(fsm.GO_TO_ZONE, fsm.ARRIVED)
    return commands


def load_first(machine):
    """첫 주문을 상판에 싣고 벨트를 비운다. 그때 나온 명령을 돌려준다."""
    machine.result(fsm.DISPENSE, fsm.ACCEPTED)
    machine.state_update(fsm.BELT, belt(True, True, FIRST), True)
    machine.result(fsm.PICK_POUCH, fsm.ACCEPTED)
    machine.result(fsm.PICK_POUCH, fsm.OK)
    return machine.state_update(fsm.BELT, belt(), True)


def events(commands):
    return [c.event for c in commands if isinstance(c, fsm.Emit)]


def calls(commands):
    return [c.service for c in commands if isinstance(c, fsm.Call)]


def test_a_threshold_reached_inside_the_batch_only_asks_for_a_refill():
    """두 번째 주문을 빼면서 임계에 닿아도 트립은 기다리지 않는다. 요청만 나간다."""
    machine, store = machine_with(3)                 # 3 → 2(첫 주문) → 1(둘째 주문, 임계 1)
    start_batch(machine)
    assert events(machine.result(fsm.DISPENSE, fsm.ACCEPTED)) == []

    commands = load_first(machine)

    assert events(commands) == ['REFILL_REQUESTED']
    assert calls(commands) == [fsm.DISPENSE]         # 같은 입력에서 다음 배출이 이어진다
    assert machine.order_states() == {FIRST: 'LOADED', SECOND: 'ACCEPTED'}
    assert store.is_paused(ITEM) is False            # 재고가 남아 있어 멈추지 않는다
    assert store.refill_requests() == (ITEM,)


def test_a_batch_order_with_no_stock_is_the_only_one_that_aborts():
    """묶음의 다음 주문이 재고 0 이면 그 주문만 닫히고 트립은 이어진다."""
    machine, store = machine_with(1)                 # 첫 주문이 마지막 한 봉투를 쓴다
    start_batch(machine)
    assert store.is_paused(ITEM) is True             # 첫 take 에서 이미 멈췄다

    commands = load_first(machine)

    assert fsm.OrderState(SECOND, 'ABORT', 'out_of_stock') in commands
    assert calls(commands) == []                     # 두 번째 배출 명령은 나가지 않는다
    assert events(commands) == ['ORDER_DONE', 'LOAD_DONE']
    assert machine.order_states() == {FIRST: 'LOADED', SECOND: 'ABORT'}
    assert machine.state == fsm.DEPARTING            # 실은 주문이 있어 출발한다


def test_the_pause_events_are_not_repeated_for_the_second_order():
    """첫 주문에서 이미 멈췄으면 두 번째 주문의 실패는 새 이벤트를 만들지 않는다."""
    machine, _store = machine_with(1)
    first = start_batch(machine)
    assert events(first) == ['REQUEST_ACCEPTED', 'AMR_DOCKED_LOAD',
                             'DISPENSER_PAUSED', 'REFILL_REQUESTED']

    second = load_first(machine)

    assert 'DISPENSER_PAUSED' not in events(second)
    assert 'REFILL_REQUESTED' not in events(second)


def test_a_refill_inside_the_trip_lets_the_next_order_dispense():
    """트립 도중에 보충이 끝나면 다음 주문이 그대로 배출된다."""
    machine, store = machine_with(1)
    start_batch(machine)
    store.refill(ITEM, 1, 'lot-c', '2027-03-01', 5)  # 빈 슬롯 B 에 캐니스터를 넣는다
    assert store.is_paused(ITEM) is False

    commands = load_first(machine)

    assert calls(commands) == [fsm.DISPENSE]
    assert [c for c in commands if isinstance(c, fsm.OrderState)] == []
    assert machine.order_states() == {FIRST: 'LOADED', SECOND: 'ACCEPTED'}


@pytest.mark.parametrize('stock, expected', [(5, []), (3, []), (2, ['REFILL_REQUESTED']),
                                             (1, ['REFILL_REQUESTED'])])
def test_the_first_order_only_asks_when_it_crosses_the_threshold(stock, expected):
    """임계(기본 1)는 뺀 뒤의 합계로 본다. 시연 재고(slot a 1)는 첫 주문부터 요청이 나간다.

    남은 합계가 1 이하가 되는 순간에 요청이 한 번 나간다. 3 에서 빼면 2 라서 아직 나가지 않는다.
    """
    machine, _store = machine_with(stock)
    commands = start_batch(machine)
    assert [name for name in events(commands) if name == 'REFILL_REQUESTED'] == expected


def test_the_fsm_can_count_the_stops_it_has_not_reached():
    """`refill_overlap` 로그가 부르는 이름이다. `stops()` 는 **메서드**라 len() 이 안 걸린다.

    #604 CI 가 그 자리였다: 노드가 `len(self._fsm.stops)` 를 걸어 TypeError 가 났고, 그 줄이
    `_send_goal` 안에 있어서 **보충 goal 이 아예 안 나갔다**. 세는 일을 FSM 한 곳에 둔다.
    """
    machine, _store = machine_with(4)
    assert machine.stops_left() == 0                       # 트립 전
    start_batch(machine)
    assert machine.stops_left() == len(machine.stops())    # 아직 한 곳도 안 들렀다
    assert machine.stops_left() >= 1
    assert isinstance(machine.stops_left(), int)
