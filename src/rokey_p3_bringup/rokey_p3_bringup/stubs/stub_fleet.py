"""스텁 주행. fleet 을 계약과 같은 이름으로 대신한다(계약 8절).

내는 것: /amr_1/base/stopped, GoToZone 서버.
계약 5절의 출발 인터락을 여기서도 본다. arm/at_home 이 true 이고 1.0 s 이내가 아니면 goal 을 거부한다.
"""

import time

import rclpy
from rclpy.action import ActionServer, CancelResponse, GoalResponse
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from std_msgs.msg import Bool

from rokey_p3_bringup.shutdown import spin_until_interrupted
from rokey_p3_bringup.stubs import common
from rokey_p3_interfaces.action import GoToZone
from rokey_p3_navigation.zones import is_zone_id
from rokey_p3_orchestrator.ros_qos import heartbeat_qos

FRESH_S = 1.0


class StubFleet(Node):
    """stub_fleet 노드."""

    def __init__(self, **kwargs):
        super().__init__('stub_fleet', **kwargs)
        self.declare_parameter('travel_s', 1.0)
        self.declare_parameter('start_distance_m', 6.0)
        self._travel_s = float(self.get_parameter('travel_s').value)
        self._start_distance = float(self.get_parameter('start_distance_m').value)

        self._at_home = None
        self._at_home_wall = 0.0
        self._stopped = True
        group = ReentrantCallbackGroup()

        self._stopped_pub = self.create_publisher(
            Bool, f'/{common.NAMESPACE}/base/stopped', heartbeat_qos())
        self.create_subscription(Bool, f'/{common.NAMESPACE}/arm/at_home',
                                 self._on_at_home, heartbeat_qos())
        self._events = common.EventIo(self, common.NAMESPACE, self._on_event)
        self._server = ActionServer(
            self, GoToZone, f'/{common.NAMESPACE}/go_to_zone',
            goal_callback=self._on_goal, cancel_callback=lambda _: CancelResponse.ACCEPT,
            execute_callback=self._execute, callback_group=group)
        self.create_timer(0.2, self._publish_stopped)   # H = 5 Hz
        self.get_logger().info('stub_fleet up. GoToZone 서버와 base/stopped.')

    def _on_at_home(self, msg):
        self._at_home = bool(msg.data)
        self._at_home_wall = time.monotonic()

    def _on_event(self, msg):
        if msg.name == 'RESET_DONE':
            # 계약 6절 4. 실물 fleet 은 initialpose 를 내고 costmap 을 비운다.
            self.get_logger().info(f'RESET_DONE epoch={msg.epoch}. 스텁은 정지 상태로 돌아간다.')
            self._stopped = True

    def _publish_stopped(self):
        self._stopped_pub.publish(Bool(data=self._stopped))

    def _arm_is_home(self):
        fresh = (time.monotonic() - self._at_home_wall) <= FRESH_S
        return bool(self._at_home) and fresh

    def _on_goal(self, goal):
        if not is_zone_id(goal.zone_id):
            self.get_logger().warning(f'모르는 구역 {goal.zone_id}. 거부한다.')
            return GoalResponse.REJECT
        if not self._arm_is_home():
            # 계약 5절: 팔이 홈이 아니거나 unknown 이면 출발하지 않는다. 타임아웃은 진입 허가가 아니다.
            self.get_logger().warning('arm/at_home 이 true 가 아니거나 오래됐다. 출발을 거부한다.')
            return GoalResponse.REJECT
        return GoalResponse.ACCEPT

    def _execute(self, goal_handle):
        zone_id = goal_handle.request.zone_id
        self._stopped = False
        steps = max(1, int(self._travel_s / 0.1))
        for step in range(steps):
            if goal_handle.is_cancel_requested:
                self._stopped = True
                goal_handle.canceled()
                return GoToZone.Result(arrived=False, message='canceled')
            feedback = GoToZone.Feedback()
            feedback.distance_remaining = self._start_distance * (1.0 - (step + 1) / steps)
            goal_handle.publish_feedback(feedback)
            time.sleep(0.1)
        self._stopped = True
        goal_handle.succeed()
        self.get_logger().info(f'{zone_id} 도착.')
        return GoToZone.Result(arrived=True, message='')


def main(args=None):
    """콘솔 진입점."""
    rclpy.init(args=args)
    node = StubFleet()
    # 액션 실행 콜백이 스레드를 오래 잡는다. 코어 수가 적은 기계에서도 굶지 않게 고정한다.
    executor = MultiThreadedExecutor(num_threads=8)
    executor.add_node(node)
    spin_until_interrupted(node, executor)


if __name__ == '__main__':
    main()
