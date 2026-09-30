"""스텁 인식. pouch_detector 를 계약과 같은 이름으로 대신한다(계약 8절).

내는 것: /amr_1/hand_camera/tag_reads, /amr_1/hand_camera/pouches, 이벤트 POUCH_DETECTED.

스텁은 볼 수 없다. 그래서 무엇이 보이는지를 /events 와 주문 풀 파일로 흉내 낸다.

- POUCH_LOADED 를 보면 그 봉투가 상판에 있다고 본다. POUCH_PLACED 면 없어진 것이다.
- ARRIVED 를 보면 그 정거장의 인식표가 보인다고 본다. 정거장은 상판 첫 봉투의 침상이다.
  병동 묶음(mode 3)은 정거장이 스테이션 하나라 그 스테이션 인식표(st-<zone>)다. 요청의 모드와 목적지는
  REQUEST_ACCEPTED.detail 에서 읽는다 — 안 그러면 스텁 팔이 st- 를 기다리는데 pt- 를 보여 늘 AUTH_FAIL 이다.
- AUTH_OK 뒤부터 상판 봉투를 검출한 것으로 본다. 계약 2.6절의 POUCH_DETECTED 자리다.

검출이 0건이어도 빈 배열을 낸다. 안 내는 것이 아니다(계약 2.4절).
"""

import json

import rclpy
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node

from rokey_p3_bringup.shutdown import spin_until_interrupted
from rokey_p3_bringup.stubs import common
from rokey_p3_interfaces.msg import PouchDetection, PouchDetectionArray, TagRead
from rokey_p3_orchestrator import order_pool
from rokey_p3_orchestrator.ros_qos import reliable_qos

CAMERA_FRAME = f'{common.NAMESPACE}/hand_camera_optical'


def ward_station(detail):
    """REQUEST_ACCEPTED.detail(JSON) 이 병동 묶음이면 그 스테이션 zone, 아니면 ''. 못 읽어도 ''."""
    try:
        request = json.loads(detail or '')
    except ValueError:
        return ''
    if not isinstance(request, dict) or request.get('mode') != order_pool.MODE_BATCH_WARD:
        return ''
    destination = request.get('destination_id')
    return destination if isinstance(destination, str) and destination.startswith('station_') else ''


class StubDetector(Node):
    """stub_detector 노드."""

    def __init__(self, **kwargs):
        super().__init__('stub_detector', **kwargs)
        self.declare_parameter('order_pool_file', '')
        self.declare_parameter('rate_hz', 5.0)
        self._pool = common.load_pool_index(
            self.get_parameter('order_pool_file').value or common.default_pool_path())

        self._on_deck = []
        self._station = ''   # 진행 중 요청이 병동 묶음이면 그 스테이션
        self._tag_id = ''
        self._visible = False

        self._tag_pub = self.create_publisher(
            TagRead, f'/{common.NAMESPACE}/hand_camera/tag_reads', reliable_qos())
        self._pouch_pub = self.create_publisher(
            PouchDetectionArray, f'/{common.NAMESPACE}/hand_camera/pouches', reliable_qos(5))
        self._events = common.EventIo(self, common.NAMESPACE, self._on_event)
        self.create_timer(1.0 / float(self.get_parameter('rate_hz').value), self._publish)
        self.get_logger().info('stub_detector up. tag_reads 와 pouches.')

    def _on_event(self, msg):
        if msg.name == 'REQUEST_ACCEPTED':
            self._station = ward_station(msg.detail)
        elif msg.name == 'POUCH_LOADED' and msg.order_id not in self._on_deck:
            self._on_deck.append(msg.order_id)
        elif msg.name == 'POUCH_PLACED' and msg.order_id in self._on_deck:
            self._on_deck.remove(msg.order_id)
        elif msg.name == 'ARRIVED':
            self._tag_id = self._stop_tag()
            self._visible = False
        elif msg.name == 'AUTH_OK':
            self._visible = True
            for order_id in self._on_deck:
                self._events.emit('POUCH_DETECTED', order_id=order_id)
        elif msg.name in ('DEPARTED', 'AUTH_FAIL', 'RETURNED'):
            self._tag_id = ''
            self._visible = False
        elif msg.name == 'RESET_DONE':
            self._on_deck.clear()
            self._station = ''
            self._tag_id = ''
            self._visible = False

    def _stop_tag(self):
        if not self._on_deck:
            return ''
        if self._station:
            return order_pool.station_tag_id(self._station)
        entry = self._pool.get(self._on_deck[0])
        return common.zone_tag_id(self._pool, entry.bed) if entry else ''

    def _publish(self):
        stamp = self.get_clock().now().to_msg()
        if self._tag_id:
            tag = TagRead()
            tag.header.stamp = stamp
            tag.header.frame_id = CAMERA_FRAME
            tag.kind = (TagRead.KIND_STATION if self._tag_id.startswith('st-')
                        else TagRead.KIND_PATIENT)
            tag.tag_id = self._tag_id
            tag.status = TagRead.STATUS_OK
            self._tag_pub.publish(tag)

        array = PouchDetectionArray()
        array.header.stamp = stamp
        array.header.frame_id = CAMERA_FRAME
        if self._visible:
            for order_id in self._on_deck:
                detection = PouchDetection()
                detection.header.stamp = stamp
                detection.header.frame_id = CAMERA_FRAME
                detection.order_id = order_id
                detection.confidence = 1.0
                detection.slot_index = -1
                array.detections.append(detection)
        self._pouch_pub.publish(array)


def main(args=None):
    """콘솔 진입점."""
    rclpy.init(args=args)
    node = StubDetector()
    # 액션 실행 콜백이 스레드를 오래 잡는다. 코어 수가 적은 기계에서도 굶지 않게 고정한다.
    executor = MultiThreadedExecutor(num_threads=8)
    executor.add_node(node)
    spin_until_interrupted(node, executor)


if __name__ == '__main__':
    main()
