"""도크 벽 반투명(재범 9/29). Isaac 부분(재질 바인딩)은 L3 미실행 — 라이다 통과 여부·rtf 도 L3."""

import importlib.util
import re
import sys
import unittest
from pathlib import Path

STANDALONE = Path(__file__).resolve().parents[1] / "standalone"
REPO = STANDALONE.parents[1]
sys.path.insert(0, str(STANDALONE))
from p3sim import glass_wall as G  # noqa: E402


def load_stage():
    spec = importlib.util.spec_from_file_location("pharmacy_stage_glass", STANDALONE / "pharmacy_stage.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class GlassWall(unittest.TestCase):
    def test_the_wall_prims_exist_in_the_scene_file_on_the_dock_wall_line(self):
        scene = (REPO / "sim" / "scenes" / "hospital_navigationv1.usda").read_text(encoding="utf-8")
        for path in G.DOCK_WALL_PRIMS:
            name = path.rsplit("/", 1)[-1]
            m = re.search(rf'def \w+ "{name}"[\s\S]{{0,1500}}?xformOp:translate = \(([^)]*)\)', scene)
            self.assertIsNotNone(m, name)
            y = float(m.group(1).split(",")[1])
            self.assertAlmostEqual(5.35, y, delta=0.01, msg=name)       # 조제실 남쪽 벽(도크 벽)

    def test_opacity_one_keeps_the_original_wall(self):
        self.assertFalse(G.should_build(1.0))
        self.assertTrue(G.should_build(G.HOSPITAL_OPACITY))
        self.assertTrue(0.0 < G.HOSPITAL_OPACITY < 1.0)
        painted, missing = G.build(None, "/x", G.DOCK_WALL_PRIMS, 1.0, log=lambda *_: None)
        self.assertEqual((0, []), (painted, missing))                   # stage 를 건드리지 않는다

    def test_the_hospital_preset_turns_it_on_and_the_default_is_off(self):
        stage = load_stage()
        self.assertEqual(G.HOSPITAL_OPACITY, stage.HOSPITAL_DOCK_WALL_OPACITY)
        self.assertEqual(G.HOSPITAL_OPACITY, stage.parse_args(["--preset", "hospital"]).dock_wall_opacity)
        self.assertEqual(1.0, stage.parse_args([]).dock_wall_opacity)

    def test_only_the_material_changes(self):
        source = (STANDALONE / "p3sim" / "glass_wall.py").read_text(encoding="utf-8")
        body = source[source.index("def build("):]
        for physics in ("CollisionAPI", "RigidBodyAPI", "SetActive", "Visibility"):
            self.assertNotIn(physics, body)


if __name__ == "__main__":
    unittest.main()
