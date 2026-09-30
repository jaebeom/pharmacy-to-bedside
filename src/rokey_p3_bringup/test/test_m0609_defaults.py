"""L2 startup: real ROS parameter overrides select guarded v2 and retain legacy modes."""

from contextlib import contextmanager

import pytest
import rclpy
from rclpy.executors import SingleThreadedExecutor
from rclpy.node import Node

from l2_teardown import assert_no_leftovers, teardown_nodes
from rokey_p3_manipulation.m0609_arm_node import M0609ArmNode
from rokey_p3_manipulation.module_execution import Feedback


@contextmanager
def configured_arm(*parameters):
    assert_no_leftovers()
    args = ['test_m0609_defaults', '--ros-args']
    for parameter in parameters:
        args.extend(['-p', parameter])
    rclpy.init(args=args)
    executor = SingleThreadedExecutor()
    # Keep the partially initialized Node so rejected configurations also release ROS resources.
    arm = M0609ArmNode.__new__(M0609ArmNode)
    initialized = False
    try:
        M0609ArmNode.__init__(arm)
        initialized = True
        yield arm
    finally:
        if initialized:
            teardown_nodes(executor, None, [arm])
        else:
            Node.destroy_node(arm)
            teardown_nodes(executor, None, [])


def test_v2_default_initializes_guarded_execution_with_matching_command_period():
    with configured_arm('scene_version:=2', 'use_sim_time:=true') as arm:
        assert isinstance(arm._module_feedback, Feedback)
        assert arm._module_limits.period == arm._period()
        assert arm._rail_joint_names == ['rail_x', 'rail_y', 'rail_z']
        assert arm.at_home() is None  # no arm/rail/holding observations yet


def test_explicit_false_selects_legacy_v2():
    with configured_arm('scene_version:=2', 'use_sim_time:=true',
                        'v2_guarded_module_path:=false') as arm:
        assert arm._scene_v2 and arm._rail_teach is not None
        assert arm._module_feedback is None


@pytest.mark.parametrize('rail_enabled', ['false', 'true'])
def test_default_scene_preserves_legacy_startup(rail_enabled):
    with configured_arm(f'rail_enabled:={rail_enabled}') as arm:
        assert not arm._scene_v2 and arm._module_feedback is None
        assert (arm._rail_teach is not None) == (rail_enabled == 'true')


@pytest.mark.parametrize('parameters', [(), ('use_sim_time:=false',),
                                      ('open_loop:=true',),
                                      ('use_sim_time:=true', 'open_loop:=true')])
def test_v2_legacy_startup_remains_available_outside_guarded_environment(parameters):
    with configured_arm('scene_version:=2', *parameters) as arm:
        assert arm._scene_v2 and arm._rail_teach is not None
        assert arm._module_feedback is None
        assert arm.get_parameter('v2_guarded_module_path').value is False


@pytest.mark.parametrize('parameters', [(), ('use_sim_time:=false',),
                                      ('use_sim_time:=true', 'open_loop:=true')])
def test_explicit_guarded_rejects_incompatible_clock_or_open_loop(parameters):
    with (pytest.raises(ValueError, match='requires closed-loop Isaac simulation'),
          configured_arm('scene_version:=2', 'v2_guarded_module_path:=true', *parameters)):
        pytest.fail('guarded configuration must be refused during startup')


def test_explicit_guarded_path_still_requires_v2():
    with (pytest.raises(ValueError, match='requires scene_version=2'),
          configured_arm('v2_guarded_module_path:=true')):
        pytest.fail('legacy scene must not start with guarded execution enabled')
