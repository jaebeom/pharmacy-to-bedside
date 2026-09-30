"""navigation 레인 한 묶음: base_driver, fleet, zones_tf 와 Nav2 스택.

세 노드는 전역 네임스페이스에서 돌고 토픽 이름은 `robot_namespace` 파라미터로 만든다.
`/tf`, `/tf_static` 이 전역이라야 Isaac·AMCL 과 같은 트리를 쓴다.
Nav2 는 `use_nav2:=false` 로 뺄 수 있다(맵이 없을 때).

`motion_backend:=waypoints` 는 빈월드 v0 다(기본은 `nav2`). 이때는 AMCL 이 없으므로
`map` → `<ns>/odom` 을 낼 것이 없다. 그래서 이 모드에서만 `dock_origin_tf` 를 같이 띄운다.
그 변환은 항등이 아니라 **도크 자리만큼 평행이동**이다(스테이지의 조인트 원점이 출발 도크다).
기본 모드에는 영향이 없다(AMCL 이 그 변환의 작성자다).

`localization:=odom` 은 nav2 모드에서 AMCL 을 빼고 같은 `dock_origin_tf` 를 띄운다(시뮬 전용).
Isaac 의 odom 은 참값을 따르고(병원 L3 2회차 추종기 d_xy 0.018 m), 렌더 기하로 만든 지도 위 AMCL 은
0.18–0.31 m 어긋났다(2·3회차). 고정물 옆 0.05 m 정차에는 그 오차가 크다. 기본은 `amcl` 그대로다.
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PythonExpression
from launch_ros.actions import Node
from nav2_common.launch import RewrittenYaml


def generate_launch_description():
    """세 노드 + (선택) Nav2."""
    share = get_package_share_directory('rokey_p3_navigation')
    namespace = LaunchConfiguration('namespace')
    use_sim_time = LaunchConfiguration('use_sim_time')
    backend = LaunchConfiguration('motion_backend')
    waypoints_mode = PythonExpression(["'", backend, "' == 'waypoints'"])
    localization = LaunchConfiguration('localization')
    no_amcl = PythonExpression(["'", backend, "' == 'waypoints' or '", localization, "' == 'odom'"])

    arguments = [
        DeclareLaunchArgument('namespace', default_value='amr_1',
                              description='AMR 네임스페이스. 계약의 amr_1'),
        DeclareLaunchArgument('use_sim_time', default_value='true'),
        DeclareLaunchArgument('use_nav2', default_value='true',
                              description='Nav2 + AMCL + map_server 도 띄운다'),
        DeclareLaunchArgument(
            'zones_file', default_value='',
            description='비면 rokey_p3_description share 의 config/zones.yaml'),
        DeclareLaunchArgument(
            'params_file', default_value=os.path.join(share, 'config', 'navigation_params.yaml'),
            description='base_driver, fleet, zones_tf 파라미터'),
        DeclareLaunchArgument(
            'map', default_value=os.path.join(share, 'config', 'maps', 'hospital.yaml'),
            description='occupancy map yaml. 9/17 마스터에서 추출한다'),
        DeclareLaunchArgument(
            'nav2_params_file', default_value=os.path.join(share, 'config', 'nav2_params.yaml')),
        DeclareLaunchArgument(
            'motion_backend', default_value='nav2',
            description='fleet 의 이동 backend. nav2(기본) 또는 waypoints(빈월드 v0 고정 경로)'),
        DeclareLaunchArgument(
            'nav2_final_approach', default_value='false',
            description='nav2 모드: Nav2 는 경로의 마지막 waypoint(접근점)까지, '
                        '정차 자리까지는 추종기로(routes_file 필요)'),
        DeclareLaunchArgument(
            'localization', default_value='amcl',
            description="nav2 모드의 map -> odom 작성자. amcl(기본) 또는 odom(시뮬 전용: AMCL 없이 도크 평행이동)"),
        DeclareLaunchArgument(
            'routes_file', default_value='',
            description='waypoints 모드의 월드별 경로 파일. 비면 zone 사이를 곧장 간다'),
    ]

    # root_key 를 주지 않는다. 세 노드는 전역 네임스페이스라 파일의 키가 곧 노드 이름이다.
    parameters = RewrittenYaml(
        source_file=LaunchConfiguration('params_file'),
        param_rewrites={'use_sim_time': use_sim_time, 'robot_namespace': namespace,
                        'zones_file': LaunchConfiguration('zones_file'),
                        'motion_backend': backend,
                        'routes_file': LaunchConfiguration('routes_file'),
                        'nav2_final_approach': LaunchConfiguration('nav2_final_approach')},
        convert_types=True)

    def lane_node(executable):
        return Node(package='rokey_p3_navigation', executable=executable, name=executable,
                    output='screen', parameters=[parameters])

    return LaunchDescription(arguments + [
        lane_node('base_driver'),
        lane_node('fleet'),
        lane_node('zones_tf'),
        # 빈월드 v0 또는 localization:=odom: AMCL 이 없으니 map -> odom 을 낼 것이 없다. 그때만 띄운다.
        # 항등이 아니라 **도크 자리만큼 평행이동**이다 — 스테이지의 조인트 원점이 출발 도크이기 때문이다
        # (dock_origin_tf_node 의 docstring 참고). 자세의 출처는 zones.yaml 하나다.
        Node(package='rokey_p3_navigation', executable='dock_origin_tf', name='dock_origin_tf',
             output='screen', condition=IfCondition(no_amcl), parameters=[parameters]),
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(os.path.join(share, 'launch', 'nav2.launch.py')),
            condition=IfCondition(PythonExpression(
                ["'", LaunchConfiguration('use_nav2'), "' in ('true', 'True', '1') and not ",
                 waypoints_mode])),
            launch_arguments={'namespace': namespace, 'use_sim_time': use_sim_time,
                              'map': LaunchConfiguration('map'), 'localization': localization,
                              'params_file': LaunchConfiguration('nav2_params_file')}.items()),
    ])
