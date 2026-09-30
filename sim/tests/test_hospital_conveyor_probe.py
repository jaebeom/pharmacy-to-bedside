"""Belt diagnostic must not declare arrival merely because a pouch stopped."""
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from sim.standalone.p3sim.hospital_conveyor_probe import HospitalConveyorProbe


class Vector(list):
    def tolist(self):
        return list(self)


class ConveyorProbeTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.probe = HospitalConveyorProbe.__new__(HospitalConveyorProbe)
        self.probe.output = Path(self.directory.name)
        self.probe.log = io.StringIO()
        self.probe.world = Mock(current_time=1.)
        self.probe.pouch = Mock()
        self.probe.targets = []
        self.probe.velocities = [(Mock(), .5)]
        self.probe.finished = False
        self.probe.next_sample = 0.
        self.probe.stop_time = None
        self.probe.settled_since = None
        self.probe.end = (2., 3., .4)
        self.probe.surface = {'min': [1.5, 2.94, .37], 'max': [2.5, 4., .395]}
        self.probe.receiver_surface = None
        self.probe.direction = '-y'
        self.probe.edge_margin = .03
        self.probe.height_tolerance = .02
        self.probe.pouch_size = (.10, .07, .01)

    def step(self, time, position, velocity=(0., 0., 0.)):
        self.probe.world.current_time = time
        self.probe.pouch.get_world_pose.return_value = (Vector(position), (1, 0, 0, 0))
        self.probe.pouch.get_linear_velocity.return_value = Vector(velocity)
        self.probe.step()

    def result(self):
        return json.loads((self.probe.output/'conveyor-result.json').read_text())

    def test_stop_away_from_exit_is_not_arrival(self):
        self.step(2, (1., 1., .4))
        self.assertFalse(self.probe.finished)
        self.assertIsNone(self.probe.stop_time)

    def test_stopped_before_real_terminal_is_not_arrival(self):
        self.step(2, (2., 3.24, .4))
        self.assertFalse(self.probe.finished)
        self.assertIsNone(self.probe.stop_time)
        self.probe.velocities[0][0].Set.assert_not_called()

    def test_arrival_requires_settling_inside_exit(self):
        self.step(2, self.probe.end, (.1, 0., 0.))
        self.assertFalse(self.probe.finished)
        self.probe.velocities[0][0].Set.assert_called_with(0.)
        self.step(3.1, self.probe.end)
        self.assertFalse(self.probe.finished)
        self.step(4.2, self.probe.end)
        self.assertTrue(self.result()['success'])

    def test_drift_after_entering_exit_cannot_pass(self):
        self.step(2, self.probe.end)
        self.step(4, (2., 4., .4))
        self.assertFalse(self.probe.finished)

    def test_return_after_drift_requires_a_new_full_settling_interval(self):
        self.step(2, self.probe.end)
        self.step(2.5, (2., 4., .4))
        self.step(4, self.probe.end)
        self.assertFalse(self.probe.finished)
        self.step(4.9, self.probe.end)
        self.assertFalse(self.probe.finished)
        self.step(5.1, self.probe.end)
        self.assertTrue(self.result()['success'])

    def test_motion_on_receiver_restarts_settling_interval(self):
        self.probe.receiver_surface = {'min': [1.5, 2.2, 0], 'max': [2.5, 2.9, .32]}
        position = (2., 2.7, .325)
        self.step(2, position)
        self.step(2.5, position, (.04, 0., 0.))
        self.step(3.1, position)
        self.assertFalse(self.probe.finished)
        self.step(4.2, position)
        self.assertEqual(self.result()['reason'], 'receiver_settled')

    def test_timeout_records_failure_and_stops_drive(self):
        self.step(90.1, (1., 1., .4))
        self.assertFalse(self.result()['success'])
        self.assertEqual(self.result()['reason'], 'timeout')
        self.probe.velocities[0][0].Set.assert_called_with(0.)

    def test_fall_records_failure(self):
        self.step(2, (1., 1., -.1))
        self.assertEqual(self.result()['reason'], 'fell')
        self.assertFalse(self.result()['success'])

    def test_application_close_records_incomplete_trial(self):
        self.probe.abort()
        self.assertFalse(self.result()['success'])
        self.assertEqual(self.result()['reason'], 'application_closed_before_terminal_result')
        self.probe.velocities[0][0].Set.assert_called_with(0.)

    def test_abort_does_not_overwrite_completed_result(self):
        self.step(90.1, (1., 1., .4))
        self.probe.abort()
        self.assertEqual(self.result()['reason'], 'timeout')

    def test_chute_mode_does_not_stop_at_old_roller_endpoint(self):
        self.probe.receiver_surface = {'min': [1.5, 2.2, 0], 'max': [2.5, 2.9, .32]}
        self.step(2, self.probe.end)
        self.assertIsNone(self.probe.stop_time)
        self.probe.velocities[0][0].Set.assert_not_called()
        self.step(3, (2., 2.7, .325))
        self.step(4.1, (2., 2.7, .325))
        self.assertEqual(self.result()['reason'], 'receiver_settled')
