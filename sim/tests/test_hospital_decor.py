"""병원 바닥 표시(`p3sim/hospital_decor.py`)의 순수 부분. Isaac 없이 돈다. Isaac 쪽(`build`)은 L3 미실행이다.

최적화 9/24 예산이 이 파일의 절반이다. 예산은 말로 두면 다음 사람이 모르고 넘는다 — 그래서 시험으로 묶는다.

    rtf −0.02 · 기동 +3 s · VRAM +0.3 GB 이내 (회차로 판정, 여기서는 못 본다)
    텍스처 긴 변 1024 이하, 합계 16 MB 이하, 알파 없음, 한 장
    재질은 적게, 복제 판은 낱개 메시로 만들지 않는다 → 메시 둘
    RTX 라이다는 시각 메시도 본다 → 바닥에서 1.5 mm 안에만
    M0609 손 카메라 시야(조제실 워크셀)에는 두지 않는다
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

ATLAS_DIR = REPO / "sim" / "assets" / "decor"
ZONES = REPO / "src" / "rokey_p3_description" / "config" / "zones.hospital.yaml"
ROUTES = REPO / "src" / "rokey_p3_description" / "config" / "routes.hospital.yaml"


def png_header(path):
    """(가로, 세로, 비트, 색 유형). PIL 없이 IHDR 만 읽는다. 색 유형 2 = RGB, 6 = RGBA."""
    data = path.read_bytes()[:33]
    assert data[:8] == b"\x89PNG\r\n\x1a\n", "PNG 가 아니다"
    width, height, bits, color = struct.unpack(">IIBB", data[16:26])
    return width, height, bits, color


def real_plan():
    """저장소의 zones·routes·지도·아틀라스로 만든 실제 배치. 시험들이 같은 것을 본다."""
    zones = hospital_zones.zones_from_yaml(ZONES)
    routes = D.parse_routes_text(ROUTES.read_text(encoding="utf-8"))
    grid = hn.load_map()
    atlas = json.loads((ATLAS_DIR / "labels.json").read_text(encoding="utf-8"))["uv"]
    return D.plan(routes, zones, grid, hn.BODY_LENGTH, hn.BODY_WIDTH, atlas), grid


def signed_area(points):
    return sum(points[i][0] * points[(i + 1) % len(points)][1] - points[(i + 1) % len(points)][0] * points[i][1]
               for i in range(len(points))) / 2.0


class Atlas(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.meta = json.loads((ATLAS_DIR / "labels.json").read_text(encoding="utf-8"))

    def test_every_label_the_floor_uses_is_in_the_atlas(self):
        """글자를 바꾸고 아틀라스를 다시 안 만들면 여기서 걸린다(`make_decor_atlas.py`)."""
        self.assertEqual(set(D.atlas_texts()), set(self.meta["uv"]))
        self.assertTrue({"B", "C1", "C2", "B 병동", "C 병실", "D 병상"} <= set(self.meta["uv"]))
        self.assertTrue({f"D{i}" for i in range(1, 11)} <= set(self.meta["uv"]))

    def test_it_is_one_small_opaque_image(self):
        width, height, bits, color = png_header(ATLAS_DIR / self.meta["image"])
        self.assertEqual((width, height), tuple(self.meta["size"]))
        self.assertLessEqual(max(width, height), 1024)            # 긴 변 1024 이하
        self.assertEqual(color, 2, "RGB 여야 한다 — 알파는 RTX 에서 비싸다")
        self.assertEqual(bits, 8)
        self.assertLess((ATLAS_DIR / self.meta["image"]).stat().st_size, 1024 * 1024)

    def test_cells_stay_inside_and_apart(self):
        rects = list(self.meta["uv"].values())
        for u0, v0, u1, v1 in rects:
            self.assertTrue(0.0 <= u0 < u1 <= 1.0 and 0.0 <= v0 < v1 <= 1.0)
        for i, a in enumerate(rects):
            for b in rects[i + 1:]:
                apart = a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1]
                self.assertTrue(apart, f"아틀라스 칸이 겹친다 {a} {b}")

    def test_cells_keep_the_plate_shape(self):
        """판 0.60 × 0.15 m 와 아틀라스 칸이 같은 비율이어야 글자가 눌리지 않는다."""
        w, h = self.meta["size"]
        for u0, v0, u1, v1 in self.meta["uv"].values():
            self.assertAlmostEqual(((u1 - u0) * w) / ((v1 - v0) * h), D.LABEL_SIZE[0] / D.LABEL_SIZE[1], delta=0.1)


class Plan(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan, cls.grid = real_plan()
        cls.lines = [s for s in cls.plan["strips"] if not s[0].startswith("bay_")]
        cls.bays = [s for s in cls.plan["strips"] if s[0].startswith("bay_")]

    def test_nothing_is_dropped_by_accident(self):
        """빠지는 것이 없다 — C 테이블(station_c·c2) zone 이 zones.hospital.yaml 에 들어와 초록 선·칸도 선다."""
        self.assertEqual([], self.plan["skipped"])
        self.assertEqual([s[0] for s in self.lines], ["ward_b", "bed_d1", "bed_d5", "station_c", "station_d"])
        zone_labels = [label for label in self.plan["labels"] if label[0] != "legend"]
        self.assertEqual(len(zone_labels), len(D.BAY_LABELS))  # 진 칸도 글자는 남긴다

    def test_the_bays_that_give_way_are_the_known_ones(self):
        """B3↔B6 은 같이 서지 않는 이웃 자리다. zones 가 바뀌어 새 겹침이 생기면 여기서 본다.

        도크를 벽 앞으로 옮긴 9/25 뒤로 적재↔도크 1 은 안 겹친다. 도크 넷은 충전 칸으로 통일해 겹쳐도 늘 그린다."""
        self.assertEqual(self.plan["merged"], [("bed_b6", "bed_b3")])
        self.assertEqual(len(self.bays), len(D.BAY_LABELS) - len(self.plan["merged"]))

    def test_everything_lies_flat_under_the_lidar_plane(self):
        """RTX 라이다는 시각 메시도 본다. 스캔 평면은 약 0.306 m — 바닥 1.5 mm 안이면 만날 수 없다."""
        heights = {p[2] for s in self.plan["strips"] for p in s[1]}
        heights |= {p[2] for label in self.plan["labels"] for p in label[2]}
        self.assertTrue(all(0.0 < z <= 0.0015 for z in heights), sorted(heights))

    def test_layers_never_share_a_height(self):
        """같은 높이 판이 겹치면 깜빡인다. 선 셋·칸·글자가 서로 다른 높이다."""
        layers = [*D.LIFT_LINES, D.LIFT_BAY, D.LIFT_LABEL]
        self.assertEqual(len(layers), len(set(layers)))
        self.assertEqual(layers, sorted(layers))                           # 글자가 맨 위

    def test_nothing_sits_in_the_pharmacy_workcell(self):
        """M0609 손 카메라 시야다(최적화 9/24)."""
        points = [p for s in self.plan["strips"] for p in s[1]] + [p for lab in self.plan["labels"] for p in lab[2]]
        self.assertFalse([p for p in points if D.in_keep_out(p[0], p[1])])

    def test_guide_lines_run_on_free_floor(self):
        """경로는 몸체 중심이 장애물에서 0.56 m 떨어진 선이다. 옆으로 0.06 m 띄워도 바닥 위여야 한다."""
        for name, points, *_ in self.lines:
            blocked = [p for p in points if self.grid.is_blocked(p[0], p[1])]
            self.assertEqual(blocked, [], name)

    def test_labels_are_on_free_floor_and_apart(self):
        quads = [label[2] for label in self.plan["labels"]]
        for zone, _text, quad, _uv in self.plan["labels"]:
            self.assertTrue(D.on_free_floor(self.grid, quad), zone)
        for i, a in enumerate(quads):
            for b in quads[i + 1:]:
                self.assertFalse(D.overlaps(a, b))

    def test_every_face_points_up(self):
        """위에서 보면 반시계여야 법선이 +z 다. 뒤집히면 한쪽 면만 그리는 판이 안 보인다."""
        for name, points, counts, indices, _color in self.plan["strips"]:
            k = 0
            for n in counts:
                face = [points[i] for i in indices[k:k + n]]
                k += n
                self.assertGreater(signed_area(face), 0.0, name)
        for zone, _text, quad, _uv in self.plan["labels"]:
            self.assertGreater(signed_area(quad), 0.0, zone)

    def test_label_text_reads_left_to_right_and_upright(self):
        """st 의 u 가 +x, v 가 +y — floor_top(남쪽에서 북쪽을 봄)에서 거울상이 아니다."""
        for _zone, _text, quad, _uv in self.plan["labels"]:
            self.assertGreater(quad[1][0], quad[0][0])
            self.assertGreater(quad[3][1], quad[0][1])

    def test_the_lines_from_load_run_side_by_side(self):
        """적재에서 같은 복도로 나가는 선들이 겹치면 깜빡이고 색이 섞인다. 나란히 띄우고 높이도 다르게 둔다."""
        offsets = sorted(D.LINE_OFFSETS.values())
        self.assertTrue(all(b - a > D.LINE_WIDTH for a, b in zip(offsets, offsets[1:], strict=False)))
        self.assertEqual(len({lift for *_rest, lift in D.GUIDE_LINES}), len(D.GUIDE_LINES))

    def test_colours_follow_the_destination_class(self):
        """재범 9/25 03:3x: B 병동 파랑, C 병실 초록, D 병상 노랑. 목적지가 아닌 자리는 주황."""
        colours = {name: color for name, _p, _c, _i, color in self.plan["strips"]}
        self.assertEqual(colours["ward_b"], D.BLUE)
        self.assertEqual(colours["bed_d1"], D.YELLOW)
        self.assertEqual(colours["bed_d5"], D.YELLOW)
        self.assertEqual(colours["bay_station_b"], D.BLUE)
        for zone in hn.BED_ZONE.values():
            if f"bay_{zone}" in colours:
                self.assertEqual(colours[f"bay_{zone}"], D.YELLOW, zone)
        for zone in ("dock_1", "dock_2"):
            self.assertEqual(colours[f"bay_{zone}"], D.OTHER_COLOR, zone)
        # 재범 9/25 컷 "A1 이 둘": 충전 표시 없는 적재 칸은 그리지 않는다(dock_1 충전 칸 하나만).
        self.assertNotIn("bay_load", colours)
        # 간호스테이션 칸은 B 하나다 — station_a(데스크 면) 칸은 없다(재범 9/25 오버헤드 컷 "B 칸이 둘").
        self.assertNotIn("bay_station_a", colours)
        stations = [name for name in colours if name.startswith("bay_station_")]
        self.assertEqual(["bay_station_b", "bay_station_c", "bay_station_d"], sorted(stations))
        self.assertEqual(D.label_style("C1")[0], D.GREEN)
        self.assertNotIn((1.0, 1.0, 1.0), [c for text in D.atlas_texts() for c in D.label_style(text)])

    def test_the_b_bay_is_the_real_station_b_stop(self):
        """B 칸은 zones 의 station_b 정차 자세(9.584, 4.660, 180°) 가운데다 — 짐작한 자리가 아니다."""
        zones = hospital_zones.zones_from_yaml(ZONES)
        x, y, _z, yaw = zones["station_b"]
        self.assertAlmostEqual(x, 9.584, places=3)
        self.assertAlmostEqual(y, 4.66, places=3)
        self.assertAlmostEqual(abs(yaw), math.pi, places=2)
        points = next(s[1] for s in self.plan["strips"] if s[0] == "bay_station_b")
        inner = points[4:]
        self.assertAlmostEqual(sum(p[0] for p in inner) / 4, x, places=6)
        self.assertAlmostEqual(sum(p[1] for p in inner) / 4, y, places=6)
        texts = {zone: text for zone, text, _q, _uv in self.plan["labels"]}
        self.assertEqual(texts["station_b"], "B")

    def test_beds_are_labelled_d1_to_d10(self):
        texts = {zone: text for zone, text, _q, _uv in self.plan["labels"]}
        for label, zone in hn.BED_ZONE.items():
            self.assertEqual(texts[zone], label)

    def test_legend_sits_in_the_lobby_on_free_floor_away_from_walkers(self):
        legend = [label for label in self.plan["labels"] if label[0] == "legend"]
        # 재범 9/25(도크 컷): 벽 모서리가 아니라 도크 열과 간호스테이션 사이 로비 가운데, 오버헤드 뷰 정방향(+15°).
        points = [p for _z, _t, quad, _uv in legend for p in quad]
        cx = sum(p[0] for p in points) / len(points)
        cy = sum(p[1] for p in points) / len(points)
        # 재범 9/25 컷에 짚은 자리: 복도 북쪽 계단 아래 로비 한가운데 (7.4, 7.2) 부근, 반듯하게(회전 없음).
        self.assertLess(math.hypot(cx - D.LEGEND_PREFERRED[0], cy - D.LEGEND_PREFERRED[1]), 0.5, (cx, cy))
        a, b = legend[0][2][0], legend[0][2][1]
        self.assertAlmostEqual(0.0, math.degrees(math.atan2(b[1] - a[1], b[0] - a[0])), places=6)
        self.assertEqual([text for _z, text, _q, _uv in legend], [text for text, _cls in D.LEGEND])
        for _zone, _text, quad, _uv in legend:
            self.assertTrue(D.on_free_floor(self.grid, quad))
            self.assertFalse([p for p in quad if D.in_keep_out(p[0], p[1])])
            for p in quad:
                for a, b in D.dummy_segments():
                    self.assertGreaterEqual(D._segment_distance(p[:2], a, b), D.LEGEND_CLEARANCE)
            x0, y0, x1, y1 = D.LEGEND_SEARCH
            self.assertTrue(all(x0 - 1 <= p[0] <= x1 + 1 and y0 - 1 <= p[1] <= y1 + 1 for p in quad))


class RoomTables(unittest.TestCase):
    """재범 9/25 오버헤드 컷: C 초록 칸·유도선이 병동 입구 복도 협탁 옆 **정차 자세**에.

    B 파랑 칸도 station_b 정차 자세에 있다."""

    def test_bays_and_line_ends_sit_on_the_real_stop_poses(self):
        zones = dict(hospital_zones.zones_from_yaml(ZONES))
        routes = D.parse_routes_text(ROUTES.read_text(encoding="utf-8"))
        atlas = json.loads((ATLAS_DIR / "labels.json").read_text(encoding="utf-8"))["uv"]
        plan = D.plan(routes, zones, hn.load_map(), hn.BODY_LENGTH, hn.BODY_WIDTH, atlas)
        strips = {name: (points, color) for name, points, _c, _i, color in plan["strips"]}
        for zone, line, colour in (("station_b", "ward_b", D.BLUE), ("station_c", "station_c", D.GREEN),
                                   ("station_d", "station_d", D.GREEN)):
            x, y = zones[zone][:2]
            ring, ring_colour = strips[f"bay_{zone}"]
            cx = sum(p[0] for p in ring[:4]) / 4
            cy = sum(p[1] for p in ring[:4]) / 4
            self.assertAlmostEqual(x, cx, places=3, msg=zone)
            self.assertAlmostEqual(y, cy, places=3, msg=zone)
            self.assertEqual(colour, ring_colour, zone)
            points, line_colour = strips[line]
            end = points[-1]
            # 선 다섯은 0.06 m 씩 나란히 띄운다(LINE_OFFSETS) — 끝은 정차 중심에서 그 오프셋 + 반폭 안, 곧 칸 안이다.
            self.assertLess(math.hypot(end[0] - x, end[1] - y), 0.2, f"{line} 끝 {end[:2]} ↔ {zone} ({x}, {y})")
            self.assertEqual(colour, line_colour, line)


class TableTints(unittest.TestCase):
    def test_b_blue_c_green_d_yellow(self):
        anchors = hn.load_anchors()
        tints = D.table_tints(anchors["bedside_tables"], ["/World/Fake/RoomC1"])
        self.assertEqual(tints[0], ("/World/Environment/hospital/SM_SideTable_02a4_01", D.BLUE))
        self.assertEqual(tints[1], ("/World/Fake/RoomC1", D.GREEN))
        d = [prim for prim, color in tints if color == D.YELLOW]
        self.assertEqual(d, [anchors["bedside_tables"][f"D{i}"]["prim"] for i in range(1, 11)])

    def test_binding_is_visual_only_and_stronger_than_descendants(self):
        try:
            from pxr import Usd, UsdGeom, UsdShade
        except ImportError:
            self.skipTest("usd-core 없음")
        stage = Usd.Stage.CreateInMemory()
        table = UsdGeom.Xform.Define(stage, D.STATION_B_TABLE_PRIM)
        UsdGeom.Cube.Define(stage, f"{D.STATION_B_TABLE_PRIM}/Top")
        lines = []
        painted = D.build_table_tints(stage, "/World/Decor", [(D.STATION_B_TABLE_PRIM, D.BLUE),
                                                              ("/World/Missing", D.YELLOW)], log=lines.append)
        self.assertEqual(painted, 1)
        binding = UsdShade.MaterialBindingAPI(table.GetPrim()).GetDirectBindingRel()
        self.assertEqual(UsdShade.MaterialBindingAPI.GetMaterialBindingStrength(binding),
                         UsdShade.Tokens.strongerThanDescendants)
        top_prim = stage.GetPrimAtPath(f"{D.STATION_B_TABLE_PRIM}/Top")
        top, _ = UsdShade.MaterialBindingAPI(top_prim).ComputeBoundMaterial()
        self.assertEqual(str(top.GetPath()), "/World/Decor/Looks/TableB")
        for prim in stage.Traverse():
            self.assertNotIn("Physics", " ".join(prim.GetAppliedSchemas()), str(prim.GetPath()))
        self.assertTrue(any("missing prims=['/World/Missing']" in line for line in lines))


class Geometry(unittest.TestCase):
    def test_offset_keeps_the_width_through_a_right_angle(self):
        """직각 모서리에서 미터 결합이 폭을 지킨다(안쪽 점이 대각선 √2 배로 들어간다)."""
        out = D.offset_polyline([(0.0, 0.0), (1.0, 0.0), (1.0, 1.0)], 0.1)
        self.assertAlmostEqual(out[0][1], 0.1)
        self.assertAlmostEqual(out[1][0], 0.9)
        self.assertAlmostEqual(out[1][1], 0.1)
        self.assertAlmostEqual(math.dist(out[1], (1.0, 0.0)), 0.1 * math.sqrt(2.0))

    def test_miter_is_clipped_at_a_hairpin(self):
        out = D.offset_polyline([(0.0, 0.0), (1.0, 0.0), (0.0, 0.01)], 0.1)
        self.assertLessEqual(math.dist(out[1], (1.0, 0.0)), 0.1 * D.MITER_LIMIT + 1e-9)

    def test_overlap_test(self):
        square = [(0, 0), (1, 0), (1, 1), (0, 1)]
        self.assertTrue(D.overlaps(square, [(0.5, 0.5), (1.5, 0.5), (1.5, 1.5), (0.5, 1.5)]))
        self.assertFalse(D.overlaps(square, [(2, 0), (3, 0), (3, 1), (2, 1)]))
        self.assertFalse(D.overlaps(square, [(1, 0), (2, 0), (2, 1), (1, 1)]))      # 닿기만 함

    def test_merge_keeps_each_part_its_own_vertices(self):
        a = ([(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)], [4], [0, 1, 2, 3])
        b = ([(5, 0, 0), (6, 0, 0), (6, 1, 0), (5, 1, 0)], [4], [0, 1, 2, 3])
        vertices, counts, indices = D.merge([a, b])
        self.assertEqual(len(vertices), 8)
        self.assertEqual(counts, [4, 4])
        self.assertEqual(indices, [0, 1, 2, 3, 4, 5, 6, 7])


if __name__ == "__main__":
    unittest.main()


class StageWiring(unittest.TestCase):
    """스테이지 쪽 배선. 재범 원칙: 적용하라고 한 기능은 기본을 켠 채로 둔다."""

    @classmethod
    def setUpClass(cls):
        import importlib.util
        spec = importlib.util.spec_from_file_location("pharmacy_stage_decor", STANDALONE / "pharmacy_stage.py")
        cls.stage = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.stage)

    def test_on_in_the_hospital_presets_and_off_elsewhere(self):
        for preset in ("hospital", "hospital-full"):
            self.assertTrue(self.stage.parse_args(["--preset", preset]).hospital_decor, preset)
        for preset in ("emptyworld-loop", "demo-ros-refill-v2", "hospital-v2"):
            self.assertFalse(self.stage.parse_args(["--preset", preset]).hospital_decor, preset)

    def test_it_can_be_turned_off_for_the_measurement_run(self):
        """최적화의 켬/끔 두 회차 비교: `P3_STAGE_ARGS=--no-hospital-decor`."""
        args = self.stage.parse_args(["--preset", "hospital", "--no-hospital-decor"])
        self.assertFalse(args.hospital_decor)

    def test_routes_come_from_beside_the_zones_file(self):
        self.assertEqual(self.stage.decor_routes_path(ZONES), ROUTES)
        self.assertTrue(self.stage.DECOR_ATLAS.is_file())


class BuildUsd(unittest.TestCase):
    """`build` 가 만드는 USD 를 usd-core 로 직접 본다. Isaac 렌더는 여기서 못 본다 — 그건 캡처가 본다."""

    @classmethod
    def setUpClass(cls):
        try:
            from pxr import Usd  # noqa: F401
        except ImportError:
            raise unittest.SkipTest("usd-core 없음") from None
        from pxr import Usd
        cls.stage = Usd.Stage.CreateInMemory()
        cls.plan, _grid = real_plan()
        cls.lines = []
        cls.counts = D.build(cls.stage, "/World/HospitalDecor", cls.plan,
                             ATLAS_DIR / "labels.png", log=cls.lines.append)

    def mesh(self, name):
        from pxr import UsdGeom
        prim = self.stage.GetPrimAtPath(f"/World/HospitalDecor/{name}")
        self.assertTrue(prim.IsValid(), name)
        return UsdGeom.Mesh(prim)

    def test_two_meshes_two_materials_one_texture(self):
        from pxr import UsdGeom, UsdShade
        meshes = [p for p in self.stage.Traverse() if p.IsA(UsdGeom.Mesh)]
        materials = [p for p in self.stage.Traverse() if p.IsA(UsdShade.Material)]
        textures = [p for p in self.stage.Traverse()
                    if p.IsA(UsdShade.Shader) and UsdShade.Shader(p).GetIdAttr().Get() == "UsdUVTexture"]
        self.assertEqual(len(meshes), 2)
        self.assertEqual(len(materials), 2)
        self.assertEqual(len(textures), 1)

    def test_no_physics_at_all(self):
        """충돌·강체가 붙으면 AMR 이 바닥 표시에 걸린다. 스키마 이름으로 전부 본다."""
        for prim in self.stage.Traverse():
            schemas = " ".join(prim.GetAppliedSchemas())
            self.assertNotIn("Physics", schemas, str(prim.GetPath()))

    def test_primvar_counts_match_the_topology(self):
        """개수가 어긋나면 RTX 가 조용히 흰색으로 그린다."""
        from pxr import UsdGeom
        strips = self.mesh("FloorStrips")
        faces = len(strips.GetFaceVertexCountsAttr().Get())
        colors = UsdGeom.PrimvarsAPI(strips).GetPrimvar("displayColor")
        self.assertEqual(colors.GetInterpolation(), UsdGeom.Tokens.uniform)
        self.assertEqual(len(colors.Get()), faces)
        labels = self.mesh("FloorLabels")
        st = UsdGeom.PrimvarsAPI(labels).GetPrimvar("st")
        self.assertEqual(len(st.Get()), len(labels.GetPointsAttr().Get()))
        self.assertEqual(len(labels.GetFaceVertexCountsAttr().Get()), len(self.plan["labels"]))

    def test_every_index_points_at_a_vertex(self):
        for name in ("FloorStrips", "FloorLabels"):
            mesh = self.mesh(name)
            n = len(mesh.GetPointsAttr().Get())
            indices = list(mesh.GetFaceVertexIndicesAttr().Get())
            self.assertTrue(all(0 <= i < n for i in indices), name)
            self.assertEqual(sum(mesh.GetFaceVertexCountsAttr().Get()), len(indices), name)

    def test_each_mesh_is_bound_to_its_material(self):
        from pxr import UsdShade
        for name, look in (("FloorStrips", "Strips"), ("FloorLabels", "Labels")):
            bound, _ = UsdShade.MaterialBindingAPI(self.mesh(name).GetPrim()).ComputeBoundMaterial()
            self.assertEqual(str(bound.GetPath()), f"/World/HospitalDecor/Looks/{look}")

    def test_the_log_line_names_what_was_built(self):
        summary = [line for line in self.lines if line.startswith("hospital_decor ")]
        self.assertEqual(len(summary), 1)
        self.assertIn("visual_only=true", summary[0])
        self.assertIn("meshes=2", summary[0])
        self.assertEqual(self.counts, (len(self.plan["strips"]), len(self.plan["labels"])))


class RoutesText(unittest.TestCase):
    """CI Evidence 잡에는 PyYAML 이 없다(#669). 경로표는 생성물 모양 그대로 PyYAML 없이 읽는다."""

    def test_reads_the_generated_routes_file(self):
        routes = D.parse_routes_text(ROUTES.read_text(encoding="utf-8"))
        self.assertGreater(len(routes), 200)
        first = routes[0]
        self.assertEqual({"from", "to", "waypoints"}, set(first))
        self.assertTrue(all(len(p) == 2 for r in routes for p in r["waypoints"]))

    def test_matches_pyyaml_when_it_is_there(self):
        try:
            import yaml
        except ImportError:
            self.skipTest("PyYAML 없음 — CI Evidence 잡과 같은 환경")
        text = ROUTES.read_text(encoding="utf-8")
        self.assertEqual(yaml.safe_load(text)["routes"], D.parse_routes_text(text))

    def test_an_unknown_line_under_routes_is_an_error(self):
        with self.assertRaises(ValueError):
            D.parse_routes_text("routes:\n  - something else\n")


class TableTintPaths(unittest.TestCase):
    """회차74(50b8769): 앵커의 씬 경로(/World/…)를 그대로 찾아 `table_tints painted=2 missing=11` 이었다."""

    def test_every_tint_prim_is_moved_under_the_base_scene_root(self):
        from p3sim import base_scene, hospital_nav

        tints = D.table_tints(hospital_nav.load_anchors()["bedside_tables"],
                              [t["prim"] for t in hospital_nav.room_tables().values()])
        self.assertEqual(13, len(tints))          # B 1 + C 2 + D 10
        for prim, _color in tints:
            moved = base_scene.scene_prim_path(prim)
            self.assertTrue(moved.startswith(f"{base_scene.BASE_ROOT}/Scene/Environment/hospital/"), moved)
        self.assertEqual("/Elsewhere/X", base_scene.scene_prim_path("/Elsewhere/X"))     # 기본 프림 밖은 그대로
        self.assertEqual("/WorldX/Y", base_scene.scene_prim_path("/WorldX/Y"))           # 접두사만 같은 이름도 그대로
