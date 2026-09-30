"""뼈대 기동. 네 노드를 use_sim_time 으로 띄운다. 실제 배치는 부하 측정 후 config/ 로 옮긴다."""

from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    """네 뼈대 노드."""
    common = [{'use_sim_time': True}]
    return LaunchDescription([
        Node(package='rokey_p3_orchestrator', executable='orchestrator', name='orchestrator', parameters=common),
        Node(package='rokey_p3_manipulation', executable='arm', name='arm', parameters=common),
        Node(package='rokey_p3_navigation', executable='fleet', name='fleet', parameters=common),
        Node(package='rokey_p3_perception', executable='pouch_detector', name='pouch_detector', parameters=common),
    ])
