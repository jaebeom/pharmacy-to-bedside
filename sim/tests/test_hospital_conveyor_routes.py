"""Pure parts of the hospital conveyor route check (#233). No Isaac.

sim/standalone/test_conveyor_routes.py is an Isaac script (it starts Isaac Sim), so unittest collects 0 tests
from it and it stays where it is. This file tests the logic it relies on: argument checks,
the expected attribute values per route, the asset ZIP/scene resolution, and SorterRouter on the committed scene layer
(usd-core; the Evidence harness runs it). What an outlet does physically is L3.

    python3 -m unittest discover -s sim/tests -p 'test_*.py'
"""

import contextlib
import importlib.util
import io
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

STANDALONE = Path(__file__).resolve().parents[1] / "standalone"
sys.path.insert(0, str(STANDALONE))

from p3sim import hospital_assets, sorter  # noqa: E402

LAYOUT = STANDALONE.parent / "scenes" / "hospital_layout.usda"
CONFIG = STANDALONE / "conveyor_config.example.json"


def load_script():
    spec = importlib.util.spec_from_file_location("conveyor_routes_script", STANDALONE / "test_conveyor_routes.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SCRIPT = load_script()


def quiet():
    return contextlib.redirect_stdout(io.StringIO())


class ScriptTests(unittest.TestCase):
    def test_import_does_not_start_isaac(self):
        self.assertFalse(any(name.split(".")[0] in ("isaacsim", "omni") for name in sys.modules))

    def test_arguments(self):
        defaults = SCRIPT.parse_args([])
        self.assertEqual(
            STANDALONE.parent / "outputs" / "hospital-custom-assets-20260918.zip",
            defaults.custom_assets_zip,
        )
        self.assertEqual(
            "https://omniverse-content-production.s3-us-west-2.amazonaws.com/Assets/Isaac/5.1",
            defaults.isaac_assets_root,
        )
        self.assertEqual(Path("/x"), SCRIPT.parse_args(["--custom-assets", "/x"]).custom_assets)
        with tempfile.TemporaryDirectory() as tmp:
            scene = Path(tmp) / "s.usda"
            args = SCRIPT.parse_args(["--scene", str(scene)])
            self.assertEqual(scene, args.scene)
            self.assertIsNone(args.custom_assets_zip)
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            SCRIPT.parse_args(["--scene", "/x.usda", "--settle-frames", "-1"])

    def test_expected_values_for_the_four_routes(self):
        config = json.loads(CONFIG.read_text(encoding="utf-8"))
        seen = set()
        for route in (1, 2, 3, 4):
            expected = SCRIPT._expected(config, route, sorter.ROUTES)
            self.assertEqual(3, len(expected))
            states = tuple(expected[config[name]["reroute_attribute"]]
                           for name in sorter.JUNCTIONS)
            self.assertIn(states, ((True, False, False),
                                   (False, True, False),
                                   (False, False, True),
                                   (False, False, False)))
            seen.add(states)
        self.assertEqual(4, len(seen))  # four outlets, four different settings

    def test_plain(self):
        self.assertEqual([1.0, 0.0], SCRIPT._plain((1, 0)))
        self.assertIs(True, SCRIPT._plain(True))
        self.assertEqual(3, SCRIPT._plain(3))


class HospitalAssetsTests(unittest.TestCase):
    def test_zip_member_outside_the_destination_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "a.zip"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("../evil.txt", "x")
            with zipfile.ZipFile(path) as archive, self.assertRaises(RuntimeError):
                hospital_assets._safe_extract(archive, Path(tmp) / "out")
            self.assertFalse((Path(tmp) / "evil.txt").exists())

    def test_extract_once_reuses_the_same_zip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "assets.zip"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("pack/m0617/m0617.usd", "#usda 1.0\n")
            first = hospital_assets._extract_once(path, Path(tmp) / "run")
            (first / "pack" / "extra").write_text("kept")
            self.assertEqual(first, hospital_assets._extract_once(path, Path(tmp) / "run"))
            self.assertTrue((first / "pack" / "extra").exists())  # not extracted again

    def test_custom_root_must_be_unique(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a" / "m").mkdir(parents=True)
            (root / "a" / "m" / "x.usd").write_text("")
            self.assertEqual((root / "a").resolve(), hospital_assets._custom_root(root, ["m/x.usd"]))
            (root / "b" / "m").mkdir(parents=True)
            (root / "b" / "m" / "x.usd").write_text("")
            with self.assertRaises(RuntimeError):
                hospital_assets._custom_root(root, ["m/x.usd"])

    def test_resolve_scene_with_a_scene_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            scene = Path(tmp) / "scene.usda"
            scene.write_text("#usda 1.0\n")
            got, paths = hospital_assets.resolve_scene(standalone_dir=STANDALONE, scene=scene, custom_assets=None,
                                                       custom_assets_zip=None, isaac_assets_root=None,
                                                       runtime_dir=Path(tmp) / "run")
            self.assertEqual(scene.resolve(), got)
            self.assertEqual(str(scene.parent.resolve()), paths[0])
            bad = Path(tmp) / "scene.txt"
            bad.write_text("")
            with self.assertRaises(FileNotFoundError):
                hospital_assets.resolve_scene(standalone_dir=STANDALONE, scene=bad, custom_assets=None,
                                              custom_assets_zip=None, isaac_assets_root=None,
                                              runtime_dir=Path(tmp) / "run")


class SorterOnTheSceneLayerTests(unittest.TestCase):
    def test_every_route_writes_and_reads_back_on_the_committed_layer(self):
        try:
            from pxr import Usd
        except ImportError:
            self.skipTest("usd-core not installed")
        stage = Usd.Stage.Open(str(LAYOUT), Usd.Stage.LoadNone)  # asset paths are placeholders: layer opinions only
        router = sorter.SorterRouter(stage, CONFIG, log=lambda _line: None)
        config = json.loads(CONFIG.read_text(encoding="utf-8"))
        for route in (1, 2, 3, 4):
            with self.subTest(route=route), quiet():
                router.route_to(route)
                self.assertEqual([], SCRIPT._verify(stage, SCRIPT._expected(config, route, sorter.ROUTES)))
        with self.assertRaises(ValueError):
            router.route_to(5)


if __name__ == "__main__":
    unittest.main()
