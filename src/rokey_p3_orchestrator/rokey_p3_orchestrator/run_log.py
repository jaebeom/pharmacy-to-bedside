"""run 기록. 이벤트·주문 상태·평가 관측을 한 줄 JSON 으로. ROS 를 import 하지 않는다.

event_logger 가 쓰는 로직이다. 여기서 정하는 것은 두 가지다.

- **run 기록의 SUCCESS 는 /evaluator/cabinet 관측만이 근거다**(계약 8절, 시나리오 5절).
  오케스트레이터가 낸 DELIVERED 는 주장이고, 주장만으로는 SUCCESS 가 되지 않는다.
  관측은 그 run 에 주장(OrderStatus)이 있는 주문에만 쓴다. 요청한 적 없는 주문이 관측만으로 SUCCESS 가 되지 않는다.
- **run 경계**(RunBook). epoch 가 오르면 새 run 을 열고, 이전 run 은 drain_s(wall) 동안 열어 둔다.
  /events·/orders/status·/evaluator/cabinet 은 다른 토픽이라 도착 순서가 정해지지 않기 때문이다.
  - 이벤트는 epoch 로, 주문 상태는 request_id 로(그 request_id 를 아는 run) 보낸다. order_id 만으로 묶지 않는다.
  - 보관함 관측은 새 run 이 자기 RESET_DONE 을 보기 전에는 새 run 판정에 쓰지 않는다. 이전 run 이 열려 있으면
    그쪽에, 아니면 새 run 에 pre_reset 으로 남긴다.
  - 닫힌 run 은 고치지 않는다. drain 뒤에 온 이전 epoch 이벤트는 새 run 에 stale, 이전 요청의 상태는 late 로 남긴다.
"""

import json
import os
import re

from rokey_p3_orchestrator.terminal_states import ABORT, HOLD_RETURN, SUCCESS, TIMEOUT
from rokey_p3_orchestrator.trip_fsm import EVENT_RESET_DONE

# 오케스트레이터의 주장. 종료 상태가 아니다(ADR 0001 주문 상태 절).
CLAIM_ACCEPTED = 'ACCEPTED'
CLAIM_IN_PROGRESS = 'IN_PROGRESS'
CLAIM_DELIVERED = 'DELIVERED'

REASON_NOT_OBSERVED = 'eval_not_observed'
REASON_CLAIM_DISAGREES = 'claim_disagrees'
REASON_NOT_TERMINAL = 'run_ended_before_terminal'
REASON_CLAIMED_SUCCESS = 'orchestrator_claimed_success'

# OrderStatus.msg 의 state 값 → 이름. 2 는 인터페이스 v1.1 의 STATE_DELIVERED 다.
ORDER_STATE_NAMES = {
    0: CLAIM_ACCEPTED,
    1: CLAIM_IN_PROGRESS,
    2: CLAIM_DELIVERED,
    10: SUCCESS,
    11: HOLD_RETURN,
    12: ABORT,
    13: TIMEOUT,
}

_HOST = re.compile(r'^[a-z0-9][a-z0-9-]{0,31}$')
_NONCE = re.compile(r'^[0-9a-f]{8}$')


def state_name(value):
    """OrderStatus.state 정수를 이름으로. 모르는 값은 그대로 보여 준다."""
    return ORDER_STATE_NAMES.get(value, f'UNKNOWN_{value}')


def run_id(started_utc, host, nonce):
    """naming.md 의 run ID = UTC compact + host + 8자리 hex."""
    if not _HOST.match(host or ''):
        raise ValueError(f'host 가 run ID 규칙에 안 맞는다: {host!r}')
    if not _NONCE.match(nonce or ''):
        raise ValueError(f'nonce 는 8자리 소문자 hex 여야 한다: {nonce!r}')
    return f"{started_utc.strftime('%Y%m%dT%H%M%SZ')}-{host}-{nonce}"


def jsonl(record):
    """한 줄 JSON. 키 순서를 고정해 diff 가 읽힌다."""
    return json.dumps(record, ensure_ascii=False, sort_keys=True) + '\n'


def judge(claim, observed, reason=''):
    """run 기록의 종료 상태를 정한다.

    관측이 있으면 SUCCESS 다. 관측이 없으면 오케스트레이터의 주장으로 닫되
    DELIVERED 주장은 SUCCESS 가 아니라 ABORT(eval_not_observed)다.
    """
    if observed:
        if claim in (HOLD_RETURN, ABORT, TIMEOUT):
            return SUCCESS, REASON_CLAIM_DISAGREES
        return SUCCESS, ''
    if claim == CLAIM_DELIVERED:
        return ABORT, REASON_NOT_OBSERVED
    if claim in (HOLD_RETURN, ABORT, TIMEOUT):
        return claim, reason
    if claim == SUCCESS:
        # 계약 2.5절: 오케스트레이터는 SUCCESS 를 내지 않는다. 냈으면 기록에 남긴다.
        return ABORT, REASON_CLAIMED_SUCCESS
    return ABORT, REASON_NOT_TERMINAL


class OrderLedger:
    """한 run 동안 주문마다 무엇을 주장했고 무엇이 관측됐는지 모은다."""

    def __init__(self):
        self._orders = {}

    def _row(self, order_id):
        return self._orders.setdefault(order_id, {
            'order_id': order_id,
            'request_id': '',
            'claim': '',
            'claim_reason': '',
            'observed': False,
            'cabinet_id': '',
        })

    def note_status(self, order_id, state, reason='', request_id=''):
        """OrderStatus 한 건. 나중 것이 앞의 주장을 덮는다."""
        row = self._row(order_id)
        row['claim'] = state
        row['claim_reason'] = reason
        if request_id:
            row['request_id'] = request_id

    def claimed(self, order_id):
        """이 run 에서 그 주문의 상태를 받은 적이 있나."""
        return order_id in self._orders

    def note_observation(self, order_id, cabinet_id, present):
        """CabinetObservation 한 건. present=true 한 번이면 관측된 것이다. 판정에 썼으면 True.

        이 run 에서 상태를 받은 적 없는 주문은 쓰지 않는다(행을 만들지 않는다). 리셋 전 트립이 놓은 봉투나
        요청하지 않은 주문이 관측만으로 SUCCESS 가 되지 않게 한다.
        """
        if not self.claimed(order_id):
            return False
        row = self._orders[order_id]
        if present:
            row['observed'] = True
            row['cabinet_id'] = cabinet_id
        return True

    def records(self):
        """주문마다 run 기록 한 줄. 처음 본 순서를 지킨다."""
        out = []
        for row in self._orders.values():
            state, reason = judge(row['claim'], row['observed'], row['claim_reason'])
            out.append({
                'order_id': row['order_id'],
                'request_id': row['request_id'],
                'claim': row['claim'],
                'observed': row['observed'],
                'cabinet_id': row['cabinet_id'],
                'state': state,
                'reason': reason,
            })
        return out


RUN_FILES = ('events', 'order_status', 'cabinet')


class RunRecord:
    """run 디렉토리 하나. 받은 그대로의 JSONL 셋과 주문 원장. 닫을 때 orders.jsonl·meta.json 을 쓴다."""

    def __init__(self, root, run_id, host, epoch, started, observing):
        self.run_id = run_id
        self.host = host
        self.epoch = epoch
        self.started = started
        self.dir = os.path.join(root, run_id)
        os.makedirs(self.dir, exist_ok=True)
        # run 이 끝날 때까지 콜백마다 append 하므로 with 로 감쌀 수 없다. close 가 닫는다.
        self._files = {name: open(os.path.join(self.dir, f'{name}.jsonl'), 'w', encoding='utf-8')  # noqa: SIM115
                       for name in RUN_FILES}
        self.ledger = OrderLedger()
        self.counts = {'events': 0, 'order_status': 0, 'cabinet': 0, 'stale': 0, 'late': 0, 'pre_reset': 0}
        self.request_ids = set()
        self.observing = observing          # 보관함 관측을 판정에 쓰나. 시작 run 이거나 자기 RESET_DONE 을 봤다
        self.closed_by_reset_epoch = None   # 이 run 을 끝낸 리셋의 epoch. 종료 경로로 닫혔으면 None
        self.drain_until = None             # 이전 run 으로 늦은 메시지를 받는 마감(wall)
        self.closed = False

    def write(self, name, record):
        handle = self._files[name]
        handle.write(jsonl(record))
        handle.flush()
        self.counts[name] += 1

    def close(self, ended):
        """orders.jsonl·meta.json 을 쓰고 파일을 닫는다. 두 번째부터는 아무것도 안 한다. 주문 수를 돌려준다."""
        if self.closed:
            return None
        orders = self.ledger.records()
        with open(os.path.join(self.dir, 'orders.jsonl'), 'w', encoding='utf-8') as handle:
            for record in orders:
                handle.write(jsonl(record))
        meta = {
            'run_id': self.run_id,
            'host': self.host,
            'epoch': self.epoch,
            'started_utc': self.started.strftime('%Y-%m-%dT%H:%M:%SZ'),
            'ended_utc': ended.strftime('%Y-%m-%dT%H:%M:%SZ'),
            'closed_by_reset_epoch': self.closed_by_reset_epoch,
            'counts': dict(self.counts),
            'orders': len(orders),
        }
        with open(os.path.join(self.dir, 'meta.json'), 'w', encoding='utf-8') as handle:
            handle.write(jsonl(meta))
        for handle in self._files.values():
            handle.close()
        self.closed = True
        return len(orders)


class RunBook:
    """열린 run 들과 run 경계(계약 6절). 메시지마다 어느 run 에 쓸지 정한다.

    시각은 호출하는 쪽이 넣는다(now_wall 은 monotonic). now_utc·nonce 는 run ID·meta 용이고 테스트가 바꾼다.
    """

    def __init__(self, root, host, drain_s, now_utc, nonce, log=None, epoch=1):
        self._root = root
        self._host = host
        self.drain_s = float(drain_s)
        self._now_utc = now_utc
        self._nonce = nonce
        self._log = log or (lambda text: None)
        self._closed_requests = set()       # 닫힌 run 이 알던 request_id. 그 뒤에 온 상태는 late 다
        self.draining = []                  # epoch 가 올라 끝났지만 drain_until 까지 늦은 메시지를 받는 run
        self.shut = False                   # close_all 뒤. 메시지를 버리고 run 을 새로 열지 않는다
        self.current = self._open(epoch, observing=True)

    def _open(self, epoch, observing):
        started = self._now_utc()
        run = RunRecord(self._root, run_id(started, self._host, self._nonce()), self._host, epoch, started, observing)
        self._log(f'run {run.run_id} 시작. epoch={epoch} 위치 {run.dir}')
        return run

    def _close(self, run):
        orders = run.close(self._now_utc())
        if orders is None:
            return
        self._closed_requests |= run.request_ids
        self._log(f'run {run.run_id} 끝. 주문 {orders}건 {run.counts}')

    def runs(self):
        """열린 run 전부. 오래된 것부터."""
        return self.draining + [self.current]

    def expire(self, now_wall):
        """drain 마감이 지난 이전 run 을 닫는다."""
        keep = []
        for run in self.draining:
            if now_wall >= run.drain_until:
                self._close(run)
            else:
                keep.append(run)
        self.draining = keep

    def close_all(self):
        """종료 경로. 열린 run 을 모두 닫는다. 두 번 불려도 두 번째는 아무것도 안 한다."""
        for run in self.runs():
            self._close(run)
        self.draining = []
        self.shut = True

    def _rotate(self, epoch, now_wall):
        previous = self.current
        previous.closed_by_reset_epoch = epoch
        previous.drain_until = now_wall + self.drain_s
        self.draining.append(previous)
        self._log(f'epoch {previous.epoch} -> {epoch}. 새 run 을 연다. '
                  f'이전 run 은 {self.drain_s:g} s 동안 늦은 메시지를 받는다.')
        self.current = self._open(epoch, observing=False)

    def event(self, record, now_wall):
        """Event 한 건(dict). epoch 가 오르면 새 run. 그 epoch 의 run 이 열려 있으면 거기, 아니면 지금 run 에 stale."""
        if self.shut:
            return None
        self.expire(now_wall)
        epoch = record['epoch']
        if epoch > self.current.epoch:
            self._rotate(epoch, now_wall)
            self.expire(now_wall)           # drain_s 가 0 이면 곧바로 닫는다
        run = next((r for r in self.runs() if r.epoch == epoch), None)
        stale = run is None
        target = run or self.current
        if stale:
            target.counts['stale'] += 1
        target.write('events', dict(record, stale=stale))
        if not stale:
            if record.get('request_id'):
                target.request_ids.add(record['request_id'])
            if record.get('name') == EVENT_RESET_DONE:
                target.observing = True
        return target

    def order_status(self, record, now_wall):
        """OrderStatus 한 건(dict). 그 request_id 를 아는 열린 run 에. 모르면 지금 run 이 새로 안다.

        닫힌 run 이 알던 request_id 면 지금 run 에 late 로 적기만 하고 판정(원장)에는 넣지 않는다.
        """
        if self.shut:
            return None
        self.expire(now_wall)
        request_id = record['request_id']
        run = next((r for r in self.runs() if request_id and request_id in r.request_ids), None)
        late = run is None and request_id in self._closed_requests
        target = run or self.current
        target.write('order_status', dict(record, late=late))
        if late:
            target.counts['late'] += 1
            return target
        if request_id:
            target.request_ids.add(request_id)
        target.ledger.note_status(record['order_id'], record['state'], record['reason'], request_id)
        return target

    def cabinet(self, record, now_wall):
        """CabinetObservation 한 건(dict). 지금 run 이 자기 RESET_DONE 을 보기 전이면 이전 run(열려 있으면)에 쓴다.

        관측을 쓸 run 도 아직 RESET_DONE 전이면 pre_reset 으로 적기만 한다(판정에 안 쓴다).
        """
        if self.shut:
            return None
        self.expire(now_wall)
        target = self.current
        if not target.observing and self.draining:
            target = self.draining[-1]
        pre_reset = not target.observing
        used = False
        if pre_reset:
            target.counts['pre_reset'] += 1
        else:
            used = target.ledger.note_observation(record['order_id'], record['cabinet_id'], record['present'])
        target.write('cabinet', dict(record, pre_reset=pre_reset, used=used))
        return target
