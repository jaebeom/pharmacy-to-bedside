"""녹화 fixture `hospital_trip.json` — 스텁 스택(실물 오케스트레이터 이벤트)을 record_fixture.py 로 녹화한 것.

프론트가 병원 화면을 mock 으로 만드는 기준 재생본이다. 다시 녹화해도 이 시험이 지키는 것:
긴급 → 병실 묶음 C1 → 병동 묶음 → 리셋, 단계가 계약 순서로 흐르고, 병동 묶음은 스테이션에서 인증된다.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from app.film import STAGE_INDEX
from app.mock import apply_frame
from app.state import WorldState

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
FIXTURE = json.loads((FIXTURES / "hospital_trip.json").read_text(encoding="utf-8"))
NOW = datetime(2026, 9, 23, 12, 0, 0, tzinfo=timezone.utc)


def replay():
    """프레임을 차례로 넣으며 (request_id, stage key) 가 바뀔 때마다 적는다."""
    state = WorldState()
    seen = []
    for frame in FIXTURE["frames"]:
        apply_frame(state, frame, NOW)
        state.note_clock(frame["t"], NOW)
        snap = state.snapshot(NOW)
        mark = ((snap["trip"] or {}).get("request_id"), snap["stage"]["key"])
        if not seen or seen[-1] != mark:
            seen.append(mark)
    return state, seen


def events(request_id):
    return [f["data"]["name"] for f in FIXTURE["frames"]
            if f["kind"] == "event" and f["data"].get("request_id") == request_id]


def test_the_fixture_was_recorded_not_written_by_hand():
    assert any("record_fixture.py" in note for note in FIXTURE["notes"])
    assert FIXTURE["frames"][0]["t"] == 0.0


def test_three_trips_then_a_reset():
    names = [f["data"]["name"] for f in FIXTURE["frames"] if f["kind"] == "event"]
    accepted = [f["data"]["request_id"] for f in FIXTURE["frames"]
                if f["kind"] == "event" and f["data"]["name"] == "REQUEST_ACCEPTED"]
    assert accepted[:3] == ["r001-0001", "web-c1", "web-ward"]
    assert "RESET_BEGIN" in names and "RESET_DONE" in names


def test_the_room_batch_visits_three_beds_and_the_ward_batch_authenticates_once_at_the_station():
    assert events("web-c1").count("AUTH_OK") == 3
    assert events("web-c1").count("CABINET_LOCKED") == 3
    ward = events("web-ward")
    assert ward.count("AUTH_OK") == 1 and "AUTH_FAIL" not in ward
    assert ward.count("CABINET_LOCKED") == 2


def test_each_trip_moves_forward_through_the_stages():
    """배송·도착은 병상마다 되풀이되지만(병실 묶음) 요청부터 복귀까지 거꾸로 가지 않는다."""
    _, seen = replay()
    for rid in ("r001-0001", "web-c1", "web-ward"):
        keys = [key for r, key in seen if r == rid]
        assert keys[0] == "request" and keys[-1] == "return", (rid, keys)
        order = [STAGE_INDEX[k] for k in keys]
        allowed_back = {(STAGE_INDEX["arrive"], STAGE_INDEX["deliver"])}
        assert all(b >= a or (a, b) in allowed_back for a, b in zip(order, order[1:], strict=False)), (rid, keys)
    assert [key for r, key in seen if r == "web-c1"].count("deliver") == 3


def test_after_replay_the_reset_opened_a_new_epoch():
    state, _ = replay()
    assert state.epoch == FIXTURE["start_epoch"] + 1
