"""도크 충전 스테이션 표시(재범 채택 9/24, `hospital_decor.charging_plan`)의 순수 부분과 usd-core 빌드.

오프라인 확인만 한다. Isaac 렌더(보이는가, 깜빡이는가)는 L3 미실행 — 정지 캡처가 본다.
"""

import json
import math
import struct
import sys
import unittest
from pathlib import Path

STANDALONE = Path(__file__).resolve().parents[1] / "standalone"
REPO = STANDALONE.parents[1]
sys.path.insert(0, str(STANDALONE))
from p3sim import hospital_decor as D  # noqa: E402
from p3sim import hospital_nav as hn  # noqa: E402
from p3sim import hospital_zones  # noqa: E402

ATLAS = REPO / "sim" / "assets" / "decor" / "charging.json"
ZONES = REPO / "src" / "rokey_p3_description" / "config" / "zones.hospital.yaml"
ANCHORS = REPO / "sim" / "scenes" / "hospital_navigationv1.anchors.json"


def plan():
    zones = hospital_zones.zones_from_yaml(ZONES)
    uv = json.loads(ATLAS.read_text(encoding="utf-8"))["uv"]
    tables = json.loads(ANCHORS.read_text(encoding="utf-8"))["outlets"]
    return zones, D.charging_plan(zones, uv, tables, hn.BODY_LENGTH, hn.BODY_WIDTH)


def normal(quad):
    a, b, c = quad[0], quad[1], quad[2]
    e1 = [b[i] - a[i] for i in range(3)]
    e2 = [c[i] - a[i] for i in range(3)]
    n = (e1[1] * e2[2] - e1[2] * e2[1], e1[2] * e2[0] - e1[0] * e2[2], e1[0] * e2[1] - e1[1] * e2[0])
    length = math.sqrt(sum(v * v for v in n))
    return tuple(v / length for v in n)


class ChargingPlan(unittest.TestCase):
    """재범 9/25 02:5x: 벽에 붙인다 — 도크 모듈(보조 테이블) 옆 벽면, 바닥 칸은 벽 밑선부터 정차 자리까지."""

    @classmethod
    def setUpClass(cls):
        cls.zones, (cls.items, cls.skipped) = plan()
        cls.by_name = {name: (quad, uv) for name, quad, uv in cls.items}
        cls.tables = json.loads(ANCHORS.read_text(encoding="utf-8"))["outlets"]

    def test_every_dock_gets_sign_edges_fill_and_bolt(self):  # noqa: D102
        self.assertEqual(self.skipped, [])
        self.assertEqual(len(self.items), 4 * 7)
        for zone, _text in D.CHARGING_DOCKS:
            for name in ("sign", "edge_bottom", "edge_right", "edge_top", "edge_left", "fill", "floor"):
                self.assertIn(f"{name}_{zone}", self.by_name)
            self.assertNotIn(f"post_{zone}", self.by_name)             # 기둥은 없다

    def test_atlas_matches_the_cells_and_the_budget(self):
        data = json.loads(ATLAS.read_text(encoding="utf-8"))
        self.assertEqual(list(data["uv"]), list(D.CHARGING_CELLS))
        raw = (ATLAS.parent / data["image"]).read_bytes()[:33]
        width, height, _bits, color = struct.unpack(">IIBB", raw[16:26])
        self.assertLessEqual(max(width, height), 1024)
        self.assertEqual(color, 2)

    def test_sign_sits_on_the_wall_face_left_of_the_dock_module(self):
        """창벽 앞면 실측 y 5.350(마클1 9/25). 판 앞면은 그 5 mm 앞, 도크 정면. 9/29 부터 도크 넷 다 모듈 왼쪽이다."""
        for zone, text in D.CHARGING_DOCKS:
            sign, _uv = self.by_name[f"sign_{zone}"]
            for p in sign:                                             # 도크 yaw 가 −1.571(≠ −π/2)이라 0.05 mm 흔들린다
                self.assertAlmostEqual(p[1], D.WALL_FRONT_Y, places=3)
            gap = D.WALL_FACE_MEASURED_Y - D.WALL_FRONT_Y
            self.assertTrue(0.0 < gap <= 0.01)                         # 벽 앞 1 cm 안(뜨지도 묻히지도 않게)
            table = self.tables[text]["shelf"]
            self.assertLess(max(p[0] for p in sign), table["min"][0])  # 모듈 왼쪽
            self.assertAlmostEqual(sum(p[0] for p in sign) / 4, self.zones[zone][0], places=6)
            self.assertAlmostEqual(sum(p[2] for p in sign) / 4, D.SIGN_CENTRE_Z)
            n = normal(sign)
            self.assertAlmostEqual(n[1], -1.0, places=4)               # 방 쪽을 본다

    def test_sign_edges_reach_into_the_wall_so_it_looks_mounted(self):
        for zone, _text in D.CHARGING_DOCKS:
            for side in ("bottom", "right", "top", "left"):
                edge, _uv = self.by_name[f"edge_{side}_{zone}"]
                ys = [p[1] for p in edge]
                self.assertAlmostEqual(min(ys), D.WALL_FRONT_Y, places=3)
                self.assertGreater(max(ys), D.WALL_FACE_MEASURED_Y + 0.03)   # 벽 속까지

    def test_floor_bay_runs_from_the_wall_line_over_the_stop(self):
        """재범 9/25: 도크 넷이 같은 모양 — 벽 밑선부터 차체 앞 끝까지 짙은 칸 한 장, ⚡A# 판은 벽 쪽."""
        for zone, text in D.CHARGING_DOCKS:
            x, y, _z, yaw = self.zones[zone]
            fill, uv = self.by_name[f"fill_{zone}"]
            rect = D.charging_bay_rect((x, y, yaw), hn.BODY_LENGTH, hn.BODY_WIDTH)
            self.assertAlmostEqual(max(p[1] for p in fill), D.FLOOR_WALL_Y)        # 뒷변 = 벽 밑선
            self.assertLess(min(p[1] for p in fill), y - hn.BODY_LENGTH / 2.0)    # 앞변이 차체 앞 끝을 덮는다
            self.assertEqual(tuple(round(v, 6) for v in (min(p[0] for p in fill), min(p[1] for p in fill))),
                             tuple(round(v, 6) for v in rect[:2]))
            self.assertEqual(uv, D.dark_uv(json.loads(ATLAS.read_text(encoding="utf-8"))["uv"]))
            plate, plate_uv = self.by_name[f"floor_{zone}"]
            self.assertEqual(plate_uv, tuple(json.loads(ATLAS.read_text(encoding="utf-8"))["uv"][text]))
            centre = (sum(p[0] for p in plate) / 4, sum(p[1] for p in plate) / 4)
            self.assertAlmostEqual(centre[0], x)
            self.assertGreater(centre[1], (rect[1] + rect[3]) / 2.0 - 0.1)       # 칸의 벽 쪽
            self.assertTrue(D.LIFT_BAY < D.LIFT_FILL < D.LIFT_MARK < D.LIFT_LABEL)
            self.assertAlmostEqual(normal(fill)[2], 1.0)
            self.assertAlmostEqual(normal(plate)[2], 1.0)

    def test_dock_bays_share_one_shape(self):
        """도크 칸 넷의 크기가 같다(통일). 9/29 부터 넷 다 모듈 왼쪽 같은 상대 자리다."""
        sizes = set()
        for zone, _text in D.CHARGING_DOCKS:
            x0, y0, x1, y1 = D.charging_bay_rect(self.zones[zone][:2] + (self.zones[zone][3],),
                                                 hn.BODY_LENGTH, hn.BODY_WIDTH)
            sizes.add((round(x1 - x0, 3), round(y1 - y0, 3)))
        self.assertEqual(len(sizes), 1)

    def test_decor_draws_the_charging_ring_for_every_dock(self):
        routes = D.parse_routes_text((REPO / "src" / "rokey_p3_description" / "config" /
                                      "routes.hospital.yaml").read_text(encoding="utf-8"))
        atlas = json.loads((REPO / "sim" / "assets" / "decor" / "labels.json").read_text(encoding="utf-8"))["uv"]
        decor = D.plan(routes, self.zones, hn.load_map(), hn.BODY_LENGTH, hn.BODY_WIDTH, atlas)
        names = {name for name, *_rest in decor["strips"]}
        for zone, _text in D.CHARGING_DOCKS:
            self.assertIn(f"bay_{zone}", names)
            self.assertNotIn(zone, [m[0] for m in decor["merged"]])

    def test_sign_stays_above_the_lidar_band(self):
        for zone, _text in D.CHARGING_DOCKS:
            sign, _uv = self.by_name[f"sign_{zone}"]
            self.assertGreater(min(p[2] for p in sign), 0.6)

    def test_nothing_in_the_pharmacy_workcell(self):
        for _name, quad, _uv in self.items:
            self.assertFalse(any(D.in_keep_out(p[0], p[1]) for p in quad))

    def test_sign_text_reads_left_to_right_from_the_room(self):
        for zone, _text in D.CHARGING_DOCKS:
            sign, _uv = self.by_name[f"sign_{zone}"]
            self.assertGreater(sign[1][0] - sign[0][0], 0.0)           # 방에서 벽을 보면 오른쪽 = +x


class ChargingUsd(unittest.TestCase):
    def test_one_mesh_one_material_no_physics(self):
        try:
            from pxr import Usd, UsdGeom, UsdShade
        except ImportError:
            raise unittest.SkipTest("usd-core 없음") from None
        _zones, (items, skipped) = plan()
        stage = Usd.Stage.CreateInMemory()
        count = D.build_charging(stage, "/World/Charging", items, skipped, ATLAS.with_name("charging.png"),
                                 log=lambda _line: None)
        self.assertEqual(count, 28)
        prims = list(Usd.PrimRange(stage.GetPrimAtPath("/World/Charging")))
        self.assertEqual(sum(p.IsA(UsdGeom.Mesh) for p in prims), 1)
        self.assertEqual(sum(p.IsA(UsdShade.Material) for p in prims), 1)
        for prim in prims:
            applied = " ".join(prim.GetAppliedSchemas())
            self.assertNotIn("Physics", applied, prim.GetPath())
        mesh = UsdGeom.Mesh(stage.GetPrimAtPath("/World/Charging/ChargingMarks"))
        self.assertEqual(len(mesh.GetPointsAttr().Get()), 112)
        self.assertEqual(len(mesh.GetFaceVertexCountsAttr().Get()), 28)


if __name__ == "__main__":
    unittest.main()
