"""#697 avoidance_encounters: AMR 2 m 안에 든 보행자·더미 구간 줄."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "standalone"))

from p3sim import encounters  # noqa: E402


class TrackerTests(unittest.TestCase):
    def test_one_start_and_one_end_with_the_closest_distance(self):
        tracker = encounters.Tracker()
        amr = (0.0, 0.0)
        lines = []
        for t, x in enumerate((3.0, 1.9, 0.8, 1.5, 2.05, 2.2, 2.5)):
            lines += tracker.update(float(t), amr, {"ped_1": (x, 0.0)})
        self.assertEqual(["encounter start who=ped_1 dist_min=1.900 sim=1.00",
                          "encounter end who=ped_1 dist_min=0.800 sim=5.00"], lines)

    def test_edge_wobble_does_not_repeat_lines(self):
        """2.0 ↔ 2.05 를 오가도 나가는 선(2.1) 안이라 구간 하나다."""
        tracker = encounters.Tracker()
        lines = []
        for t, x in enumerate((1.99, 2.05, 1.98, 2.08, 1.99)):
            lines += tracker.update(float(t), (0.0, 0.0), {"dummy_1": (x, 0.0)})
        self.assertEqual(1, len(lines))

    def test_each_prop_has_its_own_span_and_no_amr_means_no_line(self):
        tracker = encounters.Tracker()
        lines = tracker.update(0.0, (0.0, 0.0), {"ped_1": (1.0, 0.0), "dummy_2": (0.0, 1.5), "ped_2": (9.0, 9.0)})
        self.assertEqual(["encounter start who=ped_1 dist_min=1.000 sim=0.00",
                          "encounter start who=dummy_2 dist_min=1.500 sim=0.00"], lines)
        self.assertEqual([], tracker.update(1.0, None, {"ped_1": (5.0, 0.0)}))


if __name__ == "__main__":
    unittest.main()
