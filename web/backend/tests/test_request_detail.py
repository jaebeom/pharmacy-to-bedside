"""REQUEST_ACCEPTED.detail 파서 테스트. detail 은 신뢰할 수 없는 자유 문자열이다."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.request_detail import parse_request_detail

GOOD = json.dumps({
    "mode": 1,
    "destination_id": "bed_a1",
    "orders": [{"order_id": "ord-12", "patient_id": "p-7", "item_id": "drug-ibu"}],
}, separators=(",", ":"))


def test_parses_the_agreed_compact_json():
    got = parse_request_detail(GOOD)
    assert got["mode"] == 1
    assert got["mode_name"] == "MODE_URGENT"
    assert got["destination_id"] == "bed_a1"
    assert got["orders"]["ord-12"] == {"patient_id": "p-7", "item_id": "drug-ibu"}
    assert got["mode_source"] == "event_detail"


@pytest.mark.parametrize("mode,name", [
    (0, "MODE_SINGLE"), (1, "MODE_URGENT"), (2, "MODE_BATCH_ROOM"), (3, "MODE_BATCH_WARD"),
])
def test_all_four_modes_map_to_their_constant_name(mode, name):
    got = parse_request_detail(json.dumps({"mode": mode, "destination_id": "bed_a1"}))
    assert (got["mode"], got["mode_name"]) == (mode, name)


# ── 아직 머지 전이라 detail 이 비어 있는 것이 현재의 정상이다 ──────────────

@pytest.mark.parametrize("detail", ["", "   ", None])
def test_empty_detail_is_none_not_an_error(detail):
    assert parse_request_detail(detail) is None


@pytest.mark.parametrize("detail", [
    "그냥 사람이 읽는 메모",
    "{",
    "[1,2,3]",
    '"문자열"',
    "null",
    "42",
])
def test_anything_that_is_not_our_object_is_none(detail):
    assert parse_request_detail(detail) is None


def test_unknown_mode_number_is_dropped_not_guessed():
    got = parse_request_detail(json.dumps({"mode": 9, "destination_id": "bed_a1"}))
    assert got["mode"] is None and got["mode_name"] is None
    assert got["destination_id"] == "bed_a1"


def test_bool_is_not_accepted_as_a_mode():
    """파이썬에서 True 는 int 1 이다. 모드로 새어들면 안 된다."""
    got = parse_request_detail(json.dumps({"mode": True, "destination_id": "bed_a1"}))
    assert got["mode"] is None


def test_mode_as_a_string_is_dropped():
    got = parse_request_detail(json.dumps({"mode": "1", "destination_id": "bed_a1"}))
    assert got["mode"] is None


def test_partial_detail_still_yields_what_it_has():
    got = parse_request_detail(json.dumps({"destination_id": "room_a1"}))
    assert got["destination_id"] == "room_a1"
    assert got["mode"] is None and got["orders"] == {}


def test_orders_without_an_order_id_are_skipped():
    got = parse_request_detail(json.dumps({
        "mode": 0,
        "orders": [{"patient_id": "p-1"}, {"order_id": "ord-2", "item_id": "drug-x"}],
    }))
    assert list(got["orders"]) == ["ord-2"]


def test_missing_patient_and_item_become_null_not_empty_string():
    got = parse_request_detail(json.dumps({"mode": 0, "orders": [{"order_id": "ord-2"}]}))
    assert got["orders"]["ord-2"] == {"patient_id": None, "item_id": None}


def test_empty_strings_are_treated_as_missing():
    got = parse_request_detail(json.dumps({
        "mode": 0, "destination_id": "  ",
        "orders": [{"order_id": "ord-2", "patient_id": ""}],
    }))
    assert got["destination_id"] is None
    assert got["orders"]["ord-2"]["patient_id"] is None


def test_malformed_orders_field_does_not_raise():
    assert parse_request_detail(json.dumps({"mode": 0, "orders": "not a list"}))["orders"] == {}
    assert parse_request_detail(json.dumps({"mode": 0, "orders": [1, 2]}))["orders"] == {}


def test_an_object_with_nothing_useful_is_none():
    assert parse_request_detail(json.dumps({"unrelated": "x"})) is None


def test_parser_does_not_import_ros():
    import app.request_detail as mod
    src = Path(mod.__file__).read_text(encoding="utf-8")
    for banned in ("import rclpy", "from rclpy", "std_msgs"):
        assert banned not in src


# ── PR #104 이 싣는 실제 형식 ────────────────────────────────────────────

def emit_like_orchestrator(payload):
    """#104 가 detail 을 만드는 방식 그대로: 키 순서 고정, 공백 없음, 한글 원문."""
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=False)


def test_korean_text_survives_ensure_ascii_false():
    detail = emit_like_orchestrator({
        "mode": 2,
        "destination_id": "room_a1",
        "orders": [{"order_id": "ord-1", "patient_id": "김환자", "item_id": "이부프로펜"}],
    })
    assert "김환자" in detail, "orchestrator 는 ensure_ascii=False 로 낸다"
    got = parse_request_detail(detail)
    assert got["orders"]["ord-1"] == {"patient_id": "김환자", "item_id": "이부프로펜"}


def test_batch_detail_over_1000_chars_is_parsed_not_truncated():
    """병동 묶음은 detail 이 1000자를 넘을 수 있다. 자르지 말고 그대로 파싱한다."""
    orders = [
        {"order_id": f"ord-{i:03d}", "patient_id": f"환자{i:03d}", "item_id": "드러그-이부"}
        for i in range(40)
    ]
    detail = emit_like_orchestrator({"mode": 3, "destination_id": "station_a", "orders": orders})
    assert len(detail) > 1000, "이 테스트가 뜻이 있으려면 1000자를 넘겨야 한다"
    got = parse_request_detail(detail)
    assert got["mode"] == 3
    assert len(got["orders"]) == 40
    assert got["orders"]["ord-039"]["patient_id"] == "환자039"


def test_detail_with_no_whitespace_separators_parses():
    detail = emit_like_orchestrator({"mode": 1, "destination_id": "bed_a1", "orders": []})
    assert " " not in detail
    assert parse_request_detail(detail)["mode"] == 1


def test_pre_merge_build_yields_nulls_across_the_board():
    """#104 머지 전 빌드와 옛 run 은 detail 이 비어 있다. 그게 정상이고 오류가 아니다."""
    assert parse_request_detail("") is None


# ── 원문 발행기와 왕복 ────────────────────────────────────────────────────

def upstream_request_summary():
    """orchestrator 가 실제로 detail 을 만드는 그 함수를 가져온다.

    형식을 추측해서 테스트하면, 저쪽이 바꿨을 때 우리만 초록이고 실물에서 깨진다.
    `trip_fsm` 은 ROS 를 import 하지 않으므로 여기서 그냥 쓸 수 있다.
    """
    import sys

    for base in Path(__file__).resolve().parents:
        pkg = base / "src" / "rokey_p3_orchestrator"
        if (pkg / "rokey_p3_orchestrator" / "trip_fsm.py").is_file():
            if str(pkg) not in sys.path:
                sys.path.insert(0, str(pkg))
            from rokey_p3_orchestrator.trip_fsm import request_summary
            return request_summary
    pytest.skip("저장소 밖에서 돌고 있다 — 원문 발행기를 못 찾았다")


@pytest.mark.parametrize(("mode_key", "mode_value"), [
    ("single", 0), ("urgent", 1), ("batch_room", 2), ("batch_ward", 3),
])
def test_round_trip_with_the_real_emitter(mode_key, mode_value):
    request_summary = upstream_request_summary()
    detail = request_summary({
        "mode": mode_key,
        "destination_id": "bed_a1",
        "orders": [{"order_id": "ord-0001", "patient_id": "1001", "item_id": "drug-amox"}],
    })
    got = parse_request_detail(detail)
    assert got is not None, f"원문이 낸 detail 을 못 읽었다: {detail!r}"
    assert got["mode"] == mode_value
    assert got["destination_id"] == "bed_a1"
    assert got["orders"]["ord-0001"] == {"patient_id": "1001", "item_id": "drug-amox"}
    assert got["mode_source"] == "event_detail"


def test_the_real_emitter_fills_missing_ids_with_empty_strings():
    """원문은 빠진 값을 '' 로 채운다. 우리는 그것을 None 으로 읽어야 한다."""
    request_summary = upstream_request_summary()
    detail = request_summary({"mode": "single", "destination_id": "bed_a1",
                              "orders": [{"order_id": "ord-0001"}]})
    assert '"patient_id":""' in detail
    got = parse_request_detail(detail)
    assert got["orders"]["ord-0001"] == {"patient_id": None, "item_id": None}


def test_a_batch_from_the_real_emitter_survives():
    request_summary = upstream_request_summary()
    orders = [{"order_id": f"ord-{i:04d}", "patient_id": f"{1000 + i}",
               "item_id": "drug-amox"} for i in range(1, 41)]
    detail = request_summary({"mode": "batch_ward", "destination_id": "ward_a",
                              "orders": orders})
    assert len(detail) > 1000
    got = parse_request_detail(detail)
    assert got["mode"] == 3
    assert len(got["orders"]) == 40
