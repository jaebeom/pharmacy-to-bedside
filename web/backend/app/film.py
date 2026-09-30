"""촬영 화면용 — 트립을 일곱 단계로 묶고(요청→보충→조제→집기→배송→도착→복귀), 주문을 큐로 가른다. 순수.

단계는 **새 이벤트를 만들지 않는다.** 계약 이벤트에서 이미 나온 `trip.phase`(status_view 표, api.md §1.2)를
묶을 뿐이다. 두 곳만 더 본다:

- `arm_home` 은 적재 뒤(LOAD_DONE → ARM_HOME)에도, 배달 뒤(ORDER_DONE → ARM_HOME)에도 나온다.
  그 트립이 이미 `DEPARTED` 했으면 도착 쪽이다.
- 보충은 트립 단계를 바꾸지 않는다(§1.2). 출발 전 단계에서 **이 트립의 약품**이 보충 중이면 "보충" 이다.
  트립의 약품을 모르면(detail 없음) 보충으로 짐작하지 않는다.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

#: (key, 화면 이름). index 는 이 순서다.
STAGES: tuple[tuple[str, str], ...] = (
    ("request", "요청"), ("refill", "보충"), ("dispense", "조제"), ("pick", "집기"),
    ("deliver", "배송"), ("arrive", "도착"), ("return", "복귀"),
)
STAGE_LABELS = dict(STAGES)
STAGE_INDEX = {key: i for i, (key, _) in enumerate(STAGES)}
#: 트립 밖. index 는 null 이다.
OFF_TRIP = {"idle": "대기", "reset": "리셋"}

#: trip.phase → 단계. arm_home 은 따로 가른다.
PHASE_STAGE = {
    "accepted": "request",
    "docked_load": "dispense", "dispensing": "dispense",
    "loading": "pick", "load_done": "pick",
    "moving": "deliver", "arriving": "deliver",
    "arrived": "arrive", "auth": "arrive", "unloading": "arrive", "locked": "arrive", "order_done": "arrive",
    "returning": "return",
    "docked": "idle",
    "reset": "reset", "reset_done": "reset",
}
#: 보충이 단계를 가로챌 수 있는 자리 — 봉투가 아직 조제기에서 안 나왔다.
BEFORE_DISPENSE_OUT = ("request", "dispense")

#: 주문의 결말(§1.5 outcome) 중 끝난 것.
DONE_OUTCOMES = frozenset({"delivered", "pharmacy_done", "held", "aborted", "timeout"})


def stage_for(phase: str | None, *, departed: bool, trip_items: Iterable[str] = (),
              blocked_items: Iterable[str] = (), reset: bool = False) -> dict[str, Any]:
    """snapshot.stage. `blocked_items` = 보충 중이거나 PAUSED 인 약품."""
    if reset:
        key = "reset"
    elif phase is None:
        key = "idle"
    elif phase == "arm_home":
        key = "arrive" if departed else "pick"
    else:
        key = PHASE_STAGE.get(phase, "idle")
    refill_items = sorted(set(trip_items) & set(blocked_items))
    if key in BEFORE_DISPENSE_OUT and refill_items:
        key = "refill"
    return {"key": key, "label": STAGE_LABELS.get(key) or OFF_TRIP[key],
            "index": STAGE_INDEX.get(key), "phase": phase,
            "refill_item_ids": refill_items if key == "refill" else []}


def queue_rows(pool_orders: Iterable[Mapping[str, Any]], statuses: Mapping[str, Mapping[str, Any]],
               used: set[str], outcome_of) -> dict[str, list[dict[str, Any]]]:
    """주문 풀 순서대로 대기·진행·완료로 가른다.

    - 완료: 결말(outcome)이 끝난 것.
    - 진행: 상태가 왔는데 안 끝났거나, 요청에 실려 쓰였는데 아직 상태가 없는 것.
    - 대기: 풀에 있고 아직 어느 요청에도 안 실린 것.
    풀에 없는데 상태가 온 주문(풀 밖 요청)도 뒤에 붙인다 — 조용히 빼지 않는다.
    """
    out: dict[str, list[dict[str, Any]]] = {"waiting": [], "in_progress": [], "done": []}
    seen: set[str] = set()
    rows = [dict(o) for o in pool_orders]
    rows += [{"order_id": oid} for oid in sorted(statuses) if oid not in {r.get("order_id") for r in rows}]
    for row in rows:
        order_id = row.get("order_id")
        if not order_id or order_id in seen:
            continue
        seen.add(order_id)
        st = statuses.get(order_id)
        outcome = outcome_of(st["state"], st["reason"]) if st else None
        item = {"order_id": order_id, "patient_id": row.get("patient_id"), "item_id": row.get("item_id"),
                "bed": row.get("bed"), "group": row.get("group"), "label": row.get("label"), "mode": row.get("mode"),
                "request_id": (st or {}).get("request_id") or None, "outcome": outcome}
        if outcome in DONE_OUTCOMES:
            out["done"].append(item)
        elif st is not None or order_id in used:
            out["in_progress"].append(item)
        else:
            out["waiting"].append(item)
    return out
