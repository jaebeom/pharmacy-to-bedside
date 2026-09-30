"""여벌 AMR·더미 자리 `/isaac/fleet/poses` → robots[]·dummies[] (api.md §1.6). ROS 없이 돈다."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from app.fleet_poses import parse_fleet_poses
from app.ros_spec import apply_update, subscriptions
from app.state import WorldState

NOW = datetime(2026, 9, 27, 10, 0, 0, tzinfo=timezone.utc)


def message(*poses, sec=10, frame="map", v=1):
    return json.dumps({"v": v, "stamp": {"sec": sec, "nanosec": 500_000_000}, "frame_id": frame,
                       "poses": list(poses)})


def pose(who, kind, x=1.0, y=2.0, yaw=0.5):
    return {"id": who, "kind": kind, "x": x, "y": y, "yaw": yaw}


def test_the_stage_format_is_parsed():
    parsed = parse_fleet_poses(message(pose("amr_2", "spare_amr"), pose("dummy_1", "dummy", 3, 4, 0)))
    assert parsed == {"stamp": 10.5, "poses": [
        {"id": "amr_2", "kind": "spare_amr", "x": 1.0, "y": 2.0, "yaw": 0.5},
        {"id": "dummy_1", "kind": "dummy", "x": 3.0, "y": 4.0, "yaw": 0.0}]}


def test_bad_messages_and_items_are_dropped_without_raising():
    for text in (None, "", "{", "[]", message(v=2), message(frame="odom"), '{"v":1,"frame_id":"map"}'):
        assert parse_fleet_poses(text) is None
    parsed = parse_fleet_poses(message(
        pose("amr_2", "spare_amr"), pose("amr_2", "spare_amr"),              # 같은 id 두 번 — 앞의 것
        pose("x", "robot"), pose("", "dummy"), {"id": "d", "kind": "dummy", "x": "1", "y": 0, "yaw": 0},
        {"id": "n", "kind": "dummy", "x": float("nan"), "y": 0, "yaw": 0}, "junk"))
    assert [p["id"] for p in parsed["poses"]] == ["amr_2"]


def test_the_topic_row_matches_the_stage_qos():
    row = {s.topic: s for s in subscriptions("amr_1")}["/isaac/fleet/poses"]
    assert (row.kind, row.msg, row.qos, row.depth) == ("fleet_poses", "String", "reliable_qos", 1)


def test_spares_join_robots_and_dummies_get_their_own_list():
    state = WorldState()
    state.note_robot_pose("amr_1", {"x": 0.0, "y": 0.0, "yaw": 0.0}, NOW)
    apply_update(state, "fleet_poses", message(pose("amr_1", "spare_amr", 9, 9),   # 주 AMR — TF 가 기준
                                               pose("amr_3", "spare_amr"), pose("amr_2", "spare_amr", 5, 6),
                                               pose("dummy_1", "dummy", 7, 8)), NOW)
    snap = state.snapshot(NOW)
    assert [(r["robot_id"], r["kind"], r["source"]) for r in snap["robots"]] == [
        ("amr_1", "amr", "tf"), ("amr_2", "spare_amr", "fleet_poses"), ("amr_3", "spare_amr", "fleet_poses")]
    assert snap["robots"][0]["x"] == 0.0
    spare = snap["robots"][1]
    assert (spare["x"], spare["y"], spare["docked"], spare["goal_zone"]) == (5.0, 6.0, None, None)
    assert snap["dummies"] == [{"id": "dummy_1", "kind": "dummy", "x": 7.0, "y": 8.0, "yaw": 0.5,
                                "frame": "map", "age_wall_s": 0.0, "stale": False, "source": "fleet_poses"}]


def test_same_stamp_is_not_news_and_old_poses_go_stale():
    state = WorldState()
    apply_update(state, "fleet_poses", message(pose("dummy_1", "dummy")), NOW)
    apply_update(state, "fleet_poses", message(pose("dummy_1", "dummy")), NOW + timedelta(seconds=2))
    assert state.snapshot(NOW + timedelta(seconds=2))["dummies"][0]["stale"] is True   # 같은 stamp 는 갱신 아님
    apply_update(state, "fleet_poses", message(sec=11), NOW + timedelta(seconds=3))    # 빈 목록 — 사라졌다
    assert state.snapshot(NOW + timedelta(seconds=3))["dummies"] == []


def test_without_the_topic_nothing_changes():
    snap = WorldState().snapshot(NOW)
    assert snap["dummies"] == [] and snap["robots"] == []
