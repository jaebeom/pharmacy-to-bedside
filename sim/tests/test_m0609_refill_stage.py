"""Plain-Python checks for sim/standalone/m0609_refill_stage.py; Isaac is not needed and not started.

    python3 -m unittest discover -s sim/tests -p 'test_m0609_refill_stage.py'
"""

import contextlib
import importlib.util
import io
import math
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

SCRIPT = Path(__file__).resolve().parents[1] / "standalone" / "m0609_refill_stage.py"
ISAAC_MODULES = ("isaacsim", "omni", "pxr", "carb", "rclpy")
ROBOT_USD = "/abs/m0609_gripper.usd"


def load_script():
    spec = importlib.util.spec_from_file_location("m0609_refill_stage", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


STAGE = load_script()


class JointStateStampTest(unittest.TestCase):
    def test_both_publishers_carry_rounded_nanoseconds_into_seconds(self):
        bridge = STAGE.RosBridge.__new__(STAGE.RosBridge)
        bridge._joint_state_type = lambda: SimpleNamespace(header=SimpleNamespace(stamp=SimpleNamespace()))
        bridge.arm_joint_names = list(STAGE.DEFAULT_ARM_JOINTS)
        bridge.rail_joint_names = ['rail_x', 'rail_y', 'rail_z']
        for method, publisher, size in [('publish_joint_states', 'joint_states_pub', 6),
                                        ('publish_rail_states', 'rail_states_pub', 3)]:
            with self.subTest(method=method):
                messages = []
                setattr(bridge, publisher, SimpleNamespace(publish=messages.append))
                for stamp in (1.9, 1.9999999999, 2.):
                    getattr(bridge, method)(stamp, [0.] * size, [0.] * size)
                self.assertEqual([(m.header.stamp.sec, m.header.stamp.nanosec) for m in messages],
                                 [(1, 900000000), (2, 0), (2, 0)])


def args_for(*extra):
    return STAGE.parse_args(["--robot-usd", ROBOT_USD, *extra])


class ImportGuardTests(unittest.TestCase):
    def test_module_import_does_not_touch_isaac_or_ros(self):
        before = {name for name in sys.modules if name.split(".")[0] in ISAAC_MODULES}
        load_script()
        after = {name for name in sys.modules if name.split(".")[0] in ISAAC_MODULES}
        self.assertEqual(before, after)


class ArgumentTests(unittest.TestCase):
    def test_robot_usd_is_required(self):
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            STAGE.build_parser().parse_args([])

    def test_defaults(self):
        args = args_for()
        self.assertEqual("ros", args.mode)
        self.assertFalse(args.attach)
        self.assertEqual("/World/m0609", args.robot_prim)
        self.assertEqual(["joint_1", "joint_2", "joint_3", "joint_4", "joint_5", "joint_6"], args.arm_joints)
        self.assertEqual("finger_joint", args.gripper_joint)
        self.assertEqual((0.0, 0.0, 0.19671), args.tcp_offset)

    def test_coordinates_accept_spaces_or_commas(self):
        args = args_for("--mode", "selfdemo", "--canister-xyz", "0.1,0.2,0.3", "--slot-xyz", "0.4 -0.5 0.06",
                        "--canister-size", "0.03 0.03 0.07", "--attach", "--arm-joints", "a", "b", "c", "d", "e", "f")
        self.assertEqual("selfdemo", args.mode)
        self.assertEqual((0.1, 0.2, 0.3), args.canister_xyz)
        self.assertEqual((0.4, -0.5, 0.06), args.slot_xyz)
        self.assertEqual((0.03, 0.03, 0.07), args.canister_size)
        self.assertTrue(args.attach)
        self.assertEqual(["a", "b", "c", "d", "e", "f"], args.arm_joints)

    def test_invalid_values_fail(self):
        cases = (["--canister-xyz", "1 2"], ["--canister-xyz", "1 2 nan"], ["--slot-size", "0.1 0 0.1"],
                 ["--mode", "teleop"], ["--hold-distance", "0"], ["--tool-quat", "0 0 0 0"], ["--slot-letter", "c"])
        for extra in cases:
            with self.subTest(extra=extra), self.assertRaises(SystemExit), \
                    contextlib.redirect_stderr(io.StringIO()):
                STAGE.build_parser().parse_args(["--robot-usd", ROBOT_USD, *extra])

    def test_tool_quat_is_normalized(self):
        self.assertAlmostEqual(1.0, math.sqrt(sum(v * v for v in args_for("--tool-quat", "0 2 0 0").tool_quat)))


class LivestreamAndLoopTests(unittest.TestCase):
    def test_livestream_is_off_by_default(self):
        args = args_for("--headless")
        self.assertFalse(args.livestream)
        self.assertEqual({"headless": True}, STAGE.simulation_app_config(args))

    def test_livestream_config_follows_class_example(self):
        args = args_for("--livestream", "--stream-width", "1280", "--stream-height", "720")
        self.assertEqual({"headless": True, "hide_ui": False, "width": 1280, "height": 720},
                         STAGE.simulation_app_config(args))
        self.assertEqual("omni.kit.livestream.webrtc", args.livestream_extension)

    def test_loop_condition(self):
        self.assertTrue(STAGE.keep_running(True, False, False))
        self.assertTrue(STAGE.keep_running(False, False, True))
        self.assertFalse(STAGE.keep_running(False, True, True))
        self.assertFalse(STAGE.keep_running(False, False, False))


class StartupAndExitTests(unittest.TestCase):
    def test_error_exits_nonzero(self):
        self.assertEqual(1, STAGE.exit_code_for(True))
        self.assertEqual(0, STAGE.exit_code_for(False))

    def test_warmup_default(self):
        self.assertEqual(10, args_for().warmup_updates)

    def test_throttled_log_first_then_every_nth(self):
        throttle = STAGE.ThrottledLog(every=3)
        self.assertEqual([True, False, True, False, False, True], [throttle.hit() for _ in range(6)])


class LoopTests(unittest.TestCase):
    def test_loop_and_speed_defaults(self):
        args = args_for()
        self.assertEqual(1, args.loop)
        self.assertEqual(0.0007, args.tcp_speed)
        self.assertEqual(0.5, args.phase_pause_s)
        self.assertEqual(3.0, args.respawn_delay_s)

    def run_sequencer(self, plan_length, loops, pause, max_updates=1000):
        seq = STAGE.DemoSequencer(plan_length, loops, pause)
        trace = []
        for _ in range(max_updates):
            if seq.mode == "finished":
                break
            if seq.mode == "start_phase":
                trace.append((seq.cycle, seq.index))
                seq.mode = "run"
                event = seq.phase_done()  # reach the phase immediately
            elif seq.mode == "pause":
                event = seq.tick_pause()
            elif seq.mode == "home":
                seq.home_done()
                event = None
            else:
                self.fail(f"unexpected mode {seq.mode}")
            if event:
                trace.append(event)
        return seq, trace

    def test_single_cycle_without_pause(self):
        seq, trace = self.run_sequencer(3, 1, 0)
        self.assertEqual([(1, 0), (1, 1), (1, 2), "finished"], trace)
        self.assertEqual("finished", seq.mode)

    def test_two_cycles_go_home_between(self):
        _seq, trace = self.run_sequencer(2, 2, 0)
        self.assertEqual([(1, 0), (1, 1), "cycle_end", (2, 0), (2, 1), "finished"], trace)

    def test_pause_holds_for_the_given_updates(self):
        seq = STAGE.DemoSequencer(2, 1, 3)
        seq.mode = "run"
        self.assertIsNone(seq.phase_done())
        self.assertEqual("pause", seq.mode)
        self.assertEqual([None, None], [seq.tick_pause(), seq.tick_pause()])
        self.assertEqual("pause", seq.mode)
        self.assertIsNone(seq.tick_pause())
        self.assertEqual(("start_phase", 1), (seq.mode, seq.index))

    def test_loop_zero_runs_forever(self):
        seq, trace = self.run_sequencer(2, 0, 0, max_updates=200)
        self.assertNotEqual("finished", seq.mode)
        self.assertGreater(trace.count("cycle_end"), 10)

    def test_empty_plan_is_rejected(self):
        with self.assertRaises(ValueError):
            STAGE.DemoSequencer(0, 1, 0)

    def test_respawn_waits_for_slot_open_and_delay(self):
        timer = STAGE.RespawnTimer(3.0)
        self.assertFalse(timer.update(True, False, 10.0))  # still closed
        self.assertFalse(timer.update(True, True, 11.0))  # starts counting
        self.assertFalse(timer.update(True, True, 13.9))
        self.assertTrue(timer.update(True, True, 14.0))
        self.assertFalse(timer.update(True, True, 14.1))  # restarted after firing

    def test_respawn_resets_when_canister_leaves_or_gripper_closes(self):
        timer = STAGE.RespawnTimer(3.0)
        timer.update(True, True, 0.0)
        self.assertFalse(timer.update(False, True, 2.0))
        self.assertFalse(timer.update(True, True, 4.0))
        self.assertFalse(timer.update(True, False, 6.5))
        self.assertFalse(timer.update(True, True, 7.0))
        self.assertTrue(timer.update(True, True, 10.0))

    def test_joint_steps_follow_speed(self):
        self.assertEqual(120, STAGE.joint_steps((0.0,) * 6, (1.0, 0, 0, 0, 0, 0), 0.5, 1 / 60))
        self.assertEqual(30, STAGE.joint_steps((0.0,) * 6, (0.0,) * 6, 0.5, 1 / 60))


class GraspTests(unittest.TestCase):
    def test_grasp_arguments_defaults(self):
        args = args_for()
        self.assertIsNone(args.gripper_close)  # derived from the sweep unless given
        self.assertEqual([1e4, 1e2, 10.0], args.gripper_drive)
        self.assertFalse(args.keep_usd_gripper_drive)
        self.assertEqual([1.0, 1.0], args.friction)
        self.assertEqual(["left_inner_finger", "right_inner_finger"], args.finger_links)
        self.assertEqual(0.04, args.grip_depth)
        overridden = args_for("--gripper-close", "0.6", "--gripper-drive", "1", "2", "3", "--friction", "0.8", "0.6")
        self.assertEqual(0.6, overridden.gripper_close)
        self.assertEqual([1.0, 2.0, 3.0], overridden.gripper_drive)
        self.assertEqual([0.8, 0.6], overridden.friction)

    def test_negative_friction_fails(self):
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            STAGE.build_parser().parse_args(["--robot-usd", ROBOT_USD, "--friction", "-1", "1"])

    def test_pad_widths_anchor_open_spacing(self):
        widths = STAGE.pad_widths([0.150, 0.120, 0.060], 0.110)
        for expected, actual in zip([0.110, 0.080, 0.020], widths, strict=True):
            self.assertAlmostEqual(expected, actual)
        self.assertEqual([], STAGE.pad_widths([], 0.110))

    def test_close_target_interpolates_on_the_sweep(self):
        angles = [0.0, 0.5, 1.0]
        widths = [0.110, 0.070, 0.010]
        angle, clamped = STAGE.close_target_from_sweep(angles, widths, 0.036)
        self.assertFalse(clamped)
        self.assertAlmostEqual(0.5 + 0.5 * (0.070 - 0.036) / 0.060, angle)

    def test_close_target_clamps_outside_the_sweep(self):
        self.assertEqual((1.0, True), STAGE.close_target_from_sweep([0.0, 1.0], [0.110, 0.050], 0.036))
        self.assertEqual((0.0, True), STAGE.close_target_from_sweep([0.0, 1.0], [0.110, 0.050], 0.200))
        with self.assertRaises(ValueError):
            STAGE.close_target_from_sweep([0.0], [0.110], 0.036)

    def test_mimic_expected_follows_physx_convention(self):
        self.assertAlmostEqual(-0.5, STAGE.mimic_expected(0.5, 1.0, 0.0))
        self.assertAlmostEqual(0.5, STAGE.mimic_expected(0.5, -1.0, 0.0))

    def test_grasp_verified_needs_closed_and_lift(self):
        self.assertTrue(STAGE.grasp_verified(True, 0.14, 0.20, 0.01))
        self.assertFalse(STAGE.grasp_verified(True, 0.14, 0.1401, 0.01))  # 9/17 master02: canister stayed put
        self.assertFalse(STAGE.grasp_verified(False, 0.14, 0.20, 0.01))
        self.assertFalse(STAGE.grasp_verified(True, None, 0.20, 0.01))


class P4Tests(unittest.TestCase):
    def test_dof_type_names_follow_tensor_enum(self):
        self.assertEqual({0: "rotation", 1: "translation"}, STAGE.DOF_TYPE_NAMES)

    def test_joint_space_and_tool_yaw_defaults(self):
        args = args_for()
        self.assertEqual(["to_shelf"], args.joint_space_phases)
        self.assertEqual("fixed", args.tool_yaw)
        self.assertEqual([], args_for("--joint-space-phases").joint_space_phases)

    def test_fixed_tool_yaw_keeps_the_quaternion(self):
        self.assertEqual((0.0, 1.0, 0.0, 0.0), STAGE.tool_quat_for((0.0, 1.0, 0.0, 0.0), (0.3, 0.3, 0.1), (0, 0, 0),
                                                                   "fixed"))

    def test_radial_tool_yaw_turns_with_the_bearing(self):
        down = (0.0, 1.0, 0.0, 0.0)
        ahead = STAGE.tool_quat_for(down, (0.35, 0.0, 0.1), (0.0, 0.0, 0.0), "radial")
        for e, a in zip(down, ahead, strict=True):
            self.assertAlmostEqual(e, a)
        left = STAGE.tool_quat_for(down, (0.0, 0.35, 0.1), (0.0, 0.0, 0.0), "radial")
        # tool x axis (fingers) turns from world +x to world +y; tool z still points down
        x_axis = STAGE.quat_rotate(left, (1.0, 0.0, 0.0))
        z_axis = STAGE.quat_rotate(left, (0.0, 0.0, 1.0))
        for e, a in zip((0.0, 1.0, 0.0), x_axis, strict=True):
            self.assertAlmostEqual(e, a)
        for e, a in zip((0.0, 0.0, -1.0), z_axis, strict=True):
            self.assertAlmostEqual(e, a)


class PublishScheduleTests(unittest.TestCase):
    def test_thirty_hz_on_a_sixty_hz_loop(self):
        scheduled, published = 0.0, 0
        for update in range(600):  # 10 s of 60 Hz updates
            now = update / 60.0
            if now >= scheduled - 1e-9:
                published += 1
                scheduled = STAGE.next_publish_time(scheduled, now, 30.0)
        self.assertEqual(300, published)

    def test_old_now_plus_period_rule_undershoots(self):
        scheduled, published = 0.0, 0
        for update in range(600):
            now = update / 60.0
            if now >= scheduled:
                published += 1
                scheduled = now + 1.0 / 30.0
        self.assertLess(published, 300)

    def test_far_behind_restarts_from_now(self):
        self.assertEqual(5.0, STAGE.next_publish_time(1.0, 5.0, 30.0))


class LayoutTests(unittest.TestCase):
    def test_default_layout_is_consistent(self):
        self.assertEqual([], STAGE.validate_layout(args_for()))

    def test_canister_floating_above_shelf_is_reported(self):
        problems = STAGE.validate_layout(args_for("--canister-xyz", "0.35 0.25 0.30"))
        self.assertTrue(any("shelf top" in problem for problem in problems))

    def test_canister_off_shelf_footprint_is_reported(self):
        problems = STAGE.validate_layout(args_for("--canister-xyz", "0.60 0.25 0.14"))
        self.assertTrue(any("footprint" in problem for problem in problems))

    def test_slot_too_narrow_is_reported(self):
        problems = STAGE.validate_layout(args_for("--slot-size", "0.06 0.10 0.10"))
        self.assertTrue(any("cavity x" in problem for problem in problems))

    def test_overlapping_shelf_and_slot_is_reported(self):
        problems = STAGE.validate_layout(args_for("--slot-xyz", "0.35 0.25 0.05"))
        self.assertTrue(any("overlap" in problem for problem in problems))

    def test_slot_cavity_is_open_on_top(self):
        center, inner = STAGE.slot_cavity((0.0, 0.0, 0.05), (0.10, 0.10, 0.10), 0.01)
        low, high = STAGE.aabb(center, inner)
        self.assertAlmostEqual(0.01, low[2])  # floor top
        self.assertAlmostEqual(0.10, high[2])  # outer top, no lid
        self.assertAlmostEqual(0.08, inner[0])


class DispenserLayoutTests(unittest.TestCase):
    def test_defaults_have_two_slots_body_and_two_shelf_canisters(self):
        args = args_for()
        self.assertEqual((0.35, -0.37, 0.15), args.slot_b_xyz)
        self.assertEqual(2, args.shelf_count)
        center, size = STAGE.dispenser_body(args)
        self.assertAlmostEqual(0.10, center[2] + size[2] / 2)  # body top meets slot bottoms
        self.assertAlmostEqual(0.0, center[2] - size[2] / 2)  # body stands on the ground
        self.assertEqual([(0.35, 0.25, 0.14), (0.41, 0.25, 0.14)],
                         [tuple(round(v, 6) for v in p) for p in STAGE.shelf_canister_positions(args)])

    def test_no_body_when_height_zero(self):
        self.assertIsNone(STAGE.dispenser_body(args_for("--dispenser-height", "0")))

    def test_slot_alternation(self):
        self.assertEqual(["a", "b", "a", "b"], [STAGE.slot_for_cycle("ab", c) for c in (1, 2, 3, 4)])
        self.assertEqual(["b", "b"], [STAGE.slot_for_cycle("b", c) for c in (1, 2)])

    def test_overlapping_slots_are_reported(self):
        problems = STAGE.validate_layout(args_for("--slot-b-xyz", "0.35 -0.28 0.15"))
        self.assertTrue(any("slot A and slot B" in problem for problem in problems))

    def test_spare_canister_off_shelf_is_reported(self):
        problems = STAGE.validate_layout(args_for("--shelf-count", "3", "--shelf-pitch", "0.08"))
        self.assertTrue(any("shelf canister 3" in problem for problem in problems))

    def test_tight_pitch_is_reported(self):
        problems = STAGE.validate_layout(args_for("--shelf-pitch", "0.03"))
        self.assertTrue(any("--shelf-pitch" in problem for problem in problems))

    def test_slot_not_on_body_is_reported(self):
        problems = STAGE.validate_layout(args_for("--slot-b-xyz", "0.35 -0.37 0.30"))
        self.assertTrue(any("slot B bottom" in problem for problem in problems))

    def test_plan_targets_the_requested_slot(self):
        args = args_for()
        plan_a = {step[0]: step[1] for step in STAGE.plan_selfdemo(args, "a")}
        plan_b = {step[0]: step[1] for step in STAGE.plan_selfdemo(args, "b")}
        self.assertEqual((0.35, -0.25), plan_a["insert"][:2])
        self.assertEqual((0.35, -0.37), plan_b["insert"][:2])
        self.assertEqual(plan_a["lift"], plan_b["lift"])  # same carry height for A and B


class HoldingTests(unittest.TestCase):
    def test_closed_and_near_is_holding(self):
        self.assertTrue(STAGE.holding_state(True, (0.0, 0.0, 0.1), (0.0, 0.0, 0.08), 0.05))

    def test_open_or_far_or_unknown_is_not_holding(self):
        self.assertFalse(STAGE.holding_state(False, (0.0, 0.0, 0.1), (0.0, 0.0, 0.08), 0.05))
        self.assertFalse(STAGE.holding_state(True, (0.0, 0.0, 0.1), (0.0, 0.0, 0.0), 0.05))
        self.assertFalse(STAGE.holding_state(True, None, (0.0, 0.0, 0.0), 0.05))

    def test_threshold_is_strict(self):
        self.assertFalse(STAGE.holding_state(True, (0.0, 0.0, 0.05), (0.0, 0.0, 0.0), 0.05))


class JointCommandTests(unittest.TestCase):
    NAMES = ["joint_1", "joint_2", "joint_3", "joint_4", "joint_5", "joint_6"]

    def test_full_and_partial_commands_are_accepted(self):
        targets, reason = STAGE.filter_joint_command(self.NAMES, self.NAMES, [0.1] * 6)
        self.assertIsNone(reason)
        self.assertEqual(6, len(targets))
        targets, reason = STAGE.filter_joint_command(self.NAMES, ["joint_3"], [0.5])
        self.assertIsNone(reason)
        self.assertEqual({"joint_3": 0.5}, targets)

    def test_foreign_names_drop_the_whole_command(self):
        targets, reason = STAGE.filter_joint_command(self.NAMES, ["joint_1", "shoulder_pan_joint"], [0.0, 0.0])
        self.assertEqual({}, targets)
        self.assertIn("shoulder_pan_joint", reason)

    def test_malformed_commands_are_dropped(self):
        for names, positions in (([], []), (["joint_1"], []), (["joint_1", "joint_1"], [0.0, 0.1]),
                                 (["joint_1"], [float("nan")])):
            with self.subTest(names=names, positions=positions):
                targets, reason = STAGE.filter_joint_command(self.NAMES, names, positions)
                self.assertEqual({}, targets)
                self.assertIsNotNone(reason)


class PoseMathTests(unittest.TestCase):
    def assertVecAlmostEqual(self, expected, actual, places=6):
        for e, a in zip(expected, actual, strict=True):
            self.assertAlmostEqual(e, a, places=places)

    def test_rotate_by_downward_tool_quat_flips_z(self):
        self.assertVecAlmostEqual((0.0, 0.0, -0.19671), STAGE.quat_rotate((0.0, 1.0, 0.0, 0.0), (0.0, 0.0, 0.19671)))

    def test_relative_pose_round_trips(self):
        half = math.sqrt(0.5)
        parent = ((0.3, -0.1, 0.4), (half, 0.0, 0.0, half))  # 90 deg about z
        child = ((0.3, 0.1, 0.4), (1.0, 0.0, 0.0, 0.0))
        local_xyz, local_quat = STAGE.relative_pose(*parent, *child)
        self.assertVecAlmostEqual((0.2, 0.0, 0.0), local_xyz)
        back = STAGE.tcp_world(parent[0], parent[1], local_xyz)
        self.assertVecAlmostEqual(child[0], back)
        self.assertVecAlmostEqual(child[1], STAGE.quat_multiply(parent[1], local_quat))


class SelfdemoPlanTests(unittest.TestCase):
    def test_phases_follow_the_m0609_arm_sequence(self):
        plan = STAGE.plan_selfdemo(args_for())
        self.assertEqual(["to_shelf", "descend", "grasp", "lift", "to_slot", "insert", "release", "retreat"],
                         [step[0] for step in plan])
        self.assertEqual(["open", "open", "close", "close", "close", "close", "open", "open"],
                         [step[2] for step in plan])

    def test_carried_canister_clears_shelf_and_slot_and_lands_in_cavity(self):
        args = args_for()
        plan = {step[0]: step[1] for step in STAGE.plan_selfdemo(args)}
        height = args.canister_size[2]
        below_tcp = height - args.grip_depth
        top = max(args.shelf_xyz[2] + args.shelf_size[2] / 2, args.slot_xyz[2] + args.slot_size[2] / 2)
        for phase in ("lift", "to_slot"):
            self.assertGreaterEqual(plan[phase][2] - below_tcp, top + args.clearance - 1e-9)
        center_in_slot = (plan["insert"][0], plan["insert"][1], plan["insert"][2] - (height / 2 - args.grip_depth))
        cavity = STAGE.aabb(*STAGE.slot_cavity(args.slot_xyz, args.slot_size, args.slot_wall))
        self.assertTrue(STAGE.point_in_aabb(center_in_slot, cavity))
        self.assertAlmostEqual(plan["descend"][2], args.canister_xyz[2] + height / 2 - args.grip_depth)

    def test_teach_keys_match_m0609_arm_parameters(self):
        self.assertEqual("shelf_approach", STAGE.teach_key("to_shelf", "a"))
        self.assertEqual("shelf_grasp", STAGE.teach_key("descend", "a"))
        self.assertEqual("slot_b_approach", STAGE.teach_key("to_slot", "b"))
        self.assertEqual("slot_b_insert", STAGE.teach_key("insert", "b"))
        self.assertIsNone(STAGE.teach_key("grasp", "a"))

    def test_interpolation_helpers(self):
        self.assertEqual(30, STAGE.interpolation_steps((0, 0, 0), (0, 0, 0.001), 0.002))
        self.assertEqual(6000, STAGE.interpolation_steps((0, 0, 0), (0, 0, 100), 0.002))
        self.assertEqual((0.5, 1.0, 1.5), STAGE.lerp((0, 0, 0), (1, 2, 3), 0.5))
        self.assertEqual((1.0, 2.0, 3.0), STAGE.lerp((0, 0, 0), (1, 2, 3), 7.0))


if __name__ == "__main__":
    unittest.main()
