"""촬영 화면 — snapshot.stage(일곱 단계)와 GET /api/queue(대기·진행·완료)."""

from __future__ import annotations

import json

import pytest

from app.alarms import outcome_for
from app.film import STAGES, queue_rows, stage_for
from tests.test_api import T0, make_client, seed


@pytest.fixture
def client_state():
    client, state = make_client()
    with client:
        yield client, state

# ── 단계 규칙 ────────────────────────────────────────────────────────────


@pytest.mark.parametrize(("phase", "departed", "key"), [
    ("accepted", False, "request"),
    ("docked_load", False, "dispense"), ("dispensing", False, "dispense"),
    ("loading", False, "pick"), ("load_done", False, "pick"), ("arm_home", False, "pick"),
    ("moving", True, "deliver"), ("arriving", True, "deliver"),
    ("arrived", True, "arrive"), ("auth", True, "arrive"), ("unloading", True, "arrive"),
    ("locked", True, "arrive"), ("order_done", True, "arrive"), ("arm_home", True, "arrive"),
    ("returning", True, "return"),
    ("docked", True, "idle"), (None, False, "idle"),
])
def test_phase_maps_to_stage(phase, departed, key):
    assert stage_for(phase, departed=departed)["key"] == key


def test_stage_labels_and_index_follow_the_card_order():
    assert [label for _, label in STAGES] == ["요청", "보충", "조제", "집기", "배송", "도착", "복귀"]
    s = stage_for("moving", departed=True)
    assert (s["label"], s["index"], s["phase"]) == ("배송", 4, "moving")
    assert stage_for(None, departed=False)["index"] is None


def test_refill_takes_over_only_before_dispense_and_only_for_the_trips_item():
    assert stage_for("accepted", departed=False, trip_items=["drug-amox"],
                     blocked_items=["drug-amox"])["key"] == "refill"
    s = stage_for("dispensing", departed=False, trip_items=["drug-amox", "drug-ibu"], blocked_items=["drug-ibu"])
    assert (s["key"], s["refill_item_ids"]) == ("refill", ["drug-ibu"])
    # 다른 약품의 보충, 약품을 모름, 이미 집기 뒤 — 가로채지 않는다
    other = stage_for("accepted", departed=False, trip_items=["drug-amox"], blocked_items=["drug-ibu"])
    assert other["key"] == "request"
    assert stage_for("accepted", departed=False, trip_items=[], blocked_items=["drug-ibu"])["key"] == "request"
    assert stage_for("loading", departed=False, trip_items=["drug-amox"], blocked_items=["drug-amox"])["key"] == "pick"


def test_reset_wins():
    assert stage_for("moving", departed=True, reset=True)["key"] == "reset"


# ── snapshot.stage 배선 ──────────────────────────────────────────────────

def accepted_detail(mode=0, destination="bed_a1", orders=(("ord-0001", "1001", "drug-amox"),)):
    return json.dumps({"mode": mode, "destination_id": destination,
                       "orders": [{"order_id": o, "patient_id": p, "item_id": i} for o, p, i in orders]})


def test_snapshot_stage_follows_a_trip(client_state):
    client, state = client_state
    stage = lambda: client.get("/api/snapshot").json()["stage"]["key"]  # noqa: E731
    assert stage() == "idle"
    seed(state, "REQUEST_ACCEPTED", 1.0, request_id="r1", detail=accepted_detail())
    assert stage() == "request"
    for name, stamp, want in [("AMR_DOCKED_LOAD", 2.0, "dispense"), ("POUCH_LOADED", 3.0, "pick"),
                              ("LOAD_DONE", 3.5, "pick"), ("ARM_HOME", 4.0, "pick"), ("DEPARTED", 5.0, "deliver"),
                              ("ARRIVED", 6.0, "arrive"), ("ORDER_DONE", 7.0, "arrive"), ("ARM_HOME", 7.5, "arrive"),
                              ("RETURNED", 8.0, "return"), ("DOCKED", 9.0, "idle")]:
        seed(state, name, stamp, request_id="r1")
        assert stage() == want, name


def test_snapshot_stage_is_refill_while_the_trips_item_is_paused(client_state):
    client, state = client_state
    seed(state, "REQUEST_ACCEPTED", 1.0, request_id="r1", detail=accepted_detail())
    state.note_dispenser({"stamp": 1.0, "paused_item_ids": ["drug-amox"], "queue_length": 0,
                          "belt_occupied": False, "slots": []}, T0)
    s = client.get("/api/snapshot").json()["stage"]
    assert (s["key"], s["label"], s["refill_item_ids"]) == ("refill", "보충", ["drug-amox"])


# ── 주문 큐 ──────────────────────────────────────────────────────────────

def test_queue_rows_split_by_status_and_keep_pool_order():
    pool = [{"order_id": f"ord-000{n}", "bed": f"bed_a{n}"} for n in (1, 2, 3, 4)]
    statuses = {"ord-0001": {"request_id": "r1", "state": 2, "reason": ""},
                "ord-0002": {"request_id": "r2", "state": 1, "reason": ""},
                "ord-0009": {"request_id": "r9", "state": 11, "reason": "tag_unreadable"}}
    rows = queue_rows(pool, statuses, used={"ord-0001", "ord-0002", "ord-0003"}, outcome_of=outcome_for)
    assert [r["order_id"] for r in rows["done"]] == ["ord-0001", "ord-0009"], "풀 밖 주문도 빼지 않는다"
    assert [r["order_id"] for r in rows["in_progress"]] == ["ord-0002", "ord-0003"], "쓰였는데 상태 없음 = 진행"
    assert [r["order_id"] for r in rows["waiting"]] == ["ord-0004"]
    assert rows["done"][1]["outcome"] == "held"


def test_queue_endpoint_uses_the_pool_and_zone_labels(tmp_path):
    pool = tmp_path / "pool.yaml"
    pool.write_text("version: 1\norders:\n"
                    '  - {order_id: ord-0001, patient_id: "2001", item_id: drug-amox, bed: bed_a1}\n'
                    '  - {order_id: ord-0005, patient_id: "2005", item_id: drug-amox, bed: bed_b1}\n', encoding="utf-8")
    zones = tmp_path / "zones.yaml"
    zones.write_text("frame: map\nzones:\n  bed_a1:\n    kind: bed\n    room: C1\n    label: D1\n"
                     "  bed_b1:\n    kind: bed\n    room: C2\n    label: D5\n", encoding="utf-8")
    client, state = make_client(order_pool=str(pool), zones_file=str(zones))
    with client:
        seed(state, "REQUEST_ACCEPTED", 1.0, request_id="r1", detail=accepted_detail())
        body = client.get("/api/queue").json()
    assert body["counts"] == {"waiting": 1, "in_progress": 1, "done": 0}
    assert (body["in_progress"][0]["order_id"], body["in_progress"][0]["label"]) == ("ord-0001", "D1")
    assert (body["waiting"][0]["group"], body["waiting"][0]["label"]) == ("C2", "D5")


def test_a_pause_after_the_trips_pouch_is_dispensed_is_not_refill(client_state):
    """마지막 재고를 조제하는 순간 약품이 PAUSED 가 된다. 이 트립의 봉투는 이미 나왔으니 조제다."""
    client, state = client_state
    seed(state, "REQUEST_ACCEPTED", 1.0, request_id="r1", detail=accepted_detail())
    seed(state, "AMR_DOCKED_LOAD", 2.0, request_id="r1")
    seed(state, "DISPENSED", 2.1, request_id="r1", order_id="ord-0001")
    state.note_dispenser({"stamp": 2.1, "paused_item_ids": ["drug-amox"], "queue_length": 0,
                          "belt_occupied": True, "slots": []}, T0)
    assert client.get("/api/snapshot").json()["stage"]["key"] == "dispense"


def test_a_batch_waits_on_refill_only_for_the_orders_not_yet_dispensed(client_state):
    client, state = client_state
    detail = accepted_detail(mode=2, orders=(("ord-0001", "1001", "drug-amox"), ("ord-0003", "1003", "drug-ibu")))
    seed(state, "REQUEST_ACCEPTED", 1.0, request_id="r1", detail=detail)
    seed(state, "DISPENSED", 2.1, request_id="r1", order_id="ord-0001")
    state.note_dispenser({"stamp": 2.1, "paused_item_ids": ["drug-amox", "drug-ibu"], "queue_length": 0,
                          "belt_occupied": True, "slots": []}, T0)
    s = client.get("/api/snapshot").json()["stage"]
    assert (s["key"], s["refill_item_ids"]) == ("refill", ["drug-ibu"])
