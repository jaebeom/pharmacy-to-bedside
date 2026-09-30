"""base_driver 가 남의 `joint_states` 에 상태를 바꾸지 않는가.

한 바퀴 조합에서 `/amr_1/joint_states` 에는 발행자가 둘이다(시뮬 확인, 9/21):
UR5 6관절 메시지와 베이스 3관절 메시지가 **같은 토픽에 다른 메시지로** 온다.
그래서 `base_driver` 는 자기 관절이 하나도 없는 메시지를 UR5 주기로 계속 받는다.
그때 0 을 넣으면 `odom` 이 튀고 `base/stopped`·도착 판정이 흔들린다.

`rclpy`·`tf2_ros` 가 없으면 건너뛴다(로컬 Mac). CI 에서 돈다.
"""

import importlib.util

import pytest

MISSING = (importlib.util.find_spec('rclpy') is None
           or importlib.util.find_spec('tf2_ros') is None)
pytestmark = pytest.mark.skipif(MISSING, reason='rclpy·tf2_ros 없음 — 로컬 미실행(CI 로 확인)')

if not MISSING:
    import rclpy
    from sensor_msgs.msg import JointState

    from rokey_p3_navigation.base_driver_node import BaseDriver

UR5 = ('shoulder_pan_joint', 'shoulder_lift_joint', 'elbow_joint',
       'wrist_1_joint', 'wrist_2_joint', 'wrist_3_joint')


@pytest.fixture
def driver():
    rclpy.init(args=['--ros-args', '-p', 'robot_namespace:=l1_base_driver'])
    node = BaseDriver()
    yield node
    node.destroy_node()
    rclpy.try_shutdown()


def base_message(x, y, yaw, stamp_s):
    message = JointState()
    message.header.stamp.sec = int(stamp_s)
    message.header.stamp.nanosec = int((stamp_s - int(stamp_s)) * 1e9)
    message.name = ['dummy_base_prismatic_x_joint', 'dummy_base_prismatic_y_joint',
                    'dummy_base_revolute_z_joint']
    message.position = [x, y, yaw]
    message.velocity = [0.0, 0.0, 0.0]
    return message


def arm_message(stamp_s):
    message = JointState()
    message.header.stamp.sec = int(stamp_s)
    message.name = list(UR5)
    message.position = [0.1] * len(UR5)
    message.velocity = [0.2] * len(UR5)
    return message


def test_a_base_message_moves_the_state(driver):
    driver._on_joint_states(base_message(1.0, 2.0, 0.5, 1.0))
    assert driver._pose == pytest.approx((1.0, 2.0, 0.5))
    assert driver._joint_state_at is not None


def test_an_arm_only_message_changes_nothing(driver):
    driver._on_joint_states(base_message(1.0, 2.0, 0.5, 1.0))
    before = (driver._pose, driver._twist, driver._joint_state_at, driver._sim_stamp)

    for stamp in (1.01, 1.02, 1.03):     # UR5 주기로 여러 번 온다
        driver._on_joint_states(arm_message(stamp))

    assert (driver._pose, driver._twist, driver._joint_state_at, driver._sim_stamp) == before


def test_an_arm_only_message_does_not_refresh_the_watchdog(driver):
    # 자기 관절이 없는 메시지는 "joint_states 가 오고 있다" 의 증거가 아니다(계약 5절 stale 판정).
    driver._on_joint_states(arm_message(1.0))
    assert driver._joint_state_at is None


def test_a_message_without_positions_changes_nothing(driver):
    driver._on_joint_states(base_message(1.0, 2.0, 0.5, 1.0))
    before = (driver._pose, driver._joint_state_at)

    empty = base_message(0.0, 0.0, 0.0, 2.0)
    empty.position = []
    driver._on_joint_states(empty)

    assert (driver._pose, driver._joint_state_at) == before


def test_stale_warning_is_edge_triggered(driver):
    # 한 바퀴 조합에서는 UR5 메시지가 계속 온다. 남의 메시지에 5 s 마다 WARN 을 내면
    # 판정선의 "새 종류 WARN 0" 에 걸리고 진짜 고장과 구별도 안 된다. 그래서 상태 전이에서만 낸다.
    driver._publish_command()
    assert driver._joints_were_stale is True      # 아직 자기 관절을 한 번도 못 받았다

    driver._on_joint_states(base_message(1.0, 2.0, 0.5, 1.0))
    driver._publish_command()
    assert driver._joints_were_stale is False
