"""BeltObservation (contract 11.6) filled by the stage, published as JSON on /isaac/pharmacy/belt_observation behind
--belt-observation. No Isaac.

    python3 -m unittest discover -s sim/tests -p 'test_[mp]*.py'
"""

import importlib.util
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STANDALONE = ROOT / "sim" / "standalone"
sys.path.insert(0, str(STANDALONE))

from p3sim import belt, bridge  # noqa: E402
from p3sim import observation as obs  # noqa: E402

MSG = ROOT / "src" / "rokey_p3_interfaces" / "msg" / "BeltObservation.msg"
PRESETS = ("demo-ros", "demo-ros-refill", "demo-ros-refill-v2", "hospital-v2")
END, MID = (1.52, 0.0, 0.0), (0.8, 0.0, 0.0)


def load_stage():
    spec = importlib.util.spec_from_file_location("pharmacy_stage", STANDALONE / "pharmacy_stage.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def model(fail_closed=False):
    m = belt.BeltModel(1.6, 0.25, 0.15, fail_closed=fail_closed)
    m.accept("r001-0001", "ord-0001", 0.0)
    return m


class ZoneTests(unittest.TestCase):
    def test_zones(self):
        m = model()
        self.assertEqual(obs.ZONE_ON_BELT, obs.pouch_zone(m, MID))
        self.assertEqual(obs.ZONE_END, obs.pouch_zone(m, END))
        self.assertEqual(obs.ZONE_OFF_BELT, obs.pouch_zone(m, (0.8, 0.5, 0.0)))
        self.assertEqual(obs.ZONE_OFF_BELT, obs.pouch_zone(m, (1.52, 0.0, 0.3)))  # lifted away
        self.assertEqual(obs.ZONE_UNKNOWN, obs.pouch_zone(m, None))

    def test_zone_is_not_latched(self):
        m = model()
        self.assertEqual(obs.ZONE_END, obs.pouch_zone(m, END))
        self.assertEqual(obs.ZONE_ON_BELT, obs.pouch_zone(m, MID))


class MotionTests(unittest.TestCase):
    def test_stopped_only_after_the_settle_time_without_a_gap(self):
        tracker = obs.MotionTracker(0.01, 0.3)
        self.assertEqual(obs.MOTION_UNKNOWN, tracker.motion)
        self.assertEqual(obs.MOTION_MOVING, tracker.update(0.15, 1.0))
        self.assertEqual(obs.MOTION_MOVING, tracker.update(0.0, 1.1))  # slow, not settled yet
        self.assertEqual(obs.MOTION_UNKNOWN, tracker.update(None, 1.2))  # gap restarts the settle time
        self.assertEqual(obs.MOTION_MOVING, tracker.update(0.0, 1.3))
        self.assertEqual(obs.MOTION_STOPPED, tracker.update(0.005, 1.7))
        self.assertEqual(obs.MOTION_MOVING, tracker.update(0.05, 1.8))

    def test_stopped_mid_belt_is_stopped_but_not_in_the_end_zone(self):
        # a jam: STOPPED alone would permit a pick; the zone says it is not at the end (contract 11.6)
        tracker, m = obs.MotionTracker(0.01, 0.3), model()
        tracker.update(0.0, 1.0)
        self.assertEqual(obs.MOTION_STOPPED, tracker.update(0.0, 1.4))
        self.assertEqual(obs.ZONE_ON_BELT, obs.pouch_zone(m, MID))


class FieldTests(unittest.TestCase):
    def test_occupancy_and_lost_pouch(self):
        m = model(fail_closed=True)
        self.assertEqual(obs.OCCUPANCY_OCCUPIED, obs.occupancy(m))
        m.observe(None, None, 1.0)
        self.assertTrue(m.occupied)
        self.assertEqual(obs.OCCUPANCY_UNKNOWN, obs.occupancy(m))
        f = obs.fields(m, 1, 7, obs.MODE_SIM_SENSOR, obs.ZONE_OFF_BELT, obs.MOTION_STOPPED, obs.APPLIED_STOP)
        self.assertEqual((obs.ZONE_UNKNOWN, obs.MOTION_UNKNOWN), (f["pouch_zone"], f["pouch_motion"]))
        m.reset()
        self.assertEqual(obs.OCCUPANCY_EMPTY, obs.occupancy(m))

    def test_fields_encode_on_the_new_topic(self):
        m = model()
        f = obs.fields(m, 3, 42, obs.MODE_SIM_SENSOR, obs.ZONE_END, obs.MOTION_STOPPED, obs.APPLIED_STOP)
        text = bridge.encode(bridge.BELT_OBSERVATION, stamp=bridge.stamp(12.5), **f)
        message, problems = bridge.decode(bridge.BELT_OBSERVATION, text)
        self.assertEqual([], problems)
        self.assertEqual(("r001-0001", "ord-0001", 0), (message["request_id"], message["order_id"],
                                                         message["belt_motion"]))
        with self.assertRaises(ValueError):
            bridge.encode(bridge.BELT_OBSERVATION, stamp=bridge.stamp(1.0), **{**f, "pouch_zone": 4})
        after = model()
        after.reset()
        empty = obs.fields(after, 3, 43, obs.MODE_STUB, obs.ZONE_END, obs.MOTION_STOPPED, obs.APPLIED_STOP)
        self.assertEqual(("", "", obs.OCCUPANCY_EMPTY, obs.ZONE_UNKNOWN),
                         (empty["request_id"], empty["order_id"], empty["occupancy"], empty["pouch_zone"]))

    def test_command_applied_readback(self):
        self.assertEqual(obs.APPLIED_UNKNOWN, obs.command_applied(None))
        self.assertEqual(obs.APPLIED_STOP, obs.command_applied(0.0))
        self.assertEqual(obs.APPLIED_RUN, obs.command_applied(0.12))
        self.assertEqual(obs.APPLIED_STOP, obs.command_applied((0.0, 0.0, 0.0)))
        self.assertEqual(obs.APPLIED_RUN, obs.command_applied((0.12, 0.0, 0.0)))
        self.assertEqual(obs.APPLIED_UNKNOWN, obs.command_applied("x"))

    def test_step_counter_moves_only_with_sim_time(self):
        steps = obs.StepCounter()
        self.assertEqual(0, steps.tick(0.0))
        self.assertEqual(1, steps.tick(0.016))
        self.assertEqual(1, steps.tick(0.016))  # clock stalled
        self.assertEqual(1, steps.tick(0.010))  # rewound: never goes back
        self.assertEqual(2, steps.tick(0.033))

    def test_enums_match_the_interface_message(self):
        if not MSG.is_file():
            self.fail(f"missing {MSG.relative_to(ROOT)}")
        constants = dict(re.findall(r"^uint8 ([A-Z_]+)=(\d+)", MSG.read_text(), re.MULTILINE))
        ours = {name: getattr(obs, name) for name in constants}
        self.assertEqual({k: int(v) for k, v in constants.items()}, ours)
        fields = re.findall(r"^(?:string|uint8|uint32|std_msgs/Header) ([a-z_]+)\s", MSG.read_text(), re.MULTILINE)
        schema = set(bridge.SCHEMAS[bridge.BELT_OBSERVATION]) - {"v"}
        self.assertEqual({"stamp" if f == "header" else f for f in fields}, schema)


class StageTests(unittest.TestCase):
    def test_opt_in_and_presets_unchanged(self):
        stage = load_stage()
        self.assertFalse(stage.parse_args([]).belt_observation)
        for name in PRESETS:
            with self.subTest(preset=name):
                self.assertFalse(stage.parse_args(["--preset", name]).belt_observation)

    def test_wiring(self):
        source = (STANDALONE / "pharmacy_stage.py").read_text()
        self.assertIn("extra_publish=((bridge.BELT_OBSERVATION,) if args.belt_observation else ())", source)
        publish = source[source.index("if ros is not None and now >= next_belt:"):]
        publish = publish[:publish.index("next_belt = common.next_publish_time")]
        self.assertLess(publish.index("bridge.BELT, bridge.encode(bridge.BELT"),
                        publish.index("if args.belt_observation:"))
        self.assertIn("obslib.command_applied(belt_command_readback())", publish)
        # 순서: 한 틱 돌리고 → 센 다음 → 관측 seq 를 올린다. 사이에 낀 줄(긴 틱 진단)은 상관하지 않는다.
        for earlier, later in (("step_world()", "updates += 1"), ("updates += 1", "physics_steps.tick(sim_now())")):
            self.assertLess(source.index(earlier), source.index(later))
        self.assertIn('if reason in obslib.STUB_RELEASES:', source)


if __name__ == "__main__":
    unittest.main()
