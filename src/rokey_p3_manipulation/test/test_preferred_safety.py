"""Regression cases for PR #391: solution filtering, transit and failure handling."""

import math
from pathlib import Path
from types import SimpleNamespace

import pytest
import test_m0609_rail as rail_test
import test_rail_select as select_test
import test_reset_fence as rf

from rokey_p3_manipulation import clearance as C
from rokey_p3_manipulation import pick_plan as P
from rokey_p3_manipulation import refill_sequence as S
from rokey_p3_manipulation import scene_v2 as V

nodes = rf.nodes


def test_elbow_gate_filters_solutions_before_clearance_ranking(monkeypatch):
    monkeypatch.setattr(P, 'solve_chain', lambda model, targets, seed: [(0., 0., seed[0], 0., 1., 0.)])

    def clearance(samples, *args):
        elbow = min(sample[1][2] for sample in samples)
        return C.Hit('test', 'link_2', .10 if elbow < .5 else .02, 'obstacle', (0., 0., 0.))

    monkeypatch.setattr(C, 'worst_clearance', clearance)
    scene = select_test.scene()
    tcp, boxes = select_test.collision()
    result = V.plan_leg(None, [('pick', (0., 0., 0.))], (0., 0., 0.), scene, boxes, tcp,
                        [(.1,), (math.pi / 2,)], V.PREFERRED_PARAMS, False, select_test.HOME,
                        min_elbow_sin=.5)
    assert result.candidate is not None
    assert result.candidate.seed_index == 1
    assert result.candidate.clearance == .02


def test_first_feasible_ignores_even_an_impossible_extra_elbow_gate(monkeypatch):
    monkeypatch.setattr(V, 'quick_ik', lambda *args: True)

    def leg(model, points, *args, **kwargs):
        # Intentionally impossible bound in params must not affect legacy mode.
        assert kwargs.get('min_elbow_sin', 0.) == 0.
        return P.Selection(P.Candidate(0, [select_test.HOME] * len(points), .02, 'test'), [], '')

    monkeypatch.setattr(V, 'plan_leg', leg)
    params = V.PREFERRED_PARAMS._replace(min_elbow_sin=1.01)
    steps, _, _ = select_test.plan(params, V.FIRST_FEASIBLE, select_test.a_cell())
    assert steps is not None


def test_observed_failure_transfer_is_rejected_and_raised_route_is_checked():
    scene = select_test.scene()
    tcp, boxes = select_test.collision()
    start, end = (.45, -.03, .59), (1.30, .03, .59)
    value, why = V.rail_clearance(start, end, scene, boxes, tcp, V.PREFERRED_PARAMS, select_test.HOME, True)
    assert value < V.PREFERRED_PARAMS.min_clearance, why
    steps, value, why = V.checked_rail_moves('transfer', start, end, scene, boxes, tcp,
                                            V.PREFERRED_PARAMS, select_test.HOME, True)
    assert steps and value >= V.PREFERRED_PARAMS.min_clearance, why
    assert max(step.rail[2] for step in steps) > start[2]
    assert steps[-1].rail == end


def test_transit_checks_payload_against_the_destination_and_moving_rail_parts(monkeypatch):
    scene = select_test.scene()
    tcp, boxes = select_test.collision()
    seen = []

    def clearance(samples, geometry, tcp_offset, obstacles, *args):
        if any(box.link == 'canister' for box in geometry):
            seen.append((samples[0][2], tuple(obstacles)))
            return C.Hit('transfer', 'canister', 0., 'ModuleSlotWall', (0., 0., 0.))
        return C.Hit('transfer', 'link_1', .1, 'wall', (0., 0., 0.))

    monkeypatch.setattr(C, 'worst_clearance', clearance)
    start = (.4, .0, .6)
    value, _ = V.rail_clearance(start, (.5, .0, .6), scene, boxes, tcp,
                               V.PREFERRED_PARAMS, select_test.HOME, True)
    assert value < V.PREFERRED_PARAMS.min_clearance
    assert seen == [(start, V.obstacles_at(scene, start))]


def test_place_cache_does_not_reuse_a_different_transfer_origin(monkeypatch):
    scene, cell = select_test.scene(), select_test.a_cell()
    tcp, boxes = select_test.collision()
    _, grip = V.pick_points(cell, V.PREFERRED_PARAMS)
    cache = {}
    monkeypatch.setattr(V, 'quick_ik', lambda *args: True)
    monkeypatch.setattr(V, 'plan_leg', lambda model, points, *args, **kwargs:
                        P.Selection(P.Candidate(0, [select_test.HOME] * len(points), .02, 'test'), [], ''))

    def transit(name, start, end, *args, **kwargs):
        return ([], .0, 'blocked') if start == (9., 0., 0.) else ([], .02, 'clear')

    monkeypatch.setattr(V, 'checked_rail_moves', transit)

    def place(start):
        return V._place_leg(None, scene, cell, scene.targets[cell.kind], grip, boxes, tcp,
                            [select_test.HOME], V.PREFERRED_PARAMS, select_test.HOME, (0., 0., 0.),
                            start, cache, V.PREFERRED_FIRST)

    assert place((0., 0., 0.))[0] is not None
    assert place((9., 0., 0.))[0] is None
    assert len([key for key in cache if key[0] != 'place_solution']) == 2


@pytest.mark.parametrize('fault', ['drift', 'stale'])
@pytest.mark.parametrize('phase', ['stream', 'arrival'])
def test_preferred_transfer_checks_arm_during_stream_and_arrival(nodes, monkeypatch, fault, phase):
    node, teach = rail_test.rail_node(nodes, monkeypatch)
    try:
        node._v2_rail_select = V.PREFERRED_FIRST
        node.set_goal_active(True)
        node.set_gripper(True)
        observed = [teach.home_joints]
        node.joint_positions = lambda: observed[0]
        failed = None if fault == 'stale' else (1.,) * 6
        original_stream = node._stream

        if phase == 'stream':
            send = node.send_rail_command

            def disturb(point):
                sent = send(point)
                observed[0] = failed
                return sent

            node.send_rail_command = disturb
        else:
            def disturb_after_stream(*args):
                sent = original_stream(*args)
                observed[0] = failed
                return sent

            node._stream = disturb_after_stream
        assert not node.move_rail_to((.5, .0), (teach.home_joints,))
        assert 'folded arm' in node._v2_rail_fault
        assert node._gripper_closed
        assert all(message.data for message in node.gripper.sent)
        assert node.at_home() is False
        assert node._accept_refill(rail_test.handle_for(node).request) == nodes[1].GoalResponse.REJECT
        commands = len(node.rails.sent), len(node.joints.sent)
        assert not node._go_home(teach.home_joints, lambda: False)
        node.start_homing()
        assert not node._homing
        assert commands == (len(node.rails.sent), len(node.joints.sent))
    finally:
        node.set_goal_active(False)
        node.stop_threads()


def test_preferred_timeout_holds_payload_and_reset_clears_fault(nodes, monkeypatch):
    node, teach = rail_test.rail_node(nodes, monkeypatch, rail_mode='stuck')
    try:
        node._v2_rail_select = V.PREFERRED_FIRST
        node.set_goal_active(True)
        node.set_gripper(True)
        node._rail_timeout = .02
        generation = node.generation()
        assert not node.move_rail_to((.5, .0), (teach.home_joints,))
        assert node._v2_rail_fault == 'rail arrival timeout'
        assert node._gripper_closed
        assert tuple(node.rails.sent[-1].position) == teach.home_rail
        node.set_goal_active(False)
        node.on_reset_begin(2)
        node.on_reset(2)
        assert node._v2_rail_fault == ''
        commands = len(node.rails.sent), len(node.joints.sent)
        node._hold_preferred('old goal', generation)
        assert node._v2_rail_fault == ''
        assert commands == (len(node.rails.sent), len(node.joints.sent))
    finally:
        node.set_goal_active(False)
        node.stop_threads()


def test_preferred_failure_does_not_release_or_retrace_after_transfer(nodes, monkeypatch):
    node, teach = rail_test.rail_node(nodes, monkeypatch)
    try:
        node._v2_rail_select = V.PREFERRED_FIRST
        node._rail_teach = teach._replace(slots={'a': [S.Step('grasp', None, S.GRIP_CLOSE),
                                                     S.Step('transfer', None, None, (.5, .0))]})
        node.move_rail_to = lambda *args, **kwargs: False
        handle = rail_test.handle_for(node)
        result = node._execute_refill(handle)
        assert not result.success and handle.state == 'aborted'
        assert node._v2_rail_fault
        assert node._gripper_closed and not node._homing
        assert [message.data for message in node.gripper.sent] == [False, True]
        assert not [event for event in node._event_pub.sent if event.name.endswith('REFILL_DONE')]
    finally:
        node.stop_threads()


@pytest.mark.parametrize('state', ['rail_away', 'holding', 'missing_rail', 'missing_holding'])
def test_preferred_home_and_start_require_unloaded_arm_and_rail(nodes, monkeypatch, state):
    node, teach = rail_test.rail_node(nodes, monkeypatch)
    try:
        node._v2_rail_select = V.PREFERRED_FIRST
        node.rail_positions = lambda: None if state == 'missing_rail' else (
            (.5, 0.) if state == 'rail_away' else teach.home_rail)
        node.gripper_holding = lambda: None if state == 'missing_holding' else state == 'holding'
        node.set_gripper(True)
        assert node.at_home() is not True
        result = node._execute_refill(rail_test.handle_for(node))
        assert not result.success
        assert node._gripper_closed
        assert [message.data for message in node.gripper.sent] == [True]
        assert node._v2_rail_fault
    finally:
        node.stop_threads()


def test_preferred_mode_refuses_open_loop_before_planning(nodes, monkeypatch):
    node, module = rf.m0609_harness(nodes, monkeypatch, start=select_test.HOME)
    try:
        config = Path(__file__).parents[1] / 'config'
        values = {'v2_rail_joint_names': ['rail_x', 'rail_y', 'rail_z'],
                  'v2_rail_max_speed': [.8] * 3, 'v2_rail_max_accel': [1.] * 3,
                  'rail_teach_file': str(config / 'm0609_rail_teach.yaml'),
                  'v2_collision_file': str(config / 'm0609_collision.yaml'),
                  'plan_cache_dir': '',      # 파일 계획 캐시 끔(이 시험은 메모리 캐시만 본다)
                  'v2_ik_seeds': 1, 'v2_rail_select': V.PREFERRED_FIRST}
        node.get_parameter = lambda key: SimpleNamespace(value=values[key])
        node._open_loop = True
        with pytest.raises(ValueError, match='closed-loop'):
            module.M0609ArmNode._setup_v2(node)
    finally:
        node.plant.stop()


def test_no_rail_route_is_returned_when_every_corridor_is_blocked(monkeypatch):
    scene = select_test.scene()
    tested = []

    def blocked(*args, steps, **kwargs):
        tested.append(steps)
        return 0., 'blocked'

    monkeypatch.setattr(V, 'rail_clearance', blocked)
    steps, value, _ = V.checked_rail_moves('transfer', (.45, -.03, .59), (1.3, .03, .4),
                                          scene, (), (), V.PREFERRED_PARAMS, select_test.HOME, True)
    assert not steps and value < V.PREFERRED_PARAMS.min_clearance
    assert len(tested) > 1
    assert max(step.rail[2] for route in tested for step in route) <= (
        scene.rail_limits[2][1] - V.PREFERRED_PARAMS.rail_limit_margin)


@pytest.mark.parametrize('actor, bad', [('arm', (float('nan'),) * 6),
                                      ('rail', (float('inf'), 0.)), ('rail', (0.,))])
def test_hold_never_republishes_invalid_observations(nodes, monkeypatch, actor, bad):
    node, teach = rail_test.rail_node(nodes, monkeypatch)
    try:
        node._v2_rail_select = V.PREFERRED_FIRST
        node.set_goal_active(True)
        states = node._joints if actor == 'arm' else node._rail_states
        states.get = lambda: bad
        assert not node.move_rail_to((.5, 0.), (teach.home_joints,))
        assert node._v2_rail_fault
        assert (node.joints.sent if actor == 'arm' else node.rails.sent) == []
        assert all(math.isfinite(value) for pub in (node.joints, node.rails)
                   for message in pub.sent for value in message.position)
    finally:
        node.set_goal_active(False)
        node.stop_threads()
