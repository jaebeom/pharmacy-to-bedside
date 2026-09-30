"""상태 모니터. 구독만 하고 터미널에 1 Hz 텍스트 화면을 그린다. 화면 조립은 status_view.py 에 있다.

`ros2 run rokey_p3_orchestrator status_monitor [--once] [--no-clear] [--with-evaluator] [--robot-id amr_1]`

- 발행·서비스 호출·액션이 없다. 운영 노드에 영향을 주지 않는다.
- `/evaluator/cabinet` 은 평가 전용 경로라 기본으로 구독하지 않는다(계약 2.1절). `--with-evaluator` 일 때만.
- 그리기 타이머는 steady clock 이다. `/clock` 이 멈춰도 화면은 갱신되고 멈춤이 보인다.
- `--once` 는 latched 토픽이 들어올 틈(ONCE_COLLECT_S wall)을 준 뒤 한 번 찍고 끝낸다.
"""

import sys
import time

import rclpy
from rclpy.clock import Clock, ClockType
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.utilities import remove_ros_args
from rosgraph_msgs.msg import Clock as ClockMsg
from std_msgs.msg import Bool

from rokey_p3_interfaces.msg import BeltState, CabinetObservation, DispenserStatus, Event, OrderStatus
from rokey_p3_orchestrator import run_log, status_view
from rokey_p3_orchestrator.ros_qos import heartbeat_qos, latched_qos, sensor_qos

DRAW_PERIOD_S = 1.0
ONCE_COLLECT_S = 2.0
M0609_ID = 'm0609'


def stamp_seconds(stamp):
    return stamp.sec + stamp.nanosec * 1e-9


class StatusMonitorNode(Node):
    """status_monitor 노드."""

    def __init__(self, options, **kwargs):
        super().__init__('status_monitor', **kwargs)
        self._options = options
        self._model = status_view.StatusModel()
        robot = f'/{options.robot_id}'

        # /clock 은 R 로 발행되지만 best effort 구독은 어느 쪽 발행과도 맞는다. 값만 보면 된다.
        self.create_subscription(ClockMsg, '/clock', self._on_clock, sensor_qos(1))
        self.create_subscription(Event, '/events', self._on_event, latched_qos(500))
        self.create_subscription(OrderStatus, '/orders/status', self._on_order, latched_qos(50))
        self.create_subscription(DispenserStatus, '/pharmacy/dispenser/status', self._on_dispenser, latched_qos(1))
        for key, topic in (('arm_at_home', f'{robot}/arm/at_home'),
                           ('base_stopped', f'{robot}/base/stopped'),
                           ('gripper_holding', f'{robot}/gripper/holding'),
                           ('m0609_at_home', f'/{M0609_ID}/arm/at_home')):
            self.create_subscription(Bool, topic, self._signal_callback(key), heartbeat_qos())
        self.create_subscription(BeltState, '/pharmacy/belt', self._on_belt, heartbeat_qos())
        if options.with_evaluator:
            self.create_subscription(CabinetObservation, '/evaluator/cabinet', self._on_cabinet, latched_qos(50))

        if not options.once:
            self._draw_timer = self.create_timer(
                DRAW_PERIOD_S, self.draw, clock=Clock(clock_type=ClockType.STEADY_TIME))

    # 구독 ---------------------------------------------------------------

    def _on_clock(self, msg):
        self._model.note_clock(stamp_seconds(msg.clock), time.monotonic())

    def _on_event(self, msg):
        self._model.note_event({
            'stamp': stamp_seconds(msg.header.stamp), 'epoch': msg.epoch, 'name': msg.name,
            'request_id': msg.request_id, 'order_id': msg.order_id, 'robot_id': msg.robot_id, 'detail': msg.detail,
        })

    def _on_order(self, msg):
        self._model.note_order({'request_id': msg.request_id, 'order_id': msg.order_id,
                                'state': run_log.state_name(msg.state), 'reason': msg.reason})

    def _on_dispenser(self, msg):
        self._model.note_dispenser({
            'slots': [{'item_id': s.item_id, 'slot': s.slot, 'lot_id': s.lot_id, 'count': s.count, 'active': s.active}
                      for s in msg.slots],
            'paused_item_ids': list(msg.paused_item_ids),
            'queue_length': msg.queue_length,
            'belt_occupied': msg.belt_occupied,
        }, time.monotonic())

    def _signal_callback(self, key):
        def callback(msg):
            self._model.note_signal(key, bool(msg.data), time.monotonic())
        return callback

    def _on_belt(self, msg):
        self._model.note_signal('belt', {'occupied': msg.occupied, 'at_end': msg.at_end, 'order_id': msg.order_id},
                                time.monotonic())

    def _on_cabinet(self, msg):
        self._model.note_cabinet(msg.order_id, msg.cabinet_id, msg.present)

    # 그리기 ---------------------------------------------------------------

    def screen(self):
        return status_view.render(self._model, time.monotonic(), {'with_evaluator': self._options.with_evaluator})

    def draw(self):
        sys.stdout.write(status_view.frame(self.screen(), clear=not self._options.no_clear))
        sys.stdout.flush()


def main(args=None):
    """콘솔 진입점. Ctrl-C(SIGINT)면 조용히 끝낸다."""
    argv = remove_ros_args(sys.argv if args is None else args)[1:]
    options = status_view.parse_options(argv)
    rclpy.init(args=args)
    node = StatusMonitorNode(options)
    try:
        if options.once:
            deadline = time.monotonic() + ONCE_COLLECT_S
            while rclpy.ok() and time.monotonic() < deadline:
                rclpy.spin_once(node, timeout_sec=0.1)
            sys.stdout.write(status_view.frame(node.screen(), clear=False))
            sys.stdout.flush()
        else:
            rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
