"""STAT S0 작업 실행: 예약 → 출고 → 탑재 → 비행 → 인계 → 복귀, 관측 대조와 재시작 복구. ROS 를 import 하지 않는다.

계약 4–7절(docs/architecture/stat-delivery-contract-v1.md, proposed).

- 모든 명령은 INTENT 를 원장에 쓴 뒤에만 보낸다. 쓰기가 실패하면 보내지 않는다.
- custody·주문 진행은 fresh 관측으로만 commit 한다. 장치 ACK·결과는 관측을 받을 계기일 뿐이다.
- 응답이 사라지거나 시한을 넘기면 재전송하지 않고 대조한다. 재전송은 장치가 그 op 를 받은 적 없다고 답하고
  관측이 "전" 상태일 때 같은 op id 로 한 번뿐이다.
- 이 모듈은 주문 소유자(원장)의 상태를 미는 함수 묶음이다. 별도 총괄 노드가 아니다.
"""

from rokey_p3_orchestrator import stat_ledger as L
from rokey_p3_orchestrator import stat_stub as S
from rokey_p3_orchestrator.stat_intake import AUTHORIZED_ROLES, approval_problem

INTENT = 'INTENT'
SENT = 'SENT'
COMMITTED = 'COMMITTED'
OP_FAILED = 'FAILED'
RECONCILE = 'RECONCILE'
OPEN = (INTENT, SENT, RECONCILE)

NEXT_KIND = {L.RESERVED: S.DISPENSE, L.PREPARING: S.LOAD, L.LOADED: S.FLY, L.HANDOVER: S.RELEASE}
AFTER_STATE = {S.DISPENSE: L.PREPARING, S.LOAD: L.LOADED, S.FLY: L.HANDOVER, S.RELEASE: L.DELIVERED}
POD_KINDS = (S.DISPENSE, S.LOAD, S.RELEASE)
CUSTODY_AT = {S.AT_SOURCE: L.SOURCE, S.AT_PICKUP: L.PICKUP_STAGE, S.AT_DRONE: L.DRONE, S.AT_RECEIVER: L.RECEIVER}
BUSY = frozenset({L.RESERVED, L.PREPARING, L.LOADED, L.IN_TRANSIT, L.HANDOVER, L.PAUSED_RECONCILE})


class StatDispatcher:
    """원장의 STAT 주문을 stub 장치로 한 단계씩 민다. 시계는 주입한다(wall: 승인 만료, mono: 시한·관측 나이)."""

    def __init__(self, ledger, world, wall, mono, result_timeout_s=5.0, obs_max_age_s=1.0,
                 roles=AUTHORIZED_ROLES):
        self.ledger = ledger
        self.world = world
        self.wall = wall
        self.mono = mono
        self.result_timeout_s = result_timeout_s
        self.obs_max_age_s = obs_max_age_s
        self.roles = roles
        self.crash = lambda point, op_id: None      # 시험·CLI 가 crash 지점을 끼운다

    # 시작·재시작
    def start(self):
        """원장 복구 → generation +1 → 열린 op 를 모두 RECONCILE. 명령은 보내지 않는다."""
        with self.ledger.tx('start') as c:
            generation = self.ledger.bump(c, 'generation')
            for op in c.execute("SELECT * FROM ops WHERE status IN ('INTENT', 'SENT')").fetchall():
                c.execute('UPDATE ops SET status = ?, reason = ? WHERE op_id = ?',
                          (RECONCILE, 'restart', op['op_id']))
                if op['kind'] in POD_KINDS:                 # 명령이 작용했는지 모른다
                    c.execute("UPDATE pods SET custody = ?, holder = '' WHERE reserved_by = ?",
                              (L.UNKNOWN, op['order_id']))
                c.execute('UPDATE orders SET state = ? WHERE order_id = ? AND state NOT IN (?, ?, ?, ?)',
                          (L.PAUSED_RECONCILE, op['order_id'], *sorted(L.ORDER_DONE)))
            self.ledger.emit(c, 'STAT_DISPATCH_STARTED', generation=generation)
        return generation

    def run(self, max_ticks=50):
        """더 진행할 것이 없을 때까지 tick. 돈 횟수."""
        for n in range(max_ticks):
            if not self.tick():
                return n
        return max_ticks

    def tick(self):
        """주문마다 최대 한 단계. 무언가 바뀌었으면 True. 앞 주문이 움직여도 뒤 주문을 건너뛰지 않는다."""
        moved = False
        for order in self.ledger.orders():
            moved = self._step(order) or moved
        return moved

    # 외부 입력
    def cancel(self, order_id):
        order = self.ledger.order(order_id)
        if order is None:
            return 'order_unknown'
        if order['state'] == L.DELIVERED:
            return 'already_delivered'
        if order['state'] in L.ORDER_DONE:
            return 'already_done'
        with self.ledger.tx('cancel') as c:
            c.execute('UPDATE orders SET cancel_requested = 1 WHERE order_id = ?', (order_id,))
            self.ledger.emit(c, 'STAT_CANCEL_REQUESTED', order_id)
        return ''

    def on_result(self, op_id, epoch):
        """장치 결과 콜백. 지금 기다리는 op 의 것이 아니면 버린다. 맞아도 관측으로만 commit 한다."""
        op = self.ledger.op(op_id)
        order = self.ledger.order(op['order_id']) if op else None
        if op is None or epoch != self.ledger.meta('epoch') or op['status'] not in (SENT, RECONCILE):
            with self.ledger.tx('stale') as c:
                self.ledger.emit(c, 'STAT_STALE_RESULT', op['order_id'] if op else '', op_id=op_id, epoch=epoch)
            return False
        return self._settle(order, op, S.DEV_APPLIED)

    # 한 단계
    def _step(self, order):
        op = self.ledger.op(order['current_op']) if order['current_op'] else None
        if op is not None and op['status'] in OPEN:
            return self._advance(order, op)
        if order['state'] in L.ORDER_DONE:
            if order['mission'] == L.MISSION_ACTIVE and not self._op_done(order, S.RETURN):
                return self._begin(order, S.RETURN)
            return False
        if order['cancel_requested']:
            return self._stop(order, L.CANCELLED, 'cancel_requested')
        if order['state'] == L.ACCEPTED:
            return self._reserve(order)
        kind = NEXT_KIND.get(order['state'])
        if kind is None:
            return False
        problem = self._recheck(order, kind)
        if problem:
            return self._stop(order, *problem)
        return self._begin(order, kind)

    def _op_done(self, order, kind):
        op = self.ledger.op(f"{order['order_id']}/{kind}")
        return op is not None and op['status'] not in OPEN

    def _recheck(self, order, kind):
        """단계별 승인 재확인. 출고 전에는 만료·철회, 비행·해제 전에는 철회만 본다."""
        problem = approval_problem(self.ledger.approval(order['approval_id']), self.wall(), self.roles)
        if problem == 'approval_expired' and kind != S.DISPENSE:
            return None
        if problem == 'approval_expired':
            return L.EXPIRED, problem
        if problem == 'approval_revoked':
            return L.CANCELLED, problem
        return (L.FAILED, problem) if problem else None

    def _reserve(self, order):
        if any(o['state'] in BUSY or o['mission'] == L.MISSION_ACTIVE for o in self.ledger.orders()):
            return False                                   # 기체 1대. 앞 주문을 기다린다
        if not self._station_ready(order, docked=False):
            return self._wait(order, 'destination_not_ready')   # 목적지 수납칸을 출고 전에 확인한다(계획서 12.2)
        pods = [p for p in self.ledger.pods() if p['kit_id'] == order['kit_id']
                and p['kit_revision'] == order['kit_revision'] and p['quality'] == L.QUALIFIED
                and p['custody'] == L.SOURCE and not p['reserved_by'] and not p['hold']]
        if not pods:
            return self._stop(order, L.FAILED, 'no_qualified_pod')
        with self.ledger.tx('reserve') as c:
            c.execute('UPDATE pods SET reserved_by = ? WHERE pod_id = ?', (order['order_id'], pods[0]['pod_id']))
            c.execute('UPDATE orders SET state = ?, pod_id = ? WHERE order_id = ?',
                      (L.RESERVED, pods[0]['pod_id'], order['order_id']))
            self.ledger.emit(c, 'STAT_ORDER_RESERVED', order['order_id'], pod_id=pods[0]['pod_id'])
        return True

    def _wait(self, order, reason):
        """명령 없이 기다린다. 사유가 바뀔 때만 기록한다."""
        if order['reason'] == reason:
            return False
        with self.ledger.tx('wait') as c:
            c.execute('UPDATE orders SET reason = ? WHERE order_id = ?', (reason, order['order_id']))
            self.ledger.emit(c, 'STAT_ORDER_WAITING', order['order_id'], reason=reason)
        return True

    def _stop(self, order, state, reason):
        """주문을 끝낸다. Pod 는 관측된 custody 그대로 두고, SOURCE 밖이면 회수 보류를 건다."""
        with self.ledger.tx('stop') as c:
            pod = c.execute('SELECT * FROM pods WHERE pod_id = ?', (order['pod_id'],)).fetchone()
            if pod is not None and pod['custody'] == L.SOURCE:
                c.execute("UPDATE pods SET reserved_by = '' WHERE pod_id = ?", (pod['pod_id'],))
            elif pod is not None and pod['custody'] != L.RECEIVER:
                c.execute('UPDATE pods SET hold = ? WHERE pod_id = ?', (L.HOLD_RECOVERY, pod['pod_id']))
            c.execute("UPDATE orders SET state = ?, reason = ?, current_op = '' WHERE order_id = ?",
                      (state, reason, order['order_id']))
            self.ledger.emit(c, f'STAT_ORDER_{state}', order['order_id'], reason=reason)
        return True

    # 명령
    def _subject(self, order, kind):
        return self.world.drone_id if kind in (S.FLY, S.RETURN) else order['pod_id']

    def _begin(self, order, kind):
        """사전 관측 → INTENT 기록 → 명령. 사전 관측이 fresh 하지 않거나 "전" 이 아니면 보내지 않는다."""
        pre = self.world.observe(self._subject(order, kind))
        if not self._fresh(pre):
            return self._wait(order, 'observation_unavailable')
        if self._phase(order, kind, pre) != 'before':
            return self._wait(order, 'precheck_mismatch')
        if kind == S.RELEASE and not self._station_ready(order):
            return self._wait(order, 'destination_not_ready')
        op_id = f"{order['order_id']}/{kind}"
        state = L.IN_TRANSIT if kind == S.FLY else order['state']
        mission = L.MISSION_ACTIVE if kind == S.FLY else order['mission']
        reason = order['reason'] if state in L.ORDER_DONE else ''       # 대기 사유만 지운다. 종료 사유는 남긴다
        with self.ledger.tx('intent') as c:
            seq = self.ledger.bump(c, 'command_seq')
            c.execute('INSERT INTO ops VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                      (op_id, order['order_id'], kind, INTENT, self.ledger.meta('generation'), seq,
                       pre.boot_id, pre.seq, state, None, ''))
            c.execute('UPDATE orders SET current_op = ?, state = ?, mission = ?, reason = ? WHERE order_id = ?',
                      (op_id, state, mission, reason, order['order_id']))
            self.ledger.emit(c, 'STAT_OP_INTENT', order['order_id'], op_id=op_id, command_seq=seq)
        self.crash('after_intent', op_id)
        self._send(self.ledger.op(op_id), order)
        return True

    def _send(self, op, order):
        cmd = S.Command(op['op_id'], op['kind'], order['pod_id'], order['destination_id'],
                        self.ledger.meta('epoch'), self.ledger.meta('generation'), op['command_seq'])
        try:
            ack = self.world.send(cmd)
        except S.ResponseLost:
            ack = None
        self.crash('after_send', op['op_id'])
        if ack is not None and ack.status == S.DEV_REJECTED:
            with self.ledger.tx('fenced') as c:              # 더 새 generation 이 있다. 이 실행기는 손을 뗀다
                self.ledger.emit(c, 'STAT_COMMAND_FENCED', order['order_id'], op_id=op['op_id'], reason=ack.reason)
            return False
        with self.ledger.tx('sent') as c:
            c.execute('UPDATE ops SET status = ?, sent_at = ?, generation = ?, reason = ? WHERE op_id = ?',
                      (SENT, self.mono(), cmd.generation, '' if ack else 'ack_lost', op['op_id']))
            c.execute('UPDATE orders SET state = ? WHERE order_id = ? AND state = ?',
                      (op['prior_state'], order['order_id'], L.PAUSED_RECONCILE))
            self.ledger.emit(c, 'STAT_OP_SENT', order['order_id'], op_id=op['op_id'], ack=bool(ack))
        return True

    def _advance(self, order, op):
        if op['status'] != SENT:
            return self._reconcile(order, op)
        status = self._query(op)
        if status in (S.DEV_APPLIED, S.DEV_FAILED):
            return self._settle(order, op, status)
        if self.mono() - op['sent_at'] > self.result_timeout_s:
            return self._to_reconcile(order, op, 'result_timeout', None)
        return False

    def _query(self, op):
        try:
            return self.world.query(op['op_id'])
        except S.ResponseLost:
            return None

    def _settle(self, order, op, status):
        """장치가 결과를 냈다. 관측이 "후" 면 commit, 실패가 관측으로도 맞으면 실패, 아니면 대조."""
        obs = self.world.observe(self._subject(order, op['kind']))
        phase = self._phase(order, op['kind'], obs) if self._fresh(obs, op) else 'unknown'
        if phase == 'after':
            return self._commit(order, op, obs)
        if phase == 'before' and status == S.DEV_FAILED:
            return self._fail(order, op, f"{op['kind'].lower()}_failed", obs)
        wrong = op['kind'] == S.DISPENSE and phase in ('before', 'elsewhere') and self._note_stage(order)
        reason = 'pod_mismatch' if wrong or phase == 'elsewhere' else f'unconfirmed_{phase}'
        return self._to_reconcile(order, op, reason, obs if phase != 'unknown' else None)

    def _reconcile(self, order, op):
        status = self._query(op)
        obs = self.world.observe(self._subject(order, op['kind']))
        phase = self._phase(order, op['kind'], obs) if self._fresh(obs, op) else 'unknown'
        if phase == 'after':
            return self._commit(order, op, obs)
        if phase == 'before' and status == S.DEV_UNKNOWN_OPERATION:
            return self._send(op, order)                    # 받은 적 없다: 같은 op id 로 한 번
        if phase == 'before' and status == S.DEV_FAILED:
            return self._fail(order, op, f"{op['kind'].lower()}_failed", obs)
        if phase == 'unknown' or op['kind'] not in POD_KINDS:
            return False                                    # ACCEPTED 는 기다리고, 나머지는 사람이 본다
        custody = CUSTODY_AT.get(obs.location, L.UNKNOWN)
        if self.ledger.pod(order['pod_id'])['custody'] == custody:
            return False
        with self.ledger.tx('observed') as c:                # 확정은 못 해도 본 위치는 기록한다
            self._record_custody(c, order['pod_id'], obs)
            self.ledger.emit(c, 'STAT_CUSTODY_OBSERVED', order['order_id'], custody=custody, sample_seq=obs.seq)
        return True

    def _to_reconcile(self, order, op, reason, obs):
        """결과를 확정하지 못했다. Pod custody 는 fresh 관측이 있으면 그 위치, 없으면 UNKNOWN."""
        if op['status'] == RECONCILE and op['reason'] == reason:
            return False
        with self.ledger.tx('reconcile') as c:
            c.execute('UPDATE ops SET status = ?, reason = ? WHERE op_id = ?', (RECONCILE, reason, op['op_id']))
            if op['kind'] in POD_KINDS:
                self._record_custody(c, order['pod_id'], obs)
            c.execute('UPDATE orders SET state = ? WHERE order_id = ? AND state NOT IN (?, ?, ?, ?)',
                      (L.PAUSED_RECONCILE, order['order_id'], *sorted(L.ORDER_DONE)))
            self.ledger.emit(c, 'STAT_OP_RECONCILE', order['order_id'], op_id=op['op_id'], reason=reason)
        return True

    def _fail(self, order, op, reason, obs):
        with self.ledger.tx('op_failed') as c:
            c.execute('UPDATE ops SET status = ?, reason = ? WHERE op_id = ?', (OP_FAILED, reason, op['op_id']))
            if op['kind'] in POD_KINDS:
                self._record_custody(c, order['pod_id'], obs)
            if op['kind'] == S.RETURN:
                c.execute("UPDATE orders SET mission = ?, current_op = '' WHERE order_id = ?",
                          (L.MISSION_FAULT, order['order_id']))
            self.ledger.emit(c, 'STAT_OP_FAILED', order['order_id'], op_id=op['op_id'], reason=reason)
        if op['kind'] != S.RETURN and order['state'] not in L.ORDER_DONE:
            return self._stop(self.ledger.order(order['order_id']), L.FAILED, reason)
        return True

    def _commit(self, order, op, obs):
        """관측으로 확인된 물리 사실을 한 번 기록한다."""
        self.crash('before_commit', op['op_id'])
        kind, order_id, pod_id = op['kind'], order['order_id'], order['pod_id']
        wrong_station = kind == S.FLY and obs.location != order['destination_id']
        with self.ledger.tx('commit') as c:
            c.execute("UPDATE ops SET status = ?, reason = '' WHERE op_id = ?", (COMMITTED, op['op_id']))
            if kind in POD_KINDS:
                self._record_custody(c, pod_id, obs)
            if kind == S.RETURN:
                c.execute("UPDATE orders SET mission = ?, current_op = '' WHERE order_id = ?",
                          (L.MISSION_CLOSED, order_id))
            elif order['state'] in L.ORDER_DONE:
                c.execute("UPDATE orders SET current_op = '' WHERE order_id = ?", (order_id,))
            else:
                c.execute("UPDATE orders SET state = ?, current_op = '' WHERE order_id = ?",
                          (AFTER_STATE[kind], order_id))
            if kind == S.RELEASE:
                c.execute("UPDATE pods SET reserved_by = '' WHERE pod_id = ?", (pod_id,))
            self.ledger.emit(c, 'STAT_OP_COMMITTED', order_id, op_id=op['op_id'], location=obs.location,
                             holder=obs.holder, sample_seq=obs.seq)
            if kind == S.RELEASE:
                self.ledger.emit(c, 'STAT_ORDER_DELIVERED', order_id, station=obs.holder)
        if wrong_station:
            return self._stop(self.ledger.order(order_id), L.FAILED, 'destination_mismatch')
        return True

    # 관측
    def _record_custody(self, c, pod_id, obs):
        """Pod custody 를 fresh 관측의 위치로, 관측이 없으면 UNKNOWN 으로 쓴다. tx 안에서 부른다."""
        custody = CUSTODY_AT.get(obs.location, L.UNKNOWN) if obs else L.UNKNOWN
        c.execute('UPDATE pods SET custody = ?, holder = ? WHERE pod_id = ?',
                  (custody, obs.holder if obs else '', pod_id))

    def _fresh(self, obs, op=None):
        """없는 표본, 오래된 표본, INTENT 때보다 새롭지 않은 표본은 fresh 가 아니다."""
        if obs is None or self.mono() - obs.stamp > self.obs_max_age_s:
            return False
        return op is None or obs.boot_id != op['floor_boot'] or obs.seq > op['floor_seq']

    def _phase(self, order, kind, obs):
        """관측이 이 작업의 "전"·"후"·제3의 위치 중 어디인가."""
        loc, holder = obs.location, obs.holder
        if kind == S.DISPENSE:
            return {S.AT_SOURCE: 'before', S.AT_PICKUP: 'after'}.get(loc, 'elsewhere')
        if kind == S.LOAD:
            return {S.AT_PICKUP: 'before', S.AT_DRONE: 'after'}.get(loc, 'elsewhere')
        if kind == S.RELEASE:
            if loc == S.AT_RECEIVER and holder == order['destination_id']:
                return 'after'
            return 'before' if loc == S.AT_DRONE else 'elsewhere'
        if kind == S.RETURN:
            return 'after' if loc == self.world.dock_id else 'before'
        return 'before' if loc == self.world.dock_id else 'after'          # FLY: 도크를 떠나 어딘가에 도착

    def _station_ready(self, order, docked=True):
        """목적지 태그·빈 수납칸이 fresh 관측으로 맞아야 한다. 인계 전에는 기체 도킹도 본다."""
        obs = self.world.observe(order['destination_id'])
        return (self._fresh(obs) and obs.location == order['destination_id'] and not obs.occupants
                and (not docked or obs.holder == self.world.drone_id))

    def _note_stage(self, order):
        """출고 뒤 픽업 스테이지에 다른 Pod 가 있으면 그 Pod 의 관측 위치를 기록한다(잘못된 Pod)."""
        obs = self.world.observe(S.AT_PICKUP)
        wrong = [p for p in obs.occupants if p != order['pod_id']] if self._fresh(obs) else []
        if wrong:
            with self.ledger.tx('stage') as c:
                for pod_id in wrong:
                    c.execute('UPDATE pods SET custody = ?, holder = ?, hold = ? WHERE pod_id = ?',
                              (L.PICKUP_STAGE, S.AT_PICKUP, L.HOLD_RECONCILE, pod_id))
                    self.ledger.emit(c, 'STAT_WRONG_POD_OBSERVED', order['order_id'], pod_id=pod_id)
        return bool(wrong)
