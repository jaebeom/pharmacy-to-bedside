"""Belt release when the UR5 holds the belt pouch (contract 11.1 a). No Isaac.

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
PRESETS = ("demo-ros", "demo-ros-refill", "demo-ros-refill-v2", "hospital-v2")


def load_stage():
    spec = importlib.util.spec_from_file_location("pharmacy_stage", STANDALONE / "pharmacy_stage.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def pouch_at_end():
    model = belt.BeltModel(length=1.2, width=0.2, end_zone_length=0.15, settle_speed=0.01, settle_time_s=0.3)
    model.accept("r001-0001", "ord-0001", 0.0)
    model.observe(END, 0.15, 1.0)
    model.observe(END, 0.0, 1.1)
    assert model.observe(END, 0.0, 1.5)[0] == [belt.POUCH_AT_END]
    return model


class ObserveHeldTests(unittest.TestCase):
    def test_held_over_the_belt_keeps_it_occupied(self):
        model = pouch_at_end()
        for frame in (END, (1.12, 0.0, 0.04), (1.21, 0.05, 0.0)):  # first tick, lifting, still inside the margins
            self.assertFalse(model.observe_held(frame))
        self.assertEqual({"occupied": True, "at_end": True, "order_id": "ord-0001"}, model.state())

    def test_held_off_the_belt_frees_it(self):
        model = pouch_at_end()
        self.assertTrue(model.observe_held((1.12, 0.0, 0.2)))  # lifted above the on-belt height
        self.assertEqual({"occupied": False, "at_end": False, "order_id": ""}, model.state())
        self.assertEqual("", model.decide_dispense("ord-0002", ready=True, known_order=True))

    def test_unknown_pose_or_free_belt_changes_nothing(self):
        model = pouch_at_end()
        self.assertFalse(model.observe_held(None))  # fail-closed: no pose is not "off the belt"
        self.assertTrue(model.occupied)
        free = belt.BeltModel(length=1.2, width=0.2, end_zone_length=0.15)
        self.assertFalse(free.observe_held((1.12, 0.0, 0.2)))

    def test_release_back_onto_the_belt_keeps_the_latched_at_end(self):
        model = pouch_at_end()
        self.assertFalse(model.observe_held((1.12, 0.0, 0.03)))
        self.assertEqual(([], []), model.observe(END, 0.0, 2.0))  # suction off over the belt: normal path again
        self.assertTrue(model.at_end and model.occupied)


class StageScopeTests(unittest.TestCase):
    def test_only_a_ur5_cell_takes_the_held_path(self):
        stage = load_stage()
        for name in PRESETS:
            with self.subTest(preset=name):
                self.assertFalse(stage.parse_args(["--preset", name]).ur5)
        source = (STANDALONE / "pharmacy_stage.py").read_text()
        # 받침대 UR5 는 `--ur5` 로만 생기고, 합본(`--amr-usd`)이면 안 만든다 — 팔이 둘이 되면
        # `/amr_1/arm/joint_command` 의 수신자가 갈라진다(받침대는 접두 없는 이름, 합본은 `ur_arm_*`).
        self.assertIn("cell = None\n        if args.ur5 and args.amr_combined:", source)
        self.assertIn("if args.ur5 and not args.amr_combined:", source)
        # **붙잡은 경로는 받침대 전용이 아니다.** 위 두 줄이 막는 것은 "팔이 둘이 되는 것" 이고,
        # 봉투를 든 쪽이 누구냐는 별개다. lap12 에서 이 분기가 `cell` 만 보는 바람에 합본이 든 봉투가
        # 벨트를 벗어나며 `remove_pouch` 로 풀에서 빠졌고, 트레이에 놓인 뒤로 센서가 못 봤다.
        self.assertIn("holder = cell if cell is not None else amr_suction", source)
        self.assertIn("if holder is not None and holder.held is not None and holder.held[0] is obj:", source)


if __name__ == "__main__":
    unittest.main()
