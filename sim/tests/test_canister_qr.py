"""약통 QR 면·M0609 손 카메라(카드 Q1)의 순수 부분. Isaac 없이 돈다. Isaac 쪽은 L3 미실행이다."""
import importlib.util
import sys
import unittest
from pathlib import Path

STANDALONE = Path(__file__).resolve().parents[1] / "standalone"
REPO = STANDALONE.parents[1]
sys.path.insert(0, str(STANDALONE))
sys.path.insert(0, str(REPO / "src" / "rokey_p3_manipulation"))
from p3sim import amr_base, canister_qr, layout_v2  # noqa: E402

CATALOG = (REPO / "src" / "rokey_p3_orchestrator" / "config" / "pharmacy_catalog.yaml").read_text(encoding="utf-8")


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _sub(a, b):
    return tuple(x - y for x, y in zip(a, b, strict=True))


def _stage():
    spec = importlib.util.spec_from_file_location("pharmacy_stage_canister_qr", STANDALONE / "pharmacy_stage.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _hospital_cells():
    import json

    data = json.loads((REPO / "experiments" / "fixtures" / "hospital-integrated-09" / "workcell.json").read_text())
    return data["cells"]


def _grip_z(cell):
    """M0609 이 잡는 점의 높이(약통 로컬 z). scene_v2.pick_points 와 같은 규칙."""
    from rokey_p3_manipulation import scene_v2

    params = scene_v2.DEFAULT_PARAMS
    return cell["height"] / 2.0 - params.cylinder_grip if cell["type"] == "cylinder" else params.module_grip_up


def _all_cells():
    _boxes, cells = layout_v2.shelves(layout_v2.default_v2())
    return {**cells, **_hospital_cells()}


class Faces(unittest.TestCase):
    """재범 9/23 정정: QR 은 몸통 앞(통로 쪽 -y)의 스티커다. 원통은 옆면 곡면, 모듈은 앞면, 두께 ≤ 1 mm."""

    @classmethod
    def setUpClass(cls):
        _boxes, cls.cells = layout_v2.shelves(layout_v2.default_v2())
        cls.hospital = _hospital_cells()

    def test_every_stage_cell_gets_its_catalog_id(self):
        containers = canister_qr.shelf_containers(CATALOG)
        self.assertTrue(set(self.cells) <= set(containers))          # 병원 워크셀 칸도 함께 있다
        self.assertTrue(set(self.hospital) <= set(containers))
        self.assertEqual(containers["shelf_72/r0c0"], "cn-0211")     # 병원 만료 칸(칸 이름에 숫자)
        self.assertEqual(containers["floor_right/r0c1"], "cn-0106")      # 만료 칸

    def test_hospital_cells_get_only_the_front_sticker(self):
        for cell_id, cell in self.hospital.items():
            self.assertEqual([name for name, _mesh in canister_qr.cell_faces(cell)], ["front"], cell_id)

    def test_top_face_only_where_the_cell_is_open_above(self):
        for cell_id, cell in self.cells.items():
            names = [name for name, _mesh in canister_qr.cell_faces(cell)]
            self.assertEqual("top" in names, cell["access"] == "top", cell_id)

    def test_sticker_is_on_the_aisle_side_and_flush(self):
        for cell_id, cell in _all_cells().items():
            points, normals, _st, _counts, _indices = canister_qr.sticker_mesh(cell)
            for point, normal in zip(points, normals, strict=True):
                self.assertLess(point[1], 0.0, cell_id)                   # 통로 쪽(-y)
                self.assertLess(normal[1], 0.0, cell_id)                  # 밖을 본다
                if cell["type"] == "cylinder":
                    radius = (point[0] ** 2 + point[1] ** 2) ** 0.5
                    lift = radius - cell["size"]["diameter"] / 2.0
                else:
                    lift = -cell["size"]["y"] / 2.0 - point[1]
                self.assertGreater(lift, 0.0, cell_id)
                self.assertLessEqual(lift, 0.001, cell_id)                # 따로 된 판이 아니다(≤ 1 mm)
                self.assertLessEqual(abs(point[2]), cell["height"] / 2.0 - canister_qr.STICKER_EDGE_MARGIN + 1e-9)

    def test_sticker_is_not_mirrored_seen_from_the_aisle(self):
        for cell_id, cell in _all_cells().items():
            points, _normals, st, counts, indices = canister_qr.sticker_mesh(cell)
            at = 0
            for count in counts:
                quad = [points[i] for i in indices[at:at + count]]
                uv = [st[i] for i in indices[at:at + count]]
                at += count
                winding = _cross(_sub(quad[1], quad[0]), _sub(quad[2], quad[0]))
                self.assertLess(winding[1], 0.0, cell_id)                 # 감긴 방향 = -y(밖)
                self.assertGreater(quad[1][0], quad[0][0], cell_id)       # u 가 +x(통로에서 본 오른쪽)
                self.assertGreater(uv[1][0], uv[0][0], cell_id)
                self.assertGreater(quad[2][2], quad[1][2], cell_id)       # v 가 +z(위)

    def test_sticker_centre_is_below_the_grip_by_the_camera_offset(self):
        """앞 접근에서 link_6 +y 는 월드 -z 다 → 카메라 축은 잡는 점보다 0.0483 m **아래**. 부호를 여기서 고정한다."""
        from rokey_p3_manipulation import m0609_kinematics as kin
        from rokey_p3_manipulation import scene_v2

        down = kin.rotate(scene_v2.FRONT, (0.0, 1.0, 0.0))
        for got, want in zip(down, (0.0, 0.0, -1.0), strict=True):
            self.assertAlmostEqual(got, want)
        for cell_id, cell in self.hospital.items():
            axis = _grip_z(cell) - canister_qr.M0609_CAMERA_T[1]
            centre = canister_qr.sticker_center_z(cell)
            half = canister_qr.sticker_side(cell) / 2.0
            self.assertLess(centre, _grip_z(cell), cell_id)
            self.assertLessEqual(abs(centre - axis), half, cell_id)       # 카메라 축이 스티커를 지난다
        cylinder = next(c for c in self.hospital.values() if c["type"] == "cylinder")
        self.assertAlmostEqual(canister_qr.sticker_center_z(cylinder), 0.06 - 0.02 - 0.0483)
        module = next(c for c in self.hospital.values() if c["type"] == "module")
        self.assertAlmostEqual(canister_qr.sticker_center_z(module), 0.03 - 0.0483)

    def test_stage_grip_heights_match_the_planner(self):
        from rokey_p3_manipulation import scene_v2

        self.assertEqual(canister_qr.CYLINDER_GRIP_BELOW_TOP, scene_v2.DEFAULT_PARAMS.cylinder_grip)
        self.assertEqual(canister_qr.MODULE_GRIP_ABOVE_CENTRE, scene_v2.DEFAULT_PARAMS.module_grip_up)

    def test_hand_camera_sits_as_high_above_the_shelf_for_both_kinds(self):
        """94f19fb: 모듈 가운데를 잡으면 카메라가 선반면 2.2 cm 위라 가로보에 가렸다. 두 종류 모두 5 cm 위여야 한다."""
        for cell_id, cell in self.hospital.items():
            camera_above_shelf = cell["height"] / 2.0 + _grip_z(cell) - canister_qr.M0609_CAMERA_T[1]
            self.assertGreater(camera_above_shelf, 0.05, cell_id)
            bottom = cell["height"] / 2.0 + canister_qr.sticker_center_z(cell) - canister_qr.sticker_side(cell) / 2.0
            self.assertGreater(bottom, 0.03, cell_id)                     # 스티커 아래 끝도 선반면 3 cm 위

    def test_cylinder_sticker_wraps_at_most_70_degrees(self):
        for cell in _all_cells().values():
            if cell["type"] == "cylinder":
                angle = canister_qr.CYLINDER_STICKER_SIDE / (cell["size"]["diameter"] / 2.0)
                self.assertLess(angle, 70.0 * 3.141592653589793 / 180.0)


class Camera(unittest.TestCase):
    def test_mount_follows_link_6_and_looks_along_its_z(self):
        position, quat = canister_qr.camera_world_pose((0.0, 0.0, 0.0), (1.0, 0.0, 0.0, 0.0))
        for got, want in zip(position, canister_qr.M0609_CAMERA_T, strict=True):
            self.assertAlmostEqual(got, want)
        look = canister_qr._quat_rotate(quat, (0.0, 0.0, -1.0))     # USD 카메라 시선 = -Z
        for got, want in zip(look, (0.0, 0.0, 1.0), strict=True):
            self.assertAlmostEqual(got, want)

    def test_mount_moves_with_the_link(self):
        yaw90 = (0.7071068, 0.0, 0.0, 0.7071068)
        position, _ = canister_qr.camera_world_pose((1.0, 2.0, 3.0), yaw90)
        for got, want in zip(position, (1.0 - 0.0483, 2.0, 3.0185), strict=True):
            self.assertAlmostEqual(got, want, places=5)

    def test_intrinsics_match_the_d455_colour_camera(self):
        self.assertEqual(canister_qr.M0609_CAMERA_FOCAL_MM, amr_base.GRIPPER_CAMERA_FOCAL_MM)
        self.assertEqual(canister_qr.M0609_CAMERA_H_APERTURE_MM, amr_base.GRIPPER_CAMERA_H_APERTURE_MM)


class QrPixels(unittest.TestCase):
    """잡기 직전(grasp_pose) 카메라 → 스티커 거리 = link_6→TCP 0.19671 − 카메라 앞섬 0.0185 − (잡는 점 → 앞면).

    원통은 잡는 점이 중심(y)이라 반지름, 모듈은 잡는 점이 중심 − 0.04 라 0.05 − 0.04. 계산이고 L3 미확인이다.
    곡면 스티커는 정면에서 본 폭이 펼친 길이보다 좁아(원통 약 0.95배) 세로 한 변으로 잰다.
    """

    def distance(self, cell):
        to_face = cell["size"]["diameter"] / 2.0 if cell["type"] == "cylinder" else cell["size"]["y"] / 2.0 - 0.04
        return 0.19671 - canister_qr.M0609_CAMERA_T[2] - to_face

    def test_960_wide_reaches_80_px_on_both_hospital_kinds(self):
        cells = _hospital_cells()
        for kind, want in (("cylinder", 96.0), ("module", 88.0)):
            cell = next(c for c in cells.values() if c["type"] == kind)
            pixels = amr_base.qr_code_pixels(canister_qr.sticker_side(cell), self.distance(cell), 960)
            self.assertGreaterEqual(pixels, 80.0, kind)
            self.assertAlmostEqual(pixels, want, delta=1.0)


class StageFlags(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.stage = _stage()

    def test_off_by_default(self):
        args = self.stage.parse_args([])
        self.assertIsNone(args.canister_qr_dir)
        self.assertFalse(args.m0609_hand_camera)
        self.assertEqual(args.m0609_camera_resolution, [960, 600])

    def test_qr_dir_needs_the_catalog(self):
        args = self.stage.parse_args(["--canister-qr-dir", "/tmp/qr"])
        self.assertIn("--canister-qr-dir needs --catalog", " ".join(self.stage.validate(args)))

    def test_camera_needs_the_robot(self):
        args = self.stage.parse_args(["--m0609-hand-camera"])
        self.assertIn("--m0609-hand-camera needs --robot-usd", " ".join(self.stage.validate(args)))


if __name__ == "__main__":
    unittest.main()


@unittest.skipUnless(importlib.util.find_spec("pxr"), "requires USD Python (Isaac or usd-core)")
class D455Body(unittest.TestCase):
    """M0609 손 카메라의 보이는 몸체(재범 9/23). 모델의 컬러 카메라가 우리 카메라와 겹치고, 물리가 없어야 한다."""

    @classmethod
    def setUpClass(cls):
        from pxr import Gf, Usd, UsdGeom

        cls.Gf, cls.Usd, cls.UsdGeom = Gf, Usd, UsdGeom
        stage = Usd.Stage.CreateInMemory()
        camera = UsdGeom.Camera.Define(stage, "/Stage/M0609HandCamera")
        # 아무 자세에나 둔다(스테이지는 link_6 × 장착값으로 매 스텝 옮긴다).
        camera.AddTranslateOp().Set(Gf.Vec3d(0.3, -1.2, 0.9))
        camera.AddOrientOp().Set(Gf.Quatf(0.2705981, 0.6532815, -0.2705981, 0.6532815))
        cls.stage = stage
        cls.model = canister_qr.attach_d455_model(stage, "/Stage/M0609HandCamera", amr_base.gripper_usd_path())

    def test_model_colour_camera_coincides_with_ours(self):
        cache = self.UsdGeom.XformCache()
        ours = cache.GetLocalToWorldTransform(self.stage.GetPrimAtPath("/Stage/M0609HandCamera"))
        theirs = cache.GetLocalToWorldTransform(
            self.stage.GetPrimAtPath(f"{self.model}/{canister_qr.D455_COLOR_CAMERA}"))
        delta = theirs * ours.GetInverse()
        for value in delta.ExtractTranslation():
            self.assertAlmostEqual(value, 0.0, places=5)
        self.assertAlmostEqual(abs(delta.ExtractRotationQuat().GetReal()), 1.0, places=5)

    def test_model_is_a_child_so_it_follows_and_has_no_physics(self):
        self.assertTrue(self.model.startswith("/Stage/M0609HandCamera/"))
        for prim in self.Usd.PrimRange(self.stage.GetPrimAtPath(self.model)):
            applied = " ".join(prim.GetAppliedSchemas())
            self.assertNotIn("Collision", applied, prim.GetPath())
            self.assertNotIn("RigidBody", applied, prim.GetPath())

    def test_no_camera_or_render_product_left_active_in_the_model(self):
        """재범 9/23: 카메라 목록에 컬러만. M0609 는 우리 카메라가 찍으니 모델 안 카메라 넷은 다 끈다."""
        active = [str(p.GetPath()) for p in self.Usd.PrimRange(self.stage.GetPrimAtPath(self.model))
                  if p.IsA(self.UsdGeom.Camera) or p.GetName() == "TemplateRenderProducts"]
        self.assertEqual(active, [])
        self.assertTrue(self.stage.GetPrimAtPath("/Stage/M0609HandCamera").IsA(self.UsdGeom.Camera))

    def test_gripper_materials_use_only_builtin_mdl(self):
        """그리퍼·D455 재질은 Isaac 내장 MDL 이름만 쓴다.
        9/30: D455 재질 셋이 `./omniverse-content-production…` 상대 경로라 MDL 을 못 찾아 몸체가 빨갛게 보였다
        (인터넷 주소의 `https:/` 가 빠진 채 내보내졌다)."""
        asset = self.Usd.Stage.Open(amr_base.gripper_usd_path())
        sources = []
        for prim in asset.Traverse():
            attr = prim.GetAttribute("info:mdl:sourceAsset")
            if attr and attr.Get() is not None:
                sources.append((str(prim.GetPath()), attr.Get().path))
        self.assertTrue(sources)
        for prim, source in sources:
            self.assertIn(source, ("OmniPBR.mdl", "OmniGlass.mdl"), prim)

    def test_amr_gripper_turns_off_every_d455_camera_but_colour(self):
        """합본 손목 그리퍼(amr_base.add_hand_camera)가 끄는 경로가 자산에 다 있고, 남는 카메라는 컬러 하나다."""
        asset = self.Usd.Stage.Open(amr_base.gripper_usd_path())
        root = asset.GetPrimAtPath(amr_base.GRIPPER_ASSET_PRIM)
        for name in amr_base.GRIPPER_PRIMS_OFF:
            self.assertTrue(root.GetPrimAtPath(name).IsValid(), name)
        for name in amr_base.GRIPPER_PRIMS_OFF:
            root.GetPrimAtPath(name).SetActive(False)
        cameras = [str(p.GetPath()) for p in self.Usd.PrimRange(root) if p.IsA(self.UsdGeom.Camera)]
        self.assertEqual(cameras, [f"{amr_base.GRIPPER_ASSET_PRIM}/{amr_base.GRIPPER_COLOR_CAMERA}"])

    def test_body_is_d455_sized(self):
        box = self.UsdGeom.BBoxCache(self.Usd.TimeCode.Default(), ["default", "render"]).ComputeLocalBound(
            self.stage.GetPrimAtPath(self.model)).ComputeAlignedRange()
        self.assertEqual(sorted(round(v, 3) for v in box.GetSize())[-1], 0.124)
