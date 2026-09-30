"""Opt-in --belt-fail-closed (contract 11.1 proposal, off by default). No Isaac.

Default behaviour stays as pinned by R1-R3 in test_pharmacy_belt_characterization.py.

    python3 -m unittest discover -s sim/tests -p 'test_[mp]*.py'
"""

import importlib.util
import sys
import unittest
from pathlib import Path

STANDALONE = Path(__file__).resolve().parents[1] / "standalone"
sys.path.insert(0, str(STANDALONE))

from p3sim import belt  # noqa: E402

END = (1.12, 0.0, 0.0)
MID = (0.5, 0.0, 0.0)
PRESETS = ("demo-ros", "demo-ros-refill", "demo-ros-refill-v2", "hospital-v2")


def load_stage():
    spec = importlib.util.spec_from_file_location("pharmacy_stage", STANDALONE / "pharmacy_stage.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def travelling(fail_closed=True):
    model = belt.BeltModel(length=1.2, width=0.2, end_zone_length=0.15, settle_speed=0.01, settle_time_s=0.3,
                           fail_closed=fail_closed)
    model.accept("r001-0001", "ord-0001", 0.0)
    model.observe(MID, 0.15, 1.0)
    return model


class FailClosedModelTests(unittest.TestCase):
    def test_missing_velocity_is_not_a_settle_sample(self):
        model = travelling()
        model.observe(END, 0.15, 2.0)
        model.observe(END, 0.0, 2.1)
        self.assertEqual([], model.observe(END, None, 2.3)[0])  # resets the timer started at 2.1
        self.assertEqual([], model.observe(END, 0.0, 2.5)[0])
        self.assertEqual([belt.POUCH_AT_END], model.observe(END, 0.0, 2.9)[0])  # 0.3 s of received samples

    def test_lost_pouch_keeps_the_belt_occupied_until_reset(self):
        for frame in (None, (0.6, 0.5, 0.0)):  # no pose, off the belt
            with self.subTest(frame=frame):
                model = travelling()
                self.assertEqual(([], ["pouch_lost"]), model.observe(frame, 0.3, 1.1))
                self.assertEqual({"occupied": True, "at_end": False, "order_id": "ord-0001"}, model.state())
                self.assertEqual(belt.BELT_OCCUPIED, model.decide_dispense("ord-0002", ready=True, known_order=True))
                self.assertEqual(([], []), model.observe(END, 0.0, 5.0))  # back in view: still held, no event
                self.assertFalse(model.observe_held((1.12, 0.0, 0.2)))
                model.reset()
                self.assertEqual("", model.decide_dispense("ord-0002", ready=True, known_order=True))

    def test_loss_after_arrival_withdraws_at_end(self):
        model = travelling()
        model.observe(END, 0.15, 2.0)
        model.observe(END, 0.0, 2.1)
        self.assertEqual([belt.POUCH_AT_END], model.observe(END, 0.0, 2.5)[0])
        self.assertEqual(["pouch_lost"], model.observe((1.3, 0.0, -0.3), 0.5, 3.0)[1])  # fell off the end
        self.assertFalse(model.at_end)
        self.assertTrue(model.occupied)

    def test_default_model_is_unchanged(self):
        model = travelling(fail_closed=False)
        self.assertFalse(belt.BeltModel(1.2, 0.2, 0.15).fail_closed)
        self.assertEqual(["pouch_left_belt"], model.observe(None, 0.0, 1.1)[1])
        self.assertFalse(model.occupied)


class FailClosedStageTests(unittest.TestCase):
    def test_flag_is_off_by_default_and_in_every_preset(self):
        stage = load_stage()
        self.assertFalse(stage.parse_args([]).belt_fail_closed)
        for name in PRESETS:
            with self.subTest(preset=name):
                self.assertFalse(stage.parse_args(["--preset", name]).belt_fail_closed)
        self.assertTrue(stage.parse_args(["--preset", "demo-ros-refill-v2", "--belt-fail-closed"]).belt_fail_closed)

    def test_stage_wiring(self):
        source = (STANDALONE / "pharmacy_stage.py").read_text()
        observe = source[source.index("def observe_belt"):source.index("def do_reset")]
        self.assertIn("fail_closed=args.belt_fail_closed", source)
        self.assertIn("if velocity is None and args.belt_fail_closed:", observe)
        lost = observe[observe.index('if note == "pouch_lost":'):observe.index('if note == "pouch_left_belt":')]
        self.assertIn("set_belt(0.0)", lost)
        self.assertNotIn("remove_pouch", lost)  # the lost pouch is left in place; reset parks every pouch


if __name__ == "__main__":
    unittest.main()
