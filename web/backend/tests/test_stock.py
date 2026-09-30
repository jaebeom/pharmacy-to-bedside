"""조제실 재고 한눈에(api.md §6.1 `dispenser.stock`, 재범 9/29 N3 "현재 알약통 N개·모듈 N개·지금 조제기에 N개")."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from app.refill_detail import parse_shelf_stock
from app.state import WorldState

NOW = datetime(2026, 9, 29, 3, 0, 0, tzinfo=timezone.utc)


def inventory(present_by_cell: dict[str, tuple[str, bool]]) -> str:
    return json.dumps({"v": 1, "scene": "v2", "items": {"drug-amox": "cylinder", "drug-ibu": "module"},
                       "cells": [{"cell": c, "type": t, "present": p} for c, (t, p) in present_by_cell.items()]})


def test_shelf_counts_present_cells_per_kind():
    text = inventory({"s1/r0c0": ("cylinder", True), "s1/r0c1": ("module", True),
                      "s2/r0c0": ("cylinder", False), "s2/r0c1": ("module", True), "odd": ("box", True)})
    assert parse_shelf_stock(text) == {"cylinder": {"present": 1, "total": 2}, "module": {"present": 2, "total": 2}}


def test_broken_or_non_v2_inventory_is_ignored():
    assert parse_shelf_stock(None) is None
    assert parse_shelf_stock("not json") is None
    assert parse_shelf_stock(json.dumps({"scene": "v1", "cells": []})) is None


def test_the_snapshot_stock_joins_shelf_dispenser_and_refills():
    s = WorldState()
    s.note_shelf(inventory({"a": ("cylinder", True), "b": ("cylinder", False), "c": ("module", True)}))
    s.note_dispenser({"slots": [{"item_id": "drug-amox", "slot": 0, "count": 2},
                                {"item_id": "drug-amox", "slot": 1, "count": 0},
                                {"item_id": "drug-ibu", "slot": 0, "count": 5}],
                      "paused_item_ids": [], "queue_length": 0, "belt_occupied": False, "stamp": 1.0}, NOW)
    s.note_event({"name": "REFILL_DONE", "epoch": 0, "stamp": 3.0,
                  "detail": json.dumps({"item": "drug-amox", "slot": "a", "kind": "cylinder", "cell": "b"})}, NOW)
    stock = s.snapshot(NOW)["dispenser"]["stock"]
    assert stock == {"shelf": {"cylinder": {"present": 1, "total": 2}, "module": {"present": 1, "total": 1}},
                     "canisters_loaded": 2, "pouches_by_item": {"drug-amox": 2, "drug-ibu": 5},
                     "refills": {"cylinder": 1, "module": 0}}


def test_without_a_shelf_inventory_the_shelf_is_null():
    s = WorldState()
    s.note_dispenser({"slots": [], "paused_item_ids": [], "queue_length": 0, "belt_occupied": False,
                      "stamp": 1.0}, NOW)
    assert s.snapshot(NOW)["dispenser"]["stock"]["shelf"] is None
