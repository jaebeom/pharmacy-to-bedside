"""Random schedule replay and physical grasp acceptance guards."""
import unittest
from sim.standalone.p3sim.shelf_pick_trial import lift_pass, select_shelves


class ShelfPickTest(unittest.TestCase):
    def test_seed_replays_three_distinct_eligible_shelves(self):
        self.assertEqual(select_shelves(835258728), [74, 75, 69])
        for seed in range(100):
            shelves = select_shelves(seed)
            self.assertEqual(len(set(shelves)), 3)
            self.assertTrue(set(shelves) <= set(range(67, 76)))

    def samples(self):
        return [{'position': [1., 2., 1.], 'tcp_distance': .02,
                 'left_contact': True, 'right_contact': True} for _ in range(60)]

    def test_lift_must_be_sustained_with_two_contacts(self):
        samples = self.samples()
        self.assertTrue(lift_pass(samples, .94))
        self.assertFalse(lift_pass(samples[:59], .94))
        for field, value in [('position', [1., 2., .96]), ('tcp_distance', .12),
                             ('left_contact', False), ('right_contact', False)]:
            with self.subTest(field=field):
                bad = self.samples()
                bad[30][field] = value
                self.assertFalse(lift_pass(bad, .94))

    def test_nonfinite_observation_never_passes(self):
        for field, value in [('position', [1., 2., float('nan')]), ('tcp_distance', float('nan'))]:
            samples = self.samples()
            samples[1][field] = value
            self.assertFalse(lift_pass(samples, .94))
