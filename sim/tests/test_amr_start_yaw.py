"""AMR 시작·리셋 방향과 세계 yaw 규약. Isaac 없이 articulation 호출을 확인한다."""
import importlib.util
import math
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "standalone"))
from p3sim import amr_base  # noqa: E402


@unittest.skipUnless(importlib.util.find_spec("numpy"), "requires numpy")
class AmrStartYaw(unittest.TestCase):
    def runtime(self, yaw=0.0):
        runtime = amr_base.Runtime(None, "/Amr", (-8.995, 4.686), start_yaw=yaw, log=lambda _: None)
        runtime.articulation = Mock()
        runtime.indices = [3, 7, 1]
        runtime._action = SimpleNamespace
        return runtime

    def test_start_and_repeated_reset_keep_dock_yaw_and_zero_velocity(self):
        runtime = self.runtime(-math.pi / 2)
        for _ in range(2):
            runtime._last_command_s = 100.0
            runtime.reset()
            args, kwargs = runtime.articulation.set_joint_positions.call_args
            self.assertEqual(args[0].tolist(), [0.0, 0.0, -math.pi / 2])
            self.assertEqual(kwargs["joint_indices"].tolist(), [3, 7, 1])
            self.assertEqual(runtime.articulation.set_joint_velocities.call_args.args[0].tolist(), [0.0] * 3)
            action = runtime.articulation.apply_action.call_args.args[0]
            self.assertEqual(action.joint_velocities.tolist(), [0.0] * 3)
            self.assertIsNone(runtime._last_command_s)

    def test_default_start_is_zero_for_existing_nonhospital_callers(self):
        runtime = self.runtime()
        runtime.reset()
        self.assertEqual(runtime.articulation.set_joint_positions.call_args.args[0].tolist(), [0.0] * 3)

    def test_world_pose_does_not_add_initial_yaw_to_absolute_joint_yaw(self):
        runtime = self.runtime(-math.pi / 2)
        runtime.read = lambda: ((1.0, 2.0, -math.pi / 2), (0.0, 0.0, 0.0))
        for got, expected in zip(runtime.base_world_pose(), (-7.995, 6.686, -math.pi / 2), strict=True):
            self.assertAlmostEqual(got, expected)
