"""Suction target on the ROS UR5 path: the belt pouch or a pouch already on the deck (VA-1). No Isaac.

    python3 -m unittest discover -s sim/tests -p 'test_[mp]*.py'
"""

import sys
import unittest
from pathlib import Path

STANDALONE = Path(__file__).resolve().parents[1] / "standalone"
sys.path.insert(0, str(STANDALONE))

from p3sim import ur5_cell  # noqa: E402


class NearestWithinTests(unittest.TestCase):
    def test_nearest_candidate_within_the_limit(self):
        placed = [("belt", (1.0, 0.0, 0.8)), ("deck1", (0.2, 0.0, 0.5)), ("deck2", (0.25, 0.0, 0.5))]
        self.assertEqual("deck1", ur5_cell.nearest_within((0.2, 0.0, 0.52), placed, 0.05)[0])
        self.assertEqual("belt", ur5_cell.nearest_within((1.0, 0.0, 0.83), placed, 0.05)[0])

    def test_nothing_within_the_limit(self):
        placed = [("belt", (1.0, 0.0, 0.8))]
        target, distance = ur5_cell.nearest_within((1.0, 0.0, 0.9), placed, 0.05)
        self.assertIsNone(target)
        self.assertAlmostEqual(0.1, distance)
        self.assertEqual((None, None), ur5_cell.nearest_within((0.0, 0.0, 0.0), [], 0.05))

    def test_limit_is_inclusive_like_suck(self):
        self.assertEqual("p", ur5_cell.nearest_within((0.0, 0.0, 0.0), [("p", (0.05, 0.0, 0.0))], 0.05)[0])


class StageWiringTests(unittest.TestCase):
    def setUp(self):
        self.stage = (STANDALONE / "pharmacy_stage.py").read_text()
        self.cell = (STANDALONE / "p3sim" / "ur5_cell.py").read_text()

    def test_ros_ur5_path_offers_belt_and_deck_pouches(self):
        ros_ur5 = self.stage[self.stage.index("if ur5_ros is not None and cell is not None:"):
                             self.stage.index("if arm is not None and args.ros_refill_selfdemo:")]
        self.assertIn("apply_suction(closed)", ros_ur5)
        suction = self.stage[self.stage.index("def apply_suction(close):"):self.stage.index("def dispense(")]
        self.assertIn('[pool_objects[index] for index in state["carried"]]', suction)
        self.assertIn('candidates.append(state["pouch"])', suction)
        self.assertIn("cell.suck_nearest(candidates)", suction)
        self.assertIn("cell.suck(False, None)", suction)

    def test_selfdemo_path_is_unchanged(self):
        self.assertIn('cell.suck(suction == "on", u["pouch"])', self.stage)

    def test_no_target_is_logged(self):
        self.assertIn("ur5 suction miss target=none candidates=", self.cell)
        suck = self.cell[self.cell.index("    def suck(self"):self.cell.index("    def suck_nearest")]
        self.assertIn("ur5 suction miss target=none", suck)  # suck(True, None) no longer passes silently


if __name__ == "__main__":
    unittest.main()
