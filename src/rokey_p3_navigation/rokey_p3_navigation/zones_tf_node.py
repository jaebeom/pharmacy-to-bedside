"""zones_tf: zones.yaml 의 고정 프레임을 /tf_static 으로 1회 낸다. 계약 v1 3절.

- `pharmacy/<이름>` (`belt_end`, `shelf`, `dispenser_slot_a`, `dispenser_slot_b`)
- `<zone>/cabinet`, `<zone>/tag` (예: `bed_a1/cabinet`)

전부 `map` 의 자식이다. 한 부모→자식 변환의 작성자는 하나이고, 이 변환들의 작성자는 이 노드다.
Isaac 은 `map`·`odom` 을 내지 않고, `base_link` 아래 프레임만 낸다.
"""

import rclpy
from geometry_msgs.msg import TransformStamped
from rclpy.node import Node
from tf2_ros import StaticTransformBroadcaster

from rokey_p3_navigation.base_kinematics import yaw_to_quaternion
from rokey_p3_navigation.zones import ZonesError, load_zones


class ZonesTf(Node):
    """zones.yaml 을 읽어 고정 프레임을 낸다."""

    def __init__(self):
        super().__init__('zones_tf')

        zones_file = self.declare_parameter('zones_file', '').value
        self._broadcaster = StaticTransformBroadcaster(self)

        zones = self._load_zones(zones_file)
        if zones is None:
            return
        transforms = self._transforms(zones)
        if not transforms:
            self.get_logger().warn('낼 고정 프레임이 없다. zones.yaml 의 cabinet·tag·pharmacy 를 확인한다.')
            return
        self._broadcaster.sendTransform(transforms)
        self.get_logger().info(
            f'{zones.frame} 아래 고정 프레임 {len(transforms)}개: '
            f'{[transform.child_frame_id for transform in transforms]}')

    def _load_zones(self, zones_file):
        if not zones_file:
            try:
                from ament_index_python.packages import get_package_share_directory
                share = get_package_share_directory('rokey_p3_description')
            except Exception as exc:  # 패키지를 못 찾는다
                self.get_logger().error(f'zones.yaml 경로를 못 찾았다: {exc}')
                return None
            zones_file = f'{share}/config/zones.yaml'
        try:
            return load_zones(zones_file)
        except (OSError, ZonesError) as exc:
            self.get_logger().error(f'zones.yaml 을 못 읽었다({zones_file}): {exc}')
            return None

    def _transforms(self, zones):
        """`pharmacy/*` 와 구역의 `cabinet`·`tag` 를 `map` 의 자식으로 만든다."""
        stamp = self.get_clock().now().to_msg()
        transforms = []
        for name, pose in sorted(zones.pharmacy.items()):
            transforms.append(self._transform(stamp, zones.frame, f'pharmacy/{name}', pose))
        for zone_id, zone in sorted(zones.zones.items()):
            for suffix, pose in (('cabinet', zone.cabinet), ('tag', zone.tag)):
                if pose is not None:
                    transforms.append(
                        self._transform(stamp, zones.frame, f'{zone_id}/{suffix}', pose))
        return transforms

    @staticmethod
    def _transform(stamp, parent, child, pose):
        transform = TransformStamped()
        transform.header.stamp = stamp
        transform.header.frame_id = parent
        transform.child_frame_id = child
        transform.transform.translation.x = pose.x
        transform.transform.translation.y = pose.y
        transform.transform.translation.z = pose.z
        (transform.transform.rotation.x, transform.transform.rotation.y,
         transform.transform.rotation.z,
         transform.transform.rotation.w) = yaw_to_quaternion(pose.yaw)
        return transform


def main(args=None):
    """콘솔 진입점. 발행은 1회지만 transient local 이라 늦게 붙은 구독자도 받는다."""
    rclpy.init(args=args)
    node = ZonesTf()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
