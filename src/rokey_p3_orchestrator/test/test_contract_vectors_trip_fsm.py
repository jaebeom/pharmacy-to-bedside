"""L1. 컨베이어↔팔 계약 벡터(계약 v1 11절)를 트립 FSM 에 돌린다. ROS 를 import 하지 않는다.

벡터는 `rokey_p3_interfaces/contract_vectors/conveyor_arm/v1/` 에 있다. 형식은 그 폴더 README.
- 트립 FSM 에 없는 opt-in 을 요구하는 사례는 skip 한다(이유에 opt-in 이름). opt-in 을 구현하는 PR 이 여기 지원을 더한다.
- 지원하는 사례 중 지금 못 맞추는 것은 EXPECTED_FAILURES 에 적어 xfail(strict) 로 돌린다. 고치는 PR 에서 뺀다.
"""

import json
from pathlib import Path

import pytest

from rokey_p3_orchestrator import trip_fsm as fsm

VECTORS = Path(__file__).resolve().parents[2] / 'rokey_p3_interfaces' / 'contract_vectors' / 'conveyor_arm' / 'v1'
PICK = json.loads((VECTORS / 'pick.json').read_text(encoding='utf-8'))
NEXT = json.loads((VECTORS / 'next_dispense.json').read_text(encoding='utf-8'))

SUPPORTED_OPTIONS = {'next_dispense_guard'}   # 트립 FSM 의 opt-in. TripConfig.observation_guard 로 켠다
EXPECTED_FAILURES = {                            # 사례 ID → 이유. 고치는 PR 에서 뺀다
    'N09': '칸 안착 관측(계약 11.4)이 아직 없어 guard 가 안착 미확인을 막지 못한다',
}
CLEARANCE = {'CLEAR': 1, 'INTRUDING': 2, 'UNKNOWN': 0}     # ArmClearance.msg
ORDERS = [{'order_id': 'ord-0001', 'patient_id': '1001', 'item_id': 'drug-amox'},
          {'order_id': 'ord-0002', 'patient_id': '1002', 'item_id': 'drug-amox'}]


def belt(occupied=False, at_end=False, order_id=''):
    return {'occupied': occupied, 'at_end': at_end, 'order_id': order_id}


def observation(order_id='', occupancy=1, zone=0, motion=0, applied=2):
    """BeltObservation 을 노드가 FSM 에 넘기는 dict(epoch 1). 기본은 빈 벨트."""
    return {'epoch': 1, 'seq': 1, 'order_id': order_id, 'occupancy': occupancy, 'pouch_zone': zone,
            'pouch_motion': motion, 'belt_command_applied': applied}


def machine_waiting_for_the_belt(orders, guard=False):
    """적재 위치에 도착해 ord-0001 을 배출했고 벨트 도착을 기다리는 FSM."""
    machine = fsm.TripFsm(config=fsm.TripConfig(observation_guard=guard),
                          patient_beds={'1001': 'bed_a1', '1002': 'bed_a2'})
    machine.tick(0.0)
    machine.state_update(fsm.AT_HOME, True, True)
    machine.state_update(fsm.BASE_STOPPED, True, True)
    machine.state_update(fsm.BELT, belt(), True)
    if guard:
        machine.state_update(fsm.BELT_OBSERVATION, observation(), True)
        machine.state_update(fsm.ARM_CLEARANCE, {'epoch': 1, 'seq': 1, 'clearance': CLEARANCE['CLEAR']}, True)
    machine.request({'request_id': 'r001-0001', 'mode': fsm.MODE_BATCH_ROOM, 'destination_id': '', 'orders': orders})
    machine.result(fsm.GO_TO_ZONE, fsm.ACCEPTED)
    machine.result(fsm.GO_TO_ZONE, fsm.ARRIVED)
    machine.result(fsm.DISPENSE, fsm.ACCEPTED)
    return machine


def params(cases):
    out = []
    for case in cases:
        marks = []
        unsupported = set(case.get('options', {})) - SUPPORTED_OPTIONS
        if unsupported:
            marks.append(pytest.mark.skip(reason=f'트립 FSM 에 opt-in 없음: {sorted(unsupported)}'))
        elif case['id'] in EXPECTED_FAILURES:
            marks.append(pytest.mark.xfail(strict=True, reason=EXPECTED_FAILURES[case['id']]))
        out.append(pytest.param(case, id=case['id'], marks=marks))
    return out


@pytest.mark.parametrize('case', params(PICK['permit_cases']))
def test_trip_fsm_sends_the_belt_pick_only_when_the_vector_allows(case):
    given = case['input']
    if given['goal_order_id'] != 'ord-0001':
        pytest.skip('트립 FSM 의 goal 주문은 지금 배출한 주문이라 비거나 다를 수 없다')
    machine = machine_waiting_for_the_belt(ORDERS[:1])
    out = machine.state_update(fsm.BASE_STOPPED, given['base_stopped'], given['base_stopped'] is not None)
    if given['belt'] is None:
        out += machine.state_update(fsm.BELT, belt(True, True, 'ord-0001'), False)     # 1.0 s 넘은 값
    else:
        out += machine.state_update(fsm.BELT, belt(True, given['belt']['at_end'], given['belt']['order_id']), True)
    picks = [c for c in out if isinstance(c, fsm.SendGoal) and c.action == fsm.PICK_POUCH]
    assert bool(picks) is case['expect']['allowed']


@pytest.mark.parametrize('case', params(NEXT['cases']))
def test_trip_fsm_dispenses_the_next_order_only_when_the_vector_allows(case):
    given = case['input']
    guard = bool(case.get('options', {}).get('next_dispense_guard'))
    machine = machine_waiting_for_the_belt(ORDERS, guard)
    if guard:                                                                        # 종단 정착 관측(피킹 허가)
        machine.state_update(fsm.BELT_OBSERVATION, observation('ord-0001', 2, 2, 2, 2), True)
    machine.state_update(fsm.BELT, belt(True, True, 'ord-0001'), True)             # 픽 goal 이 나간다
    machine.result(fsm.PICK_POUCH, fsm.ACCEPTED)
    out = []
    if guard:
        occupied = given['belt_occupied']
        out += machine.state_update(fsm.BELT_OBSERVATION, observation(occupancy=2 if occupied else 1),
                                    occupied is not None)
        clearance = given['arm_clear']
        out += machine.state_update(fsm.ARM_CLEARANCE, {'epoch': 1, 'seq': 2, 'clearance': CLEARANCE.get(clearance, 0)},
                                    clearance is not None)
    if given['belt_occupied'] is None:
        out += machine.state_update(fsm.BELT, belt(), False)
    else:
        out += machine.state_update(fsm.BELT, belt(given['belt_occupied'], False,
                                                   'ord-0001' if given['belt_occupied'] else ''), True)
    if given['pick'] != 'pending':
        out += machine.result(fsm.PICK_POUCH, fsm.OK if given['pick'] == 'ok' else fsm.DROPPED)
    calls = [c for c in out if isinstance(c, fsm.Call) and c.service == fsm.DISPENSE
             and c.request['order_id'] == 'ord-0002']
    assert bool(calls) is case['expect']['allowed']
