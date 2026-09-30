"""Feedback gates for the guarded v2 module path. No ROS imports.

This is a simulator interlock, not a safety-rated stop. Bool holding has no
command ID: require a new observation, but do not claim controller acknowledgement.
"""

import math
import threading
import time
from collections import deque

from rokey_p3_manipulation import m0609_kinematics as K
from rokey_p3_manipulation import refill_sequence as S
from rokey_p3_manipulation.module_path import signature


class Feedback:
    def __init__(self, wall=time.monotonic):
        self.wall = wall
        self.lock = threading.RLock()
        self.fault = ''
        self.revision = 0
        self.reset()

    def reset(self):
        with self.lock:
            self.revision += 1
            self.samples = {'arm': deque(maxlen=64), 'rail': deque(maxlen=64)}
            self.holding = None
            self.holding_at = -math.inf
            self.holding_sequence = 0
            self.fault = ''

    def observe(self, actor, values, stamp, velocities=()):
        with self.lock:
            history = self.samples[actor]
            try:
                values = K.finite(values, 6 if actor == 'arm' else 3)
                stamp = K.finite((stamp,), 1)[0]
                velocities = K.finite(velocities, len(values)) if len(velocities) else ()
            except (K.PlanError, TypeError, ValueError):
                history.clear()
                return
            if history and stamp < history[-1][0]:
                history.clear()
                self.fault = 'feedback clock regressed; reset required'
                return
            if not history or stamp > history[-1][0]:
                history.append((stamp, self.wall(), values, velocities))

    def grip(self, value):
        with self.lock:
            self.holding = value if type(value) is bool else None
            self.holding_at = self.wall()
            self.holding_sequence += 1

    def latest(self, actor):
        with self.lock:
            history = self.samples[actor]
            if not history or not 0 <= self.wall() - history[-1][1] <= .5:
                return None
            return history[-1]

    def held(self):
        with self.lock:
            return self.holding if 0 <= self.wall() - self.holding_at <= .5 else None

    def settled(self, actor, target, after=-math.inf):
        """New increasing source stamps, position AND low measured velocity for 0.2 sim s."""
        with self.lock:
            latest = self.latest(actor)
            tolerance, max_speed = (.001, .002) if actor == 'rail' else (.0025, .01)
            if latest is None:
                return False
            history = list(self.samples[actor])
            start = len(history) - 1
            baseline = start
            if (not S.at_pose(latest[2], target, tolerance)
                    or any(abs(v) > max_speed for v in latest[3])):
                return False
            for previous in range(start - 1, -1, -1):
                gap = history[previous + 1][0] - history[previous][0]
                if not 0 < gap <= .1 + 1e-9:
                    break
                sample = history[previous]
                # Every sample still checks position and reported velocity. For
                # position differences, combine tiny source intervals instead of
                # dividing numerical noise by a near-zero dt.
                if (not S.at_pose(sample[2], target, tolerance)
                        or any(abs(v) > max_speed for v in sample[3])):
                    break
                dt = history[baseline][0] - sample[0]
                if dt < 1e-4:
                    continue
                speed = max(abs(v - u) / dt
                            for u, v in zip(sample[2], history[baseline][2], strict=True))
                if speed > max_speed:
                    break
                start = baseline = previous
            return latest[0] - max(history[start][0], after) >= .2

    def reason(self, holding, locked_actor=None, target=None, now=None):
        with self.lock:
            if self.fault:
                return self.fault
            a, r = self.latest('arm'), self.latest('rail')
            if a is None or r is None:
                return 'missing/stale arm or rail feedback'
            if abs(a[0] - r[0]) > .1:
                return 'arm and rail source stamps are not synchronized'
            if now is not None and any(not -.1 <= now - sample[0] <= .5 for sample in (a, r)):
                return 'feedback source stamp is stale or ahead of simulation clock'
            if self.held() is not holding:
                return 'missing/stale/unexpected holding feedback'
            if locked_actor and not self.settled(locked_actor, target):
                return f'{locked_actor} moved or has not settled'
            return ''


    def home_reason(self, arm, rail, now):
        """Confirm the actual unloaded home, using one locked feedback snapshot."""
        with self.lock:
            reason = self.reason(False, now=now)
            if reason:
                return reason
            for actor, target in (('arm', arm), ('rail', rail)):
                if not self.settled(actor, target):
                    return f'{actor} home has not settled'
            return ''


def hold(node, feedback, reason, superseded=lambda: False, revision=None):
    """Latch the failure and request holds independently from fresh measured states."""
    if superseded():
        return reason  # reset owns the controllers and cleared the old task's fault
    with feedback.lock:
        if revision is not None and revision != feedback.revision:
            return reason
        feedback.fault = reason
    for actor, send in (('arm', node.send_joint_command), ('rail', node.send_rail_command)):
        if superseded():
            return reason
        value = feedback.latest(actor)
        failure = ''
        if value is None:
            failure = f'{actor} hold not sent: missing/stale feedback; controller-local stop required'
        else:
            try:
                if send(value[2]) is False:
                    failure = f'{actor} hold request rejected'
            except Exception as error:
                failure = f'{actor} hold request failed: {type(error).__name__}'
        if failure:
            with feedback.lock:
                if revision is None or revision == feedback.revision:
                    feedback.fault += '; ' + failure
    return feedback.fault or reason


def execute(plan, node, feedback, cancelled, goal_handle, superseded=lambda: False):
    """Execute an immutable simulator plan; return None or a latched failure reason.

    Every stream tick checks live locked-axis state and payload feedback. Failures
    request a hold using fresh measured states and never open the gripper or home.
    """
    arm, rail = tuple(node._home), tuple(node._rail_teach.home_rail)
    with feedback.lock:
        revision = feedback.revision
    fault = ''
    grasp_confirmed = release_confirmed = False

    def stop(holding, actor=None, target=None, check_feedback=True):
        nonlocal fault
        if fault:
            return True
        if superseded():
            fault = 'module execution superseded by reset'
        elif cancelled():
            fault = 'cancel/reset/deadline'
        elif not getattr(node, '_module_inventory_valid', True):
            fault = 'invalid inventory during module execution'
        elif node._scene is None or signature(node._scene) != plan.scene_signature:
            fault = 'scene changed during execution'
        elif feedback.fault:
            fault = feedback.fault
        elif check_feedback:
            fault = feedback.reason(holding, actor, target, now=node.sim_now())
        return bool(fault)

    def wait_until(predicate, holding, actor=None, target=None, check_feedback=True):
        nonlocal fault
        until = feedback.wall() + 5.
        while not stop(holding, actor, target, check_feedback):
            if predicate():
                return True
            if feedback.wall() >= until:
                fault = 'feedback confirmation timeout'
                break
            if not node._poll(lambda: stop(holding, actor, target, check_feedback) or feedback.wall() >= until):
                fault = fault or ('feedback confirmation timeout' if feedback.wall() >= until else 'clock stopped')
                break
        return False

    try:
        if node._open_loop:
            fault = 'guarded module path forbids open_loop'
        elif not plan.segments:
            fault = 'empty module path'
        # Before any command, allow the first valid, unloaded home observations
        # to arrive. Once motion starts, stale/missing feedback still fails closed.
        elif not wait_until(lambda: not feedback.home_reason(arm, rail, node.sim_now()),
                            False, check_feedback=False):
            fault = fault or 'unloaded home not confirmed'
        for segment in plan.segments:
            if fault:
                break
            node._publish_feedback(goal_handle, segment.phase)
            if segment.actor in ('close', 'open'):
                # The insertion endpoint was confirmed before release. Both arm
                # and rail must still be stationary while changing the gripper.
                if stop(segment.carrying, 'rail', rail) or not feedback.settled('arm', arm):
                    fault = fault or 'arm not stationary at gripper operation'
                    break
                with feedback.lock:
                    sequence = feedback.holding_sequence
                node.set_gripper(segment.actor == 'close')
                expected = segment.actor == 'close'
                until = feedback.wall() + 5.
                while True:
                    # Expected state may legitimately change while awaiting the
                    # command; all other feedback gates remain in force.
                    with feedback.lock:
                        observed = feedback.held()
                        changed = feedback.holding_sequence > sequence and observed is expected
                    if observed is None or stop(observed, 'rail', rail) or not feedback.settled('arm', arm):
                        fault = fault or 'gripper confirmation lost stationary feedback'
                        break
                    if changed:
                        if expected:
                            grasp_confirmed = True
                        elif grasp_confirmed:
                            release_confirmed = True
                        break
                    if feedback.wall() >= until or not node._poll(lambda: cancelled()):
                        fault = 'gripper confirmation timeout/cancel'
                        break
                continue
            moving, locked, target = (segment.actor, 'rail', rail) if segment.actor == 'arm' else ('rail', 'arm', arm)
            if not S.at_pose(feedback.latest(moving)[2] if feedback.latest(moving) else None,
                             segment.points[0], .0025 if moving == 'arm' else .001):
                fault = f'{moving} start differs from checked path'
                break
            send = node.send_joint_command if moving == 'arm' else node.send_rail_command
            positions = node.joint_positions if moving == 'arm' else node.rail_positions

            def stopped(carrying=segment.carrying, actor=locked, goal=target):
                return stop(carrying, actor, goal)

            def checked_send(point, guard=stopped, send_point=send):
                return not guard() and send_point(point)

            if not node._stream(segment.points, checked_send, positions, moving,
                                stopped):
                fault = fault or 'stream stopped'
                break
            completion = feedback.latest(moving)
            if completion is None:
                fault = f'{moving} feedback missing at segment completion'
                break
            if not wait_until(lambda actor=moving, goal=segment.points[-1], stamp=completion[0]:
                              feedback.settled(actor, goal, after=stamp),
                              segment.carrying, locked, target):
                break
            if moving == 'arm':
                arm = segment.points[-1]
            else:
                rail = segment.points[-1]
        if not fault and not stop(False):
            fault = feedback.home_reason(node._home, node._rail_teach.home_rail, node.sim_now())
            if not fault and not (grasp_confirmed and release_confirmed):
                fault = 'module cycle missing confirmed grasp/release'
    except Exception as error:
        fault = f'module execution error: {type(error).__name__}: {error}'
    if fault:
        # This requests a position hold; a disconnected controller cannot be
        # proven stopped here. A hardware implementation needs a local watchdog.
        return hold(node, feedback, fault, superseded, revision)
    return None
