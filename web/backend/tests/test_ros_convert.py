"""ROS 메시지 → dict 변환 테스트. **ROS 없이 돈다** — 가짜 msg 를 duck typing 으로 넣는다.

진짜 msg 객체 대신 SimpleNamespace 를 쓰는 이유: 변환기가 `getattr` 만 쓰도록 강제하면
실물 브리지 없이도 파이프라인 전체(state → alarms → snapshot)를 여기서 시험할 수 있다.
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace as NS

import pytest

from app.ros_convert import (
    belt_state_to_dict,
    bool_value,
    cabinet_observation_to_dict,
    clock_to_seconds,
    delivery_request_to_dict,
    dispenser_status_to_dict,
    event_to_dict,
    header_stamp,
    log_to_dict,
    order_status_to_dict,
    time_to_seconds,
)
from app.state import WorldState

T0 = datetime(2026, 9, 17, 8, 0, 0, tzinfo=timezone.utc)


def stamp(sec, nanosec=0):
    return NS(header=NS(stamp=NS(sec=sec, nanosec=nanosec)))


def fake_event(*, sec=183, ns=900000000, **kw):
    fields = {"name": "ARRIVED", "request_id": "req-1", "order_id": "ord-1",
              "robot_id": "amr_1", "epoch": 3, "detail": "", **kw}
    return NS(**fields, header=NS(stamp=NS(sec=sec, nanosec=ns)))


# ── 시각 ─────────────────────────────────────────────────────────────────

def test_time_combines_seconds_and_nanoseconds():
    assert time_to_seconds(NS(sec=183, nanosec=900000000)) == pytest.approx(183.9)


def test_a_missing_time_is_zero_not_a_crash():
    assert time_to_seconds(None) == 0.0
    assert header_stamp(NS()) == 0.0


def test_clock_reads_the_nested_clock_field():
    assert clock_to_seconds(NS(clock=NS(sec=12, nanosec=500000000))) == pytest.approx(12.5)


# ── Event ────────────────────────────────────────────────────────────────

def test_event_maps_every_documented_field():
    got = event_to_dict(fake_event())
    assert got == {"name": "ARRIVED", "request_id": "req-1", "order_id": "ord-1",
                   "robot_id": "amr_1", "epoch": 3, "detail": "",
                   "stamp": pytest.approx(183.9)}


def test_event_keeps_detail_verbatim_without_parsing_it():
    detail = '{"mode":1,"destination_id":"bed_a1"}'
    assert event_to_dict(fake_event(detail=detail))["detail"] == detail


def test_empty_string_fields_stay_empty_strings_not_none():
    got = event_to_dict(NS(name="DOCKED", header=NS(stamp=NS(sec=1, nanosec=0))))
    assert got["request_id"] == "" and got["robot_id"] == ""


def test_korean_detail_survives_conversion():
    assert event_to_dict(fake_event(detail="환자 김씨"))["detail"] == "환자 김씨"


# ── OrderStatus ──────────────────────────────────────────────────────────

def test_order_status_maps_state_and_reason():
    msg = NS(request_id="req-1", order_id="ord-1", state=11, reason="pharmacy_only",
             header=NS(stamp=NS(sec=18, nanosec=0)))
    assert order_status_to_dict(msg) == {
        "request_id": "req-1", "order_id": "ord-1", "state": 11,
        "reason": "pharmacy_only", "stamp": 18.0}


# ── DispenserStatus ──────────────────────────────────────────────────────

def test_dispenser_maps_slots_and_paused_items():
    msg = NS(
        slots=[NS(item_id="drug-ibu", slot=0, lot_id="L-2409", expiry="2027-03-01",
                  count=0, active=False)],
        paused_item_ids=["drug-ibu"], queue_length=2, belt_occupied=False,
        header=NS(stamp=NS(sec=26, nanosec=0)))
    got = dispenser_status_to_dict(msg)
    assert got["paused_item_ids"] == ["drug-ibu"]
    assert got["queue_length"] == 2
    assert got["slots"][0]["slot"] == 0 and got["slots"][0]["active"] is False


def test_dispenser_slot_does_not_invent_a_capacity():
    msg = NS(slots=[NS(item_id="drug-ibu", slot=1, lot_id="L", expiry="2027-01-01",
                       count=7, active=True)],
             paused_item_ids=[], queue_length=0, belt_occupied=False,
             header=NS(stamp=NS(sec=0, nanosec=0)))
    assert "capacity" not in dispenser_status_to_dict(msg)["slots"][0]


def test_an_empty_dispenser_does_not_crash():
    got = dispenser_status_to_dict(NS(header=NS(stamp=NS(sec=0, nanosec=0))))
    assert got["slots"] == [] and got["paused_item_ids"] == []


# ── BeltState · Bool · Cabinet ───────────────────────────────────────────

def test_belt_maps_its_three_flags():
    msg = NS(occupied=True, at_end=True, order_id="ord-1",
             header=NS(stamp=NS(sec=10, nanosec=500000000)))
    got = belt_state_to_dict(msg)
    assert (got["occupied"], got["at_end"], got["order_id"]) == (True, True, "ord-1")


def test_bool_message_reads_the_data_field():
    assert bool_value(NS(data=True)) is True
    assert bool_value(NS()) is False


def test_cabinet_observation_maps_its_three_fields():
    msg = NS(order_id="ord-1", cabinet_id="bed_a1", present=True,
             header=NS(stamp=NS(sec=1, nanosec=0)))
    got = cabinet_observation_to_dict(msg)
    assert (got["order_id"], got["cabinet_id"], got["present"]) == ("ord-1", "bed_a1", True)


# ── DeliveryRequest (액션 goal — 토픽에 안 나온다) ────────────────────────

def test_delivery_request_maps_mode_and_orders():
    msg = NS(request_id="web-1", mode=3, destination_id="room_a1",
             orders=[NS(order_id="ord-1", patient_id="김환자", item_id="drug-ibu")])
    got = delivery_request_to_dict(msg)
    assert got["mode"] == 3
    assert got["orders"][0] == {"order_id": "ord-1", "patient_id": "김환자",
                                "item_id": "drug-ibu"}


def test_an_order_without_patient_or_item_yields_null_not_empty_string():
    msg = NS(request_id="web-1", mode=0, destination_id="bed_a1",
             orders=[NS(order_id="ord-1")])
    assert delivery_request_to_dict(msg)["orders"][0] == {
        "order_id": "ord-1", "patient_id": None, "item_id": None}


# ── rosout ───────────────────────────────────────────────────────────────

def test_log_maps_node_name_and_level():
    msg = NS(level=40, name="orchestrator", msg="deliver goal rejected",
             stamp=NS(sec=181, nanosec=0))
    assert log_to_dict(msg) == {"level": "error", "level_value": 40, "node": "orchestrator",
                                "message": "deliver goal rejected", "stamp": 181.0}


@pytest.mark.parametrize(("value", "name"),
                         [(10, "debug"), (20, "info"), (30, "warn"), (40, "error"), (50, "fatal")])
def test_every_log_level_gets_its_name(value, name):
    assert log_to_dict(NS(level=value, name="n", msg="m", stamp=NS(sec=0, nanosec=0)))["level"] \
        == name


def test_an_unknown_log_level_keeps_its_number():
    assert log_to_dict(NS(level=99, name="n", msg="m", stamp=NS(sec=0, nanosec=0)))["level"] == "99"


# ── 파이프라인 전체를 ROS 없이 통과시킨다 ─────────────────────────────────

def test_converted_messages_flow_all_the_way_into_a_snapshot():
    """가짜 msg → 변환 → WorldState → snapshot. 실물 브리지가 붙기 전에 배선을 증명한다."""
    state = WorldState()
    state.note_clock(clock_to_seconds(NS(clock=NS(sec=183, nanosec=900000000))), T0)
    state.note_event(event_to_dict(fake_event(name="REQUEST_ACCEPTED", epoch=1)), T0)
    state.note_order(order_status_to_dict(
        NS(request_id="req-1", order_id="ord-1", state=1, reason="",
           header=NS(stamp=NS(sec=4, nanosec=0)))))
    state.note_dispenser(dispenser_status_to_dict(
        NS(slots=[], paused_item_ids=["drug-ibu"], queue_length=1, belt_occupied=False,
           header=NS(stamp=NS(sec=26, nanosec=0)))), T0)
    state.note_belt(belt_state_to_dict(
        NS(occupied=True, at_end=False, order_id="ord-1",
           header=NS(stamp=NS(sec=7, nanosec=0)))), T0)
    state.note_signal("arm_at_home", bool_value(NS(data=True)), T0)

    snap = state.snapshot(T0)
    assert snap["epoch"] == 1
    assert snap["trip"]["request_id"] == "req-1"
    assert snap["trip"]["orders"][0]["state_name"] == "IN_PROGRESS"
    assert snap["dispenser"]["paused"] is True
    assert snap["signals"]["arm_at_home"]["value"] is True
    assert {a["kind"] for a in snap["alarms"]} == {"DISPENSER_PAUSED"}


def test_the_converter_does_not_import_ros():
    from pathlib import Path

    import app.ros_convert as mod
    src = Path(mod.__file__).read_text(encoding="utf-8")
    for banned in ("import rclpy", "from rclpy", "rokey_p3_interfaces", "std_msgs", "rosgraph"):
        assert f"\n{banned}" not in src, f"변환기에 {banned} 가 있으면 안 된다"
