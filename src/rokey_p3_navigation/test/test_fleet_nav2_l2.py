"""L2. fleet 과 fake Nav2(`NavigateToPose` 서버)로 결함 후보 F1·F2 를 재현한다. 계약 v1 6절·7절.

- test_cancel_while_nav2_is_slow_to_accept: GoToZone 을 취소했는데 Nav2 수락 응답이 늦게 온다.
  수락되는 즉시 Nav2 goal 에 cancel 이 가고, GoToZone 은 canceled 로 끝난다(F1).
- test_unanswered_cancel_still_ends_the_goal: Nav2 가 cancel 을 거절하고 goal 도 끝내지 않는다.
  GoToZone 은 cancel 종결 대기(계약 7절 10 s wall) 뒤에 끝나고, 다음 GoToZone 을 받는다(F2).
- test_acceptance_after_giving_up_is_canceled: 수락 응답이 cancel 종결 대기보다 늦게 온다.
  GoToZone 은 먼저 끝나고, 늦게 수락된 Nav2 goal 에도 cancel 이 간다(F1·F2).
- test_reset_done_while_waiting_for_the_nav2_server: Nav2 서버가 뜨기 전에 RESET_DONE 이 온다.
  서버가 뜬 뒤에도 Nav2 goal 을 보내지 않고, GoToZone 은 reset 으로 끝난다(F1).

cancel 종결 대기는 계약값 10 s 를 그대로 쓴다. 시험 시간을 줄이려고 값을 바꾸지 않는다(이 파일 전체 약 70 s).
CI 는 패키지 시험을 순서대로(--executor sequential) 돌리고 발견 범위를 LOCALHOST 로 좁힌다.
그 위에서 시험마다 전용 네임스페이스를 써서 다른 시험의 노드·액션과 이름이 겹치지 않게 한다.
`/events` 는 계약상 전역 이름이라 네임스페이스를 붙이지 않는다.
"""

import importlib.util
import math
import os
import pathlib
import threading
import time
from itertools import pairwise

import pytest
import yaml

from rokey_p3_navigation.goal_guard import CANCEL_WAIT_S

# 모듈 수준 importorskip 을 쓰지 않는다(test_fleet_wait.py 주석 참고). 표시만 하고 import 는 있을 때만 한다.
NAV2_MISSING = importlib.util.find_spec('nav2_msgs') is None
pytestmark = pytest.mark.skipif(NAV2_MISSING, reason='CI 에 nav2_msgs 미설치 — fleet L2(F1·F2) 미실행')

if not NAV2_MISSING:
    import rclpy
    from action_msgs.msg import GoalStatus
    from geometry_msgs.msg import PoseWithCovarianceStamped, TransformStamped, Twist
    from nav2_msgs.action import NavigateToPose
    from nav2_msgs.srv import ClearEntireCostmap
    from rclpy.action import ActionClient, ActionServer, CancelResponse, GoalResponse
    from rclpy.callback_groups import ReentrantCallbackGroup
    from rclpy.executors import MultiThreadedExecutor
    from rclpy.node import Node
    from rclpy.time import Time
    from std_msgs.msg import Bool

    from rokey_p3_interfaces.action import GoToZone
    from nav_msgs.msg import Odometry
    from tf2_ros import TransformBroadcaster

    from rokey_p3_interfaces.msg import DockingState, Event
    from rokey_p3_navigation.base_kinematics import body_to_world_velocity, quaternion_to_yaw, yaw_to_quaternion
    from rokey_p3_navigation.fleet_node import FleetNode
    from rokey_p3_navigation.qos_profiles import HEARTBEAT, RELIABLE
else:
    Node = object  # 건너뛸 때 아래 클래스 정의만 통과시킨다

ZONES = """frame: map
zones:
  load:   {kind: load, x: 1.0, y: 0.0, yaw: 0.0, tol_xy: 0.05, tol_yaw: 0.05}
  dock_1: {kind: dock, x: 0.0, y: 0.0, yaw: 0.0, tol_xy: 0.10, tol_yaw: 0.10}
  door_a1: {kind: door, x: 2.0, y: 0.0, yaw: 0.0, tol_xy: 0.10, tol_yaw: 0.10}
"""

#: fleet 은 5 Hz(wall) tick 에서 취소를 보고, 결과 대기는 0.1 s 마다 마감을 본다.
#: 상한은 그 두 주기(0.3 s)에 액션 왕복과 CI 러너의 스케줄 지연을 넉넉히 더한 값이다.
#: 하한은 두지 않는다. 마감은 닫기 시작한 시각부터 재므로 취소 요청 시각보다 이르게 끝날 수 없다.
SLACK_S = 5.0
#: 빈월드 대역은 완전 추종이라 빨리 간다. 상한은 거리(약 1 m)와 가속 자른 속도에 여유를 더한 값이다.
DRIVE_TIMEOUT_S = 25.0
#: Nav2 수락 응답이 늦게 오는 시간. 취소(1 s)보다 늦고 cancel 종결 대기보다 이르다.
SLOW_ACCEPT_S = 3.0
#: 포기한 뒤에 수락되도록, 취소(1 s) + cancel 종결 대기(10 s) 뒤에 수락한다.
LATE_ACCEPT_S = 1.0 + CANCEL_WAIT_S + 2.0
CANCEL_AFTER_S = 1.0


class FakeNav2(Node):
    """`<ns>/navigate_to_pose` 서버. 수락 지연·cancel 응답을 시험마다 정한다. 끝까지 가지 않는다."""

    def __init__(self, namespace, accept_delay_s=0.0, answer_cancel=True):
        super().__init__('fake_nav2', namespace=namespace)
        self.accept_delay_s = accept_delay_s
        self.answer_cancel = answer_cancel
        self.goals = []      # 수락 요청을 받은 wall 시각
        self.cancels = []    # cancel 요청을 받은 wall 시각
        self.stop = threading.Event()
        self.server = ActionServer(
            self, NavigateToPose, 'navigate_to_pose',
            execute_callback=self._execute, goal_callback=self._on_goal,
            cancel_callback=self._on_cancel, callback_group=ReentrantCallbackGroup())

    def _on_goal(self, goal):
        self.goals.append(time.monotonic())
        time.sleep(self.accept_delay_s)
        return GoalResponse.ACCEPT

    def _on_cancel(self, goal_handle):
        self.cancels.append(time.monotonic())
        return CancelResponse.ACCEPT if self.answer_cancel else CancelResponse.REJECT

    def _execute(self, goal_handle):
        while not self.stop.is_set():
            if goal_handle.is_cancel_requested:
                goal_handle.canceled()
                return NavigateToPose.Result()
            time.sleep(0.05)
        goal_handle.abort()
        return NavigateToPose.Result()


class Driver(Node):
    """orchestrator 대역: GoToZone 클라이언트, arm/at_home heartbeat, /events 발행."""

    def __init__(self, namespace):
        super().__init__('l2_driver', namespace=namespace)
        self.client = ActionClient(self, GoToZone, f'/{namespace}/go_to_zone',
                                   callback_group=ReentrantCallbackGroup())
        self._at_home = self.create_publisher(Bool, f'/{namespace}/arm/at_home', HEARTBEAT)
        self._events = self.create_publisher(Event, '/events', RELIABLE)
        self.initialposes = []
        self.stopped = []
        self.create_subscription(
            PoseWithCovarianceStamped, f'/{namespace}/initialpose', self.initialposes.append, RELIABLE)
        self.create_subscription(Bool, f'/{namespace}/base/stopped', self.stopped.append, HEARTBEAT)
        self.create_timer(0.2, lambda: self._at_home.publish(Bool(data=True)))

    def reset_done(self, epoch):
        self._events.publish(Event(name='RESET_DONE', epoch=epoch))


class FakeCostmaps(Node):
    """Nav2 global/local costmap clear 서비스 대역. 호출 시각과 선택적 응답 지연을 기록한다."""

    def __init__(self, namespace, delay_s=0.0):
        super().__init__('fake_costmaps', namespace=namespace)
        self.delay_s = delay_s
        self.calls = []
        callbacks = ReentrantCallbackGroup()
        self.create_service(
            ClearEntireCostmap, 'global_costmap/clear_entirely_global_costmap',
            lambda request, response: self._clear('global', response), callback_group=callbacks)
        self.create_service(
            ClearEntireCostmap, 'local_costmap/clear_entirely_local_costmap',
            lambda request, response: self._clear('local', response), callback_group=callbacks)

    def _clear(self, name, response):
        self.calls.append((name, time.monotonic()))
        time.sleep(self.delay_s)
        return response


class FakeWorld(Node):
    """빈월드 대역: `cmd_vel` 을 받아 자세를 적분하고 `odom` 과 TF `map`→`base_link` 를 낸다.

    Isaac 과 `base_driver` 가 할 일을 시험 안에서 대신한다. 물리는 없다(완전 추종).
    """

    PERIOD = 0.05

    def __init__(self, namespace, start=(0.0, 0.0, 0.0)):
        super().__init__('fake_world', namespace=namespace)
        self.pose = list(start)
        self.track = [tuple(self.pose)]
        self._command = (0.0, 0.0, 0.0)
        #: 받은 cmd_vel 전부. 가속 상한을 보려면 자세가 아니라 **명령**을 봐야 한다.
        self.commands = []
        self._stamp = 0.0
        self.create_subscription(Twist, f'/{namespace}/cmd_vel', self._on_cmd_vel, RELIABLE)
        self._odom = self.create_publisher(Odometry, f'/{namespace}/odom', RELIABLE)
        self._tf = TransformBroadcaster(self)
        self._frame = f'{namespace}/base_link'
        self.create_timer(self.PERIOD, self._step)

    def _on_cmd_vel(self, msg):
        self._command = (msg.linear.x, msg.linear.y, msg.angular.z)
        self.commands.append(self._command)

    def first_moving_command(self, timeout_s=5.0):
        """0 이 아닌 첫 명령. 없으면 None."""
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            for command in list(self.commands):
                if math.hypot(command[0], command[1]) > 0.0:
                    return command
            time.sleep(0.02)
        return None

    def _step(self):
        dx, dy, dyaw = body_to_world_velocity(*self._command, self.pose[2])
        self.pose[0] += dx * self.PERIOD
        self.pose[1] += dy * self.PERIOD
        self.pose[2] += dyaw * self.PERIOD
        self.track.append(tuple(self.pose))
        self._stamp += self.PERIOD
        stamp = Time(nanoseconds=int(self._stamp * 1e9)).to_msg()

        odom = Odometry()
        odom.header.stamp = stamp
        odom.twist.twist.linear.x, odom.twist.twist.linear.y = self._command[0], self._command[1]
        odom.twist.twist.angular.z = self._command[2]
        self._odom.publish(odom)

        transform = TransformStamped()
        transform.header.stamp = stamp
        transform.header.frame_id = 'map'
        transform.child_frame_id = self._frame
        transform.transform.translation.x = self.pose[0]
        transform.transform.translation.y = self.pose[1]
        (transform.transform.rotation.x, transform.transform.rotation.y,
         transform.transform.rotation.z,
         transform.transform.rotation.w) = yaw_to_quaternion(self.pose[2])
        self._tf.sendTransform(transform)


class Rig:
    """노드마다 따로 executor 를 돌린다. 실제로는 fleet·Nav2·orchestrator 가 서로 다른 프로세스다.

    한 executor 에 모두 넣으면 fleet 의 실행 콜백(Nav2 결과 대기)과 fake Nav2 의 실행 루프·수락 지연이
    스레드를 하나씩 붙잡는다. 기본 스레드 수는 CPU 수라서 2 코어 러너에서는 fleet 의 5 Hz tick 이 돌 스레드가 없다.
    #258 의 첫 CI(run 35454654056)가 그랬다: 취소한 GoToZone 을 fleet 이 teardown 에서 fake 루프가 끝난 뒤에야 봤다.
    fleet 의 executor 는 `fleet_node.main` 과 같은 기본값(`MultiThreadedExecutor()`)을 쓴다.
    """

    def __init__(self, namespace, tmp_path, fleet_threads=None, fleet_params=None):
        zones = tmp_path / 'zones.yaml'
        zones.write_text(ZONES, encoding='utf-8')
        params = tmp_path / 'fleet.yaml'
        params.write_text(
            f'fleet:\n  ros__parameters:\n    robot_namespace: {namespace}\n'
            f'    zones_file: {zones}\n    dock_zone: dock_1\n'
            + ''.join(f'    {name}: {value}\n' for name, value in (fleet_params or {}).items()), encoding='utf-8')
        rclpy.init(args=['--ros-args', '--params-file', str(params)])
        try:
            self._build(namespace, fleet_threads)
        except Exception:
            # 노드 생성이 깨지면 rclpy 를 내려 둔다. 안 그러면 다음 시험의 init 이
            # "Context.init() must only be called once" 로 같이 깨져 원인이 가려진다.
            rclpy.try_shutdown()
            raise

    def _build(self, namespace, fleet_threads):
        self.namespace = namespace
        self.fleet = FleetNode()
        self.driver = Driver(namespace)
        self.nav2 = None
        self.world = None
        self.costmaps = None
        self.executors = {'fleet': MultiThreadedExecutor(num_threads=fleet_threads),
                          'driver': MultiThreadedExecutor(num_threads=2),
                          'nav2': MultiThreadedExecutor(num_threads=4)}
        self.executors['fleet'].add_node(self.fleet)
        self.executors['driver'].add_node(self.driver)
        self.threads = [threading.Thread(target=executor.spin, daemon=True)
                        for executor in self.executors.values()]
        for thread in self.threads:
            thread.start()

    def start_world(self, **kwargs):
        """빈월드 대역을 띄운다. waypoints backend 시험에서만 쓴다."""
        self.world = FakeWorld(self.namespace, **kwargs)
        self.executors['nav2'].add_node(self.world)
        return self.world

    def start_nav2(self, **kwargs):
        self.nav2 = FakeNav2(self.namespace, **kwargs)
        self.executors['nav2'].add_node(self.nav2)
        return self.nav2

    def start_costmaps(self, **kwargs):
        self.costmaps = FakeCostmaps(self.namespace, **kwargs)
        self.executors['nav2'].add_node(self.costmaps)
        return self.costmaps

    def wait_ready(self, timeout_s=10.0):
        """go_to_zone 서버가 보이고 fleet 이 at_home 을 받았다."""
        assert self.driver.client.wait_for_server(timeout_sec=timeout_s), 'go_to_zone 서버가 안 보인다'
        _until(lambda: self.fleet._at_home is True, timeout_s, 'fleet 이 arm/at_home 을 못 받았다')

    def send(self, zone_id='load', accepted=True):
        future = self.driver.client.send_goal_async(GoToZone.Goal(zone_id=zone_id))
        _until(future.done, 5.0, 'GoToZone 수락 응답이 없다')
        handle = future.result()
        assert handle.accepted == accepted, f'GoToZone {zone_id} 수락 여부가 {accepted} 가 아니다'
        return handle

    def close(self):
        if self.nav2 is not None:
            self.nav2.stop.set()
        nodes = [node for node in (self.nav2, self.world, self.costmaps, self.driver, self.fleet)
                 if node is not None]
        if self.fleet is not None:
            try:
                _until(lambda: not self.fleet._accepted, 5.0, 'fleet 의 GoToZone 이 안 끝났다')
            except AssertionError:
                # 싣는 가속으로 yaw 맞춤이 5 s 를 넘기면 teardown 이 먼저 깨진다(CI #453).
                if self.driver is not None:
                    self.driver.reset_done(epoch=99)
                _until(lambda: not self.fleet._accepted, DRIVE_TIMEOUT_S,
                       'fleet 의 GoToZone 이 리셋 뒤에도 안 끝났다')
        for executor in self.executors.values():
            executor.shutdown(timeout_sec=5.0)
        for thread in self.threads:
            thread.join(timeout=5.0)
        for node in nodes:
            for entity in list(node.waitables):
                if isinstance(entity, (ActionServer, ActionClient)):
                    entity.destroy()
            node.destroy_node()
        rclpy.try_shutdown()


def _until(condition, timeout_s, message):
    deadline = time.monotonic() + timeout_s
    while not condition():
        if time.monotonic() > deadline:
            raise AssertionError(message)
        time.sleep(0.02)


def _result(handle, timeout_s):
    """(status, message, 받은 wall 시각)."""
    future = handle.get_result_async()
    _until(future.done, timeout_s,
           f'{timeout_s:g} s 안에 GoToZone 결과가 오지 않았다(os.cpu_count={os.cpu_count()})')
    response = future.result()
    return response.status, response.result.message, time.monotonic()


@pytest.fixture
def rig(request, tmp_path):
    rig = Rig(f'l2_fleet_{request.node.name.split("[")[0]}', tmp_path)
    yield rig
    rig.close()


#: 코어가 적은 호스트를 흉내 낸다. fleet 의 실행 콜백(결과 대기)이 스레드 하나를 잡으면
#: tick·액션 서버·구독·Nav2 클라이언트 응답이 남은 하나를 나눠 쓴다.
TWO_THREADS = 2


@pytest.fixture
def rig_docking(request, tmp_path):
    # 이 시험은 fake Nav2 를 띄우지 않는다. 기본값(10 s)이면 fleet 이 서버를 그만큼 기다린 뒤에야
    # 리셋으로 끝난다. 리셋이 wait_for_server 시작보다 앞서면 결과는 반드시 "리셋 + 10 s" 를 넘고,
    # 시험의 대기 상한도 10 s 라 구조적으로 실패한다(run 35554210889: 리셋 + 10.028 s, 40 ms 초과).
    # 기다리는 시간만 줄인다. "리셋이 goal 을 끝낸다"는 기대는 그대로다.
    rig = Rig(f'l2_fleet_{request.node.name.split("[")[0]}', tmp_path,
              fleet_params={'publish_docking_state': 'true', 'nav2_server_wait_s': 2.0})
    yield rig
    rig.close()


@pytest.fixture
def rig_two_threads(request, tmp_path):
    rig = Rig(f'l2_fleet_{request.node.name.split("[")[0]}', tmp_path, fleet_threads=TWO_THREADS)
    yield rig
    rig.close()


def test_cancel_while_nav2_is_slow_to_accept(rig):
    _cancel_while_nav2_is_slow_to_accept(rig)


def test_cancel_while_nav2_is_slow_to_accept_on_two_fleet_threads(rig_two_threads):
    _cancel_while_nav2_is_slow_to_accept(rig_two_threads)


def _cancel_while_nav2_is_slow_to_accept(rig):
    nav2 = rig.start_nav2(accept_delay_s=SLOW_ACCEPT_S)
    rig.wait_ready()
    handle = rig.send()
    time.sleep(CANCEL_AFTER_S)
    handle.cancel_goal_async()

    status, message, _ = _result(handle, SLOW_ACCEPT_S + SLACK_S)
    assert (status, message) == (GoalStatus.STATUS_CANCELED, 'canceled')
    assert len(nav2.goals) == 1
    _until(lambda: nav2.cancels, 2.0, '늦게 수락된 Nav2 goal 에 cancel 이 가지 않았다')


def test_unanswered_cancel_still_ends_the_goal(rig):
    _unanswered_cancel_still_ends_the_goal(rig)


def test_unanswered_cancel_still_ends_the_goal_on_two_fleet_threads(rig_two_threads):
    _unanswered_cancel_still_ends_the_goal(rig_two_threads)


def _unanswered_cancel_still_ends_the_goal(rig):
    nav2 = rig.start_nav2(answer_cancel=False)
    rig.wait_ready()
    handle = rig.send()
    _until(lambda: nav2.goals, 5.0, 'Nav2 가 goal 을 못 받았다')
    time.sleep(CANCEL_AFTER_S)
    canceled_at = time.monotonic()
    handle.cancel_goal_async()

    status, message, ended_at = _result(handle, CANCEL_WAIT_S + SLACK_S)
    assert (status, message) == (GoalStatus.STATUS_CANCELED, 'canceled')
    assert nav2.cancels, 'fleet 이 Nav2 에 cancel 을 보내지 않았다'
    assert ended_at - canceled_at >= CANCEL_WAIT_S

    nav2.answer_cancel = True
    rig.send()   # _accepted 가 풀려 다음 goal 을 받는다


def test_acceptance_after_giving_up_is_canceled(rig):
    nav2 = rig.start_nav2(accept_delay_s=LATE_ACCEPT_S)
    rig.wait_ready()
    handle = rig.send()
    time.sleep(CANCEL_AFTER_S)
    handle.cancel_goal_async()

    status, message, _ = _result(handle, CANCEL_WAIT_S + SLACK_S)
    assert (status, message) == (GoalStatus.STATUS_CANCELED, 'canceled')
    assert not nav2.cancels, '수락 전인데 cancel 이 갔다'
    _until(lambda: nav2.cancels, LATE_ACCEPT_S + SLACK_S,
           '포기한 뒤 늦게 수락된 Nav2 goal 에 cancel 이 가지 않았다')


def test_reset_done_while_waiting_for_the_nav2_server(rig):
    rig.wait_ready()
    handle = rig.send()
    time.sleep(CANCEL_AFTER_S)
    rig.driver.reset_done(epoch=1)
    time.sleep(CANCEL_AFTER_S)
    nav2 = rig.start_nav2()

    status, message, _ = _result(handle, SLACK_S * 2)
    assert (status, message) == (GoalStatus.STATUS_ABORTED, 'reset')
    time.sleep(CANCEL_AFTER_S)
    assert nav2.goals == [], '리셋 뒤에 Nav2 goal 이 나갔다'


def test_reset_done_publishes_initialpose_and_clears_each_costmap_once(rig):
    costmaps = rig.start_costmaps()
    rig.wait_ready()
    rig.driver.reset_done(epoch=1)
    _until(lambda: rig.driver.initialposes, 5.0, 'RESET_DONE 뒤 initialpose가 오지 않았다')
    _until(lambda: len(costmaps.calls) == 2, 5.0, 'global/local costmap clear가 모두 호출되지 않았다')
    assert sorted(name for name, _ in costmaps.calls) == ['global', 'local']

    rig.driver.reset_done(epoch=1)
    time.sleep(0.5)
    assert len(costmaps.calls) == 2, '같은 epoch가 costmap을 다시 비웠다'

    rig.driver.reset_done(epoch=0)
    time.sleep(0.5)
    assert len(costmaps.calls) == 2, '이전 epoch가 costmap을 다시 비웠다'


def test_slow_costmap_clear_does_not_stop_the_wall_tick(rig):
    rig.start_world()
    costmaps = rig.start_costmaps(delay_s=2.0)
    rig.wait_ready()
    _until(lambda: rig.driver.stopped, 5.0, 'reset 전 base/stopped heartbeat가 오지 않았다')
    before = len(rig.driver.stopped)

    rig.driver.reset_done(epoch=1)
    _until(lambda: len(costmaps.calls) == 2, 5.0, '느린 costmap 서비스가 호출되지 않았다')
    time.sleep(0.8)
    assert len(rig.driver.stopped) > before, 'costmap 응답 대기가 5 Hz wall tick을 막았다'
    _until(lambda: rig.fleet._costmap_clear_epoch is None, 5.0,
           '느린 costmap 응답이 끝난 뒤 clear 상태가 닫히지 않았다')


def test_missing_costmap_services_do_not_stop_the_wall_tick(request, tmp_path):
    test_rig = Rig(
        f'l2_fleet_{request.node.name}', tmp_path,
        fleet_params={'costmap_clear_wait_s': 0.4},
    )
    try:
        test_rig.start_world()
        test_rig.wait_ready()
        _until(lambda: test_rig.driver.stopped, 5.0,
               'reset 전 base/stopped heartbeat가 오지 않았다')
        before = len(test_rig.driver.stopped)

        test_rig.driver.reset_done(epoch=1)
        _until(lambda: test_rig.driver.initialposes, 5.0,
               'RESET_DONE 뒤 initialpose가 오지 않았다')
        _until(lambda: test_rig.fleet._costmap_clear_epoch is None, 2.0,
               '없는 costmap 서비스 대기가 wall 시한 뒤 닫히지 않았다')
        assert len(test_rig.driver.stopped) > before, '서비스 탐색이 5 Hz wall tick을 막았다'
    finally:
        test_rig.close()


def test_via_only_zone_is_not_a_destination(rig):
    # 계약 3절: door_*·cp_*·room_* 은 경유 전용이다. zones.yaml 에 있어도 GoToZone 목적지로 받지 않는다.
    nav2 = rig.start_nav2()
    rig.wait_ready()
    rig.send('door_a1', accepted=False)
    rig.send('load')   # 거부 뒤에도 다음 goal 을 받는다
    _until(lambda: nav2.goals, 5.0, 'Nav2 가 goal 을 못 받았다')
    assert len(nav2.goals) == 1


# -- DockingState(계약 11.6, opt-in) --------------------------------------------------

def test_docking_state_is_off_by_default(rig):
    # 기본값에서는 토픽을 만들지 않는다. 기존 동작은 그대로다.
    rig.wait_ready()
    time.sleep(0.5)
    assert rig.fleet.get_publishers_info_by_topic(f'/{rig.namespace}/base/docked') == []


def test_docking_state_follows_goal_and_reset(rig_docking):
    rig = rig_docking
    received = []
    rig.driver.create_subscription(DockingState, f'/{rig.namespace}/base/docked', received.append, HEARTBEAT)
    rig.wait_ready()

    def latest(check, message):
        _until(lambda: received and check(received[-1]), 5.0, f'{message}: {received[-1:]}')
        return received[-1]

    # 첫 RESET_DONE 전: epoch 는 1, UNKNOWN, zone 없음
    first = latest(lambda m: True, 'DockingState 가 오지 않았다')
    assert (first.epoch, first.docking, first.zone_id) == (1, DockingState.DOCKING_UNKNOWN, '')

    rig.driver.reset_done(epoch=2)
    after_reset = latest(lambda m: m.epoch == 2, 'epoch 2 가 오지 않았다')
    assert (after_reset.docking, after_reset.zone_id) == (DockingState.DOCKING_UNKNOWN, '')

    handle = rig.send('load')   # Nav2 서버가 없어 fleet 은 서버를 기다린다(goal 활성)
    driving = latest(lambda m: m.zone_id == 'load', '수락한 목표 zone 이 실리지 않았다')
    assert driving.docking == DockingState.DOCKING_NOT_DOCKED

    rig.driver.reset_done(epoch=3)
    status, message, _ = _result(handle, SLACK_S * 2)
    assert (status, message) == (GoalStatus.STATUS_ABORTED, 'reset')
    # 리셋이 goal 을 닫는 동안은 NOT_DOCKED 가 한두 번 더 올 수 있다. 닫힌 뒤에는 UNKNOWN 이다.
    cleared = latest(lambda m: m.epoch == 3 and m.docking == DockingState.DOCKING_UNKNOWN,
                     'epoch 3 의 UNKNOWN 이 오지 않았다')
    assert cleared.zone_id == ''
    # odom 이 한 번도 오지 않았으므로 seq 는 늘지 않는다(입력이 앞으로 가야만 +1).
    assert {m.seq for m in received} == {0}


# -- waypoints backend(빈월드 v0) -------------------------------------------------

ROUTES = """
schema_version: 1
frame: map
routes:
  - {from: dock_1, to: load, waypoints: [[0.5, 0.8]]}
"""
def shipped_follower_params():
    """실제로 싣는 추종 값. **여기에 숫자를 다시 적지 않는다** — 두 벌이 되면 어긋나도 아무도 안 본다."""
    path = pathlib.Path(__file__).resolve().parents[1] / 'config' / 'navigation_params.yaml'
    fleet = yaml.safe_load(path.read_text(encoding='utf-8'))['fleet']['ros__parameters']
    return {name: value for name, value in fleet.items() if name.startswith('follower_')}


def waypoint_rig(request, tmp_path, routes=None, params=None):
    params = dict(params or {'motion_backend': 'waypoints', 'follower_max_linear': 0.5,
                             'follower_slow_radius': 0.3, 'follower_waypoint_tolerance': 0.15})
    if routes is not None:
        path = tmp_path / 'routes.emptyworld.yaml'
        path.write_text(routes, encoding='utf-8')
        params['routes_file'] = str(path)
    return Rig(f'l2_fleet_{request.node.name.split("[")[0]}', tmp_path, fleet_params=params)


@pytest.fixture
def rig_waypoints(request, tmp_path):
    rig = waypoint_rig(request, tmp_path)
    yield rig
    rig.close()


@pytest.fixture
def rig_waypoints_routes(request, tmp_path):
    rig = waypoint_rig(request, tmp_path, routes=ROUTES)
    yield rig
    rig.close()


def test_waypoints_backend_drives_to_the_goal(rig_waypoints):
    rig = rig_waypoints
    world = rig.start_world()          # (0, 0, 0) 에서 시작한다. load 는 (1.0, 0.0, 0.0)
    rig.wait_ready()
    handle = rig.send('load')

    status, message, _ = _result(handle, DRIVE_TIMEOUT_S)
    assert (status, message) == (GoalStatus.STATUS_SUCCEEDED, 'arrived')
    assert abs(world.pose[0] - 1.0) <= 0.05 and abs(world.pose[1]) <= 0.05
    assert max(abs(y) for _, y, _ in world.track) <= 0.05   # routes 가 없으면 곧장 간다


def _deviation(track, polyline):
    """지나간 자취가 경로 선분에서 얼마나 벗어났나(m). 시뮬의 필요 여유 중 추종 항과 비교할 값이다."""
    def distance(point, first, second):
        dx, dy = second[0] - first[0], second[1] - first[1]
        length = dx * dx + dy * dy
        if length <= 0.0:
            return math.hypot(point[0] - first[0], point[1] - first[1])
        t = max(0.0, min(1.0, ((point[0] - first[0]) * dx + (point[1] - first[1]) * dy) / length))
        return math.hypot(point[0] - (first[0] + t * dx), point[1] - (first[1] + t * dy))

    segments = list(pairwise(polyline))
    return max(min(distance((x, y), a, b) for a, b in segments) for x, y, _ in track)


def test_waypoints_backend_follows_the_routes_file(rig_waypoints_routes):
    rig = rig_waypoints_routes
    world = rig.start_world()
    rig.wait_ready()
    handle = rig.send('load')

    status, message, _ = _result(handle, DRIVE_TIMEOUT_S)
    assert (status, message) == (GoalStatus.STATUS_SUCCEEDED, 'arrived')
    # dock_1 → load 사이에 (0.5, 0.8) 을 거쳐 간다. 곧장 갔다면 y 가 이만큼 커지지 않는다.
    assert max(y for _, y, _ in world.track) >= 0.6
    assert abs(world.pose[0] - 1.0) <= 0.05 and abs(world.pose[1]) <= 0.05
    # 경로 선분에서 벗어난 최대 거리. 시뮬(#410)이 장면 여유에 넣은 추종 항 0.065 m 의 상대값이다
    # (모서리 자르기 follower_waypoint_tolerance + 한 주기 이동량). 상한은 그 두 배로 둔다.
    deviation = _deviation(world.track, ((0.0, 0.0), (0.5, 0.8), (1.0, 0.0)))
    assert deviation <= 0.13, f'경로에서 {deviation:.3f} m 벗어났다(추종 항 0.065 의 두 배를 넘었다)'


def test_waypoints_backend_stops_on_reset(rig_waypoints):
    rig = rig_waypoints
    world = rig.start_world(start=(-3.0, 0.0, 0.0))   # 멀리서 시작해 주행 중에 리셋한다
    rig.wait_ready()
    handle = rig.send('load')
    _until(lambda: world.pose[0] > -2.8, 5.0, '추종이 시작되지 않았다')

    rig.driver.reset_done(epoch=2)
    status, message, _ = _result(handle, SLACK_S)
    assert (status, message) == (GoalStatus.STATUS_ABORTED, 'reset')
    stopped = tuple(world.pose)
    time.sleep(0.5)
    assert abs(world.pose[0] - stopped[0]) <= 0.02   # 리셋 뒤에는 더 가지 않는다


def test_publishing_after_the_publisher_is_gone_does_not_raise(rig_waypoints):
    # 실습29 down: 종료 중에 추종 루프가 publish 해서 InvalidHandle 이 났다.
    # 종료는 실패가 아니다 — 내려간 뒤의 발행은 조용히 False 다.
    rig = rig_waypoints
    rig.wait_ready()
    rig.fleet._cmd_vel_publisher.destroy()
    assert rig.fleet._publish_cmd_vel(Twist()) is False
    rig.fleet._publish_zero_velocity()          # 예외가 나지 않는다


@pytest.fixture
def rig_waypoints_shipped(request, tmp_path):
    # 저장소에 싣는 속도·가속 값 그대로 돈다(80 % 규칙, 재범 9/21).
    rig = waypoint_rig(request, tmp_path,
                       params={'motion_backend': 'waypoints', **shipped_follower_params()})
    yield rig
    rig.close()


def test_the_shipped_speeds_still_stop_within_two_centimetres(rig_waypoints_shipped):
    """속도를 올려도 도착 참값이 0.02 m 안에 남는가. ⑤ 집기 여유가 이 정확도에 달려 있다(lap5).

    목표 근처의 거동은 `max_linear / slow_radius` 로 정해진다. 속도를 올릴 때 감속 반경을 같이
    올린 근거가 이 시험이다 — 비를 유지하지 않으면 도착이 공차에 묶인다(K3 L3: 0.14 m).
    """
    rig = rig_waypoints_shipped
    world = rig.start_world()          # (0, 0, 0) 에서 시작한다. load 는 (1.0, 0.0, 0.0)
    rig.wait_ready()
    handle = rig.send('load')

    status, message, _ = _result(handle, DRIVE_TIMEOUT_S)
    assert (status, message) == (GoalStatus.STATUS_SUCCEEDED, 'arrived')
    assert math.hypot(world.pose[0] - 1.0, world.pose[1]) <= 0.02


def test_the_shipped_speeds_ramp_instead_of_stepping(rig_waypoints_shipped):
    """첫 명령이 상한으로 튀지 않는가. 상판에 칸막이가 없어 봉투가 미끄러진다(재범 9/21).

    스테이지의 속도 드라이브는 damping 이 커서 명령 계단을 거의 그대로 따라간다. 사슬에서
    가속을 자르는 곳은 추종기뿐이라, 여기서 안 자르면 아무도 안 자른다.
    """
    rig = rig_waypoints_shipped
    world = rig.start_world()
    rig.wait_ready()
    handle = rig.send('load')

    first = world.first_moving_command()
    assert first is not None, '움직이는 cmd_vel 이 오지 않았다'
    params = shipped_follower_params()
    one_step = params['follower_max_accel'] / params['follower_rate_hz']
    # 한 주기 폭이다. 주기가 밀려 두 번째 명령을 먼저 볼 수 있으니 두 주기까지 받아 준다.
    assert math.hypot(first[0], first[1]) <= one_step * 2.0
    assert math.hypot(first[0], first[1]) < params['follower_max_linear']
    # 보낸 goal 은 여기서 끝내고 나간다. 안 그러면 teardown 이 5 s 만 기다리다 깨진다
    # (싣는 값으로 1 m 를 가는 데 8 s 쯤 걸린다).
    assert _result(handle, DRIVE_TIMEOUT_S)[0] == GoalStatus.STATUS_SUCCEEDED


# -- nav2 + final approach(병원 9/23) ----------------------------------------------

class FakeNav2Teleport(FakeNav2):
    """Nav2 대역: 받은 목표 자세로 `world` 를 옮겨 놓고 성공한다(경로는 보지 않는다). 받은 목표를 기록한다."""

    def __init__(self, namespace, world):
        super().__init__(namespace)
        self.world = world
        self.poses = []

    def _execute(self, goal_handle):
        pose = goal_handle.request.pose.pose
        yaw = quaternion_to_yaw(pose.orientation.x, pose.orientation.y, pose.orientation.z, pose.orientation.w)
        self.poses.append((pose.position.x, pose.position.y, yaw))
        self.world.pose[:] = [pose.position.x, pose.position.y, yaw]
        time.sleep(0.3)
        goal_handle.succeed()
        return NavigateToPose.Result()


@pytest.fixture
def rig_final_approach(request, tmp_path):
    params = {'motion_backend': 'nav2', 'nav2_final_approach': 'true', **shipped_follower_params()}
    rig = waypoint_rig(request, tmp_path, routes=ROUTES, params=params)
    yield rig
    rig.close()


def test_nav2_goes_to_the_staging_point_and_the_follower_finishes(rig_final_approach):
    """9/23 병원 L3: Nav2 footprint 로는 고정물 옆 정차 자리에 못 들어가 0.56 m 앞에서 섰다.

    `nav2_final_approach` 면 Nav2 에는 경로의 마지막 waypoint(접근점)를 zone 의 yaw 로 보내고,
    정차 자리까지는 추종기가 곧장 간다.
    """
    rig = rig_final_approach
    world = rig.start_world()                  # (0, 0, 0). load 는 (1.0, 0.0, 0.0), 경로 dock_1 → load 는 (0.5, 0.8)
    nav2 = FakeNav2Teleport(rig.namespace, world)
    rig.nav2 = nav2
    rig.executors['nav2'].add_node(nav2)
    rig.wait_ready()
    handle = rig.send('load')

    status, message, _ = _result(handle, DRIVE_TIMEOUT_S)
    assert (status, message) == (GoalStatus.STATUS_SUCCEEDED, 'arrived')
    assert len(nav2.poses) == 1
    x, y, yaw = nav2.poses[0]
    assert (round(x, 3), round(y, 3)) == (0.5, 0.8), 'Nav2 목표가 접근점이 아니다'
    assert abs(yaw) <= 1e-6, 'Nav2 목표 yaw 가 zone yaw 가 아니다'
    assert abs(world.pose[0] - 1.0) <= 0.05 and abs(world.pose[1]) <= 0.05, '추종기가 정차 자리에 안 붙었다'
    assert rig.fleet._here == 'load'


class FakeNav2StopsShort(FakeNav2):
    """Nav2 대역: 목표 `short_m` 앞(출발 쪽)에 `world` 를 세워 두고, 피드백을 낸 뒤 `abort` 한다.

    `cancel` 이 오면 `canceled` 로 끝낸다. 병원 L3 3회차의 `Failed to make progress` 흉내다.
    """

    def __init__(self, namespace, world, short_m):
        super().__init__(namespace)
        self.world = world
        self.short_m = short_m
        self.statuses = []

    def _execute(self, goal_handle):
        pose = goal_handle.request.pose.pose
        start = tuple(self.world.pose[:2])
        gap = math.hypot(pose.position.x - start[0], pose.position.y - start[1])
        k = max(0.0, (gap - self.short_m) / gap) if gap > 0.0 else 0.0
        stop = (start[0] + k * (pose.position.x - start[0]), start[1] + k * (pose.position.y - start[1]))
        self.world.pose[:2] = list(stop)
        feedback = NavigateToPose.Feedback()
        feedback.current_pose.pose.position.x, feedback.current_pose.pose.position.y = stop
        feedback.distance_remaining = float(self.short_m)
        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline:
            goal_handle.publish_feedback(feedback)
            if goal_handle.is_cancel_requested:
                goal_handle.canceled()
                self.statuses.append('canceled')
                return NavigateToPose.Result()
            time.sleep(0.05)
        goal_handle.abort()
        self.statuses.append('aborted')
        return NavigateToPose.Result()


def _run_stops_short(rig, short_m):
    world = rig.start_world()                  # (0, 0, 0). 경로 dock_1 → load 의 접근점은 (0.5, 0.8)
    nav2 = FakeNav2StopsShort(rig.namespace, world, short_m)
    rig.nav2 = nav2
    rig.executors['nav2'].add_node(nav2)
    rig.wait_ready()
    return nav2, world, _result(rig.send('load'), DRIVE_TIMEOUT_S)


def test_nav2_stopping_just_short_of_the_staging_point_hands_over(rig_final_approach):
    """병원 L3 3회차(9/23): Nav2 가 접근점 0.25 m 앞(goal 공차 0.2 밖)에서 진행을 못 해 180 s 를 넘겼다.

    넘김 반경(0.5 m) 안이면 Nav2 goal 을 거두고, 추종기가 접근점을 거쳐 정차 자리로 간다.
    """
    nav2, world, (status, message, _) = _run_stops_short(rig_final_approach, short_m=0.25)
    assert (status, message) == (GoalStatus.STATUS_SUCCEEDED, 'arrived')
    assert nav2.statuses == ['canceled'], '넘김 반경 안인데 Nav2 goal 을 거두지 않았다'
    assert abs(world.pose[0] - 1.0) <= 0.05 and abs(world.pose[1]) <= 0.05, '추종기가 정차 자리에 안 붙었다'
    assert min(math.hypot(x - 0.5, y - 0.8) for x, y, _ in world.track) <= 0.1, '접근점을 거치지 않았다'
    assert rig_final_approach.fleet._here == 'load'


def test_nav2_failing_far_from_the_staging_point_is_still_a_failure(rig_final_approach):
    """넘김 반경 밖에서 Nav2 가 멈추면 추종기로 덮지 않는다 — 경로 밖 직선을 따져 본 적이 없다."""
    nav2, _, (status, message, _) = _run_stops_short(rig_final_approach, short_m=0.8)
    assert nav2.statuses == ['aborted']
    assert status == GoalStatus.STATUS_ABORTED and message.startswith('nav2_status_'), (status, message)


def test_shutdown_while_nav2_never_answers_ends_the_goal(rig):
    """병원 L3 2회차(9/23): Nav2 goal 이 걸린 채 SIGINT 를 받은 fleet 가 안 내려가 SIGKILL 됐다.

    컨텍스트가 내려가면 Nav2 결과를 기다리지 않고 goal 을 끝내야 한다(실행 스레드가 남으면 executor 가 못 내려간다).
    """
    rig.start_nav2()                    # 끝까지 결과를 내지 않는 대역
    rig.wait_ready()
    rig.send('load')
    _until(lambda: rig.nav2.goals, 5.0, 'Nav2 가 goal 을 못 받았다')
    rig.fleet.context.shutdown()
    _until(lambda: not rig.fleet._accepted, 3.0, '종료 중인데 fleet 의 GoToZone 이 안 끝났다')


def test_finish_never_returns_a_none_message(rig):
    """병원 L3 5회차(9/23) down: 결과 message 에 None 이 들어가 rosidl 변환 assert 로 fleet 가 exit -6 으로 죽었다."""

    class Handle:
        request = GoToZone.Goal(zone_id='load')
        is_cancel_requested = False

        def abort(self):
            pass

    assert rig.fleet._finish(Handle(), None).message == 'nav2_no_result'
    rig.fleet.context.shutdown()
    assert rig.fleet._finish(Handle(), None).message == 'canceled'
