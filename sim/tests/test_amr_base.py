"""이동 베이스의 dummy 3축 규약. Isaac 없음.

K2 (작전 9/21, 재범 결정 (나)): Isaac 이 `/amr_1/base/joint_command` 를 받고 `/amr_1/joint_states` 를 낸다.
**odom 과 TF 는 내지 않는다** — `odom -> amr_1/base_link` 의 작성자는 base_driver 하나다(계약 3절).

여기서 잡는 것은 주행이 준 규격(9/21, base_driver_node·base_kinematics 기준)이다. 이름이 다르면 base_driver 가
경고만 내고 0 을 내며, 속도를 0 으로 채워 보내면 `base/stopped` 가 항상 참이 되어 팔 인터록이 무너진다.

    python3 -m unittest discover -s sim/tests -p 'test_[amp]*.py'
"""

import math
import sys
import unittest
from pathlib import Path

STANDALONE = Path(__file__).resolve().parents[1] / "standalone"
sys.path.insert(0, str(STANDALONE))

from p3sim import amr_base as A  # noqa: E402


class JointNames(unittest.TestCase):
    def test_exactly_the_three_the_driver_looks_for(self):
        """다르면 base_driver 가 5 s 마다 경고만 내고 0 을 낸다(주행 9/21)."""
        self.assertEqual(A.JOINT_NAMES, ("dummy_base_prismatic_x_joint",
                                         "dummy_base_prismatic_y_joint",
                                         "dummy_base_revolute_z_joint"))

    def test_the_order_is_x_y_yaw(self):
        """position·velocity 가 같은 순서여야 한다."""
        self.assertTrue(A.JOINT_NAMES[0].endswith("x_joint"))
        self.assertTrue(A.JOINT_NAMES[1].endswith("y_joint"))
        self.assertTrue(A.JOINT_NAMES[2].endswith("z_joint"))


class WrapAngle(unittest.TestCase):
    def test_it_folds_into_minus_pi_to_pi(self):
        for yaw in (0.0, 0.5, -0.5, 3.0, 3.5, -3.5, 7.0, -7.0, 100.0):
            self.assertGreaterEqual(A.wrap_angle(yaw), -math.pi)
            self.assertLess(A.wrap_angle(yaw), math.pi)

    def test_it_keeps_the_same_direction(self):
        for yaw in (0.0, 0.5, -0.5, 3.0, 7.0, -7.0):
            turns = round((yaw - A.wrap_angle(yaw)) / (2.0 * math.pi))
            self.assertAlmostEqual(A.wrap_angle(yaw) + turns * 2.0 * math.pi, yaw, places=9)

    def test_pi_folds_to_minus_pi(self):
        """반 열린 구간이라 +pi 는 -pi 로 간다. 경계에서 두 값이 나오면 안 된다."""
        self.assertAlmostEqual(A.wrap_angle(math.pi), -math.pi)
        self.assertAlmostEqual(A.wrap_angle(-math.pi), -math.pi)


class OrderCommand(unittest.TestCase):
    def test_it_picks_by_name_not_position(self):
        """주행이 순서를 바꿔 보낼 수 있다. 이름으로 고른다."""
        out = A.order_command(["dummy_base_revolute_z_joint", "dummy_base_prismatic_x_joint"], [0.3, 1.2])
        self.assertEqual(out, (1.2, 0.0, 0.3))

    def test_a_missing_joint_is_zero(self):
        self.assertEqual(A.order_command(["dummy_base_prismatic_x_joint"], [0.5]), (0.5, 0.0, 0.0))

    def test_no_velocities_means_stop(self):
        self.assertEqual(A.order_command(A.JOINT_NAMES, None), (0.0, 0.0, 0.0))

    def test_unknown_names_are_ignored(self):
        out = A.order_command(["shoulder_pan_joint", "dummy_base_prismatic_y_joint"], [9.9, 0.4])
        self.assertEqual(out, (0.0, 0.4, 0.0))


class StateMessage(unittest.TestCase):
    def test_names_and_order(self):
        names, positions, _velocities = A.state_message((1.0, 2.0, 0.0), (0.0, 0.0, 0.0))
        self.assertEqual(names, list(A.JOINT_NAMES))
        self.assertEqual(positions[:2], [1.0, 2.0])

    def test_yaw_is_wrapped(self):
        _names, positions, _velocities = A.state_message((0.0, 0.0, 7.0), None)
        self.assertAlmostEqual(positions[2], A.wrap_angle(7.0))

    def test_missing_velocity_stays_empty_and_is_never_zero_filled(self):
        """0 으로 채우면 base/stopped 가 항상 참이 되어 팔 인터록이 무너진다(주행 9/21)."""
        _names, _positions, velocities = A.state_message((0.0, 0.0, 0.0), None)
        self.assertIsNone(velocities)

    def test_given_velocities_pass_through(self):
        _names, _positions, velocities = A.state_message((0.0, 0.0, 0.0), (0.1, -0.2, 0.3))
        self.assertEqual(velocities, [0.1, -0.2, 0.3])


class Stale(unittest.TestCase):
    def test_no_command_yet_is_stale(self):
        self.assertTrue(A.stale(None, 10.0))

    def test_the_window_is_half_a_second(self):
        self.assertFalse(A.stale(9.6, 10.0))
        self.assertTrue(A.stale(9.4, 10.0))

    def test_the_boundary_is_not_stale(self):
        self.assertFalse(A.stale(9.5, 10.0))


class Drive(unittest.TestCase):
    def test_it_is_a_velocity_drive(self):
        """stiffness 0 이라 위치를 붙잡지 않는다. 목표 속도만 따라간다."""
        stiffness, damping, max_force = A.DEFAULT_DRIVE
        self.assertEqual(stiffness, 0.0)
        self.assertGreater(damping, 0.0)
        self.assertGreater(max_force, 0.0)

    def test_the_limits_cover_the_corridor(self):
        from p3sim import layout as L

        end = L.CORRIDOR["origin_x"] + L.CORRIDOR["length"]
        self.assertGreater(A.DEFAULT_LIMITS[0][1], end)
        self.assertLess(A.DEFAULT_LIMITS[0][0], L.default_layout()["ur5_base"][0])

    def test_the_command_rate_matches_the_contract(self):
        self.assertEqual(A.COMMAND_HZ, 20.0)

    def test_every_bed_approach_pose_is_reachable(self):
        """한계 밖이면 그 침상까지 못 간다. 병실을 옮기면 여기서 걸린다(9/21 실제로 걸렸다)."""
        from p3sim import layout as L

        (xmin, xmax), (ymin, ymax) = A.DEFAULT_LIMITS
        _boxes, frames = L.ward_boxes()
        for zone, poses in frames.items():
            x, y = poses["bed"][0], poses["bed"][1]
            self.assertTrue(xmin <= x <= xmax, f"{zone}: x {x} 가 {xmin}..{xmax} 밖이다")
            self.assertTrue(ymin <= y <= ymax, f"{zone}: y {y} 가 {ymin}..{ymax} 밖이다")


class GroundClearance(unittest.TestCase):
    """바닥이 지면에 닿으면 마찰이 구동을 끌고, 접촉 문턱과 같으면 로그가 `near` 줄로 찬다."""

    def test_it_is_above_the_physx_contact_offset(self):
        """PhysX 기본 contactOffset 0.02. 같으면 매 스텝 `near sep=0.0200` 이 찍힌다(실습24)."""
        self.assertGreater(A.GROUND_CLEARANCE, 0.02)

    def test_the_deck_headroom_survives_it(self):
        """위로 올릴수록 상판 밑을 지날 여유가 줄어든다. 둘 다 임시값이라 관계만 잡는다."""
        from p3sim import layout as L

        aabb = L.amr_aabb(L.full_loop_zones()["load"])
        self.assertAlmostEqual(aabb[2][0], A.GROUND_CLEARANCE, places=9)

    def test_the_body_never_starts_in_the_floor(self):
        self.assertGreater(A.GROUND_CLEARANCE, 0.0)


class AssetOrBox(unittest.TestCase):
    """`--amr-usd` 로 공식 합본을 쓰고, 없으면 지금까지의 상자를 쓴다(재범 9/21).

    **두 길이 같은 계약을 지켜야 한다**: 같은 관절 이름 셋, 같은 속도 드라이브, 같은 반환 모양.
    다른 것은 링크·충돌체·팔을 우리가 만드는가 자산이 주는가뿐이다.
    """

    def setUp(self):
        sys.path.insert(0, str(STANDALONE))
        import pharmacy_stage

        self.stage = pharmacy_stage
        self.source = (STANDALONE / "p3sim/amr_base.py").read_text()

    def test_the_box_is_the_default(self):
        """경로가 기계마다 달라 기본값이 없다. 안 주면 지금까지와 같다."""
        self.assertIsNone(self.stage.parse_args(["--amr"]).amr_combined)
        self.assertIsNone(self.stage.parse_args(["--preset", "emptyworld-loop"]).amr_combined)

    def test_both_paths_return_the_same_shape(self):
        """반환이 다르면 부르는 쪽이 갈라진다."""
        for name in ("def build(", "def reference("):
            self.assertIn(name, self.source)
        self.assertEqual(self.source.count("return (roots[0] if roots else root, root, list(JOINT_NAMES))"), 1)
        self.assertIn('return (f"{root}/root_joint", str(body.GetPath()), list(JOINT_NAMES))', self.source)

    def test_the_asset_drive_is_overwritten_with_ours(self):
        """자산이 들고 온 게인이 다르면 같은 속도 명령에 다른 응답을 낸다.

        주행의 추종 파라미터는 **상자에서 맞춘 값**이고 추종기는 질량·관성을 모른다(주행 9/21).
        덮기 전 값을 로그에 남겨 무엇이 달랐는지 보이게 한다.
        """
        self.assertIn("api.CreateStiffnessAttr(float(drive[0]))", self.source)
        self.assertIn("asset_was=", self.source)

    def test_a_missing_dummy_joint_stops_the_run(self):
        """이름이 없으면 주행 규격을 못 지킨다 — 조용히 넘어가면 안 된다."""
        self.assertIn("not found under", self.source)
        self.assertIn("raise RuntimeError", self.source)

    def test_the_articulation_path_is_not_hardcoded(self):
        """상자는 `{root}/root_joint`, 합본은 자산이 정한 자리다."""
        self.assertIn("articulation_path or f\"{root}/root_joint\"", self.source)
        self.assertIn("articulation_path=art_path", (STANDALONE / "pharmacy_stage.py").read_text())

    def test_more_than_one_articulation_root_is_called_out(self):
        """하나여야 베이스와 팔이 한 몸이다. 둘이면 구동 경로 설계가 달라진다."""
        self.assertIn("WARN amr articulation roots=", self.source)


class AssetFacts(unittest.TestCase):
    """합본 자산에서 **런타임으로 읽은** 사실(맥마클2 탐침 9/21). #408 은 USD 를 읽은 값이고 이것은 런타임 값이다.

    여기 적힌 것이 틀리면 내 코드가 통째로 틀린다 — 그래서 값으로 박아 둔다. 자산이 바뀌면 여기가 먼저 걸린다.
    """

    def test_the_arm_joint_names_carry_the_asset_prefix(self):
        """계약 97줄 "USD 조인트 이름 그대로". 번역하지 않는다 — 실물로 갈 때 또 번역해야 한다."""
        self.assertEqual(A.ARM_JOINT_NAMES,
                         ("ur_arm_shoulder_pan_joint", "ur_arm_shoulder_lift_joint", "ur_arm_elbow_joint",
                          "ur_arm_wrist_1_joint", "ur_arm_wrist_2_joint", "ur_arm_wrist_3_joint"))

    def test_the_pedestal_ur5_names_are_different(self):
        """받침대 UR5 는 접두가 없다. 두 구성이 **다른 이름**을 쓰는 것이 맞다."""
        from p3sim import ur5_cell as U

        self.assertEqual(len(A.ARM_JOINT_NAMES), len(U.UR5_JOINTS))
        self.assertEqual(set(A.ARM_JOINT_NAMES) & set(U.UR5_JOINTS), set())
        for asset, plain in zip(A.ARM_JOINT_NAMES, U.UR5_JOINTS, strict=True):
            self.assertEqual(asset, "ur_arm_" + plain)

    def test_the_asset_has_nine_dofs_and_no_gripper(self):
        self.assertEqual(len(A.ASSET_DOF_NAMES), 9)
        self.assertEqual(A.ASSET_DOF_NAMES[:3], A.JOINT_NAMES)
        self.assertFalse([n for n in A.ASSET_DOF_NAMES if "grip" in n or "finger" in n])

    def test_there_is_no_tool0_prim_so_the_tcp_hangs_off_the_wrist(self):
        """탐침 4번: `tool0`·flange·ee 프림이 없다. 받침대 UR5 는 `tool0` 을 IK 프레임으로 쓴다."""
        self.assertEqual(A.TCP_PARENT_LINK, "ur_arm_wrist_3_link")
        self.assertNotIn("tool0", A.TCP_PARENT_LINK)

    def test_the_deck_goes_on_the_base_body_not_the_travel_chain(self):
        """`world`·`dummy_base_*` 는 이동 사슬이다. 상판은 그 위의 몸체에 얹는다."""
        self.assertEqual(A.DECK_PARENT_LINK, "base_link")
        self.assertNotIn(A.DECK_PARENT_LINK, A.JOINT_NAMES)


class WorldAnchor(unittest.TestCase):
    """합본은 `body0` 가 빈 FixedJoint 로 월드에 박혀 있다(탐침 3번) — 받침대 UR5 와 같은 모양이다.

    **프림을 옮기는 것만으로는 로봇이 안 따라온다.** `localPos0` 가 월드 좌표라 그 값을 같이 옮겨야 한다.
    이것을 안 하면 AMR 이 늘 원점에서 시작하고, 그 실패는 "왜 도크에 없나" 로 나타난다.
    """

    def test_the_reference_path_moves_the_anchor(self):
        source = (STANDALONE / "p3sim/amr_base.py").read_text()
        self.assertIn("def pin_world_joints(", source)
        self.assertIn("pinned = pin_world_joints(stage, root,", source)

    def test_it_says_so_when_there_is_no_anchor(self):
        """없는 자산도 있을 수 있다. 조용히 넘어가면 어느 쪽인지 모른다."""
        source = (STANDALONE / "p3sim/amr_base.py").read_text()
        self.assertIn("no world-anchored joint found", source)

    def test_instance_proxies_are_reported_not_skipped_silently(self):
        source = (STANDALONE / "p3sim/amr_base.py").read_text()
        self.assertIn("instance proxy", source)


class ArmBaseFrameOrigin(unittest.TestCase):
    """**축은 고르고 원점은 잰다**(비전 9/21). 자산에 `ur_arm_base_link` 링크가 없어 우리가 만드는데,

    AMR 몸체 원점에 그냥 얹으면 장착 오프셋만큼 전부 어긋난다. 증상은 27b(z 180°)처럼 **조용하고**,
    부호가 뒤집히지도 않아 **더 알아보기 어렵다.** 원점은 어깨에서 `d1` 내린 자리다.
    """

    def setUp(self):
        self.source = (STANDALONE / "p3sim/amr_base.py").read_text()

    def test_d1_matches_the_arm_sessions_dh_table(self):
        """`ur5_kinematics` 의 첫 행과 같아야 한다 — 두 벌이면 한쪽만 고쳐진다."""
        table = (Path(__file__).resolve().parents[2]
                 / "src/rokey_p3_manipulation/rokey_p3_manipulation/ur5_kinematics.py")
        if not table.is_file():
            self.skipTest("팔 기구학이 없다")
        import re

        first = re.search(r"\(([0-9.]+), 0\.0, math\.pi / 2\.0\)", table.read_text())
        self.assertIsNotNone(first, "DH 첫 행을 못 읽었다")
        self.assertAlmostEqual(A.UR5_D1, float(first.group(1)), places=9)

    def test_the_origin_is_measured_from_the_shoulder_not_the_body(self):
        self.assertIn("local[2] - UR5_D1", self.source)
        self.assertIn("SHOULDER_LINK", self.source)

    def test_it_refuses_to_build_when_the_shoulder_cannot_be_found(self):
        """자리를 모르는 채 만드는 것이 이 함수가 막으려는 실수다."""
        self.assertIn("arm_base_frame not built", self.source)
        self.assertIn("return None", self.source)

    def test_the_frame_name_is_the_decided_one(self):
        self.assertEqual(A.ARM_BASE_FRAME, "ur_arm_base_link")
        self.assertIn('CreateAttribute("isaac:nameOverride"', self.source)


class ArmBaseAxis(unittest.TestCase):
    """밑동 프레임의 **축**. 원점과 달리 이것은 관례를 고르는 것이고, 고른 관례가 틀리면 27b 가 되풀이된다.

    탐침 3(맥마클2 9/21): 어깨 프레임 = `Rz(pi + pan)` 이고 세 자세(pan −0.0001·0.2999·−0.5001) 모두
    **1e-5 안에서** 맞았다. 그래서 pan = 0 일 때 밑동은 `Rz(pi)` 다 — UR URDF `base_link` 관례다.
    """

    def test_the_yaw_is_a_half_turn(self):
        self.assertAlmostEqual(A.ARM_BASE_YAW, math.pi, places=12)

    def test_the_shoulder_convention_holds_at_the_measured_poses(self):
        """관측 쿼터니언(w, z)이 `Rz(pi + pan)` 과 맞는지 다시 계산한다. 자산이 바뀌면 여기가 걸린다."""
        measured = ((-0.000137, 7.5e-05, 1.0), (0.299935, -0.149422, 0.988774), (-0.50011, 0.247469, 0.968896))
        for pan, w, z in measured:
            angle = A.ARM_BASE_YAW + pan
            self.assertAlmostEqual(math.cos(angle / 2.0), w, places=4, msg=f"pan={pan}")
            self.assertAlmostEqual(math.sin(angle / 2.0), z, places=4, msg=f"pan={pan}")

    def test_the_stage_actually_applies_it(self):
        source = (STANDALONE / "p3sim/amr_base.py").read_text()
        self.assertIn("api.SetRotate(Gf.Vec3f(0.0, 0.0, math.degrees(ARM_BASE_YAW)))", source)


class DeckRidesTheBase(unittest.TestCase):
    """상판은 **베이스 링크의 자식 충돌체**여야 한다. `FixedCuboid` 는 월드 고정이라 AMR 이 가도 남는다."""

    def setUp(self):
        import pharmacy_stage

        from p3sim import layout as L

        self.room = pharmacy_stage.ROOM
        self.boxes, self.slots = L.tray_boxes(A.ASSET_BASE_TOP_Z)

    def extent(self, axis):
        lows = [b.center[axis] - b.size[axis] / 2.0 for b in self.boxes]
        highs = [b.center[axis] + b.size[axis] / 2.0 for b in self.boxes]
        return (min(lows), max(highs))

    def test_it_sits_on_the_body_top_not_floating_or_sunk(self):
        self.assertAlmostEqual(self.extent(2)[0], A.ASSET_BASE_TOP_Z, places=6)

    def test_it_stays_inside_the_body_footprint(self):
        """밖으로 나가면 통로 여유 계산이 틀리고 문틀에 걸린다."""
        from p3sim import layout as L

        length, width = L.AMR_BBOX
        for axis, size in ((0, length), (1, width)):
            low, high = self.extent(axis)
            self.assertGreaterEqual(low, -size / 2.0 - 1e-6, f"axis {axis}")
            self.assertLessEqual(high, size / 2.0 + 1e-6, f"axis {axis}")

    def test_the_bbox_matches_what_the_probe_measured(self):
        """`AMR_BBOX` 는 실측 표에서 왔고 탐침 3 의 런타임 bbox 와 같아야 한다."""
        from p3sim import layout as L

        self.assertAlmostEqual(L.AMR_BBOX[0], 0.4618 - (-0.4707), places=4)
        self.assertAlmostEqual(L.AMR_BBOX[1], 0.3964 - (-0.3968), places=4)
        self.assertAlmostEqual(A.ASSET_BASE_TOP_Z - A.ASSET_BASE_BOTTOM_Z, 0.32717, places=4)

    def test_every_slot_is_within_the_arm_reach(self):
        """어깨에서 2R 로 편 길이 0.817. 넘으면 팔이 자기 상판에 못 닿는다."""
        shoulder = (0.0, 0.0, A.ASSET_SHOULDER_Z)
        for slot in self.slots:
            reach = math.dist(shoulder, slot)
            self.assertLess(reach, 0.817, f"slot {slot} at {reach:.3f}")

    def test_the_deck_does_not_sit_under_the_arm_column(self):
        """팔 밑동 바로 아래에 두면 아래로 접을 때 반드시 닿는다(받침대 기둥에서 겪었다).

        밑동은 이제 원점이 아니라 `ARM_MOUNT_LOCAL` 이다 — 원점에서 재면 옮기기 전 자리를 보게 된다.
        """
        for slot in self.slots:
            away = math.hypot(slot[0] - A.ARM_MOUNT_LOCAL[0], slot[1] - A.ARM_MOUNT_LOCAL[1])
            self.assertGreater(away, 0.15, f"slot {slot}")

    def test_it_is_not_a_world_fixed_cuboid(self):
        source = (STANDALONE / "p3sim/amr_base.py").read_text()
        self.assertIn("UsdPhysics.CollisionAPI.Apply(cube.GetPrim())", source)
        # 상판을 만드는 함수 안에서는 FixedCuboid 를 쓰지 않는다(주석에는 왜 못 쓰는지가 적혀 있다).
        body = source[source.index("def build_tray_on_base("):source.index("def publish_tf(")]
        self.assertNotIn("FixedCuboid(", body)

    def test_the_slots_come_back_in_local_coordinates(self):
        """빌드 때 세계 좌표를 굳히면 AMR 이 움직인 뒤 판정이 틀린다."""
        source = (STANDALONE / "p3sim/amr_base.py").read_text()
        self.assertIn("base_link 로컬 좌표", source)


class SuctionTcpFrame(unittest.TestCase):
    """`wrist_3_link` → 팔 기구학 끝점(`tool0`)이 **항등**이다 — 비전이 자세 세 벌로 역산했다(9/21).

    표준 URDF 라면 `d6 = 0.0823` 만큼 떨어져 있어야 한다. **추측했으면 8.2 cm 를 틀렸다.**
    이것은 이 자산·이 탐침의 값이다 — 자산이 바뀌면 다시 재야 한다.
    """

    def test_the_offset_is_identity(self):
        self.assertEqual(A.TCP_LOCAL_OFFSET, (0.0, 0.0, 0.0))

    def test_it_is_not_the_standard_urdf_d6(self):
        """0.0823 이 들어 있으면 누가 '표준이니까' 로 되돌린 것이다."""
        self.assertNotAlmostEqual(A.TCP_LOCAL_OFFSET[2], 0.0823, places=4)

    def test_the_reason_is_recorded_not_just_the_value(self):
        """'항등' 만 적혀 있으면 다음 사람이 자산이 바뀌어도 그대로 믿는다."""
        source = (STANDALONE / "p3sim/amr_base.py").read_text()
        for needle in ("재서 확인했다", "세 벌", "자산이 바뀌면 다시 재야 한다"):
            self.assertIn(needle, source, needle)


class DeckIsCloseNotFar(unittest.TestCase):
    """합본에서는 걱정이 **"너무 멀다" 에서 "너무 가깝다" 로 뒤집혔다**(비전 9/21).

    받침대에서는 바깥 칸이 어깨에서 0.740 m(편 길이의 87 %)라 **뻗은 자세**가 문제였다(실습23).
    합본에서는 전부 0.26–0.41 m 다. IK 는 다 풀리고 `sin|q3|` 도 0.73 이상이라 특이점은 아니지만,
    **자기 충돌(밑동·어깨 ↔ 팔꿈치)은 아무도 오프라인으로 확인할 수 없다** — 합본 충돌 모델이 없다.
    L3 에서 볼 항목이다. 여기서는 그 구간에 있다는 것만 잡는다.
    """

    def setUp(self):
        import pharmacy_stage

        from p3sim import layout as L

        _boxes, self.slots = L.deck_boxes(A.DECK_LOCAL_CENTRE, 5, pharmacy_stage.ROOM["deck_slot_size"],
                                          pharmacy_stage.ROOM["deck_wall"])
        self.shoulder = (0.0, 0.0, A.ASSET_SHOULDER_Z)

    def distances(self):
        return [math.dist(self.shoulder, slot) for slot in self.slots]

    def test_nothing_is_near_the_reach_limit(self):
        """받침대에서 팔이 무너진 구간(편 길이의 98.9 %)과는 반대쪽이다."""
        self.assertLess(max(self.distances()), 0.5)

    def test_nothing_is_so_close_that_the_arm_folds_into_itself(self):
        """너무 가까우면 팔꿈치가 몸통으로 접힌다. 여유를 관계로 잡는다."""
        self.assertGreater(min(self.distances()), 0.2)

    def test_the_log_carries_the_distances(self):
        """L3 에서 자기 충돌을 볼 때 이 수치가 기준이 된다."""
        source = (STANDALONE / "p3sim/amr_base.py").read_text()
        self.assertIn("shoulder_distance=", source)


class NineJointsInOneMessage(unittest.TestCase):
    """계약 97줄: `/amr_1/joint_states` 는 **한 메시지에 dummy 3 + UR5 6**.

    상자 구성에서는 발행자가 둘이었다(베이스 3 과 UR5 6 이 따로). 합본은 한 articulation 이라 한 번에
    읽혀 그 문제가 사라진다.
    """

    def setUp(self):
        self.source = (STANDALONE / "p3sim/amr_base.py").read_text()
        self.stage_source = (STANDALONE / "pharmacy_stage.py").read_text()

    def test_read_all_returns_base_then_arm(self):
        self.assertIn("order = list(self.indices) + list(self.arm_indices)", self.source)
        self.assertIn("names = list(JOINT_NAMES) + (list(ARM_JOINT_NAMES) if self.arm_indices else [])",
                      self.source)

    def test_the_yaw_is_still_wrapped(self):
        """base_driver 가 그대로 odom yaw 로 쓴다."""
        self.assertIn("out_positions[2] = wrap_angle(out_positions[2])", self.source)

    def test_velocity_is_still_never_zero_filled(self):
        self.assertIn("None if velocities is None else", self.source)

    def test_the_stage_publishes_one_message(self):
        self.assertIn("names, ordered, vel = amr.read_all()", self.stage_source)

    def test_the_box_setup_reports_only_three(self):
        """상자에는 팔이 없다. 그때는 세 개짜리 메시지가 맞다."""
        self.assertIn("if all(n in names for n in ARM_JOINT_NAMES) else []", self.source)

    def test_unknown_arm_names_are_counted_not_dropped_silently(self):
        """계약 186절: 자기 이름만. 섞여 오면 세어 둔다 — 조용히 버리면 왜 안 움직이는지 모른다."""
        self.assertIn("return (len(chosen), unknown)", self.source)
        self.assertIn("amr arm_command unknown names=", self.stage_source)


class OnlyOneArm(unittest.TestCase):
    """합본은 자기 팔을 들고 온다. 받침대 UR5 를 같이 만들면 **팔이 둘**이 된다.

    그러면 `/amr_1/arm/joint_command` 의 수신자가 갈라진다 — 받침대는 접두 없는 이름, 합본은 `ur_arm_*` 다.
    이름이 다르니 한쪽은 늘 "다른 쪽 이름" 으로 버려지고, **어느 팔이 안 움직이는지는 로그를 봐야만** 안다.
    """

    def setUp(self):
        self.source = (STANDALONE / "pharmacy_stage.py").read_text()

    def test_the_pedestal_arm_is_not_built_with_the_asset(self):
        self.assertIn("if args.ur5 and not args.amr_combined:", self.source)

    def test_it_says_why(self):
        """조용히 안 만들면 "왜 받침대가 없나" 를 찾게 된다."""
        self.assertIn("ur5 pedestal disabled reason=--amr-combined", self.source)

    def test_the_pedestal_bridge_is_skipped_too(self):
        """브리지만 남으면 아무도 안 받는 토픽이 생긴다."""
        gate = "if args.ur5 and not args.amr_combined:"
        self.assertIn(gate + "\n                ur5_ros = refill.RosBridge(", self.source)

    def test_the_combined_arm_reports_its_home_joints(self):
        """받침대의 `ur5 spawn_settled`·`home_positions=` 는 그 구성에서 안 나온다 — 대신 이 줄이 나온다."""
        self.assertIn('log(f"amr arm_home steps=', self.source)
        self.assertIn("home_joint_positions 로 쓴다", self.source)


class AssetSitsAboveTheGround(unittest.TestCase):
    """합본의 충돌 메시가 링크 원점보다 **아래로** 내려간다(탐침 3: bbox 바닥 −0.0262).

    z 를 0 으로 두고 놓으면 바퀴가 지면에 박힌다. 실습(9/21)에서 `sep=-0.0259 impulse=2.19e6` 으로
    붙잡혀 **주행 명령에 전혀 안 움직였다** — dummy x 가 2963 표본 내내 0.0000 이었다.
    상자에서 `GROUND_CLEARANCE` 를 둔 것과 **같은 이유이고, 자산에서는 내가 그것을 빼먹었다.**
    """

    def setUp(self):
        self.source = (STANDALONE / "p3sim/amr_base.py").read_text()

    def test_the_lift_clears_the_probed_bottom(self):
        lift = A.GROUND_CLEARANCE - A.ASSET_BASE_BOTTOM_Z
        self.assertGreater(lift + A.ASSET_BASE_BOTTOM_Z, 0.02, "PhysX 접촉 문턱 위여야 한다")
        self.assertAlmostEqual(lift + A.ASSET_BASE_BOTTOM_Z, A.GROUND_CLEARANCE, places=9)

    def test_the_probed_bottom_matches_the_observed_penetration(self):
        """회차의 `sep=-0.0259` 와 탐침의 bbox 바닥이 같은 값이다 — 그래서 원인이 이것이다."""
        self.assertAlmostEqual(A.ASSET_BASE_BOTTOM_Z, -0.0262, places=4)

    def test_it_measures_first_and_falls_back_second(self):
        """자산이 바뀌면 박아 둔 값이 틀린다. 런타임 bbox 가 먼저다."""
        self.assertIn("def ground_lift(", self.source)
        self.assertIn("cache.ComputeWorldBound", self.source)
        self.assertIn("fell back to the probed bottom", self.source)

    def test_both_placements_get_the_same_lift(self):
        """어느 쪽이 먹는지는 **자산마다 다르다.** 같은 값을 주면 어느 쪽이 먹든 결과가 같다.

        회차 둘이 이것을 가르쳤다(9/21): `682fb30` 은 프림·앵커에 같은 (x, y) 를 줬는데 결과가 두 배가
        아니라 **한 번만** 적용됐고, `807102d` 는 **앵커 z 만** 올렸더니 몸체가 1 mm 도 안 올라갔다.
        → 이 자산은 **프림 이동**이 먹고, 받침대 UR5 자산은 **앵커**가 먹었다.
        다른 값을 주면 두 배가 되거나 어긋난다.
        """
        self.assertIn("xform.AddTranslateOp().Set(Gf.Vec3d(float(origin_xy[0]), float(origin_xy[1]), lift))",
                      self.source)
        self.assertIn("pinned = pin_world_joints(stage, root, (float(origin_xy[0]), float(origin_xy[1]), lift)",
                      self.source)

    def test_there_is_a_third_placement_as_a_last_resort(self):
        """1(프림)·2(앵커) 는 물리가 파싱하기 **전**에 거는 방식이다. 둘 다 무시하는 자산이면 뒤에 옮겨야 한다.

        되도록 안 쓴다 — 물리가 상태를 잡은 뒤에 건드리는 것이라 조용한 부작용이 생기기 쉽다.
        그래서 **필요할 때만** 쓰고 썼다는 것을 WARN 으로 남긴다.
        """
        self.assertIn("def ensure_height(", self.source)
        self.assertIn("WARN amr height_fixed_after_init", self.source)

    def test_it_does_nothing_when_the_body_is_already_high_enough(self):
        """조건 없이 쓰면 올바른 자산에서도 파싱 뒤 건드리기가 된다."""
        self.assertIn("if current >= wanted_z - 1e-6:\n                return False", self.source)

    def test_the_real_pose_is_logged_so_the_lift_can_be_checked(self):
        """807102d 에서 앵커를 올렸는데 몸체가 안 올라갔다. 그때 이 줄이 있었으면 로그만 보고 알았다."""
        self.assertIn("def log_base_pose(", self.source)
        self.assertIn("amr base_pose pos=", self.source)
        self.assertIn("expected_z_at_least=", self.source)


class CombinedArgumentName(unittest.TestCase):
    """이름 통일(재범 9/21): `ridgeback_ur5.usd` 구성을 **"AMR 합본"** 이라 부르고 인자는 `--amr-combined` 다.

    옛 이름(`--amr-usd`)은 **도는 회차를 안 끊으려고** 별칭으로 남긴다. 자산 파일명은 그대로다 —
    naming.md 가 외부 자산명을 유지해 출처를 추적한다.
    """

    def setUp(self):
        import pharmacy_stage

        self.stage = pharmacy_stage

    def test_the_new_name_works(self):
        self.assertEqual(self.stage.parse_args(["--amr", "--amr-combined", "/x/r.usd"]).amr_combined, "/x/r.usd")

    def test_the_old_name_still_works_and_says_it_is_old(self):
        """이름을 바꾸는 순간 도는 회차를 끊으면 안 된다."""
        self.assertEqual(self.stage.parse_args(["--amr", "--amr-usd", "/x/r.usd"]).amr_combined, "/x/r.usd")
        source = (STANDALONE / "pharmacy_stage.py").read_text()
        self.assertIn("--amr-usd is the old name", source)

    def test_the_old_field_is_cleared_so_nothing_reads_it(self):
        """둘 다 남겨 두면 어느 쪽을 읽는지가 코드마다 갈린다."""
        args = self.stage.parse_args(["--amr", "--amr-usd", "/x/r.usd"])
        self.assertIsNone(args.amr_usd)

    def test_the_asset_file_name_is_not_renamed(self):
        """외부 자산명은 출처 추적을 위해 유지한다(naming.md)."""
        source = (STANDALONE / "pharmacy_stage.py").read_text()
        self.assertIn("ridgeback_ur5.usd", source)


class CombinedTf(unittest.TestCase):
    """합본 경로에 **로봇 링크 TF 가 하나도 없었다**(회차 lap1, 9/21).

    받침대에서는 `ur5_cell.add_camera_and_tf` 가 냈는데 합본은 그 셀을 안 만든다. 그래서
    `amr_1/ur_arm_base_link` 도 `amr_1/deck_slot_*` 도 트리에 안 나갔고, 팔이 `놓을 곳 TF 없음` 으로
    ⑤에서 닫혔다. **흡착이 없던 것과 같은 뿌리다** — 받침대 셀에 달린 것을 합본으로 안 옮겼다.
    """

    def setUp(self):
        self.source = (STANDALONE / "p3sim/amr_base.py").read_text()
        self.stage_source = (STANDALONE / "pharmacy_stage.py").read_text()

    def test_the_parent_is_the_mobile_base_not_map(self):
        """계약 #423: `map →` 은 **받침대 조합에서만**이다. 합본에서는 `amr_1/base_link` 아래다."""
        self.assertIn('name_it(base, f"{ns}/{DECK_PARENT_LINK}")', self.source)
        self.assertNotIn("PARENT_FRAME", self.source)

    def test_the_deck_slots_get_frame_prims(self):
        """상자만 있고 프레임 프림이 없으면 낼 것이 없다."""
        self.assertIn('UsdGeom.Xform.Define(stage, f"{tray_root}/DeckSlot{index + 1}")', self.source)
        self.assertIn('f"{ns}/deck_slot_{index + 1}"', self.source)

    def test_the_arm_links_are_dynamic_and_the_rest_static(self):
        """팔은 움직이고 상판·밑동은 베이스에 붙박여 있다."""
        self.assertIn('("TfDynamic.inputs:topicName", "tf")', self.source)
        self.assertIn('("TfStatic.inputs:staticPublisher", True)', self.source)

    def test_the_stage_calls_it_only_for_the_combined_asset(self):
        self.assertIn("if args.amr_combined and amr_deck_frames:", self.stage_source)
        self.assertIn("amrlib.publish_tf(stage, AMR_ROOT,", self.stage_source)

    def test_a_tf_failure_does_not_stop_the_stage(self):
        """TF 가 없으면 팔이 못 놓지만 장면은 돌아야 원인을 본다."""
        self.assertIn("WARN amr tf disabled reason=", self.stage_source)


class HeightBudget(unittest.TestCase):
    """높이 예산은 **lift 로 재야 한다**. 9/21 에 `GROUND_CLEARANCE` 를 써서 어깨가 2.6 cm 낮게 잡혔다.

    비전이 잡았다: 밑동 월드 z 가 TF 기준 0.280, 실제 0.3362 인데 내가 쓴 값은 0.399 로 **둘 다 아니었다.**
    경계에서 6 cm 는 그대로 자세(`sin|q3|`)로 넘어온다 — 거리가 되고 안 되고가 아니라 팔이 펴지고 만다.
    """

    def test_the_lift_is_not_the_ground_clearance(self):
        """충돌체가 링크 원점보다 아래로 내려가므로 그만큼 더 올려야 한다."""
        self.assertNotAlmostEqual(A.asset_lift(), A.GROUND_CLEARANCE, places=4)
        self.assertAlmostEqual(A.asset_lift() + A.ASSET_BASE_BOTTOM_Z, A.GROUND_CLEARANCE, places=9)

    #: 받침을 달기 **전에 실제로 잰** 값들. 9/21 확정안으로 팔이 `ARM_MOUNT_LOCAL[2]` 만큼 올라갔지만
    #: 실측은 실측이라 그대로 두고, 계산이 **실측 + 올림량**인지를 본다. 실측을 덮어쓰면 다음에
    #: 높이 항이 하나 더 늘 때 어디서 틀렸는지 되짚을 근거가 사라진다.
    MEASURED_ARM_BASE_Z = 0.3362   # lap2 `base_pose` 0.0562 + 밑동 로컬 0.28 (비전의 "실제 기준")
    MEASURED_BELT_DZ = 0.4188      # lap3 검출 z. 봉투 월드 z 0.755 기준

    def test_the_arm_base_is_the_measured_one_plus_the_riser(self):
        """실측(0.3362)에 받침 올림량을 더한 값이어야 한다. 받침을 빼먹으면 0.15 가 조용히 남는다."""
        self.assertAlmostEqual(A.arm_base_world_z(), self.MEASURED_ARM_BASE_Z + A.ARM_MOUNT_LOCAL[2], places=4)

    def test_the_belt_pouch_dz_shrinks_by_exactly_the_riser(self):
        """받침이 하는 일이 이것이다 — dz 가 줄어 팔이 덜 뻗는다(비전 9/21: 뻗은비율 86 → 78 %).

        센서와 예산이 같은 기준을 쓰는지도 같이 본다: 봉투 월드 z 는 안 움직였다.
        """
        self.assertAlmostEqual(0.755 - A.arm_base_world_z(),
                               self.MEASURED_BELT_DZ - A.ARM_MOUNT_LOCAL[2], places=4)

    def test_the_riser_is_shorter_than_the_lift_it_gives(self):
        """밑동(0.28)이 몸체 윗면(0.301)보다 아래라 판은 올림량보다 **짧다**. 같다고 쓰면 밑동을 뚫는다."""
        self.assertAlmostEqual(A.riser_height(), 0.129, places=4)
        self.assertLess(A.riser_height(), A.ARM_MOUNT_LOCAL[2])

    def test_the_stop_poses_move_by_the_same_amount_the_arm_did(self):
        """팔을 −x 로 옮긴 만큼 정차 자리를 +x 로 밀어야 **팔 밑동의 월드 자리가 그대로**다.

        한쪽만 바꾸면 도달이 0.69 → 0.774 로 늘어도 아무 줄도 안 뜨고 자세만 나빠진다.
        """
        from p3sim import layout as L

        self.assertAlmostEqual(L.ARM_MOUNT_SHIFT_X, -A.ARM_MOUNT_LOCAL[0], places=9)


class CombinedSuction(unittest.TestCase):
    """합본 경로에 흡착이 **없었다.** 받침대 셀에 달려 있는데 합본은 그 셀을 안 만든다(9/21).

    그대로 뒀으면: 팔은 봉투까지 가고, 집히지 않고, `/amr_1/gripper/holding` 의 **작성자가 0** 이라
    팔이 unknown 으로 시한까지 기다린다(#444 F02). ③ 적재가 거기서 선다.
    """

    def setUp(self):
        self.source = (STANDALONE / "p3sim/amr_base.py").read_text()
        self.stage_source = (STANDALONE / "pharmacy_stage.py").read_text()

    def test_the_tcp_comes_from_the_prim_not_from_a_second_fk(self):
        """비전이 `wrist_3 == tool0` 을 역산했다. FK 를 또 풀면 푸는 쪽이 둘이 되어 어긋날 수 있다."""
        self.assertIn("f\"{self.root}/{TCP_PARENT_LINK}\"", self.source)
        # 산문에는 "Lula FK 로 구한다(받침대는)" 가 적혀 있다. **코드**가 푸는지를 본다.
        suction = self.source[self.source.index("class Suction:"):self.source.index("class Runtime:")]
        for call in ("self.solver", "compute_end_effector_pose", "LulaKinematicsSolver"):
            self.assertNotIn(call, suction, call)

    def test_a_miss_is_logged_not_silently_attached(self):
        """닿지 않았는데 붙이면 P32(흡착 실패해도 놓기를 계속)와 같은 구멍이 합본에서 되풀이된다."""
        self.assertIn("amr suction miss distance=", self.source)
        self.assertIn("amr suction miss target=none", self.source)

    def test_holding_is_published(self):
        """작성자가 0 이면 팔이 unknown 으로 시한까지 기다린다."""
        self.assertIn("amr_ros.publish_holding(amr_suction.holding())", self.stage_source)

    def test_the_held_pouch_follows_the_tcp(self):
        self.assertIn("amr_suction.follow()", self.stage_source)

    def test_reset_releases_it(self):
        """리셋 뒤에도 붙어 있으면 다음 바퀴가 봉투를 들고 시작한다.

        **글자 모양이 아니라 리셋 경로 안에 해제가 있는지**를 본다. 전에는 호출 한 줄을 통째로
        박아 놔서 인자를 하나 더하자 깨졌다 — 지키려던 것은 인자 목록이 아니다.
        """
        begin = self.stage_source.index('log(f"reset begin epoch=')
        end = self.stage_source.index('trace.mark("amr.reset")', begin)
        self.assertIn("amr_suction.suck(False, None", self.stage_source[begin:end])

    def test_every_release_says_why(self):
        """lap9: `suction on` 바로 다음 줄이 `suction off` 였는데 **팔이 떼라고 한 것인지 우리가 뗀
        것인지** 로그로 안 갈렸다. 한 일만 찍고 왜는 안 찍은 것이다.

        그래서 `suck(False, ...)` 를 부르는 곳은 전부 `reason=` 을 넘겨야 한다. 안 넘기면
        `reason=unknown` 으로 찍히지만, 그건 **다음 회차를 한 번 더 쓰고 나서야** 보인다.
        """
        for index, line in enumerate(self.stage_source.splitlines(), start=1):
            if "suck(False, None" in line and "amr_suction" in line:
                self.assertIn("reason=", line, f"{index}줄: 뗀 이유를 안 넘긴다")

    def test_it_is_only_built_for_the_combined_asset(self):
        """받침대 구성은 자기 흡착이 있다. 둘 다 만들면 작성자가 둘이 된다."""
        # 9/23: AMR 블록이 방 블록 밖(`if args.amr:` + `build_amr` 단계)으로 나와 들여쓰기가 한 단 얕아졌다.
        self.assertIn("if args.amr_combined:\n                    # 합본 팔의 흡착", self.stage_source)

    def test_the_attach_is_recorded_as_virtual(self):
        """물리적 파지가 아니다. 그렇게 적어 두지 않으면 나중에 파지 성능으로 읽힌다."""
        self.assertIn("가상 부착(텔레포트 추종)", self.source)


class DofIndices(unittest.TestCase):
    def test_it_finds_them_by_name_in_any_order(self):
        """위치로 집지 않는다 — 자산이나 빌드 순서가 바뀌면 자리는 바뀌어도 이름은 안 바뀐다."""
        names = ["shoulder_pan_joint", *reversed(A.JOINT_NAMES)]
        self.assertEqual(A.dof_indices(names), [3, 2, 1])

    def test_a_missing_axis_raises_instead_of_guessing(self):
        with self.assertRaises(KeyError):
            A.dof_indices(["dummy_base_prismatic_x_joint", "dummy_base_prismatic_y_joint"])


class ClampToLimits(unittest.TestCase):
    def test_x_and_y_are_clamped(self):
        (xmin, xmax), (ymin, ymax) = A.DEFAULT_LIMITS
        x, y, _yaw = A.clamp_to_limits((xmax + 10.0, ymin - 10.0, 0.0))
        self.assertEqual((x, y), (xmax, ymin))

    def test_yaw_is_only_wrapped_never_clamped(self):
        """revolute 에는 한계를 두지 않았다. 제자리 회전이 여러 바퀴여도 된다."""
        _x, _y, yaw = A.clamp_to_limits((0.0, 0.0, 7.0))
        self.assertAlmostEqual(yaw, A.wrap_angle(7.0))


class StageWiring(unittest.TestCase):
    """스테이지가 --amr 로 켜지고 기본값은 그대로인지. Isaac 을 띄우지 않는다(인자와 소스만 본다)."""

    def setUp(self):
        sys.path.insert(0, str(STANDALONE))
        import pharmacy_stage

        self.stage = pharmacy_stage
        self.source = (STANDALONE / "pharmacy_stage.py").read_text()

    def test_it_is_off_unless_asked(self):
        """시연 preset 의 기본 동작이 바뀌면 안 된다."""
        self.assertFalse(self.stage.parse_args([]).amr)
        self.assertFalse(self.stage.parse_args(["--preset", "emptyworld-loop"]).amr)

    def test_the_flag_turns_it_on(self):
        self.assertTrue(self.stage.parse_args(["--amr"]).amr)

    def test_the_start_pose_defaults_to_the_dock(self):
        from p3sim import layout as L

        self.assertIsNone(self.stage.parse_args(["--amr"]).amr_start)
        self.assertIn("DOCK[\"centre\"]", self.source, "기본 출발 자리가 dock_1 이어야 한다")
        self.assertEqual(len(L.DOCK["centre"]), 2)

    def test_it_subscribes_the_command_and_publishes_the_states(self):
        for needle in ("add_amr_topics", "take_amr", "publish_amr_states"):
            self.assertIn(needle, self.source, needle)

    def test_the_states_go_out_at_the_command_rate(self):
        self.assertIn("amrlib.COMMAND_HZ", self.source)

    def test_a_stale_command_stops_the_base(self):
        """계약 5절. 끊기면 0 이다."""
        self.assertIn("amrlib.stale(", self.source)

    def test_reset_returns_the_three_axes(self):
        self.assertIn("amr.reset()", self.source)

    def test_the_stage_publishes_no_odom_and_no_tf_for_the_base(self):
        """`odom -> amr_1/base_link` 의 작성자는 base_driver 하나다(계약 3절).

        스테이지에 `base_link` 라는 글자는 UR5 링크 이름으로도 나오므로, 베이스 모듈이 TF 를 내지 않는
        것과 odom 토픽이 없는 것을 본다.
        """
        self.assertNotIn("/odom", self.source)
        base_source = (STANDALONE / "p3sim/amr_base.py").read_text()
        # 합본에서는 **로봇 링크** TF 를 낸다(계약 454–458줄: `amr_1/base_link` 아래). 그건 허용이다.
        # 금지는 `odom`·`map` 을 내는 것과 `amr_1/base_link` **자체**를 child 로 내는 것이다.
        for needle in ("Odometry", "create_publisher"):
            self.assertNotIn(needle, base_source, needle)
        for forbidden in ('"odom"', "/odom", "map →", 'nameOverride"), "map"'):
            self.assertNotIn(forbidden, base_source, forbidden)
        # base_link 는 **부모로만** 쓴다 — targetPrims 에 들어가면 작성자가 둘이 된다.
        self.assertIn('("TfStatic.inputs:parentPrim", [usdrt.Sdf.Path(str(base.GetPath()))])', base_source)
        self.assertNotIn("static = [str(base.GetPath())]", base_source)


if __name__ == "__main__":
    unittest.main()


class TrayAndArmMount(unittest.TestCase):
    """9/21 재범 확정안: 팔은 몸체 뒤끝 + 낮은 받침, 반대쪽 끝은 칸막이 없는 통짜 트레이.

    `deck_slot_N` 은 **그 안의 고정된 놓을 자리**로 남는다 — 계약·`target_slot`·결정 28/44·zones·
    팔 매개변수는 하나도 안 바뀐다. 바뀐 것은 형상과 정차 자리뿐이다.
    """

    def setUp(self):
        from p3sim import layout as L

        self.L = L
        self.boxes, self.slots = L.tray_boxes(A.ASSET_BASE_TOP_Z)
        self.source = (STANDALONE / "p3sim/amr_base.py").read_text()
        self.stage_source = (STANDALONE / "pharmacy_stage.py").read_text()

    def extent(self, axis):
        lows = [b.center[axis] - b.size[axis] / 2.0 for b in self.boxes]
        highs = [b.center[axis] + b.size[axis] / 2.0 for b in self.boxes]
        return (min(lows), max(highs))

    def test_the_tray_sits_on_the_body_top(self):
        self.assertAlmostEqual(self.extent(2)[0], A.ASSET_BASE_TOP_Z, places=9)

    def test_the_tray_and_the_riser_stay_inside_the_planning_footprint(self):
        """계획 footprint 밖으로 나가면 통로 여유 계산이 틀리고 문틀에 걸린다.

        **실측 bbox 가 아니라 계획 footprint 로 본다** — 받침은 몸체 뒤끝에서 0.034 넘어가지만
        여유 규칙이 쓰는 것은 footprint 쪽이라 거기 들어 있으면 계산은 그대로 맞다.
        """
        half_x, half_y = (v / 2.0 for v in self.L.AMR_FOOTPRINT)
        low_x, high_x = self.extent(0)
        low_y, high_y = self.extent(1)
        riser_low = A.ARM_MOUNT_LOCAL[0] - A.RISER_SIZE[0] / 2.0
        for value in (low_x, high_x, riser_low, A.ARM_MOUNT_LOCAL[0] + A.RISER_SIZE[0] / 2.0):
            self.assertLessEqual(abs(value), half_x, f"x {value}")
        for value in (low_y, high_y, A.RISER_SIZE[1] / 2.0):
            self.assertLessEqual(abs(value), half_y, f"y {value}")

    def test_the_tray_does_not_overlap_the_riser(self):
        """둘이 겹치면 PhysX 가 첫 스텝에서 밀어낸다 — 조용히 자산이 튄다."""
        self.assertGreater(self.extent(0)[0], A.ARM_MOUNT_LOCAL[0] + A.RISER_SIZE[0] / 2.0)

    def test_every_slot_is_inside_the_tray_walls(self):
        """자리가 턱 위에 있으면 봉투가 벽에 얹힌다. 봉투 반 크기 + 낙하 산포까지 들어가야 한다."""
        bounds = self.L.tray_inner_bounds(A.ASSET_BASE_TOP_Z)
        margin = 0.05 + 0.04   # 봉투 긴 변의 절반 + 낙하 산포
        for slot in self.slots:
            for axis in (0, 1):
                low, high = bounds[axis]
                self.assertGreaterEqual(slot[axis] - margin, low, f"slot {slot} axis {axis}")
                self.assertLessEqual(slot[axis] + margin, high, f"slot {slot} axis {axis}")

    def test_the_outer_slot_has_room_for_the_pouch_to_slide(self):
        """바깥 자리에서 안쪽 면까지 **0.14 이상**. 봉투 반폭(0.035) + 낙하 산포(0.04) = 0.075 위의 여유다.

        **팔이 들어갈 자리가 아니다.** 처음에 그렇게 적었다가 비전이 반증했다(9/21): 자리1 에서
        제일 가까운 점은 턱 **옆면**이 아니라 **윗면**이고, link2 가 턱 위를 지난다. 그래서 폭을
        0.56 → 0.64 로 넓혀도 팔 여유는 9 mm 그대로였다. 폭이 사는 것은 **봉투가 밀릴 여지**뿐이다.
        팔 여유를 사는 것은 `lip` 이다(아래 시험).
        """
        (_lx, _hx), (low_y, high_y), _z = self.L.tray_inner_bounds(A.ASSET_BASE_TOP_Z)
        for slot in self.slots:
            self.assertGreaterEqual(slot[1] - low_y, 0.14, f"slot {slot} 와 y− 턱")
            self.assertGreaterEqual(high_y - slot[1], 0.14, f"slot {slot} 와 y+ 턱")

    def test_the_lip_is_low_enough_for_the_arm_and_high_enough_for_the_pouch(self):
        """턱 높이는 **자리1 팔 여유의 유일한 레버다** — 1 mm 낮추면 1 mm 늘어난다.

        비전 9/21: 0.05 → 9 mm, 0.04 → 19 mm, 0.03 → 29 mm, 0.02 → 39 mm. link2 가 턱 **위를**
        지나므로 가로로 넓히는 것은 아무것도 안 산다. 위(0.03)는 lap8 실측 9 mm 에 20 mm 를 더한다.
        아래로는 봉투 두께의 **세 배**는 되어야 굴러 나가는 것을 막는다 — 봉투는 던지는 것이 아니라
        놓는 것이고, 낙하 산포는 자리 간격과 `slot_accept` 가 본다.
        """
        lip = self.L.TRAY["lip"]
        self.assertLessEqual(lip, 0.03, "턱이 높으면 자리1 에서 link2 가 그만큼 붙는다")
        self.assertGreaterEqual(lip, 3 * 0.01, "봉투 두께의 세 배는 되어야 굴러 나가는 것을 막는다")

    def test_the_tray_fits_inside_the_measured_body(self):
        """트레이는 **실제 형상**이다. 계획 footprint(0.90)가 아니라 실측 bbox(0.793) 안이어야
        문틀·보관함 옆을 지날 때 계산과 실제가 갈리지 않는다."""
        half = self.L.AMR_BBOX[1] / 2.0
        low_y, high_y = self.extent(1)
        self.assertLessEqual(max(abs(low_y), abs(high_y)), half, f"y {low_y}..{high_y} vs 반폭 {half}")

    def test_the_slots_are_far_enough_apart_that_pouches_do_not_overlap(self):
        """간격은 봉투 긴 변(0.10) + 낙하 산포 양쪽(±0.04) 이상이어야 한다."""
        need = 0.10 + 2 * 0.04
        for i, a in enumerate(self.slots):
            for b in self.slots[i + 1:]:
                self.assertGreaterEqual(max(abs(a[0] - b[0]), abs(a[1] - b[1])), need - 1e-9, f"{a} {b}")

    def test_the_acceptance_box_is_the_spacing_not_a_wall(self):
        """트레이에는 칸을 가르는 벽이 없다 — 받는 상자를 정하는 것은 **자리 간격**이다.

        그래도 낙하 산포(±0.04)보다는 넓고, 간격보다는 좁아야 이웃 자리와 겹치지 않는다.
        """
        accept = self.L.TRAY["slot_accept"]
        spacing = min(abs(a[1] - b[1]) for a in self.slots for b in self.slots if a[1] != b[1])
        self.assertGreater(accept[1] / 2.0, 0.04)
        self.assertLessEqual(accept[1], spacing + 1e-9)

    def test_there_are_no_slot_dividers_left(self):
        """칸 벽이 남아 있으면 lap3 의 형상 그대로다 — 위팔이 3번 칸 벽에 sep 0.010 으로 막혔다."""
        self.assertEqual([b.name for b in self.boxes if "Slot" in b.name], [])

    def test_the_stage_moves_the_arm_before_it_measures_the_shoulder(self):
        """밑동 프레임은 어깨 프림의 자리를 **재서** 만든다. 옮기기 전에 재면 옛 자리에 박힌다."""
        moved = self.stage_source.index("amrlib.move_arm_mount(")
        measured = self.stage_source.index("amrlib.build_arm_base_frame(")
        self.assertLess(moved, measured)

    def test_the_mount_moves_both_the_joint_anchor_and_the_prims(self):
        """하나만 옮기면 조용히 어긋난다 — 1 만이면 프레임이 옛 자리, 2 만이면 물리가 되돌린다."""
        body = self.source[self.source.index("def move_arm_mount("):self.source.index("def build_arm_base_frame(")]
        self.assertIn("GetLocalPos0Attr().Set(", body)
        self.assertIn('name.startswith("ur_arm_")', body)

    def test_the_mount_only_moves_top_level_links(self):
        """부모와 자식을 둘 다 옮기면 두 번 밀린다."""
        body = self.source[self.source.index("def move_arm_mount("):self.source.index("def build_arm_base_frame(")]
        self.assertIn("GetPrimAtPath(root).GetChildren()", body)

    def test_the_combined_sensor_uses_the_tray_acceptance_box(self):
        """상판 칸 크기를 그대로 쓰면 트레이에서 맞게 놓은 봉투가 false 로 나온다."""
        self.assertIn('roomlib.TRAY["slot_accept"] if args.amr_combined else ROOM["deck_slot_size"]',
                      self.stage_source)


class BaseWorldPose(unittest.TestCase):
    """**관절값과 세계 좌표는 다르다.** dummy 관절의 원점은 출발 도크다.

    lap10 (9/21): 인식표 센서가 `read()` 를 세계로 썼다. 참값이 `bed_a1`(13.15, −0.39) 인데
    센서는 (8.55, −0.96) = **참값 − 출발 도크(4.60, 0.55)** 를 봤고 `거리 4.6363 > 0.35` 로
    어느 구역도 못 맞혀 ⑦ `AUTH_FAIL` 이 났다. 실습24 에서 같은 모양을 한 번 겪고도 또 했다.

    **아무 시험도 이것을 못 잡았다.** 원문 대조로 `amr.read()` 가 거기 있는 것만 봤기 때문이다 —
    있는 것은 맞고, **그 값의 기준이 틀렸다.** 그래서 여기서는 값을 실제로 계산해 본다.
    """

    class FakeRuntime:
        """`read()` 와 `start` 만 있는 껍데기. Isaac 없이 `base_world_pose` 의 산수를 본다."""

        def __init__(self, joints, start):
            self.joints = joints
            self.start = (float(start[0]), float(start[1]), 0.0)

        def read(self):
            return (list(self.joints), [0.0, 0.0, 0.0])

    def world(self, joints, start):
        return A.Runtime.base_world_pose(self.FakeRuntime(joints, start))

    def test_it_adds_the_spawn_origin(self):
        """lap10 의 실제 숫자. 센서가 본 (8.5487, −0.9590) + 도크 (4.60, 0.55) = 참값 (13.15, −0.41)."""
        x, y, yaw = self.world((8.5487, -0.9590, -0.0002), (4.60, 0.55))
        self.assertAlmostEqual(x, 13.1487, places=4)
        self.assertAlmostEqual(y, -0.4090, places=4)
        self.assertAlmostEqual(yaw, -0.0002, places=6)

    def test_it_is_not_the_joint_read(self):
        """출발 자리가 원점이 아니면 두 값이 **달라야** 한다. 같으면 보정이 빠진 것이다."""
        joints = (8.5487, -0.9590, 0.0)
        self.assertNotEqual(self.world(joints, (4.60, 0.55))[:2], joints[:2])

    def test_at_the_dock_the_two_agree(self):
        """출발 자리에서는 관절이 0 이고 세계 자세가 곧 도크다 — **여기서만 둘이 같다.**

        lap9 까지 조용했던 이유가 이것이다: 도크 근처에서는 틀린 값도 맞아 보인다.
        """
        self.assertEqual(self.world((0.0, 0.0, 0.0), (4.60, 0.55))[:2], (4.60, 0.55))

    def test_yaw_has_no_origin_offset(self):
        """회전 관절은 도크에서 0 이고 세계에서도 0 이다. yaw 에 보정을 넣으면 a1 과 b1 이 섞인다."""
        self.assertAlmostEqual(self.world((0.0, 0.0, 1.2), (4.60, 0.55))[2], 1.2, places=9)


class TagSensorUsesTheWorldPose(unittest.TestCase):
    """센서가 **어느 기준의 값을 쓰는지**를 본다. 이름이 거기 있는지가 아니다."""

    def setUp(self):
        self.stage_source = (STANDALONE / "pharmacy_stage.py").read_text()

    def test_the_tag_payload_does_not_read_joints_as_world(self):
        start = self.stage_source.index("def tag_payload():")
        body = self.stage_source[start:self.stage_source.index("\n        pouch_motion", start)]
        # **주석은 빼고 코드만 본다.** 안 그러면 "`amr.read()` 를 쓰면 안 된다" 고 적은 주석이
        # 그대로 걸린다 — 시험이 산문을 읽으면 맞는 코드를 막는다(이번 주에 세 번 겪었다).
        code = "\n".join(line for line in body.splitlines() if not line.lstrip().startswith("#"))
        self.assertIn("amr.base_world_pose()", code)
        self.assertNotIn("amr.read()", code, "관절값을 세계 좌표로 쓰고 있다 — lap10 이 그래서 닫혔다")

    def test_joint_states_still_publish_the_joint_values(self):
        """반대로 `/amr_1/joint_states` 는 **관절값이 맞다**(계약 97줄). 둘을 섞으면 주행이 틀린다."""
        self.assertIn("names, ordered, vel = amr.read_all()", self.stage_source)


class HeldPouchStaysInThePool(unittest.TestCase):
    """**팔이 든 봉투를 주차하면 풀에서 빠지고, 그러면 센서가 영원히 못 본다.**

    lap12 ⑧: 팔이 ⑤에서 봉투를 트레이에 제대로 놓았는데(`POUCH_LOADED amr_1/deck_slot_1`),
    `/amr_1/sim/pouches` 1268 건이 전부 빈 배열이었고 `pouch placed` 줄도 0 이었다. 팔은
    `not_detected (검출 0건)` 으로 닫혔다.

    원인: 벨트를 벗어나는 순간 `pouch_left_belt` → `remove_pouch("left_belt")`. 받침대 경로는
    그 앞의 holder 분기가 막아 주는데 **그 분기가 `cell` 만 보고 있었다.** 합본은 `cell` 이 None 이라
    통째로 안 돌았다. 흡착이 매 스텝 TCP 로 다시 끌어와서 **화면은 멀쩡했다** — 그래서 조용했다.
    """

    def setUp(self):
        self.source = (STANDALONE / "pharmacy_stage.py").read_text()

    def test_the_holder_is_whichever_suction_holds_it(self):
        self.assertIn("holder = cell if cell is not None else amr_suction", self.source)
        self.assertIn("if holder is not None and holder.held is not None and holder.held[0] is obj:", self.source)

    def test_parking_a_held_pouch_is_refused_and_logged(self):
        """분기가 또 뚫리면 **소리가 나야** 한다. 조용히 사라지는 것이 회차 하나를 통째로 썼다."""
        body = self.source[self.source.index("def remove_pouch(reason):"):self.source.index("def spawn_pouch(")]
        self.assertIn("WARN pouch_parked SKIPPED", body)
        self.assertLess(body.index("holder.held[0] is pool_objects[index]"), body.index("pool.release(index)"))

    def test_reset_releases_before_it_parks(self):
        """붙잡은 채로 주차하면 안전장치가 주차를 건너뛰고 **다음 바퀴가 봉투를 든 채로 시작한다.**"""
        begin = self.source.index('log(f"reset begin epoch=')
        end = self.source.index('trace.mark("amr.reset")', begin)
        block = self.source[begin:end]
        self.assertLess(block.index('amr_suction.suck(False, None, reason="reset"'),
                        block.index('remove_pouch("reset")'))
        self.assertLess(block.index("cell.suck(False, None)"), block.index('remove_pouch("reset")'))


class PlacedMeansResting(unittest.TestCase):
    """`pouch placed … offset_xy=` 는 **놓기 오차를 재는 줄**이다. 그러니 놓인 것만 재야 한다.

    lap15 (9/21, master02): 이송 중인 봉투가 `in_slot=False offset_xy=0.0701 dz=+0.9263` 으로
    찍혔다. 같은 시각 `wrist_3 ↔ Pouch sep=-0.0068` — **흡착된 채 공중에 있었다.** 이송 속도가
    문턱(0.02) 아래로 내려가는 순간이 있어 속도만으로는 안 걸러진다. 실제 적재는 그 뒤에
    `in_slot=True offset_xy=0.0060` 으로 따로 찍혔다.

    **판정에는 영향이 없지만 숫자에는 있다.** 비전이 `offset_xy` 최댓값으로
    `arrival_tolerance_rad` 를 조일지 정하기로 되어 있어서, 이송값이 섞이면 **있지도 않은 놓기
    오차를 보고 공차를 조이게 된다.** 재는 줄은 뜻이 틀리면 조용히 남을 속인다.
    """

    def setUp(self):
        self.source = (STANDALONE / "pharmacy_stage.py").read_text()
        start = self.source.index("def pouch_detections():")
        self.body = self.source[start:self.source.index("return found", start)]

    def test_a_carried_pouch_is_not_placed(self):
        self.assertIn("carried = holder is not None and holder.held is not None and holder.held[0] is obj",
                      self.body)
        self.assertIn("and not carried and", self.body)

    def test_height_is_checked_too(self):
        """흡착을 놓친 채 떨어지는 봉투도 "놓았다" 가 아니다 — 속도·수평거리만으로는 못 가른다."""
        self.assertIn("rested = abs(world[2] - near[2]) <= 0.05", self.body)
        self.assertIn("and rested and", self.body)

    def test_the_guard_is_looser_than_the_in_slot_z_test(self):
        """살짝 뜬 채 멈춘 것도 **재야** 한다 — 재는 줄의 문턱이 판정 문턱과 같으면
        `in_slot=False` 인 경우가 통째로 안 찍힌다. 그때가 제일 알고 싶은 때다."""
        from p3sim import layout as L

        self.assertGreater(0.05, L.TRAY["slot_accept"][2] / 2.0)


class PoseReaderMadeOnce(unittest.TestCase):
    """9/23 5a59776 py-spy: `slots_in_world` 가 부를 때마다 `SingleXFormPrim` 을 새로 만들어 루프 샘플의 16% 였다.
    경로마다 한 번만 만들고, 읽기가 실패하면 버려서 다음에 새로 만든다."""

    def setUp(self):
        import types

        made = self.made = []
        poses = self.poses = {}

        class FakeXForm:
            def __init__(self, prim_path, name):
                made.append(prim_path)
                self.path = prim_path

            def get_world_pose(self):
                pose = poses[self.path]
                if isinstance(pose, Exception):
                    raise pose
                return pose

        prims = types.ModuleType("isaacsim.core.prims")
        prims.SingleXFormPrim = FakeXForm
        self._saved = {k: sys.modules.get(k) for k in ("isaacsim", "isaacsim.core", "isaacsim.core.prims")}
        sys.modules.update({"isaacsim": types.ModuleType("isaacsim"),
                            "isaacsim.core": types.ModuleType("isaacsim.core"), "isaacsim.core.prims": prims})
        self.runtime = A.Runtime(None, "/Amr", (0.0, 0.0), log=lambda _text: None)
        self.base = f"/Amr/{A.DECK_PARENT_LINK}"
        self.arm = f"{self.base}/{A.ARM_BASE_FRAME}"

    def tearDown(self):
        for key, value in self._saved.items():
            if value is None:
                sys.modules.pop(key, None)
            else:
                sys.modules[key] = value

    def test_one_reader_per_path(self):
        self.poses[self.base] = ((1.0, 2.0, 0.1), (1.0, 0.0, 0.0, 0.0))
        self.poses[self.arm] = ((1.0, 2.0, 0.5), (1.0, 0.0, 0.0, 0.0))
        for _ in range(5):
            self.runtime.slots_in_world([(0.1, 0.0, 0.2)])
            self.runtime.world_to_arm_base((1.5, 2.0, 0.5))
        self.assertEqual([self.base, self.arm], self.made)

    def test_reads_the_current_pose_every_call(self):
        self.poses[self.base] = ((1.0, 2.0, 0.1), (1.0, 0.0, 0.0, 0.0))
        first = self.runtime.slots_in_world([(0.1, 0.0, 0.2)])
        yaw = math.pi / 2.0
        self.poses[self.base] = ((3.0, 4.0, 0.1), (math.cos(yaw / 2.0), 0.0, 0.0, math.sin(yaw / 2.0)))
        second = self.runtime.slots_in_world([(0.1, 0.0, 0.2)])
        self.assertEqual((1.1, 2.0), tuple(round(v, 6) for v in first[0][:2]))
        self.assertEqual((3.0, 4.1), tuple(round(v, 6) for v in second[0][:2]))

    def test_a_failed_read_makes_a_new_reader_next_time(self):
        self.poses[self.arm] = RuntimeError("prim gone")
        self.assertIsNone(self.runtime.world_to_arm_base((0.0, 0.0, 0.0)))
        self.poses[self.arm] = ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0, 0.0))
        self.assertEqual((1.0, 0.0, 0.0), self.runtime.world_to_arm_base((1.0, 0.0, 0.0)))
        self.assertEqual([self.arm, self.arm], self.made)


class ExtraAmrPlanTests(unittest.TestCase):
    """`--amr-count N` 의 자리 고르기. 부하 측정용이고 배송은 첫 대만 한다(재범 9/23)."""

    ZONES = {"dock_1": (-8.238, 4.169, 0.0, -1.571), "dock_2": (-5.258, 4.169, 0.0, -1.571),
             "dock_3": (-2.261, 4.169, 0.0, -1.571), "dock_4": (0.68, 4.169, 0.0, -1.571)}

    def test_one_amr_needs_no_extra(self):
        self.assertEqual([], A.extra_amr_plan(1, self.ZONES))

    def test_the_extras_stand_at_dock_two_and_up_in_order(self):
        plan = A.extra_amr_plan(3, self.ZONES)
        self.assertEqual([(2, "/amr_2", (-5.258, 4.169)), (3, "/amr_3", (-2.261, 4.169))], plan)

    def test_every_dock_can_be_used(self):
        plan = A.extra_amr_plan(4, self.ZONES)
        self.assertEqual([2, 3, 4], [index for index, _ns, _xy in plan])
        self.assertEqual(["/amr_2", "/amr_3", "/amr_4"], [ns for _i, ns, _xy in plan])

    def test_more_than_the_docks_is_refused(self):
        with self.assertRaises(ValueError):
            A.extra_amr_plan(5, self.ZONES)
        with self.assertRaises(ValueError):
            A.extra_amr_plan(0, self.ZONES)

    def test_a_missing_dock_is_refused_rather_than_stacking_two_amrs(self):
        """자리가 없으면 겹쳐 세우지 않는다 — 겹치면 서로 밀어 부하 측정이 아니라 사고가 된다."""
        with self.assertRaises(ValueError):
            A.extra_amr_plan(3, {"dock_2": (0.0, 0.0, 0.0, 0.0)})
        with self.assertRaises(ValueError):
            A.extra_amr_plan(2, None)


class TrayGrip(unittest.TestCase):
    """RC-1 회차55·56·57: 트레이 봉투가 11–13 cm(회전 반감 뒤에도 8.2 cm) 밀렸다. 트레이 면에 고무 매트 마찰."""

    def test_every_tray_collider_gets_the_grip_material(self):
        try:
            from pxr import Usd, UsdGeom, UsdShade
        except ImportError:
            self.skipTest("usd-core 없음")
        from p3sim import layout

        stage = Usd.Stage.CreateInMemory()
        UsdGeom.Xform.Define(stage, "/Amr")
        UsdGeom.Xform.Define(stage, f"/Amr/{A.DECK_PARENT_LINK}")
        A.build_tray_on_base(stage, "/Amr", layout, log=lambda *_: None)
        colliders = [p for p in stage.Traverse() if p.GetName().startswith("Tray") and p.IsA(UsdGeom.Cube)]
        self.assertTrue(colliders)
        for prim in colliders:
            bound, _rel = UsdShade.MaterialBindingAPI(prim).ComputeBoundMaterial("physics")
            self.assertTrue(bound, prim.GetPath())
            material = bound.GetPrim()
            static = material.GetAttribute("physics:staticFriction").Get()
            dynamic = material.GetAttribute("physics:dynamicFriction").Get()
            self.assertAlmostEqual(A.TRAY_GRIP["static"], static, places=5)
            self.assertAlmostEqual(A.TRAY_GRIP["dynamic"], dynamic, places=5)
            self.assertEqual("max", material.GetAttribute("physxMaterial:frictionCombineMode").Get())
            # usd-core 는 PhysxSchema 를 몰라 GetAppliedSchemas 에서 거른다. 적힌 목록(메타데이터)을 본다.
            self.assertIn("PhysxMaterialAPI", material.GetMetadata("apiSchemas").GetAddedOrExplicitItems())

    def test_the_grip_is_a_rubber_mat_not_glue(self):
        grip = A.TRAY_GRIP
        self.assertLessEqual(grip["dynamic"], grip["static"])
        self.assertLessEqual(grip["static"], 1.2)   # 놓기·집기(흡착)를 막지 않는 범위


class _Pose:
    def __init__(self, xyz, quat=(1.0, 0.0, 0.0, 0.0)):
        self.xyz, self.quat = list(xyz), list(quat)

    def get_world_pose(self):
        return self.xyz, self.quat


class _Pouch(_Pose):
    def __init__(self, xyz):
        super().__init__(xyz)
        self.set_calls = 0

    def set_world_pose(self, position, orientation):
        self.xyz, self.quat = [float(v) for v in position], [float(v) for v in orientation]
        self.set_calls += 1

    def set_linear_velocity(self, _v):
        pass

    def set_angular_velocity(self, _v):
        pass


class _Runtime:
    """base_link 자세만 흉내 낸다. 트레이 칸 한 개 = base_link 로컬 (0.05, 0, 0.329)."""
    root = "/Amr"

    def __init__(self):
        self.base = _Pose((1.0, 2.0, 0.0))

    def _pose_reader(self, _path, _name):
        return self.base

    def slots_in_world(self, local_slots):
        bx, by, bz = self.base.xyz
        return [(bx + x, by + y, bz + z) for x, y, z in local_slots]


class TrayClipTests(unittest.TestCase):
    """재범 9/24 20:5x 트레이 홀더: 칸에 멈춘 봉투는 트레이에 붙고, 팔이 잡으면 떨어진다."""

    SLOTS = [(0.05, 0.0, 0.329)]
    ACCEPT = (0.18, 0.18, 0.04)

    def make(self):
        logs = []
        clip = A.TrayClip(_Runtime(), self.SLOTS, self.ACCEPT, 0.02, log=logs.append)
        return clip, logs

    def test_a_still_pouch_in_a_slot_is_clipped_and_follows_the_tray(self):
        clip, logs = self.make()
        pouch = _Pouch((1.05, 2.0, 0.329))
        clip.update([("ord-0001", pouch)], None, lambda _o: 0.0)
        self.assertTrue(any("tray clip on order_id=ord-0001" in line for line in logs))
        clip.runtime.base.xyz = [2.0, 2.5, 0.0]                       # AMR 이 움직였다
        clip.update([("ord-0001", pouch)], None, lambda _o: 0.3)      # 붙은 뒤에는 속도와 상관없다
        self.assertAlmostEqual(2.05, pouch.xyz[0])
        self.assertAlmostEqual(2.5, pouch.xyz[1])

    def test_a_moving_or_off_slot_pouch_is_not_clipped(self):
        clip, logs = self.make()
        clip.update([("ord-0001", _Pouch((1.05, 2.0, 0.329)))], None, lambda _o: 0.5)   # 아직 구른다
        clip.update([("ord-0002", _Pouch((5.0, 5.0, 0.3)))], None, lambda _o: 0.0)       # 칸 밖(벨트·보관함)
        self.assertEqual({}, clip.clips)
        self.assertEqual([], logs)

    def test_the_arm_picking_it_releases_the_clip(self):
        clip, logs = self.make()
        pouch = _Pouch((1.05, 2.0, 0.329))
        clip.update([("ord-0001", pouch)], None, lambda _o: 0.0)
        clip.update([("ord-0001", pouch)], pouch, lambda _o: 0.0)
        self.assertEqual({}, clip.clips)
        self.assertTrue(any("tray clip off order_id=ord-0001 reason=picked" in line for line in logs))

    def test_release_all_on_reset(self):
        clip, logs = self.make()
        clip.update([("ord-0001", _Pouch((1.05, 2.0, 0.329)))], None, lambda _o: 0.0)
        clip.release_all("reset")
        self.assertEqual({}, clip.clips)
        self.assertTrue(logs[-1].endswith("reason=reset"))

