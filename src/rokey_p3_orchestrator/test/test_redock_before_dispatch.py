"""도크에 못 돌아온 채 끝난 트립 뒤, 다음 트립은 적재 위치로 가기 전에 도크부터 간다.

9/24 병원 10건(138cbac): bed_a3 에서 팔 받침이 협탁에 끼인 채 트립이 끝났고, 다음 주문이 그 자리에서 출발했다.
출발 guard 는 팔 홈(arm/at_home)만 본다. FSM 이 아는 AMR 위치 단서는 자기 복귀 결과뿐이라 그것을 기억한다.
"""

from test_trip_fsm import ORDER, events, make, request

from rokey_p3_orchestrator import trip_fsm as fsm


def goals(commands):
    return [c.goal.get('zone_id') for c in commands if isinstance(c, fsm.SendGoal)]


def notes(commands):
    return [c.text for c in commands if isinstance(c, fsm.Note)]


def end_undocked(machine):
    """적재 위치로 못 가고(not_arrived), 도크 복귀도 못 한(not_arrived) 트립 하나.

    복귀 실패 재시도(return_max_retries, 회차133)는 이 파일에서 0 으로 둔다 — 여기서 보는 것은 "도크 밖에서
    끝난 뒤" 의 동작이다. 재시도는 test_trip_fsm 이 본다.
    """
    commands = machine.request(request())
    commands += machine.result(fsm.GO_TO_ZONE, fsm.ACCEPTED)
    commands += machine.result(fsm.GO_TO_ZONE, fsm.NOT_ARRIVED)
    commands += machine.result(fsm.GO_TO_ZONE, fsm.ACCEPTED)
    commands += machine.result(fsm.GO_TO_ZONE, fsm.NOT_ARRIVED)
    assert goals(commands) == ['load', 'dock_1']
    assert commands[-1] == fsm.Finish(False)
    assert machine.state == fsm.IDLE
    return commands


def test_a_docked_finish_dispatches_straight_to_load():
    machine = make(return_max_retries=0)
    commands = machine.request(request())
    commands += machine.result(fsm.GO_TO_ZONE, fsm.ACCEPTED)
    commands += machine.result(fsm.GO_TO_ZONE, fsm.NOT_ARRIVED)   # 적재 위치 실패 → 복귀
    commands += machine.result(fsm.GO_TO_ZONE, fsm.ACCEPTED)
    commands += machine.result(fsm.GO_TO_ZONE, fsm.ARRIVED)       # 도크에는 돌아왔다
    assert commands[-1] == fsm.Finish(False)
    assert goals(machine.request(request())) == ['load']


def test_after_an_undocked_finish_the_next_trip_docks_first():
    machine = make(return_max_retries=0)
    end_undocked(machine)
    first = machine.request(request())
    assert goals(first) == ['dock_1']
    assert any('도크에 못 돌아온' in text for text in notes(first))
    assert machine.state == fsm.DISPATCHING
    assert machine.result(fsm.GO_TO_ZONE, fsm.ACCEPTED) == []    # DEPARTED·RETURNED 를 내지 않는다
    then = machine.result(fsm.GO_TO_ZONE, fsm.ARRIVED)
    assert goals(then) == ['load']
    assert events(then) == []                                     # 도크 도착은 AMR_DOCKED_LOAD 가 아니다
    arrived = machine.result(fsm.GO_TO_ZONE, fsm.ACCEPTED) + machine.result(fsm.GO_TO_ZONE, fsm.ARRIVED)
    assert events(arrived) == ['AMR_DOCKED_LOAD']
    assert machine.state == fsm.DOCKED_LOAD


def test_the_redock_waits_for_the_arm_home_guard_like_any_dispatch():
    machine = make(return_max_retries=0)
    end_undocked(machine)
    machine.state_update(fsm.AT_HOME, False, True)
    assert goals(machine.request(request())) == []
    assert goals(machine.state_update(fsm.AT_HOME, True, True)) == ['dock_1']


def test_a_failed_redock_closes_the_orders_and_keeps_the_flag():
    machine = make(return_max_retries=0)
    end_undocked(machine)
    commands = machine.request(request())
    commands += machine.result(fsm.GO_TO_ZONE, fsm.ACCEPTED)
    commands += machine.result(fsm.GO_TO_ZONE, fsm.NOT_ARRIVED)
    # 아직 싣지 않은 주문이라 ABORT 다(_close_all). 이유에 도크 재진입 실패가 남는다.
    assert fsm.OrderState(ORDER, 'ABORT', 'redock_not_arrived') in commands
    assert machine.state == fsm.RETURNING
    commands = machine.result(fsm.GO_TO_ZONE, fsm.ACCEPTED) + machine.result(fsm.GO_TO_ZONE, fsm.NOT_ARRIVED)
    assert commands[-1] == fsm.Finish(False)
    assert goals(machine.request(request())) == ['dock_1']        # 다음 트립도 도크부터


def test_a_redock_rejected_twice_gives_up_like_a_dispatch():
    machine = make(return_max_retries=0)
    end_undocked(machine)
    machine.request(request())
    machine.result(fsm.GO_TO_ZONE, fsm.REJECTED)
    machine.tick(10.0)                                             # 5 s 재시도 대기가 지났다
    commands = machine.result(fsm.GO_TO_ZONE, fsm.REJECTED)
    assert fsm.OrderState(ORDER, 'ABORT', 'goto_rejected') in commands


def test_reset_clears_the_flag():
    machine = make(return_max_retries=0)
    end_undocked(machine)
    machine.reset(2)
    assert machine.result(fsm.RESET, fsm.OK)[-1] == fsm.Emit('RESET_DONE')
    assert goals(machine.request(request())) == ['load']
