"""Isaac 타임라인 Play/Stop `/p3/sim_running` → snapshot.sim_running(api.md §1.11, 카드 ④). ROS 없이 돈다."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.ros_spec import apply_update, subscriptions
from app.state import WorldState

NOW = datetime(2026, 9, 27, 11, 0, 0, tzinfo=timezone.utc)


def test_the_topic_is_subscribed_volatile_like_the_stage_publishes_it():
    row = {s.topic: s for s in subscriptions("amr_1")}["/p3/sim_running"]
    assert (row.kind, row.msg, row.qos, row.depth, row.signal_key) == ("sim_running", "Bool", "reliable_qos", 1, None)


def test_null_until_received_then_play_stop_then_stale_after_3_s():
    state = WorldState()
    assert state.snapshot(NOW)["sim_running"] is None
    apply_update(state, "sim_running", True, NOW)
    assert state.snapshot(NOW + timedelta(seconds=1))["sim_running"] == {
        "value": True, "wall": "2026-09-27T11:00:00.000Z", "age_wall_s": 1.0, "stale": False}
    apply_update(state, "sim_running", False, NOW + timedelta(seconds=2))
    assert state.snapshot(NOW + timedelta(seconds=2))["sim_running"]["value"] is False
    gone = state.snapshot(NOW + timedelta(seconds=5.5))["sim_running"]
    assert gone["stale"] is True and gone["value"] is False          # Isaac 없음 — 마지막 값은 남긴다


def test_sim_running_is_not_one_of_the_five_signals():
    state = WorldState()
    apply_update(state, "sim_running", True, NOW)
    snap = state.snapshot(NOW + timedelta(seconds=10))
    assert "sim_running" not in snap["signals"]
    assert not [a for a in snap["alarms"] if a["kind"] == "STATUS_STALE"]
