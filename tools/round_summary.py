#!/usr/bin/env python3
"""회전(campaign) 판정 표: attempt 여러 개의 evidence run 기록을 모아 성공률과 실패 분류별 건수를 낸다.

재범 결정(2026-09-27 17:4x, hospital-full-acceptance-v3): PASS 판정선이 "attempt 16/16 무실패"에서
"attempt_success==1 인 attempt 가 전체의 90% 이상(16 개 회전이면 15 개 이상)"으로 완화됐다. 그 대신
실패마다(attempt_success 가 1 이 아닌 모든 attempt) run 기록에 failure_class(robot·infra·operator)·
failure_cause·failure_evidence·retry_run_id(있으면)를 남기게 됐다(schemas/run.schema.json,
tools/evidence.py). 이 도구는 그 record 들을 모아 한 표로 낸다 — **판정선 자체는 안 정한다**. protocol
purpose 문장이 최종 판정선이고, 사람·마1검증이 그 문장과 대조한다(tools/judge_run.py 와 같은 원칙: 근거
원문을 같이 낸다, 아무것도 고치지 않는다).

    python3 tools/round_summary.py --run <run1.json> --run <run2.json> ... [--pass-ratio 0.9] [--json]

--pass-ratio(기본 0.9, protocol purpose "90% 이상"과 같다)는 표시용 참고선이다 — 문서상 판정선을
대신하지 않는다.
"""

import argparse
import json
from pathlib import Path

FAILURE_CLASSES = ("robot", "infra", "operator")


def load_run(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def metric_value(run, name):
    for metric in run.get("metrics", []):
        if metric["name"] == name:
            return metric["value"]
    return None


def summarize(runs, pass_ratio):
    rows = []
    class_counts = dict.fromkeys(FAILURE_CLASSES, 0)
    unclassified = 0
    success = 0
    for run in runs:
        value = metric_value(run, "attempt_success")
        is_success = value == 1
        if is_success:
            success += 1
        row = {
            "run_id": run.get("run_id"),
            "repetition_index": run.get("repetition_index"),
            "outcome": run.get("outcome"),
            "attempt_success": value,
        }
        if not is_success:
            failure_class = run.get("failure_class")
            if failure_class in class_counts:
                class_counts[failure_class] += 1
            else:
                unclassified += 1
            row.update(
                failure_class=failure_class,
                failure_cause=run.get("failure_cause"),
                failure_evidence=run.get("failure_evidence"),
                retry_run_id=run.get("retry_run_id"),
            )
        rows.append(row)
    total = len(runs)
    success_rate = (success / total) if total else None
    return {
        "attempts": total,
        "success": success,
        "success_rate": success_rate,
        "pass_ratio_reference": pass_ratio,
        "meets_pass_ratio_reference": (success_rate is not None and success_rate >= pass_ratio),
        "failure_class_counts": class_counts,
        "unclassified_failures": unclassified,
        "rows": rows,
    }


def format_table(summary):
    lines = []
    rate = summary["success_rate"]
    rate_text = f"{rate:.4f}" if rate is not None else "?"
    lines.append(f"attempts={summary['attempts']} success={summary['success']} success_rate={rate_text} "
                 f"(참고선 {summary['pass_ratio_reference']:.2f} — 최종 판정선은 protocol purpose)")
    for row in summary["rows"]:
        if row["attempt_success"] == 1:
            continue
        lines.append(
            f"  FAIL rep={row['repetition_index']} run_id={row['run_id']} "
            f"class={row.get('failure_class') or '미기록'} cause={row.get('failure_cause') or '미기록'} "
            f"evidence={row.get('failure_evidence') or '미기록'} retry={row.get('retry_run_id') or '없음'}"
        )
    counted = ", ".join(f"{name}={count}" for name, count in summary["failure_class_counts"].items() if count)
    if counted or summary["unclassified_failures"]:
        extra = f", 미기록={summary['unclassified_failures']}" if summary["unclassified_failures"] else ""
        lines.append(f"failure_class 별 건수: {counted or '없음'}{extra}")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--run", action="append", default=[], required=True,
                         help="evidence run 기록 JSON 경로(여러 번 줄 수 있다, 한 회전의 attempt 마다)")
    parser.add_argument("--pass-ratio", type=float, default=0.9,
                         help="표시용 참고선(기본 0.9). 최종 판정선은 해당 protocol 의 purpose 문장이다")
    parser.add_argument("--json", action="store_true", help="사람이 읽는 표 대신 JSON 을 낸다")
    args = parser.parse_args(argv)
    runs = [load_run(path) for path in args.run]
    summary = summarize(runs, args.pass_ratio)
    print(json.dumps(summary, indent=2, ensure_ascii=False) if args.json else format_table(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
