"""병원 벽 표지판·문 앞 매트(재범 9/25 "조제실이랑 병원, 병동이랑 데코 알아서 예쁘게"). Isaac 없이 자리만 본다.

    python3 -m unittest discover -s sim/tests -p 'test_hospital_signage.py'
"""

import importlib.util
import json
import struct
import sys
import unittest
from pathlib import Path

STANDALONE = Path(__file__).resolve().parents[1] / "standalone"
REPO = STANDALONE.parents[1]
sys.path.insert(0, str(STANDALONE))
from p3sim import hospital_decor as D  # noqa: E402
from p3sim import hospital_nav as hn  # noqa: E402
from p3sim import hospital_signage as S  # noqa: E402
from p3sim import hospital_zones  # noqa: E402

ATLAS_DIR = REPO / "sim" / "assets" / "decor"
ZONES = REPO / "src" / "rokey_p3_description" / "config" / "zones.hospital.yaml"
ROUTES = REPO / "src" / "rokey_p3_description" / "config" / "routes.hospital.yaml"


class Signage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.grid = hn.load_map()
        cls.anchors = hn.load_anchors()
        zones = hospital_zones.zones_from_yaml(ZONES)
        routes = D.parse_routes_text(ROUTES.read_text(encoding="utf-8"))
        atlas = json.loads((ATLAS_DIR / "labels.json").read_text(encoding="utf-8"))["uv"]
        cls.decor = D.plan(routes, zones, cls.grid, hn.BODY_LENGTH, hn.BODY_WIDTH, atlas)
        cls.avoid = S.decor_faces(cls.decor)
        cls.plan = S.plan(cls.grid, cls.anchors, hn.STATION_B_TABLE, cls.avoid)

    def test_everything_is_placed_and_the_plan_is_deterministic(self):
        names = [s["name"] for s in self.plan["signs"]]
        self.assertEqual(["ward_C1", "ward_C2", *[f"bed_D{i}" for i in range(1, 11)], "station_b", "pharmacy",
                          "poster_hands", "poster_fall", "poster_quiet",
                          "hang_lobby", "hang_lobby_back", "hang_C1", "hang_C2"], names)
        self.assertEqual(["mat_C1", "mat_C2", "mat_pharmacy"], [m["name"] for m in self.plan["mats"]])
        self.assertEqual([], self.plan["skipped"])
        again = S.plan(self.grid, self.anchors, hn.STATION_B_TABLE, self.avoid)
        self.assertEqual(self.plan, again)

    def test_signs_sit_in_the_height_band_outside_the_lidar_plane(self):
        """RTX 라이다 스캔 띠 0.1–0.6 m·충전 판 규칙 0.85 m 위. 벽 판은 1.0–1.8 m 안이다(천장 안내판은 따로)."""
        for sign in self.plan["signs"]:
            if sign.get("hang"):
                continue
            zs = [p[2] for p in sign["quad"]]
            self.assertGreaterEqual(min(zs), S.Z_MIN, sign["name"])
            self.assertLessEqual(max(zs), S.Z_MAX, sign["name"])

    def test_every_sign_has_a_wall_behind_and_faces_the_free_side(self):
        for sign in self.plan["signs"]:
            if sign.get("hang"):
                continue
            (cx, cy), (fx, fy) = sign["centre"], sign["facing"]
            behind = (cx - fx * (S.WALL_OFFSET + S.BEHIND), cy - fy * (S.WALL_OFFSET + S.BEHIND))
            self.assertTrue(self.grid.is_blocked(*behind), f"{sign['name']} 뒤 {behind}")
            if sign["name"].startswith("bed_"):
                # 앞은 침상이다 — 판 아래 끝이 침상 윗면보다 위라 가리지 않는다.
                bed = self.anchors["beds"][sign["text"]]
                self.assertLess(bed["max"][2], min(p[2] for p in sign["quad"]))
            else:
                front = (cx + fx * S.FRONT, cy + fy * S.FRONT)
                self.assertFalse(self.grid.is_blocked(*front), f"{sign['name']} 앞 {front}")

    def test_hanging_signs_are_overhead_on_free_floor(self):
        """천장 안내판(재범 9/28 데코 2차): 로봇·보행자 머리 위(2.0–2.5 m), 밑 바닥이 비었다(벽·기둥을 안 뚫는다)."""
        hangs = [s for s in self.plan["signs"] if s.get("hang")]
        self.assertEqual(4, len(hangs))
        for sign in hangs:
            zs = [p[2] for p in sign["quad"]]
            self.assertGreaterEqual(min(zs), S.Z_HANG_MIN, sign["name"])
            self.assertLessEqual(max(zs), S.Z_HANG_MAX, sign["name"])
            for x, y, _z in sign["quad"]:
                self.assertFalse(self.grid.is_blocked(x, y), (sign["name"], x, y))

    def test_the_lobby_hanging_sign_reads_both_ways_and_ward_signs_face_the_corridor(self):
        front = next(s for s in self.plan["signs"] if s["name"] == "hang_lobby")
        back = next(s for s in self.plan["signs"] if s["name"] == "hang_lobby_back")
        self.assertEqual(((-1.0, 0.0), (1.0, 0.0)), (front["facing"], back["facing"]))   # 단면 둘을 등지게
        self.assertAlmostEqual(S.HANG_GAP, back["centre"][0] - front["centre"][0], places=9)
        self.assertIn("병동", front["text"])
        self.assertIn("조제실", back["text"])
        for room, text in (("C1", "병동 A"), ("C2", "병동 B")):
            door = self.anchors["doors"][room]
            sign = next(s for s in self.plan["signs"] if s["name"] == f"hang_{room}")
            self.assertEqual(text, sign["text"])
            self.assertEqual((-1.0, 0.0), sign["facing"])
            self.assertAlmostEqual(door["center"][1], sign["centre"][1], places=6)
            self.assertLess(door["center"][0] - sign["centre"][0], 2.0)

    def test_lobby_posters_are_on_the_south_wall_spread_out(self):
        posters = [s for s in self.plan["signs"] if s["name"].startswith("poster_")]
        self.assertEqual(3, len(posters))
        for sign in posters:
            self.assertEqual((0.0, 1.0), tuple(round(v, 9) + 0.0 for v in sign["facing"]))
        xs = sorted(s["centre"][0] for s in posters)
        self.assertTrue(all(b - a > 3.0 for a, b in zip(xs, xs[1:], strict=False)), xs)

    def test_ward_signs_are_beside_their_doors_and_bed_signs_at_their_beds(self):
        for room in ("C1", "C2"):
            door = self.anchors["doors"][room]
            sign = next(s for s in self.plan["signs"] if s["name"] == f"ward_{room}")
            self.assertLess(abs(sign["centre"][0] - door["center"][0]), 0.2)
            self.assertLess(sign["centre"][1] - door["max"][1], 2.0)
            self.assertEqual((-1.0, 0.0), sign["facing"])     # 복도(−x)를 본다
        for label, bed in self.anchors["beds"].items():
            sign = next(s for s in self.plan["signs"] if s["name"] == f"bed_{label}")
            self.assertAlmostEqual((bed["min"][0] + bed["max"][0]) / 2.0, sign["centre"][0], places=6)

    def test_nothing_in_the_pharmacy_workcell_and_the_pharmacy_sign_is_backwards_to_its_cameras(self):
        """조제실 판은 방 바깥 벽면에서 바깥(+x)을 본다 — 방 안 M0609 카메라 눈에서는 단면의 뒷면이라 안 그려진다."""
        for sign in self.plan["signs"]:
            self.assertFalse(any(D.in_keep_out(p[0], p[1]) for p in sign["quad"]), sign["name"])
        for mat in self.plan["mats"]:
            self.assertFalse(any(D.in_keep_out(p[0], p[1]) for p in mat["quad"]), mat["name"])
        pharmacy = next(s for s in self.plan["signs"] if s["name"] == "pharmacy")
        for eye in S.PHARMACY_EYES:
            self.assertFalse(S.facing_eye(pharmacy, eye), eye)

    def test_mats_lie_on_free_floor_away_from_other_floor_plates_at_their_own_height(self):
        lifts = [*D.LIFT_LINES, D.LIFT_BAY, D.LIFT_LABEL, D.LIFT_FILL, D.LIFT_MARK]
        self.assertNotIn(S.LIFT_MAT, lifts)
        self.assertLess(S.LIFT_MAT, min(D.LIFT_LINES))   # 유도선이 매트 위로 그려진다
        for mat in self.plan["mats"]:
            quad = mat["quad"]
            self.assertTrue(all(abs(p[2] - S.LIFT_MAT) < 1e-12 for p in quad))
            inner = [D._quad_point(quad, u / 10.0, v / 10.0) for u in range(11) for v in range(11)]
            self.assertTrue(D.on_free_floor(self.grid, inner), mat["name"])
            self.assertFalse(any(D.overlaps(quad, face) for face in self.avoid), mat["name"])

    def test_atlas_has_every_sign_text_and_no_pale_background(self):
        atlas = json.loads((ATLAS_DIR / "signs.json").read_text(encoding="utf-8"))
        self.assertEqual(set(S.SIGN_TEXTS), set(atlas["uv"]))
        with open(ATLAS_DIR / atlas["image"], "rb") as fh:
            data = fh.read(32)
        width, height, _bits, color = struct.unpack(">IIBB", data[16:26])
        self.assertEqual(2, color)                        # RGB, 알파 없음
        self.assertLessEqual(max(width, height), 1024)
        for text in S.SIGN_TEXTS:
            background, _ink = S.sign_style(text)
            self.assertGreater(max(background) - min(background), 0.3, text)   # 채도 — 흰·회색 바탕 없음

    @unittest.skipUnless(importlib.util.find_spec("PIL"), "PIL 없음")
    def test_atlas_pixels_match_the_style(self):
        from PIL import Image

        atlas = json.loads((ATLAS_DIR / "signs.json").read_text(encoding="utf-8"))
        image = Image.open(ATLAS_DIR / atlas["image"]).convert("RGB")
        w, h = image.size
        for text, (u0, _v0, _u1, v1) in atlas["uv"].items():
            pixel = image.getpixel((int(u0 * w) + 6, int((1.0 - v1) * h) + 1))
            expected = tuple(int(round(c * 255)) for c in S.sign_style(text)[0])
            self.assertTrue(all(abs(a - b) <= 2 for a, b in zip(pixel, expected, strict=True)), (text, pixel))


class Budget(unittest.TestCase):
    """재범 9/25 "막 무겁게 하지 말고": 표지판 메시 하나·재질 하나·텍스처 한 장, 매트는 새 메시 없이 색 띠 메시에."""

    def test_mats_become_color_strip_faces_and_signs_stay_modest(self):
        grid, anchors = hn.load_map(), hn.load_anchors()
        signage = S.plan(grid, anchors, hn.STATION_B_TABLE)
        strips = S.mat_strips(signage)
        self.assertEqual(len(signage["mats"]), len(strips))
        for _name, points, counts, indices, color in strips:
            self.assertEqual(([4], [0, 1, 2, 3]), (counts, indices))
            self.assertEqual(4, len(points))
            self.assertEqual(3, len(color))
        # 9/25 1차 14장 → 9/28 2차 21장(판 7장만 더함, 메시·재질·텍스처는 그대로 하나씩).
        self.assertLessEqual(len(signage["signs"]), 21)

    def test_one_sign_mesh_one_material_one_texture_and_no_per_sign_prims(self):
        source = (STANDALONE / "p3sim" / "hospital_signage.py").read_text(encoding="utf-8")
        body = source[source.index("def build(stage, root, signage"):]
        self.assertEqual(1, body.count("UsdGeom.Mesh.Define("))
        self.assertEqual(1, body.count("UsdShade.Material.Define("))
        self.assertEqual(1, body.count('CreateIdAttr("UsdUVTexture")'))
        self.assertNotIn("for sign in signs:\n        stage.DefinePrim", body)
        atlas = json.loads((ATLAS_DIR / "signs.json").read_text(encoding="utf-8"))
        self.assertLessEqual(atlas["size"][0], 1024)
        self.assertLessEqual(atlas["size"][1], 512)


class StageWiring(unittest.TestCase):
    def test_signage_is_built_with_the_floor_decor(self):
        source = (STANDALONE / "pharmacy_stage.py").read_text(encoding="utf-8")
        start = source.index("def build_hospital_decor(")
        body = source[start:source.index("\ndef ", start + 10)]
        self.assertIn("hospital_signage.plan(", body)
        self.assertIn("hospital_signage.build(", body)
        self.assertIn("hospital_signage.mat_strips(signage) + decor[\"strips\"]", body)
        self.assertLess(body.index("mat_strips("), body.index("hospital_decor.build(stage"))


if __name__ == "__main__":
    unittest.main()
