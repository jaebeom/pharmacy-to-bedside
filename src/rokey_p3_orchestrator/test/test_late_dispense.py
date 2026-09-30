"""배출 응답이 시한 뒤에 와서 거부로 받았는데 봉투는 벨트에 있다 — 그 봉투를 배출 증거로 받는다.

9/24 090a976 10건(master02) ord-0007: `Dispense v2-05-room ord-0007: 거부로 답한다. 10 s 안에 응답이 없다` →
`기다리는 요청이 없는 응답을 버린다` → `벨트에 봉투가 있다(order_id=ord-0007)` 1405 s → trip_limit.
"""

from test_trip_fsm import ORDER, belt, make, request

from rokey_p3_orchestrator import trip_fsm as fsm


def at_load(machine):
    machine.request(request())
    machine.result(fsm.GO_TO_ZONE, fsm.ACCEPTED)
    return machine.result(fsm.GO_TO_ZONE, fsm.ARRIVED)


def test_a_late_dispense_seen_on_the_belt_is_taken_as_dispensed():
    machine = make()
    commands = at_load(machine)
    assert fsm.Call(fsm.DISPENSE, {'request_id': 'r001-0001', 'order_id': ORDER}) in commands
    assert machine.result(fsm.DISPENSE, fsm.FAILED, {'message': 'timeout'}) == []   # 재시도 대기
    commands = machine.state_update(fsm.BELT, belt(True, False, ORDER), True)      # 봉투가 나왔다
    assert fsm.OrderState(ORDER, 'DISPENSED') in commands
    assert machine.state == fsm.WAIT_BELT
    commands = machine.state_update(fsm.BELT, belt(True, True, ORDER), True)       # 끝에 섰다
    assert [c.goal['order_id'] for c in commands if isinstance(c, fsm.SendGoal)] == [ORDER]
    assert machine.state == fsm.PICKING_BELT


def test_someone_elses_pouch_still_blocks_the_dispense():
    machine = make()
    at_load(machine)
    machine.result(fsm.DISPENSE, fsm.FAILED, {'message': 'timeout'})
    commands = machine.state_update(fsm.BELT, belt(True, True, 'ord-9999'), True)
    assert commands == []
    assert machine.state == fsm.DOCKED_LOAD
    assert machine.wait_reason()[1].startswith('벨트에 봉투가 있다')


def test_a_pouch_before_any_dispense_call_is_not_adopted():
    machine = make()
    machine.state_update(fsm.BELT, belt(True, True, ORDER), True)   # 부르기 전부터 있던 봉투
    at_load(machine)
    assert machine.state == fsm.DOCKED_LOAD
    assert machine.order_states()[ORDER] == 'ACCEPTED'
