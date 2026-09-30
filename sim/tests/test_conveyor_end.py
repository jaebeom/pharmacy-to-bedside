import math
import unittest

from sim.standalone.p3sim.conveyor_end import item_bounds, terminal_status


class ConveyorEndTest(unittest.TestCase):
    surface = {'min': [-.3, 1., .35], 'max': [.3, 2., .38]}

    def status(self, position, orientation=(1, 0, 0, 0)):
        return terminal_status(position, orientation, (.10, .07, .01), self.surface, '-y', .03, .02)

    def test_early_stop_a_quarter_metre_from_edge_fails(self):
        state = self.status((0, 1.30, .385))
        self.assertFalse(state['reached'])
        self.assertAlmostEqual(state['edge_gap_m'], .265)

    def test_whole_item_supported_and_leading_edge_near_exit(self):
        self.assertTrue(self.status((0, 1.055, .385))['reached'])

    def test_overhanging_item_does_not_pass(self):
        self.assertFalse(self.status((0, 1.02, .385))['reached'])
        self.assertFalse(self.status((.28, 1.055, .385))['reached'])

    def test_hovering_or_fallen_item_does_not_pass(self):
        self.assertFalse(self.status((0, 1.055, .50))['reached'])
        self.assertFalse(self.status((0, 1.055, .10))['reached'])

    def test_rotation_changes_leading_edge(self):
        lo, hi = item_bounds((0, 0, 0), (math.sqrt(.5), 0, 0, math.sqrt(.5)), (.10, .07, .01))
        self.assertAlmostEqual(lo[1], -.05)
        self.assertAlmostEqual(hi[0], .035)

    def test_positive_x_terminal_uses_maximum_surface_edge(self):
        state = terminal_status((.23, 1.5, .385), (1, 0, 0, 0), (.10, .07, .01),
                                self.surface, '+x', .03, .02)
        self.assertTrue(state['reached'])

    def test_invalid_direction_and_tolerance_rejected(self):
        for direction, margin in (('diagonal', .03), ('-y', 0), ('-y', math.nan)):
            with self.assertRaises(ValueError):
                terminal_status((0, 1, .385), (1, 0, 0, 0), (.1, .07, .01),
                                self.surface, direction, margin, .02)
