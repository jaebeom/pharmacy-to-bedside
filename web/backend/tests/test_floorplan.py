"""평면도 API — 지도(/api/map·/api/map/image), 전 구역 자세(/api/zones), AMR 자세(snapshot.robots).

`--map-file` 을 준 실행(병원 월드)에서만 켜진다. 안 주면 지금 동작 그대로다(404, 빈 배열).
"""

from __future__ import annotations

import math
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.floorplan import MapError, load_map, pgm_size
from app.ros_convert import transform_to_pose
from app.ros_spec import apply_update, robot_base_frame
from app.state import WorldState
from tests.test_api import T0, make_client

REPO = Path(__file__).resolve().parents[3]
HOSPITAL_MAP = REPO / "src" / "rokey_p3_navigation" / "config" / "maps" / "hospital.yaml"
HOSPITAL_ZONES = REPO / "src" / "rokey_p3_description" / "config" / "zones.hospital.yaml"


def hospital(**kw):
    return make_client(map_file=str(HOSPITAL_MAP), zones_file=str(HOSPITAL_ZONES), **kw)


# ── 지도를 안 주면 지금 동작 그대로 ──────────────────────────────────────

def test_without_a_map_the_floorplan_is_off():
    client, _ = make_client()
    with client:
        for path in ("/api/map", "/api/map/image"):
            r = client.get(path)
            assert r.status_code == 404, path
            assert r.json()["error"]["code"] == "map_unavailable"
        assert client.get("/api/snapshot").json()["robots"] == []


def test_a_map_that_cannot_be_read_says_why(tmp_path):
    client, _ = make_client(map_file=str(tmp_path / "없다.yaml"))
    with client:
        err = client.get("/api/map").json()["error"]
    assert err["code"] == "map_unavailable"
    assert "없다.yaml" in err["message"]


# ── 지도 ─────────────────────────────────────────────────────────────────

def test_the_hospital_map_is_served_as_the_yaml_says(tmp_path):
    client, _ = hospital()
    with client:
        meta = client.get("/api/map").json()
        image = client.get("/api/map/image")
    assert meta == {"source": "file", "frame": "map", "image_url": "/api/map/image",
                    "width": 859, "height": 534, "resolution": 0.05, "origin": [-12.25, -6.5, 0.0],
                    "negate": 0, "occupied_thresh": 0.65, "free_thresh": 0.196}
    assert image.status_code == 200
    assert image.headers["content-type"] == "application/octet-stream"
    assert image.content == (HOSPITAL_MAP.parent / "hospital.pgm").read_bytes(), "원본 바이트 그대로여야 한다"
    assert image.content.startswith(b"P5\n859 534\n255\n")


def test_pgm_size_skips_comment_lines(tmp_path):
    pgm = tmp_path / "m.pgm"
    pgm.write_bytes("P5\n# 주석\n3 2\n255\n".encode() + bytes(6))
    assert pgm_size(pgm) == (3, 2)
    (tmp_path / "bad.pgm").write_bytes(b"P2\n3 2\n255\n")
    with pytest.raises(MapError):
        pgm_size(tmp_path / "bad.pgm")


def test_a_map_yaml_without_its_image_is_refused(tmp_path):
    y = tmp_path / "m.yaml"
    y.write_text("image: 없다.pgm\nresolution: 0.05\norigin: [0, 0, 0]\n", encoding="utf-8")
    with pytest.raises(MapError, match="이미지가 없다"):
        load_map(y)


def test_zone_poses_land_on_free_cells_of_the_map():
    """좌표 규약(첫 행 = 위)을 틀리면 병상 정차 자세가 벽·모름 칸에 떨어진다."""
    meta = load_map(HOSPITAL_MAP)
    data = meta["image_path"].read_bytes()[len(b"P5\n859 534\n255\n"):]
    w, h, res = meta["width"], meta["height"], meta["resolution"]
    ox, oy = meta["origin"][:2]
    client, _ = hospital()
    with client:
        zones = client.get("/api/zones").json()["zones"]
    beds = [z for z in zones if z["kind"] == "bed"]
    assert len(beds) == 10
    for z in beds:
        col = int((z["x"] - ox) / res)
        row = h - 1 - int((z["y"] - oy) / res)
        assert data[row * w + col] == 254, f"{z['zone_id']} 가 빈 칸이 아니다"


# ── 구역 ─────────────────────────────────────────────────────────────────

def test_zones_lists_every_zone_with_pose_and_labels():
    client, _ = hospital()
    with client:
        body = client.get("/api/zones").json()
    assert (body["source"], body["frame"]) == ("file", "map")
    ids = [z["zone_id"] for z in body["zones"]]
    assert ids == ["bed_a1", "bed_a2", "bed_a3", "bed_a4", "bed_b1", "bed_b2", "bed_b3", "bed_b4",
                   "bed_b5", "bed_b6", "dock_1", "dock_2", "dock_3", "dock_4", "load", "station_a", "station_b",
                   "station_c", "station_d"]
    by_id = {z["zone_id"]: z for z in body["zones"]}
    assert by_id["dock_1"] == {"zone_id": "dock_1", "kind": "dock", "x": -8.995, "y": 4.686, "yaw": -1.571,
                               "group": None, "group_label": None, "ward": None, "ward_label": None,
                               "label": None}
    assert (by_id["bed_b6"]["group_label"], by_id["bed_b6"]["label"]) == ("C2 병실", "D10")


def test_zones_without_pose_have_null_coordinates(tmp_path):
    zones = tmp_path / "zones.yaml"
    zones.write_text("frame: map\nzones:\n  bed_a1: {kind: bed}\n", encoding="utf-8")
    client, _ = make_client(zones_file=str(zones))
    with client:
        z = client.get("/api/zones").json()["zones"][0]
    assert (z["x"], z["y"], z["yaw"]) == (None, None, None)


# ── AMR 자세 ─────────────────────────────────────────────────────────────

def test_mock_parks_the_amr_on_dock_1_when_the_map_is_on():
    client, _ = hospital()
    with client:
        robots = client.get("/api/snapshot").json()["robots"]
    assert robots == [{"robot_id": "amr_1", "x": -8.995, "y": 4.686, "yaw": -1.571, "frame": "map",
                       "age_wall_s": 0.0, "stale": False, "source": "mock", "goal_zone": None,
                       # mock 의 리셋 이벤트에는 robot_id 가 없다 — 첫 트립 전에는 모른다
                       "docked": None, "kind": "amr"}]


def test_a_tf_pose_goes_stale_after_one_second():
    state = WorldState()
    apply_update(state, "robot_pose", {"robot_id": "amr_1", "pose": {"x": 1.0, "y": 2.0, "yaw": 0.5}}, T0)
    fresh = state.snapshot(T0 + timedelta(seconds=0.9))["robots"][0]
    assert (fresh["x"], fresh["y"], fresh["yaw"], fresh["source"], fresh["stale"]) == (1.0, 2.0, 0.5, "tf", False)
    assert state.snapshot(T0 + timedelta(seconds=1.1))["robots"][0]["stale"] is True


def test_transform_to_pose_reads_yaw_and_stamp():
    half = math.pi / 4   # yaw 90° → q = (0, 0, sin 45°, cos 45°)
    t = SimpleNamespace(header=SimpleNamespace(stamp=SimpleNamespace(sec=12, nanosec=500_000_000)),
                        transform=SimpleNamespace(
        translation=SimpleNamespace(x=3.0, y=-1.5, z=0.0),
        rotation=SimpleNamespace(x=0.0, y=0.0, z=math.sin(half), w=math.cos(half))))
    pose = transform_to_pose(t)
    assert (pose["x"], pose["y"]) == (3.0, -1.5)
    assert pose["yaw"] == pytest.approx(math.pi / 2)
    assert pose["stamp"] == 12.5


def test_the_pose_frame_is_the_contract_base_link():
    assert robot_base_frame("amr_1") == "amr_1/base_link"


def test_a_repeated_tf_stamp_is_not_fresh_news():
    """TF 버퍼는 마지막 변환을 계속 준다. stamp 가 그대로면 TF 가 끊긴 것이다 — stale 이 돼야 한다.

    실물 확인(9/23): static_transform_publisher 를 끈 뒤에도 조회가 성공해 age 가 늘 0.1 s 안쪽이었다.
    """
    state = WorldState()
    pose = {"robot_id": "amr_1", "pose": {"x": 1.0, "y": 2.0, "yaw": 0.0, "stamp": 50.0}}
    apply_update(state, "robot_pose", pose, T0)
    apply_update(state, "robot_pose", pose, T0 + timedelta(seconds=1.0))   # 같은 stamp — 끊김
    assert state.snapshot(T0 + timedelta(seconds=1.2))["robots"][0]["stale"] is True
    moved = {"robot_id": "amr_1", "pose": {"x": 1.5, "y": 2.0, "yaw": 0.0, "stamp": 50.2}}
    apply_update(state, "robot_pose", moved, T0 + timedelta(seconds=1.2))
    robot = state.snapshot(T0 + timedelta(seconds=1.3))["robots"][0]
    assert (robot["x"], robot["stale"]) == (1.5, False)
