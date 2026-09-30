"""Hospital demo cameras (`p3sim/views.py` HOSPITAL_VIEWS): framing and sight lines, checked offline. No Isaac, no YAML.

#567 촬영 계획, 작전 9/23 결정 (가): one floor_top take of the full lap plus close-ups (conveyor_a1, a1_pick, bed_a1)
from other runs at the same SHA. The subjects come from the zone generator (`hospital_nav.zone_poses`, the source of
zones.hospital.yaml) and from the conveyor reference probe 02 path (#240 5790540704).

What it cannot see: the occupancy map is render geometry projected over z 0.10-1.80 (`maps/hospital.yaml`) with no
heights, so a ceiling, anything above 1.8 m, and a low object under a high sight line are out of reach. Those are for
the first capture on master02.

    python3 -m unittest discover -s sim/tests -p 'test_hospital_views.py'
"""

import json
import math
import sys
import unittest
from pathlib import Path

STANDALONE = Path(__file__).resolve().parents[1] / "standalone"
sys.path.insert(0, str(STANDALONE))

from p3sim import base_scene, hospital_zones, patient_plates, truth_sensors  # noqa: E402
from p3sim import hospital_nav as hn  # noqa: E402
from p3sim import views  # noqa: E402

REPO = STANDALONE.parents[1]
#: 병원 워크셀(선반 9개·레일·투입구). 조제실 뷰의 대상은 여기서 온다.
WORKCELL = json.loads((REPO / "experiments" / "fixtures" / "hospital-integrated-09" / "workcell.json").read_text())
#: M0609 팔 위 끝(홈 자세, 레일 받침 포함) 어림.
M0609_TOP = 1.45


def pharmacy_to_hospital(x, y, z):
    """약국(layout_v2) 좌표 → 병원 좌표. 약국 원점은 yaw 0 이라 평행이동뿐이다."""
    ox, oy, _oz, _yaw = base_scene.HOSPITAL_ORIGIN_A
    return (x + ox, y + oy, z)

# Conveyor reference probe 02 (#240 5790540704): where the pouch settled on the A1 roller end, and the path points on
# the corridor side before it (22.75 s turn, 25.05 s, 29.35 s). Surface heights are the probe's settled z.
A1_ROLLER_END = (*hn.A1_SETTLED_XY, 0.39)   # 잰 정착 자리(hospital_nav 가 단일 출처)
CONVEYOR_LAST_STRETCH = ((-9.763, 6.62, 0.41), (-9.368, 6.23, 0.41), (-8.314, 6.17, 0.41))
#: 간호스테이션 B(작전 9/24): 테이블 SM_SideTable_02a4_01 상판 네 모서리, 놓는 점, 합본 정차 (x, y, yaw).
STATION_B_TABLE = tuple((x, y, 0.587) for x in (9.39, 10.48) for y in (3.34, 4.16))
STATION_B_PLACE = (9.934, 3.958, 0.587)
STATION_B_STOP = (9.584, 4.660, math.pi)
ARM_TOP = 1.4  # the UR5 above the deck, as in test_pharmacy_view_ur5
BODY_HALF = hn.BODY_LENGTH / 2
SIGHT_BAND = (1.0, 1.8)  # walls and tall shelves; conveyors, beds and tables stay under 1.0 m
EYE_MARGIN = 0.3


def body_points(pose, low=0.3):
    x, y, yaw = pose
    ends = [(x + s * BODY_HALF * math.cos(yaw), y + s * BODY_HALF * math.sin(yaw), low) for s in (-1, 1)]
    return [(x, y, low), (x, y, ARM_TOP)] + ends


class HospitalViews(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.grid = hn.load_map()
        poses = hn.zone_poses(cls.grid, hn.load_anchors())
        cls.pose = {name: poses[name]["pose"] for name in ("load", "dock_1", "dock_4", "station_a", "bed_a1")}
        cls.all_pose = {name: poses[name]["pose"]
                        for name in ("load", "dock_1", "dock_2", "dock_3", "dock_4", "station_a", "bed_a1")}
        cabinet = poses["bed_a1"]["cabinet"]
        cls.subjects = {
            # the pick happens at load (beside the roller end, yaw 0), not at dock_1
            "conveyor_a1": [A1_ROLLER_END, *CONVEYOR_LAST_STRETCH, *body_points(cls.pose["load"])[:2]],
            "a1_pick": [A1_ROLLER_END, *body_points(cls.pose["load"])],
            # 한 바퀴가 도는 자리 전부 + A1 끝. 이 목록이 floor_top 자세를 정한 근거다(views.py 주석).
            "floor_top": [(p[0], p[1], 0.0) for p in cls.all_pose.values() if p] + [A1_ROLLER_END],
            "bed_a1": [tuple(cabinet), *body_points(cls.pose["bed_a1"])],
            # 간호스테이션 B 테이블 네 모서리(상판)·놓는 점·정차한 합본(작전 9/24 좌표)
            "station_b": [*STATION_B_TABLE, STATION_B_PLACE, *body_points(STATION_B_STOP)],
            # 조제실 안. 대상은 지도가 아니라 워크셀 기하(layout_v2)에서 온다.
            "m0609_shelf": cls.shelf_points(),
            "m0609_dispenser": cls.dispenser_points(),
            "m0609_overhead": cls.overhead_points(),
        }

    @classmethod
    def shelf_points(cls):
        """홈의 M0609(바닥·팔 위), 가까운 선반 셋(68–70)의 칸 앞면 바닥·윗면, 선반 앞 작업점. 병원 워크셀 기준."""
        home = WORKCELL["rail"]["origin"]
        points = [(home[0], home[1], 0.0), (home[0], home[1], M0609_TOP), (home[0], 11.35, 0.95)]
        for cell_id, cell in WORKCELL["cells"].items():
            if cell_id.split("/")[0] in ("shelf_68", "shelf_69", "shelf_70"):
                x, y, z = cell["surface"]
                points += [(x, y - 0.05, z), (x, y - 0.05, z + cell["height"])]
        return points

    @classmethod
    def dispenser_points(cls):
        """원통 투입구·모듈 구멍과 그 위 0.25 m(넣기 직전 손 높이), 넣는 자리의 M0609(바닥·팔 위)."""
        targets = WORKCELL["targets"]
        hole = tuple(targets["module"]["entry_center"])
        base = (-7.75, 10.62)       # 원형 넣기 레일 후보 뒤 0.40(scene_v2.DEFAULT_PARAMS.rail_round)
        return [tuple(targets["round"]["center"]), hole, (hole[0], hole[1], hole[2] + 0.25),
                (base[0], base[1], 0.0), (base[0], base[1], M0609_TOP)]

    @classmethod
    def overhead_points(cls):
        """레일 양 끝(받침 높이), 선반 9개 칸 앞면 바닥·윗면, 투입구·모듈 구멍, 벨트 시작, 홈의 M0609 팔 위."""
        rail = WORKCELL["rail"]
        x0, y0, _z0 = rail["origin"]
        half = rail["x_stroke"] / 2.0
        points = [(x0 - half, y0, rail["carriage_height"]), (x0 + half, y0, rail["carriage_height"]),
                  (x0, y0, M0609_TOP), tuple(WORKCELL["belt"]["start"]),
                  tuple(WORKCELL["targets"]["round"]["center"]), tuple(WORKCELL["targets"]["module"]["entry_center"])]
        for cell in WORKCELL["cells"].values():
            x, y, z = cell["surface"]
            points += [(x, y - 0.05, z), (x, y - 0.05, z + cell["height"])]
        # 선반 틀 양 끝의 바닥·꼭대기(16d170e 캡처: 칸만 보다가 동쪽 틀 위가 화면 밖이었다)
        boards = [o for o in WORKCELL["obstacles"] if o["name"].startswith("Shelf")]
        ends = [o["center"][0] + side * o["size"][0] / 2 for o in boards for side in (-1, 1)]
        top = max(o["center"][2] + o["size"][2] / 2 for o in boards)
        front = min(o["center"][1] - o["size"][1] / 2 for o in boards)
        points += [(x, front, z) for x in (min(ends), max(ends)) for z in (0.0, top)]
        return points

    def test_names_are_apart_from_the_pharmacy_views(self):
        """Not --view choices of the pharmacy scenes: views.view(scene, name) would not know them."""
        self.assertEqual(set(views.HOSPITAL_VIEW_NAMES), set(self.subjects))
        self.assertFalse(set(views.HOSPITAL_VIEW_NAMES) & set(views.ALL_VIEW_NAMES))
        for name in views.HOSPITAL_VIEW_NAMES:
            self.assertEqual(views.hospital_view(name), views.HOSPITAL_VIEWS[name])

    def test_every_subject_is_in_frame_at_both_aspects(self):
        for name, points in self.subjects.items():
            eye, target = views.hospital_view(name)
            for point in points:
                for aspect in (views.ASPECT, views.HALF_SCREEN_ASPECT):  # full screen 16:9, 재범 half screen
                    with self.subTest(view=name, point=point, aspect=round(aspect, 2)):
                        self.assertTrue(views.in_frame(eye, target, point, aspect=aspect,
                                                       fov_deg=views.hospital_view_fov_deg(name)))

    def test_only_the_overhead_widens_the_lens_and_the_default_would_cut_it(self):
        """m0609_overhead 만 초점거리를 바꾼다. 기본 60° 로는 벨트 시작이 프레임 밖이라 넓힌 것이다(재범 9/27)."""
        self.assertEqual(set(views.HOSPITAL_VIEW_FOCAL_MM), {"m0609_overhead"})
        self.assertAlmostEqual(views.hospital_view_fov_deg("floor_top"), views.HORIZONTAL_FOV_DEG)
        wide = views.hospital_view_fov_deg("m0609_overhead")
        self.assertTrue(60.0 < wide < 75.0, wide)
        eye, target = views.hospital_view("m0609_overhead")
        self.assertFalse(all(views.in_frame(eye, target, p) for p in self.subjects["m0609_overhead"]))

    def test_the_wide_lens_is_written_to_the_session_layer(self):
        """Kit Perspective 의 값은 세션 레이어에 있다. 루트에 쓰면 가려진다(8eee260 뷰 랩: focal 18.1476 그대로)."""
        source = (STANDALONE / "pharmacy_stage.py").read_text(encoding="utf-8")
        block = source[source.index("focal = views.HOSPITAL_VIEW_FOCAL_MM"):][:900]
        self.assertIn("Usd.EditContext(stage, stage.GetSessionLayer())", block)
        self.assertLess(block.index("Usd.EditContext"), block.index("GetFocalLengthAttr().Set"))

    def test_session_layer_opinion_wins_when_usd_is_here(self):
        """usd-core 가 있으면 그 이유 자체를 본다: 세션 의견 18.147 위에 루트로 쓰면 안 바뀌고, 세션에 쓰면 바뀐다."""
        try:
            from pxr import Usd, UsdGeom
        except ImportError:
            self.skipTest("usd-core 없음")
        stage = Usd.Stage.CreateInMemory()
        with Usd.EditContext(stage, stage.GetSessionLayer()):
            cam = UsdGeom.Camera.Define(stage, "/OmniverseKit_Persp")
            cam.CreateFocalLengthAttr(18.147)
        stage.GetRootLayer().ImportFromString('#usda 1.0\ndef Camera "OmniverseKit_Persp" {}')
        cam = UsdGeom.Camera(stage.GetPrimAtPath("/OmniverseKit_Persp"))
        cam.GetFocalLengthAttr().Set(15.5)
        self.assertAlmostEqual(cam.GetFocalLengthAttr().Get(), 18.147, places=3)
        with Usd.EditContext(stage, stage.GetSessionLayer()):
            cam.GetFocalLengthAttr().Set(15.5)
        self.assertAlmostEqual(cam.GetFocalLengthAttr().Get(), 15.5, places=3)

    def test_the_overhead_eye_stands_inside_the_pharmacy(self):
        """동벽(x 3.0)·남벽(y 6.2) 안쪽이다. 문(y 6.6–7.8) 밖 복도에서 보면 벽이 가린다."""
        eye, _target = views.hospital_view("m0609_overhead")
        self.assertLessEqual(eye[0], 3.0 - EYE_MARGIN + 1e-9)
        self.assertGreaterEqual(eye[1], 6.2 + EYE_MARGIN + 0.3 - 1e-9)
        self.assertTrue(self.grid.is_blocked(3.0, 9.0))      # 동벽이 지도에 있다
        self.assertTrue(self.grid.is_blocked(3.0, 11.0))

    def test_close_up_eyes_stand_on_free_floor(self):
        """An eye inside a bed or a wall shows its inside. A free cell under the eye (and 0.3 m around) keeps the
        close-ups out of mapped walls and furniture; floor_top stands above the building."""
        for name in ("conveyor_a1", "a1_pick", "bed_a1", "station_b"):
            eye, _ = views.hospital_view(name)
            self.assertGreater(eye[2], 0.5, name)
            for dx in (-EYE_MARGIN, 0.0, EYE_MARGIN):
                for dy in (-EYE_MARGIN, 0.0, EYE_MARGIN):
                    self.assertFalse(self.grid.is_blocked(eye[0] + dx, eye[1] + dy), f"{name} eye over an obstacle")

    def test_no_sight_line_crosses_a_tall_obstacle(self):
        low, high = SIGHT_BAND
        for name, points in self.subjects.items():
            if name in views.HOSPITAL_PHARMACY_VIEW_NAMES:
                continue      # 지도는 우리가 세운 워크셀을 모른다(views.py 주석). 캡처가 본다
            eye, target = views.hospital_view(name)
            for point in [*points, target]:
                for k in range(1, 200):
                    q = tuple(e + (p - e) * k / 200 for e, p in zip(eye, point, strict=True))
                    if low < q[2] < high:
                        self.assertFalse(self.grid.is_blocked(q[0], q[1]), f"{name} sight to {point} at {q}")

    def test_the_pick_camera_sees_the_roller_end_past_the_body(self):
        """The AMR stands between a careless camera and the roller end. The sight line may cross the body only well
        above its deck (0.8 m), where the arm is, not the tray walls."""
        eye, _ = views.hospital_view("a1_pick")
        x, y, yaw = self.pose["load"]
        half_w = hn.BODY_WIDTH / 2
        for k in range(1, 400):
            q = tuple(e + (p - e) * k / 400 for e, p in zip(eye, A1_ROLLER_END, strict=True))
            along = (q[0] - x) * math.cos(yaw) + (q[1] - y) * math.sin(yaw)
            across = -(q[0] - x) * math.sin(yaw) + (q[1] - y) * math.cos(yaw)
            if abs(along) <= BODY_HALF and abs(across) <= half_w:
                self.assertGreater(q[2], 0.8, f"sight to the roller end crosses the body at {q}")

    def test_the_station_camera_sees_the_place_point_over_the_body(self):
        """차체 뒤에서 본다. 놓는 점까지의 시선은 상판(0.8 m) 위 — 팔이 있는 높이 — 로만 차체를 지난다."""
        eye, _ = views.hospital_view("station_b")
        x, y, yaw = STATION_B_STOP
        half_w = hn.BODY_WIDTH / 2
        self.assertGreater(math.hypot(eye[0] - x, eye[1] - y), 1.5)
        for k in range(1, 400):
            q = tuple(e + (p - e) * k / 400 for e, p in zip(eye, STATION_B_PLACE, strict=True))
            along = (q[0] - x) * math.cos(yaw) + (q[1] - y) * math.sin(yaw)
            across = -(q[0] - x) * math.sin(yaw) + (q[1] - y) * math.cos(yaw)
            if abs(along) <= BODY_HALF and abs(across) <= half_w:
                self.assertGreater(q[2], 0.8, f"sight to the place point crosses the body at {q}")

    def test_the_bed_camera_shows_the_patient_plate(self):
        """발표 #611: 협탁 보관함·팔·인식표가 한 화면. 인식표 판(비전 77239a9)이 생겨 이제 잴 수 있다.

        판은 협탁 위 0.1 m 짜리라 손으로 "보일 것" 이라고 두면 협탁 뷰가 조금만 움직여도 조용히 빠진다.
        bed_a1 뷰를 손대지 않기로 한 결정(발표·작전 9/23)이 맞는지를 이 시험이 지킨다.
        """
        zones = hospital_zones.zones_from_yaml(REPO / "src" / "rokey_p3_description" / "config" / "zones.hospital.yaml")
        sizes = hn.cabinet_sizes(hn.load_anchors())
        patients = truth_sensors.bed_patients(
            (REPO / "src" / "rokey_p3_orchestrator" / "config" / "order_pool.hospital.yaml").read_text())
        plate = next(p for p in patient_plates.plates(zones, sizes, patients) if p["bed"] == "bed_a1")
        point = (plate["center"][0], plate["center"][1], plate["top"])
        eye, target = views.hospital_view("bed_a1")
        for aspect in (views.ASPECT, views.HALF_SCREEN_ASPECT):
            with self.subTest(aspect=round(aspect, 2)):
                self.assertTrue(views.in_frame(eye, target, point, aspect=aspect))

    def test_the_bed_camera_stays_off_the_robot(self):
        eye, _ = views.hospital_view("bed_a1")
        x, y, _ = self.pose["bed_a1"]
        self.assertGreater(math.hypot(eye[0] - x, eye[1] - y), 1.5)

    def test_the_pharmacy_cameras_are_named_as_exempt_from_the_map(self):
        """지도 검사에서 빼는 것은 결정이다. 이름을 적어 두고, 그 이름이 실제 뷰여야 한다."""
        self.assertEqual(set(views.HOSPITAL_PHARMACY_VIEW_NAMES), {"m0609_shelf", "m0609_dispenser", "m0609_overhead"})
        for name in views.HOSPITAL_PHARMACY_VIEW_NAMES:
            self.assertIn(name, views.HOSPITAL_VIEWS)
        # 빼는 이유가 실재하는지 본다: 지도는 선반 앞을 막힘으로 안다(거기 우리 선반이 서 있다).
        self.assertTrue(self.grid.is_blocked(*pharmacy_to_hospital(-0.65, 0.91, 0.0)[:2]))

    def test_the_pharmacy_cameras_stand_in_front_of_what_they_watch(self):
        """선반·투입구는 -y 로 열린다. 눈이 그 뒤에 서면 뒤통수를 찍는다."""
        for name in views.HOSPITAL_PHARMACY_VIEW_NAMES:
            eye, _target = views.hospital_view(name)
            for point in self.subjects[name]:
                self.assertLess(eye[1], point[1] + 1e-9, f"{name} eye behind {point}")

    def test_floor_top_is_tilted(self):
        """Looking straight down leaves the camera's up vector undefined (z up), so the view leans a little."""
        eye, target = views.hospital_view("floor_top")
        run = math.hypot(target[0] - eye[0], target[1] - eye[1])
        self.assertGreater(math.degrees(math.atan2(run, eye[2] - target[2])), 5.0)


if __name__ == "__main__":
    unittest.main()


class ChaseCamera(unittest.TestCase):
    """`--view amr_chase`: 차체를 따라가는 카메라(발표 #611, 작전 9/23 뒤 2.5 m·위 1.6 m)."""

    def test_it_is_not_a_fixed_pose(self):
        """정해진 자세가 없으니 HOSPITAL_VIEWS 에 있으면 안 된다 — 있으면 낡은 값을 찍는다."""
        for name in views.HOSPITAL_FOLLOW_VIEW_NAMES:
            self.assertNotIn(name, views.HOSPITAL_VIEWS)
        self.assertEqual(("amr_chase",), views.HOSPITAL_FOLLOW_VIEW_NAMES)

    def test_the_eye_sits_behind_and_above_the_body(self):
        for yaw in (0.0, math.pi / 2, -math.pi / 2, math.pi, 2.3):
            eye, target = views.chase_pose(10.0, 5.0, yaw)
            forward = (math.cos(yaw), math.sin(yaw))
            behind = (eye[0] - 10.0) * forward[0] + (eye[1] - 5.0) * forward[1]
            self.assertAlmostEqual(behind, -views.CHASE_BACK_M, places=6)
            self.assertAlmostEqual(eye[2], views.CHASE_UP_M, places=6)
            # 옆으로 새지 않는다: 눈은 진행 축 위에 있다.
            across = -(eye[0] - 10.0) * forward[1] + (eye[1] - 5.0) * forward[0]
            self.assertAlmostEqual(across, 0.0, places=6)
            # 보는 곳은 차체 **앞**이다. 한가운데를 보면 화면 절반이 상판 뚜껑이다.
            ahead = (target[0] - 10.0) * forward[0] + (target[1] - 5.0) * forward[1]
            self.assertAlmostEqual(ahead, views.CHASE_AHEAD_M, places=6)

    def test_the_body_and_the_road_ahead_are_both_in_frame(self):
        """차체 위(팔 높이)와 앞쪽 바닥이 16:9·반쪽 둘 다에 들어와야 쓸모가 있다."""
        for yaw in (0.0, math.pi / 2, -2.0):
            eye, target = views.chase_pose(10.0, 5.0, yaw)
            forward = (math.cos(yaw), math.sin(yaw))
            points = [(10.0, 5.0, 0.3), (10.0, 5.0, ARM_TOP),
                      (10.0 + forward[0] * 3.0, 5.0 + forward[1] * 3.0, 0.0)]
            for point in points:
                for aspect in (views.ASPECT, views.HALF_SCREEN_ASPECT):
                    with self.subTest(yaw=round(yaw, 2), point=point, aspect=round(aspect, 2)):
                        self.assertTrue(views.in_frame(eye, target, point, aspect=aspect))
