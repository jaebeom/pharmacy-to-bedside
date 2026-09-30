"""Guarded module failures must not fall through the node's legacy homing path."""

import json
import threading
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
import test_module_execution as execution_test
import test_reset_fence as rf

from rokey_p3_manipulation import module_execution as E
from rokey_p3_manipulation import pick_plan as P
from rokey_p3_manipulation import scene_v2 as V
from rokey_p3_manipulation.module_execution import Feedback

nodes = rf.nodes


def test_holding_callback_refreshes_freshness_on_every_heartbeat(nodes, monkeypatch):
    node, module = rf.m0609_harness(nodes, monkeypatch, start=(0.,) * 6)
    node.plant.stop()
    clock = [0.]
    node._module_feedback = Feedback(wall=lambda: clock[0])
    for i in range(25):
        clock[0] = i * .1
        module.M0609ArmNode._on_holding(node, SimpleNamespace(data=True))
        assert node._module_feedback.held() is True
    clock[0] += .6
    assert node._module_feedback.held() is None


def test_joint_state_velocity_is_forwarded_in_joint_name_order(nodes, monkeypatch):
    node, module = rf.m0609_harness(nodes, monkeypatch, start=(0.,) * 6)
    node.plant.stop()
    node._module_feedback = Feedback()
    message = SimpleNamespace(name=node._joint_names[::-1], velocity=[.6, .5, .4, .3, .2, .1],
                              header=SimpleNamespace(stamp=SimpleNamespace(sec=1, nanosec=0)))
    module.M0609ArmNode._observe_module_state(node, 'arm', (0.,) * 6, message)
    assert node._module_feedback.latest('arm')[3] == (.1, .2, .3, .4, .5, .6)
    message.velocity.pop()
    module.M0609ArmNode._observe_module_state(node, 'arm', (0.,) * 6, message)
    assert node._module_feedback.latest('arm') is None


def test_module_fault_blocks_goal_home_and_at_home(nodes, monkeypatch):
    node, module = rf.m0609_harness(nodes, monkeypatch, start=(0.,) * 6)
    try:
        node._module_feedback = Feedback()
        node._module_feedback.fault = 'rail drift'
        count = len(node.joints.sent)
        assert node._accept_refill(SimpleNamespace(item_id='drug-ibu', slot=0)) == module.GoalResponse.REJECT
        assert node.at_home() is False
        assert node._go_home(node.joint_positions(), lambda: False) is False
        node.start_homing()
        assert len(node.joints.sent) == count and not node._homing
    finally:
        node.stop_homing()
        node.plant.stop()


def test_active_module_cannot_request_legacy_recovery(nodes, monkeypatch):
    node, _ = rf.m0609_harness(nodes, monkeypatch, start=(0.,) * 6)
    try:
        node._module_request = True
        node._module_feedback = Feedback()
        count = len(node.joints.sent)
        assert node._go_home(node.joint_positions(), lambda: False) is False
        assert len(node.joints.sent) == count
    finally:
        node.stop_homing()
        node.plant.stop()


@pytest.fixture
def guarded_node(nodes, monkeypatch):
    """Actual action -> v2 -> executor pipeline with a deterministic feedback plant.

    Only planning and controller I/O are substituted; terminal action state,
    REFILL_DONE publication, feedback gates and legacy-recovery decisions run.
    """
    node, module = rf.m0609_harness(nodes, monkeypatch, start=(0.,) * 6)
    node.plant.stop()
    plant = execution_test.Plant()
    scene = V.parse_inventory((Path(__file__).parent / 'data/pharmacy_v2.json').read_text())
    cell = next(c for c in scene.cells if c.cell_id == 'upper_right/r0c0')
    plant._scene = scene._replace(cells=(cell,))
    node._scene = plant._scene
    node._scene_v2 = True
    node._module_feedback = plant.feedback
    node._module_inventory_valid = True
    node._rail_teach = SimpleNamespace(home_rail=plant._rail_teach.home_rail, slots={})
    node._rail_joint_names = list(scene.rail_names)
    node._v2, node._v2_picker = V, P.CellPicker(1)
    node._v2_cache, node._v2_cache_lock = V.PlanCache(), threading.Lock()
    node._v2_cache.refresh(node._scene)
    node._v2_max_skips, node._v2_done = 0, None
    plant.checked_plan = replace(plant.plan(), cell_id=cell.cell_id)
    node._plan_cell = lambda *args: (V.PlanEntry(plant.checked_plan, 'test controller path', .01, 0.), True)
    for method in ('sim_now', '_stream', '_poll', 'send_joint_command', 'send_rail_command',
                   'set_gripper', 'joint_positions', 'rail_positions'):
        setattr(node, method, getattr(plant, method))
    recovery = []
    node._return_home = lambda *args: recovery.append('return')
    node.start_homing = lambda: recovery.append('background')
    yield node, module, plant, recovery
    node.stop_homing()


def handle_for(plant, item='drug-ibu'):
    handle = SimpleNamespace(request=SimpleNamespace(item_id=item, slot=0, lot_id='lot-from-goal'),
                             is_cancel_requested=False, state=None, at_result=None,
                             publish_feedback=lambda feedback: None)

    def finish(state):
        handle.state = state
        handle.at_result = (plant.arm, plant.rail, plant.holding)

    handle.succeed = lambda: finish('succeeded')
    handle.abort = lambda: finish('aborted')
    handle.canceled = lambda: finish('canceled')
    return handle


@pytest.mark.parametrize('failure', ['inventory', 'unknown_item', 'plan', 'deadline', 'invalid_inventory',
                                    'inventory_while_planning'])
def test_preflight_failure_does_not_latch_hold_or_start_legacy_recovery(guarded_node, failure):
    node, module, plant, recovery = guarded_node
    item = 'drug-ibu'
    if failure == 'inventory':
        node._scene, item = None, 'drug-amox'  # a cylinder request before the first inventory
    elif failure == 'unknown_item':
        item = 'unknown'
    elif failure == 'plan':
        node._plan_cell = lambda *args: (V.PlanEntry(None, 'no feasible route', None, 0.), False)
    elif failure == 'deadline':
        node._refill_timeout = .01
    elif failure == 'inventory_while_planning':
        original = node._plan_cell

        def plan_then_invalidate(*args):
            entry = original(*args)
            node._on_inventory(SimpleNamespace(data='invalid during planning'))
            return entry

        node._plan_cell = plan_then_invalidate
    else:
        node._on_inventory(SimpleNamespace(data='not valid inventory'))
    handle = handle_for(plant, item)
    result = node._execute_refill(handle)
    assert not result.success and handle.state == 'aborted'
    assert not node._module_feedback.fault
    assert not node._left_home and node.at_home() is True
    assert not plant.commands and not recovery and not node._event_pub.sent
    assert node._accept_refill(SimpleNamespace(item_id='drug-amox', slot=0)) == module.GoalResponse.ACCEPT


def test_guarded_success_publishes_one_refill_done_after_both_axes_settle_home(guarded_node):
    node, _, plant, recovery = guarded_node
    handle = handle_for(plant)
    result = node._execute_refill(handle)
    assert result.success and result.lot_id == 'lot-from-goal' and handle.state == 'succeeded'
    assert handle.at_result == (plant._home, plant._rail_teach.home_rail, False)
    assert not node._left_home and not node._module_feedback.fault and node.at_home() is True
    assert not recovery
    [event] = node._event_pub.sent
    assert event.name.endswith('REFILL_DONE')
    assert json.loads(event.detail) == {'item': 'drug-ibu', 'slot': 'a', 'kind': 'module',
                                       'cell': 'upper_right/r0c0', 'target': 'module',
                                       'seed': 1, 'draw': 1, 'clearance': .01, 'lot': 'lot-from-goal'}


@pytest.mark.parametrize('axis', ['arm', 'rail'])
def test_missing_return_leg_cannot_publish_success(guarded_node, axis):
    node, _, plant, recovery = guarded_node
    phase = 'tuck' if axis == 'arm' else 'home'
    plant.checked_plan = replace(plant.checked_plan,
                                  segments=tuple(s for s in plant.checked_plan.segments if s.phase != phase))
    result = node._execute_refill(handle_for(plant))
    assert not result.success and node._module_feedback.fault and node._left_home
    assert not node._event_pub.sent and not recovery


def test_home_observation_is_rechecked_before_node_marks_success(guarded_node, monkeypatch):
    node, _, plant, recovery = guarded_node
    execute = E.execute

    def drift_after_execution(*args):
        assert execute(*args) is None
        plant.rail = (.1, 0., 0.)
        plant.tick()

    monkeypatch.setattr(E, 'execute', drift_after_execution)
    result = node._execute_refill(handle_for(plant))
    assert not result.success and node._module_feedback.fault and node._left_home
    assert not node._event_pub.sent and not recovery


@pytest.mark.parametrize('failure', ['no_grasp', 'no_release', 'cancel', 'invalid_inventory'])
def test_execution_failure_latches_hold_without_refill_done_or_legacy_home(guarded_node, failure):
    node, module, plant, recovery = guarded_node
    handle = handle_for(plant)
    if failure == 'no_grasp':
        plant.answer_close = False
    elif failure == 'no_release':
        plant.answer_open = False
    else:
        def inject():
            if plant.holding:
                if failure == 'cancel':
                    handle.is_cancel_requested = True
                else:
                    node._on_inventory(SimpleNamespace(data='invalid during execution'))
        plant.inject = inject
    result = node._execute_refill(handle)
    assert not result.success and node._module_feedback.fault and node._left_home
    assert handle.state == ('canceled' if failure == 'cancel' else 'aborted')
    assert not recovery and not node._event_pub.sent
    assert node._accept_refill(SimpleNamespace(item_id='drug-amox', slot=0)) == module.GoalResponse.REJECT


def test_preflight_refusal_preserves_an_existing_away_pose_and_payload(guarded_node):
    node, _, plant, recovery = guarded_node
    node._left_home, node._scene = True, None
    plant.arm, plant.holding = (.1,) * 6, True
    plant.tick()
    assert not node._execute_refill(handle_for(plant)).success
    assert node._left_home and not node.at_home() and plant.holding
    assert not node._module_feedback.fault and not plant.commands and not recovery


@pytest.mark.parametrize('command_rate', [.5, 50.])
def test_guarded_retiming_uses_the_actual_stream_period(nodes, monkeypatch, command_rate):
    node, module = rf.m0609_harness(nodes, monkeypatch, start=(0.,) * 6)
    node.plant.stop()
    config = Path(__file__).parents[1] / 'config'
    params = {'v2_rail_joint_names': ['rail_x', 'rail_y', 'rail_z'],
              'v2_rail_max_speed': [.8] * 3, 'v2_rail_max_accel': [1.] * 3,
              'rail_teach_file': str(config / 'm0609_rail_teach.yaml'),
              'v2_collision_file': str(config / 'm0609_collision.yaml'),
              'plan_cache_dir': '',      # 파일 계획 캐시 끔(이 시험은 메모리 캐시만 본다)
              'v2_ik_seeds': 1, 'v2_min_clearance': .01, 'v2_guarded_module_path': True,
              'use_sim_time': True, 'v2_seed': 1, 'v2_max_skips': 0,
              # 기본값이다. guarded 경로는 레일 고르기 방식과 무관하지만 `_setup_v2` 가 읽는다.
              'v2_rail_select': V.FIRST_FEASIBLE}
    node.get_parameter = lambda key: SimpleNamespace(value=params[key])
    node._rail_command_rate = command_rate
    node._joint_speed_limits, node._joint_accel_limits = (2.,) * 6, (4.,) * 6
    node._limits = module.seq.M0609_JOINT_LIMITS
    module.M0609ArmNode._setup_v2(node)
    assert node._module_limits.period == node._period()


@pytest.mark.parametrize('state', ['rail_away', 'holding', 'missing_rail'])
def test_guarded_home_status_requires_unloaded_arm_and_rail(guarded_node, state):
    node, _, plant, _ = guarded_node
    assert node.at_home() is True
    if state == 'rail_away':
        plant.rail = (.1, 0., 0.)
        plant.tick()
    elif state == 'holding':
        plant.holding = True
        plant.tick()
    else:
        plant.feedback.samples['rail'].clear()
    assert node.at_home() is not True
    plant.rail, plant.holding = plant._rail_teach.home_rail, False
    for _ in range(8):
        plant.tick()
    assert node.at_home() is True


@pytest.mark.parametrize('interruption', ['cancel', 'reset'])
def test_interruption_during_planning_sends_no_hold_and_does_not_latch(guarded_node, interruption):
    node, _, plant, recovery = guarded_node
    handle = handle_for(plant)
    original = node._plan_cell

    def interrupted_plan(*args):
        entry = original(*args)
        if interruption == 'cancel':
            handle.is_cancel_requested = True
        else:
            node._wait_goal_idle = lambda: None  # a slow planner can outlive RESET_DONE's bounded wait
            node.on_reset_begin(1)
            node.on_reset(1)
            for _ in range(8):
                plant.tick()
        return entry

    node._plan_cell = interrupted_plan
    assert not node._execute_refill(handle).success
    assert handle.state == ('canceled' if interruption == 'cancel' else 'aborted')
    assert not plant.commands and not plant.feedback.fault and not recovery and not node._event_pub.sent
    assert not node._left_home


def test_old_module_execution_cannot_hold_or_relatch_after_reset_done(guarded_node):
    node, _, plant, recovery = guarded_node
    after_reset = []

    def reset_during_transfer():
        if not plant.holding or after_reset:
            return
        node._wait_goal_idle = lambda: None  # exercise completion after the bounded drain wait
        node.on_reset_begin(1)
        node.on_reset(1)
        plant.arm, plant.rail, plant.holding = plant._home, plant._rail_teach.home_rail, False
        after_reset.append(len(plant.commands))

    plant.inject = reset_during_transfer
    assert not node._execute_refill(handle_for(plant)).success
    assert after_reset and len(plant.commands) == after_reset[0]
    assert not plant.feedback.fault and not recovery and not node._event_pub.sent


@pytest.mark.parametrize('clock_step', [1 / 30., .2])
def test_guarded_stream_never_skips_checked_points_or_catches_up_in_a_burst(guarded_node, monkeypatch,
                                                                         clock_step):
    node, module, _, _ = guarded_node
    clock, sent = [0.], []
    node._module_request = True
    node.sim_now = lambda: clock[0]
    monkeypatch.setattr(module.time, 'sleep', lambda _: clock.__setitem__(0, clock[0] + clock_step))
    points = tuple((.001 * i,) * 6 for i in range(10))

    def send(point):
        sent.append((clock[0], point))
        return True

    assert module.M0609ArmNode._stream(node, points, send, lambda: points[0], 'arm', lambda: False)
    assert [p for _, p in sent] == list(points)
    assert all(b[0] - a[0] >= node._period() - 1e-9 for a, b in zip(sent, sent[1:], strict=False))


def test_reset_after_executor_return_cannot_publish_refill_done(guarded_node):
    node, _, plant, recovery = guarded_node
    original = node._run_v2

    def finish_then_reset(*args):
        assert original(*args) is None
        node._wait_goal_idle = lambda: None
        node.on_reset_begin(1)
        node.on_reset(1)

    node._run_v2 = finish_then_reset
    assert not node._execute_refill(handle_for(plant)).success
    assert not node._event_pub.sent and not plant.feedback.fault and not recovery


@pytest.mark.parametrize('actor', ['arm', 'rail', 'gripper', 'event'])
def test_guarded_publishers_reject_a_previous_reset_generation(nodes, monkeypatch, actor):
    node, module = rf.m0609_harness(nodes, monkeypatch, start=(0.,) * 6)
    node.plant.stop()
    node._module_request, node._module_generation = True, node.generation()
    node.set_goal_active(True)
    node._rail_states.update((0.,) * 3)
    node._rail_command_pub = rf._Pub()
    node._fence.begin(1)
    node._fence.done(1)  # barrier is open again while an old callback is still unwinding
    before = len(node.joints.sent)
    if actor == 'arm':
        node.send_joint_command((.1,) * 6)
    elif actor == 'rail':
        node.send_rail_command((.1,) * 3)
    elif actor == 'gripper':
        node.set_gripper(False)
    else:
        node.publish_event(module.Event.REFILL_DONE, detail='obsolete task')
    assert len(node.joints.sent) == before
    assert not node._rail_command_pub.sent and not node.gripper.sent and not node._event_pub.sent
