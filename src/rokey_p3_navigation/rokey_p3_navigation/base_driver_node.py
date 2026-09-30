"""base_driver: cmd_vel 을 dummy 조인트 속도로, joint_states 를 odom·TF 로. 계약 v1 2.2절.

- `/amr_1/cmd_vel` (`amr_1/base_link` 기준) → `/amr_1/base/joint_command` (dummy 3개, `velocity`)
- `/amr_1/joint_states` → `/amr_1/odom` (`amr_1/odom` → `amr_1/base_link`) 와 같은 변환의 TF

dummy 조인트는 world 축이라 현재 yaw 로 돌린다. 변환 자체는 `base_kinematics` 의 순수 함수다.
조인트 이름은 파라미터다. **USD 안의 실제 이름은 마스터에서 확인한다.**
stale 판정과 명령 주기는 계약 4절대로 steady clock(wall) 이다. 메시지 stamp 는 sim time 이다.
"""

import time

import rclpy
from geometry_msgs.msg import Twist, TransformStamped
from nav_msgs.msg import Odometry
from rclpy.clock import Clock, ClockType
from rclpy.node import Node
from sensor_msgs.msg import JointState
from tf2_ros import TransformBroadcaster

from rokey_p3_navigation.base_kinematics import (
    body_to_world_velocity,
    difference_velocity,
    odom_from_joints,
    yaw_to_quaternion,
)
from rokey_p3_navigation.qos_profiles import RELIABLE, SENSOR


class BaseDriver(Node):
    """dummy 베이스 조인트 드라이버."""

    def __init__(self):
        super().__init__('base_driver')

        namespace = self.declare_parameter('robot_namespace', 'amr_1').value
        # USD 조인트 이름은 마스터에서 확인한다. 기본값은 자리표시자다.
        self._joint_names = [
            self.declare_parameter('joint_x', 'dummy_base_prismatic_x_joint').value,
            self.declare_parameter('joint_y', 'dummy_base_prismatic_y_joint').value,
            self.declare_parameter('joint_yaw', 'dummy_base_revolute_z_joint').value,
        ]
        self._command_period = 1.0 / float(self.declare_parameter('command_rate_hz', 20.0).value)
        self._cmd_vel_timeout = float(self.declare_parameter('cmd_vel_timeout_s', 0.5).value)
        self._joint_states_timeout = float(
            self.declare_parameter('joint_states_timeout_s', 1.0).value)
        # 진단용 문턱이다. 첫 joint_states 의 x·y 가 이보다 크면 한 번 WARN 한다(동작은 안 바뀐다).
        self._start_tolerance = float(self.declare_parameter('start_position_tolerance_m', 0.5).value)
        self._odom_frame = f'{namespace}/odom'
        self._base_frame = f'{namespace}/base_link'

        self._command = (0.0, 0.0, 0.0)
        self._cmd_vel_at = None       # steady clock, 마지막 cmd_vel 수신
        self._joint_state_at = None   # steady clock, 마지막 joint_states 수신
        self._joints_were_stale = False   # stale 로 넘어갈 때만 WARN 한다
        self._first_joint_state = True    # 첫 값이 0 근처인지 한 번 본다(아래)
        self._pose = (0.0, 0.0, 0.0)  # world 축 dummy 조인트 위치
        self._twist = (0.0, 0.0, 0.0)
        self._sim_stamp = None        # 마지막 joint_states 의 sim time (초)
        self._published_stamp = None

        self._odom_publisher = self.create_publisher(Odometry, f'/{namespace}/odom', RELIABLE)
        self._command_publisher = self.create_publisher(
            JointState, f'/{namespace}/base/joint_command', RELIABLE)
        self._tf_broadcaster = TransformBroadcaster(self)
        self.create_subscription(Twist, f'/{namespace}/cmd_vel', self._on_cmd_vel, RELIABLE)
        self.create_subscription(
            JointState, f'/{namespace}/joint_states', self._on_joint_states, SENSOR)
        # 명령 주기는 wall 이다. cmd_vel·joint_command 의 0.5 s 판정이 wall 이고(계약 4절),
        # sim time 으로 돌리면 RTF 가 낮을 때 Isaac 쪽 watchdog 이 먼저 0 으로 만든다.
        self.create_timer(self._command_period, self._publish_command,
                          clock=Clock(clock_type=ClockType.STEADY_TIME))

        self.get_logger().info(
            f'base_driver up. dummy 조인트 {self._joint_names} '
            f'(USD 이름은 마스터에서 확인). frames {self._odom_frame} -> {self._base_frame}')

    def _on_cmd_vel(self, msg):
        """마지막 명령만 기억한다. 계약 2.2절: base_link 기준 m/s, rad/s."""
        self._command = (msg.linear.x, msg.linear.y, msg.angular.z)
        self._cmd_vel_at = time.monotonic()

    def _on_joint_states(self, msg):
        """dummy 3개만 골라 odom 과 TF 를 낸다. UR5 6개는 무시한다."""
        try:
            indices = [msg.name.index(name) for name in self._joint_names]
        except ValueError:
            # 같은 토픽에 발행자가 여럿이다(UR5 6관절 메시지와 베이스 3관절 메시지가 따로 온다).
            # 남의 메시지는 조용히 건너뛴다. 진짜 고장(자기 관절이 stale 시한 넘게 안 옴)은
            # _publish_command 가 한 번 WARN 한다. 둘을 같은 줄로 내면 구별이 안 된다.
            self.get_logger().debug(
                f'dummy 조인트 {self._joint_names} 가 없는 joint_states 를 건너뛴다: '
                f'{list(msg.name)}')
            return
        if len(msg.position) <= max(indices):
            self.get_logger().debug('joint_states 의 position 이 비었다. 건너뛴다.')
            return

        self._joint_state_at = time.monotonic()
        stamp = msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9
        pose = tuple(float(msg.position[i]) for i in indices)
        if self._first_joint_state:
            # 계약 3절: odom 자세는 조인트 값 그대로다. 그래서 조인트 원점 = odom 원점 = 출발 자리다.
            # 첫 값이 0 근처가 아니면 스테이지가 world 좌표를 넣고 있다는 뜻이고, 그러면
            # map -> odom 을 도크 자리로 두는 쪽(dock_origin_tf)과 겹쳐 두 배로 어긋난다.
            self._first_joint_state = False
            if max(abs(pose[0]), abs(pose[1])) > self._start_tolerance:
                self.get_logger().warn(
                    f'첫 joint_states 의 위치가 {pose[:2]} 다. 0 근처가 아니다. '
                    '스테이지가 조인트 원점을 출발 자리가 아니라 world 로 두고 있는지 확인한다. '
                    'map -> odom 을 도크 자리로 두면 두 배로 어긋난다.')
        if len(msg.velocity) > max(indices):
            velocity = tuple(float(msg.velocity[i]) for i in indices)
        elif self._sim_stamp is None:
            velocity = (0.0, 0.0, 0.0)
        else:
            # velocity 가 비면 위치 차이로 만든다. 0 으로 두면 base/stopped 가 항상 참이 된다.
            velocity = difference_velocity(self._pose, pose, stamp - self._sim_stamp)

        self._pose, self._twist = odom_from_joints(*pose, *velocity)
        self._sim_stamp = stamp
        if self._published_stamp is not None and stamp <= self._published_stamp:
            return  # 같은 stamp 를 두 번 내면 TF 가 중복 데이터로 경고한다
        self._published_stamp = stamp
        self._publish_odom(msg.header.stamp)

    def _publish_odom(self, stamp):
        """odom 과 TF 는 한 쌍이다. 노이즈 없음, 공분산 0."""
        x, y, yaw = self._pose
        vx, vy, wz = self._twist
        quaternion = yaw_to_quaternion(yaw)

        odom = Odometry()
        odom.header.stamp = stamp
        odom.header.frame_id = self._odom_frame
        odom.child_frame_id = self._base_frame
        odom.pose.pose.position.x = x
        odom.pose.pose.position.y = y
        (odom.pose.pose.orientation.x, odom.pose.pose.orientation.y,
         odom.pose.pose.orientation.z, odom.pose.pose.orientation.w) = quaternion
        odom.twist.twist.linear.x = vx
        odom.twist.twist.linear.y = vy
        odom.twist.twist.angular.z = wz
        self._odom_publisher.publish(odom)

        transform = TransformStamped()
        transform.header.stamp = stamp
        transform.header.frame_id = self._odom_frame
        transform.child_frame_id = self._base_frame
        transform.transform.translation.x = x
        transform.transform.translation.y = y
        (transform.transform.rotation.x, transform.transform.rotation.y,
         transform.transform.rotation.z, transform.transform.rotation.w) = quaternion
        self._tf_broadcaster.sendTransform(transform)

    def _publish_command(self):
        """20 Hz. cmd_vel 이나 joint_states 가 끊기면 0 을 낸다."""
        now = time.monotonic()
        cmd_vel_stale = (self._cmd_vel_at is None
                         or now - self._cmd_vel_at > self._cmd_vel_timeout)
        joints_stale = (self._joint_state_at is None
                        or now - self._joint_state_at > self._joint_states_timeout)

        if cmd_vel_stale or joints_stale:
            # 정지는 원격 watchdog 에 맡기지 않는다(계약 5절 "정지 보장").
            velocity = (0.0, 0.0, 0.0)
            if joints_stale and not self._joints_were_stale:
                self.get_logger().warn(
                    f'dummy 조인트 {self._joint_names} 의 joint_states 가 '
                    f'{self._joint_states_timeout:g} s(wall) 넘게 없다. yaw 를 모르므로 0 만 낸다.')
        else:
            if self._joints_were_stale:
                self.get_logger().info('joint_states 가 다시 온다.')
            velocity = body_to_world_velocity(*self._command, self._pose[2])
        self._joints_were_stale = joints_stale

        command = JointState()
        command.header.stamp = self.get_clock().now().to_msg()
        command.name = list(self._joint_names)
        command.velocity = [float(value) for value in velocity]
        self._command_publisher.publish(command)


def main(args=None):
    """콘솔 진입점."""
    rclpy.init(args=args)
    node = BaseDriver()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
