"""상태 모니터 화면. 받은 메시지를 모으고(StatusModel) 텍스트 화면 한 장으로 만든다(render). ROS 를 import 하지 않는다.

status_monitor 노드가 구독한 메시지를 dict 로 바꿔 넣고, 1 Hz 로 render 결과를 터미널에 그린다.
시연·통합 때 한 화면으로 흐름을 보는 용도다(시나리오의 마스터 2 상태 GUI 자리). 판정에는 쓰지 않는다.

- 신선도는 wall 로 잰다(계약 4절). 상태 토픽(H) 1.0 s, /clock 2.0 s 를 넘으면 unknown·멈춤으로 보인다.
- 트립 상태는 최근 이벤트 이름으로 **추정**한 것이다. orchestrator FSM 의 상태를 읽는 것이 아니다.
- 이벤트는 도착 순서가 아니라 순서 키(event_key: epoch, 리셋 구분선, stamp, 도착 순번)로 줄 세운다.
  `/events` 는 latched(transient local)라 늦게 붙으면 작성자별 이력이 작성자 단위로 뭉쳐 온다(정비 실행 관측).
- 폭은 고정폭 글꼴·한 글자 한 칸으로 가정한다(한글 폭은 맞추지 않는다).
"""

import argparse

SIGNAL_FRESH_S = 1.0         # 계약 4절: 상태 토픽(H)
CLOCK_FRESH_S = 2.0          # 계약 4절: /clock
MAX_EVENTS = 12
EVENT_BUFFER = 500           # /events latched 깊이와 같다. 넘치면 순서 키가 가장 이른 것부터 버린다
MAX_ORDERS = 8
DETAIL_WIDTH = 40

EVENT_RESET_BEGIN = 'RESET_BEGIN'
EVENT_RESET_DONE = 'RESET_DONE'

#: 인터락 신호 화면 순서. (키, 이름표)
SIGNALS = (
    ('arm_at_home', 'arm/at_home'),
    ('base_stopped', 'base/stopped'),
    ('gripper_holding', 'gripper/holding'),
    ('belt', 'belt'),
    ('m0609_at_home', 'm0609 at_home'),
)

#: 최근 트립 이벤트 → 추정 단계. 조제기·M0609 이벤트는 트립 단계를 바꾸지 않는다.
TRIP_PHASES = {
    'REQUEST_ACCEPTED': '적재 위치로 이동',
    'AMR_DOCKED_LOAD': '배출',
    'DISPENSED': '벨트 이송',
    'POUCH_AT_END': '벨트 끝 픽',
    'PICK_ATTEMPT': '픽',
    'POUCH_PICKED': '픽',
    'POUCH_LOADED': '적재',
    'LOAD_DONE': '적재 끝',
    'ARM_HOME': '팔 홈',
    'DEPARTED': '병동으로 이동',
    'ARRIVING': '병동 도착 직전',
    'ARRIVED': '인증',
    'AUTH_OK': '보관함 배달',
    'AUTH_FAIL': '인증 실패',
    'POUCH_DETECTED': '보관함 배달',
    'POUCH_PLACED': '보관함 배달',
    'CABINET_LOCKED': '보관함 잠김',
    'ORDER_DONE': '주문 닫힘',
    'RETURNED': '도크로 복귀',
    'DOCKED': '대기(도크)',
    EVENT_RESET_BEGIN: '리셋 중',
    EVENT_RESET_DONE: '리셋 끝(3 s 뒤 요청 수락)',
}


def parse_options(argv):
    """노드 인자. ROS 인자는 빼고 넘긴다."""
    parser = argparse.ArgumentParser(prog='status_monitor', description='P3 상태 모니터(텍스트)')
    parser.add_argument('--once', action='store_true', help='메시지를 잠깐 모은 뒤 한 번 찍고 끝낸다')
    parser.add_argument('--no-clear', action='store_true', help='화면을 지우지 않고 이어 쓴다(tmux 로그용)')
    parser.add_argument('--with-evaluator', action='store_true',
                        help='/evaluator/cabinet 도 구독한다(평가 전용 경로, 기본 꺼짐)')
    parser.add_argument('--robot-id', default='amr_1', help='AMR 네임스페이스(기본 amr_1)')
    return parser.parse_args(argv)


def clip(text, width):
    text = str(text)
    return text if len(text) <= width else text[:max(0, width - 2)] + '..'


def event_key(event):
    """이벤트 순서 키: (epoch, 구분, stamp, 도착 순번).

    - epoch 가 먼저다. 리셋은 sim time 을 되감으므로 epoch 사이에서는 stamp 를 비교할 수 없다.
    - 한 epoch 안에서 RESET_BEGIN(0) → RESET_DONE(1) → 나머지(2). RESET_BEGIN 은 이전 epoch 의 sim stamp 를 싣고
      (끊긴 주문과 같은 stamp) RESET_DONE 은 되감긴 뒤의 stamp 라, stamp 만으로는 구분선이 제자리에 안 선다.
    - 같은 epoch·구분·stamp 면 도착 순번(seq)이다(안정 정렬). seq 가 없으면 0.
    """
    rank = {EVENT_RESET_BEGIN: 0, EVENT_RESET_DONE: 1}.get(event['name'], 2)
    return int(event['epoch']), rank, float(event['stamp']), event.get('seq', 0)


class StatusModel:
    """받은 메시지를 화면에 필요한 만큼만 모은다. 모든 시각 인자는 wall(monotonic) 이다."""

    def __init__(self, max_events=MAX_EVENTS, event_buffer=EVENT_BUFFER):
        self.max_events = max_events
        self.event_buffer = max(event_buffer, max_events)
        self.epoch = 0
        self.clock = None                # (sim 초, 받은 wall)
        self.events = []                 # 받은 이벤트 dict(도착 순번 seq 포함). 순서는 recent_events 가 정한다
        self._seq = 0
        self.trip_event = None           # 트립 단계를 정한 이벤트 이름(순서 키가 가장 늦은 트립 이벤트)
        self._trip_key = None
        self.orders = {}                 # (request_id, order_id) → dict. 넣은 순서 = 처음 본 순서
        self.request_epochs = {}         # request_id → 처음 본 epoch
        self.dispenser = None            # (dict, 받은 wall)
        self.signals = {}                # 키 → (값, 받은 wall)
        self.observed = {}               # order_id → cabinet_id (--with-evaluator)

    def recent_events(self):
        """화면에 그릴 최근 max_events 건. 순서 키 순이다."""
        return sorted(self.events, key=event_key)[-self.max_events:]

    def note_clock(self, sim_s, wall):
        self.clock = (float(sim_s), wall)

    def note_event(self, event):
        """event: stamp·epoch·name·request_id·order_id·robot_id·detail."""
        self.epoch = max(self.epoch, int(event['epoch']))
        self._seq += 1
        stored = dict(event, seq=self._seq)
        self.events.append(stored)
        if len(self.events) > self.event_buffer:
            self.events.sort(key=event_key)
            del self.events[:-self.event_buffer]
        key = event_key(stored)
        if event['name'] in TRIP_PHASES and (self._trip_key is None or key > self._trip_key):
            self._trip_key = key
            self.trip_event = event['name']
        if event.get('request_id'):
            self.request_epochs.setdefault(event['request_id'], int(event['epoch']))

    def note_order(self, status):
        """status: request_id·order_id·state(이름)·reason. 처음 본 request_id 는 지금 epoch 로 적는다."""
        request_id = status['request_id']
        epoch = self.request_epochs.setdefault(request_id, self.epoch)
        key = (request_id, status['order_id'])
        row = self.orders.pop(key, {})
        row.update(status, epoch=epoch)
        self.orders[key] = row           # 마지막으로 바뀐 행이 뒤로 간다

    def note_dispenser(self, status, wall):
        """status: slots(item_id·slot·lot_id·count·active 목록)·paused_item_ids·queue_length·belt_occupied."""
        self.dispenser = (status, wall)

    def note_signal(self, key, value, wall):
        self.signals[key] = (value, wall)

    def note_cabinet(self, order_id, cabinet_id, present):
        if present:
            self.observed[order_id] = cabinet_id


def _age(wall, now):
    return now - wall


def _freshness(entry, now, limit):
    """(값, 표시 문자열). 한 번도 안 왔으면 (None, 'never'), 넘었으면 (None, 'unknown (age N s)')."""
    if entry is None:
        return None, 'unknown (never)'
    value, wall = entry
    age = _age(wall, now)
    if age > limit:
        return None, f'unknown (age {age:.1f} s)'
    return value, f'{age:.1f} s'


def _header(model, now, options):
    if model.clock is None:
        clock_text = 'sim -, /clock never'
    else:
        sim_s, wall = model.clock
        age = _age(wall, now)
        state = 'ok' if age <= CLOCK_FRESH_S else 'STOPPED'
        clock_text = f'sim {sim_s:.1f} s, /clock {state} (age {age:.1f} s)'
    phase = TRIP_PHASES.get(model.trip_event, '-')
    source = f' <- {model.trip_event}' if model.trip_event else ''
    lines = [
        f'P3 status_monitor  epoch {model.epoch}  {clock_text}',
        f'trip (estimated from events): {phase}{source}',
    ]
    if options.get('with_evaluator'):
        lines.append('evaluator: /evaluator/cabinet subscribed (evaluation path, not for operation)')
    return lines


def _orders(model, options):
    lines = ['', f'ORDERS (latest {MAX_ORDERS}, /orders/status)']
    rows = list(model.orders.values())
    if not rows:
        return lines + ['  (none)']
    header = f"  {'epoch':>5}  {'request_id':<12} {'order_id':<10} {'state':<12} reason"
    if options.get('with_evaluator'):
        header += '  [seen]'
    lines.append(header)
    shown = rows[-MAX_ORDERS:]
    hidden = len(rows) - len(shown)
    for row in reversed(shown):
        marker = ' ' if row['epoch'] == model.epoch else '*'
        line = (f"  {marker}{row['epoch']:>4}  {clip(row['request_id'], 12):<12} {clip(row['order_id'], 10):<10} "
                f"{clip(row['state'], 12):<12} {clip(row.get('reason', ''), 24)}")
        if options.get('with_evaluator'):
            seen = model.observed.get(row['order_id'])
            line += f"  [{clip(seen, 16) if seen else '-'}]"
        lines.append(line)
    if hidden:
        lines.append(f'  .. {hidden} older rows hidden')
    if any(row['epoch'] != model.epoch for row in shown):
        lines.append('  * = request from an earlier epoch')
    return lines


def _dispenser(model, now):
    lines = ['', 'DISPENSER (/pharmacy/dispenser/status)']
    status, text = _freshness(model.dispenser, now, float('inf'))
    if status is None:
        return lines + ['  (no status yet)']
    lines[-1] += f'  age {text}  queue {status.get("queue_length", 0)}  belt_occupied {status.get("belt_occupied")}'
    items = {}
    for slot in status.get('slots', []):
        items.setdefault(slot['item_id'], {})[slot['slot']] = slot
    paused = set(status.get('paused_item_ids', []))
    if not items:
        lines.append('  (no slots)')
    for item_id in sorted(items):
        cells = []
        for index, name in ((0, 'A'), (1, 'B')):
            slot = items[item_id].get(index)
            if slot is None:
                cells.append(f'{name}: -')
                continue
            active = '*' if slot.get('active') else ' '
            cells.append(f"{name}{active} {clip(slot.get('lot_id', ''), 14):<14} x{slot.get('count', 0):<3}")
        flag = '  PAUSED' if item_id in paused else ''
        lines.append(f"  {clip(item_id, 12):<12} {'  '.join(cells)}{flag}")
    for item_id in sorted(paused - set(items)):
        lines.append(f'  {clip(item_id, 12):<12} (no slots)  PAUSED')
    return lines


def _signals(model, now):
    lines = ['', f'INTERLOCK SIGNALS (unknown after {SIGNAL_FRESH_S:g} s wall)']
    for key, label in SIGNALS:
        value, text = _freshness(model.signals.get(key), now, SIGNAL_FRESH_S)
        if value is None:
            shown = text
        elif key == 'belt':
            shown = (f"occupied={value.get('occupied')} at_end={value.get('at_end')} "
                     f"order_id={value.get('order_id') or '-'}  ({text})")
        else:
            shown = f'{value}  ({text})'
        lines.append(f'  {label:<16} {shown}')
    return lines


def _events(model):
    lines = ['', f'EVENTS (latest {model.max_events}, /events)']
    if not model.events:
        return lines + ['  (none)']
    for event in model.recent_events():
        if event['name'] in (EVENT_RESET_BEGIN, EVENT_RESET_DONE):
            detail = f" {event['detail']}" if event.get('detail') else ''
            lines.append(f"  ---- {event['name']} epoch {event['epoch']}{detail} ----")
            continue
        lines.append(f"  {event['stamp']:>9.2f}  {clip(event.get('robot_id', ''), 9):<9} "
                     f"{clip(event['name'], 17):<17} {clip(event.get('order_id', ''), 10):<10} "
                     f"{clip(event.get('detail', ''), DETAIL_WIDTH)}")
    return lines


def render(model, now, options=None):
    """화면 한 장. 줄 목록이다. now 는 wall(monotonic)."""
    options = options or {}
    return (_header(model, now, options) + _orders(model, options) + _dispenser(model, now)
            + _signals(model, now) + _events(model))


CLEAR = '\x1b[H\x1b[2J'


def frame(lines, clear):
    """터미널에 쓸 문자열. clear 면 ANSI 로 지우고 맨 위부터 다시 쓴다."""
    body = '\n'.join(lines) + '\n'
    return (CLEAR + body) if clear else ('=' * 60 + '\n' + body)
