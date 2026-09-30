"""STAT S0 접수: 합성 관측 → incident, 합성 승인 레코드, 승인 대조·멱등 주문 접수. ROS 를 import 하지 않는다.

계약 1·3절(docs/architecture/stat-delivery-contract-v1.md, proposed).
관측은 사건만 만든다. 주문은 원장에 있는 승인 레코드와 대조해서만 생긴다. 시간은 호출자가 넣는다.
"""

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from typing import NamedTuple

from rokey_p3_orchestrator.stat_ledger import (
    ACCEPTED, INCIDENT_ACK_REQUIRED, LedgerWriteError, MISSION_NOT_STARTED)

DISPOSITION_ACCEPTED = 'ACCEPTED'
DISPOSITION_REPLAY = 'REPLAY'
DISPOSITION_REJECTED = 'REJECTED'

# 합성 승인자 역할. 실제 의료진 권한 체계가 아니다(계획서 6.3).
AUTHORIZED_ROLES = frozenset({'synthetic_charge_nurse'})
INCIDENT_WINDOW_S = 300.0
MAX_ID_LEN = 64


@dataclass(frozen=True)
class EmergencyObservation:
    """병실 이상 징후 표본 하나. 출고 권한이 아니다."""

    source_id: str
    boot_id: str
    seq: int
    room_id: str
    bed_id: str          # 모르면 빈 값
    stamp: float         # 표본 시각(s). 사건 시간창에만 쓴다
    labels: tuple
    validity: str = 'VALID'


@dataclass(frozen=True)
class ApprovalRecord:
    """합성 승인 게이트웨이가 원장에 남기는 레코드. 주문 요청과 따로 온다."""

    approval_id: str
    revision: str
    incident_id: str
    approver_role: str
    subject_ref: str
    kit_id: str
    kit_revision: str
    destination_id: str
    issued_at: float     # wall s
    expires_at: float    # wall s
    quantity: int = 1


@dataclass(frozen=True)
class OrderRequest:
    """접수 요청. request_id 가 멱등 키다."""

    request_id: str
    incident_id: str
    approval_id: str
    approval_revision: str
    subject_ref: str
    kit_id: str
    kit_revision: str
    destination_id: str


class SubmitResult(NamedTuple):
    """접수 결과. 튜플로 비교할 수 있다."""

    disposition: str
    reason: str = ''
    ticket: str = ''     # 추적 ID = order_id. 거부면 빈 값


def ingest_observation(ledger, obs, window_s=INCIDENT_WINDOW_S):
    """관측을 incident 에 묶는다. (incident_id, 새로 센 표본인가). 같은 source·boot·seq 는 한 번만 센다."""
    if not obs.room_id or not obs.source_id or not math.isfinite(obs.stamp):
        raise ValueError(f'관측 필드가 비었거나 시각이 유한하지 않다: {obs}')
    with ledger.tx('observation') as c:
        fresh = c.execute('INSERT OR IGNORE INTO samples_seen VALUES (?, ?, ?)',
                          (obs.source_id, obs.boot_id, obs.seq)).rowcount == 1
        row = c.execute(
            'SELECT * FROM incidents WHERE room_id = ? AND bed_id = ? AND status = ? '
            'AND ? BETWEEN first_stamp - ? AND last_stamp + ? ORDER BY first_stamp DESC LIMIT 1',
            (obs.room_id, obs.bed_id, INCIDENT_ACK_REQUIRED, obs.stamp, window_s, window_s)).fetchone()
        if not fresh:
            return (row['incident_id'] if row else ''), False
        degraded = int(obs.validity != 'VALID')
        if row is None:
            incident_id = f'INC-{ledger.bump(c, "incident_seq"):04d}'
            c.execute('INSERT INTO incidents VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?)',
                      (incident_id, obs.room_id, obs.bed_id, obs.stamp, obs.stamp,
                       json.dumps(sorted(set(obs.labels))), degraded, INCIDENT_ACK_REQUIRED))
            ledger.emit(c, 'STAT_INCIDENT_OPENED', incident_id=incident_id, room_id=obs.room_id)
            return incident_id, True
        incident_id = row['incident_id']
        labels = sorted(set(json.loads(row['labels'])) | set(obs.labels))
        c.execute('UPDATE incidents SET first_stamp = MIN(first_stamp, ?), last_stamp = MAX(last_stamp, ?), '
                  'observation_count = observation_count + 1, labels = ?, degraded = MAX(degraded, ?) '
                  'WHERE incident_id = ?', (obs.stamp, obs.stamp, json.dumps(labels), degraded, incident_id))
        ledger.emit(c, 'STAT_INCIDENT_UPDATED', incident_id=incident_id)
        return incident_id, True


def record_approval(ledger, rec):
    """승인 레코드를 쓴다. 같은 approval_id 는 새 revision 만 덮을 수 있다(새 결정이라 철회 표시도 새로 시작)."""
    if rec.quantity != 1 or not rec.expires_at > rec.issued_at:
        raise ValueError(f'S0 승인은 수량 1, 만료가 발급 뒤여야 한다: {rec}')
    fields = asdict(rec)
    with ledger.tx('approval') as c:
        old = c.execute('SELECT revision FROM approvals WHERE approval_id = ?', (rec.approval_id,)).fetchone()
        if old is not None and old['revision'] == rec.revision:
            raise ValueError(f'같은 revision 을 다시 쓸 수 없다(철회 표시가 풀린다): {rec.approval_id} {rec.revision}')
        c.execute('INSERT OR REPLACE INTO approvals VALUES (:approval_id, :revision, :incident_id, '
                  ':approver_role, :subject_ref, :kit_id, :kit_revision, :quantity, :destination_id, '
                  ':issued_at, :expires_at, 0)', fields)
        ledger.emit(c, 'STAT_APPROVAL_RECORDED', approval_id=rec.approval_id, revision=rec.revision)


def revoke_approval(ledger, approval_id):
    """승인을 철회한다. 이미 만든 주문은 다음 단계 전 재확인에서 멈춘다."""
    with ledger.tx('revoke') as c:
        if c.execute('UPDATE approvals SET revoked = 1 WHERE approval_id = ?', (approval_id,)).rowcount != 1:
            raise KeyError(approval_id)
        ledger.emit(c, 'STAT_APPROVAL_REVOKED', approval_id=approval_id)


def content_hash(req):
    """request_id 를 뺀 요청 내용의 SHA-256."""
    body = {k: v for k, v in asdict(req).items() if k != 'request_id'}
    return hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()


def approval_problem(approval, now_wall, roles=AUTHORIZED_ROLES):
    """승인 레코드 자체가 지금 유효한가. 문제가 없으면 ''. 접수와 단계별 재확인이 같이 쓴다."""
    if approval is None:
        return 'approval_missing'
    if approval['revoked']:
        return 'approval_revoked'
    if now_wall < approval['issued_at']:
        return 'approval_not_yet_valid'
    if now_wall >= approval['expires_at']:
        return 'approval_expired'
    if approval['approver_role'] not in roles:
        return 'approver_not_authorized'
    return ''


def _mismatch(approval, req):
    for field, reason in (('incident_id', 'incident_mismatch'), ('subject_ref', 'subject_mismatch'),
                          ('kit_id', 'kit_mismatch'), ('kit_revision', 'kit_mismatch'),
                          ('destination_id', 'destination_mismatch')):
        if approval[field] != getattr(req, field):
            return reason
    return ''


def submit_order(ledger, req, now_wall, roles=AUTHORIZED_ROLES):
    """승인 대조 뒤 주문을 한 번 기록한다. 계약 3절 표의 순서대로 첫 실패를 사유로 낸다."""
    if any(not isinstance(v, str) or not v or len(v) > MAX_ID_LEN for v in asdict(req).values()):
        return SubmitResult(DISPOSITION_REJECTED, 'invalid_request')
    digest = content_hash(req)
    try:
        with ledger.tx('submit') as c:
            result = _submit(ledger, c, req, digest, now_wall, roles)
            if result.disposition == DISPOSITION_REJECTED:
                ledger.emit(c, 'STAT_ORDER_REJECTED', request_id=req.request_id, reason=result.reason)
            return result
    except LedgerWriteError:
        return SubmitResult(DISPOSITION_REJECTED, 'ledger_unavailable')


def _submit(ledger, c, req, digest, now_wall, roles):
    seen = c.execute('SELECT * FROM requests WHERE request_id = ?', (req.request_id,)).fetchone()
    if seen is not None:
        if seen['content_hash'] != digest:
            return SubmitResult(DISPOSITION_REJECTED, 'request_conflict')
        return SubmitResult(DISPOSITION_REPLAY, '', seen['order_id'])
    if c.execute('SELECT 1 FROM incidents WHERE incident_id = ?', (req.incident_id,)).fetchone() is None:
        return SubmitResult(DISPOSITION_REJECTED, 'incident_unknown')
    approval = c.execute('SELECT * FROM approvals WHERE approval_id = ?', (req.approval_id,)).fetchone()
    if approval is not None and approval['revision'] != req.approval_revision:
        return SubmitResult(DISPOSITION_REJECTED, 'approval_revision_mismatch')
    problem = approval_problem(approval, now_wall, roles) or _mismatch(approval, req)
    if problem:
        return SubmitResult(DISPOSITION_REJECTED, problem)
    if c.execute('SELECT 1 FROM orders WHERE approval_id = ?', (req.approval_id,)).fetchone() is not None:
        return SubmitResult(DISPOSITION_REJECTED, 'approval_consumed')
    seq = ledger.bump(c, 'order_seq')
    order_id = f'STAT-{seq:04d}'
    c.execute('INSERT INTO requests VALUES (?, ?, ?)', (req.request_id, digest, order_id))
    c.execute('INSERT INTO orders VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
              (order_id, seq, req.request_id, req.incident_id, req.approval_id, req.approval_revision,
               req.subject_ref, req.kit_id, req.kit_revision, req.destination_id, ACCEPTED, '', '',
               MISSION_NOT_STARTED, 0, ''))
    ledger.emit(c, 'STAT_ORDER_ACCEPTED', order_id, request_id=req.request_id, approval_id=req.approval_id)
    return SubmitResult(DISPOSITION_ACCEPTED, '', order_id)
