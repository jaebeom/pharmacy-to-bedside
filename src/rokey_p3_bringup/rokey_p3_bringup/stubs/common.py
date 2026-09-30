"""스텁이 공통으로 쓰는 조각. 다른 레인 패키지는 건드리지 않는다.

스텁은 실물이 아니다. 여기서 쓰는 지름길은 전부 주석에 적는다.
가장 큰 지름길 하나: 스텁은 볼 수 없어서, 주문 풀 파일로 "어느 봉투가 어느 침상 것인가"를 안다.
실물에서는 카메라와 씬이 그것을 준다.
"""

import os

import yaml
from ament_index_python.packages import get_package_share_directory

from rokey_p3_interfaces.msg import Event
from rokey_p3_orchestrator import order_pool
from rokey_p3_orchestrator.ros_qos import latched_qos

NAMESPACE = 'amr_1'
EVENTS_TOPIC = '/events'


def default_pool_path():
    """주문 풀은 orchestration 소유다. 스텁은 읽기만 한다."""
    return os.path.join(get_package_share_directory('rokey_p3_orchestrator'),
                        'config', 'order_pool.yaml')


def load_pool_index(path):
    """주문 ID → PoolOrder."""
    with open(path, encoding='utf-8') as handle:
        orders = order_pool.load_pool(yaml.safe_load(handle))
    return {order.order_id: order for order in orders}


def cabinet_id(pool, order_id):
    """그 주문이 들어갈 보관함 프레임. 계약 3절의 <zone>/cabinet."""
    entry = pool.get(order_id)
    return f'{entry.bed}/cabinet' if entry else ''


def zone_tag_id(pool, zone_id):
    """그 구역의 인식표 QR 내용. 계약 7절."""
    if zone_id.startswith('bed_'):
        for entry in pool.values():
            if entry.bed == zone_id:
                return order_pool.patient_tag_id(entry.patient_id)
        return ''
    if zone_id.startswith('station_'):
        return order_pool.station_tag_id(zone_id)
    return ''


class EventIo:
    """/events 발행과 epoch 따라 읽기. epoch 는 orchestrator 만 발급한다(계약 4절)."""

    def __init__(self, node, robot_id, on_event=None, stamp_source=None):
        self._node = node
        self._robot_id = robot_id
        self._on_event = on_event
        # stub_sim 은 /clock 을 만들 때 use_sim_time 을 쓸 수 없어서 자기 stamp 를 준다.
        self._stamp = stamp_source or (lambda: node.get_clock().now().to_msg())
        self.epoch = 1
        self._publisher = node.create_publisher(Event, EVENTS_TOPIC, latched_qos(500))
        node.create_subscription(Event, EVENTS_TOPIC, self._receive, latched_qos(500))

    def _receive(self, msg):
        if msg.epoch > self.epoch:
            self.epoch = msg.epoch
        if self._on_event is not None:
            # 자기 이벤트도 다시 들어온다. 스텁은 자기가 내는 이름에 반응하지 않는다.
            self._on_event(msg)

    def emit(self, name, request_id='', order_id='', detail='', robot_id=''):
        """이벤트 하나. stamp 는 sim time 이다(계약 4절)."""
        msg = Event()
        msg.header.stamp = self._stamp()
        msg.name = name
        msg.request_id = request_id
        msg.order_id = order_id
        msg.robot_id = robot_id or self._robot_id
        msg.epoch = self.epoch
        msg.detail = detail
        self._publisher.publish(msg)
