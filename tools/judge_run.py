#!/usr/bin/env python3
"""회차 판정 집계. 로그와 run 기록을 **읽기만** 하고 센다. 판정선은 기준 파일에 있다.

사람이 손으로 세다 틀린 자리를 기계가 대신 센다. 9/21 하루에만 이런 것들이 있었다.

- 보충 수를 "바퀴 x 3" 으로 곱해 추정(실제 41 건인데 44 건으로 보고).
- `grep '409'` 가 포트 번호(`45976`)를 잡아 거부 0 건을 19 건으로.
- `grep 'GroundPlane'` 만 세어 `near`(impulse 0) 오탐을 낙하로.
- "새 종류 WARN 0" 이 실은 arm 로그만 센 값. stack 의 SIGINT 줄은 노드 이름표가 없어 빠졌다.
- PLAY 시각을 폴링 시각으로 잡아 "전부 PLAY 이전" 이라고 판정.

그래서 이 도구의 규칙은 셋이다.

1. **센 값 옆에 근거 원문 한 줄을 같이 낸다.** 수치만 믿지 않게 한다.
2. **판정선을 박지 않는다.** 기준 파일(`--criteria`)과 대조해서 맞는지만 말한다.
3. 아무것도 고치지 않는다. 로그도 run 기록도 열어서 읽기만 한다.

쓰기:

    python3 tools/judge_run.py --logs ~/p3_demo_logs --stamp 20260921-120631 \\
        --run ~/.ros/rokey_p3/runs/20260921T030746Z-master02-c445420a \\
        --criteria tools/judge_criteria.example.yaml --json /tmp/judge.json

**회차에 run 이 있으면 `--run` 을 준다.** 한 기동의 stage.log 에는 여러 run 이 함께 들어 있어서,
주지 않으면 보충·낙하가 세션 전체로 세어진다. 스테이지만 돌린 회차(run 없음)는 그대로 세션 전체다.

2026-09-21 에 master02 에서 실습22(run 둘)·23b·24a 로그에 돌려 손 집계와 대조했다(맥마클2).
그때 나온 두 가지를 고쳤다: run 구간으로 자르기, 같은 줄이 두 로그에 있을 때 한 번만 세기.
"""

import argparse
import json
import os
import re

# -- 로그 줄 모양 -------------------------------------------------------------

#: Kit 줄의 머리. `2026-09-21T03:06:40Z [9,246ms] [Warning] [omni.hydra] ...`
KIT_HEAD = re.compile(r'^(?P<utc>\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ) \[(?P<ms>[\d,]+)ms\]')
#: 스테이지 자신의 줄. 시각이 없다.
STAGE_TAG = '[pharmacy_stage]'
#: PLAY. kit 로그에서는 `[py stdout]: [pharmacy_stage] timeline_event type=PLAY` 로 나온다.
PLAY = 'timeline_event type=PLAY'
#: 세 가지 표기를 다 잡는다. arm `[WARN]`, launch `[WARNING]`, Kit `[Warning]`.
WARN_TAG = re.compile(r'\[warn(?:ing)?\]', re.I)
ERROR_TAG = re.compile(r'\[error\]', re.I)
#: 진단 줄의 `"stack": [...]` 나 `traceback.format_stack` 에 걸리지 않게 이 문장으로만 센다.
TRACEBACK = 'Traceback (most recent call last)'
#: 웹 접근 로그. 포트 번호에 걸리지 않게 상태 코드 자리로만 본다.
HTTP_STATUS = re.compile(r'HTTP/1\.\d" (?P<code>\d{3})')

RELEASED = re.compile(r'refill_ros released cell=(?P<cell>\S+) ')
RESPAWN = re.compile(r'refill_ros respawn cell=(?P<cell>\S+) ')
CONTACT = re.compile(r'contact (?:found|persist) (?P<kind>touch|near) a=(?P<a>\S+) b=(?P<b>\S+) '
                     r'impulse=(?P<impulse>[\d.]+)')
#: 보충 단계 시간 줄. 끝의 `, ok):` / `, failed):` 가 결과를 가른다.
REFILL_RESULT = re.compile(r'Refill (?P<item>\S+) 단계 시간\([^)]*, (?P<result>ok|failed)\):')
STOP_LINE = re.compile(r'stop reason=(?P<reason>\S+)')
#: 스테이지 줄의 sim 시각. run 구간으로 자를 때 쓴다.
SIM_TIME = re.compile(r'sim_time=(?P<sim>[\d.]+)')


def read_lines(path):
    """없으면 빈 목록. 깨진 바이트는 버리지 않고 대체 문자로 읽는다."""
    if not path or not os.path.exists(path):
        return []
    with open(path, encoding='utf-8', errors='replace') as handle:
        return handle.read().splitlines()


def read_jsonl(path):
    return [json.loads(line) for line in read_lines(path) if line.strip()]


def evidence(index, line, limit=200):
    """근거 한 줄. 행 번호는 1 부터."""
    return {'line_no': index + 1, 'text': line.strip()[:limit]}


# -- PLAY 로 자르기 -----------------------------------------------------------

def kit_ms(line):
    """Kit 줄의 ms 카운터. 스테이지 자신의 줄처럼 머리가 없으면 None."""
    match = KIT_HEAD.match(line)
    return int(match.group('ms').replace(',', '')) if match else None


def play_ms(kit_lines):
    """PLAY 의 ms 카운터. **줄 번호로 자르지 않는다** — stage.log 는 순서가 시각 순서와 다르다."""
    for line in kit_lines:
        if PLAY in line:
            return kit_ms(line)
    return None


# -- WARN 종류 ---------------------------------------------------------------

def warn_kind(text):
    """같은 말인데 숫자·경로·시각만 다른 줄을 한 종류로 묶는 서명."""
    text = WARN_TAG.sub('[WARN]', text)
    text = re.sub(r'\[\d+\.\d+\]', '[T]', text)                 # ROS 시각
    text = re.sub(r'^\S+Z \[[\d,]+ms\] ', '', text)             # Kit 머리
    text = re.sub(r'/[\w./@:+-]+', 'PATH', text)                # 경로
    text = re.sub(r'\d+(?:[.,]\d+)?', 'N', text)                # 남은 수
    return ' '.join(text.split())[:200]


def warn_rows(lines, after_ms=None):
    """WARN 줄과 그 ms 카운터. `after_ms` 를 주면 그보다 이른 Kit 줄은 뺀다."""
    for index, line in enumerate(lines):
        if not WARN_TAG.search(line):
            continue
        stamp = kit_ms(line)
        if after_ms is not None and stamp is not None and stamp < after_ms:
            continue
        yield index, line, stamp


def merged_warn_kinds(lines_by_role, baseline=(), after_ms=None, cut_roles=('stage', 'kit')):
    """역할을 가로질러 종류별로 센다. **같은 줄이 두 로그에 있으면 한 번만 센다.**

    스테이지는 stdout 을 stage.log 로 tee 하고 Kit 은 같은 줄을 kit.log 에도 쓴다. 역할별로 세면
    그 줄이 x2 가 된다(맥마클2, 실습22 대조). 시각이 있는 줄은 (ms, 원문)으로, 없는 줄은
    (역할, 행 번호)로 하나임을 가린다.
    """
    kinds, seen = {}, set()
    for role, lines in lines_by_role.items():
        cut = after_ms if role in cut_roles else None
        for index, line, stamp in warn_rows(lines, cut):
            text = line.strip()
            identity = ('stamped', stamp, text) if stamp is not None else (role, index, text)
            kind = warn_kind(line)
            row = kinds.setdefault(kind, {'kind': kind, 'count': 0, 'evidence': evidence(index, line),
                                          'known': kind in baseline, 'roles': []})
            if role not in row['roles']:
                row['roles'].append(role)      # 어느 로그에 있었는지는 남긴다(수는 한 번만 센다)
            if identity in seen:
                continue
            seen.add(identity)
            row['count'] += 1
    return sorted(kinds.values(), key=lambda row: (-row['count'], row['kind']))


def warn_kinds(lines, baseline=(), after_ms=None):
    """WARN 을 종류별로 센다. `after_ms` 를 주면 그 카운터보다 이른 Kit 줄은 뺀다.

    머리가 없는 줄(`[pharmacy_stage]` 가 낸 것)은 자를 기준이 없으므로 **언제나 센다**.
    """
    kinds = {}
    for index, line in enumerate(lines):
        if not WARN_TAG.search(line):
            continue
        stamp = kit_ms(line)
        if after_ms is not None and stamp is not None and stamp < after_ms:
            continue
        kind = warn_kind(line)
        row = kinds.setdefault(kind, {'kind': kind, 'count': 0, 'evidence': evidence(index, line),
                                      'known': kind in baseline, 'timestamped': stamp is not None})
        row['count'] += 1
    return sorted(kinds.values(), key=lambda row: (-row['count'], row['kind']))


# -- 낙하 (#397) --------------------------------------------------------------

def drops(stage_lines):
    """released 와 respawn 사이에서 그 칸의 통이 바닥에 `touch` 하고 impulse 가 0 보다 큰 것.

    **행 순서로 구간을 잡는다**(sim 시각이 아니다). 같은 칸의 released 가 여러 번 나오므로
    시각으로 짝을 지으면 틀린다(맥마클1, 실습21d). 바닥 충돌체가 `geom`·`collisionPlane` 둘이라
    한 사건이 두 줄로 나올 수 있어 **구간마다 1 건으로 접는다**.
    """
    open_cells = {}          # 칸 -> (released 행, [근거])
    found = []
    for index, line in enumerate(stage_lines):
        released = RELEASED.search(line)
        if released:
            open_cells[released.group('cell')] = {'cell': released.group('cell'),
                                                  'released': evidence(index, line), 'hits': []}
            continue
        respawn = RESPAWN.search(line)
        if respawn:
            span = open_cells.pop(respawn.group('cell'), None)
            if span and span['hits']:
                span['respawn'] = evidence(index, line)
                found.append(span)
            continue
        contact = CONTACT.search(line)
        if not contact or contact.group('kind') != 'touch':
            continue
        if '/GroundPlane/' not in contact.group('b') or float(contact.group('impulse')) <= 0.0:
            continue
        for span in open_cells.values():
            if contact.group('a').endswith(span['cell'].replace('/', '_')):
                span['hits'].append(evidence(index, line))
    # 아직 respawn 이 오지 않은 구간도 낙하로 센다(회차가 그 사이에 끝났을 수 있다).
    for span in open_cells.values():
        if span['hits']:
            found.append(span)
    return found


# -- 보충 --------------------------------------------------------------------

def sim_window(events):
    """이 run 의 sim 구간 (처음, 마지막). 이벤트가 없으면 None — 그러면 자르지 않는다."""
    stamps = [float(row['stamp']) for row in events if isinstance(row.get('stamp'), (int, float))]
    return (min(stamps), max(stamps)) if stamps else None


def sim_time_of(line):
    match = SIM_TIME.search(line)
    return float(match.group('sim')) if match else None


def in_window(line, window):
    """stage 줄이 이 run 의 구간 안인가. 구간이 없거나 줄에 sim_time 이 없으면 참으로 본다."""
    if window is None:
        return True
    value = sim_time_of(line)
    return value is None or window[0] <= value <= window[1]


def refills(stage_lines, arm_lines, window=None):
    """스테이지의 `released` 수와 팔의 단계 시간 줄(ok/failed)을 따로 센다.

    `window` 를 주면 stage 쪽은 그 run 의 sim 구간으로 자른다. **팔 로그는 자르지 못한다** —
    그 줄의 시각은 wall 이고 run 경계와 맞출 값이 없다. 그래서 ok/failed 는 **세션 전체**다.
    """
    stage_lines = [line for line in stage_lines if in_window(line, window)]
    released = [evidence(i, line) for i, line in enumerate(stage_lines) if RELEASED.search(line)]
    results = {'ok': [], 'failed': []}
    for index, line in enumerate(arm_lines):
        match = REFILL_RESULT.search(line)
        if match:
            results[match.group('result')].append(evidence(index, line))
    return {'released': len(released), 'released_evidence': released[:1],
            'ok': len(results['ok']), 'failed': len(results['failed']),
            'failed_evidence': results['failed'][:3]}


# -- 트립과 이벤트 순서 --------------------------------------------------------

#: 계약 2.6절 한 바퀴(1인 주문)의 이벤트 차례와 ①-⑩ 단계. 값은 `test_stub_loop.py` 의 `CONTRACT_ORDER` 와 같다.
#: 단계는 "그 단계의 **마지막** 이벤트까지 봤으면 도달" 로 센다. PICK_ATTEMPT·ARM_HOME 처럼 두 번 나오는
#: 이름이 있어서 **자리로** 따라간다(이름만 찾으면 ⑧ 의 픽을 ⑤ 로 센다).
LAP_STAGES = (
    ('①', '요청 접수', ('REQUEST_ACCEPTED',)),
    ('②', '적재 위치 도킹', ('AMR_DOCKED_LOAD',)),
    ('③', '조제', ('DISPENSED',)),
    ('④', '벨트 끝', ('POUCH_AT_END',)),
    ('⑤', '적재 픽', ('PICK_ATTEMPT', 'POUCH_PICKED', 'POUCH_LOADED', 'LOAD_DONE', 'ARM_HOME')),
    ('⑥', '병동 주행', ('DEPARTED', 'ARRIVED')),
    ('⑦', '환자 인증', ('AUTH_OK',)),
    ('⑧', '수령·전달', ('POUCH_DETECTED', 'PICK_ATTEMPT', 'POUCH_PICKED', 'POUCH_PLACED',
                      'CABINET_LOCKED', 'ORDER_DONE')),
    ('⑨', '복귀', ('ARM_HOME', 'RETURNED')),
    ('⑩', '도킹', ('DOCKED',)),
)
LAP_ORDER = tuple(name for _no, _label, names in LAP_STAGES for name in names)


def reached(events):
    """기동 → ①-⑩ 중 어디까지 갔나. 첫 끊김도 같이 낸다.

    한 바퀴(1인 주문) 기준이다. 묶음이나 여러 바퀴는 이 표로 세지 않는다 — 그때는 `trips` 를 본다.
    `stale` 이벤트는 빼고 본다(이전 epoch 의 늦은 것).
    """
    names = [row.get('name') for row in events if not row.get('stale')]
    matched = 0
    for name in names:
        if matched < len(LAP_ORDER) and name == LAP_ORDER[matched]:
            matched += 1
    done, index = [], 0
    for number, label, stage_names in LAP_STAGES:
        index += len(stage_names)
        if matched >= index:
            done.append((number, label))
    stage = f'{done[-1][0]} {done[-1][1]}' if done else '기동(이벤트 0)'
    expected = LAP_ORDER[matched] if matched < len(LAP_ORDER) else None
    for number, label, stage_names in LAP_STAGES:
        if expected in stage_names and (not done or (number, label) != done[-1]):
            break
    return {'stage': stage, 'stages_done': len(done), 'matched_events': matched,
            'expected_next': expected,
            'seen_after': names[matched:matched + 3] if matched < len(names) else []}


def trips(events):
    """요청마다 `REQUEST_ACCEPTED` -> `DOCKED` 까지. 이름은 **필드로 정확히** 비교한다.

    끝나지 않은 요청도 목록에 남긴다(`end_stamp` 없음). `laps` 는 끝난 것만 센다.
    """
    started, out = {}, []
    for row in events:
        name, request = row.get('name'), row.get('request_id') or ''
        if name == 'REQUEST_ACCEPTED':
            started[request] = row
        elif name == 'DOCKED' and request in started:
            begin = started.pop(request)
            out.append({'request_id': request, 'order_id': row.get('order_id') or begin.get('order_id'),
                        'start_stamp': begin.get('stamp'), 'end_stamp': row.get('stamp'),
                        'seconds': round(float(row.get('stamp', 0)) - float(begin.get('stamp', 0)), 3)})
    for request, begin in started.items():
        out.append({'request_id': request, 'order_id': begin.get('order_id'),
                    'start_stamp': begin.get('stamp'), 'end_stamp': None, 'seconds': None})
    return out


def closed_trips(rows):
    """`DOCKED` 로 끝난 트립. `laps` 의 분모다."""
    return [row for row in rows if row.get('end_stamp') is not None]


def open_trips(rows):
    """`REQUEST_ACCEPTED` 만 있고 아직 `DOCKED` 가 없는 트립."""
    return [row for row in rows if row.get('end_stamp') is None]


def order_mismatch(events, expected):
    """이벤트 이름 차례가 기준과 다른 첫 자리. 같으면 None."""
    if not expected:
        return None
    names = [row.get('name') for row in events if not row.get('stale')]
    for index, (got, want) in enumerate(zip(names, expected, strict=False)):
        if got != want:
            return {'at': index, 'expected': want, 'got': got}
    if len(names) != len(expected):
        return {'at': min(len(names), len(expected)), 'expected': expected[len(names):len(names) + 1],
                'got': names[len(expected):len(expected) + 1]}
    return None


# -- 그 밖 --------------------------------------------------------------------

def http_rejects(web_lines):
    """4xx·5xx. `grep 409` 는 포트 번호를 잡는다(맥마클1, 9/21)."""
    out = []
    for index, line in enumerate(web_lines):
        match = HTTP_STATUS.search(line)
        if match and int(match.group('code')) >= 400:
            out.append({'code': int(match.group('code')), **evidence(index, line)})
    return out


def errors(lines):
    out = [evidence(i, line) for i, line in enumerate(lines) if ERROR_TAG.search(line)]
    traces = [evidence(i, line) for i, line in enumerate(lines) if TRACEBACK in line]
    return out, traces


def stop_flags(stage_lines):
    """`stop reason=` 줄의 값들. 없으면 None(회차가 아직 안 끝났거나 로그가 잘렸다)."""
    for index, line in enumerate(reversed(stage_lines)):
        if STOP_LINE.search(line):
            flags = dict(part.split('=', 1) for part in line.split() if '=' in part)
            flags['evidence'] = evidence(len(stage_lines) - index - 1, line)
            return flags
    return None


def cabinet_present(rows):
    """계약 8절: run 기록의 SUCCESS 근거. 빈 파일도 정상이다(`pharmacy_only` 회차)."""
    return [row for row in rows if row.get('present')]


# -- 모으기 -------------------------------------------------------------------

ROLE_LOGS = ('stage', 'kit', 'arm', 'stack', 'web', 'nav')


def collect(logs_dir, stamp, run_dir, criteria):
    """센 것만 담은 사전. 판정은 `verdicts` 가 기준 파일과 대조해서 만든다."""
    text = {role: read_lines(os.path.join(logs_dir, f'{stamp}-{role}.log')) for role in ROLE_LOGS}
    events = read_jsonl(os.path.join(run_dir, 'events.jsonl')) if run_dir else []
    cabinet = read_jsonl(os.path.join(run_dir, 'cabinet.jsonl')) if run_dir else []
    orders = read_jsonl(os.path.join(run_dir, 'orders.jsonl')) if run_dir else []

    baseline = set(criteria.get('warn_baseline', []))
    cut = play_ms(text['kit'])
    window = sim_window(events)
    warn = {}
    for role in ('arm', 'stack', 'web', 'nav'):
        warn[role] = warn_kinds(text[role], baseline)
    warn['stage'] = warn_kinds(text['stage'], baseline, after_ms=cut)
    warn['kit'] = warn_kinds(text['kit'], baseline, after_ms=cut)
    merged = merged_warn_kinds(text, baseline, after_ms=cut)

    every_error, every_trace = [], []
    for role in ROLE_LOGS:
        found, traces = errors(text[role])
        every_error += [{'role': role, **row} for row in found]
        every_trace += [{'role': role, **row} for row in traces]

    return {
        'stamp': stamp, 'run_dir': run_dir, 'play_ms': cut, 'sim_window': window,
        'trips': trips(events),
        'reached': reached(events),
        'event_order': order_mismatch(events, criteria.get('event_order')),
        'refills': {**refills(text['stage'], text['arm'], window),
                    'done_in_run': sum(1 for row in events if row.get('name') == 'REFILL_DONE')},
        'drops': drops([line for line in text['stage'] if in_window(line, window)]),
        'http_rejects': http_rejects(text['web']),
        'errors': every_error, 'tracebacks': every_trace,
        'warn': warn, 'warn_merged': merged,
        'stop': stop_flags(text['stage']),
        'cabinet_present': len(cabinet_present(cabinet)),
        'orders': [{'order_id': row.get('order_id'), 'state': row.get('state'),
                    'observed': row.get('observed')} for row in orders],
        'run_files': ({name: os.path.exists(os.path.join(run_dir, name))
                       for name in ('events.jsonl', 'order_status.jsonl', 'cabinet.jsonl',
                                    'orders.jsonl', 'meta.json')} if run_dir else None),
    }


def verdicts(counted, criteria):
    """기준 파일과 대조한다. 기준에 없는 항목은 판정하지 않고 "기준 없음" 으로 남긴다.

    `event_order` 가 비어 있지 않으면 그 자체가 판정이다. 어긋나면 미달이다(출력만 하고
    넘어가지 않는다).
    """
    gates = criteria.get('gates', {})
    new_warn = [row for row in counted['warn_merged'] if not row['known']]
    values = {
        'laps': len(closed_trips(counted['trips'])),
        'open_trips': len(open_trips(counted['trips'])),
        'errors': len(counted['errors']),
        'tracebacks': len(counted['tracebacks']),
        'drops': len(counted['drops']),
        'http_rejects': len(counted['http_rejects']),
        'new_warn_kinds': len(new_warn),
        'refill_failed': counted['refills']['failed'],
        'cabinet_present': counted['cabinet_present'],
    }
    out = []
    for name, value in sorted(values.items()):
        gate = gates.get(name)
        if gate is None:
            out.append({'name': name, 'value': value, 'gate': None, 'ok': None})
            continue
        ok = value >= gate['min'] if 'min' in gate else True
        if 'max' in gate:
            ok = ok and value <= gate['max']
        out.append({'name': name, 'value': value, 'gate': gate, 'ok': ok})
    if criteria.get('event_order'):
        mismatch = counted['event_order']
        out.append({'name': 'event_order', 'value': 0 if mismatch is None else 1,
                    'gate': {'max': 0}, 'ok': mismatch is None})
    return out, new_warn


def render(counted, judged, new_warn):
    """사람이 읽는 표. 각 수치 옆에 근거 원문 한 줄을 붙인다."""
    lines = [f"회차 {counted['stamp']}  run {counted['run_dir'] or '(없음)'}", '']
    lines.append('판정 (기준 파일과 대조)')
    for row in judged:
        mark = '기준 없음' if row['ok'] is None else ('통과' if row['ok'] else '**미달**')
        lines.append(f"  {row['name']:<16} {row['value']:>6}   {mark}   기준 {row['gate'] or '-'}")
    lines.append('')
    got = counted['reached']
    lines.append(f"도달 **{got['stage']}** (계약 차례 {got['matched_events']}/{len(LAP_ORDER)} 이벤트)")
    if got['expected_next']:
        lines.append(f"  다음에 와야 할 것: {got['expected_next']}"
                     + (f"  실제로 온 것: {got['seen_after']}" if got['seen_after'] else '  (그 뒤 이벤트 없음)'))
    else:
        lines.append('  한 바퀴의 이벤트 차례를 끝까지 봤다')
    lines.append('')
    n_closed, n_open = len(closed_trips(counted['trips'])), len(open_trips(counted['trips']))
    lines.append(f'트립 (REQUEST_ACCEPTED -> DOCKED, sim s)  완료 {n_closed}  미완료 {n_open}')
    for trip in counted['trips'] or []:
        lines.append(f"  {trip['request_id'] or '(없음)':<12} {trip['order_id'] or '':<10} "
                     f"{trip['seconds'] if trip['seconds'] is not None else '끝나지 않음'}")
    if counted['event_order']:
        lines.append(f"  이벤트 차례가 기준과 다르다: {counted['event_order']}")
    lines.append('')
    refill = counted['refills']
    window = counted['sim_window']
    scope = f"run 구간 sim {window[0]:.1f}-{window[1]:.1f} s" if window else '세션 전체(run 을 안 줬다)'
    lines.append(f"보충  released {refill['released']}({scope})  run 안 REFILL_DONE {refill['done_in_run']}")
    lines.append(f"      팔 로그 ok {refill['ok']} 실패 {refill['failed']} — **세션 전체다**(팔 줄의 시각은 wall 이라 "
                 'run 으로 자르지 못한다)')
    for row in refill['failed_evidence']:
        lines.append(f"    근거 {row['line_no']}: {row['text']}")
    lines.append(f"낙하  {len(counted['drops'])} 건 (released~respawn 구간마다 1 건, {scope})")
    for span in counted['drops']:
        lines.append(f"    {span['cell']} released {span['released']['line_no']}행 "
                     f"-> touch {span['hits'][0]['line_no']}행")
        lines.append(f"    근거 {span['hits'][0]['text']}")
    lines.append('')
    lines.append(f"거부(4xx·5xx) {len(counted['http_rejects'])}  "
                 f"[ERROR] {len(counted['errors'])}  Traceback {len(counted['tracebacks'])}")
    for row in (counted['errors'] + counted['http_rejects'])[:5]:
        lines.append(f"    근거 {row.get('role', 'web')} {row['line_no']}행: {row['text']}")
    lines.append('')
    lines.append(f"새 종류 WARN {len(new_warn)} (기준 목록에 없는 것. 같은 줄이 두 로그에 있어도 한 번만 센다)")
    for row in new_warn[:10]:
        lines.append(f"    x{row['count']} [{'·'.join(row['roles'])}] {row['evidence']['text']}")
    lines.append('')
    stop = counted['stop']
    if stop:
        lines.append(f"종료 reason={stop.get('reason')} rtf={stop.get('rtf')} "
                     f"contact_watch={stop.get('contact_watch')} ur5={stop.get('ur5')}")
        lines.append(f"    근거 {stop['evidence']['line_no']}행: {stop['evidence']['text']}")
    else:
        lines.append('종료 stop reason= 줄이 없다(회차가 안 끝났거나 로그가 잘렸다)')
    if counted['run_files'] is None:
        lines.append('run 파일 해당 없음(--run 을 주지 않았다)')
    else:
        missing = [name for name, ok in counted['run_files'].items() if not ok]
        note = f' — 없는 것 {missing}' if missing else ' (빈 파일도 있음으로 센다)'
        lines.append(f"run 파일 {5 - len(missing)}/5{note}")
    lines.append(f"보관함 관측 present=true {counted['cabinet_present']} 건")
    return '\n'.join(lines)


def load_criteria(path):
    """JSON 이나 YAML. YAML 은 PyYAML 이 있을 때만 읽는다."""
    if not path:
        return {}
    with open(path, encoding='utf-8') as handle:
        text = handle.read()
    if path.endswith('.json'):
        return json.loads(text)
    try:
        import yaml
    except ImportError as error:                                        # pragma: no cover
        raise SystemExit(f'YAML 기준 파일을 읽으려면 PyYAML 이 필요하다: {error}') from error
    return yaml.safe_load(text) or {}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--logs', required=True, help='P3_LOG_DIR')
    parser.add_argument('--stamp', required=True, help='기동 시각(로그 파일 이름 앞부분)')
    parser.add_argument('--run', default='', help='run 디렉토리')
    parser.add_argument('--criteria', default='', help='판정선 파일(YAML 또는 JSON)')
    parser.add_argument('--json', default='', help='센 것을 JSON 으로 저장할 경로')
    args = parser.parse_args(argv)

    criteria = load_criteria(args.criteria)
    counted = collect(args.logs, args.stamp, args.run, criteria)
    judged, new_warn = verdicts(counted, criteria)
    print(render(counted, judged, new_warn))
    if args.json:
        with open(args.json, 'w', encoding='utf-8') as handle:
            json.dump({'counted': counted, 'verdicts': judged}, handle,
                      ensure_ascii=False, indent=2, sort_keys=True)
    # 미달이 하나라도 있으면 1. 기준이 없는 항목은 판정하지 않으므로 0 이다.
    return 1 if any(row['ok'] is False for row in judged) else 0


if __name__ == '__main__':
    raise SystemExit(main())
