"""병원 전체 preset hospital-full(#527 H1·H2): 인자·방·씬 컨베이어·belt_end·보관함. Isaac 없음.

usd-core(pxr)가 있으면 HospitalConveyor 를 작은 가짜 스테이지에서 돌려 본다. 없으면 그 부분만 건너뛴다.

    python3 -m unittest sim.tests.test_hospital_full
"""

import importlib.util
import math
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STANDALONE = ROOT / "sim" / "standalone"
sys.path.insert(0, str(STANDALONE))

from p3sim import belt, hospital_nav, hospital_zones, layout_v2, pouch, truth_sensors, views  # noqa: E402
from p3sim import hospital_conveyor as hconv  # noqa: E402

SCENE = ROOT / "sim" / "scenes" / "hospital_navigationv1.usda"
ZONES = ROOT / "src" / "rokey_p3_description" / "config" / "zones.hospital.yaml"
POOL = ROOT / "src" / "rokey_p3_orchestrator" / "config" / "order_pool.hospital.yaml"
T = (-7.85, 9.50)
TOL = 1e-9
#: 우리가 병원에서 만들지 않는 상자(재범 결정 9/23): 벽·벨트 다리·적재 자리·배출구.
NOT_IN_HOSPITAL = re.compile(r"^(Wall_.*|BeltLeg\d+|LoadingSpot|DispenserOutlet)$")
#: 잰 정착점(#240 5790540704) — 봉투가 Rollers_01 끝에서 실제로 선 자리.
SETTLED = (-8.295, 5.036, 0.389)


def load_stage():
    spec = importlib.util.spec_from_file_location("pharmacy_stage_hospital_full", STANDALONE / "pharmacy_stage.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


STAGE = load_stage()
SITE = ["--base-usd", str(SCENE), "--amr-start", "-8.238", "4.169", "--amr-combined", "/assets/ridgeback_ur5.usd"]


def aabb(box):
    lo = [box.center[i] - box.size[i] / 2.0 for i in range(3)]
    return lo, [box.center[i] + box.size[i] / 2.0 for i in range(3)]


class PresetArgumentTests(unittest.TestCase):
    def test_preset_turns_on_the_hospital_run(self):
        args = STAGE.parse_args(["--preset", "hospital-full"])
        self.assertTrue(STAGE.hospital_full(args))
        self.assertEqual(("ros", "v2", 0.0), (args.mode, args.scene, args.ros_pick_stand_in_s))
        self.assertTrue(args.amr and args.ur5 and args.base_root_prims)
        self.assertFalse(args.no_room)
        self.assertFalse(args.ur5_spawn_ready)       # 받침대 UR5 용 — 합본이면 뜻이 없다
        self.assertEqual(["ridgeback_ur5", "Graph", "gripper"], args.base_deactivate)
        self.assertEqual([0.0, 0.0, 0.0, 0.0], list(args.pharmacy_origin))
        self.assertEqual(list(T), list(args.v2_offset))
        self.assertEqual(list(STAGE.HOSPITAL_PARKING), list(args.parking_origin))
        self.assertEqual(str(ZONES), args.zones_file)
        self.assertEqual(str(hconv.SURFACES_JSON), args.conveyor_surfaces)

    def test_other_presets_do_not_turn_it_on(self):
        for name in STAGE.PRESETS:
            if name in ("hospital-full", "hospital"):
                continue
            args = STAGE.parse_args(["--preset", name])
            self.assertFalse(STAGE.hospital_full(args), name)
            self.assertIsNone(args.v2_offset, name)
            self.assertIsNone(args.zones_file, name)
        self.assertFalse(STAGE.hospital_full(STAGE.parse_args([])))

    def test_offset_moves_the_stage_origins_once(self):
        plain = STAGE.parse_args(["--preset", "demo-ros-refill-v2"])
        moved = STAGE.parse_args(["--preset", "hospital-full"])
        for name in ("rail_origin", "dispenser_origin", "shelf_origin"):
            before, after = getattr(plain, name), getattr(moved, name)
            self.assertAlmostEqual(after[0] - before[0], T[0], delta=TOL, msg=name)
            self.assertAlmostEqual(after[1] - before[1], T[1], delta=TOL, msg=name)
            self.assertEqual(before[2], after[2], name)
        # 설계안 값(재지 않았다): 레일 원점 ≈ (-7.85, 9.80), 조제기 상자 중심 ≈ (-6.85, 10.50).
        self.assertEqual((-7.85, 9.8), tuple(round(v, 6) for v in moved.rail_origin[:2]))
        self.assertEqual((-6.85, 10.5), tuple(round(v, 6) for v in moved.dispenser_origin[:2]))
        # 준 좌표도 모듈 기준으로 보고 같이 옮긴다.
        given = STAGE.parse_args(["--preset", "hospital-full", "--rail-origin", "0 0.3 0"])
        self.assertEqual((-7.85, 9.8), tuple(round(v, 6) for v in given.rail_origin[:2]))

    def test_rail_joint_ranges_do_not_move(self):
        plain = STAGE.parse_args(["--preset", "demo-ros-refill-v2"])
        moved = STAGE.parse_args(["--preset", "hospital-full"])
        a, b = STAGE.v2_rail_info(plain), STAGE.v2_rail_info(moved)
        self.assertEqual(a["limits"], b["limits"])
        self.assertEqual(a["names"], b["names"])
        self.assertAlmostEqual(b["origin"][0] - a["origin"][0], T[0], delta=TOL)
        self.assertAlmostEqual(b["origin"][1] - a["origin"][1], T[1], delta=TOL)

    def test_validate_names_every_site_value(self):
        problems = " ".join(STAGE.validate(STAGE.parse_args(["--preset", "hospital-full"])))
        self.assertIn("--preset hospital-full needs --base-usd", problems)
        self.assertIn("--preset hospital-full needs --amr-start", problems)
        self.assertIn("--preset hospital-full needs --amr --amr-combined", problems)
        self.assertNotIn("need --base-usd", problems)          # 일반 문구를 두 번 하지 않는다

    def test_validate_passes_with_the_site_values_and_sensors(self):
        args = STAGE.parse_args(["--preset", "hospital-full", *SITE, "--sim-sensors", "--order-pool", str(POOL)])
        self.assertEqual([], STAGE.validate(args))

    def test_pouch_at_end_needs_the_hospital_run(self):
        problems = " ".join(STAGE.validate(STAGE.parse_args(["--pouch-at-end"])))
        self.assertIn("--pouch-at-end needs --hospital-full", problems)
        args = STAGE.parse_args(["--preset", "hospital-full", *SITE, "--pouch-at-end"])
        self.assertTrue(args.pouch_at_end)
        self.assertEqual([], STAGE.validate(args))

    def test_our_belt_checks_do_not_apply(self):
        # 우리 벨트가 없다: 벽·출발 구간 검사가 병원 회차를 막으면 안 된다.
        args = STAGE.parse_args(["--preset", "hospital-full", *SITE, "--wall-x", "50", "--spawn-along", "0 9"])
        self.assertEqual([], STAGE.validate(args))

    def test_zones_file_needs_the_belt_end(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "zones.yaml"
            text = ZONES.read_text(encoding="utf-8").split("pharmacy:", 1)[0]
            path.write_text(text, encoding="utf-8")
            args = STAGE.parse_args(["--preset", "hospital-full", *SITE, "--zones-file", str(path)])
            self.assertTrue(any("pharmacy.belt_end" in p for p in STAGE.validate(args)))
        args = STAGE.parse_args(["--preset", "hospital-full", *SITE, "--zones-file", "/nope/zones.yaml"])
        self.assertTrue(any("--zones-file" in p for p in STAGE.validate(args)))

    def test_room_and_scene_mistakes_are_named(self):
        args = STAGE.parse_args(["--preset", "hospital-full", *SITE, "--no-room"])
        self.assertTrue(any("--no-room" in p for p in STAGE.validate(args)))
        args = STAGE.parse_args(["--preset", "hospital-full", *SITE, "--scene", "v1"])
        self.assertTrue(any("--scene v2" in p for p in STAGE.validate(args)))


class TrayDriftLogTests(unittest.TestCase):
    """RC-1 회차55·56: 트레이 봉투가 언제 밀렸는지 가르는 진단 줄 — 움직이는 중에도 찍는다(동작 불변)."""

    def test_the_sensor_logs_tray_drift_before_the_still_check(self):
        source = (ROOT / "sim" / "standalone" / "pharmacy_stage.py").read_text()
        body = source.split("def pouch_detections():", 1)[1].split("def pouches_payload", 1)[0]
        drift = body.index("log_tray_drift(order_id, obj, world, slots, speed)")
        still = body.index("if not on_deck and speed is not None and speed > sensorlib.POUCH_STILL_SPEED:")
        self.assertLess(drift, still)
        self.assertIn('log(f"tray drift order_id={order_id} offset_xy=', source)


class TrayClipWiringTests(unittest.TestCase):
    def test_hospital_turns_the_tray_clip_on_and_releases_it_on_reset_and_stop(self):
        self.assertTrue(STAGE.parse_args(["--preset", "hospital", *SITE]).tray_clip)
        self.assertFalse(STAGE.parse_args(["--preset", "hospital-full"]).tray_clip)
        source = (ROOT / "sim" / "standalone" / "pharmacy_stage.py").read_text()
        self.assertIn('tray_clip.release_all("reset")', source)
        self.assertIn('tray_clip.release_all("timeline_stop")', source)
        self.assertIn("tray_clip.update(", source)


class TrafficDummiesDefaultTests(unittest.TestCase):
    """재범 9/25 00:2x: 회피 장면을 안전판에. 병원 preset 은 더미 2 대, 끄는 인자는 그대로다."""

    def test_hospital_runs_two_dummies_by_default_and_zero_turns_them_off(self):
        args = STAGE.parse_args(["--preset", "hospital", *SITE])
        self.assertEqual(STAGE.HOSPITAL_TRAFFIC_DUMMIES, args.traffic_dummies)
        self.assertEqual(2, STAGE.HOSPITAL_TRAFFIC_DUMMIES)
        off = STAGE.parse_args(["--preset", "hospital", *SITE, "--traffic-dummies", "0"])
        self.assertEqual(0, off.traffic_dummies)
        self.assertEqual(0, STAGE.parse_args(["--preset", "hospital-full"]).traffic_dummies)


class PedestriansDefaultTests(unittest.TestCase):
    """재범 9/25 00:2x: 보행자도 병원 preset 기본 ON(선 둘에 한 명씩), 끄는 인자는 그대로다."""

    def test_hospital_walks_two_pedestrians_by_default_and_zero_turns_them_off(self):
        args = STAGE.parse_args(["--preset", "hospital", *SITE])
        self.assertEqual(STAGE.HOSPITAL_PEDESTRIANS, args.pedestrians)
        self.assertEqual(2, STAGE.HOSPITAL_PEDESTRIANS)
        self.assertEqual([], STAGE.validate(args))
        off = STAGE.parse_args(["--preset", "hospital", *SITE, "--pedestrians", "0"])
        self.assertEqual(0, off.pedestrians)
        self.assertEqual(0, STAGE.parse_args(["--preset", "hospital-full"]).pedestrians)


class StationTagTests(unittest.TestCase):
    """재범 9/25 03:3x: 병동 → B, 병실 → C 테이블, 병상 → D. 테이블에서는 `st-<zone>`, 침상에서는 `pt-<환자>`."""

    def test_tables_are_the_three_station_zones_with_a_cabinet(self):
        self.assertEqual(["station_b", "station_c", "station_d"], hospital_zones.station_tables(ZONES))

    def test_tables_read_station_tags_first_and_beds_read_patient_tags(self):
        stations = hospital_zones.station_tables(ZONES)
        beds = {"bed_a1": "1001", "station_b": "2011"}
        self.assertEqual(("st-station_b", "station"), truth_sensors.tag_for_zone("station_b", stations, beds))
        self.assertEqual(("st-station_d", "station"), truth_sensors.tag_for_zone("station_d", stations, beds))
        self.assertEqual(("pt-1001", "patient"), truth_sensors.tag_for_zone("bed_a1", stations, beds))
        self.assertIsNone(truth_sensors.tag_for_zone("bed_b1", stations, beds))
        self.assertIsNone(truth_sensors.tag_for_zone("station_a", stations, beds))


class HospitalPouchPoolTests(unittest.TestCase):
    """9/24 10건(50b658a): 풀 8 에 주문 10 — ord-0009·0010 배출이 pool_exhausted 로 거부됐다."""

    def setUp(self):
        self.args = STAGE.parse_args(["--preset", "hospital", *SITE])
        text = (ROOT / "src" / "rokey_p3_orchestrator" / "config" / "order_pool.hospital.yaml").read_text()
        self.orders = sorted(set(re.findall(r"order_id:\s*(ord-[0-9]{4})", text)))

    def test_every_hospital_order_has_its_own_labelled_pouch(self):
        self.assertEqual(13, len(self.orders))   # 침상 10 + 테이블 B·C1·C2(재범 9/25)
        labels = pouch.pool_labels(self.orders, self.args.pouch_pool)
        self.assertEqual(set(self.orders), set(labels))
        self.assertGreaterEqual(self.args.pouch_pool, len(self.orders) + 2)   # 여벌 2(보류·재시도)

    def test_parking_row_is_free_on_the_hospital_map(self):
        grid = hospital_nav.load_map()
        for i in range(self.args.pouch_pool):
            x, y = self.args.parking_origin[0], self.args.parking_origin[1] + 0.15 * i
            self.assertFalse(grid.is_blocked(x, y), (x, y))
            self.assertGreaterEqual(grid.clearance(x, y), 0.25, (x, y))   # 칸 중심 거리(#639 의 edge_clearance 전)


class HospitalRoomTests(unittest.TestCase):
    def setUp(self):
        self.base = STAGE.room(STAGE.parse_args(["--preset", "demo-ros-refill-v2"]))
        self.args = STAGE.parse_args(["--preset", "hospital-full"])
        self.room = STAGE.room(self.args)

    def test_no_walls_belt_loading_spot_or_outlet(self):
        names = {box.name for box in self.room["boxes"]}
        self.assertFalse([name for name in names if NOT_IN_HOSPITAL.match(name)])
        expected = {box.name for box in self.base["boxes"] if not NOT_IN_HOSPITAL.match(box.name)}
        self.assertEqual(expected, names)
        self.assertTrue(any(NOT_IN_HOSPITAL.match(box.name) for box in self.base["boxes"]))  # 시험이 헛돌지 않게

    def test_every_module_box_is_the_v2_box_shifted_by_t(self):
        before = {box.name: box for box in self.base["boxes"]}
        for box in self.room["boxes"]:
            old = before[box.name]
            self.assertAlmostEqual(box.center[0] - old.center[0], T[0], delta=TOL, msg=box.name)
            self.assertAlmostEqual(box.center[1] - old.center[1], T[1], delta=TOL, msg=box.name)
            self.assertAlmostEqual(box.center[2], old.center[2], delta=TOL, msg=box.name)
            for a, b in zip(old.size, box.size, strict=True):  # 폭 = 오른쪽 − 왼쪽이라 부동소수 잡음만 있다
                self.assertAlmostEqual(a, b, delta=1e-9, msg=box.name)
            self.assertEqual((old.yaw, old.kind), (box.yaw, box.kind), box.name)

    def test_cells_targets_and_obstacles_shift(self):
        v2, base = self.room["v2"], self.base["v2"]
        self.assertEqual(set(base["cells"]), set(v2["cells"]))
        for key, cell in base["cells"].items():
            home, moved = layout_v2.canister_home(cell), layout_v2.canister_home(v2["cells"][key])
            self.assertAlmostEqual(moved[0] - home[0], T[0], delta=TOL)
            self.assertAlmostEqual(moved[1] - home[1], T[1], delta=TOL)
        self.assertAlmostEqual(v2["targets"]["round"]["center"][0] - base["targets"]["round"]["center"][0], T[0],
                               delta=TOL)
        self.assertAlmostEqual(v2["targets"]["module"]["entry_center"][1]
                               - base["targets"]["module"]["entry_center"][1], T[1], delta=TOL)
        self.assertEqual(len([o for o in base["obstacles"] if o["name"] != "DispenserOutlet"]), len(v2["obstacles"]))

    def test_zones_belt_end_and_cabinets_come_from_the_zones_file(self):
        self.assertEqual(hospital_zones.zones_from_yaml(ZONES), self.room["zones"])
        hospital = self.room["hospital"]
        self.assertEqual((-8.1937, 4.9644, 0.3847, -1.5708), hospital["belt_end"])
        self.assertEqual(hconv.SPAWN, self.room["belt_start"])
        beds = {name for name in self.room["zones"] if name.startswith("bed_") and "/" not in name}
        tables = {"station_b/cabinet", "station_c/cabinet", "station_d/cabinet"}
        self.assertEqual({f"{bed}/cabinet" for bed in beds} | tables, set(hospital["cabinet_sizes"]))
        for name, (sx, sy) in hospital["cabinet_sizes"].items():  # 협탁 bbox ≈ 0.50 × 0.53(앵커 JSON)
            if name == "station_b/cabinet":   # 스테이션 B 테이블 폭 × 놓는 띠(9/24)
                self.assertAlmostEqual(1.088, sx, places=3)
                self.assertAlmostEqual(hospital_nav.STATION_B_STRIP, sy, places=3)
                continue
            if name in tables:   # 병동 입구 복도 협탁(C1·C2): 긴 변이 y — 놓는 띠(x) × 긴 변(y)(9/25)
                self.assertAlmostEqual(hospital_nav.STATION_B_STRIP, sx, places=3)
                self.assertAlmostEqual(1.088, sy, places=3)
                continue
            self.assertAlmostEqual(0.50, sx, places=3, msg=name)
            self.assertAlmostEqual(0.5295, sy, places=3, msg=name)

    def test_the_module_stands_on_free_map_cells(self):
        """모듈 상자·쉬는 봉투·전경 카메라가 병원 지도(전 높이)의 막힌 칸에 안 걸린다. 지도는 렌더 기하에서 뽑았다."""
        grid = hospital_nav.load_map()
        step = grid.res / 2.0

        def blocked_points(lo, hi):
            hits = []
            nx, ny = int(math.ceil((hi[0] - lo[0]) / step)), int(math.ceil((hi[1] - lo[1]) / step))
            for i in range(nx + 1):
                for j in range(ny + 1):
                    x, y = lo[0] + (hi[0] - lo[0]) * i / max(nx, 1), lo[1] + (hi[1] - lo[1]) * j / max(ny, 1)
                    if grid.is_blocked(x, y):
                        hits.append((round(x, 3), round(y, 3)))
            return hits

        for box in self.room["boxes"]:
            lo, hi = aabb(box)
            self.assertEqual([], blocked_points(lo, hi), box.name)
        parking = [(self.args.parking_origin[0], self.args.parking_origin[1] + 0.15 * i)
                   for i in range(self.args.pouch_pool)]
        for x, y in parking:
            self.assertFalse(grid.is_blocked(x, y), (x, y))
            for box in self.room["boxes"]:
                lo, hi = aabb(box)
                inside = lo[0] - 0.1 <= x <= hi[0] + 0.1 and lo[1] - 0.1 <= y <= hi[1] + 0.1
                self.assertFalse(inside, f"쉬는 봉투 {(x, y)} 가 {box.name} 옆 0.1 m 안이다")
        eye, target = STAGE.shifted_view(self.args, *views.view("v2", "overview"))
        self.assertFalse(grid.is_blocked(eye[0], eye[1]), eye)
        self.assertEqual((T[0], T[1]), (round(target[0] - 0.0, 6), round(target[1] - 0.75, 6)))

    def test_module_footprint(self):
        """설계안 기록: 모듈은 x -9.45..-6.25, y 9.62..10.80 이다(Track_06 막힌 띠 x ≤ -9.55 의 동쪽)."""
        los, his = zip(*(aabb(box) for box in self.room["boxes"]), strict=True)
        x_lo, y_lo = min(lo[0] for lo in los), min(lo[1] for lo in los)
        x_hi, y_hi = max(hi[0] for hi in his), max(hi[1] for hi in his)
        self.assertEqual((-9.45, -6.25, 9.62, 10.8), tuple(round(v, 2) for v in (x_lo, x_hi, y_lo, y_hi)))


class BeltEndTests(unittest.TestCase):
    def test_belt_end_is_the_exit_edge_centre_of_rollers_01(self):
        x, y, z, yaw = hospital_nav.pharmacy_frames()["belt_end"]
        surface = hospital_nav.A1_TERMINAL_SURFACE
        self.assertAlmostEqual(-8.1937, x, places=6)      # x 중심
        self.assertEqual(surface["min"][1], y)              # −y 로 나가므로 min y
        self.assertEqual(surface["max"][2], z)              # 윗면
        self.assertAlmostEqual(-math.pi / 2, yaw)

    def test_measured_settle_point_is_inside_the_truth_sensor_zone(self):
        x, y, _z, _yaw = hospital_nav.pharmacy_frames()["belt_end"]
        gap = math.dist(SETTLED[:2], (x, y))
        self.assertAlmostEqual(0.124, gap, places=3)
        self.assertLess(gap, truth_sensors.BELT_END_RADIUS)
        self.assertTrue(truth_sensors.in_belt_end(SETTLED, (x, y)))

    def test_pouch_at_end_lies_on_the_terminal_roller_inside_the_truth_zone(self):
        # S3·S4 단독(--pouch-at-end): 봉투 발자국이 끝 롤러 윗면 안이고, 참값 센서가 보는 끝 구역 안이다.
        belt_end = hospital_nav.pharmacy_frames()["belt_end"]
        size = STAGE.DEFAULT_POUCH_SIZE
        (x, y, z), yaw = STAGE.pouch_at_end_pose(belt_end, size, 0.0)
        surface = hospital_nav.A1_TERMINAL_SURFACE
        half_long, half_short = max(size[:2]) / 2, min(size[:2]) / 2
        self.assertAlmostEqual(belt_end[3], yaw)                       # 긴 변이 나가는 방향(−y)
        self.assertGreaterEqual(x - half_short, surface["min"][0])
        self.assertLessEqual(x + half_short, surface["max"][0])
        self.assertGreaterEqual(y - half_long, surface["min"][1])      # 가장자리에서 안쪽
        self.assertLessEqual(y + half_long, surface["max"][1])
        self.assertAlmostEqual(surface["max"][2] + size[2] / 2, z)
        self.assertTrue(truth_sensors.in_belt_end((x, y, z), belt_end[:2]))
        # 끝 구역 판정(RouteBeltModel edge_margin 0.03) 안이어야 POUCH_AT_END 가 난다(S3·S4 1회차 bb3ac33 은 0.05 였다)
        edge_gap = (y - half_long) - belt_end[1]
        self.assertGreaterEqual(edge_gap, 0.0)
        self.assertLessEqual(edge_gap, 0.03)

    def test_surface_matches_the_conveyor_module_terminal(self):
        self.assertTrue(hconv.TERMINAL.endswith("/ConveyorTrack_02/Rollers_01"))
        self.assertEqual("-y", hconv.TERMINAL_DIRECTION)


class ConveyorTableTests(unittest.TestCase):
    def test_measured_table_has_19_bodies_under_the_scene_root(self):
        table = hconv.load_surfaces()
        self.assertEqual(19, len(table))
        self.assertIn(hconv.TERMINAL, table)
        self.assertTrue(all(path.startswith(hconv.SCENE_CONVEYOR_ROOT + "/") for path in table))

    def test_table_bodies_are_exactly_the_scene_node_targets(self):
        """json 의 몸체 = 씬 IsaacConveyor 노드의 inputs:conveyorPrim 대상(글자로 본다, pxr 없이)."""
        text = SCENE.read_text(encoding="utf-8")
        targets = set(re.findall(r"inputs:conveyorPrim = <([^>]+)>", text))
        self.assertEqual(set(hconv.load_surfaces()), targets)

    def test_scene_turns_the_a1_reroute_on(self):
        # 씬이 이미 Track_02 분기를 켜 둔다(`over "reroute"` inputs:value = 1). 스테이지도 탐침처럼 true 로 쓴다.
        text = SCENE.read_text(encoding="utf-8")
        track = text.index('def Xform "ConveyorTrack_02"')
        nxt = text.index('def Xform "ConveyorTrack_03"')
        section = text[track:nxt] if nxt > track else text[track:]
        self.assertRegex(section, r'over "reroute"\s*\{\s*custom bool inputs:value = 1')

    def test_paths_move_under_the_reference(self):
        self.assertEqual("/World/P3Base/Scene/Conveyor/ConveyorTrack_02/Rollers_01",
                         hconv.moved(hconv.TERMINAL, hconv.REFERENCED_CONVEYOR_ROOT))
        self.assertEqual("/Other/Path", hconv.moved("/Other/Path", hconv.REFERENCED_CONVEYOR_ROOT))
        self.assertEqual("/X/Conveyor", hconv.moved(hconv.SCENE_CONVEYOR_ROOT, "/X/Conveyor/"))

    def test_bad_tables_are_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "s.json"
            for text in ('{"surface_velocities": {}}', '{"surface_velocities": {"/Elsewhere/A": {}}}',
                         '{"surface_velocities": {"/World/Conveyor/A": {"linear": [1, 2]}}}',
                         '{"surface_velocities": {"/World/Conveyor/A": {"linear": [1, 2, NaN]}}}'):
                path.write_text(text, encoding="utf-8")
                with self.assertRaises(ValueError, msg=text):
                    hconv.load_surfaces(path)

    def test_spawn_pose_is_seeded_and_small(self):
        first = hconv.spawn_pose(0, 1, 0)
        self.assertEqual(first, hconv.spawn_pose(0, 1, 0))
        self.assertNotEqual(first, hconv.spawn_pose(0, 1, 1))
        for index in range(50):
            (x, y, z), yaw = hconv.spawn_pose(3, 2, index)
            self.assertLessEqual(abs(x - hconv.SPAWN[0]), hconv.SPAWN_JITTER_XY)
            self.assertLessEqual(abs(y - hconv.SPAWN[1]), hconv.SPAWN_JITTER_XY)
            self.assertEqual(hconv.SPAWN[2], z)
            self.assertLessEqual(abs(yaw), hconv.SPAWN_JITTER_YAW)


class RouteSpanTests(unittest.TestCase):
    """경사로처럼 높이로 긴 트랙 상자: z_band "span" 은 상자 높이 안을 벨트 위로 본다. 기본 "top" 은 그대로다."""

    RAMP = {"min": [0.0, 0.0, 0.40], "max": [2.0, 0.5, 0.90]}
    TERMINAL = {"min": [2.0, 0.0, 0.3557], "max": [2.5, 0.5, 0.3847]}

    def model(self, **kw):
        return belt.RouteBeltModel([self.RAMP], self.TERMINAL, "+x", (0.10, 0.07, 0.01), **kw)

    def test_mid_ramp_pouch(self):
        mid = belt.route_point((1.0, 0.25, 0.65))
        self.assertFalse(self.model().on_belt(mid))
        self.assertTrue(self.model(z_band="span").on_belt(mid))
        self.assertTrue(self.model(z_band="span", on_belt_height=0.10).on_belt(belt.route_point((1.0, 0.25, 0.99))))
        self.assertFalse(self.model(z_band="span", on_belt_height=0.10).on_belt(belt.route_point((1.0, 0.25, 1.1))))
        self.assertFalse(self.model(z_band="span").on_belt(belt.route_point((1.0, 0.25, 0.30))))

    def test_end_zone_is_the_same_in_both_bands(self):
        end = belt.route_point((2.45, 0.25, 0.3847 + 0.005))
        self.assertTrue(self.model().in_end_zone(end))
        self.assertTrue(self.model(z_band="span").in_end_zone(end))

    def test_unknown_band_is_refused(self):
        with self.assertRaises(ValueError):
            self.model(z_band="middle")


class StageWiringTests(unittest.TestCase):
    """Isaac 없이 볼 수 있는 배선(글자). 실제 동작은 마스터 L3(I1–I3)에서 본다."""

    def setUp(self):
        self.source = (STANDALONE / "pharmacy_stage.py").read_text(encoding="utf-8")

    def test_belt_commands_go_to_the_scene_conveyor(self):
        # 병원 컨베이어는 Play 전에 켜고 끝까지 둔다(I1 bbedd65: Play 뒤 쓰기가 닿지 않았다). set_belt 는 기록만 한다.
        body = self.source.split("        def set_belt(speed):", 1)[1].split("\n        def ", 1)[0]
        self.assertNotIn("conveyor.run()", body)
        self.assertNotIn("conveyor.stop()", body)
        build = self.source.split("conveyor_info = conveyor.discover()", 1)[1]
        self.assertLess(build.index("conveyor.run()"), build.index("world.play()"))
        self.assertIn('log("belt ours=off reason=hospital_full', self.source)

    def test_pouch_is_a_pool_pouch_at_the_measured_spawn(self):
        body = self.source.split("        def spawn_pouch(order_id):", 1)[1].split("\n        def ", 1)[0]
        self.assertIn("hconv.spawn_pose(args.seed, state[\"epoch\"], index)", body)
        self.assertIn("pool.acquire(order_id)", body)
        self.assertNotIn("CopySpec", self.source)

    def test_route_model_and_no_speed_sample(self):
        self.assertIn("beltlib.RouteBeltModel(route_tracks, terminal, hconv.TERMINAL_DIRECTION", self.source)
        self.assertIn('z_band="span"', self.source)
        self.assertIn("if (model.speed_sampling and model.running", self.source)
        self.assertIn("frame = beltlib.route_point(position, tuple(map(float, pose[1])))", self.source)

    def test_sensors_read_the_zones_file(self):
        self.assertIn('return tuple(layout["hospital"]["belt_end"][:2])', self.source)
        self.assertIn('layout["hospital"]["cabinet_sizes"].get(f"{zone}/cabinet"', self.source)

    def test_conveyor_is_set_up_after_the_scene_and_before_physics(self):
        base = self.source.index('with common.step(log, "add_base_scene"):')
        conveyor = self.source.index('with common.step(log, "hospital_conveyor"):')
        reset = self.source.index('with common.step(log, "world_reset"):')
        self.assertLess(base, conveyor)
        self.assertLess(conveyor, reset)


@unittest.skipUnless(importlib.util.find_spec("pxr"), "usd-core not installed")
class ConveyorUsdTests(unittest.TestCase):
    ROOT = "/World/P3Base/Scene/Conveyor"
    TABLE = {"/World/Conveyor/ConveyorTrack_06/Belt": ((-0.5, 0.0, 0.0), (0.0, 0.0, 0.0)),
             "/World/Conveyor/ConveyorTrack_02/Rollers_01": ((-0.5, 0.0, 0.0), (0.0, 0.0, 1.5))}

    @staticmethod
    def api_schemas(prim):
        """apiSchemas 메타데이터 그대로. usd-core 는 PhysX 스키마를 몰라 GetAppliedSchemas 가 그 이름을 거른다."""
        listop = prim.GetMetadata("apiSchemas")
        return list(listop.GetAddedOrExplicitItems()) if listop else []

    def build(self, terminal_height=0.029, target_all=True):
        from pxr import Gf, Sdf, Usd, UsdGeom

        stage = Usd.Stage.CreateInMemory()
        UsdGeom.Xform.Define(stage, "/World")

        def cube(path, center, size):
            prim = UsdGeom.Cube.Define(stage, path)
            prim.CreateSizeAttr(1.0)
            xform = UsdGeom.Xformable(prim)
            xform.AddTranslateOp().Set(Gf.Vec3d(*center))
            xform.AddScaleOp().Set(Gf.Vec3f(*size))
            return prim

        cube(f"{self.ROOT}/ConveyorTrack_06/Belt", (-9.8, 9.0, 0.90), (0.5, 4.0, 0.05))
        cube(f"{self.ROOT}/ConveyorTrack_02/Rollers_01", (-8.19, 5.45, 0.37), (0.45, 0.96, terminal_height))
        bodies = [f"{self.ROOT}/ConveyorTrack_06/Belt", f"{self.ROOT}/ConveyorTrack_02/Rollers_01"]
        for i, body in enumerate(bodies if target_all else bodies[:1]):
            graph = stage.DefinePrim(f"{self.ROOT}/Graph_{i}", "OmniGraph")
            graph.CreateAttribute("graph:variable:Velocity", Sdf.ValueTypeNames.Float).Set(1.0)
            node = stage.DefinePrim(f"{self.ROOT}/Graph_{i}/ConveyorNode", "OmniGraphNode")
            node.CreateAttribute("node:type", Sdf.ValueTypeNames.Token).Set(hconv.CONVEYOR_NODE_TYPE)
            node.CreateRelationship("inputs:conveyorPrim").SetTargets([Sdf.Path(body)])
        action = f"{self.ROOT}/ConveyorTrack_02/Sorter/ActionGraph"
        stage.DefinePrim(f"{action}/reroute").CreateAttribute("inputs:value", Sdf.ValueTypeNames.Bool).Set(False)
        stage.DefinePrim(f"{action}/SorterSpeed").CreateAttribute("inputs:value", Sdf.ValueTypeNames.Float).Set(1.0)
        return stage

    def test_graphs_are_counted_and_can_be_silenced_after_discovery(self):
        """그래프를 켜 두면 ConveyorNode 가 우리가 쓴 잰 속도를 덮는다(9/23 회차). 발견 뒤에 끈다."""
        stage = self.build()
        conveyor = hconv.HospitalConveyor(stage, self.ROOT, self.TABLE)
        info = conveyor.discover()
        self.assertEqual(2, info["graphs"])
        self.assertEqual(2, conveyor.silence_graphs())
        for path in conveyor.graph_prims:
            self.assertFalse(stage.GetPrimAtPath(path).IsActive(), path)
        # 끄는 것은 몸체와 표면 속도를 건드리지 않는다. 끈 뒤에도 run()·stop() 이 멈추지 않아야 한다 —
        # 끈 그래프의 속성 손잡이는 만료된다(9/23 회차 0b65ae2: expired 'OmniGraphNode' prim).
        conveyor.run()
        self.assertEqual((-0.5, 0.0, 0.0), tuple(conveyor.readback()))
        conveyor.stop()
        self.assertEqual((0.0, 0.0, 0.0), tuple(conveyor.readback()))
        conveyor.run()
        self.assertEqual((-0.5, 0.0, 0.0), tuple(conveyor.readback()))
        self.assertEqual([], conveyor.graph_velocities)

    def test_reassert_rewrites_only_what_went_to_zero(self):
        """Play 뒤 첫 스텝에서 표면 속도가 0 이 됐다(9/23 cc55ca7). 매 틱 맞춰 두는 길을 둔다."""
        from pxr import Gf

        stage = self.build()
        conveyor = hconv.HospitalConveyor(stage, self.ROOT, self.TABLE)
        conveyor.discover()
        conveyor.run()
        self.assertEqual(0, conveyor.reassert())           # 이미 맞으면 아무것도 안 쓴다
        stage.GetPrimAtPath(conveyor.terminal_path).GetAttribute(
            hconv.ATTR_LINEAR).Set(Gf.Vec3f(0.0, 0.0, 0.0))
        self.assertEqual(1, conveyor.reassert())
        self.assertEqual((-0.5, 0.0, 0.0), tuple(conveyor.readback()))
        conveyor.stop()
        self.assertEqual(0, conveyor.reassert())           # 세워 둔 벨트는 맞추지 않는다

    def test_hold_stops_only_the_terminal_and_run_releases_it(self):
        """봉투가 출구에 닿으면 끝 롤러만 잡는다. 매 틱 다시 쓰기도 잡힌 동안은 0 을 지킨다. run() 이 놓는다."""
        from pxr import Gf

        stage = self.build()
        conveyor = hconv.HospitalConveyor(stage, self.ROOT, self.TABLE)
        conveyor.discover()
        self.assertFalse(conveyor.hold_terminal())          # 돌기 전에는 잡지 않는다
        conveyor.run()
        self.assertTrue(conveyor.hold_terminal())
        self.assertFalse(conveyor.hold_terminal())          # 두 번 잡지 않는다
        self.assertEqual((0.0, 0.0, 0.0), tuple(conveyor.readback()))
        belt = stage.GetPrimAtPath(f"{self.ROOT}/ConveyorTrack_06/Belt").GetAttribute(hconv.ATTR_LINEAR)
        self.assertNotEqual((0.0, 0.0, 0.0), tuple(belt.Get()))    # 다른 트랙은 그대로 돈다
        self.assertEqual(0, conveyor.reassert())             # 잡힌 0 을 되돌리지 않는다
        stage.GetPrimAtPath(conveyor.terminal_path).GetAttribute(hconv.ATTR_LINEAR).Set(Gf.Vec3f(-0.5, 0.0, 0.0))
        self.assertEqual(1, conveyor.reassert())             # 누가 다시 돌려도 잡힌 동안은 0 으로
        self.assertEqual((0.0, 0.0, 0.0), tuple(conveyor.readback()))
        conveyor.run()
        self.assertFalse(conveyor.terminal_held)
        self.assertEqual((-0.5, 0.0, 0.0), tuple(conveyor.readback()))

    def test_silence_graphs_needs_discovery_first(self):
        # 비활성 프림은 PrimRange 기본 술어가 건너뛴다. 먼저 끄면 19 몸체 확인이 무너진다.
        conveyor = hconv.HospitalConveyor(self.build(), self.ROOT, self.TABLE)
        with self.assertRaises(RuntimeError):
            conveyor.silence_graphs()

    def test_discover_sets_up_only_the_conveyor_bodies(self):
        from pxr import UsdPhysics

        stage = self.build()
        conveyor = hconv.HospitalConveyor(stage, self.ROOT, self.TABLE)
        info = conveyor.discover()
        self.assertEqual(2, info["bodies"])
        self.assertEqual(f"{self.ROOT}/ConveyorTrack_02/Rollers_01", info["terminal"])
        self.assertTrue(stage.GetAttributeAtPath(
            f"{self.ROOT}/ConveyorTrack_02/Sorter/ActionGraph/reroute.inputs:value").Get())
        for path in conveyor.bodies:
            prim = stage.GetPrimAtPath(path)
            self.assertTrue(UsdPhysics.RigidBodyAPI(prim).GetKinematicEnabledAttr().Get())
            self.assertIn(hconv.SURFACE_API, self.api_schemas(prim))
            self.assertTrue(prim.GetAttribute(hconv.ATTR_ENABLED).Get())
            self.assertEqual((0.0, 0.0, 0.0), tuple(prim.GetAttribute(hconv.ATTR_LINEAR).Get()))
        for attr, _value in conveyor.graph_velocities:
            self.assertEqual(0.0, attr.Get())
        self.assertEqual(3, len(conveyor.graph_velocities))   # 그래프 변수 둘 + SorterSpeed

    def test_run_writes_the_table_and_stop_zeroes_it(self):
        stage = self.build()
        conveyor = hconv.HospitalConveyor(stage, self.ROOT, self.TABLE)
        conveyor.discover()
        conveyor.run()
        terminal = stage.GetPrimAtPath(f"{self.ROOT}/ConveyorTrack_02/Rollers_01")
        self.assertEqual((-0.5, 0.0, 0.0), tuple(terminal.GetAttribute(hconv.ATTR_LINEAR).Get()))
        self.assertEqual((0.0, 0.0, 1.5), tuple(terminal.GetAttribute(hconv.ATTR_ANGULAR).Get()))
        self.assertEqual((-0.5, 0.0, 0.0), conveyor.readback())
        self.assertTrue(conveyor.running)
        conveyor.stop()
        self.assertEqual((0.0, 0.0, 0.0), conveyor.readback())
        self.assertEqual((0.0, 0.0, 0.0), tuple(terminal.GetAttribute(hconv.ATTR_ANGULAR).Get()))
        self.assertFalse(conveyor.running)

    def test_tracks_and_terminal_are_world_boxes(self):
        stage = self.build()
        conveyor = hconv.HospitalConveyor(stage, self.ROOT, self.TABLE)
        conveyor.discover()
        terminal = conveyor.terminal_surface()
        self.assertAlmostEqual(0.37 + 0.029 / 2, terminal["max"][2], places=5)
        self.assertEqual(2, len(conveyor.tracks()))
        model = belt.RouteBeltModel(conveyor.tracks(), terminal, hconv.TERMINAL_DIRECTION, (0.10, 0.07, 0.01),
                                    z_band="span", on_belt_height=0.10)
        self.assertTrue(model.on_belt(belt.route_point((-9.8, 9.0, 0.93))))

    def test_untargeted_body_is_refused_before_any_change(self):
        stage = self.build(target_all=False)
        conveyor = hconv.HospitalConveyor(stage, self.ROOT, self.TABLE)
        with self.assertRaisesRegex(ValueError, "가리키지 않는"):
            conveyor.discover()
        prim = stage.GetPrimAtPath(f"{self.ROOT}/ConveyorTrack_06/Belt")
        self.assertNotIn(hconv.SURFACE_API, self.api_schemas(prim))
        self.assertFalse(stage.GetAttributeAtPath(
            f"{self.ROOT}/ConveyorTrack_02/Sorter/ActionGraph/reroute.inputs:value").Get())

    def test_thick_or_missing_terminal_is_refused(self):
        with self.assertRaisesRegex(ValueError, "얇은 수평면"):
            hconv.HospitalConveyor(self.build(terminal_height=0.2), self.ROOT, self.TABLE).discover()
        with self.assertRaisesRegex(ValueError, "루트가 없다"):
            hconv.HospitalConveyor(self.build(), "/World/Nope", self.TABLE).discover()
        with self.assertRaises(RuntimeError):
            hconv.HospitalConveyor(self.build(), self.ROOT, self.TABLE).run()


if __name__ == "__main__":
    unittest.main()


class TerminalRollerHold(unittest.TestCase):
    """작전 결정 9/23 (다): 끝 롤러는 돌리고, 봉투 앞 끝이 출구 0.15 m 안이면 그 몸체만 0, 다음 배출에 놓는다.

    39fc30b(늘 돌림): 출구 밖으로 밀렸다. c482ac0(늘 0): 입구 y 5.9075 에 섰다.
    """

    def test_terminal_roller_runs_at_the_measured_speed(self):
        import json

        data = json.loads((STANDALONE / "p3sim" / "hospital_conveyor_surfaces.json").read_text(encoding="utf-8"))
        self.assertEqual(data["surface_velocities"]["/World/Conveyor/ConveyorTrack_02/Rollers_01"]["linear"],
                         [-0.5, 0, 0])
        self.assertIn("hold_terminal", data["_terminal"])

    def test_stage_holds_near_the_exit_and_releases_on_dispense(self):
        source = (STANDALONE / "pharmacy_stage.py").read_text(encoding="utf-8")
        self.assertIn("HOSPITAL_TERMINAL_HOLD_MARGIN = 0.15", source)
        self.assertIn("conveyor.hold_terminal()", source)
        self.assertIn("hospital_conveyor terminal released (dispense)", source)
        self.assertIn("edge_margin=HOSPITAL_TERMINAL_EDGE_MARGIN", source)


