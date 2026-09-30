#!/usr/bin/env python3
"""병원 주문 10건을 관제 웹 API 로 차례로 넣고 판정한다(v2 준비, 9/25). 표준 라이브러리만.

    python3 tools/hospital_orders.py --web http://127.0.0.1:8000 --out ~/p3_demo_logs/orders-<시각>

웹은 `--allow-commands` 로 떠 있어야 한다(`tools/demo_v2.sh up` 이 그렇게 띄운다). 이 도구는 웹만 부른다 —
ROS 를 직접 건드리지 않는다. 실물 경로(오케스트레이터)는 웹 뒤에 있다.

**계획(기본)** — 주문 풀(`/api/order_pool`) 순서로 짠다. 트립은 한 번에 하나라 줄을 세워 하나씩 보낸다.

    1인 ord-0001 → [긴급 ord-0002 끼어듦] → 1인 0003 → 1인 0004 → 병실 묶음 C2(0005·0006·0007) → 1인 0008·0009·0010

- 긴급은 풀에서 `mode: urgent` 인 주문이다. `--urgent-after N` 번째 일반 요청이 끝난 뒤, 남은 일반 요청보다 먼저 보낸다.
- 병실 묶음은 `--batch` 주문들(한 병실이어야 한다 — 웹이 `mixed_rooms` 로 막는다). 비우면 묶음 없이 전부 1인이다.

**프로필**(`--profile`, 재범 9/24 "병상 병실 다 테스트") — 시한·판정선은 같다.

- `default` — 위 계획(1인 7·긴급 1·병실 묶음 C2 1건, 주문 10). 풀의 **침상** 주문 10건을 다 넣는다.
  병실 묶음 C2(0005–0007)는 구역 파일에 병실 테이블(station_d)이 있으면 그 테이블 한 곳에 세 봉투를 놓는다
  (재범 9/25: 병실 주문 → 그 방 테이블 C). 없으면 예전처럼 침상마다 선다(orchestrator `zones_file`).
- `beds-all` — 풀 13건을 다 넣는다(재범 9/25 03:3x "D1–D10 + C1 + C2 + B"). 요청 13개, 그중 긴급 1:
  D1–D10 각 1건(1인 9 + 긴급 ord-0002 1, `--urgent-after` 자리) → C1 테이블 ord-0012(병실 묶음 1건,
  station_c) → C2 테이블 ord-0013(병실 묶음 1건, station_d) → B 테이블 ord-0011(1인, station_b).
  C·B 는 테이블 자리라 인식표가 st-<zone> 이다.
- `station-b` — 병동 묶음(mode 3) 한 건 → `station_b`, 주문은 `--batch`(기본 C2 의 0005·0006·0007).
  `station_b` 가 zones 에 있어야 한다. 없으면 보내기 전에 멈춘다(exit 2).

**판정** — 계획의 모든 주문이 `delivered`(api.md §1.5)면 PASS(exit 0), 아니면 FAIL(exit 1).
결말·사유(`reason`)·트립의 마지막 단계는 돌면서 `/api/snapshot` 의 트립 주문에서 모은다 — `/api/queue`(#586)가
없는 웹(9/23 골든 4d01333)에서도 판정한다. `/api/queue` 가 있으면 끝에 그것으로 결말을 한 번 더 맞춘다.
둘 다 결말을 못 줬는데 그 주문의 `CABINET_LOCKED` 가 있으면 `delivered` 로 본다. 출처는 `outcome_source`
(`snapshot`·`queue`·`cabinet_locked`)에 남는다.
트립이 끝났다는 것은 스냅숏(그 트립이 닫힘) 또는 그 요청의 `DOCKED` 로만 본다.
`--out` 에 `orders.jsonl`(주문마다) · `requests.jsonl`(요청마다) · `summary.md`(표 + 판정)를 남긴다.

| 값 | 뜻 | 시계 |
|---|---|---|
| `wait_s` | 줄에 선 순간(시작 또는 긴급이 끼어든 순간) → 웹이 트립 수락을 본 순간 | wall |
| `deliver_sim_s` | `REQUEST_ACCEPTED` → 그 주문의 `CABINET_LOCKED` | sim |
| `trip_sim_s` | `REQUEST_ACCEPTED` → `DOCKED` | sim |
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

#: 기다리면 풀리는 거부(api.md §7.2). 그 밖의 거부는 입력이 틀린 것이라 멈춘다.
WAITABLE = frozenset({"trip_in_progress", "refill_in_progress", "barrier_running", "insufficient_stock"})
MODE_SINGLE, MODE_URGENT, MODE_BATCH_ROOM, MODE_BATCH_WARD = 0, 1, 2, 3
PROFILES = ("default", "beds-all", "station-b")
#: station-b 프로필의 목적지. 병원 zones 에 이 구역이 생기면 돈다(9/24 에는 station_a 만 있다).
STATION_B = "station_b"
DEFAULT_BATCH = ("ord-0005", "ord-0006", "ord-0007")


# ── 계획(순수) ───────────────────────────────────────────────────────────

#: 침상이 아니라 테이블인 목적지(병동 B = station_b, 병실 C = station_c·station_d). 10건 기본 계획은 침상 주문만 쓴다.
TABLE_PREFIXES = ("station_",)
#: 병실 C 테이블(병동 입구 복도 협탁, 재범 9/25). 나머지 station_* 은 병동 B 다.
ROOM_TABLES = ("station_c", "station_d")


def is_table_order(order: dict) -> bool:
    return (order.get("bed") or "").startswith(TABLE_PREFIXES)


def build_plan(pool: list[dict], batch: tuple[str, ...] = DEFAULT_BATCH, urgent_after: int = 1,
               prefix: str = "v2") -> list[dict]:
    """풀 순서로 요청 목록을 짠다. 각 요청: request_id, mode, destination_id, orders, urgent. 침상 주문만 쓴다."""
    pool = [o for o in pool if not is_table_order(o)]
    batch = tuple(b for b in batch if b)
    urgent = [o for o in pool if o.get("mode") == "urgent"]
    normal: list[dict] = []
    for order in pool:
        if order in urgent or order["order_id"] in batch[1:]:
            continue
        if batch and order["order_id"] == batch[0]:
            beds = {o["order_id"]: o.get("bed") for o in pool}
            normal.append({"mode": MODE_BATCH_ROOM, "destination_id": beds.get(batch[0]) or "",
                           "orders": list(batch), "urgent": False})
        else:
            normal.append({"mode": MODE_SINGLE, "destination_id": order.get("bed") or "",
                           "orders": [order["order_id"]], "urgent": False})
    steps = [{"mode": MODE_URGENT, "destination_id": o.get("bed") or "", "orders": [o["order_id"]], "urgent": True}
             for o in urgent]
    at = max(0, min(urgent_after, len(normal)))
    return _number(normal[:at] + steps + normal[at:], prefix)


def _number(plan: list[dict], prefix: str) -> list[dict]:
    for n, step in enumerate(plan, 1):
        kind = "urgent" if step["urgent"] else ("room" if step["mode"] == MODE_BATCH_ROOM else "single")
        step["request_id"] = f"{prefix}-{n:02d}-{kind}"
    return plan


def table_steps(pool: list[dict]) -> list[dict]:
    """테이블 주문 → 요청. 병실 테이블(station_c·station_d)은 병실 묶음 1건, 병동 B(station_b)는 1인.

    순서는 C 다음 B.
    """
    rooms = [o for o in pool if (o.get("bed") or "") in ROOM_TABLES]
    wards = [o for o in pool if (o.get("bed") or "").startswith("station_") and o.get("bed") not in ROOM_TABLES]
    return ([{"mode": MODE_BATCH_ROOM, "destination_id": o["bed"], "orders": [o["order_id"]], "urgent": False}
             for o in rooms]
            + [{"mode": MODE_SINGLE, "destination_id": o["bed"], "orders": [o["order_id"]], "urgent": False}
               for o in wards])


def profile_plan(profile: str, pool: list[dict], batch: tuple[str, ...], urgent_after: int) -> list[dict]:
    """프로필 → 계획. default 는 build_plan 그대로, beds-all 은 묶음 없이, station-b 는 병동 묶음 한 건."""
    if profile == "beds-all":
        return _number(build_plan(pool, (), urgent_after, prefix="beds") + table_steps(pool), "beds")
    if profile == "station-b":
        orders = [b for b in batch if b]
        return [{"request_id": "stb-01-ward", "mode": MODE_BATCH_WARD, "destination_id": STATION_B,
                 "orders": orders, "urgent": False}]
    return build_plan(pool, batch, urgent_after)


def check_plan(plan: list[dict], pool: list[dict], rooms: dict[str, str | None],
               require_all: bool = True) -> list[str]:
    """보내기 전에 알 수 있는 문제. 빈 목록이면 보낸다.

    `require_all` 이면 계획이 다뤄야 할 풀 주문을 다 넣어야 한다 — 계획에 테이블 주문이 하나라도 있으면(beds-all)
    풀 전부, 없으면(default) 침상 주문 전부다.
    """
    problems = []
    by_id = {o["order_id"]: o for o in pool}
    seen: list[str] = []
    for step in plan:
        for order_id in step["orders"]:
            if order_id not in by_id:
                problems.append(f"{step['request_id']}: 풀에 없는 주문 {order_id}")
            elif by_id[order_id].get("used"):
                problems.append(f"{step['request_id']}: 이미 쓴 주문 {order_id} — 리셋하고 다시")
            seen.append(order_id)
        if step["mode"] == MODE_BATCH_WARD and step["destination_id"] not in rooms:
            problems.append(f"{step['request_id']}: 목적지 {step['destination_id']} 가 zones 에 없다"
                            " — 구역이 생기면 돌린다")
        if step["mode"] == MODE_BATCH_ROOM:
            groups = {rooms.get(by_id.get(o, {}).get("bed") or "") for o in step["orders"]}
            if None in groups or len(groups) != 1:
                problems.append(f"{step['request_id']}: 병실 묶음이 한 병실이 아니다 {sorted(map(str, groups))}")
    dup = sorted({o for o in seen if seen.count(o) > 1})
    if dup:
        problems.append(f"두 번 넣는 주문: {dup}")
    tables = any(is_table_order(by_id.get(o, {})) for o in seen)
    missing = [o for o, row in by_id.items() if o not in seen and (tables or not is_table_order(row))]
    if require_all and missing:
        problems.append(f"계획에 없는 풀 주문: {missing}")
    return problems


def summarize(plan: list[dict], events: list[dict], outcomes: dict[str, str | None],
              timing: dict[str, dict], pool: list[dict], labels: dict[str, str | None],
              reasons: dict[str, str] | None = None, sources: dict[str, str] | None = None) -> dict:
    """주문·요청 행과 판정. events 는 현재 epoch 의 /api/events."""
    beds = {o["order_id"]: o.get("bed") for o in pool}
    first: dict[tuple[str, str], float] = {}
    locked: dict[str, float] = {}
    for ev in events:
        key = (ev.get("request_id") or "", ev["name"])
        first.setdefault(key, float(ev["stamp"]))
        if ev["name"] == "CABINET_LOCKED" and ev.get("order_id"):
            locked.setdefault(ev["order_id"], float(ev["stamp"]))
    requests, orders = [], []
    for step in plan:
        rid = step["request_id"]
        acc, docked = first.get((rid, "REQUEST_ACCEPTED")), first.get((rid, "DOCKED"))
        t = timing.get(rid, {})
        wait = (t["accepted_wall"] - t["queued_wall"]) if t.get("accepted_wall") and t.get("queued_wall") else None
        requests.append({"request_id": rid, "mode": step["mode"], "urgent": step["urgent"], "orders": step["orders"],
                         "retries": t.get("retries", 0), "wait_s": _r(wait), "last_phase": t.get("last_phase"),
                         "stopped": t.get("stopped"), "stopped_at": t.get("stopped_at"),
                         "sent": "sent_wall" in t,
                         "trip_sim_s": _r(docked - acc) if acc is not None and docked is not None else None})
        for order_id in step["orders"]:
            lock = locked.get(order_id)
            outcome, source = outcomes.get(order_id), (sources or {}).get(order_id)
            if outcome is None and lock is not None:
                # 결말을 못 봤다(/api/queue 없음 + 스냅숏이 주문을 놓침). 보관함이 잠겼으면 전달로 본다 — 출처를 남긴다.
                outcome, source = "delivered", "cabinet_locked"
            if "sent_wall" not in t:
                source = "not_sent"   # 앞 요청에서 멈춰 보내지 않았다
            bed = beds.get(order_id)
            orders.append({"order_id": order_id, "bed": bed, "label": labels.get(bed or ""),
                           "request_id": rid, "urgent": step["urgent"], "outcome": outcome,
                           "outcome_source": source,
                           "reason": (reasons or {}).get(order_id) or None,
                           "wait_s": _r(wait),
                           "deliver_sim_s": _r(lock - acc) if acc is not None and lock is not None else None})
    delivered = sum(o["outcome"] == "delivered" for o in orders)
    stopped = next((r for r in requests if r["stopped"]), None)
    return {"verdict": "PASS" if orders and delivered == len(orders) else "FAIL",
            "delivered": delivered, "total": len(orders), "requests": requests, "orders": orders,
            "stopped": stopped, "not_sent": [o["order_id"] for o in orders if o["outcome_source"] == "not_sent"]}


def _r(value: float | None) -> float | None:
    return None if value is None else round(value, 2)


def summary_markdown(result: dict) -> str:
    lines = [f"# 병원 주문 판정 — **{result['verdict']}** ({result['delivered']}/{result['total']} delivered)", ""]
    stop = result.get("stopped")
    if stop:
        # 막힌 건·사유·시각을 맨 위에(작전 9/24). 오케스트레이터가 그 트립을 잡고 있으면 다음 요청은 못 보낸다.
        which = f"{stop['request_id']}({' '.join(stop['orders'])})"
        not_sent = " ".join(result["not_sent"]) or "없음"
        lines += [f"**멈춤** {stop['stopped_at']} — {which}: {stop['stopped']}, "
                  f"마지막 단계 {stop['last_phase'] or '모름'}. 보내지 않은 주문: {not_sent}", ""]
    lines += [
             "| 주문 | 병상 | 요청 | 긴급 | 결말 | 사유 | 대기 wall s | 배송 sim s |",
             "|---|---|---|---|---|---|---|---|"]
    for o in result["orders"]:
        urgent = "예" if o["urgent"] else ""
        outcome = "미실행" if o["outcome_source"] == "not_sent" else o["outcome"]
        lines.append(f"| {o['order_id']} | {o['label'] or o['bed']} | {o['request_id']} | {urgent} "
                     f"| {outcome} | {o['reason'] or ''} | {o['wait_s']} | {o['deliver_sim_s']} |")
    lines += ["", "| 요청 | 모드 | 주문 | 재시도 | 트립 sim s | 마지막 단계 | 멈춤 |", "|---|---|---|---|---|---|---|"]
    for r in result["requests"]:
        orders = " ".join(r["orders"])
        lines.append(f"| {r['request_id']} | {r['mode']} | {orders} | {r['retries']} | {r['trip_sim_s']} "
                     f"| {r['last_phase'] or ''} | {r['stopped'] or ''} |")
    return "\n".join(lines) + "\n"


# ── 웹 ───────────────────────────────────────────────────────────────────

class Web:
    def __init__(self, base: str) -> None:
        self.base = base.rstrip("/")

    def call(self, path: str, body: dict | None = None) -> tuple[int, dict]:
        req = urllib.request.Request(self.base + path, method="POST" if body is not None else "GET",
                                     data=json.dumps(body).encode() if body is not None else None,
                                     headers={"content-type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=10) as res:
                return res.status, json.loads(res.read())
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read() or b"{}")

    def get(self, path: str) -> dict:
        code, body = self.call(path)
        if code != 200:
            raise RuntimeError(f"GET {path} → {code} {body}")
        return body

    def events(self) -> list[dict]:
        out, since = [], 0
        while True:
            page = self.get(f"/api/events?since={since}&limit=500")
            out += page["events"]
            if not page.get("has_more"):
                return out
            since = page["next_since"]


def idle(snap: dict) -> bool:
    trip = snap.get("trip")
    return bool(snap.get("accepting_requests")) and (trip is None or trip.get("phase") == "docked")


def note_trip(trip: dict, timing: dict[str, dict], seen: dict[str, dict]) -> None:
    """열린 트립에서 주문별 결말·사유와 트립의 마지막 단계를 적는다(늦게 본 것이 이긴다)."""
    rid = trip.get("request_id")
    if rid in timing:
        timing[rid]["last_phase"] = trip.get("phase_label") or trip.get("phase")
    for order in trip.get("orders") or []:
        if order.get("order_id"):
            seen[order["order_id"]] = {"outcome": order.get("outcome"), "reason": order.get("reason") or ""}


def stop(entry: dict, why: str) -> None:
    """이 요청에서 멈췄다 — 사유와 시각(wall, 이 PC 의 현지 시각)을 남긴다."""
    entry["stopped"], entry["stopped_at"] = why, time.strftime("%Y-%m-%dT%H:%M:%S")


def stops(step: dict) -> int:
    """정거장 수. 병실 묶음은 침상마다 서고, 1인·긴급은 한 곳이다."""
    return len(set(step["orders"])) if step["mode"] == MODE_BATCH_ROOM else 1


def run(web: Web, plan: list[dict], trip_timeout_s: float, log,
        seen: dict[str, dict] | None = None, timing: dict[str, dict] | None = None) -> dict[str, dict]:
    """계획을 하나씩 보낸다. 요청마다 queued·sent·accepted wall 과 재시도 수를 돌려준다.

    `seen` 에 스냅숏에서 본 주문별 결말·사유를 모은다. 멈추면 RuntimeError — 그때까지의 `timing` 은 남는다.
    """
    timing = {} if timing is None else timing
    seen = {} if seen is None else seen
    start = time.time()
    for step in plan:
        rid = step["request_id"]
        # 긴급은 끼어든 순간(앞 요청이 끝난 지금)에 줄에 선다. 일반은 처음부터 줄에 서 있었다.
        timing[rid] = {"queued_wall": time.time() if step["urgent"] else start, "retries": 0}
        # 시한은 정거장 수에 비례한다 — 병실 묶음은 침상마다 주행·인증·놓기를 한다(9/24 master02: 정거장 셋인
        # v2-05-room 이 1인 기준 900 s 에 걸려 멈췄다).
        limit = trip_timeout_s * stops(step)
        deadline = time.time() + limit
        while True:
            if time.time() > deadline:
                stop(timing[rid], "보내지 못함(시한)")
                raise RuntimeError(f"{rid}: {limit:.0f} s 안에 보내지 못했다")
            if not idle(web.get("/api/snapshot")):
                time.sleep(0.5)
                continue
            code, body = web.call("/api/requests", {"request_id": rid, "mode": step["mode"],
                                                    "destination_id": step["destination_id"],
                                                    "orders": [{"order_id": o} for o in step["orders"]]})
            if code == 200:
                timing[rid]["sent_wall"] = time.time()
                log(f"보냄 {rid} mode={step['mode']} {step['orders']}")
                break
            err = body.get("error", {})
            if err.get("code") in WAITABLE:
                timing[rid]["retries"] += 1
                log(f"기다림 {rid}: {code} {err.get('code')} — {err.get('message')}")
                time.sleep(3)
                continue
            stop(timing[rid], f"거부 {code} {err.get('code')}")
            raise RuntimeError(f"{rid}: {code} {err.get('code')} — {err.get('message')} (입력을 고쳐야 한다)")
        while True:   # 이 요청의 트립이 열리고(수락) 도크로 닫힐 때까지
            if time.time() > deadline:
                stop(timing[rid], f"트립 시한({limit:.0f} s)")
                raise RuntimeError(f"{rid}: {limit:.0f} s 안에 트립이 끝나지 않았다")
            snap = web.get("/api/snapshot")
            trip = snap.get("trip") or {}
            if trip.get("request_id") == rid:
                note_trip(trip, timing, seen)
            if trip.get("request_id") == rid and "accepted_wall" not in timing[rid]:
                timing[rid]["accepted_wall"] = time.time()
            if idle(snap) and "accepted_wall" not in timing[rid] and any(
                    e["name"] == "DOCKED" and e.get("request_id") == rid for e in web.events()):
                # 폴링 사이에 트립이 열리고 **닫혔다**(빠른 스텁). 닫힘은 그 요청의 DOCKED 로만 본다 —
                # REQUEST_ACCEPTED 로 보면 스냅숏이 아직 앞 트립(한가함)일 때 막 시작한 트립을 끝났다고 읽는다
                # (커서 검토 #616). 수락을 지금 본 것으로 적으니 대기 시간이 조금 길게 나온다.
                timing[rid]["accepted_wall"] = time.time()
                timing[rid]["accepted_late"] = True
            if "accepted_wall" in timing[rid] and idle(snap):
                log(f"끝 {rid}")
                break
            time.sleep(0.5)
    return timing


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--web", default="http://127.0.0.1:8000")
    p.add_argument("--out", required=True, help="판정 로그 디렉토리(없으면 만든다)")
    p.add_argument("--profile", choices=PROFILES, default="default", help="주문 계획(머리 주석의 표)")
    p.add_argument("--urgent-after", type=int, default=1, help="긴급이 끼어드는 자리(일반 요청 N 개 뒤)")
    p.add_argument("--batch", default=",".join(DEFAULT_BATCH), help="병실 묶음 주문(쉼표). 빈 값이면 묶음 없음")
    p.add_argument("--trip-timeout", type=float, default=900.0,
                   help="정거장 하나당 wall 시한 s. 요청의 시한 = 이 값 × 정거장 수(병실 묶음은 침상 수)")
    p.add_argument("--dry-run", action="store_true", help="계획과 확인만 찍고 보내지 않는다")
    args = p.parse_args(argv)

    out = Path(args.out).expanduser()
    web = Web(args.web)

    def log(msg: str) -> None:
        print(f"[hospital_orders {time.strftime('%H:%M:%S')}] {msg}", flush=True)

    pool = web.get("/api/order_pool")["orders"]
    zones = web.get("/api/destinations")["destinations"]
    rooms = {z["destination_id"]: z.get("group") for z in zones}
    labels = {z["destination_id"]: z.get("label") for z in zones}
    plan = profile_plan(args.profile, pool, tuple(args.batch.split(",")) if args.batch else (), args.urgent_after)
    for step in plan:
        log(f"계획 {step['request_id']} mode={step['mode']} {step['orders']}")
    problems = check_plan(plan, pool, rooms, require_all=args.profile != "station-b")
    if problems:
        for line in problems:
            log(f"문제: {line}")
        return 2
    if args.dry_run:
        return 0

    seen: dict[str, dict] = {}
    timing: dict[str, dict] = {}
    stopped = False
    try:
        run(web, plan, args.trip_timeout, log, seen=seen, timing=timing)
    except RuntimeError as exc:
        log(f"멈춤: {exc}")
        stopped = True
    epoch = web.get("/api/snapshot")["epoch"]
    events = [e for e in web.events() if e.get("epoch") == epoch]
    outcomes = {oid: v["outcome"] for oid, v in seen.items()}
    sources = dict.fromkeys(seen, "snapshot")
    code, queue = web.call("/api/queue")   # #586 이 없는 웹이면 404 — 스냅숏에서 모은 것으로 판정한다
    if code == 200:
        for bucket in ("waiting", "in_progress", "done"):
            for o in queue.get(bucket, []):
                if o.get("outcome"):
                    outcomes[o["order_id"]] = o["outcome"]
                    sources[o["order_id"]] = "queue"
    reasons = {oid: v["reason"] for oid, v in seen.items()}
    result = summarize(plan, events, outcomes, timing, pool, labels, reasons, sources)
    out.mkdir(parents=True, exist_ok=True)
    (out / "orders.jsonl").write_text("".join(json.dumps(o, ensure_ascii=False) + "\n" for o in result["orders"]),
                                      encoding="utf-8")
    (out / "requests.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in result["requests"]),
                                        encoding="utf-8")
    (out / "summary.md").write_text(summary_markdown(result), encoding="utf-8")
    log(f"판정 {result['verdict']} — {result['delivered']}/{result['total']} delivered, 로그 {out}")
    return 0 if result["verdict"] == "PASS" and not stopped else 1


if __name__ == "__main__":
    raise SystemExit(main())
