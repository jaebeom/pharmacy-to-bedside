"""`REFILL_DONE.detail` 파서. 장면 v2 의 JSON 과 v1 문자열을 함께 받는다.

`detail` 은 계약 2.6절에서 사람이 읽는 메모다. 어떤 입력에도 예외를 던지지 않아야 한다 —
장면이 바뀌는 중이고, 팔 노드가 무엇을 낼지 서버가 고를 수 없다.
"""

from __future__ import annotations

import json

import pytest

from app.refill_detail import FIELDS, KINDS, TARGETS, parse_refill_detail, refill_summary


def v2(**kw):
    """장면 v2 가 내는 방식 그대로: 키 순서 고정, 공백 없음, 한글 원문."""
    payload = {"item": "drug-amox", "slot": "a", "kind": "cylinder",
               "cell": "floor_left/r0c1", "target": "round",
               "seed": 0, "draw": 3, "clearance": 0.011}
    payload.update(kw)
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=False)


# ── v2 JSON ──────────────────────────────────────────────────────────────

def test_the_v2_shape_is_read_field_for_field():
    got = parse_refill_detail(v2())
    assert got == {"item": "drug-amox", "slot": "A", "kind": "cylinder",
                   "cell": "floor_left/r0c1", "target": "round",
                   "seed": 0, "draw": 3, "clearance": 0.011}


def test_no_whitespace_in_the_emitted_form():
    assert " " not in v2()


@pytest.mark.parametrize("kind", KINDS)
def test_every_documented_kind_passes(kind):
    assert parse_refill_detail(v2(kind=kind))["kind"] == kind


@pytest.mark.parametrize("target", TARGETS)
def test_every_documented_target_passes(target):
    assert parse_refill_detail(v2(target=target))["target"] == target


@pytest.mark.parametrize(("emitted", "expected"), [("a", "A"), ("b", "B"),
                                                   ("A", "A"), (" b ", "B")])
def test_the_slot_letter_is_normalised_to_upper_case(emitted, expected):
    """`dispenser.slots[].slot_name` 이 "A"/"B" 다.

    소문자로 두면 화면이 "방금 보충된 칸" 을 찾을 때 `"a" === "A"` 가 거짓이 되어
    **조용히 아무것도 강조되지 않는다.** 예외도 안 나고 화면도 안 깨져서 아무도 모른다.
    무엇이 실제로 왔는지는 `event.detail` 원문이 들고 있다.
    """
    assert parse_refill_detail(v2(slot=emitted))["slot"] == expected


def test_the_slot_matches_the_dispenser_slot_name_form():
    from app.state import WorldState

    assert WorldState  # 같은 형태인지는 아래 test_state 쪽에서 스냅샷으로 본다
    assert parse_refill_detail(v2(slot="a"))["slot"] in ("A", "B")


def test_a_korean_cell_name_survives():
    got = parse_refill_detail(v2(cell="왼쪽선반/r0c1"))
    assert got["cell"] == "왼쪽선반/r0c1"


# ── v1 문자열 — 파싱하지 않는다 ──────────────────────────────────────────

@pytest.mark.parametrize("detail", [
    "drug-amox slot a",
    "drug-amox slot a lot L-2409",
    "drug-ibu slot b",
])
def test_the_v1_string_is_not_parsed(detail):
    """v1 은 팔 노드 내부 문구이고 소비자를 위한 계약이 아니다. 원문은 event.detail 에 있다."""
    assert parse_refill_detail(detail) is None


@pytest.mark.parametrize("detail", ["", "   ", None])
def test_an_empty_detail_is_none(detail):
    assert parse_refill_detail(detail) is None


# ── 깨진 입력 ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("detail", [
    '{"item":"drug-amox",',          # 중간에 끊김
    "{",
    "[1,2,3]",                       # 우리 것이 아닌 JSON
    '"문자열"',
    "null",
    "42",
    "사람이 쓴 메모",
])
def test_broken_or_foreign_json_is_none_not_an_error(detail):
    assert parse_refill_detail(detail) is None


def test_json_that_has_none_of_our_keys_is_none():
    assert parse_refill_detail(json.dumps({"unrelated": "x"})) is None


# ── 모르는 값은 통과시키지 않는다 ────────────────────────────────────────

@pytest.mark.parametrize("kind", ["blob", "Cylinder", "", "cylinder2"])
def test_an_unknown_kind_becomes_null(kind):
    """계약에 없는 값을 내려보내면 화면이 그릴 수 없는 것을 받는다."""
    got = parse_refill_detail(v2(kind=kind))
    assert got["kind"] is None
    assert got["item"] == "drug-amox", "나머지 필드는 살아 있어야 한다"


@pytest.mark.parametrize("target", ["cabinet", "Round", ""])
def test_an_unknown_target_becomes_null(target):
    assert parse_refill_detail(v2(target=target))["target"] is None


@pytest.mark.parametrize("value", ["3", True, None, 1.5])
def test_a_non_integer_draw_becomes_null(value):
    assert parse_refill_detail(v2(draw=value))["draw"] is None


@pytest.mark.parametrize("value", ["0.011", True, None])
def test_a_non_number_clearance_becomes_null(value):
    assert parse_refill_detail(v2(clearance=value))["clearance"] is None


def test_surrounding_whitespace_is_forgiven():
    """JSON 발행기가 공백을 넣을 일은 없지만, 넣었다고 값을 버리지는 않는다."""
    assert parse_refill_detail(v2(kind=" cylinder "))["kind"] == "cylinder"


def test_an_integer_clearance_is_accepted_as_a_number():
    assert parse_refill_detail(v2(clearance=0))["clearance"] == 0.0


# ── 요약 ─────────────────────────────────────────────────────────────────

def test_the_summary_marks_parsed_and_carries_the_fields():
    got = refill_summary(v2(), stamp=54.5)
    assert got["parsed"] is True
    assert got["stamp"] == 54.5
    assert got["item"] == "drug-amox"
    assert set(got) == {"stamp", "parsed", *FIELDS}


def test_the_summary_marks_unparsed_with_every_field_null():
    got = refill_summary("drug-amox slot a", stamp=54.5)
    assert got["parsed"] is False
    assert got["stamp"] == 54.5
    assert all(got[f] is None for f in FIELDS)
    assert set(got) == {"stamp", "parsed", *FIELDS}


def test_parsed_is_a_boolean_not_a_version_string():
    """장면 버전이 아니다 — 서버는 장면 버전을 모른다."""
    for detail in (v2(), "drug-amox slot a", "", None):
        assert isinstance(refill_summary(detail, 1.0)["parsed"], bool)


def test_both_formats_produce_the_same_key_set():
    """화면이 형식마다 다른 키를 다루지 않게 한다."""
    assert set(refill_summary(v2(), 1.0)) == set(refill_summary("drug-amox slot a", 1.0))


def test_the_parser_does_not_import_ros():
    from pathlib import Path

    import app.refill_detail as mod
    src = Path(mod.__file__).read_text(encoding="utf-8")
    for banned in ("import rclpy", "from rclpy", "std_msgs", "rokey_p3_interfaces"):
        assert banned not in src
