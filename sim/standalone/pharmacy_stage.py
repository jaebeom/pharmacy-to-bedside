"""Stage 0.7: pharmacy room in an empty world. Medicine shelf, 2-axis rail, dispenser with refill inlets and outlet,
belt through the wall to the loading spot.

Run in an Isaac shell (see sim/README.md, "0.7단계"):
    ~/isaacsim/python.sh sim/standalone/pharmacy_stage.py --mode selfdemo --loop 0
    ~/isaacsim/python.sh sim/standalone/pharmacy_stage.py --mode ros --order-pool /abs/order_pool.yaml

Belt: Isaac Sim 5.1's own conveyor extension (isaacsim.asset.gen.conveyor), used the way its 5.1.0 test does:
a kinematic rigid collision box, omni.kit.commands "CreateConveyorBelt", speed through the graph variable
"graph:variable:Velocity" (the IsaacConveyor node writes PhysxSurfaceVelocityAPI). We do not implement belt physics.
End stop: when the pouch reaches the end zone the belt speed goes to 0; when it has settled, at_end and POUCH_AT_END.

--mode ros: the JSON topics of sim/README.md "Isaac ↔ ROS 어댑터 인터페이스" on std_msgs/String (dispense and
reset request/response, belt 5 Hz, events). An adapter on system ROS maps them to the contract types.
--mode selfdemo: no ROS besides /clock. Dispense -> belt -> at_end -> after --pick-delay-s remove the pouch (a pick
stand-in) -> next dispense, --loop times.
Stop with SIGINT only. Importing this module does not start Isaac.
"""

import argparse
import hashlib
import itertools
import json
import math
import os
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import minimal_clock as clock  # noqa: E402  (/clock graph, SIGINT flag, env summary)
import m0609_refill_stage as refill  # noqa: E402  (app config, light, livestream default, app_state log)
from p3sim import amr_base as amrlib  # noqa: E402
from p3sim import belt as beltlib  # noqa: E402
from p3sim import canister_qr  # noqa: E402
from p3sim import layout as roomlib  # noqa: E402
from p3sim import layout_v2  # noqa: E402
from p3sim import motion  # noqa: E402
from p3sim import bridge, common, diag, pouch  # noqa: E402
from p3sim import encounters  # noqa: E402
from p3sim import reset as resetlib  # noqa: E402
from p3sim import scene  # noqa: E402
from p3sim import truth_sensors as sensorlib  # noqa: E402
from p3sim import ur5_cell  # noqa: E402
from p3sim import base_scene
from p3sim import hospital_conveyor as hconv  # noqa: E402
from p3sim import hospital_nav, hospital_zones  # noqa: E402
from p3sim import zones as zoneslib  # noqa: E402
from p3sim import observation as obslib  # noqa: E402
from p3sim import views  # noqa: E402

log = common.Logger("[pharmacy_stage]")

CONVEYOR_EXTENSION = "isaacsim.asset.gen.conveyor"
# Rail topics are NOT in contract v1 (the rail is 재범's 9/17 decision). Proposed names, same shape as the arm topics:
# /m0609/rail/joint_states (JointState rail_x, rail_y, S) and /m0609/rail/joint_command (JointState position, R).
RAIL_JOINTS = ("rail_x", "rail_y")
RAIL_JOINTS_V2 = ("rail_x", "rail_y", "rail_z")
V2 = layout_v2.default_v2()
STAGE_ROOT = "/World/P3Pharmacy"
#: 선 약통의 QR 스티커를 실제 약통 자세로 다시 맞추는 주기(sim s).
CANISTER_FACE_SYNC_S = 0.5
M0609_LINKS = ("link_1", "link_2", "link_3", "link_4", "link_5", "link_6")
BELT_PRIM = f"{STAGE_ROOT}/Belt"
POUCH_ROOT = f"{STAGE_ROOT}/Pouches"
AMR_ROOT = f"{STAGE_ROOT}/Amr"  # K2: dummy 3축 이동 베이스

# 병원 전체 preset(#527 H1·H2, 재범 결정 9/23): 병원 씬 + 조제실 모듈 + 씬 컨베이어로 창구 A1 끝 롤러까지.
REPO = Path(__file__).resolve().parents[2]
HOSPITAL_SCENE = REPO / "sim" / "scenes" / "hospital_navigationv1.usda"
HOSPITAL_ZONES = REPO / "src" / "rokey_p3_description" / "config" / "zones.hospital.yaml"
HOSPITAL_ANCHORS = REPO / "sim" / "scenes" / "hospital_navigationv1.anchors.json"
#: 조제실 v2 모듈(레일·선반·조제기·약통)을 병원 씬에 놓는 평행이동 (dx, dy), yaw 0. 설계안 값이다(재지 않았다):
#: 레일 원점 ≈ (-7.85, 9.80), 조제기 상자 중심 ≈ (-6.85, 10.50), 선반 x -9.18..-7.85. 컨베이어 북쪽의 닫힌 방
#: (빈 곳 x -9.4..-6.0, y 6.6..10.9) 안이다 — 시험이 모듈 상자가 그 안인지 본다.
HOSPITAL_V2_OFFSET = (-7.85, 9.50)
#: 쉬는 봉투 자리(첫 봉투, 나머지는 +y 로 0.15 m 간격). 같은 닫힌 방 안, 모듈 남쪽. 우리가 고른 값이다.
HOSPITAL_PARKING = (-8.5, 7.0)
#: 조제기에 넣어 쓴 약통을 치울 높이(m, --workcell-consume). 바닥 아래라 카메라·라이다에 안 보이고 기구학적으로 둔다.
CONSUMED_PARK_Z = -5.0
#: 병원 봉투 풀 크기. 배달한 봉투는 보관함에 남아 풀로 돌아오지 않는다. 그리고 QR 라벨은 풀 크기만큼만
#: 주문 풀 id 를 돌려 붙인다(`pouch.pool_labels`). 9/24 50b658a 10건: 기본 8 이라 ord-0009·0010 은 QR 붙은
#: 봉투가 없었고, 9·10번째 배출이 `pool_exhausted` 로 거부됐다. 주차 줄은 y 7.0–9.1(15칸) 로
#: 지도상 비어 있다(시험이 본다).
#: 15 = 병원 주문 풀 13(침상 10 + 테이블 B·C1·C2 3, 재범 9/25 03:3x beds-all) + 여벌 2. 12 에서는 ord-0013 의
#: 라벨 봉투가 없다(`pouch.pool_labels` 가 id 를 돌려 붙이므로 풀 < 주문이면 뒤 주문이 pool_exhausted).
HOSPITAL_POUCH_POOL = 15
#: 도크 벽 불투명도(재범 9/29). glass_wall.HOSPITAL_OPACITY 와 같다(시험이 묶는다). 라이다·rtf 는 L3 미확인.
HOSPITAL_DOCK_WALL_OPACITY = 0.35
#: 병원 preset 의 가짜 AMR 대수(재범 9/25 00:2x: 회피 장면을 안전판 v0.5.0 에 넣는다). 판정선이 실패하면 0 으로
#: 되돌리고 그 항목만 뺀 채 동결한다(작전 결정 규칙). 끄는 인자는 `--traffic-dummies 0`.
HOSPITAL_TRAFFIC_DUMMIES = 2
#: 병원 preset 의 보행자 수 — 왕복 선 둘(로비·병동 앞 복도)에 한 명씩(재범 9/25 회피 장면). 판정선이 실패하면
#: 0 으로 되돌리고 그 항목만 뺀 채 동결한다(작전 결정 규칙). 끄는 인자는 `--pedestrians 0`.
HOSPITAL_PEDESTRIANS = 2
#: 병원 경로의 "벨트 위" 높이 띠(m). 출발점 바로 밑 트랙 높이를 재지 않아 BeltModel 의 0.05 보다 넉넉히 둔다(추정).
HOSPITAL_ON_BELT_HEIGHT = 0.10
#: at_end 시한 메모(로그만). 잰 운반 시간 34.58 s, 오케스트레이터 belt_timeout_s 60 과 같게 둔다.
HOSPITAL_AT_END_TIMEOUT_S = 60.0
#: 병원 씬 컨베이어 표면 속도 배율(재범 9/29 "속도 올리기"). 잰 값(롤러 0.5 m/s)으로는 봉투가 출발→A1 에 34.58 sim s
#: 걸렸다 — 봉투가 롤러에서 미끄러져 실효 ~0.15 m/s. 2 배로 올린다. **L3 미확인**: 끝 롤러 튐(39fc30b)·분기 낙하
#: (`pouch_left_belt`)·A1 정착(`pouch_at_end … in_sensor_zone`)을 마스터 랩에서 본다.
#: 되돌리기는 `--conveyor-speed-scale 1`.
HOSPITAL_CONVEYOR_SPEED_SCALE = 2.0
#: 병원 끝 롤러 도착 구역: 봉투 앞 끝이 출구 가장자리에서 이 거리 안(m). 작전 결정 9/23: 끝 롤러 표면 속도를 0 으로
#: 두어(hospital_conveyor_surfaces.json `_terminal`) 봉투가 롤러 위 조금 안쪽에 선다.
#: 0.03 이면 그 자리를 도착으로 못 본다.
HOSPITAL_TERMINAL_EDGE_MARGIN = 0.15
#: 끝 롤러를 잡는 자리: 봉투 전체가 끝 롤러 위이고 앞 끝이 출구에서 이 거리 안(m). 작전 결정 9/23 (다).
HOSPITAL_TERMINAL_HOLD_MARGIN = 0.15

# Room layout: p3sim/layout.py default_layout() (scenario.md 1 and the concept image). The belt starts at the
# dispenser outlet on its +x face and runs +x through the wall opening to the loading spot in the corridor.
ROOM = roomlib.default_layout()
DEFAULT_BELT_LENGTH = ROOM["belt_length"]
DEFAULT_BELT_WIDTH = ROOM["belt_width"]
DEFAULT_BELT_THICKNESS = 0.10
DEFAULT_BELT_YAW = 0.0  # belt runs along +x
DEFAULT_POUCH_SIZE = (0.10, 0.07, 0.01)

# Presets change argument defaults only; any argument given on the command line wins. For people starting the demo
# from the runbook (9/21). Geometry is left at the defaults verified on 9/17 master02 with f796210 (refill 3/3);
# rail_drive is pinned to the f796210 value because the stronger default of 2b846f2 has not run in Isaac yet.
VERIFIED_RAIL_DRIVE = [1e5, 1e4, 5e4]
#: 병원 주행에서 끄는 복도 카트(씬 기준 상대 경로). 지도 생성의 --skip 과 같은 프림이다.
#: --pouch-at-end: 봉투 앞 가장자리와 출구 사이(m). 탐침 02 에서 봉투가 선 자리(edge_gap 0.023, #240 5790540704)에
#: 맞춘다. 끝 구역 판정(edge_margin, 지금 HOSPITAL_TERMINAL_EDGE_MARGIN 0.15) 안이어야 POUCH_AT_END 가 난다.
POUCH_AT_END_BACKOFF = 0.02
HOSPITAL_CORRIDOR_CART = "Environment/hospital/SM_SupplyCart_02a_28"
#: 병원 뷰포트의 기본. 건물 전체 조망이고, 회차 내내 Perspective 가 이 자세다(재범 9/23).
#: 루프 한 틱이 이보다 오래 걸리면 그 틱의 호출을 남긴다(초, wall). 최적화 9/23 요청.
LOOP_STALL_WALL_S = 0.25
HOSPITAL_DEFAULT_VIEW = "floor_top"
#: 병원에서 카메라 프림을 쓸 일이 있으면 이 이름 하나만 쓴다. 한 바퀴 회차는 쓰지 않는다.
HOSPITAL_CAMERA_PRIM = "/HospitalPracticeCamera"

PRESETS = {
    # Adapter demo: JSON topics for the adapter, refills on the same screen, stand-in pick as a fallback for
    # pick_notice.
    "demo-ros": {"mode": "ros", "ros_refill_selfdemo": True, "ros_pick_stand_in_s": 5.0, "refill_loop": 0,
                 "rail_drive": VERIFIED_RAIL_DRIVE},
    # Orchestrator refill (9/18 재범): /m0609/refill drives the rail + M0609 through /m0609/arm/joint_command,
    # /m0609/rail/joint_command and /m0609/gripper/command; the stage only follows commands and reports holding.
    "demo-ros-refill": {"mode": "ros", "ros_refill_selfdemo": False, "ros_pick_stand_in_s": 5.0,
                        "rail_drive": VERIFIED_RAIL_DRIVE},
    # Scene v2 (재범 9/18): 3-axis rail, four shelves, cylinder + module canisters, round bin and module hole; the
    # arm node drives it like demo-ros-refill. Placeholder dimensions (p3sim/layout_v2.py).
    # v2 rail drive: 실습7-a (9/18) pushed the rail 0.05-0.10 m on module inserts with (1e5, 1e4, 5e4) against the
    # arm's 1e8 drives. The 2b846f2 stage default (1e7, 1e5, 1e8) is our choice; no G-1 Isaac comparison ran.
    "demo-ros-refill-v2": {"mode": "ros", "ros_refill_selfdemo": False, "ros_pick_stand_in_s": 5.0,
                           "rail_drive": [1e7, 1e5, 1e8], "scene": "v2", "view": "overview"},
    # K1 (작전 9/21, 재범 "구현부터"): 빈월드에 전 구간 한 바퀴. demo-ros-refill-v2 위에 복도·병상·도크를 얹고
    # UR5 는 실습12 에서 실제로 된 값으로 둔다(비전 9/21). 이동 베이스는 K2 에서 이 위에 얹는다 — v0 의 UR5 는
    # 받침대 그대로다. 기존 preset 은 건드리지 않는다.
    "emptyworld-loop": {"mode": "ros", "ros_refill_selfdemo": False, "ros_pick_stand_in_s": 0.0,
                        "rail_drive": [1e7, 1e5, 1e8], "scene": "v2", "view": "overview",
                        "full_loop": True, "ur5": True, "ur5_spawn_ready": True,
                        "ur5_base": (3.25, 0.55, 0.90), "ur5_pedestal_size": (0.02, 0.02),
                        "ur5_pedestal_height": 0.45, "ur5_ready": (3.30, 0.05, 0.85),
                        "deck_center": (3.25, 0.05, 0.45)},
    # 세준 hospital under scene v2 (재범 결정 9/18, #215): demo-ros-refill-v2 on site A with the decided prims off.
    # --base-usd (the prepared scene path) is a site value and must be given.
    "hospital-v2": {"mode": "ros", "ros_refill_selfdemo": False, "ros_pick_stand_in_s": 5.0,
                    "rail_drive": [1e7, 1e5, 1e8], "scene": "v2", "view": "overview",
                    "pharmacy_origin": list(base_scene.HOSPITAL_ORIGIN_A),
                    "base_deactivate": list(base_scene.HOSPITAL_DEACTIVATE),
                    "base_rigid_off": list(base_scene.HOSPITAL_RIGID_OFF)},
    # 병원 주행 v0(9/23 작전): 병원 씬(hospital_navigationv1)을 world 그대로(원점 0) 깔고 우리 방·상자는 만들지
    # 않는다(--no-room). 씬에 박힌 합본 로봇은 끄고 AMR 합본(--amr --amr-combined <경로>)을 --amr-start 에 세운다.
    # 루트의 병상 여섯도 싣는다. zones·routes 는 config/{zones,routes}.hospital.yaml. --base-usd 는 사이트 값이다.
    # 복도 x≈12 의 약품 카트는 뺀다: 카트(y 4.28–5.00)와 벽 사이가 약 1.2 m 라 Nav2 footprint(0.9 m)가
    # 양옆 0.15 m 로 지나간다. 9/23 main 녹화 회차(rtf 0.54)에서 dock_3 → bed_b1 이 여기서 "No valid trajectories"
    # 로 abort 됐다(#240). 지도·zones·routes 도 이 카트를 빼고 만든다(HOSPITAL_CORRIDOR_CART 는 그 단일 출처).
    # 씬의 `Graph`(박힌 로봇용 ROS 그래프 — 네임스페이스 없는 scan·odom·tf·카메라)와 `gripper`(박힌 로봇 손목에 붙은
    # 흡착 그리퍼 payload)도 끈다. 로봇을 끄면 둘 다 주인 없이 돈다(#523 검토 9/23). 씬에 없으면 missing 으로 적힌다.
    "hospital-nav": {"mode": "ros", "ros_refill_selfdemo": False, "ros_pick_stand_in_s": 0.0,
                     "scene": "v2", "view": "overview", "no_room": True, "amr": True,
                     "pharmacy_origin": [0.0, 0.0, 0.0, 0.0], "base_deactivate": ["ridgeback_ur5", "Graph", "gripper",
                                                                               HOSPITAL_CORRIDOR_CART],
                     "base_root_prims": True},
    # 병원 전체(재범 결정 9/23, #527): 웹 주문 → (필요하면 M0609 보충) → 조제기 → 봉투가 **씬의 컨베이어**를 타고
    # 창구 A1 끝 롤러(ConveyorTrack_02/Rollers_01)까지 → dock_1 의 AMR 합본이 롤러 끝에서 집는다 → 병상 → 보관함 →
    # 도크. hospital-nav 위에 조제실 v2 모듈을 평행이동(--v2-offset)해 얹고 우리 벽·벨트·적재 자리는 만들지 않는다.
    # --base-usd·--amr-start·--amr-combined 는 준 값만 쓴다(검사가 없으면 멈춘다). ur5 는 빈월드와 같이 켠다 —
    # 합본이 팔을 들고 오므로 받침대 UR5 는 안 생긴다(검사가 --amr-combined 를 요구한다).
    "hospital-full": {"mode": "ros", "ros_refill_selfdemo": False, "ros_pick_stand_in_s": 0.0,
                      "rail_drive": VERIFIED_RAIL_DRIVE, "scene": "v2", "view": "overview",
                      "hospital_decor": True,
                      "render_every": 2,
                      "hospital_full": True, "ur5": True, "amr": True,
                      "pharmacy_origin": [0.0, 0.0, 0.0, 0.0],
                      "base_deactivate": ["ridgeback_ur5", "Graph", "gripper"], "base_root_prims": True,
                      "v2_offset": list(HOSPITAL_V2_OFFSET), "parking_origin": list(HOSPITAL_PARKING),
                      "zones_file": str(HOSPITAL_ZONES)},
    # 병원 전 구간(재범 9/23): 조제실은 실습37 의 병원 M0609 워크셀(--workcell-layout, 실측 JSON)을 그대로 쓴다.
    # 빈월드 조제실을 옮겨 오지 않는다. 봉투는 씬 컨베이어로 A1 끝 롤러까지, 합본 AMR 의 팔이 집고 Nav2 로 간다.
    # 레일 드라이브는 `VERIFIED_RAIL_DRIVE` 다(작전 결정 9/23). 빈월드에서 쓰던 (1e7, 1e5, 1e8) 은 병원에서
    # 틱을 늘렸다 — 회차 94f19fb-rail 에서 `loop stall` 5줄 → 0줄, rtf 0.354 → 0.386 이고 보충·집기·내려놓기는
    # 그대로 통과했다. 부드러운 드라이브가 레일을 얼마나 밀리게 하는지는 아래 `rail_follow` 줄이 잰다.
    "hospital": {"mode": "ros", "ros_refill_selfdemo": False, "ros_pick_stand_in_s": 0.0,
                 "rail_drive": VERIFIED_RAIL_DRIVE, "scene": "v2", "view": "overview",
                 "hospital_decor": True,
                 # 조제실을 가득 채우고(18/18) 쓴 약통은 선반으로 안 돌아온다(재범 9/29 N3).
                 "workcell_empty_cells": 0, "workcell_consume": True,
                 "render_every": 2,
                 "hospital_full": True, "ur5": True, "amr": True,
                 "pharmacy_origin": [0.0, 0.0, 0.0, 0.0],
                 "base_deactivate": ["ridgeback_ur5", "Graph", "gripper", HOSPITAL_CORRIDOR_CART],
                 "base_root_prims": True, "parking_origin": list(HOSPITAL_PARKING),
                 "pouch_pool": HOSPITAL_POUCH_POOL, "tray_clip": True,
                 "traffic_dummies": HOSPITAL_TRAFFIC_DUMMIES, "pedestrians": HOSPITAL_PEDESTRIANS,
                 "dock_wall_opacity": HOSPITAL_DOCK_WALL_OPACITY,
                 "conveyor_speed_scale": HOSPITAL_CONVEYOR_SPEED_SCALE,
                 "zones_file": str(HOSPITAL_ZONES)},
    # No ROS: belt dispensing and the rail refill loop forever (what 마클2 runs for selfdemo refills).
    "selfdemo-refill": {"mode": "selfdemo", "loop": 0, "refill_loop": 0, "rail_drive": VERIFIED_RAIL_DRIVE},
}


def build_parser():
    parser = argparse.ArgumentParser(description="Isaac Sim 5.1 pharmacy section stage (stage 0.7).")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--livestream", action="store_true")
    parser.add_argument("--livestream-extension", default=refill.DEFAULT_LIVESTREAM_EXTENSION)
    parser.add_argument("--preset", choices=sorted(PRESETS),
                        help="set argument defaults for a named run; explicit arguments still win (see README)")
    parser.add_argument("--mode", choices=("ros", "selfdemo"), default="selfdemo")
    parser.add_argument("--scene", choices=("v1", "v2"), default="v1",
                        help="v1: the 9/17-9/18 room (default, unchanged). v2: 3-axis rail, four shelves, two canister "
                             "kinds, round bin and module hole (placeholder dimensions, ros refill only)")
    parser.add_argument("--rail-z-limits", type=float, nargs=2, default=list(V2["rail_z_limits"]),
                        metavar=("LOWER", "UPPER"), help="v2 rail_z (lift) joint limits, m")
    parser.add_argument("--belt-start", type=common.xyz, default=None,
                        help="belt top-surface point at the start; default: the dispenser outlet at --belt-top")
    parser.add_argument("--belt-top", type=common.positive_float, default=ROOM["belt_top"], help="belt top height, m")
    parser.add_argument("--shelf-origin", type=common.xyz, default=ROOM["shelf_origin"],
                        help="medicine shelf rack: x of the left side, y of the open front, floor z")
    parser.add_argument("--shelf-cols", type=int, default=ROOM["shelf_cols"])
    parser.add_argument("--shelf-rows", type=int, default=ROOM["shelf_rows"])
    parser.add_argument("--shelf-cell", type=common.positive_float, nargs=2, default=list(ROOM["shelf_cell"]),
                        metavar=("WIDTH", "HEIGHT"))
    parser.add_argument("--shelf-depth", type=common.positive_float, default=ROOM["shelf_depth"])
    parser.add_argument("--shelf-plinth", type=common.non_negative_float, default=ROOM["shelf_plinth"])
    parser.add_argument("--room-canister-size", type=common.positive_xyz, default=ROOM["canister_size"])
    parser.add_argument("--pick-cell", type=int, nargs=2, default=list(ROOM["pick_cell"]), metavar=("ROW", "COL"))
    parser.add_argument("--dispenser-origin", type=common.xyz, default=ROOM["dispenser_origin"],
                        help="dispenser cabinet: x, y centre and floor z")
    parser.add_argument("--dispenser-size", type=common.positive_xyz, default=ROOM["dispenser_size"])
    parser.add_argument("--inlet-size", type=common.positive_xyz, default=ROOM["inlet_size"])
    parser.add_argument("--inlet-height", type=common.positive_float, default=ROOM["inlet_height"])
    parser.add_argument("--inlet-gap", type=common.non_negative_float, default=ROOM["inlet_gap"],
                        help="space between the dispenser face and the inlets' back walls, m (9/18: 0 let the wrist "
                             "hit the face)")
    parser.add_argument("--rail-x-stroke", type=common.positive_float, default=ROOM["rail_x_stroke"])
    parser.add_argument("--rail-y-limits", type=float, nargs=2, default=list(ROOM["rail_y_limits"]),
                        metavar=("LOWER", "UPPER"), help="rail_y joint limits, m (joint zero = rail origin)")
    parser.add_argument("--wall-x", type=float, default=ROOM["wall_x"], help="pharmacy/corridor wall, m")
    parser.add_argument("--door-y", type=float, default=ROOM["door_y"])
    parser.add_argument("--belt-length", type=common.positive_float, default=DEFAULT_BELT_LENGTH)
    parser.add_argument("--belt-width", type=common.positive_float, default=DEFAULT_BELT_WIDTH)
    parser.add_argument("--belt-thickness", type=common.positive_float, default=DEFAULT_BELT_THICKNESS)
    parser.add_argument("--belt-yaw", type=float, default=DEFAULT_BELT_YAW, help="rad about world z")
    parser.add_argument("--belt-speed", type=common.positive_float, default=0.15, help="m/s surface speed")
    parser.add_argument("--belt-presurface", action="store_true",
                        help="apply PhysxSurfaceVelocityAPI (enabled, velocity 0) to the belt before the first play. "
                             "9/17 master02: no effect on the 1.6x speed of the scaled-cube body (5/5)")
    parser.add_argument("--rail-overlap-every", type=int, default=12,
                        help="updates between checks of the robot overlapping its own rail parts (0 = off)")
    parser.add_argument("--no-contact-log", action="store_true",
                        help="do not log contacts of the rail/M0609 bodies and the pick canister (재범 실습1 P2)")
    parser.add_argument("--contact-log-every-s", type=common.non_negative_float, default=2.0, metavar="SECONDS",
                        help="diagnosis only: sim seconds between logged lines of the same contact pair (default "
                             "2.0). P30 (9/20): the 2 s throttle hid the gripper-canister touch that pushed a "
                             "canister. 0.05-0.1 catches it; 0 logs every event (tens of thousands of lines a "
                             "minute)")
    parser.add_argument("--kit-log-verbose", action="store_true",
                        help="with --kit-log-file, also write Verbose Kit lines to it (large file)")
    parser.add_argument("--kit-log-file", default="",
                        help="fix Kit's own log file path (--/log/file); printed at start so it can be tailed after "
                             "an unexplained end. Empty keeps Kit's default path")
    parser.add_argument("--belt-body", choices=("scaled-cube", "xform"), default="xform",
                        help="conveyor rigid body: unscaled Xform with a scaled Cube collider child (default) or the "
                             "scaled Cube itself (reproduces 9/17: window + ros runs moved at 1.6x --belt-speed)")
    parser.add_argument("--end-zone", type=common.positive_float, default=0.15, help="end stop zone length, m")
    parser.add_argument("--settle-speed", type=common.positive_float, default=0.01, help="m/s")
    parser.add_argument("--settle-time-s", type=common.non_negative_float, default=0.3)
    parser.add_argument("--belt-fail-closed", action="store_true",
                        help="contract 11.1 proposal, off by default: a missing pouch velocity is not a settle sample, "
                             "and a pouch that leaves the belt keeps it occupied (pouch left in place) until reset")
    parser.add_argument("--gripper-command-seq", action="store_true",
                        help="ros mode with --ur5, off by default: apply /isaac/amr_1/gripper/command_seq "
                             "(contract 11.6 GripperCommand as JSON), ignore the Bool gripper command from the "
                             "start, and publish /isaac/amr_1/gripper/state (GripperState) at 10 Hz")
    parser.add_argument("--belt-observation", action="store_true",
                        help="ros mode, off by default: also publish /isaac/pharmacy/belt_observation (contract 11.6 "
                             "BeltObservation as JSON) at 5 Hz from the same belt state as /isaac/pharmacy/belt")
    parser.add_argument("--pouch-size", type=common.positive_xyz, default=DEFAULT_POUCH_SIZE)
    parser.add_argument("--pouch-mass", type=common.positive_float, default=0.02, help="kg")
    parser.add_argument("--tray-clip", action=argparse.BooleanOptionalAction, default=False,
                        help="합본 AMR 트레이 홀더: 칸에 멈춘 봉투를 트레이에 붙이고 팔이 잡으면 푼다(병원 preset 켬)")
    parser.add_argument("--spawn-along", type=common.pair, default=(0.05, 0.15), help="belt-frame x range, m")
    parser.add_argument("--spawn-lateral", type=common.pair, default=(-0.04, 0.04), help="belt-frame y range, m")
    parser.add_argument("--spawn-yaw", type=common.pair, default=(-0.3, 0.3), help="rad range relative to the belt")
    parser.add_argument("--spawn-drop", type=common.non_negative_float, default=0.02, help="height above belt, m")
    parser.add_argument("--seed", type=int, default=0, help="spawn randomness; draws use (seed, epoch, index)")
    parser.add_argument("--qr-dir", help="directory of <order_id>.png from make_qr_textures.py; pouches get QR tops")
    parser.add_argument("--pouch-pool", type=int, default=8,
                        help="pouches created before the simulation starts and reused (no prim create/delete while "
                             "running)")
    parser.add_argument("--parking-origin", type=float, nargs=2, default=[2.2, -1.3], metavar=("X", "Y"),
                        help="floor spot of the first idle pouch; the rest follow along +y")
    parser.add_argument("--order-pool", help="order_pool.yaml; if omitted any ord-NNNN id is known")
    parser.add_argument("--loop", type=int, default=0, help="selfdemo dispenses; 0 = forever")
    parser.add_argument("--pick-delay-s", type=common.non_negative_float, default=3.0,
                        help="selfdemo: sim seconds at the end before the pouch is removed")
    parser.add_argument("--full-loop", action="store_true",
                        help="K1: add the corridor, one ward (bed + cabinet + tag) and the AMR docks, and "
                             "publish the contract 3 zone frames. All sizes are placeholders (source: 임시)")
    parser.add_argument("--ur5-spawn-ready", action="store_true",
                        help="spawn the UR5 at the --ur5-ready TCP instead of the USD pose. Off by default so "
                             "selfdemo and every existing preset keep their behaviour; the emptyworld-loop preset "
                             "turns it on. The USD pose is the arm stretched out horizontally and the arm node does "
                             "not home on start, so the first pick would set off from it (비전 9/21)")
    parser.add_argument("--sim-sensors", action="store_true",
                        help="K4/K5: publish the truth pouch detections and tag reads as JSON on "
                             "/isaac/amr_1/pouches and /isaac/amr_1/tag_reads. Off by default. isaac_adapter maps "
                             "them to PouchDetection/TagRead on /amr_1/sim/*; the arm subscribes only with "
                             "pouch_source: sim / scan_tag_source: sim. A sensor, not a stub: only what is really "
                             "in the belt-end zone or a deck slot is reported, and tags need --amr and --order-pool")
    parser.add_argument("--ur5-base-frame", default=None, metavar="FRAME",
                        help="TF frame name for the pedestal UR5's base_link. Default amr_1/ur_arm_base_link "
                             "(decision 47, 재범 9/21): amr_1/base_link is base_driver's name for the mobile base, "
                             "so publishing it as a child here breaks contract 3 in any combination. The new name "
                             "matches the official Ridgeback+UR5 asset and URDF link name - not because anything "
                             "forces it, but because it is less confusing to read")
    parser.add_argument("--ur5-spawn-settle-steps", type=int, default=90, metavar="N",
                        help="with --ur5-spawn-ready, physics steps to settle before reading the joints that the "
                             "arm node will use as home_joint_positions (default 90, about 1.5 s at 60 Hz). Gravity "
                             "sag, if any, shows up as spawn_settled sag_rad")
    parser.add_argument("--zones-tf", action="store_true",
                        help="diagnostic: publish the zone frames on /tf_static from this stage. **Off by default** "
                             "— the contract's single writer is navigation's zones_tf (v1 59, 436-442). Only for "
                             "scene-only runs with no ROS stack. The names differ from the contract "
                             "(bed_a1_cabinet, not bed_a1/cabinet): Isaac names frames after prims and a prim name "
                             "cannot contain '/'. Never on in a full-loop run")
    parser.add_argument("--amr", action="store_true",
                        help="K2: add the AMR mobile base as a dummy 3-axis joint (x, y, yaw) driven by velocity. "
                             "Subscribes /amr_1/base/joint_command, publishes /amr_1/joint_states. No odom, no TF — "
                             "그 작성자는 base_driver 다(계약 3절). Placeholder sizes (source: 임시)")
    parser.add_argument("--amr-combined", default=None, metavar="PATH",
                        help="with --amr, use the **AMR 합본** (the official Ridgeback+UR5 asset) instead of the "
                             "placeholder box (재범 9/21: 상자로 한 시험은 뜻이 없다). The path differs per "
                             "machine, so there is no default; without it the box is used and behaviour is "
                             "unchanged. The asset's dummy joints carry the same three names, and this stage "
                             "re-applies our velocity drive over whatever gains the asset ships. The asset file "
                             "keeps its own name (ridgeback_ur5.usd) — naming.md keeps external asset names so "
                             "the source stays traceable")
    parser.add_argument("--amr-usd", default=None, metavar="PATH",
                        help="deprecated alias for --amr-combined (이름 통일 9/21). Kept so a run already in "
                             "flight is not broken; use --amr-combined")
    parser.add_argument("--amr-count", type=int, default=1, metavar="N",
                        help="합본 AMR 을 N 대 세운다(1-4, 부하 측정용). 첫 대만 주문·Nav2 를 받고 나머지는 "
                             "센서만 켠 채 도크에서 서 있는다. 2..N 은 zones 의 dock_2..dock_4 다. "
                             "다중 배송 로직은 없다(재범 9/23)")
    parser.add_argument("--traffic-dummies", type=int, default=0, metavar="N",
                        help="병원 로비·복도를 도는 가짜 AMR N 대(0-2, 기본 0, 병원 preset 은 "
                             "HOSPITAL_TRAFFIC_DUMMIES; 끄려면 --traffic-dummies 0. "
                             "재범 9/25 안전판 v0.5.0 회피 장면). "
                             "합본 모양·노란 단색·위에 DUMMY. 주행 스택 없이 고정 루프 0.5 m/s, 진짜 AMR 이 "
                             "1.5 m 안이면 선다. 충돌 상자는 /Amr 밖이라 기존 접촉 로그에 잡힌다. "
                             "--amr --amr-combined 와 병원 zones 가 있어야 한다(p3sim/traffic_dummies.py)")
    parser.add_argument("--pedestrians", type=int, default=0, metavar="N",
                        help="병원 복도를 가로질러 왕복하는 보행자 N 명(0-2, 기본 0, "
                             "병원 preset 은 HOSPITAL_PEDESTRIANS; "
                             "끄려면 --pedestrians 0. 재범 9/25 회피 장면). 캡슐+머리, "
                             "옷 파랑/초록, 0.8 m/s 로 멈추지 않는다 — AMR 이 피하는 장면이다. 충돌체 ON(라이다·"
                             "접촉 로그). 병원 zones 가 있어야 한다(p3sim/pedestrians.py)")
    parser.add_argument("--block-path", action="store_true",
                        help="감속기 정지 규칙(#721) 발동 시험: 사람 크기 빨간 캡슐 하나가 바닥 아래 숨어 있다가 "
                             "amr_1 몸체 중심이 --block-path-trigger m 안에 들면 배송 경로 위(--block-path-at)에 "
                             "한 번 올라오고 --block-path-hold s 뒤 내려간다. 기대 로그 block_path placed → "
                             "governor stop reason=obstacle → block_path lifted → governor resume, 접촉 0. "
                             "--amr --amr-combined --amr-lidar 와 같이 주고 더미·보행자는 0 으로 둔다"
                             "(p3sim/path_block.py)")
    parser.add_argument("--block-path-at", type=float, nargs=2, default=None, metavar=("X", "Y"),
                        help="캡슐 자리(m, map). 기본 p3sim/path_block.BLOCK_XY — load → 병동 공통 구간(로비 y 4.2)")
    parser.add_argument("--block-path-trigger", type=float, default=None, metavar="M",
                        help="캡슐이 올라오는 amr_1 거리(m, 몸체 중심 기준, 기본 path_block.TRIGGER_M 1.5)")
    parser.add_argument("--block-path-hold", type=float, default=None, metavar="S",
                        help="올라와 있는 시간(sim s, 기본 path_block.HOLD_S 5). Nav2 progress_checker 10 s 보다 짧게")
    parser.add_argument("--amr-start", type=float, nargs=2, default=None, metavar=("X", "Y"),
                        help="AMR 출발 자리(m, map). 기본값은 빈월드의 dock_1 이다")
    parser.add_argument("--no-room", action="store_true", help="belt only: skip shelf, dispenser, rail tracks, wall")
    parser.add_argument("--pouch-at-end", action="store_true",
                        help="병원(--hospital-full) S3·S4 단독 회차: 조제가 받아들여지면 봉투를 씬 컨베이어 "
                             "출발점이 아니라 A1 끝 롤러 위(zones 의 pharmacy.belt_end 에서 봉투 반 길이 + 여유만큼 "
                             "안쪽)에 놓는다. "
                             "DISPENSED·POUCH_AT_END 는 그대로 흐른다. 놓는 자리는 임시값이다(재범 9/23)")
    parser.add_argument("--hospital-full", action="store_true",
                        help="병원 전체(#527): 우리 벽·벨트·적재 자리·배출구 상자를 만들지 않고, 봉투를 병원 씬 "
                             "컨베이어(표면 속도 직접 쓰기)로 창구 A1 끝 롤러까지 보낸다. zones·belt_end·보관함은 "
                             "--zones-file 에서 읽는다. --preset hospital-full 이 켠다")
    parser.add_argument("--v2-offset", type=float, nargs=2, default=None, metavar=("DX", "DY"),
                        help="장면 v2 조제실 모듈 전체(선반·조제기·둥근 통·모듈 구멍·레일 원점·조제기 원점)를 "
                             "(DX, DY) m 평행이동한다. 회전은 없다. 기동 때 한 번 적용하고, --rail-origin 등 준 좌표도 "
                             "모듈 기준으로 보고 같이 옮긴다. 레일 관절값은 안 바뀐다")
    parser.add_argument("--zones-file", default=None, metavar="PATH",
                        help="zones yaml(계약 3절). --hospital-full 에서 zone 자세·pharmacy/belt_end·보관함을 이 "
                             "파일에서 읽는다(주행·웹과 같은 파일을 준다)")
    parser.add_argument("--dock-wall-opacity", type=float, default=1.0, metavar="A",
                        help="병원 도크 벽(조제실 남쪽 y 5.35) 불투명도 0–1(재범 9/29 \"반투명으로 약이 오는 것\"). "
                             "1 = 원래 벽. preset hospital 은 glass_wall.HOSPITAL_OPACITY. 재질만 바꾼다")
    parser.add_argument("--hospital-receiver-prim", default=None, metavar="PRIM",
                        help="병원 단일 봉투 검증: 이 받침 USD 경계에서 롤러 통과·정착을 감지. 끝 롤러 강제 정지 생략")
    parser.add_argument("--conveyor-surfaces", default=str(hconv.SURFACES_JSON), metavar="PATH",
                        help="--hospital-full: 씬 컨베이어 몸체의 표면 속도 json(기본: 잰 값, #240)")
    parser.add_argument("--conveyor-speed-scale", type=common.positive_float, default=1.0, metavar="X",
                        help="--hospital-full: 위 표면 속도에 곱할 배율(재범 9/29 \"속도 올리기\"). preset hospital 은 "
                             "HOSPITAL_CONVEYOR_SPEED_SCALE. 방향·분기·끝 롤러 잡기는 그대로다")
    parser.add_argument("--workcell-layout", help="Measured hospital geometry JSON; uses existing ROS controllers")
    parser.add_argument("--base-usd", default=None,
                        help="base scene under the stage (세준 hospital, prepared by prepare_hospital_scene.py); "
                             "referenced at /World/P3Base/Scene so our frame stays the world frame")
    parser.add_argument("--pharmacy-origin", type=float, nargs=4, default=[0.0, 0.0, 0.0, 0.0],
                        metavar=("X", "Y", "Z", "YAW_DEG"),
                        help="our origin (rail centre on the floor) and +x heading in the base scene's world frame")
    parser.add_argument("--base-deactivate", nargs="*", default=[], metavar="PATH",
                        help="base scene prims to deactivate, relative to its default prim (e.g. Conveyor)")
    parser.add_argument("--base-root-prims", action="store_true",
                        help="also reference the base scene's root prims outside its default prim (the hospital "
                             "navigation v1 scene keeps six beds there). "
                             "Off: they are not loaded and a WARN names them")
    parser.add_argument("--amr-hand-camera", action="store_true",
                        help="with --amr --amr-combined, attach the suction gripper + D455 asset "
                             "(sim/assets/amr_gripper) under ur_arm_wrist_3_link and publish its colour camera as "
                             "/amr_1/hand_camera/image_raw,camera_info (frame amr_1/hand_camera_optical) plus its TF. "
                             "The suction TCP moves to the asset tip unless --ur5-tcp-offset is given. "
                             "Uses --camera-resolution/--camera-max-hz. Off by default")
    parser.add_argument("--amr-lidar", action="store_true",
                        help="with --amr --amr-combined, add an RTX 2D lidar between the base panels and publish "
                             "/amr_1/scan (LaserScan, frame amr_1/lidar_link) for AMCL and the Nav2 costmaps. "
                             "Off by default (the waypoints backend does not need it)")
    parser.add_argument("--lidar-debug", action="store_true",
                        help="draw the amr_1 lidar scan points in the viewport (filming, 재범 9/25: show that "
                             "pedestrians and dummies show up in the scan). Needs --amr-lidar. Costs one more render "
                             "product; off by default")
    parser.add_argument("--amr-lidar-mount", type=float, nargs=3, default=None, metavar=("X", "Y", "Z"),
                        help="lidar position in the combined base_link frame (default amr_base.LIDAR_MOUNT_LOCAL)")
    parser.add_argument("--base-rigid-off", nargs="*", default=[], metavar="PATH",
                        help="base scene rigid bodies to turn off (they stay visible), relative to its default prim")
    parser.add_argument("--view", choices=("none", *views.ALL_VIEW_NAMES, *views.HOSPITAL_VIEW_NAMES,
                                          *views.HOSPITAL_FOLLOW_VIEW_NAMES),
                        default="none",
                        help="viewport camera at start (실습7-a4: the default camera stood behind the corridor wall). "
                             "overview: rail, robot, shelves, dispenser and bins; shelves / bins: close-ups. "
                             "ur5: the loading cell in the corridor, beside the pedestal at its top height "
                             "(diagnostic, needs --ur5 to show anything). "
                             "none keeps Kit's default (the default; demo-ros-refill-v2 sets overview)")
    parser.add_argument("--window-half", choices=("left", "right", "full"), default=None,
                        help="put the Isaac window on one half of the screen (재범 9/18: Isaac left, 관제 웹 "
                             "right); sets the window size, position and render resolution. Window managers may "
                             "ignore the position; fall back to Super+Left on GNOME")
    parser.add_argument("--screen-size", type=int, nargs=2, default=[1920, 1080], metavar=("WIDTH", "HEIGHT"),
                        help="screen pixels for --window-half")
    parser.add_argument("--robot-usd", help="M0609 + gripper USD; mounts it on the 2-axis rail (omit for no robot)")
    parser.add_argument("--robot-child", default="m0609", help="robot prim name under the USD defaultPrim")
    parser.add_argument("--arm-joints", nargs=6, default=list(refill.DEFAULT_ARM_JOINTS), metavar="NAME")
    parser.add_argument("--gripper-joint", default=refill.DEFAULT_GRIPPER_JOINT)
    parser.add_argument("--gripper-open", type=float, default=refill.DEFAULT_GRIPPER_OPEN)
    parser.add_argument("--gripper-close", type=float, default=refill.DEFAULT_GRIPPER_CLOSE)
    parser.add_argument("--arm-drive", type=float, nargs=3, default=list(refill.DEFAULT_DRIVE),
                        metavar=("STIFFNESS", "DAMPING", "MAX_FORCE"))
    parser.add_argument("--rail-drive", type=float, nargs=3, default=[1e7, 1e5, 1e8],
                        metavar=("STIFFNESS", "DAMPING", "MAX_FORCE"),
                        help="rail prismatic drives; our choice, not measured. 9/17: with (1e5, 1e4, 5e3) and "
                             "(1e5, 1e4, 5e4) the carriage was pushed 0.05-0.12 m during arm phases while the arm "
                             "drives are (1e8, 1e4, 1e8)")
    parser.add_argument("--carriage-height", type=common.positive_float, default=ROOM["carriage_height"],
                        help="robot base height on the carriage pedestal, m")
    parser.add_argument("--rail-origin", type=common.xyz, default=ROOM["rail_origin"],
                        help="rail centre on the floor = rail joint zero, m")
    parser.add_argument("--rail-origin-y", type=float, help="overrides only the y of --rail-origin, m")
    parser.add_argument("--rail-speed", type=common.positive_float, default=motion.RAIL_SPEED,
                        help="selfdemo rail top speed, m/s (80%% of our 1.0 m/s proposal; 9/17 value was 0.2)")
    parser.add_argument("--rail-accel", type=common.positive_float, default=motion.RAIL_ACCEL, help="m/s^2")
    parser.add_argument("--reach-offset", "--shelf-standoff", dest="reach_offset", type=float, nargs=2,
                        default=list(ROOM["reach_offset"]), metavar=("DX", "DY"),
                        help="selfdemo: shelf canister minus robot base (x, y) when the rail parks at the shelf")
    parser.add_argument("--inlet-standoff", type=float, nargs=2, default=list(ROOM["inlet_offset"]),
                        metavar=("DX", "DY"), help="selfdemo: inlet centre minus robot base (x, y) at the inlet")
    parser.add_argument("--carry-z", type=common.positive_float,
                        help="selfdemo: TCP z while carrying (raise, above_inlet); default inlet rim + clearance + "
                             "canister below the TCP")
    parser.add_argument("--retreat-z", type=common.positive_float,
                        help="selfdemo: TCP z after release (retreat); default = carry z")
    parser.add_argument("--retreat-back", type=common.non_negative_float, default=0.10,
                        help="selfdemo: retreat point is this far from the inlet toward the rail (-y), m")
    parser.add_argument("--urdf", help="selfdemo refill: M0609 URDF for Lula IK (class asset doosan-robot2/urdf)")
    parser.add_argument("--robot-description", help="selfdemo refill: Lula description yaml (class asset rmpflow/)")
    parser.add_argument("--grip-link", default=refill.DEFAULT_GRIP_LINK)
    parser.add_argument("--workcell-empty-cells", type=int, default=4,
                        help="워크셀에서 비워 둘 칸 수(--seed 로 고른다). 종류마다 한 칸은 반드시 남긴다. "
                             "기본 4/18 은 우리가 고른 값이다 — 잰 값이 아니다")
    parser.add_argument("--rail-follow-warn-m", type=float, default=0.02,
                        help="레일 명령과 실제 위치의 차가 이보다 크면 `rail_follow` 줄을 남긴다(m). "
                             "부드러운 드라이브가 얼마나 밀리는지 보는 값이다 — 판정선이 아니다")
    parser.add_argument("--canister-contact-threshold-n", type=float, default=5.0,
                        help="선반 약통의 접촉 보고 문턱(N). 0 이면 선반에 얹힌 쌍이 매 스텝 보고돼 PhysX "
                             "재질 경고가 수십만 줄 난다(9/23 병원 한 바퀴). 기본 5 N 은 약통 무게 위, 밀린 "
                             "접촉 아래로 고른 **추정값**이다 — 잰 값이 아니다")
    parser.add_argument("--catalog", help="pharmacy_catalog.yaml: shelf cell -> canister id (cn-NNNN) for the QR faces")
    parser.add_argument("--canister-qr-dir",
                        help="scene v2: directory of <cn-id>.png from make_qr_textures.py --catalog; every shelf "
                             "canister gets a QR on its front (-y) and top (+z) faces. Needs --catalog")
    parser.add_argument("--patient-plates", action="store_true",
                        help="hospital: a visual-only plate with the pt-<patient> QR on each bedside table "
                             "(needs --zones-file, --order-pool, --qr-dir). Authentication stays on the truth sensor")
    parser.add_argument("--hospital-decor", action=argparse.BooleanOptionalAction, default=False,
                        help="hospital: floor guide lines, stop bays and name plates (visual only, on the floor so "
                             "the RTX lidar never sees them). On in the hospital presets; --no-hospital-decor "
                             "turns it off")
    parser.add_argument("--m0609-hand-camera", action="store_true",
                        help="colour camera that follows M0609 link_6 (mount from #520, not checked on the M0609) "
                             "and publishes /m0609/hand_camera/image_raw,camera_info (frame m0609/hand_camera_optical, "
                             "no TF). Off by default")
    parser.add_argument("--m0609-camera-resolution", type=int, nargs=2, default=[960, 600], metavar=("W", "H"),
                        help="M0609 hand camera size; 960 wide gives a canister QR about 120 px at the grasp pose")
    parser.add_argument("--tcp-offset", type=common.xyz, default=refill.DEFAULT_TCP_OFFSET)
    parser.add_argument("--tool-quat", type=common.quat, default=refill.DEFAULT_TOOL_QUAT)
    parser.add_argument("--tcp-max-speed", type=common.positive_float, default=motion.TCP_SPEED,
                        help="selfdemo TCP top speed on straight moves, m/s (90%% of the M0609 1.0 m/s spec; until "
                             "9/18 the stage moved 0.0007 m per update, about 0.04 m/s)")
    parser.add_argument("--tcp-accel", type=common.positive_float, default=motion.TCP_ACCEL, help="m/s^2")
    parser.add_argument("--joint-max-speed", type=common.positive_float, nargs=6, default=list(motion.JOINT_SPEED),
                        metavar="RAD_S", help="selfdemo per-joint speed cap joint_1..6 (90%% of USD maxVelocity)")
    parser.add_argument("--clearance", type=common.positive_float, default=ROOM["clearance"])
    parser.add_argument("--grip-depth", type=common.non_negative_float, default=ROOM["grip_depth"])
    parser.add_argument("--phase-pause-s", type=common.non_negative_float, default=0.5)
    parser.add_argument("--rail-tolerance", type=common.positive_float, default=0.01,
                        help="a rail phase ends when both rail joints are within this of the target, m")
    parser.add_argument("--tcp-tolerance", type=common.positive_float, default=0.01,
                        help="a tcp phase ends when the TCP is within this of the target, m")
    parser.add_argument("--phase-timeout-s", type=common.positive_float, default=5.0,
                        help="sim seconds allowed after the planned motion to reach tolerance; then TIMEOUT and go on")
    parser.add_argument("--via-tolerance", type=common.positive_float, default=0.03,
                        help="tolerance for pass-through poses (above, lift, pull_out, retreat), m")
    parser.add_argument("--ros-refill-selfdemo", action="store_true",
                        help="in --mode ros, run the rail+arm refill loop by itself (ignores /m0609/* commands) so the "
                             "adapter test shows refills on the same screen")
    parser.add_argument("--pull-margin", type=common.non_negative_float, default=0.12,
                        help="TCP enters and leaves the shelf through a point this far in front of it, m")
    parser.add_argument("--grasp-settle-s", type=common.non_negative_float, default=1.0)
    parser.add_argument("--refill-loop", type=int, default=0, help="selfdemo refill cycles; 0 = forever")
    parser.add_argument("--physics-grasp", action="store_true",
                        help="grip by friction only; default fixes the canister to the grip link on close (attach)")
    parser.add_argument("--respawn-delay-s", type=common.non_negative_float, default=2.0,
                        help="ros refill: sim seconds after the gripper opens before the canister goes back to its "
                             "shelf cell")
    parser.add_argument("--workcell-consume", action="store_true",
                        help="ros refill: 조제기에 넣은 약통을 선반으로 되돌리지 않는다(재범 9/29 \"쓴 만큼 줄게\"). "
                             "--respawn-delay-s 뒤 치우고 그 칸은 빈 칸이다. 리셋하면 다시 찬다. "
                             "preset hospital 은 켠다")
    parser.add_argument("--hold-distance", type=common.positive_float, default=0.08,
                        help="attach when closed and TCP to canister centre is below this, m")
    parser.add_argument("--ur5", action="store_true",
                        help="UR5 on a pedestal at the belt end with deck slots (stand-in for the docked AMR arm)")
    parser.add_argument("--ur5-usd", default="", help="UR5 USD; default: assets root + " + ur5_cell.UR5_ASSET)
    parser.add_argument("--ur5-base", type=common.xyz, default=ROOM["ur5_base"], metavar='"x y z"',
                        help='pedestal top centre, m, as ONE quoted string e.g. --ur5-base "3.25 0.55 0.80". '
                             '--ur5-ready is a world point, so raising this without moving that one leaves '
                             'the rest pose closer to the shoulder')
    parser.add_argument("--ur5-pedestal-height", type=common.positive_float, default=None, metavar="M",
                        help="diagnostic: stand height, m (default: the --ur5-base height, i.e. up to the "
                             "robot). Lower leaves the stand short of the robot, which is fixed to the world "
                             "anyway; use it to take the column out of the arm's sweep (L3-2 12h)")
    parser.add_argument("--ur5-pedestal-size", type=common.xy, default=None, metavar='"x y"',
                        help='diagnostic: the stand\'s footprint, m, as ONE quoted string e.g. '
                             '--ur5-pedestal-size "0.12 0.12" (default: 0.30 0.30). A narrower stand tells the '
                             'column under the shoulder apart from the shoulder height (L3-2 12d)')
    parser.add_argument("--deck-center", type=common.xyz, default=ROOM["deck_center"])
    parser.add_argument("--deck-count", type=int, default=ROOM["deck_count"])
    parser.add_argument("--ur5-ready", type=common.xyz, default=ROOM["ur5_ready"], help="TCP rest point, m")
    parser.add_argument("--ur5-tcp-speed", type=common.positive_float, default=0.003,
                        help="UR5 TCP m per update (the rail arm uses --tcp-speed)")
    parser.add_argument("--ur5-tcp-offset", type=common.xyz, default=(0.0, 0.0, 0.0),
                        help="suction face in the tool0 frame, m")
    parser.add_argument("--ur5-contact-log", action="store_true",
                        help="--ur5 only, off by default: also watch contacts of the UR5 links (the contact log "
                             "otherwise covers the M0609 and canisters only, so a UR5 touch is not seen)")
    parser.add_argument("--no-hand-camera", action="store_true",
                        help="--ur5 without the hand camera and TF graph (contract 2.1 hand camera, 3 frames)")
    parser.add_argument("--camera-resolution", type=int, nargs=2, default=[640, 480], metavar=("W", "H"),
                        help="hand camera pixels; the contract leaves it to the QR read distance (not measured). "
                             "9/17 7ae2879: 1280x720 in window mode published 2.9 Hz")
    parser.add_argument("--camera-max-hz", type=common.positive_float, default=10.0, help="contract: 10 Hz or less")
    parser.add_argument("--camera-offset", type=common.xyz, default=(0.06, 0.0, 0.0),
                        help="camera origin in the tool0 frame, m (beside the suction face)")
    parser.add_argument("--camera-focal-mm", type=common.positive_float, default=18.0)
    parser.add_argument("--suck-distance", type=common.positive_float, default=0.04,
                        help="suction takes the pouch when its centre is within this of the TCP, m")
    parser.add_argument("--ros-pick-stand-in-s", type=common.non_negative_float, default=0.0,
                        help="ros mode: sim seconds after POUCH_AT_END to park the pouch and free the belt, standing in"
                             " "
                             "for an arm that does not really pick; 0 = off (a real UR5 picks)")
    parser.add_argument("--reset-fail", action="store_true", help="answer every reset with ok=false")
    parser.add_argument("--reset-delay-s", type=common.non_negative_float, default=0.0,
                        help="wall seconds to wait before answering a reset")
    parser.add_argument("--rate", type=common.positive_float, default=60.0)
    parser.add_argument("--duration", type=common.non_negative_float, default=0.0)
    parser.add_argument("--physics-dt", type=common.positive_float, default=1.0 / 60.0)
    parser.add_argument("--render-dt", type=common.positive_float, default=1.0 / 60.0)
    # 최적화 9/23: 물리는 60 Hz 로 두고 그리기만 N 틱에 한 번 한다. Kit 갱신과 OmniGraph(= ROS 발행)가
    # 그리기에 얹혀 도니 그것들도 60/N Hz 가 된다 — 카메라·라이다 발행 주기도 같이 내려간다(아래 render_hz).
    # 기본 1 은 지금 그대로다. 효과(rtf)는 회차가 본다.
    parser.add_argument("--render-every", type=common.positive_int, default=1, metavar="N",
                        help="N 틱마다 한 번만 그린다(기본 1 = 매 틱). 물리는 --physics-dt 그대로.")
    return parser


DECOR_ATLAS = Path(__file__).resolve().parents[1] / "assets" / "decor" / "labels.json"
#: 도크 충전 스테이션 표시 아틀라스(재범 채택 9/24). 데코와 같이 켜고 끈다(--no-hospital-decor).
CHARGING_ATLAS = DECOR_ATLAS.with_name("charging.json")
#: M0609 셀 바닥 글자 아틀라스(재범 9/25). 데코와 같이 켜고 끈다.
WORKCELL_LABELS = DECOR_ATLAS.with_name("workcell_labels.json")
#: 병원 벽 표지판 아틀라스(재범 9/25 "조제실·병원·병동 데코"). 데코와 같이 켜고 끈다.
SIGNS_ATLAS = DECOR_ATLAS.with_name("signs.json")


def decor_routes_path(zones_file):
    """zones 파일 옆의 같은 월드 routes 파일(`zones.hospital.yaml` → `routes.hospital.yaml`)."""
    zones = Path(zones_file)
    return zones.with_name(zones.name.replace("zones", "routes", 1))


def build_hospital_decor(stage, args, layout, log):
    """병원 바닥 표시를 세운다(`p3sim/hospital_decor.py`). 반환 (띠 수, 글자 수)."""
    from p3sim import hospital_decor, hospital_nav

    routes_path = decor_routes_path(args.zones_file)
    routes = (hospital_decor.parse_routes_text(routes_path.read_text(encoding="utf-8"))
              if routes_path.is_file() else [])
    if not routes:
        log(f"WARN hospital_decor no routes at {routes_path}: guide lines skipped, bays and plates only")
    atlas = json.loads(DECOR_ATLAS.read_text(encoding="utf-8"))
    decor = hospital_decor.plan(routes, layout["zones"], hospital_nav.load_map(),
                                hospital_nav.BODY_LENGTH, hospital_nav.BODY_WIDTH, atlas["uv"])
    # 벽 표지판·문 앞 매트(재범 9/25). 매트는 정차 칸·글자·범례와 겹치지 않게 잡고(유도선은 매트 위로 그려진다),
    # 새 메시 없이 바닥 색 띠 메시에 합친다(최적화 예산). 표지판은 메시 하나.
    from p3sim import hospital_signage

    signage = hospital_signage.plan(hospital_nav.load_map(), hospital_nav.load_anchors(HOSPITAL_ANCHORS),
                                    hospital_nav.STATION_B_TABLE, hospital_signage.decor_faces(decor))
    decor["strips"] = hospital_signage.mat_strips(signage) + decor["strips"]
    built = hospital_decor.build(stage, f"{STAGE_ROOT}/HospitalDecor", decor,
                                 DECOR_ATLAS.with_name(atlas["image"]), log)
    # 테이블 윗면 색(재범 9/25): B 파랑·C 초록·D 노랑. 시각 재질만. 앵커·hospital_nav 의 prim 경로는 씬 파일 기준
    # (/World/…)이고, 스테이지는 씬을 base_scene.BASE_ROOT/Scene 아래에 붙인다 — 그 경로로 옮겨 찾는다
    # (회차74 50b8769: 옮기지 않아 `table_tints painted=2 missing=11`).
    tints = hospital_decor.table_tints(hospital_nav.load_anchors()["bedside_tables"],
                                       [t["prim"] for t in hospital_nav.room_tables().values()])
    tints = [(base_scene.scene_prim_path(prim), color) for prim, color in tints]
    hospital_decor.build_table_tints(stage, f"{STAGE_ROOT}/HospitalDecor", tints, log)
    # 도크 벽 반투명(재범 9/29 "약이 오는 것을 확인"). 재질만 — 충돌·지도 그대로. 실패해도 한 바퀴는 돈다.
    try:
        from p3sim import glass_wall

        glass_wall.build(stage, f"{STAGE_ROOT}/HospitalDecor",
                         [base_scene.scene_prim_path(p) for p in glass_wall.DOCK_WALL_PRIMS],
                         getattr(args, "dock_wall_opacity", 1.0), log)
    except Exception as error:
        log(f"WARN dock_wall_glass disabled reason={type(error).__name__}: {error}")
    signs_atlas = json.loads(SIGNS_ATLAS.read_text(encoding="utf-8"))
    hospital_signage.build(stage, f"{STAGE_ROOT}/HospitalDecor/Signage", signage, signs_atlas["uv"],
                           SIGNS_ATLAS.with_name(signs_atlas["image"]), log)
    charging_atlas = json.loads(CHARGING_ATLAS.read_text(encoding="utf-8"))
    items, skipped = hospital_decor.charging_plan(layout["zones"], charging_atlas["uv"],
                                                  hospital_nav.load_anchors(HOSPITAL_ANCHORS)["outlets"],
                                                  hospital_nav.BODY_LENGTH, hospital_nav.BODY_WIDTH)
    hospital_decor.build_charging(stage, f"{STAGE_ROOT}/HospitalDecor/Charging", items, skipped,
                                  CHARGING_ATLAS.with_name(charging_atlas["image"]), log)
    workcell = getattr(args, "workcell_data", None)
    if workcell:
        # M0609 셀 바닥(재범 9/25). 워크셀 JSON 이 있을 때만 — 자리가 거기서 나온다.
        from p3sim import views, workcell_decor

        labels = json.loads(WORKCELL_LABELS.read_text(encoding="utf-8"))
        cell_decor = workcell_decor.plan(workcell, labels["uv"], views.HOSPITAL_VIEWS)
        workcell_decor.build(stage, f"{STAGE_ROOT}/HospitalDecor/Workcell", cell_decor,
                             WORKCELL_LABELS.with_name(labels["image"]), log)
    return built


def render_hz(args):
    """실제로 그려지는 초당 횟수. `--render-every` 를 나눈 값이다.

    센서 그래프의 frameSkipCount 가 이 값에서 나온다. 여기서 나누지 않으면 `--camera-max-hz` 가
    거짓이 된다 — 그래프는 그려질 때만 도는데 계산은 매 틱 그린다고 치기 때문이다.
    """
    return 1.0 / (args.render_dt * args.render_every)


def parse_args(argv=None):
    parser = build_parser()
    first, _unknown = parser.parse_known_args(argv)
    if first.preset:
        parser.set_defaults(**PRESETS[first.preset])
    args, _unknown = parser.parse_known_args(argv)
    if args.rail_y_limits[0] >= args.rail_y_limits[1]:
        parser.error(f"--rail-y-limits: lower must be below upper, got {args.rail_y_limits}")
    if args.rail_origin_y is not None:
        args.rail_origin = (args.rail_origin[0], args.rail_origin_y, args.rail_origin[2])
    # 이름 통일(재범 9/21): "AMR 합본" = `--amr-combined`. 옛 이름은 **도는 회차를 안 끊으려고** 남긴다.
    if args.amr_usd and not args.amr_combined:
        args.amr_combined = args.amr_usd
        log("WARN --amr-usd is the old name; use --amr-combined (이름 통일 9/21). 값은 그대로 쓴다")
    args.amr_usd = None
    tokens = sys.argv[1:] if argv is None else list(argv)
    def given(flag):
        return any(t == flag or t.startswith(flag + "=") for t in tokens)

    if args.scene == "v2":  # v2 defaults for these two; v1 keeps ROOM's, an explicit argument wins
        if not given("--rail-x-stroke"):
            args.rail_x_stroke = V2["rail_x_stroke"]
        if not given("--carriage-height"):
            args.carriage_height = V2["carriage_height"]
    if args.v2_offset:
        # 조제실 모듈 평행이동(#527 H1). V2 의 월드 키는 v2_params(args) 가 옮기고, 스테이지 인자 셋은 여기서 옮긴다.
        dx, dy = (float(v) for v in args.v2_offset)
        for name in ("rail_origin", "dispenser_origin", "shelf_origin"):
            point = tuple(getattr(args, name))
            setattr(args, name, (point[0] + dx, point[1] + dy, *point[2:]))
    if args.workcell_layout:
        from p3sim import workcell_layout
        if not args.base_usd or not args.amr_combined:
            parser.error('--workcell-layout requires --base-usd and --amr-combined')
        if any(args.pharmacy_origin):
            parser.error('--workcell-layout uses the hospital world frame; pharmacy-origin must be zero')
        keep_start = args.amr_start if hospital_full(args) else None
        try:
            data = workcell_layout.load(args.workcell_layout)
            workcell_layout.configure(args, data)
        except (OSError, ValueError, KeyError, TypeError) as error:
            parser.error(str(error))
        if hospital_full(args):  # 병원 전 구간: AMR 은 워크셀 JSON 자리가 아니라 --amr-start(dock_1)에 선다
            if keep_start is not None:
                args.amr_start = keep_start
        elif not given('--base-deactivate'):
            args.base_deactivate = list(base_scene.HOSPITAL_DEACTIVATE)
        if not given('--base-rigid-off'):
            args.base_rigid_off = list(base_scene.HOSPITAL_RIGID_OFF)
    return args


def pouch_at_end_pose(belt_end, pouch_size, drop):
    """--pouch-at-end 봉투 자세 ((x, y, z), yaw). belt_end = (x, y, z, yaw): 출구 가장자리 가운데·롤러 윗면·나가는 방향.

    가장자리에서 봉투 반 길이 + POUCH_AT_END_BACKOFF 만큼 안쪽, 윗면 + 반높이 + drop. 긴 변을 나가는 방향에 맞춘다.
    """
    x, y, z, yaw = (float(v) for v in belt_end)
    back = max(pouch_size[0], pouch_size[1]) / 2.0 + POUCH_AT_END_BACKOFF
    return (x - math.cos(yaw) * back, y - math.sin(yaw) * back, z + pouch_size[2] / 2.0 + drop), yaw


def _same_pose(first, second, tolerance=1e-5):
    """두 (위치, 방향) 이 같은가. QR 면을 다시 쓸 필요가 있는지만 본다(정밀도 판정이 아니다)."""
    return all(abs(float(a) - float(b)) <= tolerance
               for left, right in zip(first, second, strict=True)
               for a, b in zip(left, right, strict=True))


def hospital_full(args):
    """병원 전체 구성인가(--hospital-full, --preset hospital-full)."""
    return bool(getattr(args, "hospital_full", False))


def v2_params(args):
    """장면 v2 매개변수. --v2-offset 이 있으면 평행이동한 사본(layout_v2.translated), 없으면 V2 그대로."""
    offset = getattr(args, "v2_offset", None)
    return layout_v2.translated(V2, *offset) if offset else V2


def shifted_view(args, eye, target):
    """--v2-offset 만큼 카메라도 옮긴다. 이름 붙은 뷰는 조제실 모듈을 보게 잡은 값이다."""
    offset = getattr(args, "v2_offset", None)
    if not offset:
        return eye, target
    dx, dy = offset
    return ((eye[0] + dx, eye[1] + dy, eye[2]), (target[0] + dx, target[1] + dy, target[2]))


def hospital_layout(args):
    """--hospital-full 의 zones·pharmacy 프레임·보관함 크기. 출처는 --zones-file 과 병원 앵커 JSON 이다."""
    zones = hospital_zones.zones_from_yaml(args.zones_file)
    pharmacy = hospital_zones.pharmacy_frames_from_yaml(args.zones_file)
    sizes = hospital_nav.cabinet_sizes(hospital_nav.load_anchors(HOSPITAL_ANCHORS))
    return zones, {"pharmacy": pharmacy, "cabinet_sizes": sizes,
                   "belt_end": pharmacy.get("belt_end")}


def v2_rail_info(args):
    """The inventory's `rail` block: joint names, limits, base origin and the rail's own parts (arm clearance)."""
    return {"names": list(RAIL_JOINTS_V2),
            "limits": [[-args.rail_x_stroke / 2, args.rail_x_stroke / 2], list(args.rail_y_limits),
                       list(args.rail_z_limits)],
            "origin": [args.rail_origin[0], args.rail_origin[1], args.rail_origin[2] + args.carriage_height],
            "parts": layout_v2.rail_parts(args.rail_origin, args.rail_x_stroke, args.rail_y_limits,
                                          ROOM["rail_base_height"], args.carriage_height,
                                          lift_travel=float(args.rail_z_limits[1]))}


def room(args):
    """All static boxes, shelf cell centres, inlet centres, and the belt start, from the arguments."""
    if getattr(args, "workcell_layout", None):
        from p3sim import workcell_layout
        out = workcell_layout.room(args, args.workcell_data)
        if hospital_full(args):
            zones, hospital_info = hospital_layout(args)
            out.update(zones=zones, hospital=hospital_info, belt_start=hconv.SPAWN)
        return out
    v2 = None
    hospital = hospital_full(args)
    if getattr(args, "scene", "v1") == "v2":
        params = v2_params(args)
        shelf, v2_cells = layout_v2.shelves(params)
        cabinet, module_target = layout_v2.dispenser_with_hole(args.dispenser_origin, args.dispenser_size,
                                                               params["module_hole"])
        bin_boxes, round_target = layout_v2.round_bin_boxes(params["round_bin"])
        face_y = args.dispenser_origin[1] - args.dispenser_size[1] / 2.0
        _unused, _inlets, outlet = roomlib.dispenser_boxes(
            args.dispenser_origin, args.dispenser_size, args.inlet_size, args.inlet_height, ROOM["inlet_wall"],
            args.belt_top, ROOM["outlet_size"])
        outlet_box = [roomlib.Box("DispenserOutlet", (outlet[0] + ROOM["outlet_size"][0] / 2, outlet[1],
                                                      args.belt_top + ROOM["outlet_size"][2] / 2),
                                  ROOM["outlet_size"], roomlib.COLORS["outlet"], "visual")]
        dispenser = cabinet + [layout_v2.ledge_box(params["ledge"], face_y, params["round_bin"])] + bin_boxes
        if not hospital:  # 병원: 봉투는 씬 컨베이어 출발점에 나온다 — 우리 배출구 상자는 없다
            dispenser += outlet_box
        cells, inlets = {}, {}
        v2 = {"cells": v2_cells, "targets": {"round": round_target, "module": module_target}}
    else:
        shelf, cells = roomlib.shelf_boxes(args.shelf_origin, args.shelf_cols, args.shelf_rows,
                                           tuple(args.shelf_cell), args.shelf_depth, args.shelf_plinth)
        dispenser, inlets, outlet = roomlib.dispenser_boxes(
            args.dispenser_origin, args.dispenser_size, args.inlet_size, args.inlet_height, ROOM["inlet_wall"],
            args.belt_top, ROOM["outlet_size"], inlet_gap=args.inlet_gap)
    belt_start = args.belt_start or (outlet[0], outlet[1], args.belt_top)
    half = args.belt_width / 2.0 + 0.03
    wall = roomlib.wall_boxes(args.wall_x, ROOM["wall_y_range"], ROOM["wall_height"], ROOM["wall_thickness"],
                              (belt_start[1] - half, belt_start[1] + half),
                              (args.belt_top - args.belt_thickness - 0.05, args.belt_top + ROOM["belt_opening_above"]),
                              args.door_y, ROOM["door_width"])
    rails = roomlib.rail_boxes(args.rail_origin, args.rail_x_stroke, args.rail_y_limits, ROOM["rail_base_height"],
                               ROOM["carriage_height"])
    end_x = belt_start[0] + args.belt_length
    loading = [roomlib.Box("LoadingSpot", (end_x + 0.35, belt_start[1], 0.005), (0.6, 0.8, 0.01),
                           roomlib.COLORS["loading"], "visual")]
    legs = [roomlib.Box(f"BeltLeg{i}", (belt_start[0] + f * args.belt_length, belt_start[1],
                                        (args.belt_top - args.belt_thickness) / 2),
                        (0.05, args.belt_width * 0.8, args.belt_top - args.belt_thickness),
                        roomlib.COLORS["belt_frame"], "fixed") for i, f in enumerate((0.1, 0.5, 0.9))]
    boxes = shelf + dispenser + wall + rails + loading + legs
    zones = None
    full_loop = None
    hospital_info = None
    if hospital:
        # 병원: 씬에 벽·컨베이어가 있다. 우리 벽·벨트 다리·적재 자리는 만들지 않는다(재범 결정 9/23).
        boxes = shelf + dispenser + rails
        belt_start = hconv.SPAWN
        zones, hospital_info = hospital_layout(args)
    if getattr(args, "full_loop", False):
        # K1: 조제실 밖 한 바퀴. 치수는 전부 임시값이고 zone 자세의 단일 출처는 이 레이아웃이다.
        corridor, _line = roomlib.corridor_boxes()
        ward, _frames = roomlib.ward_boxes()
        docks, _dframes = roomlib.dock_boxes()
        boxes = boxes + corridor + ward + docks
        zones = roomlib.full_loop_zones(belt_end_xy=(end_x, belt_start[1]))
        # 첫 L3 를 화면 없이 판정하려면 무엇이 얹혔는지 로그에 있어야 한다(작전 9/21).
        full_loop = {"corridor": len(corridor), "ward": len(ward), "dock": len(docks),
                     "beds": roomlib.bed_zones()}
    if v2 is not None:
        v2["obstacles"] = [layout_v2.aabb_of(box) for box in shelf + dispenser + rails if box.kind == "fixed"]
    return {"boxes": boxes, "cells": cells, "inlets": inlets, "belt_start": belt_start, "v2": v2,
            "zones": zones, "full_loop": full_loop, "hospital": hospital_info}


def validate(args):
    problems = []
    base = getattr(args, "base_usd", None)
    if base:
        base_path = Path(base).expanduser()
        if not base_path.is_file():
            problems.append(f"--base-usd does not exist: {base}")
        elif base_scene.placeholders(base_path):
            problems.append(f"--base-usd still has {base_scene.placeholders(base_path)}; run "
                            "sim/standalone/prepare_hospital_scene.py first (sim/README.md 병원 배치 씬)")
    elif getattr(args, "preset", None) == "hospital-v2":
        problems.append("--preset hospital-v2 needs --base-usd <scene from prepare_hospital_scene.py>")
    elif getattr(args, "preset", None) == "hospital-nav":
        problems.append("--preset hospital-nav needs --base-usd <hospital_navigationv1.usda>")
    elif hospital_full(args):
        pass  # hospital_full_problems 가 --base-usd 를 요구한다(같은 말을 두 번 하지 않는다)
    elif (any(getattr(args, "pharmacy_origin", [0.0] * 4)) or getattr(args, "base_deactivate", [])
          or getattr(args, "base_rigid_off", [])):
        problems.append("--pharmacy-origin, --base-deactivate and --base-rigid-off need --base-usd")
    if getattr(args, "canister_qr_dir", None) and (not getattr(args, "catalog", None) or args.scene != "v2"):
        problems.append("--canister-qr-dir needs --catalog and scene v2 (the catalog maps shelf cells to cn- ids)")
    if getattr(args, "m0609_hand_camera", False) and not args.robot_usd:
        problems.append("--m0609-hand-camera needs --robot-usd (the camera follows the M0609 link_6)")
    if getattr(args, "pedestrians", 0) and not (0 <= args.pedestrians <= 2):
        problems.append(f"--pedestrians 는 0-2 다: {args.pedestrians}")
    if getattr(args, "traffic_dummies", 0):
        if not (0 <= args.traffic_dummies <= 2):
            problems.append(f"--traffic-dummies 는 0-2 다: {args.traffic_dummies}")
        if not (args.amr and args.amr_combined):
            problems.append("--traffic-dummies 는 --amr --amr-combined 와 같이 준다(더미가 합본 모양이다)")
    if getattr(args, "block_path", False):
        if not (args.amr and args.amr_combined and getattr(args, "amr_lidar", False)):
            problems.append("--block-path 는 --amr --amr-combined --amr-lidar 와 같이 준다(라이다가 캡슐을 봐야 "
                            "정지 규칙이 든다)")
        if args.block_path_trigger is not None and not args.block_path_trigger > 0:
            problems.append(f"--block-path-trigger 는 0 보다 커야 한다: {args.block_path_trigger}")
        if args.block_path_hold is not None and not args.block_path_hold > 0:
            problems.append(f"--block-path-hold 는 0 보다 커야 한다: {args.block_path_hold}")
    if getattr(args, "amr_count", 1) != 1 and not (args.amr and args.amr_combined):
        problems.append("--amr-count 는 --amr --amr-combined 와 같이 준다(합본 AMR 을 여러 대 세우는 것이다)")
    if getattr(args, "amr_count", 1) < 1 or getattr(args, "amr_count", 1) > len(amrlib.EXTRA_DOCK_NAMES) + 1:
        problems.append(f"--amr-count 는 1-{len(amrlib.EXTRA_DOCK_NAMES) + 1} 이다: {args.amr_count}")
    if getattr(args, "amr_hand_camera", False) and not (args.amr and args.amr_combined):
        problems.append("--amr-hand-camera needs --amr --amr-combined <ridgeback_ur5.usd> (the pedestal UR5 has "
                        "its own camera)")
    if getattr(args, "lidar_debug", False) and not getattr(args, "amr_lidar", False):
        problems.append("--lidar-debug 는 --amr-lidar 와 같이 준다(그릴 스캔이 있어야 한다)")
    if getattr(args, "amr_lidar", False) and not (args.amr and args.amr_combined):
        problems.append("--amr-lidar needs --amr --amr-combined <ridgeback_ur5.usd> (the lidar sits on the "
                        "combined base)")
    if getattr(args, "preset", None) == "hospital-nav" and args.amr_start is None:
        problems.append("--preset hospital-nav needs --amr-start X Y (dock_1 of config/zones.hospital.yaml); "
                        "the default is the empty world's dock")
    if hospital_full(args):
        problems += hospital_full_problems(args)
    elif getattr(args, "pouch_at_end", False):
        problems.append("--pouch-at-end needs --hospital-full (--preset hospital or hospital-full): "
                        "it places the pouch at the hospital A1 roller end")
    if args.shelf_cols < 1 or args.shelf_rows < 1:
        problems.append("--shelf-cols and --shelf-rows must be at least 1")
    elif getattr(args, "scene", "v1") == "v1" and tuple(args.pick_cell) not in room(args)["cells"]:
        problems.append(f"--pick-cell {args.pick_cell} is not a shelf cell")
    if args.room_canister_size[0] >= args.shelf_cell[0] or args.room_canister_size[2] >= args.shelf_cell[1]:
        problems.append("--room-canister-size does not fit a shelf cell")
    if not hospital_full(args):  # 병원은 우리 벨트가 없다 — 벽·출발 구간·끝 구간 검사는 우리 벨트 것이다
        belt_start = room(args)["belt_start"]
        if (not getattr(args, "workcell_layout", None)
                and not belt_start[0] < args.wall_x < belt_start[0] + args.belt_length):
            problems.append("the belt must pass through the wall: belt start < --wall-x < belt end")
        low, high = args.spawn_along
        if low < 0.0 or high > args.belt_length - args.end_zone:
            problems.append("--spawn-along must stay between the belt start and the end zone")
        half = args.belt_width / 2.0
        if args.spawn_lateral[0] < -half or args.spawn_lateral[1] > half:
            problems.append("--spawn-lateral must stay within the belt width")
        if args.end_zone > args.belt_length:
            problems.append("--end-zone is longer than the belt")
    if getattr(args, "ur5", False) and args.ros_pick_stand_in_s > 0:
        # The UR5 has to pick the pouch itself; a timed stand-in would free the belt instead (CPS plan test 6).
        problems.append(f"--ur5 cannot run with --ros-pick-stand-in-s {args.ros_pick_stand_in_s:g} (presets set 5); "
                        "give --ros-pick-stand-in-s 0")
    if getattr(args, "gripper_command_seq", False) and not (getattr(args, "ur5", False) and args.mode == "ros"):
        problems.append("--gripper-command-seq needs --ur5 and --mode ros (it drives the UR5 suction)")
    if getattr(args, "sim_sensors", False):
        if args.mode != "ros":
            problems.append("sim_sensors config error: --sim-sensors needs --mode ros "
                            "(the JSON bridge carries them)")
        problems += bed_patient_problems(args)
    return problems


def hospital_full_problems(args):
    """--hospital-full 이 기동 전에 요구하는 것. 사이트 값(씬·AMR 합본 경로)은 기본값을 두지 않는다."""
    problems = []
    if not getattr(args, "base_usd", None):
        problems.append(f"--preset hospital-full needs --base-usd <{HOSPITAL_SCENE.relative_to(REPO)}>")
    if getattr(args, "amr_start", None) is None:
        problems.append("--preset hospital-full needs --amr-start X Y (dock_1 of config/zones.hospital.yaml); "
                        "the default is the empty world's dock")
    if not (getattr(args, "amr", False) and getattr(args, "amr_combined", None)):
        problems.append("--preset hospital-full needs --amr --amr-combined <ridgeback_ur5.usd> (the combined arm "
                        "picks at the roller end; a pedestal UR5 would stand at the empty world's spot)")
    if getattr(args, "scene", "v1") != "v2":
        problems.append("--preset hospital-full needs --scene v2 (the translated v2 pharmacy module)")
    if getattr(args, "no_room", False):
        problems.append("--preset hospital-full builds the pharmacy module; drop --no-room")
    zones_file = getattr(args, "zones_file", None)
    if not zones_file or not Path(zones_file).expanduser().is_file():
        problems.append(f"--preset hospital-full needs --zones-file <zones.hospital.yaml>; not found: {zones_file}")
        return problems
    try:
        _zones, info = hospital_layout(args)
    except (OSError, ValueError, KeyError) as error:
        problems.append(f"--zones-file {zones_file}: {error}")
        return problems
    if info["belt_end"] is None:
        problems.append(f"--zones-file {zones_file} has no pharmacy.belt_end (the truth pouch sensor centre)")
    return problems


def sensorlib_frame_default(namespace="/amr_1"):
    """센서 자세의 기준 프레임 기본값 = 받침대 UR5 밑동(결정 47). 팔의 `arm_base_frame` 과 같은 이름이다."""
    from p3sim import sensors as sensorsmod

    return sensorsmod.frame(namespace, ur5_cell.UR5_BASE_LINK)


def bed_patients(args):
    """`{침상: {환자 id}}` from --order-pool, or {} without it. PyYAML 없이 읽는다."""
    if not getattr(args, "order_pool", None):
        return {}
    return sensorlib.bed_patients(Path(args.order_pool).expanduser().read_text())


def bed_patient_problems(args):
    """인식표 센서의 fail-closed 둘 중 하나: **한 침상에 환자가 둘 이상이면 기동을 거부**한다.

    어느 인식표를 낼지 모르는 채로 하나를 고르면 인증이 조용히 틀린다(비전 9/21). 나머지 하나
    ("풀에 없는 침상 앞에서는 아무것도 안 낸다")는 발행 쪽에 있다.
    """
    if not getattr(args, "order_pool", None):
        return ["sim_sensors config error: --sim-sensors needs --order-pool "
                "(tag ids come from it: 'pt-' + patient_id)"]
    path = Path(args.order_pool).expanduser()
    if not path.is_file():
        return []  # --order-pool 자체의 문제는 위에서 이미 잡는다
    table = bed_patients(args)
    if not table:
        return [f"sim_sensors config error: no bed/patient_id pairs in {path}"]
    ambiguous = sensorlib.ambiguous_beds(table)
    if ambiguous:
        return [f"sim_sensors config error: {ambiguous} have more than one patient in {path}; "
                "the stage would not know which tag to publish"]
    return []


def known_order_ids(args):
    if not args.order_pool:
        return None
    return pouch.order_ids_from_pool_text(Path(args.order_pool).expanduser().read_text())


def is_known(order_id, pool_ids):
    return pouch.is_order_id(order_id) and (pool_ids is None or order_id in pool_ids)


def startup_line(args):
    """First log line: which preset and every resolved argument, so a log alone tells how the stage was started."""
    resolved = json.dumps(vars(args), sort_keys=True, separators=(",", ":"), default=str)
    return f"preset={args.preset or '-'} resolved_args={resolved}"


def scene_line(args):
    """Second log line: which base scene file was given, its sha256 and the units its root layer authors.

    Kept off startup_line, whose resolved_args JSON runs to the end of the line. Values that cannot be read are
    'unknown', never guessed; '-' when there is no --base-usd."""
    base = getattr(args, "base_usd", None)
    if not base:
        return "scene base_usd=- base_usd_sha256=- meters_per_unit=- up_axis=-"
    path = Path(base).expanduser()
    try:
        data = path.read_bytes()
    except OSError:
        return f"scene base_usd={path} base_usd_sha256=unknown meters_per_unit=unknown up_axis=unknown"
    meters, up = base_scene.layer_units(data)
    return (f"scene base_usd={path} base_usd_sha256={hashlib.sha256(data).hexdigest()} "
            f"meters_per_unit={meters} up_axis={up}")


def run(args):
    log(startup_line(args))
    log(scene_line(args))
    problems = validate(args)
    if args.order_pool and not Path(args.order_pool).expanduser().is_file():
        problems.append(f"--order-pool does not exist: {args.order_pool}")
    if problems:
        for problem in problems:
            refill.write_line(f"[pharmacy_stage] error layout: {problem}", sys.stderr)
        return 2

    from isaacsim import SimulationApp

    app_config = refill.simulation_app_config(args)
    app_config["extra_args"] = []
    if args.window_half and not args.headless and not args.livestream:
        half = views.window_half(args.window_half, args.screen_size)
        app_config["extra_args"] += half.pop("extra_args")
        app_config.update(half)
        log(f"window half={args.window_half} screen={args.screen_size} config={app_config}")
    if args.kit_log_file:
        Path(args.kit_log_file).expanduser().parent.mkdir(parents=True, exist_ok=True)
        app_config["extra_args"] += diag.kit_log_args(str(Path(args.kit_log_file).expanduser()), args.kit_log_verbose)
    simulation_app = SimulationApp(app_config)
    stop_event = threading.Event()
    clock.install_sigint_handler(stop_event)
    exit_code = 0
    ros = None
    try:
        import math

        import numpy as np
        import omni.kit.app
        import omni.usd
        from isaacsim.core.utils.extensions import enable_extension

        log(f"kit_log settings={diag.kit_log_settings()} requested={args.kit_log_file or '-'}")
        quit_watch = diag.subscribe_quit(log)  # kept alive for the whole run
        a1_probe = diag.A1Probe()  # review A1: exit-cause probe, subscriptions kept for the whole run
        try:
            a1_probe.install()
        except Exception as exc:  # diagnostics must not end the stage
            log(f"a1_probe install failed {type(exc).__name__}: {exc}")
        if args.livestream:
            enable_extension(args.livestream_extension)
        enable_extension(clock.ROS2_BRIDGE_EXTENSION)
        enable_extension(CONVEYOR_EXTENSION)
        simulation_app.update()
        manager = omni.kit.app.get_app().get_extension_manager()
        for extension in (clock.ROS2_BRIDGE_EXTENSION, CONVEYOR_EXTENSION):
            if not manager.is_extension_enabled(extension):
                raise RuntimeError(f"{extension} did not stay enabled; see the startup log")
        clock.build_clock_graph()

        import omni.timeline

        timeline_flags = {"stopped": False, "closing": False}
        sim_clock = {"last": 0.0}
        trace = common.TickTrace(ticks=3)

        def on_timeline(name):
            # simulation_app.close() stops the timeline after the clock graph is gone: reading it then raised
            # OmniGraphError (9/17 master02, after --duration and app_stopped ends), so log the last read value.
            if timeline_flags["closing"]:
                log(f"timeline_event type={name} sim_time_last={sim_clock['last']:.3f} (closing)")
                return
            log(f"timeline_event type={name} sim_time={clock.read_graph_sim_time():.3f}")
            if name == "STOP":
                timeline_flags["stopped"] = True
                # 9/17 20:49:19 master02: a STOP came from inside Kit with no line before it. Record who and when.
                log(f"timeline_stop_context timeline={diag.timeline_state()} python_stack={diag.python_stack(12)}")
                log(f"timeline_stop_context recent_calls={trace.dump()}")

        timeline_events = omni.timeline.get_timeline_interface().get_timeline_event_stream()
        timeline_subscriptions = [  # kept alive for the whole run
            timeline_events.create_subscription_to_pop_by_type(
                int(getattr(omni.timeline.TimelineEventType, name)), lambda event, n=name: on_timeline(n))
            for name in ("PLAY", "PAUSE", "STOP")
        ]

        arm_ros = None
        ur5_ros = None
        amr_ros = None
        if args.mode == "ros":
            if args.ur5 and not args.amr_combined:
                ur5_ros = refill.RosBridge(ur5_cell.UR5_JOINTS, namespace="/amr_1", node_name="isaac_amr_1_arm")
            if args.amr:
                # 팔이 없어도 베이스만 돌 수 있어야 한다(K2 는 주행 단독 회차가 먼저다).
                # 합본이면 팔 6관절도 이 브리지가 받는다 — 받침대 UR5 는 그 구성에서 안 만든다.
                if ur5_ros is not None:
                    amr_ros = ur5_ros
                else:
                    arm_names = amrlib.ARM_JOINT_NAMES if args.amr_combined else []
                    amr_ros = refill.RosBridge(arm_names, namespace="/amr_1", node_name="isaac_amr_1_base")
                amr_ros.add_amr_topics(amrlib.JOINT_NAMES)
            if args.robot_usd:
                arm_ros = refill.RosBridge(args.arm_joints)  # calls rclpy.init(); JsonBridge reuses the context
                arm_ros.add_rail_topics(RAIL_JOINTS_V2 if args.scene == "v2" else RAIL_JOINTS)
                if args.scene == "v2":
                    arm_ros.add_inventory_topic()
            ros = JsonBridge(
                extra_publish=((bridge.BELT_OBSERVATION,) if args.belt_observation else ())
                + ((bridge.GRIPPER_STATE,) if args.gripper_command_seq else ())
                + ((bridge.POUCHES, bridge.TAG_READS, bridge.CABINET) if args.sim_sensors else ())
                + ((bridge.FLEET_POSES,) if fleet_poses_wanted(args) else ()),
                extra_subscribe=(bridge.GRIPPER_COMMAND_SEQ,) if args.gripper_command_seq else ())

        from isaacsim.core.api import World
        from isaacsim.core.api.objects import DynamicCuboid, GroundPlane

        world = World(stage_units_in_meters=1.0, physics_dt=args.physics_dt, rendering_dt=args.render_dt)
        if args.render_every > 1:
            # 회차 로그에서 이 설정을 찾을 수 있게 남긴다. 센서 주기도 같이 내려간다는 것이 요점이다.
            log(f"render_every n={args.render_every} physics_hz={1.0 / args.physics_dt:.1f} "
                f"render_hz={render_hz(args):.1f} (Kit 갱신·OmniGraph·ROS 발행이 render_hz 로 돈다)")
        stage = omni.usd.get_context().get_stage()
        GroundPlane(prim_path=f"{STAGE_ROOT}/GroundPlane")
        refill.ensure_light(stage)
        if args.base_usd:  # 이식 준비: 세준 hospital under us; our coordinates stay the world frame
            with common.step(log, "add_base_scene"):
                info = base_scene.add_base_scene(stage, str(Path(args.base_usd).expanduser()),
                                                 args.pharmacy_origin, args.base_deactivate, args.base_rigid_off,
                                                 root_prims=args.base_root_prims)
            # Keep the ground plane's collision but not its picture: it lies on the base scene's floor (z-fighting).
            from pxr import UsdGeom

            UsdGeom.Imageable(stage.GetPrimAtPath(f"{STAGE_ROOT}/GroundPlane")).MakeInvisible()
            log(f"base_scene usd={args.base_usd} pharmacy_origin={args.pharmacy_origin} {json.dumps(info)}")
            if info["missing"]:
                log(f"WARN base_scene deactivate paths not found: {info['missing']}")
            if info["root_prims_skipped"]:
                log(f"WARN base_scene root prims outside the default prim not loaded (--base-root-prims): "
                    f"{info['root_prims_skipped']}")
            if info["articulations"]:
                log(f"WARN base_scene articulations this stage does not drive: {info['articulations']}")
            for _ in range(10):
                simulation_app.update()
        conveyor = None
        route_tracks = None
        if hospital_full(args):
            # #527 H2: 씬 컨베이어를 우리가 돌린다. 참조 아래서 그래프가 안 돌아(#240) 표면 속도를 직접 쓴다.
            # 끝 롤러의 기하가 실려야 끝 판정이 선다 — 참조 탐침처럼 스테이지 로딩이 끝나기를 먼저 기다린다.
            with common.step(log, "hospital_conveyor"):
                context = omni.usd.get_context()
                waited = 0
                while waited < 600 and context.get_stage_loading_status()[2] > 0:
                    simulation_app.update()
                    waited += 1
                conveyor = hconv.HospitalConveyor(stage, hconv.REFERENCED_CONVEYOR_ROOT, args.conveyor_surfaces,
                                                  speed_scale=args.conveyor_speed_scale)
                conveyor_info = conveyor.discover()
                route_tracks = conveyor.tracks()
                # 발견이 끝나면 씬 그래프를 끈다. 켜 두면 ConveyorNode 가 매 틱 자기 Velocity(우리가 0 으로
                # 둔 값)를 몸체에 써서 우리가 쓴 잰 값을 덮는다 — 9/23 회차에서 before_play (-0.5,0,0) 이
                # after_reset (0,0,0) 이 되고 봉투가 출발점에 섰다(m2-hf-full-5a59776).
                conveyor_info["graphs_off"] = conveyor.silence_graphs()
                conveyor_info["speed_scale"] = conveyor.speed_scale
                # 잰 탐침 02 처럼 Play 전에 써 두고 끝까지 둔다. Play 뒤 USD 속성 쓰기는 PhysX 에 닿지 않았다
                # (I1 bbedd65: DISPENSED 뒤 running=False·표면 속도 0, 봉투가 제자리). 끝 롤러에서도 탐침은 켠 채 섰다.
                conveyor.run()
            log(f"hospital_conveyor loading_updates={waited} surfaces={args.conveyor_surfaces} "
                f"tracks={len(route_tracks)} {json.dumps(conveyor_info, separators=(',', ':'))}")
        layout = room(args)
        args.belt_start = layout["belt_start"]
        stock_present = None
        if getattr(args, "workcell_layout", None) and layout["v2"] is not None:
            # 잰 배치는 선반마다 왼쪽 원통·오른쪽 모듈로 고정이라 약통이 줄 맞춰 선다(재범 9/23).
            # 시드로 종류와 빈 칸을 섞는다. 약통을 세우는 것·QR 면·팔에 내는 재고가 **이 한 벌**에서 나온다.
            from p3sim import workcell_layout
            layout["v2"]["cells"], stock_present = workcell_layout.shuffled_stock(
                layout["v2"]["cells"], args.seed, args.workcell_empty_cells)
            kinds = {}
            for cell_id, cell in sorted(layout["v2"]["cells"].items()):
                kinds.setdefault(cell["type"], []).append(cell_id)
            log(f"workcell_stock seed={args.seed} cells={len(stock_present)} "
                f"present={sum(stock_present.values())} empty="
                f"{sorted(c for c, ok in stock_present.items() if not ok)} "
                f"kinds={ {k: len(v) for k, v in sorted(kinds.items())} }")

        def canister_home(key):
            """Centre of the canister of shelf cell `key` standing on its cell (v1 keys (row, col), v2 cell ids)."""
            if layout["v2"] is not None:
                return layout_v2.canister_home(layout["v2"]["cells"][key])
            x, y, z = layout["cells"][key]
            return (x, y, z + args.room_canister_size[2] / 2.0)
        canisters = None
        canister_faces = None   # --canister-qr-dir: 약통 QR 면(약통이 움직이면 따라 옮긴다)
        m0609_camera = None     # --m0609-hand-camera
        amr = None
        amr_suction = None
        amr_slots = []
        amr_deck_frames = []   # 합본 상판의 칸 중심(base_link 로컬). 세계 좌표는 쓸 때 변환한다
        amr_lidar_path = None  # --amr-lidar: base_link 아래 라이다 프림(TF 로 같이 낸다)
        zones_state = {"paths": []}
        if not args.no_room:
            with common.step(log, "build_room"):
                scene.build_boxes(f"{STAGE_ROOT}/Room", layout["boxes"])
                if layout["v2"] is None:
                    canisters = scene.build_canisters(f"{STAGE_ROOT}/Shelf", layout["cells"],
                                                      args.room_canister_size, 0.1, args.pick_cell)
                else:
                    # 빈 칸에는 약통을 세우지 않는다. 팔은 재고의 present 로 같은 칸을 건너뛴다.
                    stocked = {cell_id: cell for cell_id, cell in layout["v2"]["cells"].items()
                               if stock_present is None or stock_present.get(cell_id, True)}
                    canisters = scene.build_canisters_v2(f"{STAGE_ROOT}/Shelf", stocked, 0.1)
                    if args.canister_qr_dir:
                        try:
                            with common.step(log, "canister_qr"):
                                containers = canister_qr.shelf_containers(
                                    Path(args.catalog).expanduser().read_text(encoding="utf-8"))
                                canister_faces = canister_qr.CanisterFaces(
                                    stage, f"{STAGE_ROOT}/CanisterQr", stocked, containers,
                                    Path(args.canister_qr_dir).expanduser(), log)
                                for cell_id, cell in stocked.items():
                                    canister_faces.follow(cell_id, layout_v2.canister_home(cell), (1.0, 0.0, 0.0, 0.0))
                        except Exception as error:  # QR 이 없어도 보충은 돈다(팔의 약통 확인이 unreadable 로 거부한다)
                            log(f"WARN canister_qr disabled reason={type(error).__name__}: {error}")
                            canister_faces = None
                if layout.get("full_loop"):
                    summary = layout["full_loop"]
                    log(f"full_loop corridor_boxes={summary['corridor']} ward_boxes={summary['ward']} "
                        f"dock_boxes={summary['dock']} beds={summary['beds']} "
                        f"total_boxes={len(layout['boxes'])}")
                if layout.get("hospital"):
                    hospital = layout["hospital"]
                    sizes = {k: tuple(round(v, 4) for v in size) for k, size in hospital["cabinet_sizes"].items()}
                    log(f"hospital_full zones={len(layout['zones'])} zones_file={args.zones_file} "
                        f"belt_end={common.format_values(hospital['belt_end'])} cabinet_sizes={sizes} "
                        f"v2_offset={args.v2_offset} rail_origin={common.format_values(args.rail_origin)} "
                        f"dispenser_origin={common.format_values(args.dispenser_origin)} "
                        f"total_boxes={len(layout['boxes'])} (우리 벽·벨트·적재 자리 없음)")
                if layout.get("zones"):
                    # K1: 구역 고정 프레임(계약 3절). map·odom 은 내지 않는다 — 그 작성자는 base_driver 다.
                    zone_paths = zoneslib.build(stage, f"{STAGE_ROOT}/Zones", layout["zones"], log)
                    zones_state["paths"] = zone_paths
                if getattr(args, "patient_plates", False) and layout.get("hospital") and args.qr_dir:
                    # 시각 소품만(작전 9/23). 인증은 참값 센서 그대로다. 실패해도 한 바퀴는 돈다.
                    try:
                        from p3sim import patient_plates

                        from p3sim import hospital_zones as hzones

                        plates = patient_plates.plates(layout["zones"], layout["hospital"]["cabinet_sizes"],
                                                       bed_patients(args), hzones.station_tables(args.zones_file))
                        patient_plates.build(stage, f"{STAGE_ROOT}/PatientPlates", plates,
                                             Path(args.qr_dir).expanduser(), log)
                    except Exception as error:
                        log(f"WARN patient_plates disabled reason={type(error).__name__}: {error}")
                if getattr(args, "hospital_decor", False) and layout.get("hospital") and layout.get("zones"):
                    # 바닥 표시(재범 9/24 "병원 데코", 최적화 예산). 시각 소품만이고 바닥 1.5 mm 안이라
                    # 라이다가 못 본다. 실패해도 한 바퀴는 돈다.
                    try:
                        build_hospital_decor(stage, args, layout, log)
                    except Exception as error:
                        log(f"WARN hospital_decor disabled reason={type(error).__name__}: {error}")
            if layout["v2"] is None:
                log(f"room shelf_cells={len(layout['cells'])} pick_cell={args.pick_cell} "
                    f"pick_xyz={common.format_values(layout['cells'][tuple(args.pick_cell)])} "
                    f"inlet_a={common.format_values(layout['inlets']['a'])} "
                    f"inlet_b={common.format_values(layout['inlets']['b'])} "
                    f"belt_start={common.format_values(args.belt_start)} "
                    f"wall_x={args.wall_x}")
            else:
                kinds = sorted({c["type"] for c in layout["v2"]["cells"].values()})
                log(f"room scene=v2 source={layout_v2.SOURCE} shelves={[s['name'] for s in V2['shelves']]} "
                    f"cells={len(layout['v2']['cells'])} kinds={kinds} "
                    f"round_bin={layout['v2']['targets']['round']} module_hole={layout['v2']['targets']['module']} "
                    f"rail_z_limits={args.rail_z_limits}")
        if args.amr:
            # 방(--no-room)과 무관하게 만든다(9/23 병원 주행 v0: 병원 씬 위에 우리 방 없이 AMR 만 세운다).
            # 방을 만드는 경우는 예전과 같은 순서다(방 다음). 예전에는 --no-room 이면 --amr 이 조용히 빠졌다.
            with common.step(log, "build_amr"):
                # K2: dummy 3축 이동 베이스. 출발 자리 기본값은 빈월드의 dock_1 이다.
                # --amr-usd 를 주면 공식 합본(ridgeback_ur5.usd)을 참조한다(재범 지시 9/21 — 상자로 한
                # 시험은 뜻이 없다). 안 주면 지금까지의 상자 그대로다(기본 동작 불변).
                start_xy = tuple(args.amr_start) if args.amr_start else roomlib.DOCK["centre"]
                if args.amr_combined:
                    art_path, _base, _joints = amrlib.reference(
                        stage, AMR_ROOT, args.amr_combined, start_xy, log=log)
                else:
                    amrlib.build(stage, AMR_ROOT, start_xy)
                    art_path = f"{AMR_ROOT}/root_joint"
                if args.amr_combined:
                    # 9/21 재범 확정안: 팔은 몸체 뒤끝 + 낮은 받침, 반대쪽 끝은 통짜 트레이.
                    # **밑동 프레임보다 먼저** 옮긴다 — 프레임은 어깨 프림의 자리를 재서 만들기 때문에
                    # 옮기기 전에 재면 옛 자리에 박힌다.
                    amrlib.move_arm_mount(stage, AMR_ROOT, log=log)
                    # 팔 밑동 프레임은 자산에 링크가 없어 우리가 만든다. **원점은 어깨에서 재고**
                    # 축은 UR URDF base_link 관례를 따른다(비전 9/21) — 몸체 원점에 얹으면
                    # 장착 오프셋만큼 조용히 어긋난다.
                    amrlib.build_arm_base_frame(stage, AMR_ROOT, log)
                    # 트레이도 베이스 링크의 자식 충돌체로 얹는다 — 월드 고정이면 AMR 이 가도 남는다.
                    amr_slots, _tray_root, amr_deck_frames = amrlib.build_tray_on_base(
                        stage, AMR_ROOT, roomlib, log=log)
                if args.amr_combined and args.amr_lidar:
                    # Nav2 트랙(9/23): AMCL·costmap 이 읽는 /amr_1/scan. 실패해도 AMR 은 돈다(waypoints 는 안 쓴다).
                    try:
                        mount = tuple(args.amr_lidar_mount) if args.amr_lidar_mount else amrlib.LIDAR_MOUNT_LOCAL
                        amr_lidar_path = amrlib.add_lidar(stage, AMR_ROOT, f"{AMR_ROOT}/LidarGraph", mount=mount,
                                                          log=log)
                    except Exception as error:
                        log(f"WARN amr lidar disabled reason={type(error).__name__}: {error}")
                    if args.lidar_debug and amr_lidar_path:
                        try:  # 촬영용 그림이다 — 못 그려도 라이다·회차는 그대로다
                            amrlib.add_lidar_debug_draw(amr_lidar_path, log=log)
                        except Exception as error:
                            log(f"WARN amr lidar debug draw disabled reason={type(error).__name__}: {error}")
                # 도크=적재이면 주행을 생략하므로, 기동 때부터 YAML 도크 방향으로 서야 한다.
                # x/y 관절은 출발점 기준 변위이고 yaw 관절은 세계 방향이다(map->odom 은 평행이동만).
                start_yaw = layout["zones"]["dock_1"][3] if hospital_full(args) else 0.0
                amr = amrlib.Runtime(world, AMR_ROOT, start_xy, log=log, articulation_path=art_path,
                                     start_yaw=start_yaw)
                if args.amr_combined:
                    # 합본 팔의 흡착. 받침대 셀이 없으므로 `/amr_1/gripper/*` 의 작성자·수신자가 여기다.
                    # 그리퍼 자산을 붙이면 흡착점이 손목에서 그리퍼 길이만큼 멀어진다.
                    # 사람이 준 값이 없으면 자산 값을 쓴다.
                    tcp = (amrlib.GRIPPER_TCP_OFFSET if args.amr_hand_camera and not any(args.ur5_tcp_offset)
                           else tuple(args.ur5_tcp_offset))
                    amr_suction = amrlib.Suction(stage, AMR_ROOT, tcp, args.suck_distance, log)
                    log(f"amr suction tcp_link={amrlib.TCP_PARENT_LINK} offset={tuple(tcp)} "
                        f"limit={args.suck_distance} (wrist_3 == tool0. 그리퍼 자산이면 흡착점 오프셋, 아니면 0)")
                log(f"amr built root={AMR_ROOT} start_xy={start_xy} joints={list(amrlib.JOINT_NAMES)} "
                    f"source={'usd:' + args.amr_combined if args.amr_combined else 'box'} articulation={art_path}")
        if args.amr and args.amr_combined and args.amr_count > 1:
            # 부하 측정용 여벌(재범 9/23). **첫 대의 경로는 건드리지 않는다** — 위 블록을 그대로 두고
            # 여기서 따로 세운다. 이 대들은 `Runtime` 을 만들지 않으므로 명령을 받지 않고, 드라이브 목표가
            # 스폰 관절값이라 도크에 서 있는다. 주문·Nav2 는 `amr_1` 하나다.
            try:
                with common.step(log, "build_extra_amrs"):
                    plan = amrlib.extra_amr_plan(args.amr_count, layout.get("zones"))
                    for index, namespace, spot in plan:
                        root = f"{AMR_ROOT}{index}"
                        amrlib.reference(stage, root, args.amr_combined, spot, log=log)
                        amrlib.move_arm_mount(stage, root, log=log)
                        amrlib.build_arm_base_frame(stage, root, log)
                        _slots, _tray, deck_frames = amrlib.build_tray_on_base(stage, root, roomlib, log=log)
                        optical = None
                        if args.amr_hand_camera:
                            optical = amrlib.add_hand_camera(
                                stage, root, f"{root}/HandCameraGraph", 1.0 / args.render_dt,
                                tuple(args.camera_resolution), args.camera_max_hz, namespace=namespace, log=log)
                        lidar = None
                        if args.amr_lidar:
                            mount = tuple(args.amr_lidar_mount) if args.amr_lidar_mount else amrlib.LIDAR_MOUNT_LOCAL
                            lidar = amrlib.add_lidar(stage, root, f"{root}/LidarGraph", mount=mount,
                                                     namespace=namespace, log=log)
                        amrlib.publish_tf(stage, root, f"{root}/TfGraph", deck_frames, namespace=namespace, log=log,
                                          extra_static=(lidar,) if lidar else (),
                                          extra_dynamic=(optical,) if optical else ())
                        log(f"amr extra built root={root} ns={namespace} start_xy={spot} "
                            f"lidar={'on' if lidar else 'off'} camera={'on' if optical else 'off'} "
                            f"(주문·Nav2 없음. 서 있는다)")
            except Exception as error:  # 여벌이 없어도 한 바퀴는 돈다 — 부하 측정만 못 한다
                log(f"WARN amr extras disabled reason={type(error).__name__}: {error}")

        traffic = None
        if getattr(args, "traffic_dummies", 0) and args.amr and args.amr_combined:
            # 가짜 AMR(재범 9/24 부가 장면). 소품이라 실패해도 한 바퀴는 돈다.
            try:
                with common.step(log, "build_traffic_dummies"):
                    from p3sim import hospital_nav as hnav
                    from p3sim import traffic_dummies

                    traffic = traffic_dummies.Dummies(
                        stage, f"{STAGE_ROOT}/Traffic", args.traffic_dummies, args.amr_combined,
                        hnav.BODY_LENGTH, hnav.BODY_WIDTH, DECOR_ATLAS.with_name("dummy_label.png"), log)
            except Exception as error:
                log(f"WARN traffic dummies disabled reason={type(error).__name__}: {error}")
                traffic = None

        walkers = None
        if getattr(args, "pedestrians", 0) and layout.get("zones"):
            # 보행자(재범 9/25 회피 장면). 소품이라 실패해도 한 바퀴는 돈다.
            try:
                with common.step(log, "build_pedestrians"):
                    from p3sim import pedestrians

                    walkers = pedestrians.Pedestrians(stage, f"{STAGE_ROOT}/Pedestrians", args.pedestrians, log)
            except Exception as error:
                log(f"WARN pedestrians disabled reason={type(error).__name__}: {error}")
                walkers = None

        blocker = None
        if getattr(args, "block_path", False) and args.amr and args.amr_combined:
            # 정지 규칙 발동 시험 캡슐(#721). 소품이라 실패해도 한 바퀴는 돈다.
            try:
                with common.step(log, "build_path_block"):
                    from p3sim import path_block

                    blocker = path_block.PathBlock(
                        stage, f"{STAGE_ROOT}/PathBlock",
                        tuple(args.block_path_at) if args.block_path_at else path_block.BLOCK_XY,
                        path_block.TRIGGER_M if args.block_path_trigger is None else args.block_path_trigger,
                        path_block.HOLD_S if args.block_path_hold is None else args.block_path_hold, log)
            except Exception as error:
                log(f"WARN path block disabled reason={type(error).__name__}: {error}")
                blocker = None

        arm = None
        if args.robot_usd:
            with common.step(log, "build_rail_and_mount_robot"):
                arm_root, robot_prim, rail_names = scene.build_xy_rail_with_robot(
                    stage, f"{STAGE_ROOT}/Arm", str(Path(args.robot_usd).expanduser()), args.rail_origin,
                    args.rail_x_stroke, args.rail_y_limits, ROOM["rail_base_height"], args.carriage_height,
                    args.rail_drive, args.robot_child, log,
                    z_limits=tuple(args.rail_z_limits) if args.scene == "v2" else None)
            # Before any app update: 실습4-B (9/18) still showed 2 of the 4 Fabric warnings for link_2/visuals, our
            # reading being that Fabric filled the instanced prims during these updates, before the fix below ran.
            try:  # 재범 실습3 P6: a link without its mesh looks like the arm is cut in the middle
                scene.ensure_link_visuals(stage, robot_prim, ("base_link", *M0609_LINKS), log)
            except Exception as exc:  # a cosmetic stand-in must not stop the stage
                log(f"link_visuals check failed {type(exc).__name__}: {exc}")
            for _ in range(15):
                simulation_app.update()
            refill.override_drives(stage, robot_prim, args.arm_joints, args.arm_drive, False, "arm")
            from isaacsim.core.prims import SingleArticulation

            arm = {"root": arm_root, "robot_prim": robot_prim, "rail": rail_names,
                   "articulation": world.scene.add(SingleArticulation(prim_path=arm_root, name="m0609_on_rail"))}
            if args.m0609_hand_camera:
                try:
                    with common.step(log, "m0609_hand_camera"):
                        m0609_camera = canister_qr.M0609HandCamera(
                            stage, robot_prim, f"{STAGE_ROOT}/M0609HandCamera", f"{STAGE_ROOT}/M0609CameraGraph",
                            render_hz(args), tuple(args.m0609_camera_resolution), args.camera_max_hz, log,
                            body_asset=amrlib.gripper_usd_path())   # 화면에 보이는 D455 몸체(시각만)
                except Exception as error:  # 카메라가 없어도 장면은 돈다
                    log(f"WARN m0609 hand_camera disabled reason={type(error).__name__}: {error}")
                    m0609_camera = None
        velocity_attr = None
        if conveyor is not None:
            log("belt ours=off reason=hospital_full (봉투는 씬 컨베이어를 탄다; 속도는 --conveyor-surfaces 값)")
        else:
            with common.step(log, "create_conveyor_belt"):
                velocity_attr = scene.build_conveyor(stage, BELT_PRIM, args.belt_start, args.belt_length,
                                                     args.belt_width, args.belt_thickness, args.belt_yaw,
                                                     body=args.belt_body, presurface=args.belt_presurface)
                log(f"belt body={args.belt_body} presurface={args.belt_presurface} prim={BELT_PRIM} "
                    f"requested_speed={args.belt_speed}")
        cell = None
        if args.ur5 and args.amr_combined:
            # 합본이 자기 팔을 들고 온다. 둘 다 만들면 UR5 가 둘이 되고, `/amr_1/arm/joint_command` 의
            # 작성자·수신자가 갈라진다(받침대 팔은 접두 없는 이름, 합본은 `ur_arm_*`).
            log("ur5 pedestal disabled reason=--amr-combined (합본이 팔을 들고 온다; 받침대 UR5 는 안 만든다)")
        if args.ur5 and not args.amr_combined:
            cell = ur5_cell.Ur5Cell(stage, world, f"{STAGE_ROOT}/Loading", {
                "base": args.ur5_base, "usd": args.ur5_usd, "deck_center": args.deck_center,
                "pedestal_size": args.ur5_pedestal_size,
                "pedestal_height": args.ur5_pedestal_height,
                "deck_count": args.deck_count, "deck_slot_size": ROOM["deck_slot_size"], "deck_wall": ROOM["deck_wall"],
                "ready": args.ur5_ready, "tcp_offset": args.ur5_tcp_offset, "suck_distance": args.suck_distance,
                "base_frame": args.ur5_base_frame,
                "namespace": "/amr_1", "camera_resolution": tuple(args.camera_resolution),
                "camera_max_hz": args.camera_max_hz, "camera_offset": args.camera_offset,
                "camera_focal_mm": args.camera_focal_mm}, log)
            try:
                with common.step(log, "build_ur5_cell"):
                    cell.build()
            except common.StepError as error:
                # e.g. no asset server within its timeout: keep the rest of the stage running without the UR5.
                log(f"ur5 disabled reason={error}; continuing without --ur5 (use --ur5-usd with a local file)")
                cell = None
            if cell is not None and not args.no_hand_camera:
                try:
                    with common.step(log, "ur5_camera_and_tf"):
                        # `map` 이름의 프림을 부모로 준다 — 밑동 프레임이 map 에 붙어야 팔이 `<zone>/cabinet`
                        # (부모 `map`, 작성자 zones_tf)을 조회할 수 있다. 결정 47 로 이름을 가른 결과다.
                        cell.add_camera_and_tf(render_hz(args),
                                               world_root=zoneslib.parent_prim(stage, STAGE_ROOT))
                except common.StepError as error:
                    log(f"ur5 camera_and_tf disabled reason={error}; the UR5 still runs")
        amr_camera_optical = None
        if args.amr_combined and args.amr_hand_camera:
            # 합본 손 카메라. 받침대 UR5 의 카메라는 ur5_cell 이 달고, 합본에는 없었다(9/23).
            try:
                with common.step(log, "amr_hand_camera"):
                    amr_camera_optical = amrlib.add_hand_camera(
                        stage, AMR_ROOT, f"{AMR_ROOT}/HandCameraGraph", render_hz(args),
                        tuple(args.camera_resolution), args.camera_max_hz, log=log)
            except Exception as error:  # 카메라가 없어도 장면은 돈다(팔은 not_detected 로 닫는다)
                log(f"WARN amr hand_camera disabled reason={type(error).__name__}: {error}")
        if args.amr_combined and amr_deck_frames:
            # 합본의 로봇 링크 TF. 받침대에서는 `ur5_cell` 이 냈는데 그 셀을 안 만드니 여기서 낸다 —
            # 없으면 팔이 `놓을 곳 TF 없음` 으로 ⑤에서 닫힌다(회차 lap1).
            try:
                with common.step(log, "amr_tf"):
                    amrlib.publish_tf(stage, AMR_ROOT, f"{AMR_ROOT}/TfGraph", amr_deck_frames, log=log,
                                      extra_static=(amr_lidar_path,) if amr_lidar_path else (),
                                      extra_dynamic=(amr_camera_optical,) if amr_camera_optical else ())
            except Exception as error:  # TF 가 없으면 팔이 못 놓지만 장면은 돈다
                log(f"WARN amr tf disabled reason={type(error).__name__}: {error}")
        if zones_state["paths"] and args.zones_tf:
            # 구역 프레임은 로봇과 무관하게 나간다(계약 3절). 실패해도 스테이지는 계속 돈다.
            try:
                with common.step(log, "zones_tf"):
                    parent = zoneslib.parent_prim(stage, STAGE_ROOT)  # 이름이 map 인 프림이어야 frame_id 가 map 이다
                    zoneslib.publish(stage, f"{STAGE_ROOT}/ZoneGraph", parent, zones_state["paths"], log)
            except Exception as error:  # 진단 발행이 스테이지를 끝내면 안 된다
                log(f"zones tf_static disabled reason={type(error).__name__}: {error}; the stage still runs")
        parking = pouch.parking_positions(args.pouch_pool, args.parking_origin, 0.15, args.pouch_size[2] / 2.0)
        with common.step(log, "create_pouch_pool"):
            pool_objects = [DynamicCuboid(prim_path=f"{POUCH_ROOT}/Pouch_{i:02d}", name=f"pouch_{i}",
                                          position=np.array(spot), scale=np.array(args.pouch_size), size=1.0,
                                          mass=args.pouch_mass, color=np.array([0.95, 0.95, 0.85]))
                            for i, spot in enumerate(parking)]
        labels = [None] * args.pouch_pool
        qr_faces = []
        qr_written = {}     # 면 index -> 마지막으로 쓴 (position, orientation). 같은 자세는 다시 쓰지 않는다
        qr_following = set()  # 지난 틱에 쓰는 중이던 봉투. 주차로 돌아간 자세를 한 틱 더 따라간다
        if args.qr_dir:
            with common.step(log, "qr_textures"):
                texture_ids = known_order_ids(args)
                if not texture_ids:
                    raise RuntimeError("--qr-dir needs --order-pool to know which order goes on which pouch")
                labels = pouch.pool_labels(texture_ids, args.pouch_pool)
                qr_dir = Path(args.qr_dir).expanduser().resolve()
                from isaacsim.core.prims import SingleXFormPrim

                for index, order_id in enumerate(labels):
                    image = qr_dir / f"{order_id}.png"
                    if not image.is_file():
                        raise RuntimeError(f"missing {image}; run make_qr_textures.py")
                    face = f"{STAGE_ROOT}/QrFaces/Qr_{index:02d}"
                    scene.add_top_texture(stage, face, image, pouch.qr_face_size(args.pouch_size),
                                          args.pouch_size[2] / 2.0 + 0.0005)
                    qr_faces.append(SingleXFormPrim(prim_path=face, name=f"qr_face_{index}",
                                                    position=np.array(parking[index])))
            log(f"qr_textures dir={args.qr_dir} labels={labels}")
        pool = pouch.PouchPool(args.pouch_pool, labels)
        log(f"pouch_pool count={args.pouch_pool} parking={[common.format_values(s, 2) for s in parking]}")

        def set_belt(speed):
            trace.mark(f"belt.velocity={speed}")
            if conveyor is not None:  # 병원: 컨베이어는 Play 전부터 늘 돈다(위 discover 옆 주석). 여기서는 기록만 한다
                return
            velocity_attr.Set(float(speed))

        def belt_command_readback():
            """Belt drive value read back, not the value written: the PhysX surface velocity when the belt prim has one
            authored (closest to physics; a graph input reaches it a tick later), else the attribute set_belt writes.
            None when unreadable."""
            if conveyor is not None:
                return conveyor.readback()
            try:
                surface = stage.GetPrimAtPath(BELT_PRIM).GetAttribute("physxSurfaceVelocity:surfaceVelocity")
                attr = surface if surface and surface.HasAuthoredValue() else velocity_attr
                return attr.Get() if attr else None
            except Exception:  # noqa: BLE001 - an unreadable attribute is APPLIED_UNKNOWN, never a stop
                return None

        contact_watch = None
        contact_watch_bodies = []
        if not args.no_contact_log:
            # K3 판정선이 "접촉 0" 이라 **팔이 없어도** 감시가 돌아야 한다(작전 9/21: emptyworld-loop 에서
            # 꺼져 있었다). 감시할 몸체가 하나도 없으면 켜지 않는다.
            from pxr import Usd, UsdPhysics

            def rigid_bodies_under(root):
                prim = stage.GetPrimAtPath(root)
                if not prim.IsValid():
                    return []
                return [str(p.GetPath()) for p in Usd.PrimRange(prim) if p.HasAPI(UsdPhysics.RigidBodyAPI)]

            bodies = rigid_bodies_under(arm["root"]) if arm is not None else []
            if cell is not None and args.ur5_contact_log:
                bodies += rigid_bodies_under(cell.prim_path)
            if amr is not None:
                bodies += rigid_bodies_under(AMR_ROOT)  # 베이스 ↔ 고정 상자
            thresholds = {}
            if canisters:
                if layout["v2"] is None:
                    bodies.append(canisters[tuple(args.pick_cell)][0])
                else:
                    shelf_canisters = [path for path, _obj in canisters.values()]
                    bodies += shelf_canisters
                    # 약통은 늘 선반 판에 얹혀 있다. threshold 0 이면 그 쌍이 매 스텝 보고되고, 선반이
                    # 삼각 메시라 보고마다 PhysX 가 면 인덱스로 재질을 찾다 경고를 낸다(9/23: 419,292 줄,
                    # rtf 0.34). 자기 무게 위로 문턱을 두면 쉬는 접촉은 빠지고 밀린 접촉은 남는다.
                    thresholds = dict.fromkeys(shelf_canisters, args.canister_contact_threshold_n)
            contact_watch_bodies = list(bodies)
            if bodies:
                # 로봇 자기 링크끼리의 접촉은 뺀다. 팔이 없으면 뺄 것도 없다.
                contact_watch = diag.watch_contacts(stage, bodies, log, lambda: sim_clock["last"],
                                                    every_s=args.contact_log_every_s,
                                                    ignore_inside=(arm["root"] + "/") if arm is not None else None,
                                                    thresholds=thresholds)
            else:
                log("contact_watch off: no bodies to watch (no --robot-usd, --ur5-contact-log or --amr)")
        # 기동 직후 한 줄. 회차가 끝나야 아는 `stop reason=` 줄과 달리 시작에서 바로 읽힌다(작전 9/21,
        # 통합&정비 빈월드 프로필 #415 가 이 줄을 찾는다). 감시가 조용히 꺼진 회차를 여기서 가른다.
        watched = contact_watch_bodies if contact_watch is not None else []
        log(f"observers contact_watch={'on' if contact_watch is not None else 'off'} "
            f"canister_threshold_n={args.canister_contact_threshold_n:g} "
            f"watch_bodies={len(watched)} roots={sorted({b.rsplit('/', 2)[0] for b in watched})} "
            f"ur5={'on' if cell is not None else 'off'} amr={'on' if amr is not None else 'off'} "
            f"m0609={'on' if arm is not None else 'off'} zones_tf={'on' if args.zones_tf else 'off'} "
            f"hand_camera={'off' if args.no_hand_camera else 'on'}")
        def log_surface(when):
            """Review A4 "확인 실험 2": read-only belt body snapshot (attributes, composed world axes)."""
            if conveyor is not None:
                log(f"belt_surface {when} hospital_conveyor running={conveyor.running} "
                    f"terminal_surface_velocity={conveyor.readback()}")
                return
            try:
                snap = diag.surface_snapshot(stage, BELT_PRIM)
            except Exception as exc:  # diagnostics must not end the stage
                log(f"belt_surface {when} unavailable {type(exc).__name__}: {exc}")
                return
            log(f"belt_surface {when} {json.dumps(snap, default=str, separators=(',', ':'))}")

        log_surface("before_play")
        set_belt(0.0)
        with common.step(log, "world_reset"):
            world.reset()
        if conveyor is not None:
            # 리셋이 초기 상태를 되돌려 놓을 수 있다. 아직 스텝 전(=Play 전 창)이라 여기서 다시 쓴다.
            # 어느 창에서 값이 사라지는지 갈리게 세 지점을 찍는다(9/23: before_play −0.5 → after_reset 0).
            conveyor.run()
            log_surface("after_reset_rewrite")
            world.step(render=True)
            log_surface("after_first_step")
        for _ in range(10):
            world.step(render=True)
        chase_follow = None
        traffic_state = {"last": None, "extras": None}
        walker_state = {"last": None}
        encounter_state = {"tracker": encounters.Tracker(), "on": True}

        def real_amr_xys():
            """진짜 AMR (x, y) 목록: amr_1 몸체 + 여벌 합본의 base_link(서 있든 가든). 더미·보행자가 같이 쓴다."""
            if traffic_state["extras"] is None:
                from isaacsim.core.prims import SingleXFormPrim
                from pxr import Usd

                extras = []
                for index in range(2, getattr(args, "amr_count", 1) + 1):
                    root = stage.GetPrimAtPath(f"{AMR_ROOT}{index}")
                    link = next((p for p in Usd.PrimRange(root) if p.GetName() == "base_link"), None) \
                        if root.IsValid() else None
                    if link is not None:
                        extras.append((f"amr_{index}",
                                       SingleXFormPrim(prim_path=str(link.GetPath()), name=f"traffic_real_{index}")))
                traffic_state["extras"] = extras
            real = []
            if amr is not None:
                base = amr.base_world_pose()
                real.append(None if base is None else base[:2])
            for _who, prim in traffic_state["extras"]:
                position, _quat = prim.get_world_pose()
                real.append((float(position[0]), float(position[1])))
            return real

        def fleet_poses_payload():
            """관제 웹용 여벌 AMR·더미 자리. 여벌은 base_link 월드 자세를 그대로 읽는다(밀려도 따라간다)."""
            real_amr_xys()                    # 여벌 프림 목록을 한 번 채운다
            spares = []
            for who, prim in traffic_state["extras"]:
                position, quat = prim.get_world_pose()          # quat 는 (w, x, y, z)
                w, qx, qy, qz = (float(v) for v in quat)
                spares.append((who, float(position[0]), float(position[1]),
                               math.atan2(2.0 * (w * qz + qx * qy), 1.0 - 2.0 * (qy * qy + qz * qz))))
            return bridge.fleet_pose_items(spares, traffic.poses() if traffic is not None else ())

        def traffic_tick(now_s):
            """가짜 AMR 을 한 틱 옮긴다."""
            dt = 0.0 if traffic_state["last"] is None else max(0.0, now_s - traffic_state["last"])
            traffic_state["last"] = now_s
            traffic.update(dt, real_amr_xys())
        log_surface("after_reset")
        if args.view != "none":  # after reset so nothing moves the camera back; the user can orbit freely after
            hospital_viewport = hospital_full(args)
            if hospital_viewport:
                # 병원은 Perspective 하나만 쓴다. 기본은 건물 전체 조망(floor_top)이고, 근접 뷰는 --view 로
                # 짚은 촬영 회차에서만이다(재범 9/23: 뷰포트가 카메라 프림으로 자꾸 바뀌어 지저분하다).
                # 회차 중에 카메라 프림으로 바꾸지 않는다 — 실습37 워크셀 7 mm 카메라도 여기서 쓰지 않는다.
                name = args.view if args.view in views.HOSPITAL_VIEW_NAMES else HOSPITAL_DEFAULT_VIEW
                eye, target = views.hospital_view(name)
                if args.view in views.HOSPITAL_FOLLOW_VIEW_NAMES:
                    # 따라가는 카메라는 시작 자세가 없다. 첫 틱에 차체를 읽어 맞춘다(아래 chase_follow).
                    log(f"viewport follow={args.view} back={views.CHASE_BACK_M:g} up={views.CHASE_UP_M:g} "
                        f"(Perspective 를 매 틱 옮긴다. 카메라 프림은 안 바꾼다)")
            else:
                name = args.view
                eye, target = shifted_view(args, *views.view(args.scene, args.view))
                if args.workcell_layout:
                    camera = args.workcell_data['camera']
                    eye, target = camera['eye'], camera['target']
            try:
                from isaacsim.core.utils.viewports import set_camera_view

                set_camera_view(eye=list(eye), target=list(target), camera_prim_path="/OmniverseKit_Persp")
                log(f"viewport view={name} scene={args.scene} eye={common.format_values(eye)} "
                    f"target={common.format_values(target)} "
                    f"camera=/OmniverseKit_Persp{' (hospital)' if hospital_viewport else ''}")
                try:  # 재범 9/18 half screen: the real image size and apertures decide what the view shows
                    from omni.kit.viewport.utility import get_active_viewport
                    from pxr import UsdGeom

                    viewport = get_active_viewport()
                    cam = UsdGeom.Camera(stage.GetPrimAtPath("/OmniverseKit_Persp"))
                    focal = views.HOSPITAL_VIEW_FOCAL_MM.get(name) if hospital_viewport else None
                    if focal is not None:
                        # 이 뷰만 화각을 넓힌다(m0609_overhead, 재범 9/27). 프림은 그대로 Perspective 다.
                        # Kit 의 Perspective 값은 **세션 레이어**에 있다. 편집 대상(루트)에 쓰면 더 약한 의견이라
                        # 가려진다 — 8eee260 뷰 랩에서 Set 뒤 읽은 focal 이 18.1476 그대로였다(#240 5854639597).
                        from pxr import Usd

                        with Usd.EditContext(stage, stage.GetSessionLayer()):
                            cam.GetFocalLengthAttr().Set(float(focal))
                    if args.workcell_layout and not hospital_viewport:
                        from pxr import Gf
                        cam = UsdGeom.Camera.Define(stage, HOSPITAL_CAMERA_PRIM)
                        cam.CreateFocalLengthAttr(camera['focal_mm'])
                        cam.CreateHorizontalApertureAttr(24.)
                        matrix = Gf.Matrix4d().SetLookAt(Gf.Vec3d(*eye), Gf.Vec3d(*target), Gf.Vec3d(0, 0, 1))
                        UsdGeom.Xformable(cam).MakeMatrixXform().Set(matrix.GetInverse())
                        viewport.camera_path = HOSPITAL_CAMERA_PRIM
                    log(f"viewport camera resolution={getattr(viewport, 'resolution', None)} "
                        f"fill_frame={getattr(viewport, 'fill_frame', None)} "
                        f"focal={cam.GetFocalLengthAttr().Get()} h_aperture={cam.GetHorizontalApertureAttr().Get()} "
                        f"v_aperture={cam.GetVerticalApertureAttr().Get()}")
                except Exception as exc:  # diagnostics only
                    log(f"viewport camera unavailable {type(exc).__name__}: {exc}")
            except Exception as exc:  # a camera pose must not stop the stage
                log(f"viewport view={args.view} failed {type(exc).__name__}: {exc}")
            if args.view in views.HOSPITAL_FOLLOW_VIEW_NAMES and amr is not None:
                chase_state = {"warned": False, "logged": False}

                def chase_follow():
                    """Perspective 를 차체 뒤로 옮긴다. `--view amr_chase` 일 때만 매 틱 불린다.

                    **카메라 프림을 바꾸지 않는다**(재범 9/23). 실패해도 회차를 세우지 않는다 —
                    촬영용이라 그림이 안 따라올 뿐이다. 경고는 한 번만 남긴다(틱마다 찍으면 로그가 묻힌다).
                    """
                    try:
                        base = amr.base_world_pose()
                        if base is None:
                            return
                        from isaacsim.core.utils.viewports import set_camera_view

                        eye, target = views.chase_pose(*base)
                        set_camera_view(eye=list(eye), target=list(target),
                                        camera_prim_path="/OmniverseKit_Persp")
                        if not chase_state["logged"]:
                            chase_state["logged"] = True
                            log(f"viewport follow first eye={common.format_values(eye)} "
                                f"target={common.format_values(target)} base={common.format_values(base)}")
                    except Exception as exc:
                        if not chase_state["warned"]:
                            chase_state["warned"] = True
                            log(f"WARN viewport follow disabled {type(exc).__name__}: {exc}")
        # What PhysX parsed for the belt right after the first play (9/17: a run keeps 0.24 or 0.15 m/s for its whole
        # life, so the difference is fixed at start).
        if conveyor is None:
            diag.query_rigid_body(stage, BELT_PRIM, log, "belt_after_reset")
            belt_prim = stage.GetPrimAtPath(BELT_PRIM)
            log(f"belt_after_reset applied_schemas={list(belt_prim.GetAppliedSchemas())} "
                f"surface_velocity_attr={belt_prim.GetAttribute('physxSurfaceVelocity:surfaceVelocity').Get()} "
                f"surface_velocity_enabled="
                f"{belt_prim.GetAttribute('physxSurfaceVelocity:surfaceVelocityEnabled').Get()}")
        else:
            diag.query_rigid_body(stage, conveyor.terminal_path, log, "hospital_terminal_after_reset")
        if arm is not None:
            from isaacsim.core.utils.types import ArticulationAction

            robot = arm["articulation"]
            with common.step(log, "articulation_ready"):
                for _attempt in range(50):
                    if robot.handles_initialized and robot.get_joint_positions() is not None:
                        break
                    robot.initialize()
                    world.step(render=True)
                else:
                    from pxr import Usd, UsdPhysics

                    roots = [str(p.GetPath()) for p in Usd.PrimRange(stage.GetPseudoRoot())
                             if p.HasAPI(UsdPhysics.ArticulationRootAPI)]
                    raise RuntimeError(f"no joint positions from {arm['root']} after 50 tries; "
                                       f"playing={world.is_playing()}; ArticulationRootAPI prims in stage: {roots}")
            refill.log_dofs(robot)
            names = list(robot.dof_names)
            missing = [n for n in [*arm["rail"], *args.arm_joints, args.gripper_joint] if n not in names]
            if missing:
                raise common.StepError(f"dof_names: joints {missing} are not articulation dofs; have {names}")
            arm["rail_idx"] = np.array([robot.get_dof_index(n) for n in arm["rail"]])
            arm["arm_idx"] = np.array([robot.get_dof_index(n) for n in args.arm_joints])
            arm["grip_idx"] = np.array([robot.get_dof_index(args.gripper_joint)])
            arm["rail_limits"] = ((-args.rail_x_stroke / 2, args.rail_x_stroke / 2), tuple(args.rail_y_limits))

            def command(indices, values):
                trace.mark(f"m0609.apply_action(n={len(values)})")
                robot.apply_action(ArticulationAction(joint_positions=np.array(values, dtype=float),
                                                      joint_indices=indices))

            arm["command"] = command
            props = robot.dof_properties
            for name, index in zip(arm["rail"], arm["rail_idx"], strict=True):
                prop = props[int(index)]
                log(f"rail drive joint={name} stiffness={float(prop['stiffness']):.4g} "
                    f"damping={float(prop['damping']):.4g} max_force={float(prop['maxEffort']):.4g} "
                    f"max_velocity={float(prop['maxVelocity']):.4g} lower={float(prop['lower']):.3f} "
                    f"upper={float(prop['upper']):.3f} requested={tuple(args.rail_drive)}")
            arm["home_positions"] = robot.get_joint_positions().copy()
            log(f"arm ready rail_dofs={list(arm['rail'])} mode={args.mode} "
                f"home={common.format_values(arm['home_positions'])}")
        if amr is not None:
            try:
                with common.step(log, "amr_ready"):
                    amr.attach()
                    amr.reset()
                    if amr.arm_indices:
                        # 합본 팔의 홈 관절값. 받침대의 `ur5 spawn_settled`·`home_positions=` 에 해당하는 줄이다
                        # — 그 구성에서는 안 나오므로 여기서 낸다(비전이 params 에 넣는 값).
                        for _ in range(args.ur5_spawn_settle_steps):
                            world.step(render=False)
                        names, positions, _velocities = amr.read_all()
                        arm_home = dict(zip(names[3:], (round(v, 6) for v in positions[3:]), strict=True))
                        amr.arm_home = list(positions[3:])  # 리셋 뒤 자세 대조(`reset pose`)의 기준
                        log(f"amr arm_home steps={args.ur5_spawn_settle_steps} joints={arm_home} "
                            f"(비전: 이 값을 home_joint_positions 로 쓴다. 정착 뒤 값이다)")
            except Exception as error:  # 베이스가 안 붙어도 나머지 장면은 돈다
                log(f"amr disabled after reset reason={type(error).__name__}: {error}; the stage still runs")
                amr = None
        if cell is not None:
            try:
                with common.step(log, "ur5_ready"):
                    cell.ready(refill.log_dofs)
                    if args.ur5_spawn_ready:
                        # K4·K6 선행(비전·작전 9/21): --mode ros 에서 아무도 팔을 ready 로 보내지 않아 0 자세로
                        # 선다. 팔 노드의 arm/at_home 은 관절값과 home_joint_positions 의 차(0.05 rad)로 정해지고,
                        # 주행은 at_home=true 없이 GoToZone 을 전부 거부한다(계약 5절). 스폰 자세 = ready 자세여야
                        # 둘이 같이 풀린다.
                        solved, written = cell.spawn_at(args.ur5_ready)
                        log(f"ur5 spawn_ready solved={solved} tcp={common.format_values(args.ur5_ready)} "
                            f"written={ {k: round(v, 6) for k, v in written.items()} }")
                        if not solved:
                            log("WARN ur5 spawn_ready IK failed; the arm stays at the USD pose (0 자세)")
                        else:
                            # 비전이 params 에 넣을 값을 고를 수 있게 **세 지점**을 찍는다(비전 9/21):
                            # 쓴 값(IK) · 한 스텝 뒤(직후) · 정착 뒤. 중력 처짐이 있으면 셋이 다르고,
                            # 직후와 정착이 0.05 rad 넘게 벌어지면 arm/at_home 이 false 가 되어
                            # 주행이 GoToZone 을 전부 거부한다.
                            def read_joints():
                                positions = cell.robot.get_joint_positions()
                                return {name: float(positions[cell.robot.get_dof_index(name)]) for name in written}

                            def spread(a, b):
                                return max((abs(a[n] - b[n]) for n in a), default=0.0)

                            world.step(render=False)
                            immediate = read_joints()
                            dt = world.get_physics_dt()
                            for _ in range(args.ur5_spawn_settle_steps):
                                world.step(render=False)
                            settled = read_joints()
                            sag = spread(immediate, settled)
                            log(f"ur5 spawn_immediate joints={ {k: round(v, 6) for k, v in immediate.items()} } "
                                f"vs_written_rad={spread(written, immediate):.6f}")
                            log(f"ur5 spawn_settled steps={args.ur5_spawn_settle_steps} "
                                f"sim_s={args.ur5_spawn_settle_steps * dt:.3f} "
                                f"joints={ {k: round(v, 6) for k, v in settled.items()} } "
                                f"sag_rad={sag:.6f} at_home_tol=0.05 "
                                f"{'WARN sag exceeds the at_home tolerance' if sag > 0.05 else 'ok'}")
                    cell.home_positions = cell.robot.get_joint_positions().copy()
                    log(f"ur5 home_positions={common.format_values(cell.home_positions)} "
                        f"spawn_ready={'on' if args.ur5_spawn_ready else 'off'} "
                        f"(비전: 이 값을 home_joint_positions 로 쓴다)")
            except common.StepError as error:
                log(f"ur5 disabled after reset reason={error}; continuing without the UR5")
                cell = None

        if canisters and layout["v2"] is not None:
            # 선반 충돌체를 볼록체로 바꾸면(준비기 SHELF_APPROXIMATION) hull 이 칸의 빈 공간을 채워 약통이
            # 겹친 채로 시작할 수 있다(최적화 9/23). 그러면 첫 스텝에서 튕겨 나간다. 재서 남긴다 —
            # 판정이 아니라 관측이다. 큰 값이 나오면 근사를 바꿔 다시 잰다.
            with common.step(log, "canister_settle"):
                def canister_xyz():
                    return {cell_id: tuple(float(v) for v in obj.get_world_pose()[0])
                            for cell_id, (_path, obj) in canisters.items()}

                start = canister_xyz()
                dt = world.get_physics_dt()
                for _ in range(max(1, int(round(1.0 / dt)))):
                    world.step(render=False)
                settled = canister_xyz()
                moved = sorted(((math.dist(start[c], settled[c]), c) for c in start), reverse=True)
                log(f"canister_settle n={len(moved)} sim_s={max(1, int(round(1.0 / dt))) * dt:.3f} "
                    f"max_move_m={moved[0][0]:.4f} worst="
                    f"{[(c, round(d, 4)) for d, c in moved[:3]]} "
                    f"{'WARN canisters moved more than 5 mm' if moved[0][0] > 0.005 else 'ok'}")

        if conveyor is not None:
            # 병원 경로: 트랙 여럿의 월드 AABB + 끝 롤러. 끝 판정은 잰 회차와 같은 terminal_status(가장자리 0.03,
            # 높이 0.02). 경사로가 있어 "벨트 위" 는 상자 높이 전체로 본다(z_band span).
            terminal = conveyor.terminal_surface()
            receiver = None
            if args.hospital_receiver_prim:
                receiver_prim = stage.GetPrimAtPath(args.hospital_receiver_prim)
                if not receiver_prim or not receiver_prim.IsValid():
                    raise ValueError(f"receiver prim missing: {args.hospital_receiver_prim}")
                bounds = UsdGeom.BBoxCache(Usd.TimeCode.Default(),
                                          [UsdGeom.Tokens.default_, UsdGeom.Tokens.render])
                box = bounds.ComputeWorldBound(receiver_prim).ComputeAlignedRange()
                receiver = {"min": list(box.GetMin()), "max": list(box.GetMax())}
                log(f"hospital receiver prim={args.hospital_receiver_prim} surface={receiver} settle_s=1.0")
            model = beltlib.RouteBeltModel(route_tracks, terminal, hconv.TERMINAL_DIRECTION, args.pouch_size,
                                           settle_speed=args.settle_speed,
                                           settle_time_s=1.0 if receiver else args.settle_time_s,
                                           at_end_timeout_s=HOSPITAL_AT_END_TIMEOUT_S,
                                           on_belt_height=HOSPITAL_ON_BELT_HEIGHT,
                                           edge_margin=HOSPITAL_TERMINAL_EDGE_MARGIN,
                                           fail_closed=bool(receiver) or args.belt_fail_closed,
                                           z_band="span", receiver=receiver)
            spawn_on_belt = model.on_belt(beltlib.route_point(hconv.SPAWN))
            log(f"hospital belt_model tracks={len(route_tracks)} terminal={terminal} "
                f"direction={hconv.TERMINAL_DIRECTION} spawn={hconv.SPAWN} spawn_on_belt={spawn_on_belt} "
                f"on_belt_height={HOSPITAL_ON_BELT_HEIGHT} at_end_timeout_s={HOSPITAL_AT_END_TIMEOUT_S}")
            if not spawn_on_belt:
                log("WARN hospital spawn is not on any conveyor track box; the first observe would free the belt "
                    "(pouch_left_belt). 트랙 상자와 출발점을 로그에서 대조한다")
        else:
            model = beltlib.BeltModel(args.belt_length, args.belt_width, args.end_zone, args.settle_speed,
                                      args.settle_time_s, fail_closed=args.belt_fail_closed)
        pool_ids = known_order_ids(args)
        injection = resetlib.ResetInjection(args.reset_fail, args.reset_delay_s)
        state = {"epoch": beltlib.FIRST_EPOCH, "spawned": 0, "pouch": None, "pouch_path": None, "pouch_index": None,
                 "at_end_since": None,
                 "carried": [], "ur5": {"seq": None, "slot": 0},
                 "reset_due": None, "reset_epoch": None, "reset_pose_due": None, "demo_orders": None, "demo_count": 0,
                 "pick_notices_ignored_ur5": 0, "obs_mode": obslib.MODE_SIM_SENSOR, "obs_zone": obslib.ZONE_UNKNOWN}
        physics_steps = obslib.StepCounter()  # one counter for every Isaac observation seq (belt now, gripper next)
        stall_log = common.ThrottledLog(20)   # 긴 틱은 몰려 온다. 첫 줄과 20번째마다만 남긴다
        belt_rewrite_log = common.ThrottledLog(600)   # 표면 속도를 다시 쓴 줄은 10 s(60 Hz)에 한 번만 남긴다

        # ---- K4·K5 참값 센서 (--sim-sensors). 스텁이 아니라 센서다: 판정 영역 안에 실제로 있는 것만 낸다.
        sensors_on = args.sim_sensors and ros is not None
        sensor_beds = {bed: sorted(patients)[0] for bed, patients in bed_patients(args).items()}
        sensor_stations = []
        if getattr(args, "zones_file", None) and Path(args.zones_file).is_file():
            from p3sim import hospital_zones as hzones

            sensor_stations = hzones.station_tables(args.zones_file)
        sensor_frame = args.ur5_base_frame or sensorlib_frame_default()
        if sensors_on:
            log(f"sim_sensors on pouches={bridge.POUCHES}@{sensorlib.POUCHES_HZ:g}Hz "
                f"tag_reads={bridge.TAG_READS}@{sensorlib.TAG_READS_HZ:g}Hz "
                f"cabinet={bridge.CABINET}@{sensorlib.CABINET_HZ:g}Hz frame={sensor_frame} "
                f"beds={sensor_beds} amr={'on' if args.amr else 'off (태그를 내지 않는다)'}")

        def belt_end_xy():
            """벨트 끝의 월드 xy. 구역 값과 같은 출처를 쓴다(병원: zones 의 pharmacy.belt_end)."""
            if layout.get("hospital"):
                return tuple(layout["hospital"]["belt_end"][:2])
            return (1.35 + args.belt_length, args.belt_start[1])

        def pouch_speed(obj):
            """봉투의 선속도 크기. 못 읽으면 None(그때는 막지 않는다 — 진단이 센서를 멈추면 안 된다)."""
            try:
                velocity = obj.get_linear_velocity()
                if velocity is None:
                    return None
                return float(sum(float(v) * float(v) for v in velocity)) ** 0.5
            except Exception:
                return None

        tray_drift = {}   # order_id -> 마지막으로 찍은 칸 이탈(2 cm 단위)
        # 트레이 홀더(칸 클립). 합본 AMR 트레이가 있을 때만(amr_base.TrayClip).
        tray_clip = None
        if args.tray_clip and amr is not None and args.amr_combined and amr_slots:
            tray_clip = amrlib.TrayClip(amr, amr_slots, roomlib.TRAY["slot_accept"], sensorlib.POUCH_STILL_SPEED,
                                        log)
            log("tray clip ready (칸에 멈춘 봉투를 붙이고 팔이 잡으면 푼다 — 실물 트레이 홀더 대응)")

        def log_tray_drift(order_id, obj, world, slots, speed):
            """트레이 위 봉투가 칸에서 2 cm 넘게 새로 밀릴 때마다 한 줄 — **움직이는 중에도** 찍는다(진단만).

            `pouch placed … in_slot=` 줄은 봉투가 멈췄을 때만 나와 언제 밀렸는지 못 가른다(RC-1 회차55·56:
            첫 in_slot=False 가 접근점 회전 한가운데 찍혔지만 주행·넘김 중 밀렸을 수도 있다).
            그 시각을 fleet 줄과 맞춘다.
            """
            if not slots:
                return
            holder = cell if cell is not None else amr_suction
            if holder is not None and holder.held is not None and holder.held[0] is obj:
                return
            near = min(slots, key=lambda c: math.dist(world[:2], c[:2]))
            gap = math.dist(world[:2], near[:2])
            if gap > 0.35 or abs(world[2] - near[2]) > 0.05:
                return   # 트레이 위가 아니다(벨트·공중·보관함)
            bucket = int(gap / 0.02)
            if bucket == tray_drift.get(order_id):
                return
            tray_drift[order_id] = bucket
            if bucket == 0:
                return
            log(f"tray drift order_id={order_id} offset_xy={gap:.4f} d=({world[0] - near[0]:+.4f}, "
                f"{world[1] - near[1]:+.4f}) speed={speed} sim_s={sim_now():.2f}")

        def pouch_detections():
            """지금 벨트 끝이나 상판 칸에 **실제로 있는** 봉투만. 들고 있는 것은 어느 쪽도 아니라 빠진다."""
            found = []
            end = belt_end_xy()
            # **빌드 값이 아니라 지금 자리**를 읽는다 — K2b 로 상판이 베이스 위로 가면 둘이 갈린다.
            if cell is not None:
                slots = cell.slot_centres()
            elif amr is not None and amr_slots:
                # 합본 상판: 칸이 베이스와 함께 움직인다. **지금 자세**로 세계 좌표를 만든다 —
                # 빌드 때 굳히면 AMR 이 움직인 뒤 "칸 안인가" 판정이 그만큼 틀린다(조용히).
                slots = amr.slots_in_world(amr_slots)
            else:
                slots = []
            for index, order_id in sorted(pool.in_use.items()):
                obj = pool_objects[index]
                position, quat = obj.get_world_pose()
                world = tuple(float(v) for v in position)
                speed = pouch_speed(obj)
                # 합본은 트레이라 받는 상자가 다르다 — 칸 벽이 없어 **자리 간격**이 경계를 정한다.
                accept = roomlib.TRAY["slot_accept"] if args.amr_combined else ROOM["deck_slot_size"]
                on_deck = bool(slots) and any(sensorlib.in_slot(world, slot, accept) for slot in slots)
                log_tray_drift(order_id, obj, world, slots, speed)
                if not on_deck and speed is not None and speed > sensorlib.POUCH_STILL_SPEED:
                    # **아직 굴러가는 봉투는 내지 않는다.** 센서 영역이 정지 구역보다 넓어 0.667 s 먼저
                    # 잡히는데, 팔이 그 자세로 풀면 봉투가 실제로 서는 자리와 0.10 m 어긋난다(lap5).
                    # **상판 칸에 든 봉투는 이 조건을 보지 않는다.** 봉투가 차체와 같이 움직이므로 세계 속도가
                    # 0 이 아니고, AMR 이 정차·yaw 정렬 중이면 검출이 통째로 막혔다(9/23 bed_a1:
                    # `speed=0.1056 limit=0.02` 뒤 `PickPouch ord-0001: not_detected (검출 0건)`).
                    # 칸 안이라는 것 자체가 놓였다는 증거다 — 벨트 끝에서 구르는 것과 다르다.
                    if moving_warn.hit():
                        log(f"pouch detection held order_id={order_id} speed={speed:.4f} "
                            f"limit={sensorlib.POUCH_STILL_SPEED} (아직 움직인다)")
                    continue
                in_zone = sensorlib.in_belt_end(world, end)
                if not in_zone:
                    in_zone = on_deck
                    # **놓기 오차를 잰다.** 비전의 최악 예산(야코비안 0.060 + 낙하 산포 0.04 = 0.10)이
                    # 받는 상자 ±0.09 를 넘는데, 그건 상한이지 실측이 아니다. 넓히거나 공차를 조이기 전에
                    # **회차에서 한 번 재면** 어느 쪽이 맞는지 갈린다. 빗나가서 버려진 봉투도 여기 찍힌다.
                    # **속도를 못 읽어도 찍는다.** 앞의 `speed is not None` 조건을 그대로 쓰면 속도가
                    # None 인 구성에서 이 줄이 통째로 사라진다 — lap8 에 트레이 줄이 하나도 없었던 것이
                    # 그 모양이었다. 재는 줄은 조용하면 쓸모가 없다. 속도도 같이 찍어 둔다.
                    # **놓인 것만 잰다.** 앞의 조건은 속도와 수평거리만 봐서, 팔이 **들고 지나가는**
                    # 봉투도 "놓았다" 로 찍혔다(lap15: `in_slot=False offset_xy=0.0701 dz=+0.9263`,
                    # 같은 시각에 `wrist_3 ↔ Pouch sep=-0.0068` — 흡착된 채 공중이었다).
                    # 이송 속도가 문턱(0.02) 아래로 내려가는 순간이 있어 속도로는 안 걸러진다.
                    # 그 숫자가 비전의 `arrival_tolerance_rad` 판단에 **놓기 오차로 섞여 들어간다.**
                    holder = cell if cell is not None else amr_suction
                    carried = holder is not None and holder.held is not None and holder.held[0] is obj
                    if slots and not carried and (speed is None or speed <= sensorlib.POUCH_STILL_SPEED):
                        near = min(slots, key=lambda c: math.dist(world[:2], c[:2]))
                        gap = math.dist(world[:2], near[:2])
                        # 높이도 본다 — 떨어지는 중이거나 남의 자리 위를 지나는 것은 놓인 것이 아니다.
                        # `in_slot` 의 z 판정(±0.02)보다 넉넉히 둔다: 살짝 뜬 채 멈춘 것도 재야 한다.
                        rested = abs(world[2] - near[2]) <= 0.05
                        if gap <= 0.30 and rested and place_log.hit():
                            log(f"pouch placed order_id={order_id} in_slot={in_zone} "
                                f"offset_xy={gap:.4f} d=({world[0] - near[0]:+.4f}, "
                                f"{world[1] - near[1]:+.4f}) dz={world[2] - near[2]:+.4f} "
                                f"accept_half={accept[0] / 2.0} speed={speed} "
                                f"(비전 상한 0.10 대 실측. 넘으면 arrival_tolerance_rad 를 조인다)")
                if not in_zone:
                    continue
                if amr is not None and args.amr_combined:
                    # 합본: 밑동이 **움직이고 축이 Rz(pi)** 다. 뺄셈만 하면 받침대 때와 같은 숫자가 나가고
                    # 프레임 이름만 합본 것이라 아무도 못 알아챈다(회차 lap2).
                    in_base = amr.world_to_arm_base(world)
                    if in_base is None:
                        continue
                else:
                    in_base = sensorlib.to_base(world, args.ur5_base)
                found.append(sensorlib.detection(order_id, in_base, sensorlib.wxyz_to_xyzw(quat)))
            return found

        def pouches_payload():
            return sensorlib.pouches_message(sim_now(), state["epoch"], sensor_frame, pouch_detections())

        cabinet_seen = {}   # 보관함 → 지난 관측에서 안에 있던 주문들

        def cabinet_payloads():
            """보관함마다 (참값 메시지). **이벤트가 아니라 자세로 본다** — 계약 145–150줄의 평가 전용 관측이다.

            `stub_sim` 은 팔의 `POUCH_PLACED` **주장**을 받아 지어냈다(#444 F03). 그것과 달리 여기서는
            봉투가 실제로 그 부피 안에 있는지만 본다. **true→false 도 낸다**(미끄러져 나가면, #444 F04).
            """
            out = []
            size = roomlib.WARD["cabinet_size"]
            for zone in sensor_beds:
                pose = (layout["zones"] or {}).get(f"{zone}/cabinet")
                if pose is None:
                    continue
                if layout.get("hospital"):  # 병원: 그 침상 협탁의 bbox 크기(앵커 JSON)
                    size = layout["hospital"]["cabinet_sizes"].get(f"{zone}/cabinet", roomlib.WARD["cabinet_size"])
                inside, where = [], {}
                for index, order_id in sorted(pool.in_use.items()):
                    position, _quat = pool_objects[index].get_world_pose()
                    world = tuple(float(v) for v in position)
                    if sensorlib.in_cabinet(world, pose[:3], size):
                        inside.append(order_id)
                        where[order_id] = world
                updates, entered, cabinet_seen[zone] = sensorlib.cabinet_updates(inside, cabinet_seen.get(zone, set()))
                for order_id in entered:   # 한 보관함 여러 봉투의 자리(칸 겹침) 증거 — 들어온 때 한 번
                    log(f"cabinet present zone={zone} order_id={order_id} xyz={common.format_values(where[order_id])}")
                for order_id, present in updates:
                    out.append(sensorlib.cabinet_message(sim_now(), state["epoch"], f"{zone}/cabinet",
                                                         order_id, present))
            return out

        def tag_payload():
            """AMR 이 **실제로 서 있는** 침상의 인식표. 어디에도 안 서 있거나 풀에 없는 침상이면 None."""
            # **관절값이 아니라 세계 자세다.** `amr.read()` 의 원점은 출발 도크라, 그대로 쓰면
            # 구역 자세(map 기준)와 출발 자리만큼 어긋난다 — lap10 이 그래서 ⑦ 에서 닫혔다.
            positions = amr.base_world_pose()
            if positions is None:
                return None
            # 후보를 **침상으로 좁힌다.** 안 좁히면 가장 가까운 것이 `load`·`dock_1` 로 나와 침상 앞인데도
            # 아무것도 안 내는 경우가 생긴다(둘은 0.60 m 밖에 안 떨어져 있다).
            candidates = {zone: pose for zone, pose in (layout["zones"] or {}).items()
                          if zone in sensor_beds or zone in sensor_stations}
            zone_id = sensorlib.parked_zone(positions, candidates,
                                            sensorlib.TAG_READ_RADIUS, roomlib.ZONE_TOL["tol_yaw"])
            patient = sensor_beds.get(zone_id)
            read = None if zone_id is None else sensorlib.tag_for_zone(zone_id, sensor_stations, sensor_beds)
            if read is None:
                # **안 내는 것은 맞다** — 빈 `tag_id` 를 내면 인증이 거짓 통과한다(비전 #417 4절).
                # 그런데 조용하면 lap8 처럼 ⑦ `AUTH_FAIL` 의 원인이 거리인지 yaw 인지 환자 표인지
                # 갈리지 않는다. 메시지는 그대로 안 내고 **진단 줄만** 찍는다.
                if tag_miss.hit():
                    near = sensorlib.nearest_zone_diagnosis(positions, candidates,
                                                            sensorlib.TAG_READ_RADIUS,
                                                            roomlib.ZONE_TOL["tol_yaw"])
                    log(f"tag_reads none base=({positions[0]:.4f}, {positions[1]:.4f}, {positions[2]:.4f}) "
                        f"zone_id={zone_id} patient={patient} beds={sorted(sensor_beds)} stations={sensor_stations} "
                        f"nearest={near} (안 내는 것이 맞다 — 빈 tag_id 는 인증을 거짓 통과시킨다)")
                return None
            return sensorlib.tag_message(sim_now(), state["epoch"], sensor_frame, zone_id, read[0], kind=read[1])
        pouch_motion = obslib.MotionTracker(args.settle_speed, args.settle_time_s)
        gripper_gate = obslib.GripperCommandGate()  # --gripper-command-seq
        state["gripper_bool_ignored"] = 0

        # 준비 줄. **어떤 구성에서도, 실패한 조각이 있어도 반드시 나온다** — 프로필이 이 줄을 기다린다
        # (통합&정비 9/21). `timeline_event type=PLAY` 는 스폰·센서가 붙기 전에 나오고,
        # `ur5 spawn_settled` 는 IK 가 풀렸을 때만 나온다. 그래서 둘 다 준비 줄로 못 쓴다.
        log(f"stage ready ur5={'on' if cell is not None else 'off'} amr={'on' if amr is not None else 'off'} "
            f"m0609={'on' if arm is not None else 'off'} sim_sensors={'on' if sensors_on else 'off'} "
            f"zones_tf={'on' if args.zones_tf else 'off'} "
            f"spawn_ready={'on' if args.ur5_spawn_ready else 'off'} mode={args.mode}")
        log(f"start mode={args.mode} isaac={clock.isaac_version_string()} belt_start={args.belt_start} "
            f"length={args.belt_length} width={args.belt_width} yaw={args.belt_yaw} speed={args.belt_speed} "
            f"end_zone={args.end_zone} seed={args.seed} spawn_along={args.spawn_along} "
            f"spawn_lateral={args.spawn_lateral} spawn_yaw={args.spawn_yaw} pouch_size={args.pouch_size} "
            f"order_pool={args.order_pool or 'any ord-NNNN'} room={not args.no_room} "
            f"reset_fail={args.reset_fail} reset_delay_s={args.reset_delay_s}")
        refill.write_line(clock.format_start_line(clock.isaac_version_string(),
                                                  clock.environment_summary(os.environ), world.get_physics_dt(),
                                                  world.get_rendering_dt(), args.rate))

        def sim_now():
            value = clock.read_graph_sim_time()
            sim_clock["last"] = value
            return value

        def emit(name, detail=""):
            text = bridge.encode(bridge.EVENTS, stamp=bridge.stamp(sim_now()), name=name,
                                 request_id=model.request_id, order_id=model.order_id,
                                 robot_id=beltlib.ROBOT_ID, epoch=state["epoch"], detail=detail)
            log(f"event {text}")
            if ros is not None:
                ros.publish(bridge.EVENTS, text)

        def park(index):
            trace.mark(f"pouch{index}.teleport_park")
            obj = pool_objects[index]
            obj.set_world_pose(position=np.array(parking[index]), orientation=np.array([1.0, 0.0, 0.0, 0.0]))
            obj.set_linear_velocity(np.zeros(3))
            obj.set_angular_velocity(np.zeros(3))

        def remove_pouch(reason):
            """Teleport the active pouch back to its parking spot. Never deletes the prim (see PouchPool).

            **붙잡고 있는 봉투를 여기로 보내면 안 된다.** 흡착이 매 스텝 TCP 로 다시 끌어오므로 화면은
            멀쩡한데 `pool.in_use` 에서 빠져 **봉투 센서가 영원히 못 본다**(lap12 ⑧: 검출 1268 건 전부
            빈 배열). 막는 것은 `observe_belt` 의 holder 분기이고, 여기서는 **뚫렸을 때 소리를 낸다** —
            조용히 사라지는 것이 이 버그를 한 회차 통째로 쓰게 만든 이유다.
            """
            index = state.get("pouch_index")
            holder = cell if cell is not None else amr_suction
            if (index is not None and holder is not None and holder.held is not None
                    and holder.held[0] is pool_objects[index]):
                log(f"WARN pouch_parked SKIPPED reason={reason} pool_slot={index} "
                    "흡착이 들고 있는 봉투다 — 주차하면 풀에서 빠져 센서가 못 본다(lap12 ⑧)")
                return
            if index is not None:
                park(index)
                pool.release(index)
                log(f"pouch_parked path={state['pouch_path']} reason={reason}")
            state["pouch"], state["pouch_path"], state["pouch_index"], state["at_end_since"] = None, None, None, None
            if reason in obslib.STUB_RELEASES:  # freed without a physical pick (contract 11.1 b) until next dispense
                state["obs_mode"] = obslib.MODE_STUB

        def spawn_pouch(order_id):
            index = state["spawned"]
            if conveyor is not None and args.pouch_at_end:
                # S3·S4 단독(재범 9/23): A1 끝 롤러 위에 바로 놓는다. belt_end 는 출구 가장자리·롤러 윗면이다
                # (zones.hospital.yaml). 봉투 반 길이 + 여유만큼 안쪽에 놓고, 돌고 있는 롤러가 가장자리로 민다
                # (탐침 02 가 그렇게 섰다). 봉투 긴 변을 나가는 방향에 맞춘다. 자리는 임시값이다.
                position, world_yaw = pouch_at_end_pose(layout["hospital"]["belt_end"], args.pouch_size,
                                                        args.spawn_drop)
                along = lateral = yaw = 0.0
            elif conveyor is not None:
                # 병원: 잰 출발점(봉투 중심) + 작은 흔들기(추정값, hospital_conveyor.SPAWN_JITTER_*).
                # 난수는 pouch.spawn_rng 와 같은 (seed, epoch, index) 규칙이다.
                position, world_yaw = hconv.spawn_pose(args.seed, state["epoch"], index)
                along = position[0] - hconv.SPAWN[0]
                lateral = position[1] - hconv.SPAWN[1]
                yaw = world_yaw
            else:
                rng = pouch.spawn_rng(args.seed, state["epoch"], index)
                along, lateral, yaw = pouch.sample_spawn(rng, args.spawn_along, args.spawn_lateral, args.spawn_yaw)
                up = args.pouch_size[2] / 2.0 + args.spawn_drop
                position = pouch.belt_to_world(args.belt_start, args.belt_yaw, along, lateral, up)
                world_yaw = args.belt_yaw + yaw
            slot = pool.acquire(order_id)  # dispense() checked pool.free first
            state["speed_checked"] = False
            state["belt_speed_check"] = None
            if pool.labels[slot] not in (None, order_id):
                log(f"qr_mismatch order_id={order_id} pouch_label={pool.labels[slot]} pool_slot={slot}")
            obj = pool_objects[slot]
            trace.mark(f"pouch{slot}.teleport_spawn")
            path = f"{POUCH_ROOT}/Pouch_{slot:02d}"
            # Order id lives in this log and in state, not in USD customData: no USD edits on physics prims mid-run.
            obj.set_world_pose(position=np.array(position),
                               orientation=np.array([math.cos(world_yaw / 2), 0.0, 0.0, math.sin(world_yaw / 2)]))
            obj.set_linear_velocity(np.zeros(3))
            obj.set_angular_velocity(np.zeros(3))
            state["spawned"] += 1
            state["pouch"], state["pouch_path"], state["pouch_index"] = obj, path, slot
            log(f"spawn index={index} pool_slot={slot} order_id={order_id} path={path} "
                f"xyz={common.format_values(position)} "
                f"yaw={world_yaw:.4f} along={along:.4f} lateral={lateral:.4f} rel_yaw={yaw:.4f} "
                f"seed={args.seed} epoch={state['epoch']}")

        def apply_suction(close):
            """UR5 suction on the ROS path: close on the belt pouch or a pouch already on the deck, nearest the TCP
            (VA-1); a close with nothing in reach is a logged miss."""
            if close:
                candidates = [pool_objects[index] for index in state["carried"]]
                if state["pouch"] is not None and state["pouch"] not in candidates:
                    candidates.append(state["pouch"])
                cell.suck_nearest(candidates)
            else:
                cell.suck(False, None)

        def dispense(request_id, order_id):
            if model.is_resend(request_id, order_id) and state["pouch"] is not None:
                log(f"dispense request_id={request_id} order_id={order_id} accepted=True message= resend=True")
                return True, ""  # same answer; no spawn, no belt command, no second DISPENSED (contract 11.2)
            ready = state["reset_due"] is None
            message = model.decide_dispense(order_id, ready, is_known(order_id, pool_ids), bool(pool.free))
            accepted = message == ""
            log(f"dispense request_id={request_id} order_id={order_id} accepted={accepted} message={message}"
                + (f" pool={args.pouch_pool} in_use={sorted(pool.in_use)}"
                   if message == beltlib.POOL_EXHAUSTED else ""))
            if accepted:
                state["obs_mode"] = obslib.MODE_SIM_SENSOR
                pouch_motion.reset()
                model.accept(request_id, order_id, sim_now())
                if conveyor is not None and conveyor.terminal_held:
                    conveyor.run()                      # 앞 봉투 때 잡은 끝 롤러를 놓는다
                    log("hospital_conveyor terminal released (dispense)")
                spawn_pouch(order_id)
                set_belt(args.belt_speed)
                emit(beltlib.DISPENSED)
            return accepted, message

        def observe_belt():
            if not model.occupied:
                pouch_motion.reset()
                state["obs_zone"] = obslib.ZONE_UNKNOWN
                return
            obj = state["pouch"]
            frame, speed = None, 0.0
            if obj is not None:
                pose = obj.get_world_pose()
                position = tuple(map(float, pose[0]))
                velocity = obj.get_linear_velocity()
                speed = float(np.linalg.norm(velocity)) if velocity is not None else 0.0
                if velocity is None and args.belt_fail_closed:
                    speed = None  # not a settle sample (contract 11.1); the default above counts it as stopped (R1)
                if conveyor is not None:
                    # 병원 경로 벨트: belt_frame 이 없다(트랙 여럿). 봉투 월드 자세를 그대로 준다.
                    frame = beltlib.route_point(position, tuple(map(float, pose[1])))
                    if not args.hospital_receiver_prim and not conveyor.terminal_held:
                        near = beltlib.terminal_status(position, tuple(map(float, pose[1])), args.pouch_size,
                                                       model.terminal, model.direction,
                                                       HOSPITAL_TERMINAL_HOLD_MARGIN, model.height_tolerance)
                        if near["reached"] and conveyor.hold_terminal():
                            log(f"hospital_conveyor terminal held order_id={model.order_id} frame={frame} "
                                f"edge_gap_m={near.get('edge_gap_m')} margin={HOSPITAL_TERMINAL_HOLD_MARGIN}")
                else:
                    top = (args.belt_start[0], args.belt_start[1], args.belt_start[2])
                    frame = beltlib.belt_frame(position, top, args.belt_yaw)
                    frame = (frame[0], frame[1], frame[2] - args.pouch_size[2] / 2.0)
                if (model.speed_sampling and model.running and velocity is not None
                        and not state.get("speed_checked")
                        and beltlib.speed_sample_due(frame[0], args.belt_length)):
                    state["speed_checked"] = True
                    along = beltlib.speed_along(tuple(map(float, velocity)), args.belt_yaw)
                    ratio, mismatch = beltlib.speed_mismatch(along, args.belt_speed)
                    state["belt_speed_check"] = (ratio, mismatch)
                    belt_prim = stage.GetPrimAtPath(BELT_PRIM)
                    surface = belt_prim.GetAttribute("physxSurfaceVelocity:surfaceVelocity")
                    scale = belt_prim.GetAttribute("xformOp:scale")
                    log(f"belt speed_measured={along:.4f} requested={args.belt_speed} ratio={ratio:.3f} "
                        f"mismatch={mismatch} surface_velocity_attr={surface.Get() if surface else None} "
                        f"graph_velocity={velocity_attr.Get()} body={args.belt_body} "
                        f"body_scale={scale.Get() if scale else None} frame_x={frame[0]:.3f} "
                        f"order_id={model.order_id}")
                    log_surface("at_speed_sample")
                    if mismatch:
                        log(beltlib.speed_mismatch_error(along, args.belt_speed, ratio))
            state["obs_zone"] = obslib.pouch_zone(model, frame)
            # **붙잡고 있는 쪽은 받침대 셀일 수도 합본 흡착일 수도 있다.** 여기가 `cell` 만 보고 있어서
            # 합본에서는 아래 분기가 통째로 안 돌았고, 팔이 든 봉투가 벨트를 벗어나는 순간
            # `pouch_left_belt` -> `remove_pouch` 로 **주차장으로 보내지고 풀에서 빠졌다.**
            # 흡착이 매 스텝 TCP 로 다시 끌어와서 화면상으로는 멀쩡했고, 트레이에 놓이기까지 했다 —
            # 다만 `pool.in_use` 에 없으니 **봉투 센서가 영원히 못 본다.** lap12 ⑧ 이 그것이다
            # (`/amr_1/sim/pouches` 1268 건 전부 빈 배열, `pouch placed` 줄도 0).
            holder = cell if cell is not None else amr_suction
            if obj is None or (holder is not None and holder.holding() and holder.held[0] is obj):
                pouch_motion.reset()  # a held pouch follows the TCP by teleport (velocity zeroed): motion unknown
            else:
                pouch_motion.update(float(np.linalg.norm(velocity)) if velocity is not None else None, sim_now())
            if holder is not None and holder.held is not None and holder.held[0] is obj:
                # Held is not picked: the belt stays occupied and state["pouch"] stays set until the held
                # pouch is outside the belt volume (contract 11.1 a; geometric check of the virtual attach).
                order_id = model.order_id
                if not model.observe_held(frame):
                    return
                state["carried"].append(state["pouch_index"])
                log(f"pouch picked_by={'ur5' if cell is not None else 'amr'} order_id={order_id} "
                    f"pool_slot={state['pouch_index']} off_belt frame={common.format_values(frame)} "
                    f"(풀에 남는다 — 빼면 트레이에 놓인 뒤로 센서가 못 본다)")
                state.update(pouch=None, pouch_path=None, pouch_index=None, at_end_since=None)
                return
            was_running = model.running
            events, notes = model.observe(frame, speed, sim_now())
            if was_running and not model.running and not args.hospital_receiver_prim:
                set_belt(0.0)
            for note in notes:
                speed_text = "none" if speed is None else f"{speed:.4f}"
                log(f"belt note={note} order_id={model.order_id or '-'} frame={frame} speed={speed_text}")
                if note == "pouch_lost":  # --belt-fail-closed: belt stays occupied, pouch stays where it is until reset
                    set_belt(0.0)
                if note == "pouch_left_belt":
                    set_belt(0.0)
                    remove_pouch("left_belt")
            for name in events:
                if name == beltlib.POUCH_AT_END:
                    state["at_end_time"] = sim_now()
                    if conveyor is not None and frame is not None:
                        # I1 판정 줄: 봉투가 선 자리와 끝 판정 값. 잰 회차(#240)는 (-8.295, 5.036), 34.58 sim s 였다.
                        status = model.end_status(frame)
                        end = belt_end_xy()
                        log(f"hospital pouch_at_end order_id={model.order_id} "
                            f"xyz={common.format_values(frame[:3])} edge_gap_m={status['edge_gap_m']:.4f} "
                            f"bottom_gap_m={status['bottom_gap_m']:.4f} "
                            f"belt_end_dist_m={math.dist(frame[:2], end):.4f} "
                            f"in_sensor_zone={sensorlib.in_belt_end(frame[:3], end)} "
                            f"sim_s_since_dispense={sim_now() - model.dispensed_at:.2f} "
                            f"measured_ref=(-8.295,5.036)@34.58s")
                    check = state.get("belt_speed_check")
                    emit(name, beltlib.at_end_detail(*check) if check else "")
                else:
                    emit(name)

        def do_reset(epoch):
            try:
                return do_reset_steps(epoch)
            except Exception as exc:  # answer ok=false instead of ending the stage
                log(f"step=reset FAILED {type(exc).__name__}: {exc}")
                state["epoch"] = epoch
                return False, f"reset_error: {type(exc).__name__}"

        def do_reset_steps(epoch):
            note = resetlib.epoch_note(state["epoch"], epoch)
            if note:
                log(f"reset note={note}")
            log(f"reset begin epoch={epoch} steps={list(resetlib.STEPS)}")
            set_belt(0.0)
            # **떼는 것이 주차보다 먼저다.** 붙잡은 채로 주차하면 흡착이 매 스텝 다시 끌어와
            # 주차가 무효가 되고, `remove_pouch` 의 안전장치가 주차 자체를 건너뛴다. 그러면 다음
            # 바퀴가 봉투를 든 채로 시작한다 — 리셋이 리셋이 아니게 된다.
            if cell is not None:  # UR5: suction off, back to its start joints
                cell.suck(False, None)
                state["ur5"] = {"seq": None, "slot": 0}
                if getattr(cell, "home_positions", None) is not None:
                    trace.mark("ur5.set_joint_positions")
                    cell.robot.set_joint_positions(cell.home_positions)
            if amr_suction is not None:
                amr_suction.suck(False, None, reason="reset", now=sim_now())
            remove_pouch("reset")
            if tray_clip is not None:
                tray_clip.release_all("reset")
            state["carried"] = []
            if amr is not None:  # K2: 3축을 출발 자세로. 속도 드라이브라 위치를 직접 쓴다
                trace.mark("amr.reset")
                amr.reset()
            for index in range(args.pouch_pool):  # teleport, never delete (PouchPool)
                park(index)
            pool.release_all()
            model.reset()
            if arm is not None and arm.get("home_positions") is not None:
                # Contract 6 step 2: gripper open, M0609 home; on this stage the rail is part of the M0609 and goes to
                # its zero. set_joint_positions writes positions and drive targets together (no prim edits).
                trace.mark("m0609.set_joint_positions")
                arm["articulation"].set_joint_positions(arm["home_positions"])
                if arm.get("ros_refill"):
                    ros_refill_clear()
                if arm.get("demo"):
                    demo = arm["demo"]
                    if demo["attach"] is not None:
                        demo["attach"]["local"] = None
                    demo.update(seq=None, closed=False, rail_hold=None, cycle_letter="a", respawn_check=None,
                                  arm_cmd=None)
            if canisters:  # canisters moved by refills go back to their cells
                trace.mark(f"canisters.teleport_home(n={len(canisters)})")
                for cell_key, (_path, obj) in canisters.items():
                    obj.set_world_pose(position=np.array(canister_home(cell_key)),
                                       orientation=np.array([1.0, 0.0, 0.0, 0.0]))
                    obj.set_linear_velocity(np.zeros(3))
                    obj.set_angular_velocity(np.zeros(3))
                    if canister_faces is not None:
                        canister_faces.follow(cell_key, canister_home(cell_key), (1.0, 0.0, 0.0, 0.0))
            log(f"reset scope belt=stopped pouches=parked ur5={'home' if cell is not None else '-'} "
                f"m0609_rail={'home+zero' if arm is not None else '-'} canisters={len(canisters or {})} "
                f"amr={'start' if amr is not None else '-'}")
            state["epoch"] = epoch
            state["spawned"] = 0
            cabinet_seen.clear()   # 새 run: 지난 run 주문의 false 를 새 epoch 에 내지 않는다
            state["obs_mode"] = obslib.MODE_SIM_SENSOR
            gripper_gate.reset()  # command_seq starts again at 1 after RESET_DONE
            ok, message = injection.outcome()
            state["reset_pose_due"] = (sim_now() + resetlib.POSE_CHECK_DELAY_S, epoch)
            log(f"reset done epoch={epoch} ok={ok} message={message}")
            log_surface(f"after_sim_reset epoch={epoch}")
            return ok, message

        def log_reset_pose():
            """리셋 1 s 뒤 도크 자세 오차와 팔 관절 오차 한 줄(#696 제안 4). 판정하지 않고 적기만 한다."""
            _due, epoch = state["reset_pose_due"]
            state["reset_pose_due"] = None
            errors = {}
            base = None
            if amr is not None:
                base, _velocities = amr.read()
                if base is not None:
                    base = (base[0], base[1], amrlib.wrap_angle(base[2] - amr.start[2]))
                if getattr(amr, "arm_indices", None):
                    _names, positions, _velocities = amr.read_all()
                    errors["amr_arm"] = resetlib.max_joint_error(getattr(amr, "arm_home", None), positions[3:])
            if cell is not None and getattr(cell, "home_positions", None) is not None:
                errors["ur5"] = resetlib.max_joint_error(cell.home_positions, cell.robot.get_joint_positions())
            if arm is not None and arm.get("home_positions") is not None:
                errors["m0609"] = resetlib.max_joint_error(arm["home_positions"],
                                                           arm["articulation"].get_joint_positions())
            log(resetlib.pose_line(epoch, base, errors))

        def handle_ros():
            for text in ros.take(bridge.DISPENSE_REQUEST):
                message, errors = bridge.decode(bridge.DISPENSE_REQUEST, text)
                if errors:
                    log(f"dispense_request dropped errors={errors} data={text!r}")
                    continue
                accepted, reason = dispense(message["request_id"], message["order_id"])
                ros.publish(bridge.DISPENSE_RESPONSE, bridge.encode(
                    bridge.DISPENSE_RESPONSE, request_id=message["request_id"], order_id=message["order_id"],
                    accepted=accepted, message=reason))
            for text in ros.take(bridge.PICK_NOTICE):
                message, errors = bridge.decode(bridge.PICK_NOTICE, text)
                if errors:
                    log(f"pick_notice dropped errors={errors} data={text!r}")
                    continue
                if args.ur5:  # the UR5 picks; a notice is not a pick. Counted, never applied (CPS plan test 6)
                    state["pick_notices_ignored_ur5"] += 1
                    log(f"ros pick_notice ignored order_id={message['order_id']} epoch={message['epoch']} "
                        f"reason=ur5_picks count={state['pick_notices_ignored_ur5']}")
                    continue
                applies, why = bridge.pick_notice_applies(message, state["epoch"], model.order_id,
                                                          model.at_end and state["pouch"] is not None)
                if not applies:
                    log(f"ros pick_notice ignored order_id={message['order_id']} epoch={message['epoch']} reason={why}")
                    continue
                at_end_time = state.get("at_end_time")
                delay = sim_now() - at_end_time if at_end_time is not None else float("nan")
                log(f"ros pick_notice order_id={message['order_id']} delay_s={delay:.3f} sim_time={sim_now():.3f}")
                remove_pouch("ros_pick_notice")
                model.reset()
            for text in ros.take(bridge.RESET_REQUEST):
                message, errors = bridge.decode(bridge.RESET_REQUEST, text)
                if errors:
                    log(f"reset_request dropped errors={errors} data={text!r}")
                    continue
                ok, reason = do_reset(message["epoch"])
                state["reset_due"] = time.monotonic() + injection.delay_s
                state["reset_epoch"], state["reset_result"] = message["epoch"], (ok, reason)
            if state["reset_due"] is not None and time.monotonic() >= state["reset_due"]:
                ok, reason = state["reset_result"]
                ros.publish(bridge.RESET_RESPONSE, bridge.encode(bridge.RESET_RESPONSE, epoch=state["reset_epoch"],
                                                                 ok=ok, message=reason))
                state["reset_due"] = None

        def setup_refill_demo(arm, layout, canisters):
            if not (args.urdf and args.robot_description):
                log("refill_demo off: --urdf and --robot-description are needed for IK; the rail stays at zero")
                return None
            from isaacsim.core.prims import SingleXFormPrim
            from isaacsim.robot_motion.motion_generation import ArticulationKinematicsSolver, LulaKinematicsSolver
            from pxr import Usd

            with common.step(log, "refill_demo_ik"):
                robot_root = stage.GetPrimAtPath(arm["robot_prim"])
                links = {p.GetName(): str(p.GetPath()) for p in Usd.PrimRange(robot_root)}
                for needed in (args.grip_link, "base_link"):
                    if needed not in links:
                        raise RuntimeError(f"link {needed!r} not under {arm['robot_prim']}")
                lula = LulaKinematicsSolver(robot_description_path=str(Path(args.robot_description).expanduser()),
                                            urdf_path=str(Path(args.urdf).expanduser()))
                solver = ArticulationKinematicsSolver(arm["articulation"], lula, args.grip_link)
            pick_path, pick_obj = canisters[tuple(args.pick_cell)]
            cell = layout["cells"][tuple(args.pick_cell)]
            home_xyz = (cell[0], cell[1], cell[2] + args.room_canister_size[2] / 2.0)
            dt = world.get_rendering_dt()
            demo = {
                "lula": lula, "solver": solver, "grip": SingleXFormPrim(prim_path=links[args.grip_link], name="grip"),
                "base": SingleXFormPrim(prim_path=links["base_link"], name="arm_base"), "canister": pick_obj,
                "canister_home": home_xyz, "attach": None if args.physics_grasp else {"local": None},
                "seq": None, "plan": None, "cycle_letter": "a", "step": 0, "steps": 0, "start": None,
                "closed": False, "pause_updates": int(round(args.phase_pause_s / dt)),
                "settle_updates": max(1, int(round(args.grasp_settle_s / dt))), "cycle_started": None,
                "timeout_updates": max(1, int(round(args.phase_timeout_s / dt))), "rail_hold": None,
                "respawn_check": None,
            }
            log(f"refill_demo on pick_cell={args.pick_cell} canister={pick_path} "
                f"home={common.format_values(home_xyz)} "
                f"grasp={'physics' if args.physics_grasp else 'attach(follow)'} "
                f"loop={args.refill_loop or 'forever'} "
                f"reach_offset={args.reach_offset} tcp_max_speed={args.tcp_max_speed} tcp_accel={args.tcp_accel} "
                f"rail_speed={args.rail_speed} rail_accel={args.rail_accel} joint_max_speed={args.joint_max_speed}")
            return demo

        def refill_plan(letter):
            plan = roomlib.plan_rail_refill(
                arm["demo"]["canister_home"], args.room_canister_size[2], layout["inlets"][letter], args.inlet_size,
                ROOM["inlet_wall"], args.rail_origin, args.reach_offset, arm["rail_limits"][0], arm["rail_limits"][1],
                args.clearance, args.grip_depth, shelf_front_y=args.shelf_origin[1], pull_margin=args.pull_margin,
                inlet_offset=args.inlet_standoff, carry_z=args.carry_z, retreat_z=args.retreat_z,
                retreat_back=args.retreat_back)
            steps = {phase: target for phase, _kind, target, _gripper in plan}
            log(f"refill plan inlet={letter} shelf_rail={common.format_values(steps['rail_to_shelf'])} "
                f"inlet_rail={common.format_values(steps['rail_to_inlet'])} "
                f"above_canister={common.format_values(steps['above_canister'])} "
                f"above_inlet={common.format_values(steps['above_inlet'])} "
                f"insert={common.format_values(steps['insert'])} retreat={common.format_values(steps['retreat'])} "
                f"rail_origin={common.format_values(args.rail_origin)} shelf_standoff={args.reach_offset} "
                f"inlet_standoff={args.inlet_standoff} rail_y_limits={common.format_values(args.rail_y_limits)} "
                f"rail_drive={args.rail_drive}")
            return plan

        def demo_poses():
            demo = arm["demo"]
            link = demo["grip"].get_world_pose()
            link_pose = (tuple(map(float, link[0])), tuple(map(float, link[1])))
            can = demo["canister"].get_world_pose()
            return link_pose, (tuple(map(float, can[0])), tuple(map(float, can[1])))

        def demo_gripper(closed):
            demo = arm["demo"]
            arm["command"](arm["grip_idx"], [args.gripper_close if closed else args.gripper_open])
            if closed != demo["closed"]:
                log(f"refill gripper {'close' if closed else 'open'}")
                demo["closed"] = closed
            attach = demo["attach"]
            if attach is None:
                return
            link_pose, can_pose = demo_poses()
            tcp = refill.tcp_world(link_pose[0], link_pose[1], args.tcp_offset)
            if closed and attach["local"] is None and refill.holding_state(True, tcp, can_pose[0], args.hold_distance):
                attach["local"] = refill.relative_pose(link_pose[0], link_pose[1], can_pose[0], can_pose[1])
                log(f"refill attach follow local_xyz={common.format_values(attach['local'][0])}")
            elif not closed and attach["local"] is not None:
                attach["local"] = None
                log("refill release follow")

        def demo_follow():
            """Attach without USD edits: teleport the held canister to the grip link pose every update.

            9/17 master02: creating or deleting prims while simulating invalidated the physics tensor view, so this
            stage does not add a FixedJoint at grasp time (0.5단계 m0609_refill_stage still does and ran fine)."""
            attach = arm["demo"]["attach"]
            if attach is None or attach["local"] is None:
                return
            link = arm["demo"]["grip"].get_world_pose()
            link_xyz, link_quat = tuple(map(float, link[0])), tuple(map(float, link[1]))
            local_xyz, local_quat = attach["local"]
            position = refill.tcp_world(link_xyz, link_quat, local_xyz)
            orientation = refill.quat_multiply(link_quat, local_quat)
            trace.mark("canister.teleport_follow")
            arm["demo"]["canister"].set_world_pose(position=np.array(position), orientation=np.array(orientation))
            arm["demo"]["canister"].set_linear_velocity(np.zeros(3))
            arm["demo"]["canister"].set_angular_velocity(np.zeros(3))

        def demo_respawn():
            demo = arm["demo"]
            if demo["attach"] is not None:
                demo["attach"]["local"] = None
            trace.mark("canister.teleport_respawn")
            demo["canister"].set_world_pose(position=np.array(demo["canister_home"]),
                                            orientation=np.array([1.0, 0.0, 0.0, 0.0]))
            demo["canister"].set_linear_velocity(np.zeros(3))
            demo["canister"].set_angular_velocity(np.zeros(3))
            demo["respawn_check"] = 30
            log(f"refill respawn canister_home={common.format_values(demo['canister_home'])}")

        def ros_refill_update(closed):
            """--mode ros without --ros-refill-selfdemo: the arm node drives the rail + M0609 by topics. The stage
            attaches a canister when the gripper closes near it (holding), follows it, reports where it was released
            and puts it back on its shelf cell after --respawn-delay-s. No IK here.
            v1: the one pick-cell canister, released into inlet a/b. v2: the nearest of all shelf canisters, released
            into the round bin or the module hole; the inventory topic follows every pick and respawn."""
            if arm is None or not canisters:
                return
            ros_refill = arm.get("ros_refill")
            if ros_refill is None:
                from isaacsim.core.prims import SingleXFormPrim
                from pxr import Usd

                links = {p.GetName(): str(p.GetPath()) for p in Usd.PrimRange(stage.GetPrimAtPath(arm["robot_prim"]))}
                if args.grip_link not in links:
                    raise RuntimeError(f"link {args.grip_link!r} not under {arm['robot_prim']}")
                if layout["v2"] is None:
                    candidates = {tuple(args.pick_cell): canisters[tuple(args.pick_cell)]}
                else:
                    candidates = dict(canisters)
                ros_refill = {"grip": SingleXFormPrim(prim_path=links[args.grip_link], name="ros_grip"),
                              "candidates": candidates, "held": None, "local": None, "closed": False,
                              "pending": {}, "last_release": None, "faces_synced": None,
                              # 조제기에 넣어 치운 칸(--workcell-consume). 이 세대에는 다시 안 잡는다. 리셋이 비운다.
                              "consumed": set()}
                arm["ros_refill"] = ros_refill
                log(f"refill_ros on scene={args.scene} canisters={len(candidates)} "
                    f"first={next(iter(candidates.values()))[0]} grip_link={args.grip_link} "
                    f"tcp_offset={args.tcp_offset} hold_distance={args.hold_distance} "
                    f"respawn_delay_s={args.respawn_delay_s} consume={args.workcell_consume}")
                publish_inventory()
            grip = ros_refill["grip"].get_world_pose()
            link_xyz, link_quat = tuple(map(float, grip[0])), tuple(map(float, grip[1]))
            if closed is not None and closed != ros_refill["closed"]:
                ros_refill["closed"] = closed
                tcp = refill.tcp_world(link_xyz, link_quat, args.tcp_offset)
                if closed:
                    poses = {key: ros_refill["candidates"][key][1].get_world_pose()
                             for key in ros_refill["candidates"]
                             if key not in ros_refill["pending"] and key not in ros_refill["consumed"]}
                    nearest = min(poses, key=lambda k: math.dist(tcp, tuple(map(float, poses[k][0]))), default=None)
                    can_xyz = None if nearest is None else tuple(map(float, poses[nearest][0]))
                    distance = math.inf if can_xyz is None else math.dist(tcp, can_xyz)
                    if can_xyz is not None and refill.holding_state(True, tcp, can_xyz, args.hold_distance):
                        can_quat = tuple(map(float, poses[nearest][1]))
                        ros_refill["held"] = nearest
                        ros_refill["local"] = refill.relative_pose(link_xyz, link_quat, can_xyz, can_quat)
                        log(f"refill_ros grasp attached distance={distance:.4f} "
                            f"canister={common.format_values(can_xyz)} cell={cell_label(nearest)} "
                            f"sim_time={sim_now():.3f}")
                        publish_inventory()
                    else:
                        log(f"refill_ros grasp miss distance={distance:.4f} limit={args.hold_distance} "
                            f"tcp={common.format_values(tcp)} nearest={cell_label(nearest)} "
                            f"canister={'-' if can_xyz is None else common.format_values(can_xyz)}")
                elif ros_refill["local"] is not None:
                    key = ros_refill["held"]
                    obj = ros_refill["candidates"][key][1]
                    can_xyz = tuple(map(float, obj.get_world_pose()[0]))
                    ros_refill["local"], ros_refill["held"] = None, None
                    ros_refill["pending"][key] = sim_now() + args.respawn_delay_s
                    if layout["v2"] is None:
                        inlet = roomlib.inlet_containing(can_xyz, layout["inlets"], args.inlet_size,
                                                         ROOM["inlet_wall"])
                        log(f"refill_ros released inlet={inlet or 'none'} canister={common.format_values(can_xyz)} "
                            f"sim_time={sim_now():.3f} respawn_in_s={args.respawn_delay_s}")
                    else:
                        target = layout_v2.judge_target(can_xyz, layout["v2"]["targets"]["round"],
                                                        layout["v2"]["targets"]["module"])
                        ros_refill["last_release"] = {"cell": key, "canister_id": canister_id(key),
                                                      "type": layout["v2"]["cells"][key]["type"], "target": target,
                                                      "sim_time": round(sim_now(), 3)}
                        log(f"refill_ros released cell={key} type={layout['v2']['cells'][key]['type']} "
                            f"target={target} canister={common.format_values(can_xyz)} sim_time={sim_now():.3f} "
                            f"respawn_in_s={args.respawn_delay_s}")
                        publish_inventory()
            if ros_refill["local"] is not None:
                ros_refill_follow()
            if canister_faces is not None:
                # 움직이는 약통의 QR 면: 잡힌 것과 놓여서 되돌아가기를 기다리는 것(떨어지는 중일 수 있다).
                # 선 약통도 CANISTER_FACE_SYNC_S 마다 실제 자세로 맞춘다 — 칸 기준 자리(canister_home)와
                # 물리로 가라앉은 자리가 다르면 스티커가 몸통에서 어긋난다(재범 9/23 화면).
                keys = [ros_refill["held"], *ros_refill["pending"]]
                synced = ros_refill.get("faces_synced")
                if synced is None or sim_now() - synced >= CANISTER_FACE_SYNC_S:
                    ros_refill["faces_synced"] = sim_now()
                    keys = list(ros_refill["candidates"])
                for key in keys:
                    if key is not None:
                        xyz, quat = ros_refill["candidates"][key][1].get_world_pose()
                        canister_faces.follow(key, tuple(map(float, xyz)), tuple(map(float, quat)))
            for key, due in list(ros_refill["pending"].items()):
                if sim_now() < due:
                    continue
                del ros_refill["pending"][key]
                obj = ros_refill["candidates"][key][1]
                if args.workcell_consume:
                    # 조제기에 들어간 약통이다 — 선반으로 안 돌아온다.
                    # 보이지 않는 곳(바닥 아래)으로 치우고 그 칸은 빈 칸이다.
                    home = canister_home(key)
                    obj.set_world_pose(position=np.array((home[0], home[1], CONSUMED_PARK_Z)),
                                       orientation=np.array([1.0, 0.0, 0.0, 0.0]))
                    obj.set_linear_velocity(np.zeros(3))
                    obj.set_angular_velocity(np.zeros(3))
                    if canister_faces is not None:
                        canister_faces.follow(key, (home[0], home[1], CONSUMED_PARK_Z), (1.0, 0.0, 0.0, 0.0))
                    ros_refill["consumed"].add(key)
                    log(f"refill_ros consumed cell={cell_label(key)} left_on_shelf="
                        f"{len(ros_refill['candidates']) - len(ros_refill['consumed'])}")
                    publish_inventory()
                    continue
                trace.mark("canister.teleport_respawn")
                obj.set_world_pose(position=np.array(canister_home(key)), orientation=np.array([1.0, 0.0, 0.0, 0.0]))
                obj.set_linear_velocity(np.zeros(3))
                obj.set_angular_velocity(np.zeros(3))
                if canister_faces is not None:
                    canister_faces.follow(key, canister_home(key), (1.0, 0.0, 0.0, 0.0))
                log(f"refill_ros respawn cell={cell_label(key)} "
                    f"canister_home={common.format_values(canister_home(key))}")
                publish_inventory()

        def cell_label(key):
            if key is None:
                return "-"
            return key if isinstance(key, str) else f"r{key[0]}c{key[1]}"

        def canister_id(key):
            return "can-" + cell_label(key).replace("/", "-")

        def publish_inventory():
            """v2 only: /m0609/shelf/inventory (JSON, transient local) with every cell's canister, the targets, the
            obstacle boxes and the last release."""
            if layout["v2"] is None or arm_ros is None:
                return
            ros_refill = arm.get("ros_refill") or {}
            absent = set(ros_refill.get("pending", {})) | set(ros_refill.get("consumed", ()))
            if ros_refill.get("held") is not None:
                absent.add(ros_refill["held"])
            present = {cell_id: (stock_present is None or stock_present.get(cell_id, True))
                       and cell_id not in absent for cell_id in layout["v2"]["cells"]}
            message = layout_v2.inventory(layout["v2"]["cells"], present, layout["v2"]["targets"],
                                          layout["v2"]["obstacles"], ros_refill.get("last_release"),
                                          bridge.stamp(sim_clock["last"]),
                                          rail=v2_rail_info(args))
            if args.workcell_layout:
                from p3sim import workcell_layout
                message['source'] = workcell_layout.layout_source(args.workcell_data)
            arm_ros.publish_inventory(json.dumps(message, separators=(",", ":")))
            log(f"refill_ros inventory present={sum(present.values())}/{len(present)} "
                f"last_release={ros_refill.get('last_release')}")

        def ros_refill_clear():
            """Reset / STOP recovery: drop the attachment; canisters go home through the reset itself."""
            ros_refill = arm.get("ros_refill") if arm is not None else None
            if ros_refill:
                ros_refill.update(local=None, held=None, closed=False, pending={}, consumed=set())
                publish_inventory()

        def ros_refill_follow():
            ros_refill = arm.get("ros_refill") if arm is not None else None
            if not ros_refill or ros_refill["local"] is None:
                return
            grip = ros_refill["grip"].get_world_pose()
            link_xyz, link_quat = tuple(map(float, grip[0])), tuple(map(float, grip[1]))
            local_xyz, local_quat = ros_refill["local"]
            obj = ros_refill["candidates"][ros_refill["held"]][1]
            trace.mark("canister.teleport_follow")
            obj.set_world_pose(position=np.array(refill.tcp_world(link_xyz, link_quat, local_xyz)),
                               orientation=np.array(refill.quat_multiply(link_quat, local_quat)))
            obj.set_linear_velocity(np.zeros(3))
            obj.set_angular_velocity(np.zeros(3))

        rail_overlap = {"pairs": diag.ContactPairLog(every_s=2.0), "parts": None, "count": 0}
        # 레일이 명령을 따라가는 정도. 드라이브를 부드럽게 한 값이 얼마나 밀리는지 이 줄로 잰다(작전 9/23).
        rail_follow = {"target": None, "worst": 0.0, "log": common.ThrottledLog(120)}

        def check_rail_overlap():
            """Robot vs its own rail parts (재범 실습7-a: "M0609 가 베이스가 되는 레일을 관통"). Logged, not blocked."""
            if arm is None or args.rail_overlap_every <= 0 or "rail_idx" not in arm:
                return
            rail_overlap["count"] += 1
            if rail_overlap["count"] % args.rail_overlap_every:
                return
            if rail_overlap["parts"] is None:
                rail_overlap["parts"] = layout_v2.rail_parts(args.rail_origin, args.rail_x_stroke, args.rail_y_limits,
                                                             ROOM["rail_base_height"], args.carriage_height,
                                                             lift=args.scene == "v2",
                                                             lift_travel=float(args.rail_z_limits[1]))
            positions = arm["articulation"].get_joint_positions()
            if positions is None:
                return
            rail_now = dict(zip(("x", "y", "z"), map(float, positions[arm["rail_idx"]]), strict=False))
            try:
                hits = diag.robot_rail_overlaps(rail_overlap["parts"], rail_now, arm["robot_prim"] + "/")
            except Exception as exc:  # diagnostics must not end the stage
                log(f"rail_overlap check failed {type(exc).__name__}: {exc}")
                args.rail_overlap_every = 0
                return
            for part, body in hits:
                if rail_overlap["pairs"].add(part, body, sim_clock["last"]):
                    log(f"rail_overlap part={part} robot={body} rail={common.format_values(list(rail_now.values()))} "
                        f"count={rail_overlap['pairs'].count(part, body)} sim_time={sim_clock['last']:.3f}")

        def check_rail_follow():
            """레일이 명령을 얼마나 따라가는지. 드라이브를 부드럽게 하면(VERIFIED_RAIL_DRIVE) 여기가 벌어진다.

            9/23 까지 **재지 않았다** — 레일 드라이브를 바꾸면서 무엇이 나빠지는지 볼 값이 없었다.
            같은 관절의 명령과 실제 위치 차를 재고, 가장 큰 것만 주기로 남긴다.
            """
            target = rail_follow["target"]
            if not target or arm is None or "rail_idx" not in arm:
                return
            positions = arm["articulation"].get_joint_positions()
            if positions is None:
                return
            gaps = []
            for name, want in target.items():
                try:
                    index = arm["articulation"].get_dof_index(name)
                except Exception:  # noqa: BLE001 - 진단이 스테이지를 끝내면 안 된다
                    continue
                gaps.append((abs(float(positions[index]) - float(want)), name, float(positions[index]), float(want)))
            if not gaps:
                return
            worst = max(gaps)
            rail_follow["worst"] = max(rail_follow["worst"], worst[0])
            if worst[0] > args.rail_follow_warn_m and rail_follow["log"].hit():
                log(f"rail_follow gap_m={worst[0]:.4f} joint={worst[1]} now={worst[2]:.4f} want={worst[3]:.4f} "
                    f"worst_m={rail_follow['worst']:.4f} drive={list(args.rail_drive)} "
                    f"sim_time={sim_clock['last']:.3f}")

        def a1_poll():
            """Raw Kit state before every loop-condition evaluation (always True: never ends the loop)."""
            try:
                a1_probe.poll(simulation_app)
            except Exception as exc:  # diagnostics must not end the stage
                log(f"a1_probe poll failed {type(exc).__name__}: {exc}")
            return True

        def something_held():
            demo = arm.get("demo") if arm is not None else None
            if demo and demo.get("attach") and demo["attach"].get("local") is not None:
                return True
            return ros_refill_holding() or (cell is not None and cell.held is not None)

        ticks = {"n": 0}

        def step_world():
            """One update. While something is held by teleport, step physics only, move the held object to the
            gripper's new pose, then render: otherwise the rendered frame shows the canister where gravity and the
            finger contacts left it during the step, one update behind the gripper (재범 실습1 P1: the lifted
            canister swung back and forth — our reading, not confirmed).

            `--render-every N` 이면 N 틱마다만 그린다. 물리(`world.step`)와 잡은 것 따라 옮기기는 **매 틱**
            한다 — 그리기만 건너뛴다. 안 그리는 틱에는 Kit 갱신도 OmniGraph 도 돌지 않는다."""
            ticks["n"] += 1
            draw = ticks["n"] % args.render_every == 0
            if not something_held():
                world.step(render=draw)
                return
            world.step(render=False, update_fabric=True)
            if arm is not None and arm.get("demo"):
                demo_follow()
            ros_refill_follow()
            if cell is not None:
                cell.follow()
            if draw:
                trace.mark("world.render(after_follow)")
                world.render()

        def ros_refill_holding():
            ros_refill = arm.get("ros_refill") if arm is not None else None
            return bool(ros_refill and ros_refill["local"] is not None)

        def arm_tour_update():
            if arm is None:
                return
            if "demo" not in arm:
                if layout["v2"] is not None:
                    arm["demo"] = None
                    log("refill_demo off: scene v2 is driven by the arm node (--preset demo-ros-refill-v2)")
                    return
                arm["demo"] = setup_refill_demo(arm, layout, canisters) if canisters else None
                if not canisters:
                    log("refill_demo off: --no-room has no shelf canisters")
            if not arm["demo"]:
                return
            demo = arm["demo"]
            demo_follow()
            if demo["respawn_check"] is not None:
                demo["respawn_check"] -= 1
                if demo["respawn_check"] <= 0:
                    _link, can_pose = demo_poses()
                    offset = math.dist(can_pose[0], demo["canister_home"])
                    upright = abs(can_pose[1][0])  # |w| of the unit quaternion; 1 = no tilt or yaw
                    log(f"refill respawn_settled canister={common.format_values(can_pose[0])} "
                        f"quat={common.format_values(can_pose[1])} home={common.format_values(demo['canister_home'])} "
                        f"offset_m={offset:.4f} upright={upright:.4f}")
                    demo["respawn_check"] = None
                    if (offset > 0.01 or upright < 0.995) and demo.get("respawn_retries", 0) < 3:
                        # 9/17 4c07d8f: a respawned canister lay on its side (z 0.83, y +0.09) and was not lifted.
                        demo["respawn_retries"] = demo.get("respawn_retries", 0) + 1
                        log(f"refill respawn_retry attempt={demo['respawn_retries']}")
                        demo_respawn()
                    else:
                        demo["respawn_retries"] = 0
            robot = arm["articulation"]
            if robot.get_joint_positions() is None:
                if not_ready_ik.hit():
                    log(f"refill paused: articulation has no joint positions (count={not_ready_ik.count}); "
                        "waiting for the physics view")
                return
            if demo["seq"] is None:
                demo["plan"] = refill_plan(demo["cycle_letter"])
                demo["seq"] = refill.DemoSequencer(len(demo["plan"]), args.refill_loop, demo["pause_updates"])
                demo["cycle_started"] = sim_now()
            seq = demo["seq"]
            if seq.mode == "finished":
                return
            if seq.mode == "home":  # plan already ends at rail home; respawn and alternate inlets
                demo_respawn()
                demo["cycle_letter"] = "b" if demo["cycle_letter"] == "a" else "a"
                demo["plan"] = refill_plan(demo["cycle_letter"])
                seq.home_done()
                demo["cycle_started"] = sim_now()
                return
            if seq.mode == "pause":
                event = seq.tick_pause()
                if event:
                    report_cycle(event)
                return
            phase, kind, goal, gripper = demo["plan"][seq.index]
            if seq.mode == "start_phase":
                seq.mode = "run"
                demo["step"] = 0
                link_pose, _can = demo_poses()
                rail_start = tuple(map(float, robot.get_joint_positions()[arm["rail_idx"]]))
                tcp_start = refill.tcp_world(link_pose[0], link_pose[1], args.tcp_offset)
                rail_goal = goal if kind == "rail" else demo["rail_hold"]
                arm_now = robot.get_joint_positions()[arm["arm_idx"]]
                dt = world.get_rendering_dt()
                if kind == "rail":
                    demo["start"] = rail_start
                    demo["profile"] = (math.dist(goal, rail_start), args.rail_speed, args.rail_accel)
                    demo["steps"] = max(1, math.ceil(motion.trapezoid_duration(*demo["profile"]) / dt))
                elif kind == "tcp":
                    demo["start"] = tcp_start
                    demo["profile"] = (math.dist(goal, tcp_start), args.tcp_max_speed, args.tcp_accel)
                    demo["steps"] = max(1, math.ceil(motion.trapezoid_duration(*demo["profile"]) / dt))
                else:
                    demo["steps"] = demo["settle_updates"]
                log(f"refill cycle={seq.cycle} inlet={demo['cycle_letter']} phase={phase} kind={kind} "
                    f"target={common.format_values(goal)} steps={demo['steps']} "
                    f"rail={common.format_values(rail_start)} "
                    f"rail_target={'-' if rail_goal is None else common.format_values(rail_goal)} "
                    f"tcp={common.format_values(tcp_start)} "
                    f"tcp_target={common.format_values(goal) if kind != 'rail' else '-'} "
                    f"applied_rail_target={applied_rail_target()} arm={common.format_values(arm_now)}")
                demo_gripper(gripper == "close")
            if kind != "rail" and demo["rail_hold"] is not None:
                arm["command"](arm["rail_idx"], list(demo["rail_hold"]))  # keep the carriage parked during arm motion
            if demo["step"] >= demo["steps"]:
                link_pose, can_pose = demo_poses()
                rail_now = tuple(map(float, robot.get_joint_positions()[arm["rail_idx"]]))
                tcp_now = refill.tcp_world(link_pose[0], link_pose[1], args.tcp_offset)
                tolerance = roomlib.phase_tolerance(phase, kind, args.rail_tolerance, args.tcp_tolerance,
                                                    args.via_tolerance)
                if kind == "rail":
                    error = max(abs(rail_now[0] - goal[0]), abs(rail_now[1] - goal[1]))
                    reached = error <= tolerance
                elif kind == "tcp":
                    error = math.dist(tcp_now, goal)
                    reached = error <= tolerance
                else:
                    error, reached = math.dist(tcp_now, goal), True
                overtime = demo["step"] - demo["steps"]
                # Allowance grows with the planned motion (4c07d8f: rail_home from x 1.05 ran out of a flat 5 s).
                if not reached and overtime < demo["timeout_updates"] + demo["steps"]:
                    if kind == "rail":
                        arm["command"](arm["rail_idx"], list(goal))
                    else:
                        hold_ik(goal)
                    demo["step"] += 1
                    return
                status = "reached" if reached else "TIMEOUT"
                log(f"refill {status} cycle={seq.cycle} phase={phase} error_m={error:.4f} "
                    f"extra_s={overtime * world.get_rendering_dt():.2f} rail={common.format_values(rail_now)} "
                    f"canister={common.format_values(can_pose[0])} applied_rail_target={applied_rail_target()} "
                    f"arm={common.format_values(robot.get_joint_positions()[arm['arm_idx']])}")
                event = seq.phase_done()
                if event:
                    report_cycle(event)
                return
            alpha = (motion.trapezoid_fraction((demo["step"] + 1) * world.get_rendering_dt(), *demo["profile"])
                     if kind != "hold" else 1.0)
            if kind == "rail":
                arm["command"](arm["rail_idx"], [demo["start"][0] + alpha * (goal[0] - demo["start"][0]),
                                                 demo["start"][1] + alpha * (goal[1] - demo["start"][1])])
                demo["rail_hold"] = goal
            else:
                target = goal if kind == "hold" else refill.lerp(demo["start"], goal, alpha)
                hold_ik(target, phase)
            demo_gripper(gripper == "close")
            demo["step"] += 1

        def applied_rail_target():
            """Rail position targets the articulation controller last applied, as the physics sees them."""
            try:
                positions = arm["articulation"].get_applied_action().joint_positions
                values = [positions[int(i)] for i in arm["rail_idx"]]
            except (AttributeError, IndexError, TypeError) as error:
                return f"unavailable({type(error).__name__})"
            if any(v is None for v in values):
                return str(values)
            return common.format_values([float(v) for v in values])

        def hold_ik(target, phase="settle"):
            """IK for the six arm joints only (Lula cspace joint_1..joint_6); the rail joints are not in the solve."""
            demo = arm["demo"]
            base = demo["base"].get_world_pose()
            demo["lula"].set_robot_base_pose(robot_position=base[0], robot_orientation=base[1])
            offset = refill.quat_rotate(args.tool_quat, args.tcp_offset)
            flange = np.array([t - o for t, o in zip(target, offset, strict=True)])
            action, solved = demo["solver"].compute_inverse_kinematics(
                target_position=flange, target_orientation=np.array(args.tool_quat))
            if solved:
                # Joint speed cap (80% of USD maxVelocity) relative to the last commanded arm targets.
                indices = [int(i) for i in action.joint_indices]
                order = [list(map(int, arm["arm_idx"])).index(i) for i in indices]
                previous = demo.get("arm_cmd")
                if previous is None:
                    current = arm["articulation"].get_joint_positions()
                    previous = {i: float(current[i]) for i in indices}
                dt = world.get_rendering_dt()
                limited = motion.clamp_step([previous[i] for i in indices], [float(v) for v in action.joint_positions],
                                            [args.joint_max_speed[k] * dt for k in order])
                demo["arm_cmd"] = dict(zip(indices, limited, strict=True))
                action.joint_positions = np.array(limited)
                trace.mark("m0609.apply_action(ik)")
                arm["articulation"].apply_action(action)
            elif not_ready_ik.hit():
                log(f"refill ik_failed phase={phase} target={common.format_values(target)} count={not_ready_ik.count}")

        def report_cycle(event):
            demo = arm["demo"]
            _link, can_pose = demo_poses()
            letter = demo["cycle_letter"]
            inlet = layout["inlets"][letter]
            wall = ROOM["inlet_wall"]
            cavity = refill.aabb((inlet[0], inlet[1], inlet[2] + wall / 2.0),
                                 (args.inlet_size[0] - 2 * wall, args.inlet_size[1] - 2 * wall,
                                  args.inlet_size[2] - wall))
            inside = refill.point_in_aabb(can_pose[0], cavity)
            log(f"refill cycle={demo['seq'].cycle} inlet={letter} canister_in_inlet={inside} "
                f"canister={common.format_values(can_pose[0])} grasp={'physics' if args.physics_grasp else 'attach'} "
                f"sim_s={sim_now() - demo['cycle_started']:.3f} next={event}")

        not_ready_ik = common.ThrottledLog(60)
        arm_name_warn = common.ThrottledLog(60)
        moving_warn = common.ThrottledLog(60)   # 굴러가는 봉투를 막은 것은 정상이라 가끔만 찍는다
        place_log = common.ThrottledLog(5)      # 놓기 오차. 판정이 아니라 **재는** 줄이라 자주 찍는다
        tag_miss = common.ThrottledLog(60)      # 인식표가 안 나가는 이유. 안 내는 것 자체는 정상이다

        def ur5_update():
            if cell is None:
                return
            if cell.held is not None:
                trace.mark("pouch.teleport_follow_ur5")
            cell.follow()
            if args.mode != "selfdemo":
                return
            u = state["ur5"]
            if u["seq"] is None:
                if not (model.at_end and state["pouch"] is not None):
                    return
                pick = tuple(map(float, state["pouch"].get_world_pose()[0]))
                u["pouch"] = state["pouch"]
                u["plan"] = roomlib.plan_suction_pick_place(pick, args.pouch_size[2], cell.slots[u["slot"]],
                                                            ROOM["deck_slot_size"], ROOM["deck_wall"], args.clearance,
                                                            args.ur5_ready)
                u["seq"] = refill.DemoSequencer(len(u["plan"]), 1, int(round(args.phase_pause_s /
                                                                             world.get_rendering_dt())))
                log(f"ur5 pick order_id={model.order_id} pick={common.format_values(pick)} "
                    f"deck_slot={u['slot'] + 1}")
            seq = u["seq"]
            if seq.mode == "pause":
                event = seq.tick_pause()
                if event == "finished":
                    finish_ur5_pick()
                return
            if seq.mode == "finished":
                finish_ur5_pick()
                return
            phase, kind, goal, suction = u["plan"][seq.index]
            if seq.mode == "start_phase":
                seq.mode = "run"
                u["step"] = 0
                u["start"] = cell.tcp()[0]
                u["steps"] = (refill.interpolation_steps(u["start"], goal, args.ur5_tcp_speed) if kind == "tcp"
                              else max(1, int(round(args.grasp_settle_s / world.get_rendering_dt()))))
                log(f"ur5 phase={phase} kind={kind} target={common.format_values(goal)} suction={suction} "
                    f"steps={u['steps']} tcp={common.format_values(u['start'])} "
                    f"base={common.format_values(args.ur5_base)}")
                cell.suck(suction == "on", u["pouch"])
            if u["step"] >= u["steps"]:
                error = math.dist(cell.tcp()[0], goal)
                overtime = u["step"] - u["steps"]
                if kind == "tcp" and error > args.tcp_tolerance and overtime < int(round(
                        args.phase_timeout_s / world.get_rendering_dt())):
                    trace.mark("ur5.apply_action(ik)")
                    cell.ik_to(goal)
                    u["step"] += 1
                    return
                status = "reached" if kind != "tcp" or error <= args.tcp_tolerance else "TIMEOUT"
                log(f"ur5 {status} phase={phase} error_m={error:.4f} holding={cell.holding()}")
                if status == "TIMEOUT":  # did the joints not follow the solution, or was the solution itself off?
                    log(f"ur5 ik_check phase={phase} {cell.ik_report()}")
                event = seq.phase_done()
                if event == "finished":
                    finish_ur5_pick()
                return
            target = goal if kind == "hold" else refill.lerp(u["start"], goal, (u["step"] + 1) / u["steps"])
            trace.mark("ur5.apply_action(ik)")
            if not cell.ik_to(target) and not_ready_ik.hit():
                log(f"ur5 ik_failed phase={phase} target={common.format_values(target)} count={not_ready_ik.count}")
            u["step"] += 1

        def finish_ur5_pick():
            u = state["ur5"]
            slot = cell.slots[u["slot"]]
            pos = tuple(map(float, u["pouch"].get_world_pose()[0]))
            inside = refill.point_in_aabb(pos, refill.aabb(slot, ROOM["deck_slot_size"]))
            log(f"ur5 placed deck_slot={u['slot'] + 1} in_slot={inside} pouch={common.format_values(pos)} "
                f"sim_time={sim_now():.3f}")
            u["seq"] = None
            u["slot"] += 1
            if u["slot"] >= args.deck_count:
                log(f"ur5 deck full slots={args.deck_count}; parking carried pouches {state['carried']}")
                for index in state["carried"]:
                    park(index)
                    pool.release(index)
                state["carried"] = []
                u["slot"] = 0

        def selfdemo_update():
            ur5_update()
            arm_tour_update()
            if state["demo_orders"] is None:
                ids = sorted(pool_ids) if pool_ids else [f"ord-{n:04d}" for n in range(1, 5)]
                state["demo_orders"] = itertools.cycle(ids)
            if not model.occupied:
                if args.loop and state["demo_count"] >= args.loop:
                    return
                state["demo_count"] += 1
                dispense(f"r000-{state['demo_count']:04d}", next(state["demo_orders"]))
                return
            if model.at_end and cell is not None:
                return  # the UR5 takes it (ur5_update)
            if model.at_end:
                if state["at_end_since"] is None:
                    state["at_end_since"] = sim_now()
                elif sim_now() - state["at_end_since"] >= args.pick_delay_s:
                    log(f"cycle={state['demo_count']} order_id={model.order_id} picked_stand_in=True "
                        f"sim_time={sim_now():.3f}")
                    remove_pouch("selfdemo_pick")
                    model.reset()

        period = 1.0 / args.rate
        started = time.monotonic()
        sim_started = sim_now()
        next_tick = started
        next_belt = started
        next_fleet = started
        fleet_state = {"on": ros is not None and fleet_poses_wanted(args)}
        running = {"last": None, "next": started}
        next_arm_states = started
        next_ur5_states = started
        next_amr_states = started
        next_pouches = started
        next_tags = started
        next_cabinet = started
        next_gripper = started
        updates = 0
        reason = "app_stopped"
        headless = args.headless or args.livestream
        while a1_poll() and not stop_event.is_set() and common.keep_running(simulation_app.is_running(),
                                                              simulation_app.is_exiting(), headless):
            now = time.monotonic()
            if args.duration and now - started >= args.duration:
                reason = "duration"
                break
            if timeline_flags["stopped"]:
                # A timeline STOP drops every physics handle (5.1.0 SimulationManager._on_stop) and PhysX puts bodies
                # back to their authored USD poses. 9/17 master02 4c07d8f died ~2 s after one (no timeline log then).
                timeline_flags["stopped"] = False
                stops = state.get("stops", 0) + 1
                state["stops"] = stops
                log(f"physics_view lost by timeline STOP count={stops}; playing again and restarting cycles")
                world.play()
                recovered = False
                waited = 0
                for _ in range(120):
                    world.step(render=True)
                    waited += 1
                    ready = arm is None or arm["articulation"].get_joint_positions() is not None
                    ready = ready and (cell is None or cell.robot.get_joint_positions() is not None)
                    # 합본 AMR(베이스 3축 + UR5)도 같은 핸들을 잃는다. 9/24 회차37(aca8840): 이 줄이 없어 M0609 만
                    # 살아나고 /amr_1/joint_states·odom 이 STOP 의 sim 시각에서 멈췄다("Physics Simulation View is
                    # not created yet in order to use apply_action" 118,579줄). 리셋(do_reset_steps)도 핸들을 다시
                    # 만들지 않는다 — amr.reset() 이 같은 경고로 끝난다.
                    ready = ready and (amr is None or amr.articulation.get_joint_positions() is not None)
                    if ready:
                        recovered = True
                        break
                    if arm is not None:
                        arm["articulation"].initialize()
                    if cell is not None:
                        cell.robot.initialize()
                    if amr is not None:
                        amr.articulation.initialize()
                if not recovered:
                    log("physics_view not recovered after 120 updates; exiting with code 3")
                    exit_code = 3
                    reason = "physics_view_lost"
                    break
                set_belt(0.0)
                remove_pouch("timeline_stop")
                if tray_clip is not None:
                    tray_clip.release_all("timeline_stop")
                for index in range(args.pouch_pool):
                    park(index)
                pool.release_all()
                model.reset()
                if arm is not None and arm.get("ros_refill"):
                    ros_refill_clear()
                if arm is not None and arm.get("demo"):
                    arm["demo"].update(seq=None, closed=False, rail_hold=None, respawn_check=None, arm_cmd=None)
                    if arm["demo"]["attach"] is not None:
                        arm["demo"]["attach"]["local"] = None
                if cell is not None:
                    cell.suck(False, None)
                    state["carried"] = []
                    state["ur5"] = {"seq": None, "slot": 0}
                if amr_suction is not None:
                    amr_suction.suck(False, None, reason="timeline_stop", now=sim_now())
                    state["carried"] = []
                if amr is not None:
                    # STOP 은 몸체를 USD 에 작성된 자세로 돌린다. 3축과 남은 속도 명령을 출발 자세·0 으로 맞춘다.
                    amr.reset()
                log(f"physics_view recovered updates={waited} timeline_subscriptions={len(timeline_subscriptions)}")
                continue
            demo_now = arm.get("demo") if arm is not None else None
            refill_label = "-"
            if demo_now and demo_now.get("seq") is not None and demo_now.get("plan"):
                seq_now = demo_now["seq"]
                if seq_now.index < len(demo_now["plan"]):
                    refill_label = f"{demo_now['plan'][seq_now.index][0]}/{seq_now.mode}"
            trace.next_tick(f"sim={sim_clock['last']:.2f} refill={refill_label} belt_occupied={model.occupied}")
            if conveyor is not None:
                # Play 뒤 첫 스텝에서 잰 표면 속도가 0 으로 돌아갔다(9/23 cc55ca7). 무엇이 쓰는지 모르니
                # 매 틱 맞춰 둔다. 다시 쓴 수를 세어 앞 세 번과 주기마다 남긴다 — 계속 다시 쓰는데도
                # 봉투가 안 가면 USD 쓰기가 PhysX 에 안 닿는다는 뜻이다(그때는 다른 길을 본다).
                rewritten = conveyor.reassert()
                if rewritten:
                    state["belt_rewrites"] = state.get("belt_rewrites", 0) + 1
                    if state["belt_rewrites"] <= 3 or belt_rewrite_log.hit():
                        log(f"hospital_conveyor reassert bodies={rewritten} "
                            f"times={state['belt_rewrites']} terminal={conveyor.readback()} "
                            f"sim_s={sim_now():.2f}")
            if qr_faces:
                # QR 면은 봉투를 따라간다(Cube gprim 아래에 넣지 않는다). 주차된 봉투는 안 움직이므로
                # **쓰는 중인 봉투 + 방금 빠진 봉투**만, 그 중에서도 자세가 바뀐 것만 쓴다.
                # 최적화 9/23: 이 루프가 60 s py-spy 표본의 16 %(485/2950)였다. set_world_pose 가 USD 를
                # 쓸 때마다 Property 창 `_on_usd_changed` 도 같이 돈다. 쓰기를 한 블록으로 묶어 알림도 한 번이다.
                # 방금 빠진 봉투를 한 틱 더 보는 것은 주차 자리로 텔레포트한 자세를 면이 따라가야 해서다 —
                # 안 그러면 면이 옛 자리에 남는다.
                live = {index for index in pool.in_use if index < len(qr_faces)}
                moving = []
                for index in sorted(live | qr_following):
                    position, orientation = pool_objects[index].get_world_pose()
                    last = qr_written.get(index)
                    if last is not None and _same_pose(last, (position, orientation)):
                        continue
                    moving.append((index, position, orientation))
                trace.mark(f"qr_faces.set_world_pose(n={len(moving)}/{len(live | qr_following)})")
                if moving:
                    from pxr import Sdf

                    with Sdf.ChangeBlock():
                        for index, position, orientation in moving:
                            qr_faces[index].set_world_pose(position=position, orientation=orientation)
                    for index, position, orientation in moving:
                        qr_written[index] = (position, orientation)
                qr_following = live
            if ros is not None:
                ros.spin_once()
                handle_ros()
                if args.ros_pick_stand_in_s > 0 and model.at_end and state["pouch"] is not None:
                    if state["at_end_since"] is None:
                        state["at_end_since"] = sim_now()
                    elif sim_now() - state["at_end_since"] >= args.ros_pick_stand_in_s:
                        log(f"ros pick_stand_in order_id={model.order_id} after_s={args.ros_pick_stand_in_s} "
                            f"sim_time={sim_now():.3f}")
                        remove_pouch("ros_pick_stand_in")
                        model.reset()
                if ur5_ros is not None and cell is not None:
                    cell.follow()
                    ur5_ros.spin_once()
                    targets, closed = ur5_ros.take()
                    if targets:
                        indices = np.array([cell.robot.get_dof_index(name) for name in targets])
                        cell.robot.apply_action(cell._action(joint_positions=np.array(list(targets.values())),
                                                             joint_indices=indices))
                    if args.gripper_command_seq:  # only command_seq applies; the Bool is ignored from the start
                        if closed is not None:
                            state["gripper_bool_ignored"] += 1
                        closed = None
                        for text in ros.take(bridge.GRIPPER_COMMAND_SEQ):
                            command, errors = bridge.decode(bridge.GRIPPER_COMMAND_SEQ, text)
                            if errors:
                                log(f"gripper command_seq dropped errors={errors} data={text!r}")
                                continue
                            applies, why = gripper_gate.accept(command, state["epoch"])
                            if not applies:
                                log(f"gripper command_seq ignored seq={command['command_seq']} reason={why}")
                                continue
                            log(f"gripper command_seq applied seq={command['command_seq']} close={command['close']}")
                            if command["close"] != cell.holding():
                                apply_suction(command["close"])
                    if closed is not None and closed != cell.holding():
                        apply_suction(closed)
                if arm is not None and args.ros_refill_selfdemo:
                    arm_tour_update()
                elif arm_ros is not None and arm is not None:
                    arm_ros.spin_once()
                    targets, closed = arm_ros.take()
                    if targets:
                        indices = np.array([arm["articulation"].get_dof_index(name) for name in targets])
                        arm["command"](indices, list(targets.values()))
                    rail_targets = arm_ros.take_rail()
                    if rail_targets:
                        indices = np.array([arm["articulation"].get_dof_index(name) for name in rail_targets])
                        arm["command"](indices, list(rail_targets.values()))
                        rail_follow["target"] = dict(rail_targets)
                    check_rail_follow()
                    if closed is not None:
                        arm["command"](arm["grip_idx"], [args.gripper_close if closed else args.gripper_open])
                    ros_refill_update(closed)
            else:
                selfdemo_update()
            if m0609_camera is not None:
                m0609_camera.follow()   # link_6 을 따라 손 카메라를 옮긴다(자식으로 못 단다)
            if amr_suction is not None:
                amr_suction.follow()   # 붙잡은 봉투를 TCP 에 붙여 옮긴다(텔레포트 추종)
            if tray_clip is not None:
                held = amr_suction.held[0] if amr_suction is not None and amr_suction.held is not None else None
                tray_clip.update([(oid, pool_objects[i]) for i, oid in sorted(pool.in_use.items())], held,
                                 pouch_speed, now=sim_now())
            if amr is not None and amr_ros is not None and cell is None and amr.arm_indices:
                # 합본의 팔: /amr_1/arm/joint_command 의 위치 목표를 같은 articulation 에 적용한다.
                targets, closed_amr = amr_ros.take()
                if amr_suction is not None and closed_amr is not None and closed_amr != amr_suction.holding():
                    # **명령이 바뀐 것을 먼저 찍는다.** lap9 에서 `on` 다음 줄이 곧장 `off` 였는데
                    # 팔이 떼라고 한 것인지 우리가 뗀 것인지 로그로 안 갈렸다. 이 줄이 있으면
                    # `/amr_1/gripper/command` 를 따로 기록하지 않아도 스테이지 로그만으로 갈린다.
                    log(f"amr gripper_command close={closed_amr} holding={amr_suction.holding()} "
                        f"t={sim_now():.3f} (참값이 명령을 따라간다 — 다르면 여기서 바뀐다)")
                    if closed_amr:
                        candidates = [pool_objects[index] for index in state["carried"]]
                        if state["pouch"] is not None and state["pouch"] not in candidates:
                            candidates.append(state["pouch"])
                        amr_suction.suck_nearest(candidates, reason="gripper_command close=true",
                                                 now=sim_now())
                    else:
                        amr_suction.suck(False, None, reason="gripper_command close=false", now=sim_now())
                if targets:
                    applied, unknown = amr.apply_arm_positions(targets)
                    if unknown:
                        state["arm_unknown_names"] = state.get("arm_unknown_names", 0) + len(unknown)
                        if arm_name_warn.hit():
                            log(f"amr arm_command unknown names={sorted(unknown)} "
                                f"applied={applied} (계약 186절: 자기 이름만)")
            if amr is not None and amr_ros is not None:
                amr_ros.spin_once()
                command, last_seen = amr_ros.take_amr()
                wall_now = time.monotonic()
                if command is None or amrlib.stale(last_seen, wall_now):
                    # 계약 5절: 명령이 끊기면 0 이다. 속도 드라이브라 목표 0 이 곧 정지다.
                    amr.apply((0.0, 0.0, 0.0), wall_now)
                else:
                    amr.apply(amrlib.order_command(command[0], command[1]), wall_now)
            trace.mark("world.step")
            tick_started = time.monotonic()
            step_world()
            tick_wall = time.monotonic() - tick_started
            if tick_wall > LOOP_STALL_WALL_S and stall_log.hit():
                # 틱이 길면 joint_states·dispense 응답이 그만큼 늦는다(9/23: 공백 0.67-1.13 s,
                # `waypoint 도착 못 함`·`Dispense 2 s 안에 응답이 없다`). 그 틱에 무엇을 불렀는지 남긴다.
                log(f"loop stall wall_s={tick_wall:.3f} sim={sim_now():.3f} recent_calls={trace.dump()}")
            updates += 1
            physics_steps.tick(sim_now())
            check_rail_overlap()
            observe_belt()
            now = time.monotonic()
            if arm_ros is not None and arm is not None and now >= next_arm_states:
                positions = arm["articulation"].get_joint_positions()
                velocities = arm["articulation"].get_joint_velocities()
                if positions is not None and velocities is not None:
                    arm_ros.publish_joint_states(sim_now(), positions[arm["arm_idx"]], velocities[arm["arm_idx"]])
                    arm_ros.publish_rail_states(sim_now(), positions[arm["rail_idx"]], velocities[arm["rail_idx"]])
                    arm_ros.publish_holding(ros_refill_holding())  # attach by distance on close (ros refill)
                next_arm_states = common.next_publish_time(next_arm_states, now, refill.JOINT_STATES_HZ)
            if ur5_ros is not None and cell is not None and now >= next_ur5_states:
                positions = cell.robot.get_joint_positions()
                velocities = cell.robot.get_joint_velocities()
                if positions is not None and velocities is not None:
                    ur5_ros.publish_joint_states(sim_now(), positions[cell.arm_idx], velocities[cell.arm_idx])
                    ur5_ros.publish_holding(cell.holding())
                next_ur5_states = common.next_publish_time(next_ur5_states, now, refill.JOINT_STATES_HZ)
            if sensors_on and now >= next_pouches:
                ros.publish(bridge.POUCHES, bridge.encode(bridge.POUCHES, **pouches_payload()))
                next_pouches = common.next_publish_time(next_pouches, now, sensorlib.POUCHES_HZ)
            if sensors_on and now >= next_cabinet:
                for payload in cabinet_payloads():
                    ros.publish(bridge.CABINET, bridge.encode(bridge.CABINET, **payload))
                next_cabinet = common.next_publish_time(next_cabinet, now, sensorlib.CABINET_HZ)
            if sensors_on and amr is not None and now >= next_tags:
                payload = tag_payload()
                if payload is not None:  # 풀에 없는 침상 앞에서는 **아무것도 안 낸다**(fail-closed)
                    ros.publish(bridge.TAG_READS, bridge.encode(bridge.TAG_READS, **payload))
                next_tags = common.next_publish_time(next_tags, now, sensorlib.TAG_READS_HZ)
            if amr is not None and amr_ros is not None and now >= next_amr_states:
                # 계약 97줄: 한 메시지에 dummy 3 + UR5 6. 합본은 한 articulation 이라 한 번에 읽힌다.
                # 속도는 **비우지 않고 그대로** 낸다. 0 으로 채우면 base/stopped 가 항상 참이 된다(주행 9/21).
                names, ordered, vel = amr.read_all()
                if ordered is not None:
                    amr_ros.publish_amr_states(sim_now(), names, ordered, vel)
                if amr_suction is not None:
                    # 작성자가 0 이면 팔이 unknown 으로 시한까지 기다린다(작전 9/21, #444 F02).
                    amr_ros.publish_holding(amr_suction.holding())
                next_amr_states = common.next_publish_time(next_amr_states, now, amrlib.COMMAND_HZ)
            if chase_follow is not None:
                chase_follow()
            if state["reset_pose_due"] is not None and sim_now() >= state["reset_pose_due"][0]:
                try:
                    log_reset_pose()
                except Exception as error:  # 로그 한 줄이 회차를 멈추지 않는다
                    log(f"WARN reset pose unreadable reason={type(error).__name__}: {error}")
            if walkers is not None:
                walker_now = sim_now()
                walkers.update(0.0 if walker_state["last"] is None else walker_now - walker_state["last"], walker_now,
                               real_amr_xys())
                walker_state["last"] = walker_now
            if traffic is not None:
                traffic_tick(sim_now())       # 시뮬 시간 — 0.5 m/s 는 sim 기준이다(`now` 는 벽시계)
            if blocker is not None and amr is not None:
                blocker.update(sim_now(), real_amr_xys()[0])   # amr_1 몸체 중심(못 읽으면 None)
            if amr is not None and (walkers is not None or traffic is not None or blocker is not None) \
                    and encounter_state["on"]:
                # AMR 2 m 안에 든 보행자·더미·정지 캡슐 구간(#697 avoidance_encounters). 기록만 한다.
                try:
                    others = {**(walkers.positions() if walkers is not None else {}),
                              **(traffic.positions() if traffic is not None else {}),
                              **(blocker.positions() if blocker is not None else {})}
                    base = amr.base_world_pose()
                    for line in encounter_state["tracker"].update(sim_now(), None if base is None else base[:2],
                                                                  others):
                        log(line)
                except Exception as error:  # 로그 한 줄이 회차를 멈추지 않는다. 한 번 실패하면 끈다
                    log(f"WARN encounters disabled reason={type(error).__name__}: {error}")
                    encounter_state["on"] = False
            if args.gripper_command_seq and ros is not None and cell is not None and now >= next_gripper:
                ros.publish(bridge.GRIPPER_STATE, bridge.encode(
                    bridge.GRIPPER_STATE, stamp=bridge.stamp(sim_now()),
                    **obslib.gripper_fields(state["epoch"], physics_steps.seq, gripper_gate.last_applied,
                                            cell.holding())))
                next_gripper = common.next_publish_time(next_gripper, now, 10.0)
            if fleet_state["on"] and now >= next_fleet:
                # 관제 웹 전체 보기(재범 v1.0). 소품 자리라 한 번 실패하면 끄고 회차는 계속 간다.
                try:
                    ros.publish(bridge.FLEET_POSES, bridge.encode(
                        bridge.FLEET_POSES, stamp=bridge.stamp(sim_now()), frame_id="map",
                        poses=fleet_poses_payload()))
                except Exception as error:
                    log(f"WARN fleet poses disabled reason={type(error).__name__}: {error}")
                    fleet_state["on"] = False
                next_fleet = common.next_publish_time(next_fleet, now, bridge.FLEET_POSES_HZ)
            if ros is not None:
                playing = bool(world.is_playing())
                if playing != running["last"] or now >= running["next"]:
                    # 관제 웹 Play/Stop(재범 v1.0). 바뀌면 곧바로, 아니면 1 Hz.
                    ros.publish_running(playing)
                    if playing != running["last"]:
                        log(f"sim_running {str(playing).lower()} sim_time={sim_now():.3f}")
                    running["last"] = playing
                    running["next"] = common.next_publish_time(running["next"], now, bridge.SIM_RUNNING_HZ)
            if ros is not None and now >= next_belt:
                st = model.state()
                ros.publish(bridge.BELT, bridge.encode(bridge.BELT, stamp=bridge.stamp(sim_now()), epoch=state["epoch"],
                                                       **st))
                if args.belt_observation:
                    ros.publish(bridge.BELT_OBSERVATION, bridge.encode(
                        bridge.BELT_OBSERVATION, stamp=bridge.stamp(sim_now()),
                        **obslib.fields(model, state["epoch"], physics_steps.seq, state["obs_mode"], state["obs_zone"],
                                        pouch_motion.motion, obslib.command_applied(belt_command_readback()))))
                next_belt = common.next_publish_time(next_belt, now, 5.0)
            next_tick += period
            delay = next_tick - time.monotonic()
            if delay > 0:
                time.sleep(delay)
            else:
                next_tick = time.monotonic()

        elapsed = time.monotonic() - started
        timeline_flags["closing"] = True  # from here on nothing reads the clock graph from timeline callbacks
        if stop_event.is_set():
            reason = "sigint"
        if reason == "app_stopped":
            refill.log_app_state(simulation_app)
            log(f"kit_log tail this file for the reason: {diag.kit_log_settings().get('/log/file')} "
                f"quit_watch={'on' if quit_watch is not None else 'off'}")
        # Every end uses the last sim time read inside the loop: no clock graph reads on the way out (9/17 master02:
        # two OmniGraphError tracebacks after app_stopped and after --duration).
        sim_elapsed = sim_clock["last"] - sim_started
        log(f"stop reason={reason} updates={updates} wall_s={elapsed:.3f} "
            f"loop_hz={updates / elapsed if elapsed > 0 else 0.0:.2f} sim_s={sim_elapsed:.3f} "
            f"rtf={sim_elapsed / elapsed if elapsed > 0 else 0.0:.3f} dispensed={state['spawned']} "
            f"render_products={cell.render_products if cell is not None else 0} "
            f"ur5={'on' if cell is not None else 'off'} pick_notices_ignored_ur5={state['pick_notices_ignored_ur5']} "
            f"gripper_bool_ignored={state['gripper_bool_ignored']} "
            f"contact_watch={'on' if contact_watch is not None else 'off'}")
    except Exception as exc:
        import traceback

        refill.write_line(f"[pharmacy_stage] error {type(exc).__name__}: {exc}", sys.stderr)
        traceback.print_exc()
        exit_code = common.exit_code_for(True)
    finally:
        if ros is not None:
            try:
                ros.publish_running(False)      # 관제 웹: 끝났다(다음 1 Hz 가 안 오는 것보다 빠르다)
            except Exception as exc:  # shutdown must continue
                refill.write_line(f"[pharmacy_stage] sim_running false not sent {exc}", sys.stderr)
            try:
                ros.node.destroy_node()
                for extra in (ur5_ros, arm_ros):
                    if extra is not None:
                        extra.close(shutdown=False)
                import rclpy

                if rclpy.ok():
                    rclpy.shutdown()
            except Exception as exc:  # shutdown must continue
                refill.write_line(f"[pharmacy_stage] ros close error {exc}", sys.stderr)
        if exit_code:
            refill.write_line(f"[pharmacy_stage] exit code={exit_code} "
                              "(skipping simulation_app.close(), which exits 0)", sys.stderr)
            os._exit(exit_code)
        simulation_app.close()
    return exit_code


class JsonBridge:
    """std_msgs/String publishers and subscribers for the JSON topics, on Isaac's internal rclpy."""

    def __init__(self, extra_publish=(), extra_subscribe=()):
        import rclpy
        from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy
        from std_msgs.msg import String

        self._rclpy = rclpy
        self._string = String
        log(f"rclpy init={refill.init_rclpy(rclpy)}")
        self.node = rclpy.create_node("isaac_pharmacy_stage")

        def profile(topic):
            reliability, durability, depth = bridge.QOS[topic]
            return QoSProfile(
                reliability=ReliabilityPolicy.RELIABLE if reliability == "reliable" else ReliabilityPolicy.BEST_EFFORT,
                durability=(DurabilityPolicy.TRANSIENT_LOCAL if durability == "transient_local"
                            else DurabilityPolicy.VOLATILE),
                history=HistoryPolicy.KEEP_LAST, depth=depth)

        from std_msgs.msg import Bool

        self._bool = Bool
        self._running_pub = self.node.create_publisher(Bool, bridge.SIM_RUNNING, QoSProfile(
            reliability=ReliabilityPolicy.RELIABLE, durability=DurabilityPolicy.VOLATILE,
            history=HistoryPolicy.KEEP_LAST, depth=1))
        self._publishers = {topic: self.node.create_publisher(String, topic, profile(topic))
                            for topic in (bridge.DISPENSE_RESPONSE, bridge.RESET_RESPONSE, bridge.BELT, bridge.EVENTS,
                                          *extra_publish)}
        self._inbox = {bridge.DISPENSE_REQUEST: [], bridge.RESET_REQUEST: [], bridge.PICK_NOTICE: [],
                       **{topic: [] for topic in extra_subscribe}}
        for topic in self._inbox:
            self.node.create_subscription(String, topic, lambda msg, t=topic: self._inbox[t].append(msg.data),
                                          profile(topic))
        log(f"ros json topics pub={sorted(self._publishers)} sub={sorted(self._inbox)}")

    def spin_once(self):
        self._rclpy.spin_once(self.node, timeout_sec=0.0)

    def take(self, topic):
        items, self._inbox[topic] = self._inbox[topic], []
        return items

    def publish(self, topic, text):
        msg = self._string()
        msg.data = text
        self._publishers[topic].publish(msg)

    def publish_running(self, playing):
        msg = self._bool()
        msg.data = bool(playing)
        self._running_pub.publish(msg)

    def close(self):
        self.node.destroy_node()
        if self._rclpy.ok():
            self._rclpy.shutdown()


def fleet_poses_wanted(args):
    """`/isaac/fleet/poses` 를 내나: 여벌 AMR(`--amr-count` > 1)이나 더미(`--traffic-dummies`)가 있을 때."""
    return bool(getattr(args, "amr", False) and getattr(args, "amr_combined", None)
                and (getattr(args, "amr_count", 1) > 1 or getattr(args, "traffic_dummies", 0)))


def main(argv=None):
    return run(parse_args(argv))


if __name__ == "__main__":
    sys.exit(main())
