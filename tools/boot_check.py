#!/usr/bin/env python3
"""기동 직후 자동 점검: 주문을 넣기 전에 화면·시계·녹화가 제대로인지 본다. 하나라도 걸리면 0 이 아닌 값으로 끝난다.

마클1 제안, 작전 카드(9/24). 회차가 끝난 뒤에야 "녹화가 0 B", "콘솔이 잠겨 검은 화면", "창이 겹침"을
알게 된 일이 여러 번 있었다(실습40 8·9회차, 5a10c79 master02). 주문을 넣기 **전에** 멈추게 한다.

    source /opt/ros/jazzy/setup.bash && export ROS_DOMAIN_ID=<도메인>
    python3 tools/boot_check.py --stage-log <stage 로그> --record <녹화 파일> [--skip window]

점검 아홉(순서대로, 하나가 걸려도 나머지는 본다):

- tree     `--tree-sha <40자>` 를 주면 지금 도는 트리가 그 SHA 인가. (a) `git rev-parse HEAD` 일치 (b) `git status
           --porcelain` 이 빔(.gitignore 경로는 git 이 뺀다) (c) 이 boot_check 와 실행 중인 `hospital_orders.py`·
           `demo_v2.sh` 가 그 트리 안의 추적 파일(떼어 온 사본이 아님) (d) `--need <경로>`·`--need profile:<이름>` 이
           있음. 한 줄 `[boot_check] tree=<12자> clean=<y/n> tools=<in-tree/copy> need=<ok/missing:…>` 를 찍는다.
           `--skip tree` 는 받지 않는다. `--tree-sha` 가 없으면 적기만 한다. 재범 질책(9/24, 마스터 운영): 회차가
           말한 SHA 와 실제 트리·도구가 달랐다.

- disk     녹화 파일이 있는 곳(없으면 홈)의 여유가 `--min-disk-gb`(20) 이상인가. 90 분 녹화가 중간에 끊기지 않게.

- stale    지난 회차가 남긴 것이 없는가. 관제 웹 창이 둘 이상, 화면 녹화기(gst-launch·ffmpeg)가 `--max-recorders`(1)
           보다 많음(지금 회차의 것 하나만 허용), 역할이 끝나 셸만 남은 `demo_v2` tmux 세션(`p3v2-*`), 1 분 load 가
           `--load-baseline`(또는 `P3_LOAD_BASELINE`) 의 2 배 초과면 걸리고 목록을 찍는다. 죽이지는 않는다.
           master02 9/24: 관제 창 60개와 15시간 된 녹화기가 남아 load 19.7 이었다(master01 2.3).

- window   `tools/demo_window_layout.py --check-only` 가 0 인가(Isaac 왼쪽 반·웹 오른쪽 반).
           `--window-wait-s`(20) 동안 다시 본다.
- lock     화면이 잠겨 있지 않은가. `loginctl` 의 LockedHint(seat0 세션, 없으면 `XDG_SESSION_ID`), 그다음 GNOME
           ScreenSaver GetActive.
           둘 다 못 읽으면 **걸린 것으로 친다**(잠금을 못 본 채 녹화를 시작하지 않는다). `--lock-unknown-ok` 로 푼다.
- viewport stage 로그에 `viewport camera resolution=(W, H)` 가 있고 W·H 가 0 보다 큰가.
- clock    `--clock-wait-s` 사이에 sim 시각이 흐르고, 발행자가 둘 이상이 아닌가(2 s 간격 세 번 중 최대).
           discovery 가 덜 돼 발행자가 0 으로 읽혀도 시각이 흐르면 통과다.
- costmap  `--costmap-topic`(예: `/amr_1/global_costmap/costmap`)의 전역 코스트맵이 실제 지도를 받았는가
           — width×resolution·height×resolution 이 `--costmap-min-m`(기본 10 m) 이상인가(Nav2 기본 빈
           격자는 100×100, 0.05 m/px = 5×5 m 라 이 값으로 확실히 가린다). `--costmap-wait-s`(30) 동안
           `--costmap-retry-s`(2)마다 다시 본다. `--nav-log` 를 주면 그 로그에 지도를 못 받은 흔적 문구가
           있는지도 본다(보조 판정). **`--costmap-topic` 이 없으면(기본값) 이 점검은 항상 통과한다** —
           v1.0 후보라 지금 도는 캠페인에는 안 넣는다(시뮬통합 9/27 카드, 회차133 #240 5848721883·
           5853335533: 지도를 못 받아 로봇이 범위 밖이 되고 Nav2 목표가 전부 ABORTED 됐다).
- record   녹화 파일이 있고, `--record-wait-s` 사이에 크기가 늘었는가.

끝나는 값: 0 다 통과, 5 하나라도 걸림, 2 인자 잘못. 걸리면 마지막 줄이 `[boot_check] FAIL <점검> — 회차 중단` 이고
(stderr 에도 낸다), 결과 한 줄을 `--summary`(기본: stage 로그 옆 SUMMARY.txt)에 덧붙인다.
설치는 하지 않는다(표준 라이브러리, ros2·loginctl·gdbus 는 있으면 쓴다).
"""

import argparse
import contextlib
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

TAG = '[boot_check]'
CHECKS = ('tree', 'stale', 'disk', 'window', 'lock', 'viewport', 'clock', 'costmap', 'record')
#: 지도를 못 받은 흔적(시뮬통합 9/27, 회차133). 하나라도 --nav-log 안에 있으면 costmap 판정을 보조한다.
COSTMAP_FAIL_PHRASES = ("Can't update static costmap layer, no map received",
                        "Robot is out of bounds of the costmap")
SKIPPABLE = tuple(c for c in CHECKS if c != 'tree')   # tree 는 건너뛸 수 없다(작전 9/24)
REPO_ROOT = Path(__file__).resolve().parents[1]
WINDOW_TOOL = Path(__file__).resolve().with_name('demo_window_layout.py')
WINDOW_RETRY_S = 3.0
VIEWPORT_RE = re.compile(r'viewport camera resolution=\((\d+),\s*(\d+)\)')


def run(cmd, timeout):
    """(돌았나, 끝난 값, stdout+stderr). 명령이 없거나 시한이면 (False, None, 이유)."""
    try:
        done = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        return False, None, f'{cmd[0]} 없음'
    except subprocess.TimeoutExpired:
        return False, None, f'{cmd[0]} {timeout} s 시한'
    return True, done.returncode, (done.stdout or '') + (done.stderr or '')


def parse_locked_hint(text):
    """`loginctl show-session … -p LockedHint` 출력 → True/False/None(모름)."""
    match = re.search(r'LockedHint=(yes|no)', text or '')
    return None if match is None else match.group(1) == 'yes'


def parse_screensaver(text):
    """`gdbus call … GetActive` 출력 `(true,)`/`(false,)` → True/False/None."""
    match = re.search(r'\((true|false),?\)', text or '')
    return None if match is None else match.group(1) == 'true'


def parse_seat_session(text, uid):
    """`loginctl list-sessions` 표 → 이 사용자의 seat0 세션 번호, 없으면 None.

    tmux·ssh 셸에는 `XDG_SESSION_ID` 가 없다(이 PC 9/24 관측). 화면 잠금은 seat0(그래픽) 세션의 것이다."""
    for line in (text or '').splitlines():
        parts = line.split()
        if len(parts) >= 4 and parts[1] == str(uid) and parts[3] == 'seat0':
            return parts[0]
    return None


def parse_viewport(text):
    """stage 로그 → 마지막 `viewport camera resolution=(W, H)` 의 (W, H), 없으면 None."""
    found = VIEWPORT_RE.findall(text or '')
    return None if not found else (int(found[-1][0]), int(found[-1][1]))


def parse_publisher_count(text):
    """`ros2 topic info /clock` → 발행자 수. 토픽이 없으면 0, 못 읽으면 None."""
    match = re.search(r'Publisher count:\s*(\d+)', text or '')
    if match:
        return int(match.group(1))
    if not text or 'Unknown topic' in text:
        return 0
    return None


def parse_clock_csv(text):
    """`ros2 topic echo /clock --once --csv --field clock` 의 `sec,nanosec` → 초(float), 못 읽으면 None."""
    match = re.search(r'^(\d+),(\d+)', (text or '').strip())
    return None if match is None else int(match.group(1)) + int(match.group(2)) * 1e-9


def check_window(args):
    """창 배치. up 직후에는 브라우저 창이 아직 없을 수 있어(마클1 9/24 회차33)
    `--window-wait-s` 동안 3 s 마다 다시 본다."""
    if not WINDOW_TOOL.is_file():
        return False, (f'{WINDOW_TOOL.name} 가 {WINDOW_TOOL.parent} 에 없다 — '
                       'boot_check.py 만 떼어 쓰지 말고 tools/ 째 쓴다')
    deadline = time.monotonic() + args.window_wait_s
    tries = 0
    while True:
        tries += 1
        cmd = [sys.executable, str(WINDOW_TOOL), '--check-only']
        cmd += ['--isaac', args.isaac] if args.isaac else []
        cmd += ['--web', args.web] if args.web else []
        ok, code, out = run(cmd, timeout=30)
        tail = (out.strip().splitlines() or ['-'])[-1]
        if ok and code == 0:
            return True, f'demo_window_layout --check-only 끝난 값 0(시도 {tries}): {tail}'
        if time.monotonic() >= deadline:
            detail = out if not ok else f'demo_window_layout --check-only 끝난 값 {code}: {tail}'
            return False, (f'{detail}(시도 {tries}, {args.window_wait_s:g} s) — 창을 옮기려면 '
                           'python3 tools/demo_window_layout.py 를 한 번 돌리고 다시 본다')
        time.sleep(WINDOW_RETRY_S)


def locked_state():
    """(True/False/None, 어디서 읽었나)."""
    # 화면 잠금은 seat0(그래픽) 세션의 것이다. 셸의 `XDG_SESSION_ID` 는 pts 세션일 수 있어(마클1 9/24 master01:
    # 셸이 세션 11, 화면은 세션 2) seat0 세션을 먼저 찾고, 없을 때만 셸의 세션을 본다.
    ok, code, out = run(['loginctl', 'list-sessions', '--no-legend'], timeout=10)
    session = parse_seat_session(out, os.getuid()) if ok and code == 0 else None
    session = session or os.environ.get('XDG_SESSION_ID')
    if session:
        ok, code, out = run(['loginctl', 'show-session', session, '-p', 'LockedHint'], timeout=10)
        if ok and code == 0:
            state = parse_locked_hint(out)
            if state is not None:
                return state, f'loginctl session {session}'
    ok, code, out = run(['gdbus', 'call', '--session', '--dest', 'org.gnome.ScreenSaver', '--object-path',
                         '/org/gnome/ScreenSaver', '--method', 'org.gnome.ScreenSaver.GetActive'], timeout=10)
    if ok and code == 0:
        state = parse_screensaver(out)
        if state is not None:
            return state, 'gnome ScreenSaver'
    return None, 'loginctl·gdbus 둘 다 못 읽음'


def check_lock(args):
    state, source = locked_state()
    if state is None:
        return bool(args.lock_unknown_ok), f'잠금 모름({source})' + (' — --lock-unknown-ok 로 통과' if
                                                                 args.lock_unknown_ok else '')
    return not state, f'{"잠김" if state else "안 잠김"}({source})'


def check_viewport(args):
    if not args.stage_log:
        return False, '--stage-log 가 없다'
    path = Path(args.stage_log).expanduser()
    try:
        text = path.read_text(encoding='utf-8', errors='replace')
    except OSError as error:
        return False, f'{path} 를 못 읽음: {error}'
    size = parse_viewport(text)
    if size is None:
        return False, f'{path} 에 `viewport camera resolution=` 줄이 없다(아직 ready 전이거나 뷰포트가 없다)'
    return size[0] > 0 and size[1] > 0, f'viewport {size[0]}x{size[1]}'


def clock_now():
    ok, code, out = run(['ros2', 'topic', 'echo', '/clock', '--once', '--no-daemon', '--csv', '--field', 'clock'],
                        timeout=10)
    return parse_clock_csv(out) if ok and code == 0 else None


def clock_publishers(tries=3, gap_s=2.0):
    """`/clock` 발행자 수를 `tries` 번 읽어 가장 큰 값. discovery 가 덜 되면 0 이 먼저 나온다
    (마클1 9/24 회차33: 같은 환경에서 세 번이 0·1·1). 하나도 못 읽으면 (None, 이유)."""
    counts, reason = [], ''
    for index in range(tries):
        ok, code, out = run(['ros2', 'topic', 'info', '/clock', '--no-daemon'], timeout=20)
        if ok:
            count = parse_publisher_count(out)
            if count is not None:
                counts.append(count)
        else:
            reason = out
        if index + 1 < tries:
            time.sleep(gap_s)
    return (max(counts) if counts else None), (counts or reason)


def check_clock(args):
    """발행자가 둘 이상이면 걸린다(다른 Isaac 이 같은 도메인에 있다). 하나이거나, discovery 가 덜 돼 0·못 읽음이어도
    sim 시각이 흐르면 통과다(작전 9/24: 오탐이 회차를 세웠다)."""
    count, seen = clock_publishers()
    first = clock_now()
    time.sleep(args.clock_wait_s)
    second = clock_now()
    moving = first is not None and second is not None and second > first
    shown = f'발행자 {count if count is not None else "?"}(읽은 값 {seen}), sim {first} → {second}'
    if count is not None and count > 1:
        return False, shown + ' — /clock 발행자가 둘 이상이다'
    if not moving:
        return False, shown + ' — 흐르지 않는다'
    return True, shown + ('' if count == 1 else ' — 발행자는 못 셌지만 시각이 흐른다')


def check_record(args):
    if not args.record:
        return False, '--record 가 없다(녹화 없이 도는 회차면 --skip record)'
    path = Path(args.record).expanduser()
    try:
        first = path.stat().st_size
    except OSError as error:
        return False, f'{path} 없음: {error}'
    time.sleep(args.record_wait_s)
    second = path.stat().st_size
    hint = '' if second > first else (' — 멈춘 화면이면 녹화기가 버퍼를 안 비웠을 수 있다. '
                                      'ffmpeg 는 -flush_packets 1 을 준다(256 KiB 단위로 쓴다, 마클1 9/24)')
    return second > first, f'{path.name} {first} → {second} B({args.record_wait_s:g} s){hint}'


def parse_costmap_info(text):
    """`ros2 topic echo --once --field info <전역 코스트맵 토픽>` 출력(MapMetaData YAML)에서
    width·height·resolution. 셋 다 있어야 값을 낸다(없으면 None) — origin 은 판정에 안 쓴다."""
    width = re.search(r'^width:\s*(\d+)', text or '', re.M)
    height = re.search(r'^height:\s*(\d+)', text or '', re.M)
    resolution = re.search(r'^resolution:\s*([\d.eE+-]+)', text or '', re.M)
    if not (width and height and resolution):
        return None
    return {'width': int(width.group(1)), 'height': int(height.group(1)),
           'resolution': float(resolution.group(1))}


def costmap_size_ok(info, min_m):
    return info is not None and info['width'] * info['resolution'] >= min_m \
        and info['height'] * info['resolution'] >= min_m


def check_costmap(args):
    """--costmap-topic 이 없으면(기본값) 늘 통과한다 — v1.0 후보라 지금 도는 캠페인에는 안 넣는다(위 문서)."""
    if not args.costmap_topic:
        return True, '꺼짐(--costmap-topic 없음)'
    deadline = time.monotonic() + args.costmap_wait_s
    tries, info = 0, None
    while True:
        tries += 1
        ok, code, out = run(['ros2', 'topic', 'echo', '--once', '--field', 'info', args.costmap_topic,
                             '--no-daemon'], timeout=10)
        info = parse_costmap_info(out) if ok and code == 0 else None
        if costmap_size_ok(info, args.costmap_min_m) or time.monotonic() >= deadline:
            break
        time.sleep(args.costmap_retry_s)
    shown = (f'{info["width"]}x{info["height"]} @ {info["resolution"]:.4f} m/px = '
            f'{info["width"] * info["resolution"]:.1f}x{info["height"] * info["resolution"]:.1f} m'
            if info else f'{args.costmap_topic} 을 못 읽음')
    got = costmap_size_ok(info, args.costmap_min_m)
    detail = f'{shown}(시도 {tries}, {args.costmap_wait_s:g} s)'
    if not got:
        return False, f'{detail} — 지도를 못 받았다(기본 격자로 남음)'
    if args.nav_log:
        try:
            text = Path(args.nav_log).expanduser().read_text(encoding='utf-8', errors='replace')
        except OSError:
            text = ''
        bad = [phrase for phrase in COSTMAP_FAIL_PHRASES if phrase in text]
        if bad:
            return False, f'{detail} — nav.log 에 지도를 못 받은 흔적이 있다: {bad}'
    return True, detail


def parse_window_list(text, pattern):
    """`demo_window_layout.py --list` 줄 중 pattern(대소문자 무시)에 맞는 줄."""
    rx = re.compile(pattern, re.IGNORECASE)
    return [line.strip() for line in (text or '').splitlines() if line.startswith('0x') and rx.search(line)]


RECORDER_NAMES = {'ffmpeg', 'gst-launch-1.0'}
RECORDER_SOURCE = re.compile(r'ximagesrc|x11grab')


def parse_processes(text):
    """`ps -eo pid=,ppid=,etimes=,comm=,args=` → [(pid, ppid, 경과 s, 실행 파일 이름, 명령)]."""
    rows = []
    for line in (text or '').splitlines():
        parts = line.split(None, 4)
        if len(parts) >= 4 and all(p.isdigit() for p in parts[:3]):
            rows.append((int(parts[0]), int(parts[1]), int(parts[2]), parts[3], parts[4] if len(parts) > 4 else ''))
    return rows


def recorders_of(rows):
    """화면 녹화기 [(pid, 경과 s, 명령 앞 80자)]. 실행 파일이 ffmpeg·gst-launch-1.0 인 것만 센다.

    마클1 9/24 회차50: 명령줄만 보면 녹화기를 감싼 `bash -c ffmpeg …`, sys.csv 의 `pgrep -fc x11grab` 자신,
    demo_v2 캡처(`num-buffers=1` 한 장짜리)까지 세어 자기 회차를 잔류로 걸었다."""
    return [(pid, etime, args[:80]) for pid, _ppid, etime, name, args in rows
            if name in RECORDER_NAMES and RECORDER_SOURCE.search(args) and 'num-buffers=1' not in args]


def idle_sessions(panes_text, rows, prefix):
    """`tmux list-panes -a -F '#{session_name} #{pane_pid}'` → 자식 프로세스가 하나도 없는 prefix 세션.

    demo_v2 는 역할을 `bash -c 'trap …; 명령'` 으로 띄워 pane 의 현재 명령이 늘 bash 다(마클1 회차50). 그래서
    명령 이름이 아니라 pane 셸에 자식이 남아 있는지로 본다 — 역할이 끝난 pane 만 자식이 없다."""
    parents = {ppid for _pid, ppid, _etime, _name, _args in rows}
    idle = set()
    for line in (panes_text or '').splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[0].startswith(prefix) and parts[1].isdigit() and int(parts[1]) not in parents:
            idle.add(parts[0])
    return sorted(idle)


def check_stale(args):
    problems, notes = [], []
    web = args.web or r'navigator|p3 관제'
    if WINDOW_TOOL.is_file():
        ok, code, out = run([sys.executable, str(WINDOW_TOOL), '--list'], timeout=30)
        if ok and code == 0:
            windows = parse_window_list(out, web)
            notes.append(f'관제 창 {len(windows)}')
            if len(windows) > 1:
                problems.append(f'관제 창 {len(windows)}개(1 이어야 한다): ' + ' | '.join(windows[:5]) +
                                (' …' if len(windows) > 5 else ''))
        else:
            notes.append('창 목록 못 읽음')
    ok, code, out = run(['ps', '-eo', 'pid=,ppid=,etimes=,comm=,args='], timeout=10)
    rows = parse_processes(out) if ok and code == 0 else None
    if rows is not None:
        recorders = recorders_of(rows)
        notes.append(f'녹화기 {len(recorders)}')
        if len(recorders) > args.max_recorders:
            problems.append(f'녹화기 {len(recorders)}개(최대 {args.max_recorders}): ' +
                            ' | '.join(f'pid {pid} {etime // 60}분 {cmd}' for pid, etime, cmd in recorders))
        ok, code, out = run(['tmux', 'list-panes', '-a', '-F', '#{session_name} #{pane_pid}'], timeout=10)
        if ok and code == 0:
            idle = idle_sessions(out, rows, args.tmux_prefix)
            if idle:
                problems.append(f'역할이 끝나 셸만 남은 tmux 세션 {idle}')
    load = read_load()
    if load is not None:
        notes.append(f'load {load:.2f}')
        baseline = args.load_baseline
        if baseline is None:
            notes.append('load 기준선 없음(--load-baseline 또는 P3_LOAD_BASELINE)')
        elif load > 2.0 * baseline:
            problems.append(f'load {load:.2f} > 기준선 {baseline:g} 의 2 배 — 다른 프로세스가 CPU 를 쓰고 있다')
    if problems:
        return False, '; '.join(problems) + ' — 정리한 뒤 다시 띄운다(boot_check 는 죽이지 않는다)'
    return True, ', '.join(notes)


def read_load(path='/proc/loadavg'):
    """1 분 load average. 못 읽으면 None."""
    try:
        return float(Path(path).read_text(encoding='ascii').split()[0])
    except (OSError, ValueError, IndexError):
        return None


def check_disk(args):
    base = Path(args.record).expanduser().parent if args.record else Path.home()
    base = base if base.exists() else Path.home()
    free = shutil.disk_usage(base).free / 1e9
    return free >= args.min_disk_gb, f'{base} 여유 {free:.1f} GB(최소 {args.min_disk_gb:g})'


def _git(root, *args):
    ok, code, out = run(['git', '-C', str(root), *args], timeout=20)
    return (out if ok and code == 0 else None), (code if ok else out)


def _tracked(root, path):
    try:
        rel = Path(path).resolve().relative_to(Path(root).resolve())
    except ValueError:
        return False
    out, _ = _git(root, 'ls-files', '--error-unmatch', str(rel))
    return out is not None


def running_tool_paths(rows, names=('hospital_orders.py', 'demo_v2.sh')):
    """실행 중인 도구의 스크립트 경로. 상대 경로는 그 프로세스의 cwd 기준으로 푼다."""
    found = []
    for pid, _ppid, _etime, _name, args in rows:
        for word in args.split():
            if Path(word).name in names:
                path = Path(word)
                if not path.is_absolute():
                    with contextlib.suppress(OSError):
                        path = Path(os.readlink(f'/proc/{pid}/cwd')) / path
                found.append(path)
    return found


def profile_names(root):
    """tools/hospital_orders.py 의 PROFILES 튜플. 못 읽으면 빈 튜플."""
    try:
        text = (Path(root) / 'tools' / 'hospital_orders.py').read_text(encoding='utf-8')
    except OSError:
        return ()
    match = re.search(r'^PROFILES\s*=\s*\(([^)]*)\)', text, re.MULTILINE)
    if not match:
        return ()
    return tuple(a or b for a, b in re.findall(r'"([^"]+)"|\'([^\']+)\'', match.group(1)))


def check_tree(args):
    root = Path(args.tree_root)
    head, _ = _git(root, 'rev-parse', 'HEAD')
    head = (head or '').strip()
    status, _ = _git(root, 'status', '--porcelain')
    clean = status is not None and not status.strip()
    ok, code, out = run(['ps', '-eo', 'pid=,ppid=,etimes=,comm=,args='], timeout=10)
    rows = parse_processes(out) if ok and code == 0 else []
    copies = [str(p) for p in [Path(args.self_path), *running_tool_paths(rows)] if not _tracked(root, p)]
    missing = []
    for need in args.need:
        if need.startswith('profile:'):
            if need.split(':', 1)[1] not in profile_names(root):
                missing.append(need)
        elif not ((root / need).exists() if not Path(need).is_absolute() else Path(need).exists()):
            missing.append(need)
    line = (f'{TAG} tree={head[:12] or "?"} clean={"y" if clean else "n"} '
            f'tools={"copy" if copies else "in-tree"} need={"missing:" + ",".join(missing) if missing else "ok"}')
    print(line, flush=True)
    if not args.tree_sha:
        return True, 'tree 게이트 꺼짐(--tree-sha 없음) — 적기만 한다'
    problems = []
    if head != args.tree_sha:
        problems.append(f'HEAD {head or "?"} ≠ --tree-sha {args.tree_sha}')
    if not clean:
        dirty = (status or '').strip().splitlines()
        problems.append(f'트리가 깨끗하지 않다({len(dirty)}줄): ' + ' | '.join(dirty[:5]))
    if copies:
        problems.append('트리 밖이거나 추적 안 된 도구: ' + ', '.join(copies))
    if missing:
        problems.append('카드가 요구한 것이 없다: ' + ', '.join(missing))
    if problems:
        return False, '; '.join(problems)
    return True, f'{root} = {head[:12]}, 깨끗함, 도구 트리 안, need ok'


RUNNERS = {'tree': check_tree, 'stale': check_stale, 'disk': check_disk, 'window': check_window, 'lock': check_lock,
           'viewport': check_viewport, 'clock': check_clock, 'costmap': check_costmap, 'record': check_record}


def _env_float(name):
    try:
        return float(os.environ[name])
    except (KeyError, ValueError):
        return None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--stage-log', help='stage 로그(viewport 줄을 찾는다)')
    parser.add_argument('--record', help='녹화 파일(크기가 느는지 본다)')
    parser.add_argument('--skip', action='append', default=[], choices=SKIPPABLE,
                        help='건너뛸 점검(여러 번 줄 수 있다). tree 는 건너뛸 수 없다')
    parser.add_argument('--tree-sha', help='카드가 말한 트리 SHA 40자. 주면 tree 게이트가 켜진다')
    parser.add_argument('--need', action='append', default=[],
                        help='카드가 요구하는 파일(트리 기준 경로) 또는 profile:<hospital_orders 프로필>')
    parser.add_argument('--tree-root', default=str(REPO_ROOT), help=argparse.SUPPRESS)
    parser.add_argument('--self-path', default=str(Path(__file__).resolve()), help=argparse.SUPPRESS)
    parser.add_argument('--clock-wait-s', type=float, default=2.0)
    parser.add_argument('--costmap-topic', help='전역 코스트맵 토픽(예: /amr_1/global_costmap/costmap). '
                                                '없으면(기본) costmap 점검은 항상 통과한다(v1.0 후보)')
    parser.add_argument('--costmap-min-m', type=float, default=10.0,
                        help='width·height 가 이 m 이상이어야 지도를 받은 것으로 본다(Nav2 기본 격자는 5x5 m)')
    parser.add_argument('--costmap-wait-s', type=float, default=30.0,
                        help='costmap 이 자리에 올 때까지 기다리는 최대 s')
    parser.add_argument('--costmap-retry-s', type=float, default=2.0, help='costmap 을 다시 보는 간격 s')
    parser.add_argument('--nav-log', help='nav 로그(costmap 의 보조 판정 — 지도를 못 받은 흔적 문구를 본다)')
    parser.add_argument('--isaac', help='창 점검에 넘길 Isaac 창 식(기본은 demo_window_layout 의 것)')
    parser.add_argument('--web', help='창 점검에 넘길 웹 창 식(기본은 demo_window_layout 의 것)')
    parser.add_argument('--window-wait-s', type=float, default=20.0, help='창이 자리에 올 때까지 기다리는 최대 s')
    # x264 mp4 는 화면이 거의 멈춰 있으면 5 s 동안 크기가 그대로였다(마클1 9/24, 524336 B). 그래서 15 s 다.
    parser.add_argument('--record-wait-s', type=float, default=15.0)
    parser.add_argument('--max-recorders', type=int, default=1, help='허용하는 화면 녹화기 수(stale 점검)')
    parser.add_argument('--load-baseline', type=float, default=_env_float('P3_LOAD_BASELINE'),
                        help='이 장비의 깨끗한 회차 load(1 분). 그 2 배를 넘으면 stale 이 걸린다. '
                             '없으면 load 는 적기만 한다')
    parser.add_argument('--min-disk-gb', type=float, default=20.0, help='녹화할 곳의 최소 여유(disk 점검)')
    parser.add_argument('--tmux-prefix', default='p3v2-', help='demo_v2 tmux 세션 접두(stale 점검)')
    parser.add_argument('--lock-unknown-ok', action='store_true', help='잠금 상태를 못 읽어도 통과로 친다')
    parser.add_argument('--summary', help='결과 한 줄을 덧붙일 파일(기본: --stage-log 옆 SUMMARY.txt, 없으면 안 쓴다)')
    args = parser.parse_args(argv)
    if args.tree_sha and not re.fullmatch(r'[0-9a-f]{40}', args.tree_sha):
        parser.error('--tree-sha 는 40자 소문자 16진수다')
    failed = []
    for name in CHECKS:
        if name in args.skip:
            print(f'{TAG} {name} SKIP')
            continue
        try:
            passed, detail = RUNNERS[name](args)
        except Exception as error:  # 점검 하나가 터져도 나머지는 본다
            passed, detail = False, f'{type(error).__name__}: {error}'
        print(f'{TAG} {name} {"PASS" if passed else "FAIL"} {detail}', flush=True)
        if not passed:
            failed.append(name)
    if failed:
        # 회차27(마클1 9/24): FAIL 줄이 다른 줄에 묻혀 35 분 동안 아무도 몰랐다. 마지막 줄을 눈에 띄게 하고
        # stderr 에도 내고, 회차 폴더의 SUMMARY.txt 에 남긴다.
        final = f'{TAG} FAIL {",".join(failed)} — 회차 중단'
        bar = '#' * 72
        print(f'{bar}\n{final}\n{bar}', flush=True)
        print(final, file=sys.stderr, flush=True)
        write_summary(args, final)
        return 5
    print(f'{TAG} OK')
    write_summary(args, f'{TAG} OK')
    return 0


def summary_path(args):
    """--summary, 없으면 --stage-log 옆 SUMMARY.txt, 둘 다 없으면 None."""
    if args.summary:
        return Path(args.summary).expanduser()
    if args.stage_log:
        return Path(args.stage_log).expanduser().parent / 'SUMMARY.txt'
    return None


def write_summary(args, line):
    """한 줄을 덧붙인다. 못 쓰면 그 사실만 찍는다 — 점검 결과(끝나는 값)는 바꾸지 않는다."""
    path = summary_path(args)
    if path is None:
        return
    try:
        with path.open('a', encoding='utf-8') as handle:
            handle.write(f'{time.strftime("%Y-%m-%dT%H:%M:%S%z")} {line}\n')
    except OSError as error:
        print(f'{TAG} SUMMARY 를 못 씀 {path}: {error}', flush=True)


if __name__ == '__main__':
    sys.exit(main())
