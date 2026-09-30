"""M0609 셀 바닥 꾸밈(재범 9/25, `p3sim/workcell_decor.py`)의 순수 부분과 usd-core 빌드.

오프라인 확인: 판이 설비를 덮고 A1 롤러 끝·AMR 집기 자리를 안 덮는다, 전부 바닥 1.5 mm 안·층마다 다른 높이·
위를 본다, 글자가 조제실 촬영 뷰와 a1_pick 프레임 밖, 아틀라스 예산. Isaac 렌더는 L3 미실행.
"""

import json
import struct
import sys
import unittest
from pathlib import Path

STANDALONE = Path(__file__).resolve().parents[1] / "standalone"
REPO = STANDALONE.parents[1]
sys.path.insert(0, str(STANDALONE))
from p3sim import hospital_nav as hn  # noqa: E402
from p3sim import hospital_zones, views  # noqa: E402
from p3sim import workcell_decor as W  # noqa: E402

WORKCELL = REPO / "experiments" / "fixtures" / "hospital-integrated-09" / "workcell.json"
LABELS = REPO / "sim" / "assets" / "decor" / "workcell_labels.json"
ZONES = REPO / "src" / "rokey_p3_description" / "config" / "zones.hospital.yaml"


def plan():
    workcell = json.loads(WORKCELL.read_text(encoding="utf-8"))
    uv = json.loads(LABELS.read_text(encoding="utf-8"))["uv"]
    return workcell, W.plan(workcell, uv, views.HOSPITAL_VIEWS)


def inside(box, x, y):
    return box[0] <= x <= box[2] and box[1] <= y <= box[3]


class WorkcellFloor(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workcell, cls.decor = plan()
        cls.anchor = cls.decor["anchors"]
        cls.plate = cls.anchor["plate"]

    def test_plate_covers_rail_dispenser_front_and_belt_start(self):
        for key in ("rail_west", "rail_east", "belt_start", "belt_end", "dispenser_front", "panel"):
            self.assertTrue(inside(self.plate, *self.anchor[key]), key)
        dispenser = self.anchor["dispenser"]
        self.assertLessEqual(self.plate[1], dispenser[1])                   # 조제기 앞면까지
        self.assertAlmostEqual(self.plate[3], self.anchor["shelves"][1])   # 선반 앞면에서 멈춘다

    def test_a1_roller_end_and_amr_pick_spot_are_untouched(self):
        zones = hospital_zones.zones_from_yaml(ZONES)
        pharmacy = hospital_zones.pharmacy_frames_from_yaml(ZONES)
        belt_end = pharmacy["belt_end"]
        for x, y in ((belt_end[0], belt_end[1]), zones["load"][:2], zones["dock_1"][:2]):
            self.assertFalse(inside(self.plate, x, y))
            self.assertGreater(self.plate[1] - y, 2.0)                      # 워크셀 판 남쪽 끝보다 2 m 넘게 남쪽

    def test_plate_south_edge_is_on_free_floor_except_under_the_belt(self):
        """남쪽 끝이 벽 속이면 틀린 것이다. 벨트(x −9.82, 폭 약 0.5 m) 밑은 지도에 막힘으로 나오지만 벽이 아니다."""
        grid = hn.load_map()
        x0, y0, x1, _y1 = self.plate
        belt_x = self.anchor["belt_start"][0]
        for k in range(41):
            x = x0 + (x1 - x0) * k / 40
            if abs(x - belt_x) <= 0.30:
                continue
            self.assertFalse(grid.is_blocked(x, y0), (round(x, 2), y0))

    def test_everything_is_flat_under_the_lidar_and_faces_up(self):
        heights = set()
        for quad, _color in self.decor["faces"]:
            zs = {p[2] for p in quad}
            self.assertEqual(len(zs), 1)
            z = zs.pop()
            self.assertLess(z, 0.0015)
            heights.add(z)
            (ax, ay, _), (bx, by, _), (cx, cy, _) = quad[:3]
            self.assertGreater((bx - ax) * (cy - ay) - (by - ay) * (cx - ax), 0.0)   # 위에서 보면 반시계
        for _text, quad, _uv in self.decor["labels"]:
            self.assertLess(quad[0][2], 0.0015)
        self.assertEqual(heights, {W.LIFT_BASE, W.LIFT_BORDER, W.LIFT_TRENCH, W.LIFT_BOX})
        self.assertLess(W.LIFT_LABEL, 0.0010)                               # hospital_decor 유도선보다 아래

    def test_both_labels_stay_out_of_the_filming_views(self):
        self.assertEqual([t for t, _q, _uv in self.decor["labels"]], ["power", "data"])
        for text, quad, _uv in self.decor["labels"]:
            for name in W.PROTECTED_VIEWS:
                eye, target = views.hospital_view(name)
                for p in quad:
                    for aspect in (views.ASPECT, views.HALF_SCREEN_ASPECT):
                        self.assertFalse(views.in_frame(eye, target, p, margin=1.0, aspect=aspect), (text, name))
            self.assertTrue(all(inside(self.plate, p[0], p[1]) for p in quad), text)

    def test_trenches_run_on_the_plate_from_the_panel(self):
        for name, points in W.trench_routes(self.anchor):
            self.assertEqual(points[0][1], self.anchor["panel"][1], name)
            for x, y in points:
                self.assertTrue(inside(self.plate, x, y), (name, x, y))

    def test_hazard_border_alternates_yellow_and_black(self):
        stripes = W.border_stripes(self.plate)
        colors = [color for _quad, color in stripes]
        self.assertIn(W.YELLOW, colors)
        self.assertIn(W.STRIPE_BLACK, colors)
        self.assertGreater(len(stripes), 100)

    def test_label_atlas_is_small_and_opaque(self):
        data = json.loads(LABELS.read_text(encoding="utf-8"))
        raw = (LABELS.parent / data["image"]).read_bytes()[:33]
        width, height, _bits, color = struct.unpack(">IIBB", raw[16:26])
        self.assertLessEqual(max(width, height), 1024)
        self.assertEqual(color, 2)
        self.assertEqual(set(data["uv"]), {"power", "data"})


class WorkcellUsd(unittest.TestCase):
    def test_two_meshes_two_materials_no_physics(self):
        try:
            from pxr import Usd, UsdGeom, UsdShade
        except ImportError:
            raise unittest.SkipTest("usd-core 없음") from None
        _workcell, decor = plan()
        stage = Usd.Stage.CreateInMemory()
        W.build(stage, "/World/Workcell", decor, LABELS.with_name("workcell_labels.png"), log=lambda _line: None)
        prims = list(Usd.PrimRange(stage.GetPrimAtPath("/World/Workcell")))
        self.assertEqual(sum(p.IsA(UsdGeom.Mesh) for p in prims), 2)
        self.assertEqual(sum(p.IsA(UsdShade.Material) for p in prims), 2)
        for prim in prims:
            self.assertNotIn("Physics", " ".join(prim.GetAppliedSchemas()), prim.GetPath())


if __name__ == "__main__":
    unittest.main()
