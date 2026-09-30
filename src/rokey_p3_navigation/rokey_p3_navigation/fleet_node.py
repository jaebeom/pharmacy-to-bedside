"""fleet: GoToZone 서버. Nav2 NavigateToPose 를 감싼다. 계약 v1 2.2절·5절·6절·7절.

- `/amr_1/go_to_zone` (`GoToZone`): `zone_id` → `zones.yaml` 자세 → Nav2 `NavigateToPose`
- `arrived=true` 는 허용오차 안에서 **정지한 뒤에만** 낸다
- 출발 인터락: `/amr_1/arm/at_home` 이 1.0 s 이내에 true 로 오지 않으면 goal 을 거부한다
- `/amr_1/base/stopped` 5 Hz
- `/events` 의 `RESET_DONE` 을 보면 `/amr_1/initialpose` 를 도크 자세로 내고 Nav2 costmap 둘을 비운다

판정(도킹·정지·출발·제한 시간)은 `docking` 의 순수 함수다. fleet 는 이벤트를 내지 않는다(계약 2.6절).
시계는 둘이다. 액션 제한 시간은 sim time, heartbeat 주기와 stale 판정은 steady clock(wall) 이다(계약 4절).
"""

import os
import contextlib
import math
import threading
import time

import rclpy
from action_msgs.msg import GoalStatus
from geometry_msgs.msg import PoseStamped, PoseWithCovarianceStamped, Twist, Vector3
from nav2_msgs.action import NavigateToPose
from nav2_msgs.srv import ClearEntireCostmap
from nav_msgs.msg import Odometry
from rclpy.action import ActionClient, ActionServer, CancelResponse, GoalResponse
from rclpy.callback_groups import MutuallyExclusiveCallbackGroup, ReentrantCallbackGroup
from rclpy.clock import Clock, ClockType
from rclpy.exceptions import InvalidHandle
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from rclpy.time import Time
from std_msgs.msg import Bool
from tf2_ros import Buffer, TransformException, TransformListener

from rokey_p3_interfaces.action import GoToZone
from rokey_p3_interfaces.msg import DockingState, Event
from rokey_p3_navigation.base_kinematics import quaternion_to_yaw, yaw_to_quaternion
from rokey_p3_navigation.docking import (
    base_stopped,
    departure_allowed,
    docked,
    goal_timeout_s,
    observation_fresh,
    pose_error,
    settle_ok,
    speed_is_quiet,
)
from rokey_p3_navigation.docking_state import EPOCH_BEFORE_RESET, SeqCounter, judge
from rokey_p3_navigation.goal_guard import CANCEL, IGNORED, GoalGuard
from rokey_p3_navigation.qos_profiles import HEARTBEAT, RELIABLE
from rokey_p3_navigation.routes import (
    RoutesError, departure_point, has_pair, load_routes, staging_point, waypoints)
from rokey_p3_navigation.topology import is_terminal
from rokey_p3_navigation.waypoint_follower import REST, FollowerConfig, follow, moving_start
from rokey_p3_navigation.zones import ZonesError, load_zones

#: 인터페이스 v1.1 이 `Event.RESET_DONE` 상수를 넣기 전까지 문자열로 비교한다(계약 10절).
RESET_DONE = 'RESET_DONE'

#: 이동 backend. 심월드에서 Nav2 로 갈아 끼우는 자리는 여기 하나다.
NAV2 = 'nav2'
WAYPOINTS = 'waypoints'


class FleetNode(Node):
    """GoToZone 서버 하나. v1 은 AMR 1대라 동시에 goal 하나만 받는다."""

    def __init__(self):
        super().__init__('fleet')

        namespace = self.declare_parameter('robot_namespace', 'amr_1').value
        zones_file = self.declare_parameter('zones_file', '').value
        self._dock_zone = self.declare_parameter('dock_zone', 'dock_1').value
        self._at_home_max_age = float(self.declare_parameter('at_home_max_age_s', 1.0).value)
        self._odom_timeout = float(self.declare_parameter('odom_timeout_s', 1.0).value)
        self._linear_tol = float(self.declare_parameter('stopped_linear_tol', 0.02).value)
        self._angular_tol = float(self.declare_parameter('stopped_angular_tol', 0.02).value)
        self._quiet_hold = float(self.declare_parameter('stopped_hold_s', 0.5).value)
        self._timeout_load_dock = float(
            self.declare_parameter('goal_timeout_load_dock_s', 120.0).value)
        self._timeout_ward = float(self.declare_parameter('goal_timeout_ward_s', 180.0).value)
        self._settle_timeout = float(self.declare_parameter('settle_timeout_s', 5.0).value)
        self._nav_server_wait = float(self.declare_parameter('nav2_server_wait_s', 10.0).value)
        stopped_rate = float(self.declare_parameter('stopped_rate_hz', 5.0).value)
        navigate_action = self.declare_parameter(
            'navigate_action', f'/{namespace}/navigate_to_pose').value
        self._costmap_clear_wait = max(
            0.0, float(self.declare_parameter('costmap_clear_wait_s', 10.0).value))
        global_clear_service = self.declare_parameter(
            'global_costmap_clear_service',
            f'/{namespace}/global_costmap/clear_entirely_global_costmap').value
        local_clear_service = self.declare_parameter(
            'local_costmap_clear_service',
            f'/{namespace}/local_costmap/clear_entirely_local_costmap').value
        # RViz·AMCL 관례값이다. 맵과 도킹 오차를 잰 뒤 조정한다.
        self._cov_xy = float(self.declare_parameter('initialpose_cov_xy', 0.25).value)
        self._cov_yaw = float(self.declare_parameter('initialpose_cov_yaw', 0.0685).value)
        self._base_frame = f'{namespace}/base_link'
        self._odom_frame = f'{namespace}/odom'
        # 이동 backend. 기본은 지금까지의 Nav2 다. waypoints 는 빈월드 v0 의 고정 경로 추종이다.
        self._backend = self.declare_parameter('motion_backend', NAV2).value
        if self._backend not in (NAV2, WAYPOINTS):
            self.get_logger().error(f'모르는 motion_backend {self._backend!r}. {NAV2} 로 둔다.')
            self._backend = NAV2
        routes_file = self.declare_parameter('routes_file', '').value
        # nav2 모드에서 Nav2 는 경로의 마지막 waypoint(접근점)까지만 보내고, 정차 자리까지의 마지막 구간은
        # waypoint 추종기로 붙는다(`routes.staging_point`). 기본 꺼짐 — 끄면 지금까지처럼 Nav2 가 끝까지 간다.
        self._final_approach = bool(self.declare_parameter('nav2_final_approach', False).value)
        # 접근점까지 이만큼 남으면 Nav2 를 거두고 추종기로 넘긴다. 병원 L3 3회차(9/23): Nav2 가 접근점
        # 0.25 m 앞(goal 공차 0.2 밖)에서 `Failed to make progress` 로 180 s 를 넘겼다. 추종기는 접근점을
        # 거쳐 정차 자리로 가므로 넘기는 자리가 경로 밖으로 벗어나지 않는다.
        self._handoff_radius = float(self.declare_parameter('nav2_handoff_radius', 0.5).value)
        self._handoff_requested = False
        # 빈월드에서 튜닝할 값이다. 실측이 아니다.
        self._follower = FollowerConfig(
            max_linear=float(self.declare_parameter('follower_max_linear', 0.3).value),
            max_angular=float(self.declare_parameter('follower_max_angular', 0.5).value),
            slow_radius=float(self.declare_parameter('follower_slow_radius', 0.5).value),
            waypoint_tolerance=float(
                self.declare_parameter('follower_waypoint_tolerance', 0.05).value),
            # 도착으로 볼 반경. zone 공차(판정의 선)와 다른 것이고, 실제로는 둘 중 작은 값을 쓴다.
            arrive_xy=float(self.declare_parameter('follower_arrive_xy', 0.02).value),
            arrive_yaw=float(self.declare_parameter('follower_arrive_yaw', 0.02).value),
            # 한 주기에 명령이 바뀔 수 있는 폭. 상판의 봉투가 미끄러지지 않게 하는 값이고,
            # 사슬 어디에도 다른 가속 상한이 없다(스테이지 드라이브는 damping 이 커서 계단을 그대로 따른다).
            max_accel=float(self.declare_parameter('follower_max_accel', 0.8).value),
            max_angular_accel=float(
                self.declare_parameter('follower_max_angular_accel', 1.6).value))
        self._follower_period = 1.0 / float(self.declare_parameter('follower_rate_hz', 20.0).value)
        # 계약 11.6 `/<ns>/base/docked`(DockingState). opt-in 이다. 끄면 토픽도 만들지 않는다.
        self._docking_enabled = bool(self.declare_parameter('publish_docking_state', False).value)
        # AMCL(map -> odom) 신선도 문턱, sim s. 계약 11.6: 문턱은 L3 측정 뒤 정한다.
        # 0 이하는 미정이고, 미정이면 DockingState 는 늘 UNKNOWN 이다. 값을 추측해 채우지 않는다.
        self._amcl_max_age = float(self.declare_parameter('amcl_max_age_s', 0.0).value)
        self._docking_zone_id = None     # 마지막으로 수락한 GoToZone 의 목표. RESET_DONE 에서 비운다
        self._docking_seq = SeqCounter()
        self._here = self._dock_zone     # 마지막으로 도착한 zone. 경로를 고를 때 쓴다

        self._zones = self._load_zones(zones_file)
        self._routes = self._load_routes(routes_file)   # zones 를 참조하므로 그 뒤여야 한다
        self._at_home = None
        self._at_home_at = None      # steady clock
        self._odom_at = None         # steady clock
        self._odom_stamp = None      # sim time (초)
        self._odom_twist = None      # 마지막 odom 속도 (vx, vy, wz), base_link. 추종기를 움직이는 채로 넘겨받을 때 쓴다
        self._quiet_for = 0.0        # sim time 으로 잰 정지 지속 시간
        self._accepted = False       # GoToZone goal 을 받아 둔 상태인가
        self._goal_handle = None
        self._nav_goal_handle = None
        self._deadline = None        # sim time
        self._outcome = None         # tick·RESET_DONE 이 먼저 정한 종료 이유
        self._settle_event = threading.Event()
        self._settle_message = None
        self._settle_deadline = None
        # Nav2 하위 goal 의 token, 마지막 RESET_DONE epoch, cancel 종결 대기(계약 7절 10 s wall)
        self._guard = GoalGuard()

        self._tf_buffer = Buffer()
        self._tf_listener = TransformListener(self._tf_buffer, self)

        watchers = MutuallyExclusiveCallbackGroup()
        actions = ReentrantCallbackGroup()

        self._costmap_clear_clients = {}
        if self._backend == NAV2:
            self._costmap_clear_clients = {
                'global': self.create_client(
                    ClearEntireCostmap, global_clear_service, callback_group=actions),
                'local': self.create_client(
                    ClearEntireCostmap, local_clear_service, callback_group=actions),
            }
        self._costmap_clear_epoch = None
        self._costmap_clear_deadline = None
        self._costmap_clear_pending = {}

        self._stopped_publisher = self.create_publisher(
            Bool, f'/{namespace}/base/stopped', HEARTBEAT)
        self._initialpose_publisher = self.create_publisher(
            PoseWithCovarianceStamped, f'/{namespace}/initialpose', RELIABLE)
        self._cmd_vel_publisher = None
        # nav2 모드에서도 `nav2_final_approach` 면 마지막 구간은 추종기가 cmd_vel 을 낸다. Nav2 controller 와
        # 같은 토픽이지만 동시에 내지 않는다 — 추종기는 Nav2 goal 이 SUCCEEDED 로 끝난 뒤에만 돈다.
        if self._backend == WAYPOINTS or self._final_approach:
            self._cmd_vel_publisher = self.create_publisher(
                Twist, f'/{namespace}/cmd_vel', RELIABLE)
        self._docked_publisher = None
        if self._docking_enabled:
            self._docked_publisher = self.create_publisher(
                DockingState, f'/{namespace}/base/docked', HEARTBEAT)
        self.create_subscription(Odometry, f'/{namespace}/odom', self._on_odom,
                                 RELIABLE, callback_group=watchers)
        self.create_subscription(Bool, f'/{namespace}/arm/at_home', self._on_at_home,
                                 HEARTBEAT, callback_group=watchers)
        # 계약 2.5절의 /events 는 L(latched) 이지만 fleet 는 volatile 로 받는다.
        # 재시작한 fleet 가 밀린 RESET_DONE 을 보고 initialpose 를 다시 내면 안 된다.
        # 발행자가 TRANSIENT_LOCAL 이라 QoS 는 호환된다.
        self.create_subscription(Event, '/events', self._on_event,
                                 RELIABLE, callback_group=watchers)
        # heartbeat 주기는 wall 이다. sim time 으로 돌리면 RTF 가 낮을 때 받는 쪽에서 stale 이 된다.
        self.create_timer(1.0 / stopped_rate, self._tick, callback_group=watchers,
                          clock=Clock(clock_type=ClockType.STEADY_TIME))

        self._navigator = ActionClient(self, NavigateToPose, navigate_action,
                                       callback_group=actions)
        self._server = ActionServer(
            self, GoToZone, f'/{namespace}/go_to_zone',
            execute_callback=self._execute,
            goal_callback=self._on_goal,
            cancel_callback=self._on_cancel,
            callback_group=actions)

        self.get_logger().info(
            f'fleet up. 구역 {sorted(self._zones.zones) if self._zones else "없음"}, '
            f'리셋 뒤 도크 {self._dock_zone}, Nav2 액션 {navigate_action}')

    # -- 설정 -------------------------------------------------------------

    def _load_zones(self, zones_file):
        """zones.yaml 을 읽는다. 없으면 goal 을 전부 거부한다."""
        if not zones_file:
            try:
                from ament_index_python.packages import get_package_share_directory
                share = get_package_share_directory('rokey_p3_description')
            except Exception as exc:  # 패키지를 못 찾는다
                self.get_logger().error(f'zones.yaml 경로를 못 찾았다: {exc}')
                return None
            zones_file = f'{share}/config/zones.yaml'
        try:
            zones = load_zones(zones_file)
        except (OSError, ZonesError) as exc:
            self.get_logger().error(f'zones.yaml 을 못 읽었다({zones_file}): {exc}')
            return None
        for zone in zones.zones.values():
            if zone.tol_xy <= 0.0 or zone.tol_yaw <= 0.0:
                self.get_logger().warn(
                    f'{zone.zone_id} 의 허용오차가 0 이다. 도착 판정이 성립하지 않는다. '
                    '9/19 도킹 오차 측정 뒤 채운다.')
        return zones

    def _load_routes(self, routes_file):
        """월드별 routes 파일을 읽는다. 비우면 없는 것이고, 그러면 zone 사이를 곧장 간다."""
        if not routes_file or self._zones is None:
            return None
        try:
            return load_routes(routes_file, self._zones)
        except (OSError, RoutesError) as exc:
            self.get_logger().error(f'routes 파일을 못 읽었다({routes_file}): {exc}')
            return None

    # -- 상태 수신 --------------------------------------------------------

    def _on_odom(self, msg):
        """정지 판정용 속도만 본다. 자세는 TF(map -> base_link)로 본다.

        수신이 `odom_timeout_s` 넘게 끊겼으면 그 전의 정지 누적은 버린다. 빈 구간을 조용한
        시간으로 이어 붙이면 관측이 없어도 arrived 가 된다.
        """
        stamp = msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9
        now = time.monotonic()
        gap = not observation_fresh(
            None if self._odom_at is None else now - self._odom_at, self._odom_timeout)
        linear = (msg.twist.twist.linear.x ** 2 + msg.twist.twist.linear.y ** 2) ** 0.5
        if gap or not speed_is_quiet(
                linear, msg.twist.twist.angular.z, self._linear_tol, self._angular_tol):
            self._quiet_for = 0.0
        elif self._odom_stamp is not None and stamp > self._odom_stamp:
            self._quiet_for += stamp - self._odom_stamp
        self._odom_stamp = stamp
        self._odom_at = now
        self._odom_twist = (msg.twist.twist.linear.x, msg.twist.twist.linear.y, msg.twist.twist.angular.z)

    def _on_at_home(self, msg):
        """출발 인터락 입력. 계약 5절."""
        self._at_home = bool(msg.data)
        self._at_home_at = time.monotonic()

    def _on_event(self, msg):
        """fleet 는 RESET_DONE 만 본다(계약 2.5절). 늦게 온 이전 epoch 은 버린다."""
        if msg.name != RESET_DONE:
            return
        if self._guard.on_reset_done(msg.epoch, time.monotonic()) == IGNORED:
            return
        self._docking_zone_id = None
        self._here = self._dock_zone
        self.get_logger().info(f'RESET_DONE epoch {msg.epoch}. initialpose 를 {self._dock_zone} 로.')
        if self._goal_handle is not None:
            self._close_nav('리셋', 'reset')
        if self._publish_initialpose():
            self._start_costmap_clear(msg.epoch)

    # -- 액션 -------------------------------------------------------------

    def _on_goal(self, goal):
        """수락 조건은 계약 5절. 거부는 goal 거부로 끝난다(이벤트 없음)."""
        zone_id = goal.zone_id
        if self._zones is None or zone_id not in self._zones.zones:
            self.get_logger().warn(f'GoToZone 거부: 모르는 구역 {zone_id}')
            return GoalResponse.REJECT
        if not is_terminal(zone_id):
            self.get_logger().warn(f'GoToZone 거부: {zone_id} 는 경유 전용 구역이다(계약 3절)')
            return GoalResponse.REJECT
        if self._accepted:
            self.get_logger().warn(f'GoToZone 거부: 진행 중인 goal 이 있다 ({zone_id})')
            return GoalResponse.REJECT
        age = None if self._at_home_at is None else time.monotonic() - self._at_home_at
        if not departure_allowed(self._at_home, age, self._at_home_max_age):
            self.get_logger().warn(
                f'GoToZone 거부: arm/at_home 이 {self._at_home} (age {age}). 계약 5절 출발 인터락.')
            return GoalResponse.REJECT
        self._docking_zone_id = zone_id
        self._accepted = True
        return GoalResponse.ACCEPT

    def _on_cancel(self, goal_handle):
        """취소는 받는다. Nav2 goal 취소는 tick 이 보낸다."""
        return CancelResponse.ACCEPT

    def _execute(self, goal_handle):
        """Nav2 로 보내고, 멈춰 선 뒤에야 arrived 를 낸다. 재시도는 없다(계약 7절)."""
        zone = self._zones.zones[goal_handle.request.zone_id]
        self._outcome = None
        self._settle_message = None
        self._settle_deadline = None
        self._settle_event.clear()
        self._deadline = self._sim_now() + goal_timeout_s(
            zone.kind, self._timeout_load_dock, self._timeout_ward)
        token = self._guard.begin()
        self._goal_handle = goal_handle
        try:
            if self._backend == WAYPOINTS:
                return self._follow_waypoints(goal_handle, zone)
            return self._navigate(goal_handle, zone, token)
        finally:
            self._guard.finish(token)
            self._goal_handle = None
            self._nav_goal_handle = None
            self._deadline = None
            self._accepted = False

    def _navigate(self, goal_handle, zone, token):
        if not self._navigator.wait_for_server(timeout_sec=self._nav_server_wait):
            return self._finish(goal_handle, self._closed_outcome() or 'nav2_unavailable')
        # 서버를 기다리는 동안 취소·제한 시간·리셋으로 닫혔으면 Nav2 에 보내지 않는다.
        if not self._guard.should_send(token):
            return self._finish(goal_handle, self._closed_outcome())

        if self._final_approach:
            # 병상 정차 자리에서 떠나면 먼저 들어온 길로 접근점까지 물러난다(도착의 거울, routes.departure_point).
            here = self._zones.zones.get(self._here)
            departure = departure_point(self._routes, here, zone.zone_id, self._current_pose(),
                                        here.tol_xy if here is not None else 0.0)
            if departure is not None:
                closed = self._back_out(goal_handle, here, departure)
                if closed is not None:
                    return closed

        staging = (staging_point(self._routes, self._here, zone.zone_id)
                   if self._final_approach else None)
        nav_goal = NavigateToPose.Goal()
        nav_goal.pose = self._zone_pose(zone, at=staging)
        self._handoff_requested = False
        send_future = self._navigator.send_goal_async(
            nav_goal, feedback_callback=lambda message: self._on_nav_feedback(goal_handle, message, staging))
        give_up = self._cancel_wait_expired
        nav_goal_handle = _wait_for(send_future, give_up)
        if nav_goal_handle is None and give_up():
            # 수락 응답 없이 cancel 종결 대기가 끝났다. 늦게 수락되면 그때 취소한다.
            send_future.add_done_callback(lambda future: self._cancel_if_late(token, future))
            return self._finish(goal_handle, self._closed_outcome())
        if nav_goal_handle is None or not nav_goal_handle.accepted:
            return self._finish(goal_handle, self._closed_outcome() or 'nav2_rejected')
        self._nav_goal_handle = nav_goal_handle
        # 보내는 사이에 닫혔으면 _close_nav 가 이 goal 을 못 봤다. 여기서 취소한다.
        if self._guard.on_accepted(token) == CANCEL:
            nav_goal_handle.cancel_goal_async()

        # 제한 시간·취소·리셋은 tick 과 RESET_DONE 이 Nav2 goal 을 취소해서 이 대기를 끝낸다.
        # Nav2 가 cancel 에 답하지 않아도 cancel 종결 대기(계약 7절 10 s wall) 뒤에는 끝낸다.
        result = _wait_for(nav_goal_handle.get_result_async(), give_up)
        if result is None:
            self.get_logger().warn('Nav2 가 cancel 뒤 종결을 알리지 않았다. 결과 없이 끝낸다.')
            return self._finish(goal_handle, self._closed_outcome())
        status = result.status
        if self._closed_outcome() is not None:
            return self._finish(goal_handle, self._closed_outcome())
        if status != GoalStatus.STATUS_SUCCEEDED:
            if staging is not None and self._near(staging):
                # 넘김 반경 안에서 Nav2 가 멈췄거나(abort) 우리가 거뒀다(cancel). yaw 는 아직 안 맞았다 — 추종기가
                # 접근점까지 yaw 를 그대로 두고 옮긴 뒤 거기서 돈다(9/24 10건: 옮기며 돌다 D3 협탁에 닿았다).
                self.get_logger().info(
                    f'{self._here} → {zone.zone_id}: Nav2 가 접근점 ({staging[0]:.3f}, {staging[1]:.3f}) '
                    f'{self._handoff_radius:.2f} m 안에서 status {status} 로 끝났다. 접근점부터 추종기로 간다.')
                return self._follow_waypoints(goal_handle, zone, path=(staging,))
            return self._finish(goal_handle, f'nav2_status_{status}')
        if staging is not None:
            # Nav2 가 접근점에서 yaw 를 goal 공차 안으로 맞췄다. 남은 차이는 추종기가 접근점에서 제자리로 맞추고
            # 정차 자리까지는 곧장(waypoint 0개) 옆걸음으로 붙는다.
            self.get_logger().info(
                f'{self._here} → {zone.zone_id}: Nav2 로 접근점 ({staging[0]:.3f}, {staging[1]:.3f}) 도착. '
                '마지막 구간은 추종기로 간다.')
            return self._follow_waypoints(goal_handle, zone, path=())

        self._settle_deadline = min(self._deadline, self._sim_now() + self._settle_timeout)
        # tick 이 판정을 끝낸다. 종료 중이면 tick 이 더 돌지 않으므로 기다리지 않는다(무한 대기 금지).
        while not self._settle_event.wait(timeout=0.2):
            if self._shutting_down():
                return self._finish(goal_handle, 'canceled')
        if self._settle_message == 'arrived':
            self._here = zone.zone_id
        return self._finish(goal_handle, self._settle_message)

    def _back_out(self, goal_handle, here, point):
        """정차 자리 `here` 에서 접근점 `point` 까지 yaw 를 그대로 두고 옮긴다. 닿으면 None, 닫히면 `_finish` 결과.

        Nav2 는 그 뒤 접근점에서 시작한다. 정차 자리에서 곧장 Nav2 로 떠나면 footprint 가 협탁에서 2 mm 라
        DWB 가 비껴 나가며 모서리를 스쳤다(9/24 10건 bed_b1 → bed_b2, touch 2).
        """
        goal = (point[0], point[1], here.yaw)
        previous = ((0.0, 0.0), 0.0)
        started = self._sim_now()
        self.get_logger().info(
            f'{here.zone_id} 에서 떠난다. 접근점 ({point[0]:.3f}, {point[1]:.3f}) 까지 방향 고정 옆걸음.')
        while True:
            if not self.context.ok():
                self.get_logger().info('종료 중이다. 물러나기를 멈춘다.')
                return self._finish(goal_handle, 'canceled')
            if self._closed_outcome() is not None:
                self._publish_zero_velocity()
                return self._finish(goal_handle, self._closed_outcome())
            command = follow(self._current_pose(), (), 0, goal, here.tol_xy, here.tol_yaw, self._follower,
                             previous=previous, dt=self._follower_period)
            previous = (command.world, command.wz)
            if command.reason is not None:
                self.get_logger().warn(f'물러나기 정지: {command.reason}', throttle_duration_sec=5.0)
            if command.arrived:
                self._publish_zero_velocity()
                self.get_logger().info(
                    f'{here.zone_id} 접근점 도착({self._sim_now() - started:.1f} s sim). Nav2 로 넘긴다.')
                return None
            if not self._publish_cmd_vel(
                    Twist(linear=Vector3(x=command.vx, y=command.vy), angular=Vector3(z=command.wz))):
                return self._finish(goal_handle, 'canceled')
            time.sleep(self._follower_period)

    def _follow_waypoints(self, goal_handle, zone, path=None):
        """빈월드 v0: 고정 waypoint 를 따라 `cmd_vel` 을 낸다. 장애물 회피·재계획은 없다.

        도착은 추종기의 공차 판정 + 기존 정지 판정(`stopped_hold_s`)이다. 취소·리셋·제한 시간은
        tick 이 세운 `_outcome` 으로 끝난다(Nav2 경로와 같다).

        `path` 를 주면(nav2 final approach) 접근점에서 먼저 제자리로 yaw 를 맞추고 옆걸음으로 정차 자리에 든다
        (`follow` 의 `turn_first`). 접근점은 회전 여유가 트인 자리다(`hospital_nav.approach_point`).
        """
        explicit = path is not None
        if not explicit:
            path = waypoints(self._routes, self._here, zone.zone_id)
        if not explicit and self._routes is not None and not has_pair(self._routes, self._here, zone.zone_id):
            # 빈 목록("따져 봤다")과 쌍 없음("아무도 안 따져 봤다")은 가는 방법이 같아 조용히 섞인다.
            # 여기서 갈라 놓지 않으면 zone 이 하나 늘 때 고정물을 가로지르는 직선이 소리 없이 생긴다.
            self.get_logger().warn(
                f'경로표에 {self._here} → {zone.zone_id} 쌍이 없다. 곧장 간다 — '
                '따져 본 적 없는 직선이다. 빈 목록으로 적어 두면 이 줄은 사라진다.')
        goal = (zone.x, zone.y, zone.yaw)
        index = 0
        settled_at = None
        turning_logged = False
        turn_started = None   # turn_first: 접근점에서 제자리 회전을 시작한 sim 시각
        slide_logged = False
        arrive_yaw = min(zone.tol_yaw, self._follower.arrive_yaw)
        #: 가속 상한의 기준이 되는 직전 명령(world (vx, vy), wz). 빈월드 backend 는 목표마다 정지에서 시작한다.
        #: nav2 final approach(`path` 를 줌)는 Nav2 를 거둔 직후라 아직 움직인다 — 지금 속도에서 줄여 간다.
        previous = REST
        if explicit and observation_fresh(self._odom_age_s(), self._odom_timeout):
            previous = moving_start(self._odom_twist, self._current_pose())
            speed = math.hypot(*previous[0])
            if speed > self._linear_tol:
                self.get_logger().info(
                    f'{zone.zone_id}: 추종기가 움직이는 채로 넘겨받는다({speed:.2f} m/s, {previous[1]:.2f} rad/s). '
                    f'가속 상한 {self._follower.max_accel} m/s² 로 줄여 간다.')
        self.get_logger().info(
            f'{self._here} → {zone.zone_id}: waypoint {len(path)}개를 따라간다'
            f'(backend={WAYPOINTS if not explicit else "nav2+final_approach"}).')
        while True:
            if not self.context.ok():
                # 종료 중이다(SIGINT). 더 내지 않고 조용히 끝낸다. 실습29 down 에서 여기서
                # publish 하다 InvalidHandle 이 났다 — 종료는 실패가 아니다.
                self.get_logger().info('종료 중이다. 추종을 멈춘다.')
                return self._finish(goal_handle, 'canceled')
            if self._closed_outcome() is not None:
                self._publish_zero_velocity()
                return self._finish(goal_handle, self._closed_outcome())
            pose = self._current_pose()
            command = follow(pose, path, index, goal, zone.tol_xy, zone.tol_yaw, self._follower,
                             previous=previous, dt=self._follower_period, turn_first=explicit)
            index = command.index
            previous = (command.world, command.wz)
            if command.reason is not None:
                self.get_logger().warn(f'추종 정지: {command.reason}', throttle_duration_sec=5.0)
            if not self._publish_cmd_vel(
                    Twist(linear=Vector3(x=command.vx, y=command.vy), angular=Vector3(z=command.wz))):
                return self._finish(goal_handle, 'canceled')
            if explicit and pose is not None and index >= len(path) and not slide_logged:
                # 접근점에서 도는 시간과 옆걸음 시작을 남긴다. 회전이 어디서 끝났는지가 이 exp 의 판정선이다.
                distance, angle = pose_error(pose, goal)
                if turn_started is None and angle > arrive_yaw:
                    turn_started = self._sim_now()
                    self.get_logger().info(
                        f'{zone.zone_id} 접근점 ({pose[0]:.3f}, {pose[1]:.3f}) 에서 제자리로 yaw 를 맞춘다'
                        f'({pose[2]:.3f} → {zone.yaw:.3f} rad).')
                elif angle <= arrive_yaw:
                    slide_logged = True
                    took = 0.0 if turn_started is None else self._sim_now() - turn_started
                    self.get_logger().info(
                        f'{zone.zone_id} yaw 맞춤 끝({took:.1f} s sim). 정차 자리까지 {distance:.3f} m 옆걸음.')
            if (pose is not None and not command.arrived and index >= len(path)
                    and pose_error(pose, goal)[0] <= zone.tol_xy and not turning_logged):
                # 마지막 구간: 자리는 잡았고 yaw 만 돈다. feedback 의 distance_remaining 이 0 근처에서
                # 멈추는 구간이라, 이 줄이 없으면 "회전 중" 과 "멈춤" 을 로그로 가를 수 없다. goal 당 한 번.
                turning_logged = True
                self.get_logger().info(
                    f'{zone.zone_id} 자리 도착. yaw 만 맞춘다(목표 {zone.yaw:.3f} rad).')
            if command.arrived:
                if settled_at is None:
                    settled_at = self._sim_now()
                if settle_ok(self._quiet_for, self._quiet_hold,
                             self._odom_age_s(), self._odom_timeout):
                    self._here = zone.zone_id
                    return self._finish(goal_handle, 'arrived')
                if self._sim_now() - settled_at > self._settle_timeout:
                    reason = ('stale_odom' if not observation_fresh(
                        self._odom_age_s(), self._odom_timeout) else 'not_stopped')
                    return self._finish(goal_handle, reason)
            else:
                settled_at = None
            if pose is not None:
                distance = pose_error(pose, goal)[0]
                goal_handle.publish_feedback(GoToZone.Feedback(distance_remaining=float(distance)))
            time.sleep(self._follower_period)

    def _publish_zero_velocity(self):
        """추종을 끝낼 때 0 을 낸다. 명령이 끊기면 base_driver 도 0 을 내지만(계약 5절) 먼저 세운다."""
        self._publish_cmd_vel(Twist())

    def _publish_cmd_vel(self, twist):
        """cmd_vel 을 낸다. 종료 중이면 False. 내려가는 중의 publish 는 예외를 던진다."""
        if self._cmd_vel_publisher is None:
            return False
        try:
            self._cmd_vel_publisher.publish(twist)
        except InvalidHandle:
            return False
        return True

    def _finish(self, goal_handle, message):
        """계약 2.2절: 도착이 아니면 abort 이고 arrived=false 다.

        종료 중에는 goal 상태를 바꾸는 것도 InvalidHandle 을 던진다. 그때도 결과는 돌려준다
        (종료는 실패가 아니다. 실습29 down 에서 여기서 예외가 났다).
        """
        if message is None:
            # 종료 중(SIGINT)에는 guard 가 닫히지 않은 채 결과 대기를 끝낸다 — 닫힌 이유가 없다. 결과의 message 는
            # string 이라 None 을 넣으면 rosidl 변환이 assert 로 프로세스를 죽인다(병원 L3 5회차 down, exit -6).
            message = 'canceled' if self._shutting_down() else 'nav2_no_result'
        # 종료 중에는 goal 상태를 바꾸는 것도 InvalidHandle 이나 rcl 오류("feedback publisher is invalid")를 던진다
        # (병원 L3 1회차 down 의 Traceback). 결과는 그대로 돌려준다.
        with contextlib.suppress(InvalidHandle, _RCL_ERROR):
            if message == 'arrived':
                goal_handle.succeed()
                return GoToZone.Result(arrived=True, message='arrived')
            if message == 'canceled' and goal_handle.is_cancel_requested:
                goal_handle.canceled()
                return GoToZone.Result(arrived=False, message='canceled')
            self.get_logger().warn(f'GoToZone {goal_handle.request.zone_id} 실패: {message}')
            goal_handle.abort()
        return GoToZone.Result(arrived=False, message=message)

    def _on_nav_feedback(self, goal_handle, message, staging=None):
        with contextlib.suppress(InvalidHandle, _RCL_ERROR):
            goal_handle.publish_feedback(
                GoToZone.Feedback(distance_remaining=float(message.feedback.distance_remaining)))
        if staging is None or self._handoff_requested:
            return
        position = message.feedback.current_pose.pose.position
        nav_goal_handle = self._nav_goal_handle
        away = math.hypot(position.x - staging[0], position.y - staging[1])
        if nav_goal_handle is None or away > self._handoff_radius:
            return
        # 접근점 가까이서 Nav2 가 고정물 옆 비용에 걸려 제자리에 머무는 것을 기다리지 않는다.
        self._handoff_requested = True
        self.get_logger().info(
            f'접근점 ({staging[0]:.3f}, {staging[1]:.3f}) {self._handoff_radius:.2f} m 안이다. Nav2 goal 을 거둔다.')
        nav_goal_handle.cancel_goal_async()

    def _near(self, point):
        """지금 자세(map TF)가 `point` 에서 넘김 반경 안이다. 자세를 모르면 아니다."""
        pose = self._current_pose()
        return pose is not None and math.hypot(pose[0] - point[0], pose[1] - point[1]) <= self._handoff_radius

    # -- 주기 동작 --------------------------------------------------------

    def _tick(self):
        """5 Hz(wall). base/stopped 발행, 제한 시간, 도착 판정."""
        if not observation_fresh(self._odom_age_s(), self._odom_timeout):
            self._quiet_for = 0.0
        self._poll_costmap_clear()
        self._publish_stopped()
        self._publish_docking_state()
        self._enforce_deadline()
        self._check_settled()

    def _odom_age_s(self):
        """마지막 odom 수신 뒤 wall 경과(s). 한 번도 없으면 None."""
        return None if self._odom_at is None else time.monotonic() - self._odom_at

    def _publish_stopped(self):
        """odom 이 1.0 s 없으면 아무것도 내지 않는다. 받는 쪽에서 unknown 이 된다(계약 2절 H)."""
        if not observation_fresh(self._odom_age_s(), self._odom_timeout):
            return
        self._stopped_publisher.publish(
            Bool(data=base_stopped(self._accepted, self._quiet_for, self._quiet_hold)))

    def _enforce_deadline(self):
        goal_handle = self._goal_handle
        if goal_handle is None or self._outcome is not None:
            return
        if goal_handle.is_cancel_requested:
            self._close_nav('취소 요청', 'canceled')
        elif self._deadline is not None and self._sim_now() > self._deadline:
            self._close_nav('제한 시간', 'timeout')

    def _close_nav(self, reason, outcome):
        """진행 중인 Nav2 goal 을 취소해 실행 중인 goal 을 끝낸다."""
        self._outcome = outcome
        self._guard.close(outcome, time.monotonic())
        self.get_logger().warn(f'Nav2 goal 취소: {reason}')
        if self._nav_goal_handle is not None:
            self._nav_goal_handle.cancel_goal_async()
        self._settle_message = outcome
        self._settle_event.set()

    def _closed_outcome(self):
        """닫힌 이유. RESET_DONE 은 guard 를 먼저 닫으므로 `_outcome` 이 아직 없을 수 있다."""
        return self._outcome or self._guard.reason

    def _cancel_wait_expired(self):
        """닫기 시작한 뒤 cancel 종결 대기(계약 7절 10 s wall)가 지났는가. **종료 중이면 곧바로 참이다.**

        SIGINT 로 컨텍스트가 내려가면 Nav2 도 같이 내려가 결과가 오지 않는다. 그때 계속 기다리면 실행 스레드가
        안 끝나 executor 가 내려가지 못하고 SIGTERM 에도 버티다 SIGKILL 된다(병원 L3 2회차 9/23).
        """
        return self._shutting_down() or self._guard.expired(time.monotonic())

    def _shutting_down(self):
        return not self.context.ok()

    def _cancel_if_late(self, token, future):
        """결과 없이 끝낸 goal 이 늦게 수락되면 취소한다."""
        nav_goal_handle = future.result()
        if nav_goal_handle is not None and nav_goal_handle.accepted \
                and self._guard.on_accepted(token) == CANCEL:
            self.get_logger().warn('끝낸 GoToZone 의 Nav2 goal 이 늦게 수락됐다. 취소한다.')
            nav_goal_handle.cancel_goal_async()

    def _check_settled(self):
        """Nav2 가 끝난 뒤 허용오차 안에서 멈췄는지 본다.

        캐시된 목표 자세와 과거 정지 누적만으로는 arrived 가 아니다. odom 이
        `odom_timeout_s` 안에 있어야 하고, 그 연속 구간에서만 정지를 센다.
        """
        goal_handle = self._goal_handle
        if self._settle_deadline is None or goal_handle is None or self._settle_event.is_set():
            return
        zone = self._zones.zones[goal_handle.request.zone_id]
        current = self._current_pose()
        target = (zone.x, zone.y, zone.yaw)
        odom_age = self._odom_age_s()
        if (current is not None
                and settle_ok(self._quiet_for, self._quiet_hold, odom_age, self._odom_timeout)
                and docked(current, target, zone.tol_xy, zone.tol_yaw)):
            self._settle_message = 'arrived'
            self._settle_event.set()
            return
        if self._sim_now() <= self._settle_deadline:
            return
        if current is None:
            self._settle_message = 'no_pose'
        elif not observation_fresh(odom_age, self._odom_timeout):
            self._settle_message = 'stale_odom'
        else:
            distance, angle = pose_error(current, target)
            self.get_logger().warn(
                f'{zone.zone_id} 도착 판정 실패: 거리 {distance:.3f} m (tol {zone.tol_xy}), '
                f'각 {angle:.3f} rad (tol {zone.tol_yaw}), 정지 {self._quiet_for:.2f} s')
            self._settle_message = (
                'not_stopped' if self._quiet_for < self._quiet_hold else 'out_of_tolerance')
        self._settle_event.set()

    # -- 보조 ------------------------------------------------------------

    def _sim_now(self):
        """sim time 초. 액션 제한 시간은 sim time 이다(계약 4절)."""
        return self.get_clock().now().nanoseconds * 1e-9

    def _zone_pose(self, zone, at=None):
        """zone 자세. `at` 을 주면 자리만 그 (x, y) 로 바꾸고 yaw 는 zone 것을 쓴다(접근점)."""
        pose = PoseStamped()
        pose.header.frame_id = self._zones.frame
        pose.header.stamp = self.get_clock().now().to_msg()
        pose.pose.position.x = zone.x if at is None else float(at[0])
        pose.pose.position.y = zone.y if at is None else float(at[1])
        (pose.pose.orientation.x, pose.pose.orientation.y,
         pose.pose.orientation.z, pose.pose.orientation.w) = yaw_to_quaternion(zone.yaw)
        return pose

    def _publish_docking_state(self):
        """계약 11.6. 판정은 `docking_state.judge` 다. `publish_docking_state` 를 켰을 때만 낸다."""
        if self._docked_publisher is None:
            return
        zone = pose = amcl_age = None
        if self._zones is not None:
            zone = self._zones.zones.get(self._docking_zone_id)
            pose = self._current_pose()
            amcl_age = self._amcl_age()
        odom_age = None if self._odom_at is None else time.monotonic() - self._odom_at
        judgement = judge(
            epoch_known=self._guard.epoch is not None, goal_active=self._accepted, zone=zone, pose=pose,
            odom_age_s=odom_age, odom_timeout_s=self._odom_timeout,
            amcl_age_s=amcl_age, amcl_max_age_s=self._amcl_max_age)
        epoch = self._guard.epoch if self._guard.epoch is not None else EPOCH_BEFORE_RESET
        message = DockingState(
            epoch=epoch, seq=self._docking_seq.advance(epoch, self._odom_stamp), docking=judgement.docking,
            zone_id=self._docking_zone_id or '',
            error_xy=float(judgement.error_xy), error_yaw=float(judgement.error_yaw))
        if self._odom_stamp is not None:
            message.header.stamp = Time(nanoseconds=int(self._odom_stamp * 1e9)).to_msg()
        self._docked_publisher.publish(message)

    def _amcl_age(self):
        """map -> odom(AMCL) 변환이 sim time 으로 얼마나 오래됐나(s). 없으면 None."""
        try:
            transform = self._tf_buffer.lookup_transform(self._zones.frame, self._odom_frame, Time())
        except TransformException:
            return None
        stamp = transform.header.stamp.sec + transform.header.stamp.nanosec * 1e-9
        return max(0.0, self._sim_now() - stamp)

    def _current_pose(self):
        """map -> base_link 를 TF 로 본다. AMCL 이 없으면 None 이다."""
        try:
            transform = self._tf_buffer.lookup_transform(
                self._zones.frame, self._base_frame, Time())
        except TransformException as exc:
            self.get_logger().warn(f'{self._zones.frame} -> {self._base_frame} TF 가 없다: {exc}',
                                   throttle_duration_sec=2.0)
            return None
        rotation = transform.transform.rotation
        return (transform.transform.translation.x, transform.transform.translation.y,
                quaternion_to_yaw(rotation.x, rotation.y, rotation.z, rotation.w))

    def _publish_initialpose(self):
        """리셋 뒤 AMCL 을 도크 자세로 되돌린다(계약 6절 4단계)."""
        if self._zones is None or self._dock_zone not in self._zones.zones:
            self.get_logger().error(
                f'도크 구역 {self._dock_zone} 이 zones.yaml 에 없다. initialpose 생략.')
            return False
        zone = self._zones.zones[self._dock_zone]
        message = PoseWithCovarianceStamped()
        message.header.frame_id = self._zones.frame
        message.header.stamp = self.get_clock().now().to_msg()
        message.pose.pose.position.x = zone.x
        message.pose.pose.position.y = zone.y
        (message.pose.pose.orientation.x, message.pose.pose.orientation.y,
         message.pose.pose.orientation.z,
         message.pose.pose.orientation.w) = yaw_to_quaternion(zone.yaw)
        message.pose.covariance[0] = self._cov_xy
        message.pose.covariance[7] = self._cov_xy
        message.pose.covariance[35] = self._cov_yaw
        self._initialpose_publisher.publish(message)
        return True

    def _start_costmap_clear(self, epoch):
        """`initialpose` 뒤 global/local costmap clear를 예약한다. 서비스 대기로 tick을 막지 않는다."""
        if not self._costmap_clear_clients:
            return
        for future in self._costmap_clear_pending.values():
            if future is not None and not future.done():
                future.cancel()
        self._costmap_clear_epoch = epoch
        self._costmap_clear_deadline = time.monotonic() + self._costmap_clear_wait
        self._costmap_clear_pending = dict.fromkeys(self._costmap_clear_clients)
        self._poll_costmap_clear()

    def _poll_costmap_clear(self):
        """준비된 clear 서비스는 한 번 호출하고, 부재·무응답은 wall 시한 뒤 WARN으로 닫는다."""
        if self._costmap_clear_epoch is None:
            return
        now = time.monotonic()
        for name, future in list(self._costmap_clear_pending.items()):
            client = self._costmap_clear_clients[name]
            if future is None and client.service_is_ready():
                self._costmap_clear_pending[name] = client.call_async(ClearEntireCostmap.Request())
                continue
            if future is not None and future.done():
                try:
                    future.result()
                    self.get_logger().info(
                        f'RESET_DONE epoch {self._costmap_clear_epoch}: {name} costmap clear 완료.')
                except Exception as exc:  # rclpy future가 서비스 예외를 전달한다
                    self.get_logger().warn(
                        f'RESET_DONE epoch {self._costmap_clear_epoch}: '
                        f'{name} costmap clear 실패: {exc}')
                del self._costmap_clear_pending[name]
                continue
            if now >= self._costmap_clear_deadline:
                state = '서비스 없음' if future is None else '응답 없음'
                self.get_logger().warn(
                    f'RESET_DONE epoch {self._costmap_clear_epoch}: '
                    f'{name} costmap clear {state} ({self._costmap_clear_wait:g} s wall).')
                if future is not None:
                    future.cancel()
                del self._costmap_clear_pending[name]
        if not self._costmap_clear_pending:
            self._costmap_clear_epoch = None
            self._costmap_clear_deadline = None


try:  # rcl 이 내는 예외 타입. rclpy 가 공개 이름으로 내보내지 않아 구현 모듈에서 가져온다.
    from rclpy.impl.implementation_singleton import rclpy_implementation as _rclpy_impl
    _RCL_ERROR = getattr(_rclpy_impl, 'RCLError', RuntimeError)
except ImportError:  # pragma: no cover - rclpy 가 없으면 이 노드 자체가 안 뜬다
    _RCL_ERROR = RuntimeError


def _wait_for(future, give_up=None, poll_s=0.1):
    """executor 를 막지 않고 future 를 기다린다. 결과 콜백은 다른 스레드가 처리한다.

    `give_up()` 이 참이 되면 기다리기를 그만두고 None 을 돌려준다.
    """
    done = threading.Event()
    future.add_done_callback(lambda _: done.set())
    while not done.wait(timeout=poll_s):
        if give_up is not None and give_up():
            return None
    return future.result()


#: executor 스레드 하한. 실행 콜백(Nav2 결과 대기)이 스레드 하나를 잡는 동안 tick 이 돌 스레드가 하나 더 있어야 한다.
#: 2 는 #293 의 L2(스레드 2개에서 취소가 10 s 안에 종결)가 확인한 값이다.
MIN_EXECUTOR_THREADS = 2


def executor_threads(cpu_count):
    """CPU 수를 따르되 하한 2. 코어가 많은 호스트는 전과 같고, 1 코어 호스트만 2 가 된다."""
    return max(MIN_EXECUTOR_THREADS, cpu_count or MIN_EXECUTOR_THREADS)


def main(args=None):
    """콘솔 진입점. 액션 서버가 액션 클라이언트를 기다리므로 멀티스레드 executor 를 쓴다."""
    rclpy.init(args=args)
    node = FleetNode()
    executor = MultiThreadedExecutor(num_threads=executor_threads(os.cpu_count()))
    executor.add_node(node)
    try:
        executor.spin()
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
