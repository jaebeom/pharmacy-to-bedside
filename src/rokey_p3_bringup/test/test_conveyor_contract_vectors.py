"""L1. 컨베이어↔팔 계약 벡터(계약 v1 11절)와 기준 판정기가 같은 말을 하는지 본다. ROS 를 import 하지 않는다.

벡터는 구현과 무관한 데이터다. 여기서는 형식을 검사하고, 기준 판정기가 모든 기대값을 내는지 본다.
구현(스테이지·stub_sim·trip_fsm)을 벡터에 맞추는 러너는 각 레인에 둔다.
"""

from pathlib import Path

import pytest

from rokey_p3_bringup import conveyor_contract as cc

# 소스 트리의 벡터. 다른 패키지 파일을 소스 경로로 읽는 것은 navigation 의 test_zones_skeleton 과 같다.
VECTORS = Path(__file__).resolve().parents[2] / 'rokey_p3_interfaces' / 'contract_vectors' / 'conveyor_arm' / 'v1'
DISPENSE = cc.load_vectors(VECTORS, 'dispense')


def test_the_file_names_its_contract_clause_and_commit():
    assert DISPENSE['boundary'] == 'dispense'
    assert 'delivery-contract-v1.md 11.' in DISPENSE['contract']
    assert 'dc172d1' in DISPENSE['contract']
    assert {'settle_speed', 'settle_time_s'} <= set(DISPENSE['params'])


def test_vector_ids_are_unique_and_every_vector_checks_something():
    ids = [v['id'] for v in DISPENSE['vectors']]
    assert len(ids) == len(set(ids))
    assert all(i.startswith('D') for i in ids)
    for vector in DISPENSE['vectors']:
        assert vector['clause'] and vector['title'], vector['id']
        assert any('expect' in step for step in vector['steps']), vector['id']


@pytest.mark.parametrize('vector', DISPENSE['vectors'], ids=lambda v: v['id'])
def test_vector_format(vector):
    assert set(vector.get('options', {})) <= set(cc.OPTIONS)
    times = [step['t'] for step in vector['steps']]
    assert times == sorted(times), '시각은 줄지 않는다'
    for step in vector['steps']:
        inputs = [k for k in cc.STEP_INPUTS if k in step]
        assert len(inputs) == 1, step
        assert set(step) <= {'t', 'expect', *cc.STEP_INPUTS}, step
        assert set(step.get('expect', {})) <= set(cc.EXPECT_KEYS), step
        if 'pouch' in step:
            assert step['pouch']['at'] in cc.POSITIONS, step


@pytest.mark.parametrize('vector', DISPENSE['vectors'], ids=lambda v: v['id'])
def test_reference_meets_every_expectation(vector):
    assert cc.run_belt_vector(DISPENSE['params'], vector) == []


def test_both_readings_of_an_undecided_clause_are_pinned():
    """fail_closed 는 (제안·미확정)이다. 현재 기본값과 opt-in 두 읽기를 모두 벡터로 고정한다."""
    lost = [v for v in DISPENSE['vectors'] if any(s.get('pouch', {}).get('at') == 'lost' for s in v['steps'])]
    assert {bool(v.get('options', {}).get('fail_closed')) for v in lost} == {False, True}


def test_unknown_option_and_position_are_refused():
    with pytest.raises(ValueError):
        cc.BeltReference(0.01, 0.3, fail_open=True)
    belt = cc.BeltReference(0.01, 0.3)
    belt.step(0.0, {'dispense': {'request_id': 'r001-0001', 'order_id': 'ord-0001'}})
    with pytest.raises(ValueError):
        belt.step(1.0, {'pouch': {'at': 'floor'}})


# 피킹·다음 배출 ------------------------------------------------------------------

PICK = cc.load_vectors(VECTORS, 'pick')
NEXT = cc.load_vectors(VECTORS, 'next_dispense')


def test_every_boundary_file_names_its_clause_and_commit():
    for data, boundary in ((PICK, 'pick'), (NEXT, 'next_dispense')):
        assert data['boundary'] == boundary
        assert 'delivery-contract-v1.md' in data['contract'] and 'dc172d1' in data['contract']


def test_ids_are_unique_across_all_files():
    ids = ([v['id'] for v in DISPENSE['vectors']] + [v['id'] for v in PICK['at_end_vectors']]
           + [c['id'] for c in PICK['permit_cases']] + [c['id'] for c in NEXT['cases']])
    assert len(ids) == len(set(ids))


@pytest.mark.parametrize('vector', PICK['at_end_vectors'], ids=lambda v: v['id'])
def test_reference_settles_at_end_as_the_vector_says(vector):
    test_vector_format(vector)
    assert cc.run_belt_vector(PICK['params'], vector) == []


@pytest.mark.parametrize('case', PICK['permit_cases'], ids=lambda c: c['id'])
def test_reference_pick_permit(case):
    assert set(case['input']) == {'base_stopped', 'belt', 'goal_order_id'}
    assert cc.pick_allowed(case['input']) is case['expect']['allowed']


@pytest.mark.parametrize('case', NEXT['cases'], ids=lambda c: c['id'])
def test_reference_next_dispense_permit(case):
    given = case['input']
    assert set(given) == {'belt_occupied', 'pick', 'placement', 'arm_clear'}
    assert given['pick'] in cc.PICK_RESULTS
    assert given['placement'] in (*cc.PLACEMENT, None) and given['arm_clear'] in (*cc.ARM_CLEAR, None)
    assert set(case.get('options', {})) <= {'next_dispense_guard'}
    assert cc.next_dispense_allowed(given, **case.get('options', {})) is case['expect']['allowed']


def test_the_guard_never_allows_what_the_current_rule_forbids():
    """guard 는 조건을 더하기만 한다. 같은 입력에서 현재 규칙이 막는 것을 guard 가 허가하면 안 된다."""
    for case in NEXT['cases']:
        if cc.next_dispense_allowed(case['input'], next_dispense_guard=True):
            assert cc.next_dispense_allowed(case['input']), case['id']
