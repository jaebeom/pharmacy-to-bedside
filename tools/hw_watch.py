#!/usr/bin/env python3
"""하드웨어 감시: GPU·load·잔류 프로세스를 재고 판단까지 해서, 정상이면 조용하고 문제일 때만 한 줄 낸다.

재범 9/27 지시: 마클1·마클2가 매번 nvidia-smi 를 손으로 찍고 "87 도면 괜찮나" 를 사람(에이전트)이 판단하는 게
비효율이다. 이 도구가 그 판단을 한다 — 기준은 오늘까지 확립된 것뿐이다: GPU 열 상한 87 도(두 장비 공통),
스로틀 비트(`clocks_throttle_reasons.active`), load 기준선의 2 배(`tools/boot_check.py` 의 stale 판정과 같은
기준·같은 코드), 그리고 GPU 전력이 최근 중앙값 대비 갑자기 떨어지는 것(9/27 master01 13:00-13:40 15 W 미스터리
같은 사건을 놓치지 않으려는 것 — 경보만 낸다, 원인은 안 밝힌다).

    python3 tools/hw_watch.py --load-baseline 8.4 [--gpu-csv <회차>/gpu.csv] [--interval 5] [--once]

nvidia-smi 쿼리 필드는 기동 때 한 번만 실제로 찔러 보고 정한다(`--query-gpu` 필드 하나가 이 GPU·드라이버에서
안 먹힐 수 있다 — 마클1 9/27: `enforced.power.limit` 자체를 거부, `clocks_throttle_reasons.active` 대신
`clocks_event_reasons.active` 만 받는 드라이버도 있었다). 안 먹히는 필드는 빼고 돈다 — 사람이 매번 알아낼
필요가 없다.

잔류 프로세스 판정은 새로 만들지 않았다. `tools/boot_check.py` 의 `check_stale`(관제 창·녹화기·tmux·load) 를
그대로 부른다 — 기준이 갈리면 안 된다. 이 감시가 자주 도는 대신(`--stale-every`), GPU·load 는 매 간격마다,
잔류 프로세스(ps·tmux·창 목록)는 더 뜸하게 본다(비용이 크다).

**관측만 한다** — 프로세스를 죽이거나 전력·팬 값을 바꾸지 않는다(nvidia-smi 조회·파일 읽기·`ps`·`tmux
list-panes` 뿐이다). 걸리면 시각·항목·값·기준을 담은 한 줄만 낸다(stdout, `--gpu-csv` 는 표본만 남긴다).

기준값은 전부 인자다(작전 9/27 카드) — 코드에 박지 않는다: `--temp-limit`(GPU 열 상한, 기본 87),
`--power-limit-expected`(GPU 전력 상한 기대값, 기본 80 — `--no-power-limit-check` 로 끈다),
`--power-limit-tolerance`, `--load-baseline`(호스트별, `P3_LOAD_BASELINE` 환경변수도 받는다),
`--rtf-min`(`--stage-log` 를 같이 줘야 stop 줄을 읽는다). 전력 상한은 CSV 필드가 없는 드라이버(마클1 9/27
master01: `power.limit`·`enforced.power.limit` 자체를 거부)에서는 기동 때 한 번 `nvidia-smi -q -d POWER`
텍스트를 대신 읽는다(이 하드웨어는 상한이 안 바뀐다고 본다 — 매 표본 다시 찌르지 않는다).

설치는 하지 않는다(표준 라이브러리, nvidia-smi 는 있으면 쓴다). **마스터에서 실제로 켜는 것은 이 카드가
아니다** — 이 파일은 도구고, 반영은 작전이 한 번 더 검증한 뒤 마클1·마클2 에게 직접 지시한다.
"""

import argparse
import csv
import importlib.util
import re
import statistics
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
_SPEC = importlib.util.spec_from_file_location("boot_check", ROOT / "boot_check.py")
boot_check = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(boot_check)

#: 순서대로 쓰려는 필드. `timestamp` 는 항상 살아있다고 본다(뺄 대상이 아니다).
PREFERRED_FIELDS = ["timestamp", "power.draw", "power.limit", "enforced.power.limit", "utilization.gpu",
                    "memory.used", "clocks.sm", "temperature.gpu", "clocks_throttle_reasons.active"]
#: 이 드라이버에서 안 먹히면 이걸로 한 번 더 시도한다(마클1 9/27: clocks_event_reasons 로 받는 드라이버가 있다).
ALIASES = {"clocks_throttle_reasons.active": "clocks_event_reasons.active"}
NUMERIC_FIELDS = {"power.draw", "power.limit", "enforced.power.limit", "utilization.gpu", "memory.used",
                  "clocks.sm", "temperature.gpu"}
NOT_ACTIVE = ("0x0000000000000000", "0x0", "n/a", "not active")
POWER_LIMIT_TEXT = re.compile(r"Current Power Limit\s*:\s*([\d.]+)\s*W")
RTF = re.compile(r"rtf=([\d.]+)")
RTF_TAIL_BYTES = 8192  #: stop 줄 하나만 있으면 되니 파일 전체를 매 표본 읽지 않는다.


def run_nvidia_smi(fields, timeout=10):
    """(성공, stdout, stderr). nvidia-smi 가 없거나 시한이면 (False, '', 이유)."""
    cmd = ["nvidia-smi", f"--query-gpu={','.join(fields)}", "--format=csv,noheader,nounits"]
    try:
        done = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        return False, "", "nvidia-smi 없음"
    except subprocess.TimeoutExpired:
        return False, "", f"nvidia-smi {timeout} s 시한"
    if done.returncode != 0:
        return False, "", (done.stderr or done.stdout or f"exit {done.returncode}").strip()
    return True, done.stdout, ""


def probe_fields(runner=run_nvidia_smi):
    """이 GPU·드라이버에서 실제로 받는 필드 목록. 하나씩 빼거나 별칭으로 바꿔 가며 한 번만 확인한다."""
    fields = list(PREFERRED_FIELDS)
    for _ in range(len(fields) + len(ALIASES) + 1):
        ok, _, err = runner(fields)
        if ok:
            return fields
        bad = _field_named_in_error(err, fields)
        if bad is None:
            # 어떤 필드인지 에러로 못 가르면(예: nvidia-smi 자체가 없음) 더 줄여도 소용없다.
            return [f for f in fields if f == "timestamp"] or ["timestamp"]
        if bad in ALIASES and ALIASES[bad] not in fields:
            fields = [ALIASES[bad] if f == bad else f for f in fields]
        else:
            fields = [f for f in fields if f != bad]
    return fields


def _field_named_in_error(err, fields):
    """nvidia-smi 에러 문자열에 등장하는 필드 하나(있으면). 길게 겹치는 이름부터 본다(예: power.limit 이
    enforced.power.limit 안에도 부분 일치하므로)."""
    for field in sorted(fields, key=len, reverse=True):
        if field != "timestamp" and field in err:
            return field
    return None


def parse_row(line, fields):
    """CSV 한 줄 → {field: 값(문자열, 숫자 필드는 float 시도)}. 못 읽으면 None."""
    parts = [p.strip() for p in next(csv.reader([line]))] if line.strip() else []
    if len(parts) != len(fields):
        return None
    row = {}
    for field, value in zip(fields, parts, strict=True):
        if field in NUMERIC_FIELDS:
            try:
                row[field] = float(value)
            except ValueError:
                row[field] = None  # [N/A] 등 — 이 GPU 는 그 필드를 안 준다(에러는 아니다)
        else:
            row[field] = value
    return row


def run_power_query_text(timeout=10):
    """(성공, stdout, stderr) of `nvidia-smi -q -d POWER`. --query-gpu 가 `enforced.power.limit` 자체를
    거부하는 드라이버(마클1 9/27, master01)를 위한 대체 경로 — 이 텍스트 출력은 거부하지 않았다."""
    try:
        done = subprocess.run(["nvidia-smi", "-q", "-d", "POWER"], capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        return False, "", "nvidia-smi 없음"
    except subprocess.TimeoutExpired:
        return False, "", f"nvidia-smi {timeout} s 시한"
    if done.returncode != 0:
        return False, "", (done.stderr or done.stdout or f"exit {done.returncode}").strip()
    return True, done.stdout, ""


def power_limit_from_text(text):
    """`-q -d POWER` 출력에서 `Current Power Limit` 의 W 값. 없으면 None."""
    match = POWER_LIMIT_TEXT.search(text or "")
    return float(match.group(1)) if match else None


def effective_power_limit(row, text_fallback_w):
    """(값, 출처) — CSV 필드가 있으면 그것, 없으면(이 GPU·드라이버가 필드 자체를 거부) 시작 때 한 번 잰
    `-q -d POWER` 값을 쓴다(값은 바뀌지 않는다고 본다 — 이 하드웨어는 상한 조정이 안 된다)."""
    for key in ("enforced.power.limit", "power.limit"):
        value = row.get(key)
        if value is not None:
            return value, key
    if text_fallback_w is not None:
        return text_fallback_w, "-q -d POWER 파싱"
    return None, None


def latest_rtf(stage_log_path, tail_bytes=RTF_TAIL_BYTES):
    """stage 로그 끝 `tail_bytes` 안의 마지막 `rtf=` 값. round 가 아직 안 끝났으면(줄 자체가 없으면) None."""
    try:
        with open(stage_log_path, "rb") as handle:
            handle.seek(0, 2)
            size = handle.tell()
            handle.seek(max(0, size - tail_bytes))
            text = handle.read().decode("utf-8", errors="replace")
    except OSError:
        return None
    matches = RTF.findall(text)
    return float(matches[-1]) if matches else None


def throttled(row):
    """스로틀 비트가 켜져 있나(0x0 이 아니면 켜짐). 필드가 없으면 None(모름). 경보 여부는 이걸로 안 정한다
    — 0x1(GPU idle)은 늘 켜지고 0x4(SW power cap)는 만부하에서 정상이라 `throttle_bit_warning` 을 쓴다."""
    value = row.get("clocks_throttle_reasons.active") or row.get("clocks_event_reasons.active")
    if value is None:
        return None
    return value.strip().lower() not in NOT_ACTIVE


#: NVML 비트값(표준). 0x1 GPU idle, 0x4 SW power cap 은 각각 유휴·상한에 닿은 정상 만부하에서 항상 켜진다.
#: 0x8 HW slowdown, 0x20 SW thermal, 0x40 HW thermal, 0x80 HW power brake 는 항상 실제 문제다.
BIT_GPU_IDLE = 0x1
BIT_SW_POWER_CAP = 0x4
ALWAYS_WARN_BITS = 0x8 | 0x20 | 0x40 | 0x80


def throttle_bit_warning(row, power_limit_expected_w, power_limit_tolerance_w, power_limit_text_fallback_w):
    """None 이면(스로틀 비트만 보면) 정상. 작전 9/27 지적: 0x1 은 유휴 GPU 가 항상 켜는 비트라 무해하고,
    0x4 는 80 W 상한에 정확히 닿은 정상 만부하에서 항상 켜진다(마1검증 9/27 실측: 86 °C·0x4 는 정상 동작).
    0x4 는 전력 상한 자체가 기대값과 다르거나 실제 전력이 그 상한의 절반 밑일 때만(진짜 이상) 경보한다 —
    `power_limit_expected_w` 가 없으면(`--no-power-limit-check`) 이 둘 다 끈다(마1검증 9/27 비차단 관찰:
    "전력 상한 판정을 전부 끈다" 는 뜻으로 읽는 게 덜 놀랍다 — GPU 자기 신고값을 기준 삼아 몰래 계속 보지
    않는다). 그 밖의 비트(HW slowdown·SW/HW 열·power brake, 그리고 목록에 없는 비트)는 늘 경보한다."""
    text = row.get("clocks_throttle_reasons.active") or row.get("clocks_event_reasons.active")
    if text is None:
        return None
    try:
        mask = int(text, 16)
    except ValueError:
        return None  # 16진수가 아닌 형식 — 판정하지 않는다(모른다)
    if mask & ALWAYS_WARN_BITS:
        return f"GPU 스로틀 걸림({text}) — HW slowdown·열·power brake 계열"
    if mask & BIT_SW_POWER_CAP:
        if power_limit_expected_w is None:
            return None  # --no-power-limit-check — 전력 상한 관련 판정을 전부 끈다
        limit, source = effective_power_limit(row, power_limit_text_fallback_w)
        draw = row.get("power.draw")
        if limit is not None and abs(limit - power_limit_expected_w) > power_limit_tolerance_w:
            return (f"GPU SW 전력 상한 걸림({text}) — 상한 자체가 기대값과 다르다"
                   f"({source}: {limit:g} W, 기대 {power_limit_expected_w:g} W)")
        if draw is not None and draw < 0.5 * power_limit_expected_w:
            return (f"GPU SW 전력 상한 걸림({text}) — 전력 {draw:g} W 가 상한의 절반"
                   f"({0.5 * power_limit_expected_w:g} W) 밑")
        return None  # 상한에 닿은 정상 만부하 — 조용하다
    if mask & ~BIT_GPU_IDLE:
        return f"GPU 스로틀 걸림({text}) — 알려지지 않은 비트, 안전하게 경보한다"
    return None  # 0x1(idle)만 켜짐 — 무해


def judge(row, history, load_baseline, power_drop_ratio, power_drop_min_w, temp_limit_c=87.0,
         power_limit_expected_w=None, power_limit_tolerance_w=3.0, power_limit_text_fallback_w=None,
         rtf=None, rtf_min=None):
    """[경고 문장] — 없으면 정상. 기준값은 전부 인자다(작전 9/27: 코드에 박지 않는다)."""
    warnings = []
    throttle_msg = throttle_bit_warning(row, power_limit_expected_w, power_limit_tolerance_w,
                                        power_limit_text_fallback_w)
    if throttle_msg:
        warnings.append(throttle_msg)
    if (row.get("temperature.gpu") or 0) >= temp_limit_c:
        warnings.append(f"GPU {row['temperature.gpu']:g} °C — 열 상한({temp_limit_c:g} °C) 근접")
    draw = row.get("power.draw")
    if draw is not None and len(history) >= 3:
        recent = statistics.median(h["power.draw"] for h in history if h.get("power.draw") is not None)
        if recent >= power_drop_min_w and draw < power_drop_ratio * recent:
            warnings.append(f"GPU 전력 급락({draw:g} W, 최근 중앙값 {recent:.1f} W) — 원인 불명, 시각을 남긴다")
    if power_limit_expected_w is not None:
        limit, source = effective_power_limit(row, power_limit_text_fallback_w)
        if limit is not None and abs(limit - power_limit_expected_w) > power_limit_tolerance_w:
            warnings.append(f"GPU 전력 상한이 기대값과 다르다({source}: {limit:g} W, "
                            f"기대 {power_limit_expected_w:g} W)")
    load = boot_check.read_load()
    if load is not None and load_baseline is not None and load > 2.0 * load_baseline:
        warnings.append(f"load {load:.2f} > 기준선 {load_baseline:g} 의 2 배")
    if rtf is not None and rtf_min is not None and rtf < rtf_min:
        warnings.append(f"rtf {rtf:g} < 하한 {rtf_min:g}(stage 로그 stop 줄)")
    return warnings


def stale_warning(web, max_recorders, tmux_prefix):
    """boot_check 의 관제 창·녹화기·tmux 판정 그대로(회차 자신의 것과 남은 것을 코드로 이미 가른다 —
    tmux 는 자식 프로세스가 없는 세션만 잔류로 본다, 살아 있는 회차의 세션은 안 걸린다).

    load 는 여기서 빼고 None 으로 보낸다(작전 9/27 지적) — check_stale 의 load 판정은 "다른 프로세스가
    CPU 를 쓴다"고 적지만, `--stale-every` 로 회차 도중에도 이 함수를 부르면 그 회차 자신의 정상적인 부하가
    기준선의 2 배를 넘을 수 있어(잔류가 아닌데 잔류로 잘못 읽힌다). load 판정은 `judge()` 가 이미
    독립적으로, 옳게 이름 붙여(`load ... > 기준선`) 하고 있으므로 여기서 또 하지 않는다."""
    args = argparse.Namespace(web=web, max_recorders=max_recorders, tmux_prefix=tmux_prefix, load_baseline=None)
    ok, detail = boot_check.check_stale(args)
    return None if ok else f"잔류: {detail}"


def _open_csv_writer(path, fields):
    is_new = not path.is_file() or path.stat().st_size == 0
    handle = path.open("a", newline="", encoding="utf-8")
    writer = csv.writer(handle)
    if is_new:
        writer.writerow(fields)
    return handle, writer


def watch(args, runner=run_nvidia_smi, sleep=time.sleep, clock=time.monotonic, out=sys.stdout,
         power_query=run_power_query_text):
    fields = probe_fields(runner)
    dropped = [f for f in PREFERRED_FIELDS if f not in fields and ALIASES.get(f) not in fields]
    if dropped:
        print(f"[hw_watch] 이 GPU·드라이버가 안 받는 필드라 뺐다: {', '.join(dropped)}", file=out)
    power_limit_fallback = None
    if (args.power_limit_expected is not None and "power.limit" not in fields
            and "enforced.power.limit" not in fields):
        ok, stdout, err = power_query()
        power_limit_fallback = power_limit_from_text(stdout) if ok else None
        if power_limit_fallback is None:
            print(f"[hw_watch] 전력 상한 필드도 -q -d POWER 도 못 읽었다: {err or '줄을 못 찾음'}"
                  " — 전력 상한 판정을 건너뛴다", file=out)
    handle = writer = None
    if args.gpu_csv:
        handle, writer = _open_csv_writer(Path(args.gpu_csv), fields)
    history = []
    last_rtf_warned = None
    deadline = None if args.duration is None else clock() + args.duration
    sample = 0
    try:
        while True:
            ok, stdout, err = runner(fields)
            if not ok:
                print(f"[hw_watch] nvidia-smi 실패: {err}", file=out)
            else:
                row = parse_row(stdout.strip().splitlines()[0], fields) if stdout.strip() else None
                if row is None:
                    print("[hw_watch] nvidia-smi 출력을 못 읽었다", file=out)
                else:
                    if writer:
                        writer.writerow([row[f] if row[f] is not None else "" for f in fields])
                        handle.flush()
                    rtf = latest_rtf(args.stage_log) if args.stage_log else None
                    rtf_is_new = rtf is not None and rtf != last_rtf_warned
                    for warning in judge(row, history, args.load_baseline, args.power_drop_ratio,
                                        args.power_drop_min_w, args.temp_limit, args.power_limit_expected,
                                        args.power_limit_tolerance, power_limit_fallback,
                                        rtf if rtf_is_new else None, args.rtf_min):
                        print(f"[hw_watch] WARN {row.get('timestamp', '')} {warning}", file=out)
                    if rtf_is_new:
                        last_rtf_warned = rtf
                    history.append(row)
                    del history[:-args.history]
            sample += 1
            if args.stale_every and sample % args.stale_every == 0:
                warning = stale_warning(args.web, args.max_recorders, args.tmux_prefix)
                if warning:
                    print(f"[hw_watch] WARN {warning}", file=out)
            if args.once or (args.count and sample >= args.count) or (deadline and clock() >= deadline):
                break
            sleep(args.interval)
    finally:
        if handle:
            handle.close()
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--load-baseline", type=float, default=boot_check._env_float("P3_LOAD_BASELINE"),
                        help="이 장비의 깨끗한 회차 load(1 분). boot_check 와 같은 뜻(없으면 load 판정을 건너뛴다)")
    parser.add_argument("--gpu-csv", help="이 파일에 매 표본을 이어 붙인다(헤더는 파일이 없거나 비었을 때 한 번)")
    parser.add_argument("--interval", type=float, default=5.0, help="표본 간격 s")
    parser.add_argument("--once", action="store_true", help="한 번만 재고 끝난다")
    parser.add_argument("--count", type=int, help="이 표본 수만큼 재고 끝난다(--once 보다 우선순위 낮음)")
    parser.add_argument("--duration", type=float, help="이 s 가 지나면 끝난다")
    parser.add_argument("--history", type=int, default=12, help="전력 급락 판단에 쓰는 최근 표본 수")
    parser.add_argument("--power-drop-ratio", type=float, default=0.3,
                        help="최근 중앙값의 이 비율 밑으로 떨어지면 경보")
    parser.add_argument("--power-drop-min-w", type=float, default=40.0,
                        help="최근 중앙값이 이 값 이상일 때만 급락을 본다(유휴 상태의 정상적인 낮은 값은 제외)")
    parser.add_argument("--stale-every", type=int, default=12,
                        help="이 표본마다 한 번 관제 창·녹화기·tmux 잔류(boot_check stale, load 는 뺀 값)"
                             "를 본다. 회차 도중에도 안전하다(그 회차 자신의 창·녹화기·tmux 는 안 걸린다"
                             " — stale_warning() 문서). 0 이면 안 본다")
    parser.add_argument("--temp-limit", type=float, default=87.0,
                        help="GPU 열 상한 °C(두 장비 공통 목표 온도, 9/24 관측). 이 이상이면 근접 경보")
    parser.add_argument("--power-limit-expected", type=float, default=80.0,
                        help="GPU 전력 상한의 기대값 W(두 장비 공통, 9/24 관측). None 이면 이 판정을 끈다")
    parser.add_argument("--no-power-limit-check", dest="power_limit_expected", action="store_const", const=None,
                        help="--power-limit-expected 을 끈다")
    parser.add_argument("--power-limit-tolerance", type=float, default=3.0,
                        help="기대값과 이 W 넘게 차이 나면 경보")
    parser.add_argument("--rtf-min", type=float,
                        help="이 값 밑이면 경보(--stage-log 가 있어야 읽는다). 기본은 안 본다")
    parser.add_argument("--stage-log", help="stage 로그 경로 — 있으면 stop 줄의 rtf 를 읽는다(끝 8 KB 만)")
    parser.add_argument("--web", help="관제 창 식(잔류 판정에 넘김, boot_check 와 같은 뜻)")
    parser.add_argument("--max-recorders", type=int, default=1, help="허용하는 화면 녹화기 수(잔류 판정)")
    parser.add_argument("--tmux-prefix", default="p3v2-", help="demo_v2 tmux 세션 접두(잔류 판정)")
    args = parser.parse_args(argv)
    return watch(args)


if __name__ == "__main__":
    sys.exit(main())
