"""Validate shipped USD and detect geometry/anchor drift; run with pxr available."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

from tools.check_dispenser_asset import check, check_scene

ROOT = Path(__file__).resolve().parents[2]
ASSET = ROOT/'src/rokey_p3_description/models/dispenser/dispenser.usdc'
META = ASSET.with_name('asset.json')


@unittest.skipUnless(importlib.util.find_spec('pxr') and ASSET.exists(),
                     'requires USD Python and dispenser.usdc (not shipped in the public repository)')
class DispenserAssetTest(unittest.TestCase):
    def test_shipped_geometry_and_anchors(self):
        self.assertTrue(check(ASSET, META)['support_connected'])

    def altered(self, directory, prim_path, delta, change_metadata=False):
        from pxr import Gf, Usd, UsdGeom
        asset = Path(directory)/'asset.usdc'
        source = Usd.Stage.Open(str(ASSET))
        source.GetRootLayer().Export(str(asset))
        stage = Usd.Stage.Open(str(asset))
        xf = UsdGeom.Xformable(stage.GetPrimAtPath(prim_path))
        matrix = xf.GetLocalTransformation()
        matrix.SetTranslateOnly(matrix.ExtractTranslation()+Gf.Vec3d(*delta))
        xf.ClearXformOpOrder()
        xf.AddTransformOp(opSuffix='test').Set(matrix)
        stage.GetRootLayer().Save()
        info = json.loads(META.read_text())
        info.update(asset_sha256=hashlib.sha256(asset.read_bytes()).hexdigest(), asset_bytes=asset.stat().st_size)
        if change_metadata:
            name = prim_path.rsplit('/', 1)[1]
            info['anchors_local'][name] = [a+b for a, b in zip(info['anchors_local'][name], delta, strict=True)]
        meta = Path(directory)/'asset.json'
        meta.write_text(json.dumps(info))
        return asset, meta

    def test_anchor_and_metadata_cannot_move_without_visible_rim(self):
        with tempfile.TemporaryDirectory() as directory:
            asset, meta = self.altered(directory, '/Dispenser/Anchors/PillOpening', (.03, 0, 0), True)
            with self.assertRaisesRegex(AssertionError, 'pill anchor differs from rim'):
                check(asset, meta)

    def test_visible_module_cannot_move_without_anchor(self):
        with tempfile.TemporaryDirectory() as directory:
            asset, meta = self.altered(directory, '/Dispenser/Inlets/ModuleLeft', (.03, 0, 0))
            with self.assertRaisesRegex(AssertionError, 'module anchor differs from opening'):
                check(asset, meta)

    def test_disconnected_support_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            asset, meta = self.altered(directory, '/Dispenser/Inlets/PillSupport', (0, -.3, 0))
            with self.assertRaisesRegex(AssertionError, 'support disconnected'):
                check(asset, meta)

    def scene(self, directory):
        from pxr import Gf, Usd, UsdGeom
        path = Path(directory)/'scene.usda'
        stage = Usd.Stage.CreateNew(str(path))
        root = UsdGeom.Xform.Define(stage, '/Placed')
        root.GetPrim().GetReferences().AddReference(str(ASSET))
        root.AddTranslateOp().Set(Gf.Vec3d(3, 5, 0))
        root.AddRotateZOp().Set(25.)
        stage.GetRootLayer().Save()
        return stage, path

    def test_scene_rigid_placement_keeps_reference_geometry(self):
        with tempfile.TemporaryDirectory() as directory:
            stage, path = self.scene(directory)
            self.assertEqual(check_scene(ASSET, path, '/Placed')['saved_scene_geometry'], 'PASS')

    def test_scene_pill_only_offset_is_rejected_even_when_asset_hash_matches(self):
        from pxr import Gf, UsdGeom
        with tempfile.TemporaryDirectory() as directory:
            stage, path = self.scene(directory)
            xf = UsdGeom.Xformable(stage.GetPrimAtPath('/Placed/Inlets/PillRim00'))
            op = xf.AddTranslateOp(opSuffix='integration')
            op.Set(Gf.Vec3d(.3, -.1, 0))
            xf.SetXformOpOrder([op, *[x for x in xf.GetOrderedXformOps() if x != op]])
            stage.GetRootLayer().Save()
            with self.assertRaisesRegex(ValueError, 'geometry/anchor transform override'):
                check_scene(ASSET, path, '/Placed')

    def test_scene_scaling_is_rejected(self):
        from pxr import Gf, UsdGeom
        with tempfile.TemporaryDirectory() as directory:
            stage, path = self.scene(directory)
            UsdGeom.Xformable(stage.GetPrimAtPath('/Placed')).AddScaleOp().Set(Gf.Vec3f(2, 2, 2))
            stage.GetRootLayer().Save()
            with self.assertRaisesRegex(ValueError, 'must not scale/shear'):
                check_scene(ASSET, path, '/Placed')

    def test_live_session_override_is_rejected_without_saving(self):
        from pxr import Gf, UsdGeom
        from sim.standalone.p3sim.dispenser_reference import check_live_scene
        with tempfile.TemporaryDirectory() as directory:
            stage, path = self.scene(directory)
            stage.SetEditTarget(stage.GetSessionLayer())
            xf = UsdGeom.Xformable(stage.GetPrimAtPath('/Placed/Inlets/PillSupport'))
            xf.AddTranslateOp(opSuffix='local').Set(Gf.Vec3d(.3, -.1, 0))
            with self.assertRaisesRegex(ValueError, 'geometry/anchor transform override'):
                check_live_scene(ASSET, stage, '/Placed')

    def test_hospital_loader_checks_before_returning_to_physics_caller(self):
        from pxr import Gf, Usd, UsdGeom
        from sim.standalone.p3sim.base_scene import add_base_scene
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'hospital.usda'
            source = Usd.Stage.CreateNew(str(path))
            world = UsdGeom.Xform.Define(source, '/World')
            source.SetDefaultPrim(world.GetPrim())
            dispenser = UsdGeom.Xform.Define(source, '/World/IntegratedDispenser')
            dispenser.GetPrim().GetReferences().AddReference(str(ASSET))
            dispenser.AddTranslateOp().Set(Gf.Vec3d(3, 5, 0))
            source.GetRootLayer().Save()
            good = Usd.Stage.CreateInMemory()
            report = add_base_scene(good, str(path), (0, 0, 0, 0))
            self.assertEqual(len(report['dispenser_checks']), 1)
            self.assertEqual(report['dispenser_checks'][0]['scene_geometry'], 'PASS')
            xf = UsdGeom.Xformable(source.GetPrimAtPath('/World/IntegratedDispenser/Inlets/PillSupport'))
            xf.AddTranslateOp(opSuffix='local').Set(Gf.Vec3d(.3, -.1, 0))
            source.GetRootLayer().Save()
            with self.assertRaisesRegex(ValueError, 'geometry/anchor transform override'):
                add_base_scene(Usd.Stage.CreateInMemory(), str(path), (0, 0, 0, 0))

    def test_hospital_deactivation_cannot_bypass_reference_check(self):
        from pxr import Usd, UsdGeom
        from sim.standalone.p3sim.base_scene import add_base_scene
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'hospital.usda'
            source = Usd.Stage.CreateNew(str(path))
            world = UsdGeom.Xform.Define(source, '/World')
            source.SetDefaultPrim(world.GetPrim())
            dispenser = UsdGeom.Xform.Define(source, '/World/IntegratedDispenser')
            dispenser.GetPrim().GetReferences().AddReference(str(ASSET))
            source.GetRootLayer().Save()
            with self.assertRaisesRegex(ValueError, 'missing/inactive'):
                add_base_scene(Usd.Stage.CreateInMemory(), str(path), (0, 0, 0, 0),
                               deactivate=['IntegratedDispenser'])


if __name__ == '__main__':
    unittest.main()
