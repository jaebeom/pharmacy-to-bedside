"""UR5 pedestal pin, read back (L3-2 9/20: base_frame_mismatch, the UR5 simulated at the origin). usd-core only;
the Evidence harness runs these. What PhysX does with the fixed root joint is L3.

    python3 -m unittest discover -s sim/tests -p 'test_[mp]*.py'
"""

import sys
import tempfile
import unittest
from pathlib import Path

STANDALONE = Path(__file__).resolve().parents[1] / "standalone"
sys.path.insert(0, str(STANDALONE))

from p3sim import ur5_cell  # noqa: E402

PEDESTAL = (3.25, 0.55, 0.45)
UR5 = "/World/P3Pharmacy/Loading/UR5"


def build(tmp, reset_stack=False, move_prim=True, place=False, asset_ops=False, parent_offset=None):
    """A fake UR5 asset (fixed root joint to the world, body1 base_link, articulation root on the joint) referenced
    at UR5, pinned the way Ur5Cell.build does it. Returns (stage, cell)."""
    from pxr import Gf, Usd, UsdGeom, UsdPhysics

    asset_path = Path(tmp) / "ur5.usda"
    asset = Usd.Stage.CreateNew(str(asset_path))
    root = UsdGeom.Xform.Define(asset, "/ur5")
    asset.SetDefaultPrim(root.GetPrim())
    if asset_ops:  # like imported robot assets: translate, orient and scale ops already authored on the root
        root.AddTranslateOp().Set(Gf.Vec3d(0.0, 0.0, 0.0))
        root.AddOrientOp().Set(Gf.Quatf(1.0, 0.0, 0.0, 0.0))
        root.AddScaleOp().Set(Gf.Vec3f(1.0, 1.0, 1.0))
    base = UsdGeom.Xform.Define(asset, "/ur5/base_link")
    if reset_stack:
        base.SetResetXformStack(True)
    UsdGeom.Xform.Define(asset, "/ur5/flange")
    joint = UsdPhysics.FixedJoint.Define(asset, "/ur5/root_joint")
    joint.GetBody1Rel().SetTargets(["/ur5/base_link"])
    joint.GetLocalPos0Attr().Set(Gf.Vec3f(0.0, 0.0, 0.0))
    UsdPhysics.ArticulationRootAPI.Apply(joint.GetPrim())
    asset.GetRootLayer().Save()

    stage = Usd.Stage.CreateInMemory()
    loading = UsdGeom.Xform.Define(stage, "/World/P3Pharmacy/Loading")
    if parent_offset is not None:
        loading.AddTranslateOp().Set(Gf.Vec3d(*parent_offset))
    prim = stage.DefinePrim(UR5)
    prim.GetReferences().AddReference(str(asset_path))
    lines = []
    if place:  # the fix: Ur5Cell.build authors the prim translation before pinning
        lines.append(ur5_cell.place_prim(stage, UR5, PEDESTAL))
    elif move_prim:  # what SingleArticulation(position=pedestal) was expected to do in USD
        UsdGeom.XformCommonAPI(prim).SetTranslate(Gf.Vec3d(*PEDESTAL))
    cell = ur5_cell.Ur5Cell(stage, None, "/World/P3Pharmacy/Loading", {"base": PEDESTAL}, lines.append)
    cell._pin_world_joints(UR5, PEDESTAL)
    return stage, cell, lines


class PinReportTests(unittest.TestCase):
    def setUp(self):
        try:
            import pxr  # noqa: F401
        except ImportError:
            self.skipTest("usd-core not installed")
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def test_pin_writes_and_reads_back_on_a_referenced_asset(self):
        stage, cell, lines = build(self.tmp.name)
        self.assertEqual([(f"{UR5}/root_joint", PEDESTAL)], [(p, tuple(round(v, 4) for v in w))
                                                             for p, w in cell.pinned])
        self.assertIn("set_ok=True", lines[0])
        report = ur5_cell.pin_report(stage, UR5, cell.pinned, PEDESTAL)
        self.assertEqual([], report["problems"])
        self.assertIn("base_link_resets_xform_stack=False", report["line"])
        self.assertIn("readback=[3.2500, 0.5500, 0.4500]", report["line"])

    def test_base_link_that_resets_the_xform_stack_is_reported(self):
        stage, cell, _lines = build(self.tmp.name, reset_stack=True)
        problems = ur5_cell.pin_report(stage, UR5, cell.pinned, PEDESTAL)["problems"]
        self.assertTrue(any("resets the xform stack" in p for p in problems))
        self.assertTrue(any("is not the pedestal" in p for p in problems))  # stays at the origin

    def test_prim_left_at_the_origin_is_reported(self):
        stage, cell, _lines = build(self.tmp.name, move_prim=False)
        report = ur5_cell.pin_report(stage, UR5, cell.pinned, PEDESTAL)
        self.assertEqual(1, len(report["problems"]))  # the joint readback matches; base_link does not
        self.assertIn("base_link composed world [0.0000, 0.0000, 0.0000] is not the pedestal", report["problems"][0])

    def test_readback_different_from_the_written_value_is_reported(self):
        stage, cell, _lines = build(self.tmp.name)
        path, _written = cell.pinned[0]
        problems = ur5_cell.pin_report(stage, UR5, [(path, (9.0, 9.0, 9.0))], PEDESTAL)["problems"]
        self.assertTrue(any("readback" in p and "!= written" in p for p in problems))


class PlacePrimTests(unittest.TestCase):
    """SIM-9 step 2: the 13a2dfd run showed the UR5 prim composed at the origin; build() now authors it in USD."""

    def setUp(self):
        try:
            import pxr  # noqa: F401
        except ImportError:
            self.skipTest("usd-core not installed")
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def check_on_pedestal(self, stage, cell, placed):
        from pxr import Usd, UsdGeom, UsdPhysics

        ok, composed = placed
        self.assertTrue(ok)
        for got, want in zip(composed, PEDESTAL, strict=True):
            self.assertAlmostEqual(want, got, places=5)
        self.assertEqual([], ur5_cell.pin_report(stage, UR5, cell.pinned, PEDESTAL)["problems"])
        # The world anchor is added once: localPos0 (body0 empty = world frame) must equal where base_link is now,
        # not pedestal + pedestal, or PhysX gets two joint frames that disagree.
        joint = UsdPhysics.Joint(stage.GetPrimAtPath(f"{UR5}/root_joint"))
        anchor = tuple(float(v) for v in joint.GetLocalPos0Attr().Get())
        base = UsdGeom.Xformable(stage.GetPrimAtPath(f"{UR5}/base_link"))
        base_world = tuple(base.ComputeLocalToWorldTransform(Usd.TimeCode.Default()).ExtractTranslation())
        for a, b, p in zip(anchor, base_world, PEDESTAL, strict=True):
            self.assertAlmostEqual(b, a, places=5)
            self.assertAlmostEqual(p, a, places=5)

    def test_place_then_pin_puts_prim_base_link_and_anchor_on_the_pedestal(self):
        stage, cell, lines = build(self.tmp.name, place=True)
        self.check_on_pedestal(stage, cell, lines[0])

    def test_asset_with_translate_orient_scale_ops(self):
        stage, cell, lines = build(self.tmp.name, place=True, asset_ops=True)
        self.check_on_pedestal(stage, cell, lines[0])

    def test_translated_parent_does_not_shift_the_robot(self):
        stage, cell, lines = build(self.tmp.name, place=True, parent_offset=(1.0, -2.0, 0.5))
        self.check_on_pedestal(stage, cell, lines[0])


class WiringTests(unittest.TestCase):
    def test_ready_logs_the_check_after_reset(self):
        source = (STANDALONE / "p3sim" / "ur5_cell.py").read_text()
        ready = source[source.index("    def ready("):source.index("    # ---- motion helpers ----")]
        self.assertIn("pin_report(self.stage, self.prim_path, self.pinned, self.cfg[\"base\"])", ready)
        self.assertIn('self.log(f"ur5 pin_failed {problem}")', ready)
        self.assertLess(ready.index("pin_report("), ready.index("ur5 ready joints="))

    def test_build_places_the_prim_before_pinning_and_before_the_articulation(self):
        source = (STANDALONE / "p3sim" / "ur5_cell.py").read_text()
        build = source[source.index("    def build(self):"):source.index("    def _pin_world_joints(")]
        place = build.index("place_prim(self.stage, prim_path, cfg[\"base\"])")
        self.assertLess(place, build.index("self._pin_world_joints(prim_path, cfg[\"base\"])"))
        self.assertLess(place, build.index("SingleArticulation(prim_path=prim_path"))

    def test_world_reset_has_a_step_line(self):
        stage = (STANDALONE / "pharmacy_stage.py").read_text()
        self.assertIn('with common.step(log, "world_reset"):\n            world.reset()', stage)


if __name__ == "__main__":
    unittest.main()
