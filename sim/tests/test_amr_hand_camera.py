"""AMR 합본 손 카메라(9/23)가 계약·팔 params 와 같은 이름인가. Isaac·ROS 없이 돈다.

`add_hand_camera` 자체는 Isaac 이 있어야 돈다(L3 미실행). 여기서는 이름·규약을 코드끼리 맞댄다.
"""
import importlib.util
import sys
import unittest
from pathlib import Path

STANDALONE = Path(__file__).resolve().parents[1] / "standalone"
sys.path.insert(0, str(STANDALONE))
from p3sim import amr_base  # noqa: E402


def _stage():
    spec = importlib.util.spec_from_file_location("pharmacy_stage_hand_camera", STANDALONE / "pharmacy_stage.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class HandCameraNames(unittest.TestCase):
    def test_frames_are_the_contract_optical_frame_and_the_published_wrist_link(self):
        tool, optical = amr_base.hand_camera_frames()
        self.assertEqual(optical, "amr_1/hand_camera_optical")          # 계약 2.1 손 카메라 frame
        # publish_tf 가 ur_arm_*_link 를 amr_1/<이름> 으로 낸다. 팔 tool_frame 이 이 이름이어야 관측 자세가 풀린다.
        self.assertEqual(tool, f"amr_1/{amr_base.TCP_PARENT_LINK}")
        self.assertEqual(amr_base.TCP_LOCAL_OFFSET, (0.0, 0.0, 0.0))     # 손목 = tool0 이라 IK 끝점과 같은 프레임

    def test_asset_is_in_the_repository_not_in_inbox(self):
        path = Path(amr_base.gripper_usd_path())
        self.assertTrue(path.is_file(), path)
        self.assertNotIn("inbox", path.parts)


class QrPixelBudget(unittest.TestCase):
    """9/23 카메라 L3: 한 변 58 px 에서 판독 실패. 목표는 재관측에서 한 변 ≥ 100 px(작전). 계산이고 L3 미확인이다."""

    def setUp(self):
        from p3sim import pouch

        self.face = pouch.qr_face_size((0.10, 0.07, 0.01))[0]

    def test_face_is_square_on_the_short_side(self):
        from p3sim import pouch

        self.assertEqual(pouch.qr_face_size((0.10, 0.07, 0.01)), (self.face, self.face))
        self.assertAlmostEqual(self.face, 0.056)

    def test_refine_view_reaches_100_px_at_1280_wide(self):
        # 재관측: 카메라 → 봉투 윗면 0.20 m(refine_view_standoff_m), D455 컬러 1280×800.
        self.assertGreaterEqual(amr_base.qr_code_pixels(self.face, 0.20, 1280), 100.0)

    def test_640_wide_would_not_reach_100_px_even_at_the_refine_distance(self):
        """그래서 해상도를 올린다. 거리를 더 줄이면 흡착컵(카메라 앞 0.12 m)이 봉투에 닿는다."""
        self.assertLess(amr_base.qr_code_pixels(self.face, 0.20, 640), 100.0)
        self.assertGreater(0.20 - (amr_base.GRIPPER_TCP_OFFSET[2] - 0.0355), 0.05)   # 흡착컵은 봉투 위 5 cm 넘게 뜬다


@unittest.skipUnless(importlib.util.find_spec("pxr"), "requires USD Python (Isaac or usd-core)")
class GripperAssetGeometry(unittest.TestCase):
    """자산에서 잰 값과 코드 상수가 같은가, 그리고 reference 가 attach_frame 을 손목에 겹치는가(usd-core)."""

    @classmethod
    def setUpClass(cls):
        from pxr import Gf, Sdf, Usd, UsdGeom

        cls.Gf, cls.UsdGeom = Gf, UsdGeom
        stage = Usd.Stage.CreateInMemory()
        UsdGeom.Xform.Define(stage, "/Robot")
        wrist = UsdGeom.Xform.Define(stage, f"/Robot/{amr_base.TCP_PARENT_LINK}")
        # 손목을 아무 자세에나 둔다. 붙인 결과가 손목 기준으로 같아야 한다.
        wrist.AddTranslateOp().Set(Gf.Vec3d(1.0, -2.0, 0.5))
        wrist.AddOrientOp().Set(Gf.Quatf(0.9238795, 0.0, 0.3826834, 0.0))
        gripper = stage.DefinePrim(wrist.GetPath().AppendChild(amr_base.GRIPPER_NAME), "Xform")
        gripper.GetReferences().AddReference(amr_base.gripper_usd_path(), Sdf.Path(amr_base.GRIPPER_ASSET_PRIM))
        attach = gripper.GetPrimAtPath(amr_base.GRIPPER_ATTACH_FRAME)
        xform = UsdGeom.Xformable(gripper)
        xform.ClearXformOpOrder()
        xform.AddTransformOp().Set(UsdGeom.Xformable(attach).GetLocalTransformation().GetInverse())
        cls.stage, cls.gripper, cls.attach = stage, gripper, attach
        cache = UsdGeom.XformCache()
        cls.wrist_inv = cache.GetLocalToWorldTransform(wrist.GetPrim()).GetInverse()
        cls.cache = cache

    def in_wrist(self, prim):
        return self.cache.GetLocalToWorldTransform(prim) * self.wrist_inv

    def assertVec(self, got, want, places=4):
        for g, w in zip(got, want, strict=True):
            self.assertAlmostEqual(float(g), float(w), places=places)

    def test_attach_frame_lands_on_the_wrist(self):
        m = self.in_wrist(self.attach)
        self.assertVec(m.ExtractTranslation(), (0.0, 0.0, 0.0))
        self.assertAlmostEqual(abs(m.ExtractRotationQuat().GetReal()), 1.0, places=4)

    def test_tcp_offset_is_the_suction_point(self):
        m = self.in_wrist(self.gripper.GetPrimAtPath("suction_cup"))
        self.assertVec(m.ExtractTranslation(), amr_base.GRIPPER_TCP_OFFSET)

    def test_colour_camera_looks_along_the_tool_z(self):
        prim = self.gripper.GetPrimAtPath(amr_base.GRIPPER_COLOR_CAMERA)
        self.assertTrue(prim.IsA(self.UsdGeom.Camera))
        camera = self.UsdGeom.Camera(prim)
        self.assertAlmostEqual(camera.GetFocalLengthAttr().Get(), amr_base.GRIPPER_CAMERA_FOCAL_MM, places=3)
        self.assertAlmostEqual(camera.GetHorizontalApertureAttr().Get(), amr_base.GRIPPER_CAMERA_H_APERTURE_MM,
                               places=3)
        m = self.in_wrist(prim)
        self.assertVec(m.ExtractTranslation(), (-0.0115, 0.07, 0.0355))
        look = m.ExtractRotationMatrix().GetRow(2) * -1.0          # USD 카메라 시선 = -Z
        self.assertVec(look, (0.0, 0.0, 1.0), places=3)

    def test_parts_to_switch_off_exist(self):
        for name in (*amr_base.GRIPPER_JOINTS_OFF, *amr_base.GRIPPER_PRIMS_OFF):
            self.assertTrue(self.gripper.GetPrimAtPath(name).IsValid(), name)


class HandCameraStageWiring(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.stage = _stage()
        cls.source = (STANDALONE / "pharmacy_stage.py").read_text(encoding="utf-8")

    def test_needs_the_combined_asset(self):
        args = self.stage.parse_args(["--amr-hand-camera"])
        self.assertIn("--amr-hand-camera needs --amr --amr-combined", " ".join(self.stage.validate(args)))

    def test_off_by_default(self):
        self.assertFalse(self.stage.parse_args([]).amr_hand_camera)

    def test_the_optical_frame_moves_with_the_wrist_tf(self):
        self.assertIn("extra_dynamic=(amr_camera_optical,) if amr_camera_optical else ()", self.source)


if __name__ == "__main__":
    unittest.main()
