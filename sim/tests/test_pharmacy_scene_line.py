"""Scene identification in the stage log: base scene sha256 and root-layer units (sim/scenes/README.md 2). No Isaac.

    python3 -m unittest discover -s sim/tests -p 'test_[mp]*.py'
"""

import hashlib
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

STANDALONE = Path(__file__).resolve().parents[1] / "standalone"
sys.path.insert(0, str(STANDALONE))

from p3sim import base_scene  # noqa: E402

HOSPITAL = Path(__file__).resolve().parents[1] / "scenes" / "hospital_layout.usda"


def load_stage():
    spec = importlib.util.spec_from_file_location("pharmacy_stage", STANDALONE / "pharmacy_stage.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


STAGE = load_stage()


class LayerUnitsTests(unittest.TestCase):
    def test_committed_hospital_scene(self):
        self.assertEqual(("1", "Z"), base_scene.layer_units(HOSPITAL.read_bytes()))

    def test_unset_unknown_and_body_keys(self):
        self.assertEqual(("unset", "unset"), base_scene.layer_units(b'#usda 1.0\n(\n    defaultPrim = "W"\n)\n'))
        self.assertEqual(("unknown", "unknown"), base_scene.layer_units(b"PXR-USDC\x00\x01"))
        body_only = b'#usda 1.0\n(\n)\ndef Xform "W" (\n    metersPerUnit = 0.01\n)\n{\n}\n'
        self.assertEqual(("unset", "unset"), base_scene.layer_units(body_only))
        self.assertEqual(("0.01", "Y"), base_scene.layer_units(b'#usda 1.0\n(\n    metersPerUnit = 0.01\n'
                                                               b'    upAxis = "Y"\n)\n'))


class SceneLineTests(unittest.TestCase):
    def test_without_base_scene(self):
        self.assertEqual("scene base_usd=- base_usd_sha256=- meters_per_unit=- up_axis=-",
                         STAGE.scene_line(STAGE.parse_args([])))

    def test_with_a_base_scene_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "scene.usda"
            path.write_bytes(HOSPITAL.read_bytes())
            line = STAGE.scene_line(STAGE.parse_args(["--base-usd", str(path)]))
            digest = hashlib.sha256(HOSPITAL.read_bytes()).hexdigest()
            self.assertEqual(f"scene base_usd={path} base_usd_sha256={digest} meters_per_unit=1 up_axis=Z", line)

    def test_missing_file_is_unknown(self):
        line = STAGE.scene_line(STAGE.parse_args(["--base-usd", "/nonexistent/p3/scene.usda"]))
        self.assertIn("base_usd_sha256=unknown meters_per_unit=unknown up_axis=unknown", line)

    def test_logged_right_after_the_startup_line(self):
        source = (STANDALONE / "pharmacy_stage.py").read_text()
        body = source.split("def run(args):", 1)[1].lstrip()
        self.assertTrue(body.startswith("log(startup_line(args))\n    log(scene_line(args))"))


if __name__ == "__main__":
    unittest.main()
