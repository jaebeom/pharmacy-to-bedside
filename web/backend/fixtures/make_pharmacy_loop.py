"""mock 재생용 fixture 를 만든다. 손으로 JSON 을 고치지 말고 이 스크립트를 고쳐라.

한 편의 내용(작전 지시):
  조제실 한 바퀴(pharmacy_only) + 보충 + 리셋 1회 + 리셋 뒤 새 요청.

이벤트 이름과 순서는 Event.msg 상수와 rokey_p3_bringup/test 의 기대 순서를 따른다.
REQUEST_ACCEPTED.detail 은 **두 경우를 다 넣는다** — PR #104 이 실어 주는 compact JSON 과,
머지 전 빌드/옛 run 에서 나오는 빈 문자열.

    python3 fixtures/make_pharmacy_loop.py
"""

from __future__ import annotations

import json
from pathlib import Path

OUT = Path(__file__).with_name("pharmacy_loop.json")

# PR #104 이 detail 을 만드는 방식 그대로: 키 순서 고정, 공백 없음, 한글 원문
def detail_json(mode: int, destination_id: str, orders: list[dict]) -> str:
    return json.dumps(
        {"mode": mode, "destination_id": destination_id, "orders": orders},
        separators=(",", ":"), ensure_ascii=False,
    )


frames: list[dict] = []


def at(t: float, kind: str, **data) -> None:
    frames.append({"t": round(t, 3), "kind": kind, "data": data})


def event(t: float, name: str, *, epoch: int, request_id: str = "", order_id: str = "",
          robot_id: str = "", detail: str = "") -> None:
    at(t, "event", name=name, request_id=request_id, order_id=order_id,
       robot_id=robot_id, epoch=epoch, detail=detail, stamp=round(t, 3))


def order(t: float, request_id: str, order_id: str, state: int, reason: str = "") -> None:
    at(t, "order", request_id=request_id, order_id=order_id, state=state,
       reason=reason, stamp=round(t, 3))


def dispenser(t: float, *, paused: list[str], queue: int, belt_occupied: bool,
              ibu_count: int, ibu_active: bool) -> None:
    at(t, "dispenser", stamp=round(t, 3), paused_item_ids=paused, queue_length=queue,
       belt_occupied=belt_occupied, slots=[
           {"item_id": "drug-ibu", "slot": 0, "lot_id": "L-2409",
            "expiry": "2027-03-01", "count": ibu_count, "active": ibu_active},
           {"item_id": "drug-acet", "slot": 1, "lot_id": "L-2411",
            "expiry": "2027-06-30", "count": 7, "active": True},
       ])


def belt(t: float, *, occupied: bool, at_end: bool, order_id: str = "") -> None:
    at(t, "belt", stamp=round(t, 3), occupied=occupied, at_end=at_end, order_id=order_id)


def signal(t: float, key: str, value: bool) -> None:
    at(t, "signal", key=key, value=value, stamp=round(t, 3))


LOG_LEVELS = {"warn": 30, "error": 40, "fatal": 50}


def log(t: float, level: str, node: str, message: str) -> None:
    """/rosout 한 줄. WARN 이상만 넣는다 (api.md §5).

    **문구는 예시다.** 실물에서 이 문장이 그대로 나온다는 뜻이 아니다 — 프론트가 에러 로그
    탭을 실데이터로 그려 볼 수 있게 모양만 맞춘 것이다.
    """
    at(t, "log", level=level, level_value=LOG_LEVELS[level], node=node,
       message=message, stamp=round(t, 3))


# ── 0. 초기 상태 ─────────────────────────────────────────────────────────
E1 = 1
dispenser(0.0, paused=[], queue=0, belt_occupied=False, ibu_count=3, ibu_active=True)
belt(0.0, occupied=False, at_end=False)
for key, value in (("arm_at_home", True), ("base_stopped", True),
                   ("gripper_holding", False), ("m0609_at_home", True)):
    signal(0.0, key, value)

# ── 1. 조제실 한 바퀴 (pharmacy_only) — detail 이 있는 경우 (#104 머지 후) ──
# 주문 ID·환자·약품은 `src/rokey_p3_orchestrator/config/order_pool.yaml` 원문과 같은 것을 쓴다.
# 풀과 fixture 가 어긋나면 프론트가 "이미 쓴 주문" 을 잘못 판단한다.
R1, O1 = "req-0001", "ord-0001"
D1 = detail_json(0, "station_a", [
    {"order_id": O1, "patient_id": "1001", "item_id": "drug-amox"},
])
event(2.0, "REQUEST_ACCEPTED", epoch=E1, request_id=R1, order_id=O1, detail=D1)
order(2.0, R1, O1, 0)                                   # ACCEPTED
event(4.5, "AMR_DOCKED_LOAD", epoch=E1, request_id=R1, order_id=O1, robot_id="amr_1")
order(4.5, R1, O1, 1)                                   # IN_PROGRESS
signal(4.5, "base_stopped", True)

event(7.0, "DISPENSED", epoch=E1, request_id=R1, order_id=O1, robot_id="dispenser")
dispenser(7.0, paused=[], queue=0, belt_occupied=True, ibu_count=2, ibu_active=True)
belt(7.0, occupied=True, at_end=False, order_id=O1)

event(10.5, "POUCH_AT_END", epoch=E1, request_id=R1, order_id=O1, robot_id="dispenser")
belt(10.5, occupied=True, at_end=True, order_id=O1)

event(11.5, "PICK_ATTEMPT", epoch=E1, request_id=R1, order_id=O1, robot_id="amr_1")
signal(11.5, "arm_at_home", False)
event(13.0, "POUCH_PICKED", epoch=E1, request_id=R1, order_id=O1, robot_id="amr_1")
signal(13.0, "gripper_holding", True)
belt(13.0, occupied=False, at_end=False)
event(15.0, "POUCH_LOADED", epoch=E1, request_id=R1, order_id=O1, robot_id="amr_1")
signal(15.0, "gripper_holding", False)
event(15.5, "LOAD_DONE", epoch=E1, request_id=R1, order_id=O1, robot_id="amr_1")
event(17.0, "ARM_HOME", epoch=E1, request_id=R1, order_id=O1, robot_id="amr_1")
signal(17.0, "arm_at_home", True)

# pharmacy_only 는 LOAD_DONE 뒤 HOLD_RETURN/pharmacy_only 로 닫는다
order(18.0, R1, O1, 11, "pharmacy_only")                # HOLD_RETURN
event(18.0, "ORDER_DONE", epoch=E1, request_id=R1, order_id=O1, robot_id="amr_1")
event(20.0, "DOCKED", epoch=E1, request_id=R1, order_id=O1, robot_id="amr_1")

# ── 2. 보충 ──────────────────────────────────────────────────────────────
event(26.0, "DISPENSER_PAUSED", epoch=E1, robot_id="dispenser", detail="drug-ibu")
dispenser(26.0, paused=["drug-ibu"], queue=1, belt_occupied=False, ibu_count=0, ibu_active=False)
log(26.0, "warn", "orchestrator", "Dispense rejected: belt_occupied, retry 1/3")
event(26.5, "REFILL_REQUESTED", epoch=E1, robot_id="dispenser", detail="drug-ibu")
log(26.6, "warn", "isaac_adapter", "unknown dispense message pool_exhausted")
signal(28.0, "m0609_at_home", False)
event(54.5, "REFILL_DONE", epoch=E1, robot_id="m0609", detail="drug-ibu slot a")  # 약 28 sim s
log(48.0, "warn", "m0609_arm", "waypoint timeout after 12.0 s, re-planning")
signal(56.0, "m0609_at_home", True)
event(56.5, "DISPENSER_RESUMED", epoch=E1, robot_id="dispenser", detail="drug-ibu")
dispenser(56.5, paused=[], queue=0, belt_occupied=False, ibu_count=12, ibu_active=True)

# ── 3. 리셋 1회 ──────────────────────────────────────────────────────────
# 리셋은 타임라인을 Stop 하지 않는다 — sim_s 는 되감기지 않고 계속 흐른다.
# 세대 구분은 오직 epoch 이다.
E2 = E1 + 1
log(60.5, "error", "orchestrator",
    "deliver goal rejected: request_id 'req-0001' already used")
log(61.0, "warn", "m0609_arm", "waypoint timeout after 8.0 s, re-planning")
event(62.0, "RESET_BEGIN", epoch=E2)
log(62.1, "warn", "event_logger", "run closed mid-trip by reset, epoch -> 2")
event(64.0, "RESET_DONE", epoch=E2)

# ── 4. 리셋 뒤 새 요청 — detail 이 빈 경우 (#104 머지 전 빌드 / 옛 run) ────
R2, O2 = "req-0002", "ord-0002"
event(67.5, "REQUEST_ACCEPTED", epoch=E2, request_id=R2, order_id=O2, detail="")
order(67.5, R2, O2, 0)
event(70.0, "AMR_DOCKED_LOAD", epoch=E2, request_id=R2, order_id=O2, robot_id="amr_1")
order(70.0, R2, O2, 1)
event(72.5, "DISPENSED", epoch=E2, request_id=R2, order_id=O2, robot_id="dispenser")
dispenser(72.5, paused=[], queue=0, belt_occupied=True, ibu_count=11, ibu_active=True)
belt(72.5, occupied=True, at_end=False, order_id=O2)
event(76.0, "POUCH_AT_END", epoch=E2, request_id=R2, order_id=O2, robot_id="dispenser")
belt(76.0, occupied=True, at_end=True, order_id=O2)
event(77.0, "PICK_ATTEMPT", epoch=E2, request_id=R2, order_id=O2, robot_id="amr_1")
signal(77.0, "arm_at_home", False)
event(78.5, "POUCH_PICKED", epoch=E2, request_id=R2, order_id=O2, robot_id="amr_1")
signal(78.5, "gripper_holding", True)
belt(78.5, occupied=False, at_end=False)
event(80.5, "POUCH_LOADED", epoch=E2, request_id=R2, order_id=O2, robot_id="amr_1")
signal(80.5, "gripper_holding", False)
event(81.0, "LOAD_DONE", epoch=E2, request_id=R2, order_id=O2, robot_id="amr_1")
event(82.5, "ARM_HOME", epoch=E2, request_id=R2, order_id=O2, robot_id="amr_1")
signal(82.5, "arm_at_home", True)
order(83.5, R2, O2, 11, "pharmacy_only")
event(83.5, "ORDER_DONE", epoch=E2, request_id=R2, order_id=O2, robot_id="amr_1")
event(85.5, "DOCKED", epoch=E2, request_id=R2, order_id=O2, robot_id="amr_1")
log(85.8, "error", "fleet", "GoToZone rejected: zone 'bed_b2' not in zones.yaml")

frames.sort(key=lambda f: f["t"])

doc = {
    "name": "pharmacy_loop",
    "description": "조제실 한 바퀴(pharmacy_only) + 보충 + 리셋 1회 + 리셋 뒤 새 요청",
    "start_epoch": E1,
    "duration_sim_s": frames[-1]["t"],
    "notes": [
        "REQUEST_ACCEPTED.detail: req-0001 은 PR #104 형식 JSON, req-0002 는 빈 문자열.",
        "주문 ID 는 order_pool.yaml 원문과 같다 (ord-0001·ord-0002). 재생 뒤 ord-0003·ord-0004 가 미사용으로 남는다.",
        "/rosout WARN·ERROR 를 6줄 섞었다 — /api/logs 탭을 실데이터로 볼 수 있게.",
        "리셋은 타임라인을 Stop 하지 않아 sim_s 가 되감기지 않는다. 세대 구분은 epoch.",
    ],
    "frames": frames,
}
OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"{OUT} — 프레임 {len(frames)}개, {doc['duration_sim_s']} sim s")
