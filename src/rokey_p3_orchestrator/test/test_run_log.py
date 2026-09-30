import datetime

import pytest

from rokey_p3_orchestrator import run_log


def test_state_name_covers_v1_and_v1_1_values():
    assert run_log.state_name(0) == 'ACCEPTED'
    assert run_log.state_name(2) == 'DELIVERED'
    assert run_log.state_name(11) == 'HOLD_RETURN'
    assert run_log.state_name(99) == 'UNKNOWN_99'


def test_run_id_follows_naming_rule():
    when = datetime.datetime(2026, 9, 17, 1, 2, 3, tzinfo=datetime.timezone.utc)
    assert run_log.run_id(when, 'master02', 'a1b2c3d4') == '20260917T010203Z-master02-a1b2c3d4'


@pytest.mark.parametrize('host,nonce', [('Master02', 'a1b2c3d4'), ('master02', 'A1B2C3D4'), ('', 'a1b2c3d4')])
def test_run_id_rejects_bad_parts(host, nonce):
    with pytest.raises(ValueError):
        run_log.run_id(datetime.datetime.now(datetime.timezone.utc), host, nonce)


def test_success_needs_the_evaluator_observation():
    assert run_log.judge('DELIVERED', observed=True) == ('SUCCESS', '')


def test_delivered_without_observation_is_abort():
    assert run_log.judge('DELIVERED', observed=False) == ('ABORT', run_log.REASON_NOT_OBSERVED)


def test_orchestrator_claim_of_success_is_not_success():
    state, reason = run_log.judge('SUCCESS', observed=False)
    assert state == 'ABORT'
    assert reason == run_log.REASON_CLAIMED_SUCCESS


def test_other_terminal_claims_pass_through_with_their_reason():
    assert run_log.judge('HOLD_RETURN', False, 'auth_fail') == ('HOLD_RETURN', 'auth_fail')
    assert run_log.judge('TIMEOUT', False, '') == ('TIMEOUT', '')


def test_observation_beats_a_disagreeing_claim():
    assert run_log.judge('ABORT', observed=True) == ('SUCCESS', run_log.REASON_CLAIM_DISAGREES)


def test_order_that_never_closed_is_abort():
    assert run_log.judge('IN_PROGRESS', False) == ('ABORT', run_log.REASON_NOT_TERMINAL)


def test_ledger_writes_success_only_from_the_cabinet_observation():
    ledger = run_log.OrderLedger()
    ledger.note_status('ord-0001', 'DELIVERED', '', 'r001-0001')
    ledger.note_status('ord-0002', 'DELIVERED', '', 'r001-0001')
    ledger.note_observation('ord-0001', 'bed_a1/cabinet', True)
    records = {row['order_id']: row for row in ledger.records()}
    assert records['ord-0001']['state'] == 'SUCCESS'
    assert records['ord-0001']['cabinet_id'] == 'bed_a1/cabinet'
    assert records['ord-0002']['state'] == 'ABORT'
    assert records['ord-0002']['reason'] == run_log.REASON_NOT_OBSERVED
    assert records['ord-0002']['claim'] == 'DELIVERED'


def test_ledger_ignores_an_absent_observation():
    ledger = run_log.OrderLedger()
    ledger.note_status('ord-0001', 'DELIVERED')
    ledger.note_observation('ord-0001', 'bed_a1/cabinet', False)
    assert ledger.records()[0]['state'] == 'ABORT'


def test_jsonl_is_one_sorted_line():
    line = run_log.jsonl({'b': 2, 'a': 1})
    assert line == '{"a": 1, "b": 2}\n'
