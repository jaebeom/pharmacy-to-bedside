"""합성 요청 발행기. 주문 풀을 읽어 Deliver goal 을 낸다. 계약 1절·2.5절.

토픽이 아니라 액션 클라이언트다. 긴급 요청은 큐 맨 앞에 넣는 것으로 선점을 구현하고
진행 중인 트립은 건드리지 않는다. 순서 규칙은 order_pool.py, 언제 보낼지(리셋 뒤 대기)는
request_pacer.py 에 있고 여기는 ROS 배선만 한다.
"""

import os
import time
from functools import partial

import rclpy
import yaml
from ament_index_python.packages import get_package_share_directory
from rclpy.action import ActionClient
from rclpy.node import Node

from rokey_p3_interfaces.action import Deliver
from rokey_p3_interfaces.msg import Event, Order
from rokey_p3_orchestrator import order_pool, run_log
from rokey_p3_orchestrator.request_pacer import RequestPacer
from rokey_p3_orchestrator.ros_qos import latched_qos

DELIVER_ACTION = '/deliver'
EVENTS_TOPIC = '/events'


def default_pool_path():
    """설치된 패키지 share 의 기본 주문 풀. 경로를 하드코딩하지 않는다."""
    return os.path.join(get_package_share_directory('rokey_p3_orchestrator'),
                        'config', 'order_pool.yaml')


class OrderGeneratorNode(Node):
    """order_generator 노드. 요청을 한 건씩 보내고 결과를 기다린다."""

    def __init__(self, **kwargs):
        super().__init__('order_generator', **kwargs)
        self.declare_parameter('order_pool_file', '')
        self.declare_parameter('max_requests', 0)
        self.declare_parameter('start_delay_s', 3.0)
        self.declare_parameter('gap_s', 1.0)
        # RESET_DONE 을 본 뒤 보내지 않는 시간(wall). 계약 6절 5 의 3 s 에 여유를 더했다.
        self.declare_parameter('reset_settle_s', 3.5)

        path = self.get_parameter('order_pool_file').value or default_pool_path()
        with open(path, encoding='utf-8') as handle:
            self._orders = order_pool.load_pool(yaml.safe_load(handle))
        self._by_id = {order.order_id: order for order in self._orders}

        self._max_requests = int(self.get_parameter('max_requests').value)
        # 시작 유예와 요청 사이 간격은 실행 환경의 시계다. sim time 이 멈춰도 흘러야 한다.
        self._ready_at = time.monotonic() + float(self.get_parameter('start_delay_s').value)
        # epoch 는 orchestrator 만 발급한다(계약 4절). 발행기는 /events 로 따라 읽기만 한다.
        self._pacer = RequestPacer(order_pool.build_requests(self._orders),
                                   settle_s=float(self.get_parameter('reset_settle_s').value))
        self._sent = 0               # 지금 epoch 에서 결과까지 받은 요청 수(max_requests 와 비교)
        self._active = None          # 결과를 기다리는 request_id. v1 은 한 번에 하나
        self._drained = False
        self.last_result = None      # 마지막 Deliver 결과. L2 테스트가 읽는다

        self._client = ActionClient(self, Deliver, DELIVER_ACTION)
        self._events = self.create_subscription(Event, EVENTS_TOPIC, self._on_event, latched_qos(500))
        self._timer = self.create_timer(max(0.1, float(self.get_parameter('gap_s').value)), self._tick)
        self.get_logger().info(
            f'order_generator up. 주문 {len(self._orders)}건, 요청 {len(self._pacer.queue)}건, 풀 {path}')

    def _on_event(self, msg):
        """리셋으로 epoch 가 오르면 seq 를 1부터 다시 세고 큐를 다시 채운다(계약 6절 3).

        RESET_DONE 을 본 뒤 reset_settle_s 동안은 보내지 않는다. orchestrator 가 barrier 동안 거부하고
        거부된 요청은 버려지기 때문이다(계약 2.5절·6절 5).
        """
        previous = self._pacer.epoch
        if self._pacer.observe(msg.name, msg.epoch, time.monotonic()):
            self.get_logger().info(f'epoch {previous} -> {msg.epoch}. 요청 큐를 다시 채운다.')
            self._sent = 0
            self._drained = False

    def _tick(self):
        """다음 요청 하나를 보낸다. v1 은 진행 중 트립이 하나뿐이다."""
        now = time.monotonic()
        if self._active or now < self._ready_at:
            return
        if self._max_requests and self._sent >= self._max_requests:
            self._announce_drained(f'max_requests={self._max_requests} 만큼 보냈다. 더 안 보낸다.')
            return
        if not self._pacer.queue:
            self._announce_drained('요청 큐가 비었다.')
            return
        holding = self._pacer.holding(now)
        if holding:
            self.get_logger().info(f'요청을 보내지 않는다: {holding}', throttle_duration_sec=1.0)
            return
        if not self._client.server_is_ready():
            self.get_logger().warning(f'{DELIVER_ACTION} 서버를 기다린다.', throttle_duration_sec=5.0)
            return

        epoch = self._pacer.epoch
        request_id, pending = self._pacer.take(now)
        self._active = request_id
        goal = self._build_goal(request_id, pending)
        self.get_logger().info(
            f'{goal.request.request_id} 보냄. mode={pending.mode} '
            f'destination={pending.destination_id} orders={list(pending.order_ids)}')
        self._client.send_goal_async(goal).add_done_callback(partial(self._on_goal_response, request_id, epoch))

    def _announce_drained(self, message):
        if not self._drained:
            self._drained = True
            self.get_logger().info(message)

    def _build_goal(self, request_id, pending):
        goal = Deliver.Goal()
        request = goal.request
        request.header.stamp = self.get_clock().now().to_msg()
        request.request_id = request_id
        request.mode = pending.mode_value
        request.destination_id = pending.destination_id
        request.orders = [self._order_msg(order_id) for order_id in pending.order_ids]
        return goal

    def _order_msg(self, order_id):
        entry = self._by_id[order_id]
        return Order(order_id=entry.order_id, patient_id=entry.patient_id, item_id=entry.item_id)

    def _on_goal_response(self, request_id, epoch, future):
        handle = future.result()
        if not handle.accepted:
            # 계약 2.5절: 거부는 goal 거부로 끝난다. 이벤트도 지표 분모도 없다.
            self.get_logger().error(f'{request_id} Deliver goal 이 거부됐다. 다음 요청으로 넘어간다.')
            self._release(request_id)
            return
        handle.get_result_async().add_done_callback(partial(self._on_result, request_id, epoch))

    def _on_result(self, request_id, epoch, future):
        """보낸 수는 그 요청을 보낸 epoch 가 지금 epoch 일 때만 센다.

        트립 도중 리셋하면 끊긴 요청의 abort 결과가 epoch 상승(보낸 수 0) 뒤에 올 수 있다. 그것을 세면
        새 epoch 가 요청 한 건도 안 보내고 max_requests 에 닿는다(마클 실측, main fd13a46).
        """
        result = future.result().result
        self.last_result = result
        states = ', '.join(f'{order.order_id}={run_log.state_name(order.state)}'
                           for order in result.orders)
        self.get_logger().info(f'{request_id} Deliver 결과 success={result.success} [{states}]')
        if epoch == self._pacer.epoch:
            self._sent += 1
        else:
            self.get_logger().info(
                f'{request_id} 는 epoch {epoch} 의 요청이다. epoch {self._pacer.epoch} 의 보낸 수에 세지 않는다.')
        self._release(request_id)

    def _release(self, request_id):
        if self._active == request_id:
            self._active = None


def main(args=None):
    """콘솔 진입점."""
    rclpy.init(args=args)
    node = OrderGeneratorNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
