"""Intake guards and exactly-once completion without Isaac/ROS."""
import math
import unittest
from sim.standalone.p3sim.inlet_capture import Intake, Port


class CaptureTest(unittest.TestCase):
    def setUp(self):
        self.port = Port('module', (0, 0, 0), (0, 1, 0), (.008, .03, .008))
        self.intake = Intake(self.port)

    def offer(self, now, **kwargs):
        args = {'item_id': 'a', 'kind': 'module', 'position': (0, 0, 0), 'held': False, 'angle': 0, 'speed': 0}
        args.update(kwargs)
        return self.intake.offer(now, **args)

    def test_released_item_centres_and_completes_once(self):
        self.assertEqual(self.offer(0, position=(.005, 0, 0)), 'settling')
        self.assertEqual(self.offer(.25, position=(.005, 0, 0)), 'capture_started')
        mid = self.intake.advance(.75)
        self.assertAlmostEqual(mid['position'][0], .0025)
        self.assertAlmostEqual(mid['position'][1], .1)
        self.assertFalse(mid['complete'])
        self.assertTrue(self.intake.advance(1.25)['complete'])
        self.assertEqual(self.intake.accepted, {'a'})
        self.assertEqual(self.offer(2), 'already_stored')
        self.assertIsNone(self.intake.advance(3))

    def test_interlocks_restart_dwell(self):
        cases = [({'held': True}, 'held'), ({'kind': 'pill'}, 'wrong_kind'),
                 ({'position': (.1, 0, 0)}, 'outside'), ({'angle': math.pi/2}, 'misaligned'),
                 ({'speed': .2}, 'moving'), ({'position': (math.nan, 0, 0)}, 'invalid_sample')]
        for extra, reason in cases:
            with self.subTest(reason=reason):
                self.intake.reset()
                self.assertEqual(self.offer(0), 'settling')
                self.assertEqual(self.offer(.2, **extra), reason)
                self.assertEqual(self.offer(.3), 'settling')
                self.assertIsNone(self.intake.advance(.4))

    def test_busy_rejects_second_item_and_reset_aborts_motion(self):
        self.offer(0)
        self.offer(.25)
        self.assertEqual(self.offer(.3, item_id='b'), 'busy')
        self.intake.reset()
        self.assertIsNone(self.intake.advance(0))
        self.assertFalse(self.intake.accepted)

    def test_time_reversal_requires_reset(self):
        self.offer(1)
        with self.assertRaises(ValueError):
            self.offer(.5)

    def test_round_intake_moves_down(self):
        x = Intake(Port('pill', (0, 0, 1), (0, 0, -1), (.02, .02, .03), dwell=0))
        self.assertEqual(x.offer(0, 'p', 'pill', (0, 0, 1), held=False, angle=0, speed=0), 'capture_started')
        self.assertAlmostEqual(x.advance(1)['position'][2], .8)

    def test_invalid_port_rejected(self):
        with self.assertRaises(ValueError):
            Port('pill', (0, 0, 0), (0, 0, 0), (1, 1, 1))
