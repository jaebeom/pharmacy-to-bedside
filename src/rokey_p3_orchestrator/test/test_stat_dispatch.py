"""STAT S0 실행 L1: 정상 한 바퀴, 응답 소실, crash 재시작, fence, 관측 결손, 잘못된 Pod·목적지, 취소, 늦은 결과.

판정은 dispatcher 반환값이 아니라 stub 세계의 applied(물리 적용 횟수)·위치와 원장의 주문·Pod·이벤트로 한다.
crash 는 같은 프로세스 안에서 원장·세계 파일을 닫고 다시 여는 것까지다. 실제 프로세스 재시작은 CLI 시험이 본다.
"""

import pytest

from rokey_p3_orchestrator import stat_ledger as L
from rokey_p3_orchestrator import stat_stub as S
from rokey_p3_orchestrator.stat_dispatch import StatDispatcher
from rokey_p3_orchestrator.stat_intake import (
    ApprovalRecord, EmergencyObservation, OrderRequest, ingest_observation, record_approval, revoke_approval,
    submit_order)
from rokey_p3_orchestrator.stat_ledger import LedgerWriteError, StatLedger

DEST, OTHER = 'STN-3F-A', 'STN-3F-B'


class Clock:
    def __init__(self):
        self.t = 1_000.0

    def __call__(self):
        return self.t


class Crash(Exception):
    pass


class Rig:
    """원장·세계·dispatcher 한 벌. reopen() 은 전부 닫고 파일에서 다시 연다(재시작)."""

    def __init__(self, tmp_path):
        self.tmp, self.clock = tmp_path, Clock()
        S.StubWorld.create(tmp_path / 'world.json', self.clock, {'POD-1': 'SIM-KIT-A', 'POD-2': 'SIM-KIT-A'},
                           [DEST, OTHER])
        self.reopen()
        self.ledger.seed_pods([{'pod_id': p, 'kit_id': 'SIM-KIT-A', 'kit_revision': 'k1'}
                               for p in ('POD-1', 'POD-2')])

    def reopen(self):
        if hasattr(self, 'ledger'):
            self.ledger.close()
        self.ledger = StatLedger(self.tmp / 'stat.db')
        self.world = S.StubWorld(self.tmp / 'world.json', self.clock)
        self.d = StatDispatcher(self.ledger, self.world, self.clock, self.clock)
        self.d.start()

    def order(self, n=1, dest=DEST, kit_revision='k1'):
        incident, _ = ingest_observation(self.ledger, EmergencyObservation(
            'cam', 'b1', n, f'R{n}', 'B1', self.clock.t, ('fall_suspected',)))
        record_approval(self.ledger, ApprovalRecord(f'APR-{n}', 'r1', incident, 'synthetic_charge_nurse', 'SUBJ',
                                                    'SIM-KIT-A', kit_revision, dest, self.clock.t,
                                                    self.clock.t + 600))
        req = OrderRequest(f'REQ-{n}', incident, f'APR-{n}', 'r1', 'SUBJ', 'SIM-KIT-A', kit_revision, dest)
        return submit_order(self.ledger, req, self.clock.t).ticket

    def until(self, order_id, state, limit=20):
        for _ in range(limit):
            if self.ledger.order(order_id)['state'] == state:
                return
            self.d.tick()
        raise AssertionError(f'{order_id} 가 {state} 에 닿지 않았다: {self.ledger.order(order_id)}')

    def applied(self, kind=None):
        counts = S.StubWorld(self.tmp / 'world.json', self.clock).state['applied']
        return counts if kind is None else counts[kind]

    def names(self, order_id):
        return self.ledger.event_names(order_id)


@pytest.fixture
def rig(tmp_path):
    return Rig(tmp_path)


def test_normal_round_trip_delivers_once_and_closes_the_mission(rig):
    oid = rig.order()
    rig.d.run()
    order, pod = rig.ledger.order(oid), rig.ledger.pod('POD-1')
    assert (order['state'], order['mission']) == (L.DELIVERED, L.MISSION_CLOSED)
    assert (pod['custody'], pod['holder']) == (L.RECEIVER, DEST)
    assert rig.applied() == dict.fromkeys(S.KINDS, 1)
    names = rig.names(oid)
    assert names.index('STAT_ORDER_DELIVERED') < len(names) - 1      # 인계 확정 뒤에 복귀 commit
    assert names.count('STAT_ORDER_DELIVERED') == 1


def test_incident_without_approval_never_commands_the_world(rig):
    ingest_observation(rig.ledger, EmergencyObservation('cam', 'b1', 1, 'R1', 'B1', rig.clock.t, ('fall',)))
    rig.clock.t += 3600
    rig.d.run()
    assert rig.applied() == dict.fromkeys(S.KINDS, 0)
    assert rig.ledger.orders() == []


def test_lost_dispense_ack_is_reconciled_without_a_second_dispense(rig):
    rig.world.inject('drop_ack:DISPENSE')
    oid = rig.order()
    rig.d.run()
    assert rig.ledger.order(oid)['state'] == L.DELIVERED
    assert rig.applied(S.DISPENSE) == 1


def test_lost_release_result_is_committed_once_from_observation(rig):
    rig.world.inject('drop_result:RELEASE', -1)
    oid = rig.order()
    rig.d.run()
    assert rig.ledger.order(oid)['state'] == L.IN_TRANSIT or rig.ledger.order(oid)['state'] == L.HANDOVER
    rig.clock.t += 6.0                                               # 결과 시한 초과 → 대조
    rig.d.run()
    assert rig.ledger.order(oid)['state'] == L.DELIVERED
    assert rig.applied(S.RELEASE) == 1
    assert rig.names(oid).count('STAT_ORDER_DELIVERED') == 1


@pytest.mark.parametrize('point', ['after_intent', 'after_send', 'before_commit'])
@pytest.mark.parametrize('kind', [S.DISPENSE, S.RELEASE])
def test_crash_at_each_boundary_recovers_without_repeating_the_physical_step(rig, point, kind):
    oid = rig.order()

    def crash(where, op_id):
        if where == point and op_id.endswith(kind):
            raise Crash(where)
    rig.d.crash = crash
    with pytest.raises(Crash):
        rig.d.run()
    rig.reopen()                                                     # 새 generation, 열린 op 는 RECONCILE
    assert rig.ledger.meta('generation') == 2
    rig.d.run()
    assert rig.ledger.order(oid)['state'] == L.DELIVERED
    assert rig.applied() == dict.fromkeys(S.KINDS, 1)
    assert [p['pod_id'] for p in rig.ledger.pods() if p['custody'] == L.SOURCE] == ['POD-2']


def test_device_that_lost_its_records_is_not_blindly_resent(rig):
    oid = rig.order()

    def crash(where, op_id):
        if where == 'after_intent' and op_id.endswith(S.DISPENSE):
            raise Crash(where)
    rig.d.crash = crash
    with pytest.raises(Crash):
        rig.d.run()
    rig.world.forget_records()
    rig.reopen()
    assert rig.ledger.pod('POD-1')['custody'] == L.UNKNOWN           # 재시작 직후: 명령이 작용했는지 모른다
    rig.d.run()
    assert rig.ledger.order(oid)['state'] == L.PAUSED_RECONCILE      # 받았는지 모른다: 사람이 본다
    assert rig.ledger.pod('POD-1')['custody'] == L.SOURCE            # 관측으로 확인한 위치
    assert rig.applied(S.DISPENSE) == 0


def test_stale_generation_command_is_refused_by_the_device(rig):
    rig.order()
    rig.d.run()
    before = rig.applied()
    ack = rig.world.send(S.Command('STAT-0009/DISPENSE', S.DISPENSE, 'POD-2', '', 1, 0, 99))
    assert (ack.status, ack.reason) == (S.DEV_REJECTED, 'stale_generation')
    assert rig.applied() == before


def test_results_for_other_epochs_or_finished_ops_change_nothing(rig):
    rig.world.inject('hold:DISPENSE')
    oid = rig.order()
    rig.until(oid, L.RESERVED)
    rig.d.tick()                                                     # 수락만 되고 아직 적용 전
    op_id = f'{oid}/DISPENSE'
    assert not rig.d.on_result(op_id, epoch=0)                       # 다른 epoch
    assert not rig.d.on_result('STAT-0404/DISPENSE', epoch=1)       # 모르는 op
    assert rig.ledger.op(op_id)['status'] == 'SENT'
    assert rig.d.on_result(op_id, epoch=1)                           # 맞는 결과여도 관측이 "전" 이면 확정 못 한다
    assert rig.ledger.op(op_id)['status'] == 'RECONCILE' and rig.applied(S.DISPENSE) == 0
    rig.world.apply_pending()
    rig.d.run()
    assert rig.ledger.order(oid)['state'] == L.DELIVERED
    assert not rig.d.on_result(op_id, epoch=1)                       # 끝난 op 의 늦은 결과
    assert rig.names(oid).count('STAT_STALE_RESULT') == 2
    assert rig.applied(S.DISPENSE) == 1


@pytest.mark.parametrize('fault', ['stale_obs', 'no_obs'])
def test_missing_or_repeated_observation_keeps_custody_unknown_to_the_ledger(rig, fault):
    oid = rig.order()
    rig.until(oid, L.RESERVED)
    rig.d.tick()                                                     # DISPENSE 사전 관측·전송
    rig.world.inject(fault, -1)
    rig.d.run()
    rig.clock.t += 6.0
    rig.d.run()
    assert rig.ledger.order(oid)['state'] == L.PAUSED_RECONCILE
    assert rig.ledger.pod('POD-1')['custody'] == L.UNKNOWN           # 세계에선 PICKUP 이지만 관측이 없다
    assert rig.applied(S.LOAD) == 0
    rig.world.inject(fault, 0)
    rig.clock.t += 1.0
    rig.d.run()
    assert rig.ledger.order(oid)['state'] == L.DELIVERED
    assert rig.applied(S.DISPENSE) == 1


def test_old_observation_is_not_used_to_commit(rig):
    oid = rig.order()
    rig.until(oid, L.RESERVED)
    rig.d.tick()                                                     # DISPENSE 전송. 세계에선 이미 적용
    rig.world.clock = lambda: rig.clock.t - 5.0                      # 표본 시각이 5 s 늦다
    rig.d.run()
    assert rig.ledger.order(oid)['state'] == L.PAUSED_RECONCILE
    assert rig.ledger.pod('POD-1')['custody'] == L.UNKNOWN
    rig.world.clock = rig.clock
    rig.d.run()
    assert rig.ledger.order(oid)['state'] == L.DELIVERED


def occupy(rig, station, pod_id='POD-2'):
    """다른 물건이 목적지 수납칸에 있는 세계. 원장은 모른다."""
    rig.world.state['pods'][pod_id].update(location=S.AT_RECEIVER, holder=station)
    rig.world.save()


def test_occupied_destination_blocks_dispense_and_release(rig):
    occupy(rig, DEST)
    waiting = rig.order(1)
    rig.d.run()
    assert rig.ledger.order(waiting)['state'] == L.ACCEPTED and rig.applied(S.DISPENSE) == 0
    assert rig.names(waiting).count('STAT_ORDER_WAITING') == 1      # 사유가 바뀔 때만 기록
    handover = rig.order(2, dest=OTHER)
    rig.until(handover, L.HANDOVER)
    occupy(rig, OTHER)
    rig.d.run()
    assert rig.ledger.order(handover)['state'] == L.HANDOVER
    assert rig.ledger.op(f'{handover}/RELEASE') is None and rig.applied(S.RELEASE) == 0


def test_wrong_pod_on_the_stage_is_recorded_and_not_loaded(rig):
    rig.world.inject('wrong_pod')
    oid = rig.order()
    rig.d.run()
    assert (rig.ledger.order(oid)['state'], rig.ledger.op(f'{oid}/DISPENSE')['reason']) == \
        (L.PAUSED_RECONCILE, 'pod_mismatch')
    wrong = rig.ledger.pod('POD-2')
    assert (wrong['custody'], wrong['hold']) == (L.PICKUP_STAGE, L.HOLD_RECONCILE)
    assert rig.applied(S.LOAD) == 0


def test_arrival_at_the_wrong_station_never_releases(rig):
    rig.world.inject('wrong_station')
    oid = rig.order()
    rig.d.run()
    order, pod = rig.ledger.order(oid), rig.ledger.pod('POD-1')
    assert (order['state'], order['reason'], order['mission']) == (L.FAILED, 'destination_mismatch',
                                                                   L.MISSION_CLOSED)
    assert (pod['custody'], pod['hold']) == (L.DRONE, L.HOLD_RECOVERY)
    assert rig.applied(S.RELEASE) == 0


@pytest.mark.parametrize('kind, state, custody', [
    (S.DISPENSE, L.SOURCE, L.SOURCE),
    (S.RELEASE, L.DRONE, L.DRONE),
])
def test_device_failure_stops_the_order_where_the_pod_actually_is(rig, kind, state, custody):
    rig.world.inject(f'fail:{kind}')
    oid = rig.order()
    rig.d.run()
    order, pod = rig.ledger.order(oid), rig.ledger.pod('POD-1')
    assert (order['state'], order['reason']) == (L.FAILED, f'{kind.lower()}_failed')
    assert (pod['custody'], pod['hold']) == (custody, '' if custody == L.SOURCE else L.HOLD_RECOVERY)
    assert rig.applied(kind) == 0
    assert not rig.ledger.pod('POD-1')['reserved_by'] or custody != L.SOURCE   # 출고 전 실패면 예약을 놓는다


def test_failure_is_not_confirmed_while_results_keep_disappearing(rig):
    rig.world.inject('fail:DISPENSE')
    rig.world.inject('drop_result:DISPENSE', -1)                     # 실패했다는 결과조차 오지 않는다
    oid = rig.order()
    rig.d.run()
    rig.clock.t += 6.0
    rig.d.run()
    assert rig.ledger.order(oid)['state'] == L.PAUSED_RECONCILE      # 실패로도 성공으로도 단정하지 않는다
    assert rig.ledger.pod('POD-1')['custody'] == L.SOURCE            # 관측으로 본 위치는 기록한다
    assert rig.applied(S.DISPENSE) == 0
    rig.world.inject('drop_result:DISPENSE', 0)
    rig.d.run()
    assert (rig.ledger.order(oid)['state'], rig.ledger.order(oid)['reason']) == (L.FAILED, 'dispense_failed')
    assert rig.applied(S.DISPENSE) == 0


def test_order_without_a_matching_pod_fails_before_any_command(rig):
    oid = rig.order(kit_revision='k9')                               # 재고에 없는 kit revision
    rig.d.run()
    assert (rig.ledger.order(oid)['state'], rig.ledger.order(oid)['reason']) == (L.FAILED, 'no_qualified_pod')
    assert rig.applied() == dict.fromkeys(S.KINDS, 0)
    assert [p['reserved_by'] for p in rig.ledger.pods()] == ['', '']


def test_waits_when_the_precheck_observation_is_missing_or_disagrees(rig):
    oid = rig.order()
    rig.until(oid, L.RESERVED)
    rig.world.inject('no_obs', -1)
    rig.d.run()
    assert rig.ledger.order(oid)['reason'] == 'observation_unavailable'
    rig.world.inject('no_obs', 0)
    rig.world.state['pods']['POD-1'].update(location=S.AT_DRONE, holder=rig.world.drone_id)   # 누가 옮겼다
    rig.world.save()
    rig.d.run()
    assert rig.ledger.order(oid)['reason'] == 'precheck_mismatch'
    assert rig.ledger.order(oid)['state'] == L.RESERVED
    assert rig.applied() == dict.fromkeys(S.KINDS, 0)
    assert rig.names(oid).count('STAT_ORDER_WAITING') == 2           # 사유가 바뀔 때만


def test_executor_fenced_by_a_newer_generation_changes_nothing(rig):
    oid = rig.order()
    rig.until(oid, L.RESERVED)
    rig.world.send(S.Command('other/DISPENSE', S.DISPENSE, 'POD-2', '', 1, 99, 1))   # 더 새 generation 이 왔다
    before = rig.applied()
    rig.d.run()
    assert 'STAT_COMMAND_FENCED' in rig.names(oid)
    assert rig.ledger.order(oid)['state'] == L.RESERVED
    assert rig.applied(S.LOAD) == before[S.LOAD]


def test_cancel_and_missing_order(rig):
    assert rig.d.cancel('STAT-0404') == 'order_unknown'


def test_return_failure_after_delivery_keeps_the_delivery(rig):
    rig.world.inject('fail:RETURN')
    oid = rig.order()
    rig.d.run()
    order = rig.ledger.order(oid)
    assert (order['state'], order['mission']) == (L.DELIVERED, L.MISSION_FAULT)


def test_ledger_write_failure_before_a_command_sends_nothing(rig):
    oid = rig.order()
    rig.ledger.fail_labels.add('intent')
    with pytest.raises(LedgerWriteError):
        rig.d.run()
    assert rig.applied(S.DISPENSE) == 0 and rig.ledger.ops(oid) == []
    rig.ledger.fail_labels.clear()
    rig.d.run()
    assert rig.ledger.order(oid)['state'] == L.DELIVERED
    assert rig.applied(S.DISPENSE) == 1


@pytest.mark.parametrize('stage, custody, hold, applied_kinds', [
    (L.RESERVED, L.SOURCE, '', ()),
    (L.PREPARING, L.PICKUP_STAGE, L.HOLD_RECOVERY, (S.DISPENSE,)),
    (L.HANDOVER, L.DRONE, L.HOLD_RECOVERY, (S.DISPENSE, S.LOAD, S.FLY, S.RETURN)),
])
def test_cancel_ends_where_the_pod_physically_is(rig, stage, custody, hold, applied_kinds):
    oid = rig.order()
    rig.until(oid, stage)
    assert rig.d.cancel(oid) == ''
    rig.d.run()
    pod = rig.ledger.pod('POD-1')
    assert rig.ledger.order(oid)['state'] == L.CANCELLED
    assert (pod['custody'], pod['hold']) == (custody, hold)
    assert rig.applied() == {k: int(k in applied_kinds) for k in S.KINDS}
    assert rig.d.cancel(oid) == 'already_done'


def test_cancel_after_delivery_is_refused(rig):
    oid = rig.order()
    rig.d.run()
    assert rig.d.cancel(oid) == 'already_delivered'
    assert rig.ledger.order(oid)['state'] == L.DELIVERED


def test_approval_rechecked_before_irreversible_steps(rig):
    expired = rig.order(1)
    rig.until(expired, L.RESERVED)
    rig.clock.t += 601
    rig.d.run()
    assert rig.ledger.order(expired)['state'] == L.EXPIRED
    revoked = rig.order(2)
    rig.until(revoked, L.HANDOVER)
    revoke_approval(rig.ledger, 'APR-2')
    rig.d.run()
    assert rig.ledger.order(revoked)['reason'] == 'approval_revoked'
    assert rig.applied(S.DISPENSE) == 1 and rig.applied(S.RELEASE) == 0


def test_expiry_after_dispense_does_not_stop_a_pod_already_in_the_air(rig):
    oid = rig.order()
    rig.until(oid, L.LOADED)
    rig.clock.t += 601                                               # 출고 뒤 승인 만료. 철회는 아니다
    rig.d.run()
    assert rig.ledger.order(oid)['state'] == L.DELIVERED             # 계약: 만료는 출고 전에만 막는다
    assert rig.applied(S.RELEASE) == 1


def test_late_success_after_timeout_is_reconciled_and_cannot_touch_the_next_order(rig):
    rig.world.inject('hold:DISPENSE')
    first = rig.order(1)
    rig.d.run()
    rig.clock.t += 6.0
    rig.d.run()
    assert rig.ledger.op(f'{first}/DISPENSE')['status'] == 'RECONCILE'
    rig.world.apply_pending()                                        # 늦게 적용됨
    rig.d.run()
    assert rig.ledger.order(first)['state'] == L.DELIVERED
    rig.world.inject('hold:DISPENSE')
    second = rig.order(2, dest=OTHER)
    rig.until(second, L.RESERVED)
    rig.d.tick()
    assert not rig.d.on_result(f'{first}/RELEASE', epoch=1)          # 앞 주문의 늦은 결과
    assert rig.ledger.order(second)['state'] == L.RESERVED
    assert rig.applied(S.DISPENSE) == 1


def test_resubmitted_request_after_delivery_does_not_dispense_again(rig):
    oid = rig.order()
    rig.d.run()
    req = OrderRequest('REQ-1', 'INC-0001', 'APR-1', 'r1', 'SUBJ', 'SIM-KIT-A', 'k1', DEST)
    assert submit_order(rig.ledger, req, rig.clock.t) == ('REPLAY', '', oid)
    rig.d.run()
    assert rig.applied(S.DISPENSE) == 1


def test_sample_not_newer_than_the_intent_floor_is_not_fresh(rig):
    op = {'floor_boot': 'world-1', 'floor_seq': 10}

    def sample(seq, boot='world-1', age=0.0):
        return S.Observation('POD-1', S.AT_PICKUP, S.AT_PICKUP, (), boot, seq, rig.clock.t - age)
    assert not rig.d._fresh(sample(10), op) and not rig.d._fresh(sample(9), op)
    assert rig.d._fresh(sample(11), op)
    assert rig.d._fresh(sample(1, boot='world-2'), op)              # 장치 재부팅: 하한 대신 나이만 본다
    assert not rig.d._fresh(sample(12, age=1.5), op)
