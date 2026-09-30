"""Nav2 + AMCL + map_server. ROS 2 Jazzy / Nav2 Jazzy 기준.

노드는 `namespace`(기본 `amr_1`) 안에서 돌고 토픽은 그 안의 상대 이름이다: `scan`, `odom`, `cmd_vel`.
TF 는 remap 하지 않는다. `/tf`, `/tf_static` 은 전역이고 Isaac·base_driver·zones_tf 와 같은 트리다.

맵은 9/17 마스터에서 뽑는다. 경로는 `map` 인자다.
`localization:=odom` 이면 AMCL 을 띄우지 않는다(map -> odom 은 navigation.launch 의 dock_origin_tf 가 낸다).

`speed_governor` 도 이 묶음 안에서 돈다. 지역 코스트맵의 여유로 `controller_server` 의 속도 제한을 낸다 —
최고 속도를 1.0 m/s 로 올린 대신 가까운 곳에서 50 % 로 줄이는 쪽이 짝이다(#526 을 #547 로 되돌린 이유).
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, GroupAction
from launch.conditions import IfCondition, UnlessCondition
from launch.substitutions import LaunchConfiguration, PythonExpression
from launch_ros.actions import Node, PushRosNamespace
from nav2_common.launch import ReplaceString, RewrittenYaml

LOCALIZATION_NODES = ['map_server', 'amcl']
#: `localization:=odom` 일 때. map_server 는 costmap 의 static layer 에 그대로 필요하다.
MAP_ONLY_NODES = ['map_server']
NAVIGATION_NODES = ['controller_server', 'planner_server', 'behavior_server', 'bt_navigator']


def generate_launch_description():
    """localization(map_server, amcl) 과 navigation(controller, planner, behavior, bt) 두 묶음."""
    share = get_package_share_directory('rokey_p3_navigation')
    namespace = LaunchConfiguration('namespace')
    use_sim_time = LaunchConfiguration('use_sim_time')
    autostart = LaunchConfiguration('autostart')
    log_level = LaunchConfiguration('log_level')

    arguments = [
        DeclareLaunchArgument('namespace', default_value='amr_1',
                              description='AMR 네임스페이스. 계약의 amr_1'),
        DeclareLaunchArgument('use_sim_time', default_value='true',
                              description='/clock 은 Isaac 하나가 낸다(계약 4절)'),
        DeclareLaunchArgument('autostart', default_value='true',
                              description='lifecycle 노드를 자동으로 active 로'),
        DeclareLaunchArgument('log_level', default_value='info'),
        DeclareLaunchArgument(
            'map', default_value=os.path.join(share, 'config', 'maps', 'hospital.yaml'),
            description='occupancy map yaml. 9/17 마스터에서 추출한다'),
        DeclareLaunchArgument(
            'localization', default_value='amcl',
            description='amcl(기본) 또는 odom(시뮬 전용: AMCL 을 띄우지 않는다)'),
        DeclareLaunchArgument(
            'params_file', default_value=os.path.join(share, 'config', 'nav2_params.yaml'),
            description='Nav2 파라미터'),
    ]

    # 코스트맵 장애물 층의 관측 토픽은 **절대 이름**이어야 한다. 코스트맵은 `/<ns>/local_costmap`
    # 네임스페이스의 노드라 상대 `scan` 이 `/<ns>/local_costmap/scan` 으로 한 단계 더 들어간다 —
    # 라이다는 `/<ns>/scan` 으로 낸다(9/23 회차18: 그 토픽 Subscription 0). 그렇다고 `/amr_1/scan` 을
    # 박으면 `namespace` 인자가 죽으므로, yaml 의 `<robot_namespace>` 를 여기서 바꾼다(nav2 관용구).
    params_file = ReplaceString(
        source_file=LaunchConfiguration('params_file'),
        replacements={'<robot_namespace>': ('/', namespace)})

    # 네임스페이스를 파라미터 키 앞에 붙이고 map 경로와 use_sim_time 을 덮어쓴다.
    parameters = RewrittenYaml(
        source_file=params_file,
        root_key=namespace,
        param_rewrites={'use_sim_time': use_sim_time, 'yaml_filename': LaunchConfiguration('map')},
        convert_types=True)

    with_amcl = PythonExpression(["'", LaunchConfiguration('localization'), "' != 'odom'"])

    def nav2_node(package, executable, name, condition=None):
        return Node(package=package, executable=executable, name=name, output='screen',
                    parameters=[parameters], condition=condition,
                    arguments=['--ros-args', '--log-level', log_level])

    def lifecycle_manager(name, node_names, condition=None):
        return Node(package='nav2_lifecycle_manager', executable='lifecycle_manager', name=name,
                    output='screen', condition=condition,
                    parameters=[{'use_sim_time': use_sim_time, 'autostart': autostart,
                                 'node_names': node_names}])

    nodes = GroupAction([
        PushRosNamespace(namespace),
        nav2_node('nav2_map_server', 'map_server', 'map_server'),
        nav2_node('nav2_amcl', 'amcl', 'amcl', condition=IfCondition(with_amcl)),
        lifecycle_manager('lifecycle_manager_localization', LOCALIZATION_NODES, condition=IfCondition(with_amcl)),
        lifecycle_manager('lifecycle_manager_localization', MAP_ONLY_NODES, condition=UnlessCondition(with_amcl)),
        # map_server 활성화 감시(회차133: configure 응답이 DDS 에서 사라져 관리자가 멈추고 지도가 한 번도 안 나왔다).
        # 20 s 안에 active 가 아니면 map_server 에 직접 configure/activate 를 보낸다. 정상이면 한 줄만 남긴다.
        Node(package='rokey_p3_navigation', executable='map_activation_guard', name='map_activation_guard',
             output='screen', parameters=[{'target': 'map_server'}],
             arguments=['--ros-args', '--log-level', log_level]),
        nav2_node('nav2_controller', 'controller_server', 'controller_server'),
        # 속도 제한(재범 9/23: 넓은 복도에서 빠르게, 가까운 데서만 0.5). controller_server 와 **같은
        # 네임스페이스**여야 `local_costmap/costmap` 과 `speed_limit` 이 맞는다. Nav2 lifecycle 이
        # 아니라 그냥 노드다 — 없으면 제한이 안 오고 nav2_params 의 최고 속도가 그대로 쓰인다.
        Node(package='rokey_p3_navigation', executable='speed_governor', name='speed_governor',
             output='screen', parameters=[parameters],
             arguments=['--ros-args', '--log-level', log_level]),
        nav2_node('nav2_planner', 'planner_server', 'planner_server'),
        nav2_node('nav2_behaviors', 'behavior_server', 'behavior_server'),
        nav2_node('nav2_bt_navigator', 'bt_navigator', 'bt_navigator'),
        lifecycle_manager('lifecycle_manager_navigation', NAVIGATION_NODES),
    ])

    return LaunchDescription(arguments + [nodes])
