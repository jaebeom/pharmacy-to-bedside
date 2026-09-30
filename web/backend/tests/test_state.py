"""snapshot 조립 테스트 (api.md §1). ROS 없이 돈다."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from app.state import WorldState

T0 = datetime(2026, 9, 17, 8, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def state():
    s = WorldState()
    s.note_clock(0.0, T0)
    return s


def ev(state, name, stamp, wall=T0, **kw):
    return state.note_event({"name": name, "stamp": stamp, "epoch": kw.pop("epoch", 1), **kw}, wall)


DETAIL = json.dumps(
    {"mode": 1, "destination_id": "bed_a1",
     "orders": [{"order_id": "ord-1", "patient_id": "김환자", "item_id": "drug-ibu"}]},
    separators=(",", ":"), ensure_ascii=False)


# ── seq 와 커서 ──────────────────────────────────────────────────────────

def test_seq_starts_at_one_and_increases_by_one(state):
    assert [ev(state, "DEPARTED", float(i))["seq"] for i in range(3)] == [1, 2, 3]


def test_events_since_is_exclusive(state):
    for i in range(5):
        ev(state, "DEPARTED", float(i))
    page, _cursor, _more = state.events_for(1, since=2, limit=10)
    assert [e["seq"] for e in page] == [3, 4, 5]


def test_events_can_be_filtered_to_one_epoch(state):
    ev(state, "DEPARTED", 1.0, epoch=1)
    ev(state, "RESET_BEGIN", 2.0, epoch=2)
    ev(state, "DEPARTED", 3.0, epoch=2)
    assert len(state.events_for(2, since=0, limit=10)[0]) == 2
    assert len(state.events_for(None, since=0, limit=10)[0]) == 3


def test_event_buffer_drops_the_oldest_not_the_newest():
    s = WorldState(event_buffer=3)
    for i in range(5):
        s.note_event({"name": "DEPARTED", "stamp": float(i), "epoch": 1}, T0)
    assert [e["seq"] for e in s.events] == [3, 4, 5]


# ── 트립 ─────────────────────────────────────────────────────────────────

def test_no_trip_before_any_request(state):
    assert state.snapshot(T0)["trip"] is None


def test_trip_opens_on_request_accepted(state):
    ev(state, "REQUEST_ACCEPTED", 2.0, request_id="req-1", detail=DETAIL)
    trip = state.snapshot(T0)["trip"]
    assert trip["request_id"] == "req-1"
    assert trip["phase"] == "accepted"


def test_trip_closes_on_docked(state):
    ev(state, "REQUEST_ACCEPTED", 2.0, request_id="req-1", detail=DETAIL)
    ev(state, "DOCKED", 20.0, request_id="req-1")
    assert state.snapshot(T0)["trip"] is None


def test_detail_fills_mode_and_destination(state):
    ev(state, "REQUEST_ACCEPTED", 2.0, request_id="req-1", detail=DETAIL)
    trip = state.snapshot(T0)["trip"]
    assert (trip["mode"], trip["mode_name"]) == (1, "MODE_URGENT")
    assert trip["destination_id"] == "bed_a1"
    assert trip["mode_source"] == "event_detail"


def test_empty_detail_leaves_everything_null(state):
    """#104 머지 전 빌드. 오류가 아니라 정상 경로다."""
    ev(state, "REQUEST_ACCEPTED", 2.0, request_id="req-1", detail="")
    state.note_order({"request_id": "req-1", "order_id": "ord-1", "state": 1, "stamp": 3.0})
    trip = state.snapshot(T0)["trip"]
    assert trip["mode"] is None and trip["destination_id"] is None
    assert trip["mode_source"] is None
    assert trip["orders"][0]["patient_id"] is None
    assert trip["orders"][0]["item_id"] is None


def test_detail_supplies_patient_and_item_for_matching_order(state):
    ev(state, "REQUEST_ACCEPTED", 2.0, request_id="req-1", detail=DETAIL)
    state.note_order({"request_id": "req-1", "order_id": "ord-1", "state": 1, "stamp": 3.0})
    order = state.snapshot(T0)["trip"]["orders"][0]
    assert order["patient_id"] == "김환자" and order["item_id"] == "drug-ibu"


def test_order_state_name_comes_from_the_constant_table(state):
    ev(state, "REQUEST_ACCEPTED", 2.0, request_id="req-1", detail=DETAIL)
    state.note_order({"request_id": "req-1", "order_id": "ord-1", "state": 11,
                      "reason": "pharmacy_only", "stamp": 18.0})
    order = state.snapshot(T0)["trip"]["orders"][0]
    assert order["state_name"] == "HOLD_RETURN" and order["reason"] == "pharmacy_only"


def test_phase_follows_the_latest_event(state):
    ev(state, "REQUEST_ACCEPTED", 2.0, request_id="req-1", detail=DETAIL)
    ev(state, "DEPARTED", 10.0, request_id="req-1")
    assert state.snapshot(T0)["trip"]["phase"] == "moving"
    ev(state, "ARRIVING", 12.0, request_id="req-1")
    assert state.snapshot(T0)["trip"]["phase"] == "arriving"


# ── 리셋과 epoch ─────────────────────────────────────────────────────────

def test_reset_begin_raises_the_epoch_and_clears_the_trip(state):
    ev(state, "REQUEST_ACCEPTED", 2.0, request_id="req-1", detail=DETAIL)
    ev(state, "RESET_BEGIN", 60.0, epoch=2)
    snap = state.snapshot(T0)
    assert snap["epoch"] == 2
    assert snap["trip"] is None
    assert snap["reset_in_progress"] is True


def test_reset_done_ends_the_reset(state):
    ev(state, "RESET_BEGIN", 60.0, epoch=2)
    ev(state, "RESET_DONE", 64.0, epoch=2)
    assert state.snapshot(T0)["reset_in_progress"] is False


def test_recent_events_only_shows_the_current_epoch(state):
    ev(state, "DEPARTED", 1.0, epoch=1)
    ev(state, "RESET_BEGIN", 60.0, epoch=2)
    names = [e["name"] for e in state.snapshot(T0)["recent_events"]]
    assert names == ["RESET_BEGIN"]


def test_epoch_never_goes_backwards(state):
    ev(state, "RESET_BEGIN", 60.0, epoch=5)
    ev(state, "DEPARTED", 61.0, epoch=2)  # 늦게 도착한 옛 세대 이벤트
    assert state.snapshot(T0)["epoch"] == 5


# ── 신선도 ───────────────────────────────────────────────────────────────

def test_fresh_signal_is_not_stale(state):
    state.note_signal("arm_at_home", True, T0)
    assert state.snapshot(T0)["signals"]["arm_at_home"]["stale"] is False


def test_signal_older_than_one_second_is_stale(state):
    state.note_signal("m0609_at_home", True, T0)
    snap = state.snapshot(T0 + timedelta(seconds=1.5))
    assert snap["signals"]["m0609_at_home"]["stale"] is True


def test_clock_older_than_two_seconds_is_not_alive(state):
    assert state.snapshot(T0 + timedelta(seconds=1.0))["clock"]["alive"] is True
    assert state.snapshot(T0 + timedelta(seconds=2.5))["clock"]["alive"] is False


def test_only_the_five_documented_signal_keys_appear(state):
    state.note_signal("arm_at_home", True, T0)
    state.note_signal("made_up_signal", True, T0)
    assert set(state.snapshot(T0)["signals"]) == {"arm_at_home"}


def test_belt_message_also_feeds_the_belt_signal(state):
    state.note_belt({"occupied": True, "at_end": False, "order_id": "ord-1", "stamp": 7.0}, T0)
    snap = state.snapshot(T0)
    assert snap["belt"]["occupied"] is True
    assert snap["signals"]["belt"]["value"] is True


# ── 조제기 ───────────────────────────────────────────────────────────────

def test_dispenser_paused_is_derived_from_the_item_list(state):
    state.note_dispenser({"paused_item_ids": ["drug-ibu"], "queue_length": 1,
                          "belt_occupied": False, "slots": [], "stamp": 26.0}, T0)
    assert state.snapshot(T0)["dispenser"]["paused"] is True


def test_slot_number_gets_a_letter_name(state):
    state.note_dispenser({"paused_item_ids": [], "queue_length": 0, "belt_occupied": False,
                          "slots": [{"item_id": "drug-ibu", "slot": 0},
                                    {"item_id": "drug-acet", "slot": 1}], "stamp": 0.0}, T0)
    slots = state.snapshot(T0)["dispenser"]["slots"]
    assert [s["slot_name"] for s in slots] == ["A", "B"]


def test_unseen_sources_are_null_not_empty_objects(state):
    snap = state.snapshot(T0)
    assert snap["dispenser"] is None
    assert snap["belt"] is None
    assert snap["cabinet"] is None


# ── 계약 모양 ────────────────────────────────────────────────────────────

def test_snapshot_is_json_serialisable(state):
    ev(state, "REQUEST_ACCEPTED", 2.0, request_id="req-1", detail=DETAIL)
    state.note_dispenser({"paused_item_ids": [], "queue_length": 0, "belt_occupied": False,
                          "slots": [], "stamp": 0.0}, T0)
    state.note_belt({"occupied": False, "at_end": False, "order_id": "", "stamp": 0.0}, T0)
    json.dumps(state.snapshot(T0))  # 던지면 실패


def test_wall_times_are_iso_with_exactly_three_decimals(state):
    state.note_signal("arm_at_home", True, datetime(2026, 9, 17, 8, 12, 3, 412000, tzinfo=timezone.utc))
    assert state.snapshot(T0)["signals"]["arm_at_home"]["wall"] == "2026-09-17T08:12:03.412Z"


def test_server_run_id_differs_between_runs():
    assert WorldState().server_run_id != WorldState().server_run_id


# ── phase / phase_label (status_view.TRIP_PHASES 원문) ───────────────────

def test_phase_label_carries_the_korean_string_from_status_view(state):
    ev(state, "REQUEST_ACCEPTED", 2.0, request_id="req-1", detail=DETAIL)
    trip = state.snapshot(T0)["trip"]
    assert trip["phase"] == "accepted"
    assert trip["phase_label"] == "적재 위치로 이동"
    assert trip["phase_source"] == "status_view"


@pytest.mark.parametrize(("name", "phase", "label"), [
    ("AMR_DOCKED_LOAD", "docked_load", "배출"),
    ("DISPENSED", "dispensing", "벨트 이송"),
    ("POUCH_AT_END", "dispensing", "벨트 끝 픽"),
    ("LOAD_DONE", "load_done", "적재 끝"),
    ("ARM_HOME", "arm_home", "팔 홈"),
    ("DEPARTED", "moving", "병동으로 이동"),
    ("ARRIVING", "arriving", "병동 도착 직전"),
    ("ARRIVED", "arrived", "인증"),
    ("AUTH_FAIL", "auth", "인증 실패"),
    ("CABINET_LOCKED", "locked", "보관함 잠김"),
    ("DOCKED", "docked", "대기(도크)"),
])
def test_each_event_maps_to_its_documented_phase_and_label(state, name, phase, label):
    ev(state, "REQUEST_ACCEPTED", 2.0, request_id="req-1", detail=DETAIL)
    ev(state, name, 10.0, request_id="req-1")
    state.trip_open = True  # DOCKED 로 닫혀도 단계 자체는 보고 싶다
    trip = state.snapshot(T0)["trip"]
    assert (trip["phase"], trip["phase_label"]) == (phase, label)


@pytest.mark.parametrize("name", [
    "DISPENSER_PAUSED", "DISPENSER_RESUMED", "REFILL_REQUESTED", "REFILL_DONE",
])
def test_dispenser_and_m0609_events_do_not_change_the_phase(state, name):
    """작전 지시: 조제기·M0609 이벤트는 단계를 바꾸지 않는다."""
    ev(state, "REQUEST_ACCEPTED", 2.0, request_id="req-1", detail=DETAIL)
    ev(state, "DEPARTED", 10.0, request_id="req-1")
    ev(state, name, 12.0, request_id="req-1", robot_id="dispenser")
    trip = state.snapshot(T0)["trip"]
    assert trip["phase"] == "moving", "조제기 이벤트가 단계를 덮어썼다"
    assert trip["phase_label"] == "병동으로 이동"


# ── 보충 진행 표시 ───────────────────────────────────────────────────────

def dispenser_seen(state, stamp=0.0, paused=()):
    state.note_dispenser({"paused_item_ids": list(paused), "queue_length": 0,
                          "belt_occupied": False, "slots": [], "stamp": stamp}, T0)


def test_refilling_is_false_before_any_refill(state):
    dispenser_seen(state)
    assert state.snapshot(T0)["dispenser"]["refilling"] is False


def test_refilling_is_true_between_request_and_done(state):
    ev(state, "REFILL_REQUESTED", 26.5, robot_id="dispenser", detail="drug-ibu")
    dispenser_seen(state, 26.5, paused=["drug-ibu"])
    snap = state.snapshot(T0)["dispenser"]
    assert snap["refilling"] is True
    assert snap["refilling_item_ids"] == ["drug-ibu"]


def test_refilling_clears_on_done(state):
    ev(state, "REFILL_REQUESTED", 26.5, robot_id="dispenser", detail="drug-ibu")
    ev(state, "REFILL_DONE", 54.5, robot_id="m0609", detail="drug-ibu slot a")
    dispenser_seen(state, 56.0)
    snap = state.snapshot(T0)["dispenser"]
    assert snap["refilling"] is False
    assert snap["refilling_item_ids"] == []


def test_refilling_items_come_from_paused_ids_not_from_detail(state):
    """작전 지시: detail 은 구조 파싱 대상이 아니다. 약품은 조제기가 말해 주는 값으로."""
    ev(state, "REFILL_REQUESTED", 26.5, robot_id="dispenser", detail="사람이 읽는 아무 메모")
    dispenser_seen(state, 26.5, paused=["drug-ibu", "drug-acet"])
    snap = state.snapshot(T0)["dispenser"]
    assert snap["refilling"] is True
    assert snap["refilling_item_ids"] == ["drug-ibu", "drug-acet"]


def test_refilling_is_decided_by_event_name_even_when_detail_is_empty(state):
    ev(state, "REFILL_REQUESTED", 26.5, robot_id="dispenser", detail="")
    dispenser_seen(state, 26.5, paused=["drug-ibu"])
    assert state.snapshot(T0)["dispenser"]["refilling"] is True


def test_a_reset_clears_refilling_because_events_are_scoped_to_the_epoch(state):
    ev(state, "REFILL_REQUESTED", 26.5, robot_id="dispenser", detail="drug-ibu")
    ev(state, "RESET_BEGIN", 62.0, epoch=2)
    dispenser_seen(state, 62.0, paused=["drug-ibu"])
    assert state.snapshot(T0)["dispenser"]["refilling"] is False


def test_one_item_done_does_not_clear_another_items_refilling_flag(state):
    """A 완료가 B 의 진행 표시를 끄면 안 된다."""
    ev(state, "REFILL_REQUESTED", 10.0, robot_id="dispenser", detail="drug-amox")
    ev(state, "REFILL_REQUESTED", 20.0, robot_id="dispenser", detail="drug-ibu")
    ev(state, "REFILL_DONE", 50.0, robot_id="m0609", detail="drug-amox slot a")
    dispenser_seen(state, 50.0, paused=["drug-ibu"])
    snap = state.snapshot(T0)["dispenser"]
    assert snap["refilling"] is True
    assert snap["refilling_item_ids"] == ["drug-ibu"]


def test_two_dones_clear_two_requests(state):
    ev(state, "REFILL_REQUESTED", 10.0, robot_id="dispenser")
    ev(state, "REFILL_REQUESTED", 20.0, robot_id="dispenser")
    ev(state, "REFILL_DONE", 40.0, robot_id="m0609")
    ev(state, "REFILL_DONE", 50.0, robot_id="m0609")
    dispenser_seen(state, 50.0, paused=["drug-ibu"])
    snap = state.snapshot(T0)["dispenser"]
    assert snap["refilling"] is False
    assert snap["refilling_item_ids"] == []


def test_snapshot_keeps_the_open_item_timeout_after_the_other_item_is_done(state):
    """snapshot 경로도 같은 짝짓기를 쓴다. 정렬 키가 도착 순과 달라도 결과는 같다."""
    from app.alarms import REFILL_TIMEOUT_SIM_S

    ev(state, "REFILL_REQUESTED", 10.0, robot_id="dispenser", order_id="ord-a")
    ev(state, "REFILL_REQUESTED", 20.0, robot_id="dispenser", order_id="ord-b")
    ev(state, "REFILL_DONE", 50.0, robot_id="m0609", order_id="ord-a")
    dispenser_seen(state, 50.0, paused=["drug-ibu"])
    now_sim = 20.0 + REFILL_TIMEOUT_SIM_S + 0.1
    state.note_clock(now_sim, T0)
    snap = state.snapshot(T0)
    assert snap["dispenser"]["refilling"] is True
    failed = [a for a in snap["alarms"] if a["kind"] == "REFILL_FAILED"]
    assert [a["order_id"] for a in failed] == ["ord-b"]


# ── 신선도 임계는 토픽 종류마다 다르다 ──────────────────────────────────

def test_dispenser_gets_a_looser_threshold_than_heartbeats(state):
    """DispenserStatus 는 H 가 아니라 L(변화 시 + 1 Hz)이다.

    1 Hz 발행에 1.0 s 임계를 쓰면 실물에서 가짜 stale 이 깜빡인다.
    """
    from app.alarms import DISPENSER_STALE_WALL_S, STALE_WALL_S

    assert DISPENSER_STALE_WALL_S > STALE_WALL_S
    dispenser_seen(state, 0.0)
    state.note_signal("arm_at_home", True, T0)

    at_1_5s = state.snapshot(T0 + timedelta(seconds=1.5))
    assert at_1_5s["signals"]["arm_at_home"]["stale"] is True, "H 는 1.0 s 면 낡았다"
    assert at_1_5s["dispenser"]["stale"] is False, "L 은 1.5 s 로는 아직 아니다"

    at_3_5s = state.snapshot(T0 + timedelta(seconds=3.5))
    assert at_3_5s["dispenser"]["stale"] is True


# ── 단계표는 원문에서 온다 (베낀 사본이 아니다) ─────────────────────────

def test_the_phase_table_is_the_upstream_one():
    """status_view.TRIP_PHASES 를 import 해서 쓴다. 베껴 두면 저쪽이 바뀔 때 갈라진다."""
    from app.orchestrator_view import TRIP_PHASES, status_view

    assert TRIP_PHASES is status_view.TRIP_PHASES
    assert len(TRIP_PHASES) == 22


def test_the_signal_keys_and_thresholds_are_the_upstream_ones():
    from app.alarms import CLOCK_STALE_WALL_S, SIGNAL_KEYS, STALE_WALL_S
    from app.orchestrator_view import status_view

    upstream_keys = tuple(k for k, _ in status_view.SIGNALS)
    assert upstream_keys == SIGNAL_KEYS
    assert status_view.SIGNAL_FRESH_S == STALE_WALL_S
    assert status_view.CLOCK_FRESH_S == CLOCK_STALE_WALL_S


def test_events_sharing_a_label_share_a_phase():
    """phase 를 한글 라벨에서 뽑으므로 둘이 어긋날 수 없다."""
    from collections import defaultdict

    from app.orchestrator_view import TRIP_PHASES, phase_for

    by_label = defaultdict(set)
    for name, label in TRIP_PHASES.items():
        by_label[label].add(phase_for(name)[0])
    bad = {label: phases for label, phases in by_label.items() if len(phases) > 1}
    assert not bad, f"같은 라벨인데 phase 가 갈린다: {bad}"


@pytest.mark.parametrize(("name", "phase", "label"), [
    ("AUTH_OK", "unloading", "보관함 배달"),
    ("POUCH_DETECTED", "unloading", "보관함 배달"),
    ("POUCH_PLACED", "unloading", "보관함 배달"),
    ("AUTH_FAIL", "auth", "인증 실패"),
])
def test_cabinet_delivery_events_share_one_phase(state, name, phase, label):
    from app.orchestrator_view import phase_for

    assert phase_for(name) == (phase, label)


# ── 이벤트 순서는 도착 순서가 아니라 event_key 다 ───────────────────────

def test_late_arriving_events_are_shown_in_event_key_order(state):
    """/events 는 latched 라 늦게 붙으면 작성자별로 뭉쳐서 온다.

    도착 순서로 그리면 늦게 연 화면의 타임라인이 통째로 뒤죽박죽이 된다.
    """
    # orchestrator 이력이 먼저 통째로, 그 다음 arm 이력이 통째로 오는 모양
    ev(state, "REQUEST_ACCEPTED", 2.0, request_id="req-1")
    ev(state, "LOAD_DONE", 15.5, request_id="req-1")
    ev(state, "DOCKED", 20.0, request_id="req-1")
    ev(state, "PICK_ATTEMPT", 11.5, request_id="req-1", robot_id="amr_1")
    ev(state, "POUCH_PICKED", 13.0, request_id="req-1", robot_id="amr_1")

    stamps = [e["stamp"] for e in state.snapshot(T0)["recent_events"]]
    assert stamps == sorted(stamps), f"stamp 순이 아니다: {stamps}"


def test_the_reset_divider_stays_in_place_even_when_stamps_rewind(state):
    """RESET_BEGIN 은 이전 epoch 의 stamp 를 싣는다 — stamp 만으로는 제자리에 안 선다."""
    ev(state, "RESET_BEGIN", 62.0, epoch=2)
    ev(state, "RESET_DONE", 3.0, epoch=2)      # 되감긴 뒤의 stamp
    ev(state, "REQUEST_ACCEPTED", 7.5, epoch=2, request_id="req-2")
    names = [e["name"] for e in state.snapshot(T0)["recent_events"]]
    assert names == ["RESET_BEGIN", "RESET_DONE", "REQUEST_ACCEPTED"]


# ── 리셋이 계속 도는 실물에서 새지 않는가 ────────────────────────────────

def churn(state, resets=200, per_epoch=3):
    """리셋이 20 s 마다 도는 실물(Isaac 조제실)을 흉내 낸다."""
    for epoch in range(1, resets + 1):
        state.note_event({"name": "RESET_BEGIN", "epoch": epoch, "stamp": epoch * 20.0}, T0)
        state.note_event({"name": "RESET_DONE", "epoch": epoch, "stamp": epoch * 20.0 + 2}, T0)
        for i in range(per_epoch):
            rid = f"r{epoch:03d}-{i}"
            state.note_event({"name": "REQUEST_ACCEPTED", "epoch": epoch,
                              "stamp": epoch * 20.0 + 3 + i, "request_id": rid,
                              "detail": DETAIL}, T0)
            state.note_order({"request_id": rid, "order_id": f"ord-{i}",
                              "state": 11, "reason": "pharmacy_only", "stamp": 0.0})
            state.note_event({"name": "DOCKED", "epoch": epoch,
                              "stamp": epoch * 20.0 + 8 + i, "request_id": rid}, T0)
            state.note_log({"level": "warn", "level_value": 30, "node": "n",
                            "message": "m", "stamp": 0.0}, T0)


def test_nothing_grows_without_bound_while_resets_keep_coming(state):
    """리셋이 20 s 마다 도는 실물에서 몇 시간을 버텨야 한다."""
    churn(state)
    assert len(state.events) <= state.event_buffer
    assert len(state.logs) <= state.log_buffer
    assert len(state.request_detail) <= 10, \
        f"request_detail 이 {len(state.request_detail)}개까지 자랐다 — 세대마다 비워야 한다"
    assert len(state.used_request_ids) <= 10
    assert len(state.used_order_ids) <= 10
    assert len(state.orders) <= 10


def test_a_snapshot_after_long_churn_only_shows_the_current_epoch(state):
    churn(state, resets=50)
    snap = state.snapshot(T0)
    assert snap["epoch"] == 50
    assert all(e["epoch"] == 50 for e in snap["recent_events"])
    assert all(a["epoch"] == 50 for a in snap["alarms"])


def test_detail_from_an_earlier_epoch_does_not_bleed_through(state):
    """세대가 바뀌면 detail 도 비운다 — 옛 트립의 환자·약품이 새 화면에 남으면 안 된다."""
    ev(state, "REQUEST_ACCEPTED", 2.0, request_id="req-1", detail=DETAIL)
    assert "req-1" in state.request_detail
    ev(state, "RESET_BEGIN", 60.0, epoch=2)
    assert state.request_detail == {}


# ── 늦게 붙어 이벤트가 뭉쳐 올 때의 리셋 판정 ───────────────────────────

def test_a_burst_on_connect_does_not_lock_the_screen_in_reset(state):
    """latched 라 지난 이벤트가 작성자별로 뭉쳐 온다.

    도착 순서로 보면 옛 RESET_BEGIN 이 새 RESET_DONE 뒤로 가서, 첫 화면이 "리셋 중" 으로
    잘못 잠기고 요청이 전부 barrier_running 으로 거부된다.
    """
    # 새 세대의 완료가 먼저 도착하고, 옛 세대의 시작이 뒤늦게 도착한다
    ev(state, "RESET_DONE", 22.0, epoch=2)
    ev(state, "RESET_BEGIN", 20.0, epoch=2)
    ev(state, "RESET_BEGIN", 0.5, epoch=1)
    assert state.snapshot(T0)["reset_in_progress"] is False


def test_a_real_unfinished_reset_is_still_detected(state):
    ev(state, "RESET_DONE", 22.0, epoch=2)
    ev(state, "RESET_BEGIN", 40.0, epoch=3)
    assert state.snapshot(T0)["reset_in_progress"] is True


# ── Isaac 쪽 작성자 ──────────────────────────────────────────────────────

def test_dispenser_events_from_isaac_do_not_disturb_the_trip(state):
    """Isaac 이 낸 이벤트는 어댑터가 robot_id 'dispenser' 로 옮겨 싣는다."""
    ev(state, "REQUEST_ACCEPTED", 2.0, request_id="req-1", detail=DETAIL)
    ev(state, "DEPARTED", 10.0, request_id="req-1", robot_id="amr_1")
    ev(state, "DISPENSER_PAUSED", 12.0, robot_id="dispenser")
    trip = state.snapshot(T0)["trip"]
    assert trip["phase"] == "moving", "조제기 이벤트가 트립 단계를 덮었다"
    assert trip["robot_id"] == "amr_1", "트립의 로봇이 dispenser 로 바뀌었다"


# ── 페이지네이션: 커서로 자르고 나서 정렬한다 ───────────────────────────

def test_paging_never_loses_an_event_that_arrived_out_of_order(state):
    """순서로 자르면 seq 가 낮은데 event_key 가 늦은 것이 영영 안 온다.

    실물에서 실제로 났다: 화면이 RESET_BEGIN·RESET_DONE 을 끝내 못 받았다.
    """
    for name, stamp in [("DOCKED", 30.0), ("REQUEST_ACCEPTED", 10.0), ("DEPARTED", 20.0)]:
        ev(state, name, stamp, request_id="r1")

    delivered: set[int] = set()
    cursor = 0
    for _ in range(10):
        page, cursor, more = state.events_for(1, since=cursor, limit=2)
        delivered |= {e["seq"] for e in page}
        if not more:
            break
    assert delivered == {e["seq"] for e in state.events}, "커서를 돌렸는데 빠진 이벤트가 있다"


def test_the_cursor_never_goes_backwards(state):
    for name, stamp in [("DOCKED", 30.0), ("REQUEST_ACCEPTED", 10.0),
                        ("DEPARTED", 20.0), ("ARRIVED", 25.0)]:
        ev(state, name, stamp, request_id="r1")
    cursor = 0
    seen = [cursor]
    for _ in range(10):
        _page, cursor, more = state.events_for(1, since=cursor, limit=2)
        seen.append(cursor)
        if not more:
            break
    assert seen == sorted(seen), f"커서가 되돌아갔다: {seen}"


def test_a_page_is_still_shown_in_event_key_order(state):
    for name, stamp in [("DOCKED", 30.0), ("REQUEST_ACCEPTED", 10.0), ("DEPARTED", 20.0)]:
        ev(state, name, stamp, request_id="r1")
    page, _cursor, _more = state.events_for(1, since=0, limit=10)
    stamps = [e["stamp"] for e in page]
    assert stamps == sorted(stamps), f"페이지 안이 stamp 순이 아니다: {stamps}"


def test_seq_is_not_contiguous_inside_one_epoch(state):
    """epoch 로 거르면 seq 에 구멍이 난다 — 구멍으로 유실을 판단하면 안 된다."""
    ev(state, "DEPARTED", 1.0, epoch=1)
    ev(state, "RESET_BEGIN", 2.0, epoch=2)
    ev(state, "DEPARTED", 3.0, epoch=2)
    page, _cursor, _more = state.events_for(2, since=0, limit=10)
    seqs = sorted(e["seq"] for e in page)
    assert seqs == [2, 3], seqs
    assert seqs[0] != 1, "1번은 다른 epoch 것이라 이 목록에 없다 — 구멍은 정상이다"


# ── 트립의 로봇은 AMR 뿐이다 ────────────────────────────────────────────

def trip_robot(state):
    return state.snapshot(T0)["trip"]["robot_id"]


def test_a_dispenser_event_does_not_become_the_trip_robot(state):
    """master02 스텁 원문에 `"robot_id": "dispenser"` 가 찍혔다.

    "마지막 이벤트의 robot_id" 로 채우면 DISPENSED 직후에 로봇이 조제기로 보인다.
    조제기·M0609 는 조제실 설비이고 트립을 수행하는 로봇이 아니다.
    """
    ev(state, "REQUEST_ACCEPTED", 2.0, request_id="req-1", detail=DETAIL)
    ev(state, "AMR_DOCKED_LOAD", 4.0, request_id="req-1", robot_id="amr_1")
    ev(state, "DISPENSED", 7.0, request_id="req-1", robot_id="dispenser")
    assert trip_robot(state) == "amr_1"


@pytest.mark.parametrize("robot", ["dispenser", "m0609"])
def test_pharmacy_equipment_never_becomes_the_trip_robot(state, robot):
    ev(state, "REQUEST_ACCEPTED", 2.0, request_id="req-1", detail=DETAIL)
    ev(state, "AMR_DOCKED_LOAD", 4.0, request_id="req-1", robot_id="amr_1")
    ev(state, "POUCH_AT_END", 9.0, request_id="req-1", robot_id=robot)
    ev(state, "REFILL_DONE", 11.0, request_id="req-1", robot_id=robot)
    assert trip_robot(state) == "amr_1"


def test_the_robot_is_unknown_until_an_amr_event_arrives(state):
    """요청이 수락된 직후에는 아직 로봇이 안 붙는다. 지어내지 않는다."""
    ev(state, "REQUEST_ACCEPTED", 2.0, request_id="req-1", detail=DETAIL)
    assert trip_robot(state) is None


def test_the_robot_is_taken_from_request_accepted_when_it_carries_one(state):
    ev(state, "REQUEST_ACCEPTED", 2.0, request_id="req-1", detail=DETAIL, robot_id="amr_3")
    ev(state, "DISPENSED", 7.0, request_id="req-1", robot_id="dispenser")
    assert trip_robot(state) == "amr_3"


def test_the_robot_stays_fixed_for_the_trip(state):
    """한 번 정해지면 트립 동안 바뀌지 않는다 — 뒤에 다른 AMR 이벤트가 와도."""
    ev(state, "REQUEST_ACCEPTED", 2.0, request_id="req-1", detail=DETAIL)
    ev(state, "AMR_DOCKED_LOAD", 4.0, request_id="req-1", robot_id="amr_1")
    ev(state, "DEPARTED", 10.0, request_id="req-1", robot_id="amr_2")
    assert trip_robot(state) == "amr_1", "처음 붙은 AMR 이 트립의 로봇이다"


@pytest.mark.parametrize("robot", ["amr_1", "amr_2", "amr_5", "amr_12"])
def test_every_amr_id_shape_is_accepted(state, robot):
    ev(state, "REQUEST_ACCEPTED", 2.0, request_id="req-1", detail=DETAIL)
    ev(state, "AMR_DOCKED_LOAD", 4.0, request_id="req-1", robot_id=robot)
    assert trip_robot(state) == robot


def test_a_late_arriving_amr_event_does_not_win_over_an_earlier_one(state):
    """뭉쳐 와도 event_key 순으로 처음 나오는 AMR 이 트립의 로봇이다."""
    ev(state, "REQUEST_ACCEPTED", 2.0, request_id="req-1", detail=DETAIL)
    ev(state, "DEPARTED", 10.0, request_id="req-1", robot_id="amr_2")   # 먼저 도착
    ev(state, "AMR_DOCKED_LOAD", 4.0, request_id="req-1", robot_id="amr_1")  # 늦게 도착
    assert trip_robot(state) == "amr_1", "stamp 가 이른 쪽이 트립의 로봇이다"
