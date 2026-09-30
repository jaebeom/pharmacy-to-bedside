"""TIMEOUT diagnosis for the UR5 pick: the last IK solution against the joints as they are. No Isaac.

L3-2 9/20: every tcp phase stopped 6.5-7 cm short with suction never engaging. A large joint gap means the joints
did not follow the solution; a small one means the solution itself was off.

    python3 -m unittest discover -s sim/tests -p 'test_[mp]*.py'
"""

import sys
import unittest
from pathlib import Path

STANDALONE = Path(__file__).resolve().parents[1] / "standalone"
sys.path.insert(0, str(STANDALONE))

from p3sim import ur5_cell  # noqa: E402

TARGETS = {"shoulder_pan_joint": 0.50, "shoulder_lift_joint": -1.20, "elbow_joint": 0.90}
FOLLOWED = {"shoulder_pan_joint": 0.4999, "shoulder_lift_joint": -1.2001, "elbow_joint": 0.9000}
LAGGING = {"shoulder_pan_joint": 0.41, "shoulder_lift_joint": -1.19, "elbow_joint": 0.90}


class JointGapTests(unittest.TestCase):
    def test_sorted_by_size_of_the_difference(self):
        rows = ur5_cell.joint_gap(TARGETS, LAGGING)
        self.assertEqual(["shoulder_pan_joint", "shoulder_lift_joint", "elbow_joint"], [r[0] for r in rows])
        self.assertAlmostEqual(0.09, rows[0][3], places=6)
        self.assertAlmostEqual(-0.01, rows[1][3], places=6)

    def test_only_joints_that_were_read(self):
        rows = ur5_cell.joint_gap(TARGETS, {"elbow_joint": 0.80})
        self.assertEqual([("elbow_joint", 0.90, 0.80, 0.10)], [(n, round(t, 2), round(a, 2), round(d, 2))
                                                               for n, t, a, d in rows])

    def test_line_names_the_worst_joints(self):
        line = ur5_cell.joint_gap_line((2.8, 0.99, 0.82), True, TARGETS, LAGGING)
        self.assertIn("tcp_target=[2.8000, 0.9900, 0.8200]", line)
        self.assertIn("solved=True", line)
        self.assertIn("max_joint_diff_rad=0.0900", line)
        self.assertIn("shoulder_pan_joint: want 0.5000 have 0.4100 diff +0.0900", line)

    def test_line_when_the_joints_followed(self):
        line = ur5_cell.joint_gap_line((2.8, 0.99, 0.82), True, TARGETS, FOLLOWED)
        self.assertIn("max_joint_diff_rad=0.0001", line)

    def test_line_without_anything_to_compare(self):
        line = ur5_cell.joint_gap_line((1.0, 0.0, 0.5), False, {}, {})
        self.assertIn("nothing to compare", line)
        self.assertIn("solved=False", line)


class WiringTests(unittest.TestCase):
    def setUp(self):
        self.cell = (STANDALONE / "p3sim" / "ur5_cell.py").read_text()
        self.stage = (STANDALONE / "pharmacy_stage.py").read_text()

    def test_ik_to_records_the_solution(self):
        ik = self.cell[self.cell.index("    def ik_to(self"):self.cell.index("    def ik_report(self")]
        self.assertIn("self.last_ik = (tuple(float(v) for v in tcp_xyz), bool(solved), targets)", ik)
        self.assertLess(ik.index("self.last_ik ="), ik.index("self.robot.apply_action(action)"))

    def test_timeout_logs_the_check(self):
        body = self.stage[self.stage.index('status = "reached" if kind != "tcp"'):]
        body = body[:body.index("event = seq.phase_done()")]
        self.assertIn('if status == "TIMEOUT":', body)
        self.assertIn('log(f"ur5 ik_check phase={phase} {cell.ik_report()}")', body)

    def test_ur5_contacts_are_opt_in(self):
        self.assertIn('parser.add_argument("--ur5-contact-log", action="store_true"', self.stage)
        watch = self.stage[self.stage.index("contact_watch = None"):self.stage.index("def log_surface(")]
        self.assertIn("if cell is not None and args.ur5_contact_log:", watch)


if __name__ == "__main__":
    unittest.main()
