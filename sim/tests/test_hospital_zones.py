"""hospital_zones: zones yaml -> 스테이지 layout["zones"](#527 H1). Isaac·PyYAML 없음.

    python3 -m unittest sim.tests.test_hospital_zones
"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STANDALONE = ROOT / "sim" / "standalone"
sys.path.insert(0, str(STANDALONE))

from p3sim import hospital_nav, hospital_zones, layout  # noqa: E402

CONFIG = ROOT / "src" / "rokey_p3_description" / "config"
HOSPITAL = CONFIG / "zones.hospital.yaml"
EMPTY = CONFIG / "zones.emptyworld.yaml"


class HospitalFileTests(unittest.TestCase):
    def setUp(self):
        self.text = HOSPITAL.read_text(encoding="utf-8")
        self.doc = hospital_zones.load_doc(HOSPITAL)
        self.zones = hospital_zones.zones_from_yaml(HOSPITAL)

    def test_path_and_text_give_the_same(self):
        self.assertEqual(self.zones, hospital_zones.zones_from_yaml(self.text))
        self.assertEqual(self.zones, hospital_zones.zones_from_yaml(str(HOSPITAL)))

    def test_every_bed_has_pose_cabinet_and_tag(self):
        beds = [name for name, entry in self.doc["zones"].items() if entry["kind"] == "bed"]
        self.assertEqual(10, len(beds))  # D1–D10 -> bed_a1–a4, bed_b1–b6 (파일 머리 주석)
        for bed in beds:
            entry = self.doc["zones"][bed]
            self.assertEqual((entry["x"], entry["y"], 0.0, entry["yaw"]), self.zones[bed])
            for sub in ("cabinet", "tag"):
                pose = self.zones[f"{bed}/{sub}"]
                self.assertEqual(4, len(pose))
                self.assertTrue(all(isinstance(v, float) for v in pose))
                expected = self.doc["zones"][bed][sub]
                self.assertEqual((expected["x"], expected["y"], expected["z"], expected["yaw"]), pose)
            # 실제 QR 면과 태그 TF 높이가 같다: 판 두께 4mm + QR 면 0.5mm.
            self.assertAlmostEqual(self.zones[f"{bed}/tag"][2] - self.zones[f"{bed}/cabinet"][2],
                                   0.0045, places=6)

    def test_docks_and_load_are_present(self):
        self.assertIn("load", self.zones)
        docks = sorted(name for name in self.zones if name.startswith("dock_"))
        self.assertEqual(["dock_1", "dock_2", "dock_3", "dock_4"], docks)
        for name in docks + ["load", "station_a"]:
            self.assertNotIn(f"{name}/cabinet", self.zones)
            self.assertEqual(0.0, self.zones[name][2])

    def test_round_trip_through_the_generator(self):
        # 읽은 문서를 hospital_nav 생성기로 다시 찍으면 파일과 글자 하나까지 같다.
        self.assertEqual(self.text, hospital_nav.zones_yaml_text(self.doc))

    def test_stage_consumers_accept_the_shape(self):
        # 스테이지가 쓰는 두 곳: cabinet_payloads 는 pose[:3] 를, tag_payload 는 bed zone 의 (x, y, z, yaw) 를 본다.
        from p3sim import zones as zoneslib

        prims = zoneslib.zone_prims(self.zones)
        self.assertEqual(len(self.zones), len(prims))
        self.assertIn("bed_a1_cabinet", {prim for prim, _frame, _xyz, _quat in prims})

    def test_tolerances_and_pharmacy_belt_end(self):
        tolerances = hospital_zones.tolerances_from_yaml(HOSPITAL)
        self.assertEqual({"tol_xy": 0.15, "tol_yaw": 0.2}, tolerances["bed_a1"])
        # 작전 9/23 확정: Rollers_01 끝 중심 윗면, yaw −90°(#527 H2). 예전에는 병원 파일에 pharmacy 가 없었다.
        self.assertEqual({"belt_end": (-8.1937, 4.9644, 0.3847, -1.5708)},
                         hospital_zones.pharmacy_frames_from_yaml(HOSPITAL))


class EmptyWorldFileTests(unittest.TestCase):
    def test_matches_full_loop_zones(self):
        zones = hospital_zones.zones_from_yaml(EMPTY)
        code = layout.full_loop_zones()
        self.assertEqual(set(code), set(zones))
        for name, pose in code.items():
            for a, b in zip(pose, zones[name], strict=True):
                self.assertAlmostEqual(a, b, places=4, msg=name)

    def test_round_trip_through_the_inverse(self):
        # layout.zones_yaml 이 역함수다: 읽은 zones·pharmacy 를 다시 찍으면 파일과 같다.
        text = EMPTY.read_text(encoding="utf-8")
        zones = hospital_zones.zones_from_yaml(text)
        pharmacy = hospital_zones.pharmacy_frames_from_yaml(text)
        self.assertEqual(text, layout.zones_yaml_text(layout.zones_yaml(zones, pharmacy=pharmacy)))


class ParserTests(unittest.TestCase):
    def test_refuses_what_it_does_not_read(self):
        for text in ("frame: map\nzones:\n  - load\n",
                     "frame: map\nzones:\n  load: [1, 2]\n",
                     "frame: map\nzones:\n  load:\n    x: 1\n    x: 2\n",
                     "frame: odom\nzones:\n  load:\n    x: 1\n    y: 2\n    yaw: 0\n",
                     "frame: map\n"):
            with self.assertRaises(ValueError, msg=text):
                hospital_zones.zones_from_yaml(text)

    def test_missing_field_is_named(self):
        with self.assertRaisesRegex(ValueError, "bed_a1.cabinet"):
            hospital_zones.zones_from_yaml("frame: map\nzones:\n  bed_a1:\n    x: 1.0\n    y: 2.0\n    yaw: 0.0\n"
                                           "    cabinet:\n      x: 1.0\n      y: 2.0\n      yaw: 0.0\n")

    def test_comments_and_negative_numbers(self):
        zones = hospital_zones.zones_from_yaml("# 머리\nframe: map  # map\nzones:\n  dock_1:\n    kind: dock\n"
                                               "    x: -8.238\n    y: 4.169\n    yaw: -1.571\n")
        self.assertEqual({"dock_1": (-8.238, 4.169, 0.0, -1.571)}, zones)


if __name__ == "__main__":
    unittest.main()
