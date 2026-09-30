import math
import unittest

from sim.standalone.p3sim.outlet_chute import chute_geometry
from sim.standalone.p3sim.conveyor_end import receiver_status


class OutletChuteTest(unittest.TestCase):
    roller = {'min': [-.25, 1., .35], 'max': [.25, 2., .38]}
    table = {'min': [-.24, .5, 0.], 'max': [.24, .95, .32]}

    def geometry(self, receiver=None):
        return chute_geometry(self.roller, receiver or self.table, '-y', entry_overlap=.01,
                              landing_overlap=.15, width_margin=.01, thickness=.01)

    def test_chute_bridges_horizontal_gap_and_height_step(self):
        chute = self.geometry()
        self.assertAlmostEqual(chute['start'][1], 1.01)
        self.assertAlmostEqual(chute['end'][1], .80)
        self.assertAlmostEqual(chute['drop'], .06)
        self.assertGreater(chute['slope_degrees'], 0)
        self.assertEqual(len(chute['points']), 8)
        self.assertLess(chute['width'], .48)

    def test_disconnected_and_uphill_receivers_are_rejected(self):
        for table in ({'min': [1., .5, 0], 'max': [1.5, .95, .32]},
                      {'min': [-.24, .5, 0], 'max': [.24, .95, .40]}):
            with self.assertRaises(ValueError):
                self.geometry(table)

    def test_entry_recess_removes_upward_lip_without_changing_receiver_height(self):
        chute = chute_geometry(self.roller, self.table, '-y', entry_overlap=.01,
                               landing_overlap=.15, width_margin=.01, thickness=.01, entry_recess=.002)
        self.assertAlmostEqual(chute['start'][2], .378)
        self.assertAlmostEqual(chute['end'][2], .32)

    def test_excessive_recess_is_rejected(self):
        with self.assertRaises(ValueError):
            chute_geometry(self.roller, self.table, '-y', entry_overlap=.01, landing_overlap=.15,
                           width_margin=.01, thickness=.01, entry_recess=.02)

    def test_receiver_is_required_not_just_flat_roller_end(self):
        state = receiver_status((0., 1.055, .385), (1, 0, 0, 0), (.1, .07, .01), self.table, .004)
        self.assertFalse(state['reached'])

    def test_pouch_flat_and_fully_on_receiver_is_ready_to_settle(self):
        state = receiver_status((0., .75, .325), (1, 0, 0, 0), (.1, .07, .01), self.table, .004)
        self.assertTrue(state['reached'])

    def test_tilted_pouch_on_chute_is_not_receiver_arrival(self):
        orientation = (math.cos(.15), math.sin(.15), 0, 0)
        state = receiver_status((0., .85, .34), orientation, (.1, .07, .01), self.table, .004)
        self.assertFalse(state['reached'])
