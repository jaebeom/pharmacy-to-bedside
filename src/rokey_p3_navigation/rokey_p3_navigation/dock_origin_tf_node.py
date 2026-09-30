"""빈월드 v0 의 `map` → `<ns>/odom` 고정 변환. 계약 v1 3절.

AMCL 이 있을 때 그 변환의 작성자는 AMCL 이다. **이 노드는 AMCL 이 없는 빈월드(`motion_backend: waypoints`)에서만 뜬다.**

왜 항등이 아닌가:
- 스테이지는 dummy 조인트 값을 그대로 낸다. 그 원점은 world 가 아니라 **AMR 이 시작(리셋)하는 도크 자리**다
  (실습24, master02 `b09c22c`: 베이스가 `dock_1` (4.60, 0.55)에 서 있는데 `joint_states` 는 (0, 0, 0)).
- `base_driver` 는 계약 3절대로 그 값을 그대로 `odom` 자세로 쓴다. 그래서 `odom` 원점 = 도크다.
- `map` → `odom` 을 항등으로 두면 fleet 은 베이스가 `map` (0, 0)에 있다고 믿는다.
  도크가 (4.60, 0.55)면 4 m 넘게 어긋난다.

왜 yaw 는 0 인가:
- dummy 축(prismatic x·y)은 **world 축과 평행**하다. 조인트 값이 늘 world 축 기준이라 `odom` 프레임은 회전하지 않는다.
- 그래서 이 변환은 **평행이동만**이다. 도크의 yaw 를 넣으면 틀린다(도크 yaw 가 0 이 아닌 월드에서 드러난다).
- 도크 yaw 는 `zones.yaml` 에 그대로 있고, 목표 자세 판정에서 쓰인다. 여기서는 쓰지 않는다.

자세의 출처는 `zones.yaml` 하나다(`dock_zone` 파라미터가 고르는 zone). 스테이지의 출발 자리와 같은 파일에서 나와야
조용히 어긋나지 않는다.

**전제(시뮬 9/21 확인): yaw 관절 0 = world yaw 0 이다.** 사슬에 중간 회전이 없고 배치가 순수 평행이동이라
`--amr-start X Y` 는 이 관계에 닿지 않는다. 나중에 출발 yaw 를 인자로 열면 시뮬은 링크를 돌리지 않고
revolute 의 영점을 옮기는 쪽으로 간다 — 그러면 "yaw 관절 0 = 출발 yaw" 가 되어 **이 식이 바뀐다.**
"""

import rclpy
from geometry_msgs.msg import TransformStamped
from rclpy.node import Node
from tf2_ros import StaticTransformBroadcaster

from rokey_p3_navigation.zones import ZonesError, load_zones


class DockOriginTf(Node):
    """`map` → `<ns>/odom` 을 도크 자리만큼 평행이동으로 1회 낸다."""

    def __init__(self):
        super().__init__('dock_origin_tf')
        namespace = self.declare_parameter('robot_namespace', 'amr_1').value
        dock_zone = self.declare_parameter('dock_zone', 'dock_1').value
        zones_file = self.declare_parameter('zones_file', '').value

        zones = self._load_zones(zones_file)
        if zones is None or dock_zone not in zones.zones:
            self.get_logger().error(
                f'도크 {dock_zone} 을 zones.yaml 에서 못 찾았다. map -> {namespace}/odom 를 내지 않는다. '
                'fleet 은 TF 가 없어 추종을 시작하지 못한다.')
            return

        zone = zones.zones[dock_zone]
        self._broadcaster = StaticTransformBroadcaster(self)
        transform = TransformStamped()
        transform.header.stamp = self.get_clock().now().to_msg()
        transform.header.frame_id = zones.frame
        transform.child_frame_id = f'{namespace}/odom'
        transform.transform.translation.x = zone.x
        transform.transform.translation.y = zone.y
        transform.transform.rotation.w = 1.0     # 평행이동만. 위 docstring 참고
        self._broadcaster.sendTransform(transform)
        self.get_logger().info(
            f'{zones.frame} -> {namespace}/odom = 도크 {dock_zone} 의 자리 '
            f'({zone.x:.3f}, {zone.y:.3f}), yaw 0(평행이동만). AMCL 이 없는 빈월드 전용이다.')

    def _load_zones(self, zones_file):
        if not zones_file:
            try:
                from ament_index_python.packages import get_package_share_directory
                zones_file = (f'{get_package_share_directory("rokey_p3_description")}'
                              '/config/zones.yaml')
            except Exception as exc:  # 패키지를 못 찾는다
                self.get_logger().error(f'zones.yaml 경로를 못 찾았다: {exc}')
                return None
        try:
            return load_zones(zones_file)
        except (OSError, ZonesError) as exc:
            self.get_logger().error(f'zones.yaml 을 못 읽었다({zones_file}): {exc}')
            return None


def main(args=None):
    """콘솔 진입점. static TF 는 한 번 내고 남아 있으면 된다."""
    rclpy.init(args=args)
    node = DockOriginTf()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
