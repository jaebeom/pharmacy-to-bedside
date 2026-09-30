"""L2. 관절이 0 일 때 `map` 기준 자세가 **출발 도크**인가. 계약 v1 3절.

실습24(master02 `b09c22c`) 관측: 베이스가 `dock_1` (4.60, 0.55)에 서 있는데 `/amr_1/joint_states` 의
position 은 (0, 0, 0)이다. 스테이지의 조인트 원점이 world 가 아니라 **출발(리셋) 자리**이기 때문이다.
`base_driver` 는 계약대로 그 값을 그대로 `odom` 자세로 쓰므로, `map` → `odom` 을 항등으로 두면
fleet 이 베이스를 `map` (0, 0)으로 읽어 4 m 넘게 어긋난다.

그래서 `dock_origin_tf` 가 그 변환을 **도크 자리만큼 평행이동**으로 낸다. 이 시험이 그것을 고정한다.
`rclpy`·`tf2_ros` 가 없으면 건너뛴다(로컬 Mac). CI 에서 돈다.
"""

import importlib.util
import threading
import time

import pytest

MISSING = (importlib.util.find_spec('rclpy') is None
           or importlib.util.find_spec('tf2_ros') is None)
pytestmark = pytest.mark.skipif(MISSING, reason='rclpy·tf2_ros 없음 — 로컬 미실행(CI 로 확인)')

if not MISSING:
    import rclpy
    from rclpy.executors import MultiThreadedExecutor
    from rclpy.node import Node
    from rclpy.time import Time
    from sensor_msgs.msg import JointState
    from tf2_ros import Buffer, TransformListener

    from rokey_p3_navigation.base_driver_node import BaseDriver
    from rokey_p3_navigation.base_kinematics import quaternion_to_yaw
    from rokey_p3_navigation.dock_origin_tf_node import DockOriginTf
    from rokey_p3_navigation.qos_profiles import RELIABLE
else:
    Node = object

#: 실습24 의 값이다. 도크가 원점이 아닌 자리에 있어야 이 시험이 뜻을 갖는다.
DOCK = (4.60, 0.55)
JOINTS = ('dummy_base_prismatic_x_joint', 'dummy_base_prismatic_y_joint',
          'dummy_base_revolute_z_joint')
ZONES = f"""frame: map
zones:
  load:   {{kind: load, x: 4.00, y: 0.55, yaw: 0.0, tol_xy: 0.15, tol_yaw: 0.2}}
  dock_1: {{kind: dock, x: {DOCK[0]}, y: {DOCK[1]}, yaw: 0.0, tol_xy: 0.15, tol_yaw: 0.2}}
"""


class Stage(Node):
    """스테이지 대역: 조인트 값을 **출발 자리 기준**으로 낸다(world 가 아니다)."""

    def __init__(self, namespace):
        super().__init__('fake_stage', namespace=namespace)
        self.publisher = self.create_publisher(JointState, f'/{namespace}/joint_states', RELIABLE)
        self.stamp = 0.0

    def publish(self, x, y, yaw):
        self.stamp += 0.05
        message = JointState()
        message.header.stamp = Time(nanoseconds=int(self.stamp * 1e9)).to_msg()
        message.name = list(JOINTS)
        message.position = [x, y, yaw]
        message.velocity = [0.0, 0.0, 0.0]
        self.publisher.publish(message)


@pytest.fixture
def rig(request, tmp_path):
    namespace = f'l2_dock_{request.node.name}'
    zones = tmp_path / 'zones.yaml'
    zones.write_text(ZONES, encoding='utf-8')
    params = tmp_path / 'params.yaml'
    params.write_text(
        ''.join(f'{node}:\n  ros__parameters:\n    robot_namespace: {namespace}\n'
                f'    zones_file: {zones}\n    dock_zone: dock_1\n'
                for node in ('base_driver', 'dock_origin_tf')), encoding='utf-8')
    rclpy.init(args=['--ros-args', '--params-file', str(params)])

    driver, origin, stage = BaseDriver(), DockOriginTf(), Stage(namespace)
    listener = Node('l2_listener', namespace=namespace)
    buffer = Buffer()
    TransformListener(buffer, listener)
    executor = MultiThreadedExecutor(num_threads=4)
    for node in (driver, origin, stage, listener):
        executor.add_node(node)
    thread = threading.Thread(target=executor.spin, daemon=True)
    thread.start()

    yield namespace, stage, buffer

    executor.shutdown(timeout_sec=5.0)
    thread.join(timeout=5.0)
    for node in (driver, origin, stage, listener):
        node.destroy_node()
    rclpy.try_shutdown()


def _pose(buffer, namespace, timeout_s=5.0):
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            transform = buffer.lookup_transform('map', f'{namespace}/base_link', Time())
        except Exception:                      # noqa: BLE001 — TF 가 아직 없다
            time.sleep(0.05)
            continue
        rotation = transform.transform.rotation
        return (transform.transform.translation.x, transform.transform.translation.y,
                quaternion_to_yaw(rotation.x, rotation.y, rotation.z, rotation.w))
    raise AssertionError(f'{timeout_s:g} s 안에 map -> {namespace}/base_link 가 오지 않았다')


def test_zero_joints_mean_the_robot_is_at_the_dock(rig):
    namespace, stage, buffer = rig
    for _ in range(5):
        stage.publish(0.0, 0.0, 0.0)
        time.sleep(0.05)

    x, y, yaw = _pose(buffer, namespace)
    assert (x, y) == pytest.approx(DOCK, abs=0.01)
    assert yaw == pytest.approx(0.0, abs=0.01)


def test_joint_values_move_the_robot_from_the_dock(rig):
    namespace, stage, buffer = rig
    for _ in range(5):
        stage.publish(-0.60, 0.0, 0.0)     # 도크에서 -x 로 0.60 m = load(4.00, 0.55)
        time.sleep(0.05)

    x, y, _ = _pose(buffer, namespace)
    assert (x, y) == pytest.approx((4.00, 0.55), abs=0.01)
