"""Feedback-loss/cancel tests drive the executor through real command boundaries."""

import math
from dataclasses import replace
from types import SimpleNamespace

import pytest

from rokey_p3_manipulation import module_execution as E
from rokey_p3_manipulation import module_path as M
from rokey_p3_manipulation import scene_v2 as V


class Plant:
    def __init__(self):
        self.now = 0.
        self.feedback = E.Feedback(wall=lambda: self.now)
        self.arm, self.rail, self.holding = (0.,) * 6, (0.,) * 3, False
        self._home, self._rail_teach = self.arm, SimpleNamespace(home_rail=self.rail)
        self._scene = V.Scene((), {}, (), {}, ('rail_x', 'rail_y', 'rail_z'), (), (0., 0., 0.))
        self._open_loop = False
        self.commands, self.phases = [], []
        self.answer_close = self.answer_open = True
        self.inject = lambda: None
        for _ in range(8):
            self.tick()

    def tick(self):
        self.now += .05
        self.inject()
        self.feedback.observe('arm', self.arm, self.now)
        self.feedback.observe('rail', self.rail, self.now)
        self.feedback.grip(self.holding)

    def _poll(self, cancelled):
        if cancelled():
            return False
        self.tick()
        return True

    def _stream(self, points, send, positions, topic, cancelled):
        for point in points:
            if cancelled() or not send(point):
                return False
            self.tick()
        return True

    def _publish_feedback(self, goal, phase):
        self.phases.append(phase)

    def send_joint_command(self, point):
        self.arm = tuple(point)
        self.commands.append(('arm', self.arm))
        return True

    def send_rail_command(self, point):
        self.rail = tuple(point)
        self.commands.append(('rail', self.rail))
        return True

    def set_gripper(self, close):
        self.commands.append(('grip', close))
        if self.answer_close if close else self.answer_open:
            self.holding = close

    def joint_positions(self):
        return self.arm

    def rail_positions(self):
        return self.rail

    def sim_now(self):
        return self.now

    def plan(self):
        home, rail = (0.,) * 6, (0.,) * 3
        pick, insert, transfer = (.1,) * 6, (.15,) * 6, (.01, 0., 0.)
        return M.Plan((M.Segment('pick', 'arm', (home, pick), False, .02),
                       M.Segment('grasp', 'close', (), False, 0.),
                       M.Segment('transfer', 'rail', (rail, transfer), True, .02),
                       M.Segment('insert', 'arm', (pick, insert), True, .02),
                       M.Segment('release', 'open', (), True, 0.),
                       M.Segment('tuck', 'arm', (insert, home), False, .02),
                       M.Segment('home', 'rail', (transfer, rail), False, .02)),
                      .1, .01, 1, 1, M.signature(self._scene), 'test')


def test_in_position_while_moving_is_not_a_settled_rail():
    plant = Plant()
    plant.rail = (.0009, 0., 0.)
    plant.tick()
    assert not plant.feedback.settled('rail', plant.rail)
    for _ in range(6):
        plant.tick()
    assert plant.feedback.settled('rail', plant.rail)


def test_duplicate_stamps_cannot_manufacture_settle_or_freshness():
    plant = Plant()
    for _ in range(15):
        plant.now += .05
        plant.feedback.observe('rail', plant.rail, .4)
    assert plant.feedback.latest('rail') is None
    assert not plant.feedback.settled('rail', plant.rail)


@pytest.mark.parametrize('failure', ['nan', 'regression', 'stale', 'holding', 'unsynchronized'])
def test_missing_or_invalid_observations_fail_closed(failure):
    plant = Plant()
    if failure == 'nan':
        plant.feedback.observe('rail', (math.nan, 0., 0.), .5)
    elif failure == 'regression':
        plant.feedback.observe('rail', plant.rail, .1)
    elif failure == 'stale':
        plant.now += .6
    elif failure == 'holding':
        plant.feedback.grip(None)
    else:
        plant.feedback.observe('arm', plant.arm, 2.)
    assert plant.feedback.reason(False)


def test_success_requires_new_grasp_and_release_observations():
    plant = Plant()
    assert E.execute(plant.plan(), plant, plant.feedback, lambda: False, None) is None
    assert [v for kind, v in plant.commands if kind == 'grip'] == [True, False]
    assert plant.arm == plant._home and plant.rail == plant._rail_teach.home_rail


def test_initial_observations_can_arrive_after_executor_start():
    plant = Plant()
    plant.feedback.reset()
    assert E.execute(plant.plan(), plant, plant.feedback, lambda: False, None) is None
    assert [v for kind, v in plant.commands if kind == 'grip'] == [True, False]


def test_initial_observation_wait_is_bounded_and_does_not_open_or_move():
    plant = Plant()
    plant.feedback.reset()
    plant.tick = lambda: setattr(plant, 'now', plant.now + .05)
    started = plant.now
    error = E.execute(plant.plan(), plant, plant.feedback, lambda: False, None)
    assert 'timeout' in error
    assert 5. <= plant.now - started <= 5.1
    assert not plant.commands


def test_initial_wait_can_be_cancelled_without_inventing_empty_gripper_state():
    plant = Plant()
    plant.feedback.reset()
    plant.tick = lambda: setattr(plant, 'now', plant.now + .05)
    error = E.execute(plant.plan(), plant, plant.feedback, lambda: plant.now >= .6, None)
    assert 'cancel' in error
    assert plant.now < .7 and plant.feedback.held() is None and not plant.commands


def test_initial_deadline_is_checked_inside_a_poll_when_the_clock_stalls():
    plant = Plant()
    plant.feedback.reset()
    started, calls = plant.now, []

    def poll(cancelled):
        calls.append(True)
        if len(calls) == 1:
            plant.now += 3.9  # one late clock tick, but no state/holding messages
            return True
        until = plant.now + 4.  # the node's clock-stall polling bound
        while plant.now < until:
            if cancelled():
                return False
            plant.now += .01
        return False

    plant._poll = poll
    error = E.execute(plant.plan(), plant, plant.feedback, lambda: False, None)
    assert 'feedback confirmation timeout' in error
    assert plant.now - started <= 5.02 and not plant.commands


def test_stream_end_without_feedback_fails_explicitly_without_infinite_stamp():
    plant = Plant()
    stream = plant._stream

    def lose_final_observation(points, send, positions, topic, cancelled):
        result = stream(points, send, positions, topic, cancelled)
        plant.feedback.samples[topic].clear()
        return result

    plant._stream = lose_final_observation
    error = E.execute(plant.plan(), plant, plant.feedback, lambda: False, None)
    assert 'arm feedback missing at segment completion' in error
    assert 'grasp' not in plant.phases and plant.now < 1.


def test_hold_reports_missing_feedback_and_rejected_commands_without_replaying_stale_positions():
    plant = Plant()
    plant.now += .6
    plant.feedback.observe('rail', plant.rail, plant.now)
    plant.send_rail_command = lambda point: False
    error = E.hold(plant, plant.feedback, 'lost feedback')
    assert 'arm hold not sent: missing/stale feedback' in error
    assert 'rail hold request rejected' in error
    assert not plant.commands


def test_tiny_stamp_interval_uses_a_longer_velocity_baseline_and_checks_displacement():
    plant = Plant()
    plant.feedback.observe('arm', (1e-6,) * 6, plant.now + 1e-8)
    assert plant.feedback.settled('arm', (0.,) * 6)
    plant.feedback.observe('arm', (.003,) * 6, plant.now + 2e-8)
    assert not plant.feedback.settled('arm', (0.,) * 6)


@pytest.mark.parametrize('actor,dimension,speed', [('arm', 6, .1), ('rail', 3, .02)])
def test_reported_velocity_prevents_aliasing_as_a_stationary_axis(actor, dimension, speed):
    plant = Plant()
    plant.feedback.observe(actor, (0.,) * dimension, plant.now + .05, velocities=(speed,) * dimension)
    assert not plant.feedback.settled(actor, (0.,) * dimension)


def test_nonfinite_reported_velocity_invalidates_feedback():
    plant = Plant()
    plant.feedback.observe('arm', plant.arm, plant.now + .05, velocities=(math.nan,) * 6)
    assert plant.feedback.latest('arm') is None


def test_initial_wait_preserves_existing_fault_and_reset_cancellation():
    plant = Plant()
    plant.feedback.reset()
    plant.feedback.fault = 'existing clock regression'
    assert 'existing clock regression' in E.execute(plant.plan(), plant, plant.feedback, lambda: False, None)
    assert not plant.commands
    plant.feedback.reset()
    assert 'superseded' in E.execute(plant.plan(), plant, plant.feedback, lambda: False, None,
                                    superseded=lambda: True)
    assert not plant.commands and not plant.feedback.fault


@pytest.mark.parametrize('actor,residual', [('arm', .0015), ('rail', .0005)])
def test_small_static_residual_is_allowed_without_changing_the_planned_target(actor, residual):
    plant = Plant()
    dimension = 6 if actor == 'arm' else 3
    setattr(plant, actor, (residual,) * dimension)
    for _ in range(8):
        plant.tick()
    assert plant.feedback.settled(actor, (0.,) * dimension)


def test_continuous_holding_observations_remain_fresh_through_a_long_transfer():
    plant = Plant()
    plant.holding = True
    for _ in range(40):
        plant.tick()
        assert plant.feedback.held() is True
    plant.now += .6
    assert plant.feedback.held() is None


@pytest.mark.parametrize('failure', ['no_grasp', 'no_release', 'lost_payload', 'rail_drift', 'cancel', 'scene'])
def test_faults_stop_the_pipeline_without_opening_or_homing(failure):
    plant = Plant()
    def cancelled():
        return failure == 'cancel' and bool(plant.holding)
    if failure == 'no_grasp':
        plant.answer_close = False
    elif failure == 'no_release':
        plant.answer_open = False
    elif failure != 'cancel':
        def inject():
            if not plant.holding:
                return
            if failure == 'lost_payload':
                plant.holding = None
            elif failure == 'rail_drift':
                plant.rail = (.1, 0., 0.)
            else:
                plant._scene = plant._scene._replace(base_origin=(1., 0., 0.))
        plant.inject = inject
    error = E.execute(plant.plan(), plant, plant.feedback, cancelled, None)
    assert error and plant.feedback.fault == error
    assert 'tuck' not in plant.phases and 'home' not in plant.phases
    if failure != 'no_release':
        assert ('grip', False) not in plant.commands
    if failure == 'no_grasp':
        assert 'transfer' not in plant.phases


def test_open_loop_is_rejected():
    plant = Plant()
    plant._open_loop = True
    assert 'open_loop' in E.execute(plant.plan(), plant, plant.feedback, lambda: False, None)
    assert not any(kind == 'grip' for kind, _ in plant.commands)


def test_empty_plan_cannot_succeed_without_executing_a_refill():
    plant = Plant()
    assert E.execute(replace(plant.plan(), segments=()), plant, plant.feedback, lambda: False, None)
    assert not any(kind == 'grip' for kind, _ in plant.commands)


def test_reset_between_hold_guard_and_latch_cannot_restore_an_old_fault():
    plant = Plant()
    revision = plant.feedback.revision

    def reset_after_guard_read():
        plant.feedback.reset()
        return False  # the generation snapshot was read just before the reset

    assert E.hold(plant, plant.feedback, 'old fault', reset_after_guard_read, revision)
    assert not plant.feedback.fault and not plant.commands
