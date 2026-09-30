"""기동 조합. 뼈대 launch. orchestration 담당 소유.

뼈대 노드다. 기동해서 로그 한 줄을 남기고 spin 한다. 실제 동작은 아직 없다.
"""

import rclpy
from rclpy.node import Node

from rokey_p3_bringup.shutdown import spin_until_interrupted


class BringupCheck(Node):
    """bringup_check 노드."""

    def __init__(self):
        super().__init__('bringup_check')
        self.get_logger().info('bringup_check up. 기동 조합 확인 로직은 아직 없다.')


def main(args=None):
    """콘솔 진입점."""
    rclpy.init(args=args)
    node = BringupCheck()
    spin_until_interrupted(node)


if __name__ == '__main__':
    main()
