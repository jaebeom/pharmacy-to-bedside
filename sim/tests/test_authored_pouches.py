import sys
import unittest
from pathlib import Path

STANDALONE = Path(__file__).resolve().parents[1] / "standalone"
sys.path.insert(0, str(STANDALONE))
from p3sim import authored_pouches  # noqa: E402


class TemplateSpawnerTests(unittest.TestCase):
    def test_bed_contract(self):
        self.assertEqual(
            authored_pouches.EXPECTED_BEDS,
            ("bed_a1", "bed_a2", "bed_a3", "bed_a4", "bed_b1", "bed_b2", "bed_b3", "bed_b4", "bed_b5", "bed_b6"),
        )

    def test_order_id_becomes_safe_unique_prim_name(self):
        self.assertEqual(authored_pouches.TemplateSpawner._safe_name("ord-0001/x"), "ord_0001_x")

    def test_the_pouch_qr_carries_the_order_id_not_the_bed(self):
        """계약 161·270·649줄: 봉투 QR = order_id. 팔이 goal order_id 와 대조한다(#501 은 bed_id 를 넣었다)."""
        try:
            from pxr import Sdf, Usd, UsdGeom, UsdPhysics
        except ImportError:
            self.skipTest("usd-core not installed")
        stage = Usd.Stage.CreateInMemory()
        UsdGeom.Xform.Define(stage, "/World")
        template = UsdGeom.Xform.Define(stage, "/World/PouchTemplate").GetPrim()
        UsdPhysics.RigidBodyAPI.Apply(template)
        UsdGeom.Mesh.Define(stage, "/World/PouchTemplate/QR")
        captured = []
        original = authored_pouches.bind_qr
        authored_pouches.bind_qr = lambda _stage, path, payload, _out: captured.append((path, payload))
        try:
            spawner = authored_pouches.TemplateSpawner(stage, "/World/PouchTemplate")
            path = spawner.spawn("ord-0007", "bed_b1", (0.0, 0.0, 0.5), "/tmp/unused")
        finally:
            authored_pouches.bind_qr = original
        self.assertEqual([(path, "ord-0007")], captured)
        prim = stage.GetPrimAtPath(path)
        self.assertEqual("bed_b1", prim.GetAttribute("p3:bedId").Get())
        self.assertEqual("ord-0007", prim.GetAttribute("p3:orderId").Get())
        self.assertIsInstance(Sdf.Path(path), Sdf.Path)


if __name__ == "__main__":
    unittest.main()
