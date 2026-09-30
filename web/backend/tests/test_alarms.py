"""알람 규칙표(api.md §4.1) 테스트. ROS 없이 돈다."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.alarms import (
    CLOCK_STALE_WALL_S,
    RESET_TIMEOUT_WALL_S,
    STATE_ACCEPTED,
    STATE_IN_PROGRESS,
    STATE_SUCCESS,
    REFILL_TIMEOUT_SIM_S,
    STALE_WALL_S,
    STATE_ABORT,
    STATE_DELIVERED,
    STATE_HOLD_RETURN,
    STATE_TIMEOUT,
    alarm_id,
    evaluate_alarms,
)

ALARM_FIELDS = {"id", "level", "kind", "message", "request_id", "order_id", "stamp", "epoch"}


def ev(name, stamp, **kw):
    base = {"name": name, "stamp": stamp, "request_id": "req-1", "order_id": "ord-1",
            "robot_id": "amr_1", "epoch": 3, "detail": ""}
    base.update(kw)
    return base


def kinds(alarms):
    return {a["kind"] for a in alarms}


def by_kind(alarms, kind):
    return next(a for a in alarms if a["kind"] == kind)


# ── 계약: 객체 모양 ──────────────────────────────────────────────────────

def test_alarm_has_exactly_the_eight_documented_fields():
    alarms = evaluate_alarms(events=[ev("AUTH_FAIL", 10.0)], epoch=3, now_sim_s=11.0)
    assert alarms, "AUTH_FAIL 은 알람을 내야 한다"
    for a in alarms:
        assert set(a) == ALARM_FIELDS


def test_level_is_always_one_of_three():
    alarms = evaluate_alarms(
        events=[ev("AUTH_FAIL", 10.0), ev("ARRIVING", 9.0), ev("RESET_BEGIN", 12.0)],
        epoch=3, now_sim_s=13.0,
    )
    assert {a["level"] for a in alarms} <= {"info", "warn", "error"}


def test_empty_input_yields_no_alarms():
    assert evaluate_alarms(epoch=0, now_sim_s=0.0) == []


# ── 이벤트성 규칙 ────────────────────────────────────────────────────────

def test_auth_fail_is_error_and_names_destination_and_order():
    alarms = evaluate_alarms(
        events=[ev("AUTH_FAIL", 10.0, order_id="ord-12")],
        epoch=3, now_sim_s=11.0, destination_id="bed_a1",
    )
    a = by_kind(alarms, "AUTH_FAIL")
    assert a["level"] == "error"
    assert "bed_a1" in a["message"] and "ord-12" in a["message"]
    assert a["order_id"] == "ord-12"


def test_urgent_arriving_is_warn():
    alarms = evaluate_alarms(
        events=[ev("ARRIVING", 20.0)], epoch=3, now_sim_s=21.0, destination_id="bed_a1"
    )
    a = by_kind(alarms, "URGENT_ARRIVING")
    assert a["level"] == "warn"
    assert "bed_a1" in a["message"]


def test_non_urgent_trip_has_no_arriving_alarm():
    """ARRIVING 은 긴급만 낸다. 일반 트립 이벤트열에는 없으므로 알람도 없다."""
    events = [ev("DEPARTED", 30.0), ev("ARRIVED", 40.0), ev("AUTH_OK", 41.0)]
    assert "URGENT_ARRIVING" not in kinds(evaluate_alarms(events=events, epoch=3, now_sim_s=42.0))


# ── 주문 종료 상태 ───────────────────────────────────────────────────────

@pytest.mark.parametrize(
    ("state", "kind", "level"),
    [
        (STATE_HOLD_RETURN, "HOLD_RETURN", "warn"),
        (STATE_ABORT, "ABORT", "error"),
        (STATE_TIMEOUT, "TIMEOUT", "error"),
    ],
)
def test_terminal_states_map_to_documented_kind_and_level(state, kind, level):
    # reason 은 `pharmacy_only` 가 아닌 것으로 — 그건 정상 완주라 알람이 면제된다.
    orders = {"ord-12": {"state": state, "reason": "auth_mismatch",
                         "stamp": 50.0, "request_id": "req-1"}}
    a = by_kind(evaluate_alarms(orders=orders, epoch=3, now_sim_s=51.0), kind)
    assert a["level"] == level
    assert a["order_id"] == "ord-12"


def test_terminal_alarm_always_carries_the_reason():
    orders = {"ord-12": {"state": STATE_ABORT, "reason": "gripper_lost",
                         "stamp": 50.0, "request_id": "req-1"}}
    a = by_kind(evaluate_alarms(orders=orders, epoch=3, now_sim_s=51.0), "ABORT")
    assert "gripper_lost" in a["message"]


@pytest.mark.parametrize(("reason", "words", "state", "kind"), [
    ("qr_mismatch", "약 QR 이 주문과 다름", STATE_ABORT, "ABORT"),          # 벨트 끝 집기 실패는 ABORT
    ("not_detected", "약 QR 을 못 읽음", STATE_HOLD_RETURN, "HOLD_RETURN"),  # 상판(병상) 집기 실패는 회수
])
def test_pouch_qr_reasons_are_said_in_korean_with_the_code(reason, words, state, kind):
    """#784(재범 9/29 QR 필수): 봉투 QR 이 다르거나 못 읽어 닫힌 주문은 사람 말로, 원문 코드도 같이."""
    orders = {"ord-12": {"state": state, "reason": reason, "stamp": 50.0, "request_id": "req-1"}}
    a = by_kind(evaluate_alarms(orders=orders, epoch=3, now_sim_s=51.0), kind)
    assert f"(사유: {words} — {reason})" in a["message"]


def test_empty_reason_does_not_leave_a_dangling_label():
    orders = {"ord-12": {"state": STATE_ABORT, "reason": "", "stamp": 50.0}}
    a = by_kind(evaluate_alarms(orders=orders, epoch=3, now_sim_s=51.0), "ABORT")
    assert "사유" not in a["message"]


def test_in_flight_and_delivered_orders_raise_nothing():
    orders = {"ord-12": {"state": STATE_DELIVERED, "reason": "", "stamp": 50.0}}
    assert evaluate_alarms(orders=orders, epoch=3, now_sim_s=51.0) == []


# ── 조제기 ───────────────────────────────────────────────────────────────

def test_dispenser_paused_lists_the_paused_items():
    disp = {"paused_item_ids": ["drug-ibu"], "stamp": 60.0}
    a = by_kind(evaluate_alarms(dispenser=disp, epoch=3, now_sim_s=61.0), "DISPENSER_PAUSED")
    assert a["level"] == "warn" and "drug-ibu" in a["message"]


def test_dispenser_alarm_clears_when_resumed():
    disp = {"paused_item_ids": [], "stamp": 90.0}
    assert "DISPENSER_PAUSED" not in kinds(
        evaluate_alarms(dispenser=disp, epoch=3, now_sim_s=91.0)
    )


# ── 보충 ─────────────────────────────────────────────────────────────────

def test_refill_within_normal_28s_is_not_a_failure():
    """정상 보충은 약 28 sim s. 아직 기다릴 시간이 남았으면 알람 없음."""
    events = [ev("REFILL_REQUESTED", 100.0)]
    assert "REFILL_FAILED" not in kinds(
        evaluate_alarms(events=events, epoch=3, now_sim_s=100.0 + 28.0)
    )


def test_refill_failure_fires_past_the_threshold():
    events = [ev("REFILL_REQUESTED", 100.0)]
    now = 100.0 + REFILL_TIMEOUT_SIM_S + 0.1
    a = by_kind(evaluate_alarms(events=events, epoch=3, now_sim_s=now), "REFILL_FAILED")
    assert a["level"] == "error"


def test_refill_done_clears_the_pending_refill():
    events = [ev("REFILL_REQUESTED", 100.0), ev("REFILL_DONE", 128.0, detail="drug-ibu slot a")]
    assert "REFILL_FAILED" not in kinds(
        evaluate_alarms(events=events, epoch=3, now_sim_s=200.0)
    )


def test_a_stale_done_from_an_earlier_refill_does_not_clear_a_new_request():
    """이전 보충의 완료가 새 요청을 지워버리면 안 된다."""
    events = [ev("REFILL_DONE", 50.0), ev("REFILL_REQUESTED", 100.0)]
    now = 100.0 + REFILL_TIMEOUT_SIM_S + 0.1
    assert "REFILL_FAILED" in kinds(evaluate_alarms(events=events, epoch=3, now_sim_s=now))


def test_one_item_done_does_not_clear_another_items_timeout_alarm():
    """A 완료가 B 의 미완료 실패 알람을 가리면 안 된다.

    마지막 요청·마지막 완료만 보면 A 요청 → B 요청 → A 완료에서 B 가 남아 있는데도
    알람이 없다. 열린 요청마다 시한을 잰다.
    """
    events = [
        ev("REFILL_REQUESTED", 10.0, order_id="ord-a"),
        ev("REFILL_REQUESTED", 20.0, order_id="ord-b"),
        ev("REFILL_DONE", 50.0, order_id="ord-a"),
    ]
    now = 20.0 + REFILL_TIMEOUT_SIM_S + 0.1
    alarms = [a for a in evaluate_alarms(events=events, epoch=3, now_sim_s=now)
              if a["kind"] == "REFILL_FAILED"]
    assert len(alarms) == 1
    assert alarms[0]["order_id"] == "ord-b"
    assert alarms[0]["stamp"] == 20.0


def test_two_open_refills_can_each_raise_their_own_timeout():
    events = [
        ev("REFILL_REQUESTED", 10.0, order_id="ord-a"),
        ev("REFILL_REQUESTED", 20.0, order_id="ord-b"),
    ]
    now = 10.0 + REFILL_TIMEOUT_SIM_S + 0.1
    alarms = [a for a in evaluate_alarms(events=events, epoch=3, now_sim_s=now)
              if a["kind"] == "REFILL_FAILED"]
    assert {a["order_id"] for a in alarms} == {"ord-a"}
    later = [a for a in evaluate_alarms(
        events=events, epoch=3, now_sim_s=20.0 + REFILL_TIMEOUT_SIM_S + 0.1)
        if a["kind"] == "REFILL_FAILED"]
    assert {a["order_id"] for a in later} == {"ord-a", "ord-b"}


def test_matching_dones_clear_every_open_request():
    events = [
        ev("REFILL_REQUESTED", 10.0, order_id="ord-a"),
        ev("REFILL_REQUESTED", 20.0, order_id="ord-b"),
        ev("REFILL_DONE", 40.0, order_id="ord-a"),
        ev("REFILL_DONE", 50.0, order_id="ord-b"),
    ]
    assert "REFILL_FAILED" not in kinds(
        evaluate_alarms(events=events, epoch=3, now_sim_s=200.0))


def test_unmatched_refill_requests_pair_done_to_the_oldest_open_request():
    from app.alarms import unmatched_refill_requests

    events = [
        ev("REFILL_REQUESTED", 10.0, order_id="ord-a"),
        ev("REFILL_REQUESTED", 20.0, order_id="ord-b"),
        ev("REFILL_DONE", 50.0, order_id="ord-a"),
    ]
    pending = unmatched_refill_requests(events)
    assert [e["order_id"] for e in pending] == ["ord-b"]


def test_extra_refill_done_does_not_go_negative():
    from app.alarms import unmatched_refill_requests

    events = [ev("REFILL_DONE", 5.0), ev("REFILL_DONE", 6.0),
              ev("REFILL_REQUESTED", 10.0, order_id="ord-a")]
    pending = unmatched_refill_requests(events)
    assert [e["order_id"] for e in pending] == ["ord-a"]


# ── 신선도 ───────────────────────────────────────────────────────────────

def test_signal_exactly_at_the_threshold_is_not_stale():
    ages = {"m0609_at_home": STALE_WALL_S}
    assert "STATUS_STALE" not in kinds(evaluate_alarms(signal_ages=ages, epoch=3, now_sim_s=1.0))


def test_signal_past_the_threshold_is_stale_and_names_the_signal():
    ages = {"m0609_at_home": 82.4}
    a = by_kind(evaluate_alarms(signal_ages=ages, epoch=3, now_sim_s=1.0), "STATUS_STALE")
    assert a["level"] == "warn" and "m0609_at_home" in a["message"]


def test_each_stale_signal_gets_its_own_alarm():
    ages = {"m0609_at_home": 5.0, "belt": 5.0}
    stale = [a for a in evaluate_alarms(signal_ages=ages, epoch=3, now_sim_s=1.0)
             if a["kind"] == "STATUS_STALE"]
    assert len(stale) == 2
    assert len({a["id"] for a in stale}) == 2


def test_unknown_signal_keys_are_ignored():
    ages = {"not_a_real_signal": 999.0}
    assert evaluate_alarms(signal_ages=ages, epoch=3, now_sim_s=1.0) == []


def test_clock_exactly_at_the_threshold_is_alive():
    assert "CLOCK_STOPPED" not in kinds(
        evaluate_alarms(clock_age_wall_s=CLOCK_STALE_WALL_S, epoch=3, now_sim_s=1.0)
    )


def test_clock_past_the_threshold_is_an_error():
    a = by_kind(evaluate_alarms(clock_age_wall_s=3.1, epoch=3, now_sim_s=1.0), "CLOCK_STOPPED")
    assert a["level"] == "error"


def test_clock_never_seen_is_not_reported_as_stopped():
    assert evaluate_alarms(clock_age_wall_s=None, epoch=3, now_sim_s=1.0) == []


# ── 리셋 ─────────────────────────────────────────────────────────────────

def test_reset_in_progress_is_info_and_names_the_epoch():
    a = by_kind(evaluate_alarms(events=[ev("RESET_BEGIN", 200.0, epoch=4)],
                                epoch=4, now_sim_s=201.0), "RESET_IN_PROGRESS")
    assert a["level"] == "info" and "4" in a["message"]


def test_reset_done_clears_it():
    events = [ev("RESET_BEGIN", 200.0), ev("RESET_DONE", 203.5)]
    assert "RESET_IN_PROGRESS" not in kinds(
        evaluate_alarms(events=events, epoch=4, now_sim_s=204.0)
    )


# ── 중복 접기와 정렬 ─────────────────────────────────────────────────────

def test_the_same_alarm_twice_is_folded_into_one():
    events = [ev("AUTH_FAIL", 10.0, order_id="ord-12"), ev("AUTH_FAIL", 12.0, order_id="ord-12")]
    fails = [a for a in evaluate_alarms(events=events, epoch=3, now_sim_s=13.0)
             if a["kind"] == "AUTH_FAIL"]
    assert len(fails) == 1
    assert fails[0]["stamp"] == 12.0, "접힐 때 나중 것이 이겨야 한다"


def test_the_same_kind_on_different_orders_stays_separate():
    events = [ev("AUTH_FAIL", 10.0, order_id="ord-12"), ev("AUTH_FAIL", 11.0, order_id="ord-13")]
    fails = [a for a in evaluate_alarms(events=events, epoch=3, now_sim_s=12.0)
             if a["kind"] == "AUTH_FAIL"]
    assert len(fails) == 2


def test_epoch_is_part_of_the_identity():
    assert alarm_id("AUTH_FAIL", "req-1", "ord-1", 3) != alarm_id("AUTH_FAIL", "req-1", "ord-1", 4)


def test_errors_sort_before_warns_before_infos():
    alarms = evaluate_alarms(
        events=[ev("AUTH_FAIL", 10.0), ev("ARRIVING", 11.0), ev("RESET_BEGIN", 12.0)],
        epoch=3, now_sim_s=13.0,
    )
    levels = [a["level"] for a in alarms]
    assert levels == sorted(levels, key=lambda name: {"error": 0, "warn": 1, "info": 2}[name])


def test_same_level_sorts_newest_first():
    orders = {
        "ord-1": {"state": STATE_ABORT, "reason": "x", "stamp": 10.0},
        "ord-2": {"state": STATE_ABORT, "reason": "y", "stamp": 20.0},
    }
    stamps = [a["stamp"] for a in evaluate_alarms(orders=orders, epoch=3, now_sim_s=21.0)]
    assert stamps == [20.0, 10.0]


# ── 순수성 ───────────────────────────────────────────────────────────────

def test_evaluate_does_not_mutate_its_inputs():
    events = [ev("AUTH_FAIL", 10.0)]
    orders = {"ord-12": {"state": STATE_ABORT, "reason": "x", "stamp": 50.0}}
    disp = {"paused_item_ids": ["drug-ibu"], "stamp": 60.0}
    before = (repr(events), repr(orders), repr(disp))
    evaluate_alarms(events=events, orders=orders, dispenser=disp, epoch=3, now_sim_s=61.0)
    assert (repr(events), repr(orders), repr(disp)) == before


def test_evaluate_is_deterministic():
    events = [ev("AUTH_FAIL", 10.0), ev("ARRIVING", 11.0)]
    first = evaluate_alarms(events=events, epoch=3, now_sim_s=12.0)
    second = evaluate_alarms(events=events, epoch=3, now_sim_s=12.0)
    assert first == second


def test_module_does_not_import_ros():
    import app.alarms as mod
    src = Path(mod.__file__).read_text(encoding="utf-8")
    for banned in ("import rclpy", "from rclpy", "rokey_p3_interfaces", "std_msgs"):
        assert banned not in src, f"순수 함수 모듈에 {banned} 가 있으면 안 된다"


# ── 리셋이 멈춤 (barrier_failed 를 밖에서 아는 유일한 신호) ───────────────

def test_a_reset_within_the_deadline_is_not_stuck():
    alarms = evaluate_alarms(events=[ev("RESET_BEGIN", 200.0)], epoch=4, now_sim_s=205.0,
                             reset_age_wall_s=RESET_TIMEOUT_WALL_S)
    assert "RESET_STUCK" not in kinds(alarms)
    assert "RESET_IN_PROGRESS" in kinds(alarms), "그동안은 진행 중으로 보인다"


def test_a_reset_past_the_deadline_is_an_error():
    alarms = evaluate_alarms(events=[ev("RESET_BEGIN", 200.0)], epoch=4, now_sim_s=205.0,
                             reset_age_wall_s=RESET_TIMEOUT_WALL_S + 1.0)
    a = by_kind(alarms, "RESET_STUCK")
    assert a["level"] == "error" and "4" in a["message"]


def test_no_reset_means_no_stuck_alarm():
    assert "RESET_STUCK" not in kinds(
        evaluate_alarms(epoch=4, now_sim_s=1.0, reset_age_wall_s=None))


def test_the_stuck_deadline_is_configurable():
    alarms = evaluate_alarms(events=[ev("RESET_BEGIN", 200.0)], epoch=4, now_sim_s=205.0,
                             reset_age_wall_s=10.0, reset_timeout_wall_s=5.0)
    assert "RESET_STUCK" in kinds(alarms)


# ── pharmacy_only 의 정상 완주는 경고가 아니다 ──────────────────────────

PHARMACY_ONLY = "pharmacy_only"


def order_row(state, reason, **kw):
    row = {"state": state, "reason": reason, "stamp": 18.0, "request_id": "r1"}
    row.update(kw)
    return row


def test_a_pharmacy_only_close_raises_no_alarm():
    """1차 시연이 이 모드다. 경고로 올리면 매 바퀴 성공이 노란 줄로 보인다.

    `trip_fsm.py:733` 은 적재 뒤 도크로 복귀하며 실은 주문을
    `HOLD_RETURN(pharmacy_only)` 로 닫는다. 상태는 맞지만 이상이 아니다.
    """
    orders = {"ord-0001": order_row(STATE_HOLD_RETURN, PHARMACY_ONLY)}
    assert evaluate_alarms(orders=orders, epoch=1, now_sim_s=20.0) == []


@pytest.mark.parametrize("reason", ["auth_mismatch", "goto_rejected", "drain_timeout",
                                    "rejected", ""])
def test_any_other_hold_return_is_still_a_warning(reason):
    """`trip_fsm.py:977` 쪽 HOLD_RETURN 은 진짜 이상이다. 지금대로 warn."""
    orders = {"ord-0001": order_row(STATE_HOLD_RETURN, reason)}
    a = by_kind(evaluate_alarms(orders=orders, epoch=1, now_sim_s=20.0), "HOLD_RETURN")
    assert a["level"] == "warn"


def test_a_mixed_batch_warns_only_about_the_held_order():
    """묶음에서 한 주문은 정상 완주, 다른 주문은 인증 실패로 회수될 수 있다."""
    orders = {
        "ord-0001": order_row(STATE_HOLD_RETURN, PHARMACY_ONLY),
        "ord-0002": order_row(STATE_HOLD_RETURN, "auth_mismatch"),
    }
    alarms = evaluate_alarms(orders=orders, epoch=1, now_sim_s=20.0)
    assert len(alarms) == 1, f"알람이 {len(alarms)}건이다: {[a['kind'] for a in alarms]}"
    assert alarms[0]["order_id"] == "ord-0002"
    assert "auth_mismatch" in alarms[0]["message"]


def test_abort_and_timeout_are_untouched_by_this_rule():
    """다른 종료 상태의 규칙은 건드리지 않는다 — reason 이 pharmacy_only 라도."""
    for state, kind in [(STATE_ABORT, "ABORT"), (STATE_TIMEOUT, "TIMEOUT")]:
        orders = {"ord-0001": order_row(state, PHARMACY_ONLY)}
        a = by_kind(evaluate_alarms(orders=orders, epoch=1, now_sim_s=20.0), kind)
        assert a["level"] == "error"


def test_the_exemption_is_exact_not_a_prefix_match():
    """reason 이 조금 달라도 면제되면, 진짜 이상이 조용히 묻힌다."""
    for reason in ["pharmacy_only_x", "pharmacy", "PHARMACY_ONLY", " pharmacy_only"]:
        orders = {"ord-0001": order_row(STATE_HOLD_RETURN, reason)}
        assert kinds(evaluate_alarms(orders=orders, epoch=1, now_sim_s=20.0)) == {"HOLD_RETURN"}, \
            f"reason {reason!r} 가 면제됐다"


# ── outcome 파생 ─────────────────────────────────────────────────────────

@pytest.mark.parametrize(("state", "reason", "expected"), [
    (STATE_ACCEPTED, "", "accepted"),
    (STATE_IN_PROGRESS, "", "in_progress"),
    (STATE_DELIVERED, "", "delivered"),
    (STATE_SUCCESS, "", "delivered"),
    (STATE_HOLD_RETURN, PHARMACY_ONLY, "pharmacy_done"),
    (STATE_HOLD_RETURN, "auth_mismatch", "held"),
    (STATE_HOLD_RETURN, "", "held"),
    (STATE_ABORT, "gripper_lost", "aborted"),
    (STATE_TIMEOUT, "", "timeout"),
])
def test_outcome_is_one_word_per_case(state, reason, expected):
    from app.alarms import outcome_for

    assert outcome_for(state, reason) == expected


def test_the_alarm_rule_and_outcome_agree():
    """같은 판정 함수를 쓴다. 따로 판정하면 '알람은 없는데 화면은 회수' 가 된다."""
    from app.alarms import is_pharmacy_only_close, outcome_for

    for reason in [PHARMACY_ONLY, "auth_mismatch", "goto_rejected", ""]:
        exempt = is_pharmacy_only_close(STATE_HOLD_RETURN, reason)
        orders = {"ord-0001": order_row(STATE_HOLD_RETURN, reason)}
        alarmed = bool(evaluate_alarms(orders=orders, epoch=1, now_sim_s=20.0))
        assert exempt != alarmed, f"reason {reason!r}: 면제와 알람이 어긋난다"
        assert (outcome_for(STATE_HOLD_RETURN, reason) == "pharmacy_done") == exempt


def test_an_unknown_state_falls_back_to_accepted_not_a_made_up_outcome():
    from app.alarms import outcome_for

    assert outcome_for(99, "") == "accepted"


# ── 지금 낼 수 없는 약품 (선검사 근거) ──────────────────────────────────

def dispenser_with(slots, paused=()):
    return {"paused_item_ids": list(paused), "queue_length": 0,
            "belt_occupied": False, "slots": list(slots), "stamp": 0.0}


def slot(item, count=5, active=True, number=0):
    return {"item_id": item, "slot": number, "lot_id": "", "expiry": "",
            "count": count, "active": active}


def test_a_stocked_item_is_available():
    from app.alarms import unavailable_items

    assert unavailable_items(dispenser_with([slot("drug-amox")])) == set()


def test_a_paused_item_is_unavailable():
    from app.alarms import unavailable_items

    dispenser = dispenser_with([slot("drug-amox")], paused=["drug-amox"])
    assert unavailable_items(dispenser) == {"drug-amox"}


def test_an_empty_slot_makes_the_item_unavailable():
    """실습8: amox 재고 0 인데 요청이 수락됐고 적재에서 ABORT out_of_stock 으로 끝났다."""
    from app.alarms import unavailable_items

    dispenser = dispenser_with([slot("drug-amox", count=0, active=False)])
    assert unavailable_items(dispenser) == {"drug-amox"}


def test_one_empty_slot_does_not_block_when_another_has_stock():
    from app.alarms import unavailable_items

    dispenser = dispenser_with([slot("drug-amox", count=0, active=False, number=0),
                                slot("drug-amox", count=3, active=True, number=1)])
    assert unavailable_items(dispenser) == set()


def test_an_item_that_is_in_no_slot_is_not_blocked():
    """모르는 것으로 거부하지 않는다. 슬롯에 없으면 재고를 판단할 근거가 없다."""
    from app.alarms import unavailable_items

    assert unavailable_items(dispenser_with([slot("drug-ibu")])) == set()


def test_an_inactive_slot_counts_as_unavailable_even_with_stock():
    from app.alarms import unavailable_items

    dispenser = dispenser_with([slot("drug-amox", count=9, active=False)])
    assert unavailable_items(dispenser) == {"drug-amox"}


@pytest.mark.parametrize("dispenser", [None, {}, {"slots": [], "paused_item_ids": []}])
def test_no_dispenser_state_blocks_nothing(dispenser):
    from app.alarms import unavailable_items

    assert unavailable_items(dispenser) == set()


# ── 품목별 가용 재고 ─────────────────────────────────────────────────────

def test_stock_adds_up_across_slots_of_the_same_item():
    from app.alarms import available_stock

    dispenser = dispenser_with([slot("drug-amox", count=3, number=0),
                                slot("drug-amox", count=2, number=1)])
    assert available_stock(dispenser) == {"drug-amox": 5}


def test_an_inactive_slot_contributes_nothing():
    from app.alarms import available_stock

    dispenser = dispenser_with([slot("drug-amox", count=3, number=0),
                                slot("drug-amox", count=9, active=False, number=1)])
    assert available_stock(dispenser) == {"drug-amox": 3}


def test_an_item_with_no_slot_has_no_key_at_all():
    """0 이 아니라 '모른다' 다. 모르는 것으로 거부하지 않는 원칙과 같다."""
    from app.alarms import available_stock

    assert "drug-ibu" not in available_stock(dispenser_with([slot("drug-amox")]))


def test_no_dispenser_means_no_stock_knowledge():
    from app.alarms import available_stock

    assert available_stock(None) == {}


# ── 알람 문구의 목적지는 그 요청의 것이다 (9/23 스텁 한 바퀴, #576) ─────────

def accepted(request_id, mode, destination_id, stamp):
    detail = json.dumps({"mode": mode, "destination_id": destination_id, "orders": []})
    return ev("REQUEST_ACCEPTED", stamp, request_id=request_id, order_id="", detail=detail)


def test_an_old_urgent_alarm_keeps_its_own_destination_when_the_next_trip_opens():
    """긴급(bed_a2) 트립 뒤 병동 묶음(station_a) 트립이 열리자 긴급 알람이 "— station_a" 로 바뀌었다."""
    events = [accepted("r001-0001", 1, "bed_a2", 3.0), ev("ARRIVING", 6.0, request_id="r001-0001", order_id=""),
              accepted("v1-ward", 3, "station_a", 94.0)]
    a = by_kind(evaluate_alarms(events=events, epoch=3, now_sim_s=100.0,
                                destination_id="station_a", trip_request_id="v1-ward"), "URGENT_ARRIVING")
    assert "bed_a2" in a["message"] and "station_a" not in a["message"]


@pytest.mark.parametrize("mode", [0, 2, 3])
def test_arriving_of_a_non_urgent_request_is_not_an_urgent_alarm(mode):
    """api.md 4.1 "긴급 모드만". orchestrator 는 긴급에만 ARRIVING 을 내지만 웹도 지킨다(프론트 재현 9/23)."""
    events = [accepted("req-1", mode, "bed_a1", 1.0), ev("ARRIVING", 5.0, order_id="")]
    assert "URGENT_ARRIVING" not in kinds(evaluate_alarms(events=events, epoch=3, now_sim_s=6.0))


def test_arriving_without_a_known_mode_still_alarms():
    """detail 이 빈 옛 빌드 — 모드를 모르면 orchestrator 를 믿는다."""
    events = [ev("ARRIVING", 5.0)]
    assert "URGENT_ARRIVING" in kinds(evaluate_alarms(events=events, epoch=3, now_sim_s=6.0))


def test_auth_fail_of_a_batch_stop_names_the_request_not_a_question_mark():
    """묶음 정거장의 AUTH_FAIL 에는 order_id 가 없다 — 9/23 에 "station_a 인증 실패 — ?" 로 떴다."""
    events = [accepted("v1-ward", 3, "station_a", 94.0), ev("AUTH_FAIL", 112.0, request_id="v1-ward", order_id="")]
    a = by_kind(evaluate_alarms(events=events, epoch=3, now_sim_s=113.0), "AUTH_FAIL")
    assert a["message"] == "station_a 인증 실패 — v1-ward"


def test_without_detail_only_the_current_trip_borrows_its_destination():
    """옛 빌드(detail 없음): 지금 트립의 이벤트만 지금 목적지를 쓴다. 지난 트립의 것은 "목적지"."""
    events = [ev("AUTH_FAIL", 10.0, request_id="old", order_id="ord-1")]
    a = by_kind(evaluate_alarms(events=events, epoch=3, now_sim_s=11.0,
                                destination_id="bed_b1", trip_request_id="new"), "AUTH_FAIL")
    assert a["message"] == "목적지 인증 실패 — ord-1"
