"""실제 ROS 구독이 namespace·map_topic·remap을 따르는가. ROS가 없으면 미실행이다."""

import importlib.util
import time
from types import SimpleNamespace

import pytest

MISSING = any(importlib.util.find_spec(name) is None for name in ('rclpy', 'tf2_ros', 'nav2_msgs'))
pytestmark = pytest.mark.skipif(MISSING, reason='ROS 없음 — map 입력 연결 L2 미실행')

if not MISSING:
    import rclpy
    from geometry_msgs.msg import TransformStamped
    from nav_msgs.msg import OccupancyGrid
    from rclpy.parameter import Parameter
    from rclpy.qos import DurabilityPolicy, QoSProfile

    from rokey_p3_navigation.speed_governor_node import SpeedGovernor


@pytest.mark.parametrize(('extra_args', 'suffix'), [
    ([], 'map'),
    (['-p', 'map_topic:=global_costmap/costmap'], 'global_costmap/costmap'),
    (['-r', 'map:=/governor_source_test/global_costmap/costmap'], 'global_costmap/costmap'),
])
def test_filter_receives_only_the_resolved_input_topic(extra_args, suffix):
    """잘못된 소스를 지정하면 실제로 그 격자를 받는다는 반례까지 확인한다. 필터가 소스를 교정하지는 않는다."""
    rclpy.init(args=['--ros-args', '-r', '__ns:=/governor_source_test', *extra_args])
    node = probe = None
    try:
        node = SpeedGovernor()
        # 전역 map remap은 감속기에만 적용한다. 시험 발행자까지 적용하면 decoy/source가 합쳐진다.
        probe = rclpy.create_node('map_source_probe', use_global_arguments=False)
        expected = '/governor_source_test/' + suffix
        assert node._map_topic == expected
        qos = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL)
        other = 'global_costmap/costmap' if suffix == 'map' else 'map'
        decoy = probe.create_publisher(OccupancyGrid, '/governor_source_test/' + other, qos)
        source = probe.create_publisher(OccupancyGrid, expected, qos)
        assert source.topic_name == expected
        assert decoy.topic_name != source.topic_name
        message = OccupancyGrid()
        message.header.frame_id = 'map'
        message.info.width = message.info.height = 1
        message.info.resolution = 0.05
        message.info.origin.orientation.w = 1.0
        message.data = [100]
        decoy.publish(message)
        until = time.monotonic() + 0.3
        while time.monotonic() < until:
            rclpy.spin_once(node, timeout_sec=0.05)
        assert node._static is None
        message.data = [0]
        source.publish(message)
        until = time.monotonic() + 3.0
        while node._static is None and time.monotonic() < until:
            rclpy.spin_once(node, timeout_sec=0.05)
        assert node._static is not None, f'정적 입력 {expected}를 받지 못함'
        assert node._static[0] == [0]
    finally:
        if probe is not None:
            probe.destroy_node()
        if node is not None:
            node.destroy_node()
        rclpy.try_shutdown()


def test_diagnostics_default_off_and_runtime_toggle_preserve_stop_resume(monkeypatch):
    rclpy.init(args=[])
    node = None
    try:
        node = SpeedGovernor()
        assert node.get_parameter('stop_diagnostics').value is False
        lines = []
        monkeypatch.setattr(node, 'get_logger', lambda: SimpleNamespace(
            info=lines.append, warn=lines.append, error=lines.append))
        now = [0.0]
        monkeypatch.setattr(node, '_now_s', lambda: now[0])
        message = OccupancyGrid()
        message.header.frame_id = 'map'
        message.info.width = message.info.height = 101
        message.info.resolution = 0.05
        message.info.origin.position.x = message.info.origin.position.y = -2.525
        message.info.origin.orientation.w = 1.0
        message.data = [0] * (101 * 101)
        node._on_map(message)
        transform = TransformStamped()
        transform.header.frame_id, transform.child_frame_id = 'map', 'governor_test_odom'
        transform.transform.rotation.w = 1.0
        node._tf.set_transform_static(transform, 'test')
        message.header.frame_id = 'governor_test_odom'
        message.data[50 * 101 + 66] = 100  # 몸체 앞끝에서 0.3 m
        node._heading = 0.0
        node._on_costmap(message)
        assert node._rule.stopped and node._percent == 1.0
        assert not any('governor ahead ' in line for line in lines)
        assert sum('governor stop reason=obstacle' in line for line in lines) == 1
        result = node.set_parameters([Parameter('stop_diagnostics', value=True)])
        assert all(item.successful for item in result)
        node._on_costmap(message)
        assert node._rule.stopped and node._percent == 1.0
        assert sum('governor ahead ' in line for line in lines) == 1
        assert all(item.successful for item in node.set_parameters([Parameter('stop_diagnostics', value=False)]))
        message.data = [0] * (101 * 101)
        now[0] = 1.0
        node._on_costmap(message)
        now[0] = 2.0
        node._on_costmap(message)
        assert not node._rule.stopped and node._percent > 1.0
        assert sum('governor ahead ' in line for line in lines) == 1
        assert sum('governor resume ' in line for line in lines) == 1
    finally:
        if node is not None:
            node.destroy_node()
        rclpy.try_shutdown()
