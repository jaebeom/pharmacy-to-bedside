"""관제 전 과정 점검표(프론트 4372934)의 백엔드 필드 셋 — 보충 중 대상·약통 QR 판독·도킹.

오케스트레이터·인터페이스는 바꾸지 않는다. 기존 토픽(`/events`, `/pharmacy/dispenser/status`,
`/m0609/shelf/inventory`, `/m0609/hand_camera/tag_reads`)만으로 만든다.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.refill_detail import parse_shelf_kinds, refill_target
from app.ros_convert import string_data, tag_read_to_dict
from app.ros_spec import apply_update, subscriptions
from app.state import WorldState

NOW = datetime(2026, 9, 24, 20, 0, 0, tzinfo=timezone.utc)

SHELF = json.dumps({
    "scene": "v2",
    "items": {"drug-amox": "cylinder"},
    "cells": [
        {"cell": "floor_left/r0c0", "type": "cylinder", "item": "drug-amox"},
        {"cell": "floor_left/r0c1", "type": "module", "item": "drug-ibu"},
        {"cell": "floor_left/r0c2", "type": "tablet", "item": "drug-odd"},
    ],
})


def event(state, name, *, robot_id="amr_1", epoch=1, stamp=1.0, request_id="r001-0001"):
    state.note_event({"name": name, "epoch": epoch, "stamp": stamp, "robot_id": robot_id,
                      "request_id": request_id, "order_id": "", "detail": ""}, NOW)


def dispenser(state, slots, paused=()):
    state.note_dispenser({"slots": slots, "paused_item_ids": list(paused), "queue_length": 0,
                          "belt_occupied": False, "stamp": 1.0}, NOW)


def slot(item, index, count):
    return {"item_id": item, "slot": index, "lot_id": "", "expiry": "", "count": count, "active": False}


# ── ① 보충 중 대상 ─────────────────────────────────────────────────────

def test_shelf_kinds_come_from_the_items_table_then_the_cells():
    assert parse_shelf_kinds(SHELF) == {"drug-amox": "cylinder", "drug-ibu": "module"}


def test_a_shelf_message_that_is_not_scene_v2_is_ignored():
    for text in ("", "not json", "[]", json.dumps({"scene": "v1", "cells": []}), None):
        assert parse_shelf_kinds(text) is None
    state = WorldState()
    state.note_shelf(SHELF)
    state.note_shelf("garbage")
    assert state.shelf_kinds == {"drug-amox": "cylinder", "drug-ibu": "module"}


def test_the_target_slot_is_the_first_empty_one_like_the_refill_planner():
    kinds = {"drug-ibu": "module"}
    both = [slot("drug-ibu", 0, 0), slot("drug-ibu", 1, 0)]
    only_b = [slot("drug-ibu", 0, 3), slot("drug-ibu", 1, 0)]
    assert refill_target("drug-ibu", both, kinds)["slot_name"] == "A"
    assert refill_target("drug-ibu", only_b, kinds) == {
        "item_id": "drug-ibu", "slot_name": "B", "kind": "module", "target": "module"}
    assert refill_target("drug-ibu", [slot("drug-ibu", 0, 3)], {}) == {
        "item_id": "drug-ibu", "slot_name": None, "kind": None, "target": None}


def test_refill_targets_follow_the_open_refill_request():
    state = WorldState()
    state.note_shelf(SHELF)
    dispenser(state, [slot("drug-amox", 0, 0), slot("drug-amox", 1, 0)], paused=["drug-amox"])
    assert state.snapshot(NOW)["dispenser"]["refill_targets"] == []   # 요청 전
    event(state, "REFILL_REQUESTED", robot_id="dispenser")
    assert state.snapshot(NOW)["dispenser"]["refill_targets"] == [
        {"item_id": "drug-amox", "slot_name": "A", "kind": "cylinder", "target": "round"}]
    event(state, "REFILL_DONE", robot_id="m0609", stamp=2.0)
    assert state.snapshot(NOW)["dispenser"]["refill_targets"] == []


# ── ② 약통 QR 판독 ─────────────────────────────────────────────────────

def test_only_container_reads_are_kept():
    state = WorldState()
    dispenser(state, [])
    state.note_tag_read({"kind": 0, "tag_id": "pt-1001", "status": 0, "stamp": 1.0}, NOW)
    assert state.snapshot(NOW)["dispenser"]["container_read"] is None
    state.note_tag_read({"kind": 3, "tag_id": "cn-0007", "status": 0, "stamp": 5.0}, NOW)
    state.note_tag_read({"kind": 4, "tag_id": "md-0001", "status": 0, "stamp": 6.0}, NOW)
    read = state.snapshot(NOW + timedelta(seconds=2))["dispenser"]["container_read"]
    assert read == {"tag_id": "cn-0007", "status": "ok", "stamp": 5.0,
                    "wall": "2026-09-24T20:00:00.000Z", "age_wall_s": 2.0}


def test_an_unreadable_container_read_says_so_and_a_reset_clears_it():
    state = WorldState()
    dispenser(state, [])
    state.note_tag_read({"kind": 3, "tag_id": "", "status": 1, "stamp": 5.0}, NOW)
    assert state.snapshot(NOW)["dispenser"]["container_read"]["status"] == "unreadable"
    event(state, "RESET_BEGIN", epoch=2)
    assert state.snapshot(NOW)["dispenser"]["container_read"] is None


# ── ③ 도킹 ─────────────────────────────────────────────────────────────

def docked(state):
    return state.snapshot(NOW)["robots"][0]["docked"]


def test_docked_follows_the_last_event_of_that_amr():
    state = WorldState()
    state.note_robot_pose("amr_1", {"x": 0.0, "y": 0.0, "yaw": 0.0}, NOW)
    assert docked(state) is None                                  # 이벤트가 없다 — 모른다
    event(state, "RESET_DONE", stamp=0.5)
    assert docked(state) is True                                  # 리셋은 도크 자세로 되돌린다
    event(state, "REQUEST_ACCEPTED", stamp=1.0)
    assert docked(state) is False
    event(state, "DISPENSED", robot_id="dispenser", stamp=2.0)    # 다른 로봇의 이벤트는 안 본다
    event(state, "RETURNED", stamp=3.0)
    assert docked(state) is False
    event(state, "DOCKED", stamp=4.0)
    assert docked(state) is True
    event(state, "DISPENSER_PAUSED", robot_id="dispenser", stamp=5.0)
    assert docked(state) is True


def test_a_trip_that_ends_without_docked_stays_undocked_and_a_new_epoch_forgets_it():
    state = WorldState()
    state.note_robot_pose("amr_1", {"x": 0.0, "y": 0.0, "yaw": 0.0}, NOW)
    event(state, "REQUEST_ACCEPTED", stamp=1.0)
    event(state, "RETURNED", stamp=2.0)                           # 복귀 실패 — DOCKED 없이 끝
    assert docked(state) is False
    event(state, "RESET_BEGIN", epoch=2, robot_id="", stamp=3.0)
    assert docked(state) is None
    event(state, "RESET_DONE", epoch=2, stamp=3.5)
    assert docked(state) is True


# ── 배선 ──────────────────────────────────────────────────────────────

def test_the_two_m0609_topics_are_subscribed_with_the_publishers_qos():
    subs = {s.topic: s for s in subscriptions("amr_1")}
    shelf = subs["/m0609/shelf/inventory"]
    assert (shelf.kind, shelf.msg, shelf.qos, shelf.depth) == ("shelf", "String", "latched_qos", 1)
    reads = subs["/m0609/hand_camera/tag_reads"]
    assert (reads.kind, reads.msg, reads.qos) == ("tag_read", "TagRead", "reliable_qos")


def test_converted_messages_reach_the_snapshot():
    msg = SimpleNamespace(kind=3, tag_id="cn-0003", status=0,
                          header=SimpleNamespace(stamp=SimpleNamespace(sec=7, nanosec=0)))
    state = WorldState()
    dispenser(state, [slot("drug-ibu", 0, 0)])
    apply_update(state, "shelf", string_data(SimpleNamespace(data=SHELF)), NOW)
    apply_update(state, "tag_read", tag_read_to_dict(msg), NOW)
    assert state.shelf_kinds["drug-ibu"] == "module"
    assert state.snapshot(NOW)["dispenser"]["container_read"]["tag_id"] == "cn-0003"
