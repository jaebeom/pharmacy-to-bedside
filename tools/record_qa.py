#!/usr/bin/env python3
"""회차가 끝난 뒤 녹화 파일 QA: fps·프레임 수·길이·손상, 그리고 디스크 여유. 기준 미달이면 "녹화 결손".

재범 지시(9/24 14:4x, "녹화가 핵심"). 녹화가 0 B·검은 화면·8 s 만에 닫힘을 회차가 끝난 한참 뒤에 안 일이 있었다
(실습40 8·9회차, 마클2 5a51804 rec.stop). 회차를 내리자마자 한 번 돌려 SUMMARY.txt 에 한 줄 남긴다.

    python3 tools/record_qa.py --record <녹화 파일> --wall-s <녹화한 벽시계 s> [--summary <SUMMARY.txt>]
    python3 tools/record_qa.py --record <녹화 파일> --started <시작 시각> [--ended <닫은 시각>]   # 자정을 넘겨도 맞다

- ffprobe 로 영상 스트림 패킷을 한 번 훑는다(디코드하지 않아 90 분 파일도 빠르다). 프레임 수 = 패킷 수,
  길이 = 마지막 pts − 첫 pts, fps = 프레임 수 ÷ 길이. 컨테이너가 끝을 못 쓴 파일(녹화기가 죽음)도 읽힌다.
- drop = 길이 × 목표 fps − 프레임 수(음수면 0). ffprobe 가 낸 오류 줄 수를 손상(corrupt)으로 센다.
- 기준: fps ≥ `--min-fps`(29), `--wall-s` 를 주면 |길이 − 벽시계| ≤ `--dur-tol`(2 %), 손상 0,
  드롭 ≤ 목표 프레임의 `--max-drop`(2 %), 디스크 여유 ≥ `--min-disk-gb`(20).
- 결과 한 줄 `record_qa: fps=.. frames=.. dur=.. wall=.. drop=.. corrupt=.. disk=.. — OK|녹화 결손(<이유>)` 를
  찍고 `--summary`(기본: 녹화 파일 옆 SUMMARY.txt)에 덧붙인다. 끝나는 값: 0 OK, 5 결손, 2 인자 잘못.
"""

import argparse
from datetime import datetime
import shutil
import subprocess
import sys
import time
from pathlib import Path

TAG = '[record_qa]'
PROBE = ['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'packet=pts_time', '-of', 'csv=p=0']


def probe(path, timeout=600):
    """(pts 목록, 오류 줄 수) 또는 예외 문자열. pts 가 N/A 인 패킷은 세기만 하고 시각에는 안 쓴다."""
    try:
        done = subprocess.run([*PROBE, str(path)], capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        return None, 'ffprobe 없음'
    except subprocess.TimeoutExpired:
        return None, f'ffprobe {timeout} s 시한'
    return parse_packets(done.stdout), len([line for line in done.stderr.splitlines() if line.strip()])


def parse_packets(text):
    """csv 한 줄에 pts_time 하나 → (패킷 수, 첫 pts, 마지막 pts). 시각을 못 읽으면 첫·마지막은 None."""
    count, first, last = 0, None, None
    for line in (text or '').splitlines():
        value = line.strip().rstrip(',')
        if not value:
            continue
        count += 1
        try:
            pts = float(value)
        except ValueError:
            continue
        first = pts if first is None else min(first, pts)
        last = pts if last is None else max(last, pts)
    return count, first, last


def judge(frames, first, last, corrupt, disk_gb, args):
    """(결손 이유 목록, 결과 한 줄의 값들)."""
    duration = (last - first) if first is not None and last is not None else 0.0
    fps = frames / duration if duration > 0 else 0.0
    expected = duration * args.target_fps
    drop = max(0, round(expected - frames))
    reasons = []
    if frames == 0:
        reasons.append('프레임 0')
    if fps < args.min_fps:
        reasons.append(f'fps {fps:.2f} < {args.min_fps:g}')
    if args.wall_s and abs(duration - args.wall_s) > args.dur_tol * args.wall_s:
        reasons.append(f'길이 {duration:.1f} s 가 벽시계 {args.wall_s:g} s 와 {args.dur_tol:.0%} 넘게 다름')
    if corrupt:
        reasons.append(f'손상 {corrupt}줄')
    if expected > 0 and drop > args.max_drop * expected:
        reasons.append(f'드롭 {drop}(목표의 {drop / expected:.1%})')
    if disk_gb is not None and disk_gb < args.min_disk_gb:
        reasons.append(f'디스크 여유 {disk_gb:.1f} GB < {args.min_disk_gb:g}')
    values = (f'fps={fps:.2f} frames={frames} dur={duration:.1f}s wall={args.wall_s or "-"}s drop={drop} '
              f'corrupt={corrupt} disk={"?" if disk_gb is None else f"{disk_gb:.0f}GB"}')
    return reasons, values


def free_gb(path):
    try:
        return shutil.disk_usage(path).free / 1e9
    except OSError:
        return None


def parse_moment(text):
    """시각 → (초, 날짜가 있나).

    epoch 초(`1727190000`), 날짜 포함 ISO(`2026-09-25T00:12:03`), 또는 시계만(`00:12:03`)."""
    text = text.strip()
    try:
        return float(text), True
    except ValueError:
        pass
    try:
        return datetime.fromisoformat(text).timestamp(), True
    except ValueError:
        pass
    parts = text.split(':')
    if len(parts) == 3:
        h, m, sec = (float(v) for v in parts)
        return h * 3600 + m * 60 + sec, False
    raise ValueError(f'시각을 못 읽음: {text!r}(epoch 초, YYYY-MM-DDTHH:MM:SS, HH:MM:SS)')


def wall_between(started, ended):
    """두 시각 사이 벽시계 초. 시계만 준 경우 끝이 시작보다 이르면 자정을 넘긴 것으로 보고 하루를 더한다
    (마클2 9/25 다중 PC 10건: HH:MM:SS 뺄셈이 음수가 되어 멀쩡한 3788 s 녹화를 결손으로 찍었다)."""
    (a, dated_a), (b, dated_b) = parse_moment(started), parse_moment(ended)
    wall = b - a
    if wall < 0 and not (dated_a and dated_b):
        wall += 86400
    return wall


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--record', required=True, help='녹화 파일')
    parser.add_argument('--wall-s', type=float, help='녹화를 켜 둔 벽시계 s(주면 길이를 대조한다)')
    parser.add_argument('--started',
                        help='녹화 시작 시각(epoch 초·날짜 포함 ISO·HH:MM:SS). 주면 --wall-s 를 계산한다')
    parser.add_argument('--ended', help='녹화를 닫은 시각(같은 형식). 없으면 지금')
    parser.add_argument('--target-fps', type=float, default=30.0, help='녹화기에 준 fps(드롭 계산)')
    parser.add_argument('--min-fps', type=float, default=29.0)
    parser.add_argument('--dur-tol', type=float, default=0.02, help='길이 허용 비율(0.02 = ±2 %%)')
    parser.add_argument('--max-drop', type=float, default=0.02, help='드롭 허용 비율(목표 프레임 대비)')
    parser.add_argument('--min-disk-gb', type=float, default=20.0)
    parser.add_argument('--summary', help='결과 한 줄을 덧붙일 파일(기본: 녹화 파일 옆 SUMMARY.txt)')
    args = parser.parse_args(argv)
    if args.started:
        ended = args.ended or datetime.now().isoformat(timespec='seconds')
        try:
            args.wall_s = wall_between(args.started, ended)
        except ValueError as error:
            parser.error(str(error))
    if args.wall_s is not None and args.wall_s <= 0:
        # 음수·0 벽시계는 녹화가 아니라 호출 쪽 시각 계산이 틀린 것이다. 결손으로 찍지 않고 인자 오류로 멈춘다.
        parser.error(f'--wall-s {args.wall_s:g} 은 0 보다 커야 한다. 시각 계산을 확인한다 — '
                     '--started/--ended 를 쓰면 자정을 넘겨도 맞다')
    path = Path(args.record).expanduser()
    disk = free_gb(path.parent if path.parent.exists() else Path.home())
    if not path.is_file():
        line = f'record_qa: 파일 없음 {path} disk={"?" if disk is None else f"{disk:.0f}GB"} — 녹화 결손(파일 없음)'
        return finish(args, path, line, ok=False)
    packets, corrupt = probe(path)
    if packets is None:
        return finish(args, path, f'record_qa: {corrupt} — 녹화 결손(검사 못 함)', ok=False)
    frames, first, last = packets
    reasons, values = judge(frames, first, last, corrupt, disk, args)
    verdict = 'OK' if not reasons else f'녹화 결손({"; ".join(reasons)})'
    return finish(args, path, f'record_qa: {values} — {verdict}', ok=not reasons)


def finish(args, path, line, ok):
    print(f'{TAG} {line}', flush=True)
    if not ok:
        print(f'{TAG} {line}', file=sys.stderr, flush=True)
    summary = Path(args.summary).expanduser() if args.summary else path.parent / 'SUMMARY.txt'
    try:
        with summary.open('a', encoding='utf-8') as handle:
            handle.write(f'{time.strftime("%Y-%m-%dT%H:%M:%S%z")} {line}\n')
    except OSError as error:
        print(f'{TAG} SUMMARY 를 못 씀 {summary}: {error}', flush=True)
    return 0 if ok else 5


if __name__ == '__main__':
    sys.exit(main())
