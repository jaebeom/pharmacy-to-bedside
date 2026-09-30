"""감속기 속도 제한 → snapshot.signals.speed_limit·WS `speed_limit`(api.md §1.9). ROS 없이 돈다."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.ros_convert import speed_limit_to_dict
from app.ros_spec import apply_update, subscriptions
from app.state import WorldState

NOW = datetime(2026, 9, 27, 9, 0, 0, tzinfo=timezone.utc)


def msg(value, percentage=True, sec=12):
    return SimpleNamespace(speed_limit=value, percentage=percentage,
                           header=SimpleNamespace(stamp=SimpleNamespace(sec=sec, nanosec=0)))


@pytest.mark.parametrize("value,percentage,pct,reason", [
    (50.0, True, 50.0, None),              # 근접 감속
    (100.0, True, 100.0, None),
    (0.0, True, 100.0, None),              # Nav2 에서 0 은 "제한 없음"
    (1.0, True, 1.0, "obstacle_ahead"),    # 감속기 정지 규칙(STOP_PERCENT)
    (0.5, False, None, None),              # m/s 로 온 값 — 비율을 모른다
])
def test_the_limit_is_read_as_a_percentage_and_a_stop_reason(value, percentage, pct, reason):
    out = speed_limit_to_dict(msg(value, percentage))
    assert (out["speed_limit_pct"], out["stop_reason"], out["stamp"]) == (pct, reason, 12.0)


def test_the_topic_is_subscribed_like_the_governor_publishes_it():
    row = {s.topic: s for s in subscriptions("amr_1")}["/amr_1/speed_limit"]
    assert (row.kind, row.msg, row.qos, row.depth) == ("speed_limit", "SpeedLimit", "latched_qos", 1)


def test_the_snapshot_has_no_key_until_a_limit_arrives_then_goes_stale_after_3_s():
    state = WorldState()
    assert "speed_limit" not in state.snapshot(NOW)["signals"]
    apply_update(state, "speed_limit", speed_limit_to_dict(msg(1.0)), NOW)
    view = state.snapshot(NOW + timedelta(seconds=2))["signals"]["speed_limit"]
    assert view == {"speed_limit_pct": 1.0, "stop_reason": "obstacle_ahead",
                    "wall": "2026-09-27T09:00:00.000Z", "age_wall_s": 2.0, "stale": False}
    assert state.snapshot(NOW + timedelta(seconds=3.5))["signals"]["speed_limit"]["stale"] is True


def test_a_quiet_speed_limit_does_not_raise_status_stale():
    state = WorldState()
    apply_update(state, "speed_limit", speed_limit_to_dict(msg(50.0)), NOW)
    alarms = state.snapshot(NOW + timedelta(seconds=10))["alarms"]
    assert not [a for a in alarms if a["kind"] == "STATUS_STALE"]


def test_the_socket_sends_speed_limit_only_when_it_changes():
    app = create_app(mock=True, autostart=False)
    state, hub = app.state.world, app.state.hub
    client = TestClient(app)
    with client, client.websocket_connect("/ws") as ws:
        assert ws.receive_json()["type"] == "hello"
        apply_update(state, "speed_limit", speed_limit_to_dict(msg(50.0)), datetime.now(timezone.utc))
        hub.mark_dirty()
        kinds = [ws.receive_json() for _ in range(3)]
        sent = [m for m in kinds if m["type"] == "speed_limit"]
        assert len(sent) == 1 and sent[0]["data"]["speed_limit_pct"] == 50.0
        # 같은 값이 다시 와도(1 Hz 재발행) 따로 보내지 않는다
        apply_update(state, "speed_limit", speed_limit_to_dict(msg(50.0)), datetime.now(timezone.utc))
        hub.mark_dirty()
        again = [ws.receive_json() for _ in range(2)]
        assert not [m for m in again if m["type"] == "speed_limit"]
        apply_update(state, "speed_limit", speed_limit_to_dict(msg(1.0)), datetime.now(timezone.utc))
        hub.mark_dirty()
        later = [ws.receive_json() for _ in range(3)]
        stop = [m for m in later if m["type"] == "speed_limit"]
        assert len(stop) == 1 and stop[0]["data"]["stop_reason"] == "obstacle_ahead"


# ── 알람 OBSTACLE_STOP(카드 ③) ─────────────────────────────────────────

def stop_alarms(state, at):
    return [a for a in state.snapshot(at)["alarms"] if a["kind"] == "OBSTACLE_STOP"]


def test_a_stop_that_lasts_5_s_raises_obstacle_stop_and_clears_on_resume():
    state = WorldState()
    for second in range(0, 7):                      # 1 Hz 재발행 — 정지 시작 시각은 첫 줄이다
        apply_update(state, "speed_limit", speed_limit_to_dict(msg(1.0)), NOW + timedelta(seconds=second))
    assert not stop_alarms(state, NOW + timedelta(seconds=4.9))
    [alarm] = stop_alarms(state, NOW + timedelta(seconds=6.2))
    assert alarm["level"] == "warn" and alarm["message"] == "AMR 정지 — 앞 장애물 (6.2 s)"
    apply_update(state, "speed_limit", speed_limit_to_dict(msg(50.0)), NOW + timedelta(seconds=7))
    assert not stop_alarms(state, NOW + timedelta(seconds=7.5))
    # 다시 멈추면 시각을 새로 센다
    apply_update(state, "speed_limit", speed_limit_to_dict(msg(1.0)), NOW + timedelta(seconds=8))
    assert not stop_alarms(state, NOW + timedelta(seconds=10))


def test_a_stale_stop_is_not_alarmed():
    state = WorldState()
    apply_update(state, "speed_limit", speed_limit_to_dict(msg(1.0)), NOW)
    assert not stop_alarms(state, NOW + timedelta(seconds=10))    # 3 s 넘게 안 왔다 — 모른다


# ── /p3/alerts(카드 ③, 시뮬통합 #757) ────────────────────────────────────

import json  # noqa: E402

from app.alarms import parse_p3_alert  # noqa: E402


def alert(kind, detail="1/3 NOT_ARRIVED, 10 s 뒤 재시도", robot="amr_1"):
    return json.dumps({"kind": kind, "robot": robot, "detail": detail, "sim": 12.5, "wall": 1790000000.0})


def p3_alarms(state, at):
    return {a["kind"]: a for a in state.snapshot(at)["alarms"]
            if a["kind"] in ("DOCK_RETRY", "DOCK_GIVEUP", "MAP_GUARD_INTERVENE", "MAP_GUARD_GIVEUP")}


def test_alert_lines_are_parsed_and_junk_is_dropped():
    assert parse_p3_alert(alert("DOCK_RETRY")) == {
        "kind": "DOCK_RETRY", "robot": "amr_1", "detail": "1/3 NOT_ARRIVED, 10 s 뒤 재시도", "sim": 12.5}
    for text in (None, "", "{", "[]", alert("DOCK_EXPLODED"), '{"kind":"DOCK_RETRY","sim":true}'):
        parsed = parse_p3_alert(text)
        assert parsed is None or parsed["sim"] == 0.0


def test_the_alerts_topic_is_subscribed_latched_depth_20():
    row = {s.topic: s for s in subscriptions("amr_1")}["/p3/alerts"]
    assert (row.kind, row.msg, row.qos, row.depth) == ("p3_alert", "String", "latched_qos", 20)


def test_retry_and_intervene_last_60_s_and_giveups_last_until_reset():
    state = WorldState()
    for kind in ("DOCK_RETRY", "MAP_GUARD_INTERVENE", "DOCK_GIVEUP", "MAP_GUARD_GIVEUP"):
        apply_update(state, "p3_alert", alert(kind, detail=""), NOW)
    now = p3_alarms(state, NOW + timedelta(seconds=30))
    assert {k: a["level"] for k, a in now.items()} == {
        "DOCK_RETRY": "warn", "MAP_GUARD_INTERVENE": "warn", "DOCK_GIVEUP": "error", "MAP_GUARD_GIVEUP": "error"}
    assert now["DOCK_GIVEUP"]["message"] == "도킹 포기 — amr_1" and now["DOCK_GIVEUP"]["order_id"] == "amr_1"
    assert now["MAP_GUARD_GIVEUP"]["message"] == "지도 미수신 — amr_1"
    later = p3_alarms(state, NOW + timedelta(seconds=90))
    assert set(later) == {"DOCK_GIVEUP", "MAP_GUARD_GIVEUP"}          # 재시도·개입은 지나갔다
    state.note_event({"name": "RESET_BEGIN", "epoch": 2, "stamp": 0.0}, NOW + timedelta(seconds=100))
    assert p3_alarms(state, NOW + timedelta(seconds=101)) == {}         # 포기는 리셋이 지운다


def test_a_newer_alert_of_the_same_kind_replaces_the_older_one():
    state = WorldState()
    apply_update(state, "p3_alert", alert("DOCK_RETRY", "1/3 …"), NOW)
    apply_update(state, "p3_alert", alert("DOCK_RETRY", "2/3 …"), NOW + timedelta(seconds=50))
    [retry] = [a for a in state.snapshot(NOW + timedelta(seconds=100))["alarms"] if a["kind"] == "DOCK_RETRY"]
    assert retry["message"] == "도킹 재시도 — amr_1: 2/3 …"
