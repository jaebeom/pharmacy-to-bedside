"""api.md 와 서버가 어긋나지 않는지 본다.

계약 문서는 프론트가 **유일하게** 보는 것이다. 서버에 필드를 더하고 문서를 안 고치면
프론트는 그 필드가 있는 줄도 모르고, 반대로 문서에만 있는 필드를 프론트가 기다리면
영원히 안 온다. 둘 다 테스트로는 안 잡히고 화면에서만 깨진다.

이 파일은 그 표류를 막는다. 문서를 고치기 싫어서 필드를 안 만드는 일이 없도록,
**검사는 "문서에 언급이 있는가" 수준**으로만 한다 — 형식까지 맞추라고 하지 않는다.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.main import LOG_LEVELS, REJECT_CODES
from app.mock import apply_frame, load_fixture
from app.live_sensors import LiveSensors
from app.state import WorldState

DOC = (Path(__file__).resolve().parents[2] / "api.md").read_text(encoding="utf-8")
NOW = datetime(2026, 9, 17, 8, 0, 0, tzinfo=timezone.utc)
FLEET = ('{"v":1,"stamp":{"sec":5,"nanosec":0},"frame_id":"map","poses":['
         '{"id":"amr_2","kind":"spare_amr","x":1.0,"y":2.0,"yaw":0.0},'
         '{"id":"dummy_1","kind":"dummy","x":3.0,"y":4.0,"yaw":0.0}]}')


def populated_snapshot() -> dict:
    """모든 가지가 채워진 snapshot — null 이면 중첩 키가 안 보여서 검사가 헐거워진다."""
    state = WorldState(show_evaluator=True)
    for frame in load_fixture()["frames"]:
        if frame["kind"] == "event" and frame["data"]["name"] == "DOCKED":
            break
        apply_frame(state, frame, NOW)
        state.note_clock(frame["t"], NOW)
    state.note_cabinet("ord-0001", "bed_a1", True, NOW)
    state.note_robot_pose("amr_1", {"x": 1.0, "y": 2.0, "yaw": 0.0}, NOW)
    state.note_tag_read({"kind": 3, "tag_id": "cn-0007", "status": 0, "stamp": 1.0}, NOW)
    # AMR 손 카메라 판독 셋(§1.12) — 종류마다 info 키가 달라서 다 채운다.
    for kind, tag in ((2, "ord-0001"), (0, "2001"), (1, "station_b")):
        state.note_qr_read("amr_1", {"kind": kind, "tag_id": tag, "status": 0, "stamp": 2.0}, NOW)
    state.note_speed_limit({"speed_limit_pct": 50.0, "stop_reason": None, "stamp": 1.0}, NOW)
    state.note_fleet_poses(FLEET, NOW)
    state.note_sim_running(True, NOW)
    state.live = LiveSensors()
    state.live.note_scan({"robot_id": "amr_1", "frame": "map", "stamp": 1.0,
                          "points": [[1.0, 2.0]], "range_max": 10.0}, NOW)
    return state.snapshot(NOW)


def walk(obj, prefix=""):
    if isinstance(obj, dict):
        for key, value in obj.items():
            yield prefix + key
            yield from walk(value, prefix + key + ".")
    elif isinstance(obj, list) and obj:
        yield from walk(obj[0], prefix)


SNAPSHOT_KEYS = sorted(set(walk(populated_snapshot())))


def test_the_snapshot_is_not_trivially_empty():
    """검사가 뜻을 가지려면 가지가 실제로 채워져 있어야 한다."""
    snap = populated_snapshot()
    assert snap["trip"] is not None
    assert snap["dispenser"] is not None
    assert snap["belt"] is not None
    assert snap["cabinet"] is not None
    assert len(SNAPSHOT_KEYS) > 80


@pytest.mark.parametrize("path", SNAPSHOT_KEYS)
def test_every_snapshot_field_is_mentioned_in_the_contract(path):
    leaf = path.split(".")[-1]
    assert re.search(rf'"{re.escape(leaf)}"', DOC), (
        f"snapshot 이 내는 `{path}` 가 api.md 에 없다. "
        "서버에 필드를 더했으면 계약도 고쳐야 한다 — 프론트는 문서만 본다."
    )


@pytest.mark.parametrize("code", REJECT_CODES)
def test_every_reject_code_is_documented(code):
    assert f"`{code}`" in DOC, f"거부 코드 `{code}` 가 api.md 에 없다"


@pytest.mark.parametrize("level", sorted(LOG_LEVELS))
def test_every_log_level_is_documented(level):
    assert level in DOC


def test_every_alarm_kind_is_documented():
    from app.alarms import TERMINAL_STATES

    kinds = {
        "URGENT_ARRIVING", "AUTH_FAIL", "DISPENSER_PAUSED", "REFILL_FAILED",
        "STATUS_STALE", "CLOCK_STOPPED", "RESET_IN_PROGRESS", "RESET_STUCK",
        *(kind for kind, _ in TERMINAL_STATES.values()),
    }
    missing = sorted(k for k in kinds if k not in DOC)
    assert not missing, f"알람 종류가 api.md 에 없다: {missing}"


def test_every_fault_name_is_documented():
    from app.faults import SIMPLE_FAULTS, STALE_KEYS

    missing = [n for n in SIMPLE_FAULTS if f"`{n}`" not in DOC]
    assert not missing, f"고장 이름이 api.md 에 없다: {missing}"
    assert all(key in DOC for key in STALE_KEYS)


def test_every_cli_flag_is_documented():
    from app.main import build_parser

    flags = [a for action in build_parser()._actions for a in action.option_strings
             if a.startswith("--") and a != "--help"]
    missing = [f for f in flags if f"`{f}`" not in DOC]
    assert not missing, f"실행 인자가 api.md 에 없다: {missing}"


def test_the_documented_thresholds_match_the_code():
    """문서의 숫자와 코드의 상수가 갈라지면, 둘 다 맞아 보이는데 화면만 틀린다."""
    from app.alarms import (
        CLOCK_STALE_WALL_S,
        DISPENSER_STALE_WALL_S,
        RESET_SETTLE_WALL_S,
        STALE_WALL_S,
    )

    for value, label in [(STALE_WALL_S, "1.0"), (CLOCK_STALE_WALL_S, "2.0"),
                         (DISPENSER_STALE_WALL_S, "3.0"), (RESET_SETTLE_WALL_S, "3.5")]:
        assert f"{value:.1f}" == label, f"상수가 바뀌었다 — api.md 의 {label} s 도 고쳐라"
        assert f"{label} s" in DOC, f"{label} s 임계가 api.md 에 없다"
