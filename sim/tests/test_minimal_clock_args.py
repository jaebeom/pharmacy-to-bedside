"""Plain-Python checks for sim/standalone/minimal_clock.py; Isaac is not needed and not started.

    python3 -m unittest discover -s sim/tests -p 'test_minimal_clock_args.py'
"""

import contextlib
import importlib.util
import io
import signal
import sys
import threading
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "standalone" / "minimal_clock.py"
ISAAC_MODULES = ("isaacsim", "omni", "pxr", "carb")


def load_script():
    spec = importlib.util.spec_from_file_location("minimal_clock", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ImportGuardTests(unittest.TestCase):
    def test_module_import_does_not_touch_isaac(self):
        before = {name for name in sys.modules if name.split(".")[0] in ISAAC_MODULES}
        load_script()
        after = {name for name in sys.modules if name.split(".")[0] in ISAAC_MODULES}
        self.assertEqual(before, after)


class ArgumentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.clock = load_script()

    def test_defaults(self):
        args = self.clock.parse_args([])
        self.assertFalse(args.headless)
        self.assertEqual(60.0, args.rate)
        self.assertEqual(0.0, args.duration)
        self.assertIsNone(args.physics_dt)
        self.assertIsNone(args.render_dt)
        self.assertEqual(0.0, args.stop_play_after)

    def test_explicit_values(self):
        args = self.clock.parse_args(
            ["--headless", "--rate", "30", "--duration", "5", "--physics-dt", "0.005", "--render-dt", "0.02",
             "--stop-play-after", "3"]
        )
        self.assertTrue(args.headless)
        self.assertEqual((30.0, 5.0, 0.005, 0.02, 3.0),
                         (args.rate, args.duration, args.physics_dt, args.render_dt, args.stop_play_after))

    def test_unknown_kit_arguments_are_ignored(self):
        args = self.clock.parse_args(["--headless", "--/app/some/setting=1"])
        self.assertTrue(args.headless)

    def test_invalid_values_fail(self):
        for argv in (["--rate", "0"], ["--rate", "-1"], ["--duration", "-1"], ["--physics-dt", "0"],
                     ["--render-dt", "nan"]):
            with self.subTest(argv=argv), self.assertRaises(SystemExit), \
                    contextlib.redirect_stderr(io.StringIO()):
                self.clock.build_parser().parse_args(argv)


class ContractConstantTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.clock = load_script()

    def test_clock_topic_and_qos_match_contract(self):
        # Contract v1 2.1: /clock, R = reliable volatile depth 10. Empty qosProfile keeps rmw defaults.
        self.assertEqual("clock", self.clock.CLOCK_TOPIC)
        self.assertEqual("", self.clock.CLOCK_QOS_PROFILE)
        self.assertEqual(10, self.clock.CLOCK_QUEUE_SIZE)
        self.assertEqual(60.0, self.clock.DEFAULT_RATE_HZ)

    def test_sim_time_is_monotonic_across_stop(self):
        # Contract v1 4: sim time rewinds only through the reset barrier, never on a plain Stop/Play.
        self.assertIs(False, self.clock.READ_SIM_TIME_RESET_ON_STOP)

    def test_node_and_extension_names(self):
        self.assertEqual("isaacsim.ros2.bridge", self.clock.ROS2_BRIDGE_EXTENSION)
        self.assertEqual("isaacsim.ros2.bridge.ROS2PublishClock", self.clock.NODE_PUBLISH_CLOCK)
        self.assertEqual("isaacsim.core.nodes.IsaacReadSimulationTime", self.clock.NODE_READ_SIM_TIME)
        self.assertEqual("omni.graph.action.OnPlaybackTick", self.clock.NODE_ON_PLAYBACK_TICK)


class LoggingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.clock = load_script()

    def test_environment_summary_distinguishes_library_sources(self):
        internal = self.clock.environment_summary({
            "RMW_IMPLEMENTATION": "rmw_fastrtps_cpp", "ROS_DOMAIN_ID": "115", "ROS_DISTRO": "jazzy",
            "LD_LIBRARY_PATH": "/x:/home/rokey/isaacsim/exts/isaacsim.ros2.bridge/jazzy/lib",
            "FASTRTPS_DEFAULT_PROFILES_FILE": "/home/rokey/.ros/fastdds_whitelist.xml",
        })
        self.assertEqual("115", internal["ROS_DOMAIN_ID"])
        self.assertEqual("/home/rokey/.ros/fastdds_whitelist.xml", internal["FASTRTPS_DEFAULT_PROFILES_FILE"])
        self.assertTrue(internal["ld_internal_jazzy"])
        self.assertFalse(internal["ld_opt_ros"])

        system = self.clock.environment_summary({"LD_LIBRARY_PATH": "/opt/ros/jazzy/lib"})
        self.assertEqual("<unset>", system["RMW_IMPLEMENTATION"])
        self.assertEqual("<unset>", system["FASTRTPS_DEFAULT_PROFILES_FILE"])
        self.assertFalse(system["ld_internal_jazzy"])
        self.assertTrue(system["ld_opt_ros"])

    def test_start_line_is_one_line_with_required_fields(self):
        line = self.clock.format_start_line(
            "5.1.0-rc.19", self.clock.environment_summary({"ROS_DOMAIN_ID": "115"}), 1 / 60, 1 / 60, 60.0
        )
        self.assertNotIn("\n", line)
        for field in ("isaac=5.1.0-rc.19", "RMW_IMPLEMENTATION=", "ROS_DOMAIN_ID=115",
                      "FASTRTPS_DEFAULT_PROFILES_FILE=", "physics_dt=",
                      "render_dt=", "topic=/clock", "reset_on_stop=False", "expected_rtf=1.000"):
            self.assertIn(field, line)


class LoopConditionTests(unittest.TestCase):
    def test_running_app_always_continues(self):
        clock = load_script()
        self.assertTrue(clock.keep_running(True, False, False))
        self.assertTrue(clock.keep_running(True, False, True))

    def test_headless_ignores_early_false_but_not_exit(self):
        clock = load_script()
        self.assertTrue(clock.keep_running(False, False, True))
        self.assertFalse(clock.keep_running(False, True, True))

    def test_windowed_stops_when_app_stops(self):
        clock = load_script()
        self.assertFalse(clock.keep_running(False, False, False))


class SignalTests(unittest.TestCase):
    def test_sigint_sets_flag_instead_of_exiting(self):
        clock = load_script()
        stop_event = threading.Event()
        previous = clock.install_sigint_handler(stop_event)
        self.addCleanup(signal.signal, signal.SIGINT, previous)
        signal.raise_signal(signal.SIGINT)
        self.assertTrue(stop_event.is_set())


if __name__ == "__main__":
    unittest.main()
