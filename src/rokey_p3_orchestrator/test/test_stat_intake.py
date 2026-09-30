"""STAT S0 접수 L1: 관측 → incident, 승인 대조, 멱등 접수, 원장 쓰기 실패, 원장 재열기.

기대값은 반환값만이 아니라 원장의 주문·요청 행과 outbox 이벤트로 본다.
"""

from dataclasses import replace

import pytest

from rokey_p3_orchestrator.stat_intake import (
    ApprovalRecord, DISPOSITION_ACCEPTED, DISPOSITION_REJECTED, DISPOSITION_REPLAY, EmergencyObservation,
    OrderRequest, ingest_observation, record_approval, revoke_approval, submit_order)
from rokey_p3_orchestrator.stat_ledger import INCIDENT_ACK_REQUIRED, StatLedger

NOW = 1_000.0


@pytest.fixture
def ledger(tmp_path):
    book = StatLedger(tmp_path / 'stat.db')
    yield book
    book.close()


def obs(seq, source='cam-402', stamp=NOW, room='R402', bed='B1', labels=('fall_suspected',)):
    return EmergencyObservation(source, 'boot-1', seq, room, bed, stamp, labels)


def approval(incident, **changes):
    rec = ApprovalRecord('APR-1', 'r1', incident, 'synthetic_charge_nurse', 'SUBJ-SIM-01',
                         'SIM-KIT-A', 'k1', 'STN-3F-A', NOW, NOW + 600.0)
    return replace(rec, **changes)


def request(incident, request_id='REQ-1', **changes):
    req = OrderRequest(request_id, incident, 'APR-1', 'r1', 'SUBJ-SIM-01', 'SIM-KIT-A', 'k1', 'STN-3F-A')
    return replace(req, **changes)


def approved_incident(ledger, **approval_changes):
    incident_id, _ = ingest_observation(ledger, obs(1))
    record_approval(ledger, approval(incident_id, **approval_changes))
    return incident_id


def accepted_names(ledger):
    return [n for n in ledger.event_names() if n == 'STAT_ORDER_ACCEPTED']


def test_observation_opens_an_incident_and_never_an_order(ledger):
    incident_id, counted = ingest_observation(ledger, obs(1))
    assert counted
    assert ledger.incident(incident_id)['status'] == INCIDENT_ACK_REQUIRED
    assert ledger.orders() == []
    assert 'STAT_ORDER_ACCEPTED' not in ledger.event_names()


def test_long_silence_is_not_an_approval(ledger):
    incident_id, _ = ingest_observation(ledger, obs(1))
    result = submit_order(ledger, request(incident_id), now_wall=NOW + 3600.0)
    assert result == (DISPOSITION_REJECTED, 'approval_missing', '')
    assert ledger.orders() == []
    assert ledger.incident(incident_id)['status'] == INCIDENT_ACK_REQUIRED


def test_repeated_observations_update_one_incident(ledger):
    first, _ = ingest_observation(ledger, obs(1))
    assert ingest_observation(ledger, obs(1)) == (first, False)          # 같은 표본 재전송
    assert ingest_observation(ledger, obs(7, source='mic-402', stamp=NOW + 5)) == (first, True)
    assert ingest_observation(ledger, obs(2, stamp=NOW - 3)) == (first, True)   # 순서가 바뀐 표본
    assert ledger.incident(first)['observation_count'] == 3
    other_bed, _ = ingest_observation(ledger, obs(3, bed='B2'))
    later, _ = ingest_observation(ledger, obs(4, stamp=NOW + 10_000))
    assert len({first, other_bed, later}) == 3
    assert ledger.orders() == []


def test_one_approval_makes_at_most_one_order(ledger):
    incident_id = approved_incident(ledger)
    assert submit_order(ledger, request(incident_id), NOW).disposition == DISPOSITION_ACCEPTED
    again = submit_order(ledger, request(incident_id, request_id='REQ-2'), NOW)
    assert again == (DISPOSITION_REJECTED, 'approval_consumed', '')
    assert len(ledger.orders()) == 1


@pytest.mark.parametrize('approval_changes, request_changes, now, reason', [
    ({}, {}, NOW + 600.0, 'approval_expired'),
    ({'approver_role': 'synthetic_visitor'}, {}, NOW, 'approver_not_authorized'),
    ({}, {'approval_revision': 'r0'}, NOW, 'approval_revision_mismatch'),
    ({}, {'approval_id': 'APR-404'}, NOW, 'approval_missing'),
    ({}, {'subject_ref': 'SUBJ-SIM-02'}, NOW, 'subject_mismatch'),
    ({}, {'kit_revision': 'k2'}, NOW, 'kit_mismatch'),
    ({}, {'destination_id': 'STN-3F-B'}, NOW, 'destination_mismatch'),
    ({'incident_id': 'INC-0999'}, {}, NOW, 'incident_mismatch'),
    ({}, {'incident_id': 'INC-0999'}, NOW, 'incident_unknown'),
    ({}, {'kit_id': ''}, NOW, 'invalid_request'),
    ({}, {'request_id': 'R' * 65}, NOW, 'invalid_request'),
])
def test_approval_must_match_the_request(ledger, approval_changes, request_changes, now, reason):
    incident_id = approved_incident(ledger, **approval_changes)
    result = submit_order(ledger, request(incident_id, **request_changes), now)
    assert result == (DISPOSITION_REJECTED, reason, '')
    assert ledger.orders() == []
    if reason != 'invalid_request':
        assert ledger.events()[-1]['detail']['reason'] == reason


def test_revoked_approval_is_rejected_and_a_new_revision_is_needed(ledger):
    incident_id = approved_incident(ledger)
    revoke_approval(ledger, 'APR-1')
    assert submit_order(ledger, request(incident_id), NOW).reason == 'approval_revoked'
    record_approval(ledger, approval(incident_id, revision='r2'))
    assert submit_order(ledger, request(incident_id), NOW).reason == 'approval_revision_mismatch'
    ok = submit_order(ledger, request(incident_id, approval_revision='r2'), NOW)
    assert ok.disposition == DISPOSITION_ACCEPTED


def test_same_revision_cannot_be_rewritten_to_undo_a_revocation(ledger):
    incident_id = approved_incident(ledger)
    revoke_approval(ledger, 'APR-1')
    with pytest.raises(ValueError):
        record_approval(ledger, approval(incident_id))
    assert ledger.approval('APR-1')['revoked'] == 1


def test_approval_is_not_valid_before_it_is_issued(ledger):
    incident_id = approved_incident(ledger)
    assert submit_order(ledger, request(incident_id), NOW - 1).reason == 'approval_not_yet_valid'


def test_same_request_replays_and_different_content_conflicts(ledger):
    incident_id = approved_incident(ledger)
    first = submit_order(ledger, request(incident_id), NOW)
    replay = submit_order(ledger, request(incident_id), NOW + 900.0)       # 만료 뒤 재전송도 같은 답
    assert (first.disposition, replay.disposition) == (DISPOSITION_ACCEPTED, DISPOSITION_REPLAY)
    assert replay.ticket == first.ticket
    conflict = submit_order(ledger, request(incident_id, destination_id='STN-3F-B'), NOW)
    assert conflict == (DISPOSITION_REJECTED, 'request_conflict', '')
    assert len(ledger.orders()) == 1
    assert len(accepted_names(ledger)) == 1


def test_ledger_write_failure_records_nothing_and_does_not_bind_the_key(ledger):
    incident_id = approved_incident(ledger)
    ledger.fail_labels.add('submit')
    assert submit_order(ledger, request(incident_id), NOW) == (DISPOSITION_REJECTED, 'ledger_unavailable', '')
    assert ledger.orders() == [] and ledger.request('REQ-1') is None
    ledger.fail_labels.clear()
    assert submit_order(ledger, request(incident_id), NOW).disposition == DISPOSITION_ACCEPTED


def test_reopened_ledger_keeps_orders_approvals_and_pods(tmp_path):
    path = tmp_path / 'stat.db'
    book = StatLedger(path)
    incident_id = approved_incident(book)
    ticket = submit_order(book, request(incident_id), NOW).ticket
    assert book.seed_pods([{'pod_id': 'POD-1', 'kit_id': 'SIM-KIT-A', 'kit_revision': 'k1'}])
    book.close()

    reopened = StatLedger(path)
    assert reopened.order(ticket)['state'] == 'ACCEPTED'
    assert reopened.approval('APR-1')['revision'] == 'r1'
    assert not reopened.seed_pods([{'pod_id': 'POD-9', 'kit_id': 'SIM-KIT-A', 'kit_revision': 'k1'}])
    assert [p['pod_id'] for p in reopened.pods()] == ['POD-1']
    assert submit_order(reopened, request(incident_id), NOW) == (DISPOSITION_REPLAY, '', ticket)
    reopened.close()
