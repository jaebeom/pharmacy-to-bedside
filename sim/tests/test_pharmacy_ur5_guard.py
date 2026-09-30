"""Real-pick readiness in pharmacy_stage.py: with --ur5 no stand-in or pick_notice frees the belt. No Isaac.

    python3 -m unittest discover -s sim/tests -p 'test_[mp]*.py'
"""

import contextlib
import importlib.util
import io
import sys
import unittest
from pathlib import Path

STANDALONE = Path(__file__).resolve().parents[1] / "standalone"
sys.path.insert(0, str(STANDALONE))

GUARD = "--ur5 cannot run with --ros-pick-stand-in-s"
PRESETS_WITH_STAND_IN = ("demo-ros", "demo-ros-refill", "demo-ros-refill-v2", "hospital-v2")


def load_stage():
    spec = importlib.util.spec_from_file_location("pharmacy_stage", STANDALONE / "pharmacy_stage.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


STAGE = load_stage()


def guard_problems(argv):
    return [p for p in STAGE.validate(STAGE.parse_args(argv)) if p.startswith(GUARD)]


class Ur5StandInGuardTests(unittest.TestCase):
    def test_presets_alone_are_unchanged(self):
        for name in PRESETS_WITH_STAND_IN:
            with self.subTest(preset=name):
                args = STAGE.parse_args(["--preset", name])
                self.assertEqual(5.0, args.ros_pick_stand_in_s)
                self.assertFalse(args.ur5)
                self.assertEqual([], guard_problems(["--preset", name]))
        self.assertEqual([], guard_problems([]))
        self.assertEqual([], guard_problems(["--mode", "ros", "--ros-pick-stand-in-s", "3"]))

    def test_ur5_with_a_stand_in_is_refused(self):
        for name in PRESETS_WITH_STAND_IN:
            with self.subTest(preset=name):
                self.assertEqual(1, len(guard_problems(["--preset", name, "--ur5"])))
        problems = guard_problems(["--mode", "ros", "--ur5", "--ros-pick-stand-in-s", "2"])
        self.assertEqual(1, len(problems))
        self.assertIn("give --ros-pick-stand-in-s 0", problems[0])

    def test_ur5_with_the_stand_in_off_passes(self):
        self.assertEqual([], guard_problems(["--ur5"]))
        for name in PRESETS_WITH_STAND_IN:
            with self.subTest(preset=name):
                self.assertEqual([], guard_problems(["--preset", name, "--ur5", "--ros-pick-stand-in-s", "0"]))

    def test_refusal_exits_2_before_isaac(self):
        args = STAGE.parse_args(["--preset", "demo-ros-refill-v2", "--ur5"])
        err = io.StringIO()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
            self.assertEqual(2, STAGE.run(args))
        self.assertIn(GUARD, err.getvalue())
        self.assertNotIn("isaacsim", sys.modules)

    def test_pick_notice_is_counted_not_applied_with_ur5(self):
        source = (STANDALONE / "pharmacy_stage.py").read_text()
        handle = source[source.index("def handle_ros"):source.index("def setup_refill_demo")]
        notice = handle[handle.index("ros.take(bridge.PICK_NOTICE)"):handle.index("bridge.pick_notice_applies(")]
        self.assertIn("if args.ur5:", notice)
        self.assertIn('state["pick_notices_ignored_ur5"] += 1', notice)
        self.assertIn("reason=ur5_picks", notice)
        self.assertIn("continue", notice[notice.index("if args.ur5:"):])
        self.assertIn("pick_notices_ignored_ur5={state['pick_notices_ignored_ur5']}", source)


if __name__ == "__main__":
    unittest.main()
