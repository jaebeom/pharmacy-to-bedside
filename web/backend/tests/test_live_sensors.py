"""카메라 MJPEG·라이다 스캔 실시간 표시(api.md §1.8). ROS·Pillow 없이 돈다.

기본은 꺼짐이고, 켜도 카메라는 보는 사람이 있을 때만 받는다 — 촬영 때만 켜서 rtf 에 손대지 않기 위해서다.
JPEG 인코더(Pillow)는 CI 환경에 없다(새 의존성 금지). 여기서는 가짜 인코더를 끼운다.
실제 인코딩과 rclpy 배선은 `test_live_sensors_ros.py`(ros 마커)가 본다.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app import live_sensors as L
from app.main import create_app
from app.ros_convert import image_to_dict, pouch_array_to_list
from app.ros_spec import apply_update
from app.state import WorldState

NOW = datetime(2026, 9, 25, 3, 0, 0, tzinfo=timezone.utc)
JPEG_HEAD = b"\xff\xd8"


def fake_encoder(frame):
    """인코더 자리. 프레임 모양만 검사하고 표식 바이트를 돌려준다."""
    L.check_frame(frame)
    return JPEG_HEAD + bytes([frame["data"][0]])


@pytest.fixture(autouse=True)
def no_pillow(monkeypatch):
    """CI 와 같게: 앱이 만드는 LiveSensors 도 가짜 인코더를 쓰고, 인코더는 있다고 본다."""
    monkeypatch.setattr(L, "encode_jpeg", fake_encoder)
    monkeypatch.setattr(L, "available", lambda: (True, ""))


def frame(width=1280, height=800, encoding="rgb8", channels=3, value=100):
    return {"data": bytes([value]) * (width * height * channels), "width": width, "height": height,
            "encoding": encoding,
            "step": width * channels, "stamp": 1.0}


# ── 스캔 ─────────────────────────────────────────────────────────────────

def test_scan_points_drop_invalid_ranges_and_cap_the_count():
    ranges = [1.0] * 1000 + [math.inf, math.nan, 0.01, 99.0]
    points = L.scan_points(ranges, 0.0, 2 * math.pi / 1000, 0.1, 30.0)
    assert 0 < len(points) <= L.SCAN_MAX_POINTS
    assert all(abs(math.hypot(x, y) - 1.0) < 0.01 for x, y in points)


def test_scan_points_move_into_the_map_with_the_scan_pose():
    # 정면 한 줄기(각 0, 거리 2)가 yaw 90° 로 선 로봇에서는 map +y 쪽이다
    points = L.scan_points([2.0], 0.0, 0.1, 0.1, 10.0, pose=(5.0, 1.0, math.pi / 2))
    assert points == [[5.0, 3.0]]


# ── 프레임 ───────────────────────────────────────────────────────────────

def test_supported_encodings_pass_the_shape_check():
    for encoding, channels in (("rgb8", 3), ("bgr8", 3), ("rgba8", 4), ("bgra8", 4), ("mono8", 1)):
        assert L.check_frame(frame(8, 4, encoding, channels))[0] == 8 * channels


def test_a_padded_row_step_passes_and_a_short_step_does_not():
    assert L.check_frame({"data": b"\x00" * 40, "width": 8, "height": 4, "encoding": "mono8", "step": 10})[0] == 10
    with pytest.raises(ValueError):
        L.check_frame({"data": b"\x00" * 40, "width": 8, "height": 4, "encoding": "rgb8", "step": 10})


def test_an_unknown_encoding_or_short_buffer_is_refused():
    with pytest.raises(ValueError):
        L.check_frame(frame(8, 8, "16UC1", 2))
    short = frame(8, 8)
    short["data"] = short["data"][:10]
    with pytest.raises(ValueError):
        L.check_frame(short)


def test_frames_are_only_kept_while_someone_watches_and_at_most_5_fps():
    live = L.LiveSensors()
    assert not live.due("amr_hand", 0.0)                  # 아무도 안 본다 — 복사도 안 한다
    assert not live.note_frame("amr_hand", frame(), NOW, 0.0)
    assert live.acquire("amr_hand")
    assert live.wanted_images() == {"amr_hand"}
    assert live.note_frame("amr_hand", frame(), NOW, 0.0)
    assert not live.due("amr_hand", 0.1)                  # 0.2 s 안에 또 오면 버린다
    assert live.due("amr_hand", 0.2)
    live.release("amr_hand")
    assert live.wanted_images() == set()
    assert live.jpeg("amr_hand") is None                  # 다 나가면 프레임을 들고 있지 않는다


def test_viewers_are_capped_per_camera():
    live = L.LiveSensors()
    assert all(live.acquire("m0609_hand") for _ in range(L.MAX_VIEWERS))
    assert not live.acquire("m0609_hand")
    assert live.acquire("amr_hand")


def test_a_frame_is_encoded_once_and_shared():
    calls = []
    live = L.LiveSensors(encoder=lambda f: calls.append(1) or fake_encoder(f))
    live.acquire("amr_hand")
    live.note_frame("amr_hand", frame(), NOW, 0.0)
    first = live.jpeg("amr_hand")
    assert live.jpeg("amr_hand") is first                 # 같은 프레임이면 다시 인코딩하지 않는다
    assert len(calls) == 1
    live.note_frame("amr_hand", frame(value=200), NOW, 1.0)
    assert live.jpeg("amr_hand") == (first[0] + 1, JPEG_HEAD + b"\xc8")
    assert len(calls) == 2


def test_the_camera_list_carries_text_overlays():
    live = L.LiveSensors()
    live.note_tag("amr_hand", {"tag_id": "pt-1001", "status": 0, "stamp": 3.0})
    live.note_pouches("amr_hand", [{"order_id": "ord-0001", "confidence": 0.91234, "slot_index": 0}])
    read = {"tag_id": "cn-0007", "status": "ok", "stamp": 5.0, "wall": "x"}
    cams = {c["name"]: c for c in live.cameras(NOW, container_read=read)}
    assert cams["amr_hand"]["overlay"] == {
        "tag": {"tag_id": "pt-1001", "status": "ok", "stamp": 3.0},
        "pouches": [{"order_id": "ord-0001", "confidence": 0.912, "slot_index": 0}]}
    assert cams["m0609_hand"]["overlay"]["tag"] == {"tag_id": "cn-0007", "status": "ok", "stamp": 5.0}
    assert cams["amr_hand"]["stale"] is True and cams["amr_hand"]["width"] is None   # 프레임 전


# ── snapshot·배선 ─────────────────────────────────────────────────────────

def test_the_snapshot_scan_is_null_unless_live_sensors_are_on():
    state = WorldState()
    apply_update(state, "scan", {"robot_id": "amr_1"}, NOW)     # 꺼져 있으면 버린다
    assert state.snapshot(NOW)["scan"] is None
    state.live = L.LiveSensors()
    apply_update(state, "scan", {"robot_id": "amr_1", "frame": "map", "stamp": 4.0,
                                 "points": [[1.0, 2.0]], "range_max": 10.0}, NOW)
    scan = state.snapshot(NOW + timedelta(seconds=3))["scan"]
    assert scan["points"] == [[1.0, 2.0]] and scan["frame"] == "map"
    assert scan["stale"] is True                                  # 2 s 넘게 안 왔다


def test_converters_copy_the_image_and_keep_only_text_fields_of_detections():
    header = SimpleNamespace(stamp=SimpleNamespace(sec=2, nanosec=0))
    msg = SimpleNamespace(header=header, data=bytearray(b"\x01\x02"), width=1, height=1,
                          encoding="mono8", step=1)
    out = image_to_dict(msg)
    msg.data[0] = 9
    assert out["data"] == b"\x01\x02" and out["stamp"] == 2.0
    det = SimpleNamespace(order_id="ord-0003", confidence=0.5, slot_index=2, pose=object())
    assert pouch_array_to_list(SimpleNamespace(detections=[det])) == [
        {"order_id": "ord-0003", "confidence": 0.5, "slot_index": 2}]


# ── API ──────────────────────────────────────────────────────────────────

def test_the_api_is_off_by_default():
    client = TestClient(create_app(mock=True, autostart=False))
    assert client.get("/api/cameras").json() == {"enabled": False, "limits": L.limits(), "cameras": []}
    for path in ("/api/cameras/amr_hand/stream", "/api/cameras/amr_hand/frame.jpg"):
        res = client.get(path)
        assert res.status_code == 404 and res.json()["error"]["code"] == "live_sensors_off"
    assert client.get("/api/snapshot").json()["scan"] is None


def test_frame_jpg_returns_the_latest_frame_and_limits_viewers():
    app = create_app(mock=True, autostart=False, live=True)
    live = app.state.world.live
    client = TestClient(app)
    live.acquire("amr_hand")
    live.note_frame("amr_hand", frame(), NOW, 0.0)
    res = client.get("/api/cameras/amr_hand/frame.jpg")
    assert res.status_code == 200 and res.headers["content-type"] == "image/jpeg"
    assert res.content == JPEG_HEAD + b"d"                        # 가짜 인코더: 첫 바이트 100
    assert live.wanted_images() == {"amr_hand"}                  # 한 장 요청은 제 자리를 돌려놓았다
    live.acquire("amr_hand"), live.acquire("amr_hand")
    assert client.get("/api/cameras/amr_hand/stream").status_code == 429
    res = client.get("/api/cameras/front/stream")
    assert res.status_code == 404 and res.json()["error"]["code"] == "unknown_camera"


def test_live_sensors_turn_themselves_off_without_an_encoder(monkeypatch, capsys):
    monkeypatch.setattr(L, "available", lambda: (False, "Pillow 가 없다"))
    app = create_app(mock=True, autostart=False, live=True)
    assert app.state.world.live is None
    assert "--live-sensors 를 끈다: Pillow 가 없다" in capsys.readouterr().out
    assert TestClient(app).get("/api/cameras").json()["enabled"] is False
