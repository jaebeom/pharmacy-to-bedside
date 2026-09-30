"""run 기록기. /events, /orders/status, /evaluator/cabinet 을 run 별 JSONL 로. 계약 1절·8절.

SUCCESS 는 /evaluator/cabinet 관측으로만 쓴다. 오케스트레이터의 DELIVERED 는 주장이라
관측이 없으면 ABORT(eval_not_observed)로 닫는다. 판정 규칙은 run_log.py 에 있다.
평가 경로는 이 노드만 구독한다. 운영 노드는 구독하지 않는다(계약 2.1절).

원본 로그는 저장소 밖에 쓴다(docs/process/repository-rules.md). 기본 위치는 $ROS_HOME/rokey_p3/runs 다.
evidence/runs/ 의 증거 기록은 사람이 이 파일들을 보고 따로 만든다.

epoch 가 오르면 새 run 을 열고 이전 run 은 run_drain_s(wall) 동안 열어 둔다. 토픽마다 도착 순서가 달라서
이전 요청의 늦은 주문 상태·RESET_DONE 전 보관함 관측이 새 run 에 섞이지 않게 한다(run_log.RunBook).

run 은 종료 경로마다 한 번 닫는다(orders.jsonl·meta.json). drain 중인 이전 run 도 같이 닫는다.
SIGINT·SIGTERM 은 rclpy 가 받아 spin 이 끝나고, SIGHUP(tmux 창을 닫을 때)은 이 노드가 받는다. SIGKILL 은 막을 수 없다.
SIGHUP 처리기는 Python 처리기라 spin 이 깨어나야 돈다. 그래서 steady clock 타이머로 spin 을 주기적으로 깨운다.
launch 는 SIGTERM 을 받으면 자식에게 신호를 보내지 않고 끝난다. 그러면 이 노드는 신호를 못 받는다.
launch 는 SIGINT 로 내린다(README).
"""

import datetime
import os
import re
import signal
import socket
import time

import rclpy
from rclpy.clock import Clock, ClockType
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node

from rokey_p3_interfaces.msg import CabinetObservation, Event, OrderStatus
from rokey_p3_orchestrator import run_log
from rokey_p3_orchestrator.ros_qos import latched_qos

EVENTS_TOPIC = '/events'
ORDER_STATUS_TOPIC = '/orders/status'
CABINET_TOPIC = '/evaluator/cabinet'

_HOST_BAD = re.compile(r'[^a-z0-9-]+')

#: 닫는 동안 무시하는 신호. 두 번째 Ctrl-C 가 orders.jsonl 을 반쯤 쓴 채로 끊지 않게 한다.
CLOSE_SIGNALS = (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)

#: spin 을 깨우는 주기(wall). SIGHUP 을 받고 run 을 닫기까지 최대 이만큼 늦다.
WAKE_PERIOD_S = 0.5


class Hangup(Exception):
    """SIGHUP. 터미널(tmux 창)이 닫혔다. rclpy 는 이 신호를 받지 않는다."""


def raise_hangup(signum, frame):
    """SIGHUP 을 main 스레드의 예외로 바꾼다. 기본 동작이면 run 을 닫지 못하고 죽는다."""
    raise Hangup()


def default_log_dir():
    """원본 로그 위치. 저장소 안에 쓰지 않는다."""
    ros_home = os.environ.get('ROS_HOME') or os.path.join(os.path.expanduser('~'), '.ros')
    return os.path.join(ros_home, 'rokey_p3', 'runs')


def sanitize_host(name):
    """naming.md 의 host 부분으로 쓸 수 있게 다듬는다."""
    cleaned = _HOST_BAD.sub('-', (name or '').lower()).strip('-')[:32]
    return cleaned or 'unknown'


def stamp_seconds(stamp):
    """header.stamp 를 초 단위 실수로. 지표는 이 값의 차이다(계약 4절)."""
    return stamp.sec + stamp.nanosec * 1e-9


class EventLoggerNode(Node):
    """event_logger 노드. run 하나가 디렉토리 하나다. run 경계·판정은 run_log.RunBook 이 정한다."""

    def __init__(self, **kwargs):
        super().__init__('event_logger', **kwargs)
        self.declare_parameter('log_dir', '')
        self.declare_parameter('run_host', '')
        # epoch 가 오른 뒤 이전 run 이 늦은 주문 상태·이벤트·관측을 받는 시간(wall).
        self.declare_parameter('run_drain_s', 2.0)

        root = self.get_parameter('log_dir').value or default_log_dir()
        host = sanitize_host(self.get_parameter('run_host').value or socket.gethostname())
        self._book = run_log.RunBook(
            root, host, float(self.get_parameter('run_drain_s').value),
            now_utc=lambda: datetime.datetime.now(datetime.timezone.utc),
            nonce=lambda: os.urandom(4).hex(),
            log=lambda text: self.get_logger().info(text))

        self.create_subscription(Event, EVENTS_TOPIC, self._on_event, latched_qos(500))
        self.create_subscription(OrderStatus, ORDER_STATUS_TOPIC, self._on_order_status, latched_qos(50))
        self.create_subscription(CabinetObservation, CABINET_TOPIC, self._on_cabinet, latched_qos(50))
        self._start_wake_timer()

    def _start_wake_timer(self):
        """SIGHUP 처리기가 돌 틈을 만들고, drain 이 끝난 이전 run 을 닫는다.

        signal.signal 로 건 Python 처리기는 main 스레드가 인터프리터로 돌아와야 돈다. rclpy.spin 은 받을 것이
        없으면 rcl_wait 안에서 무기한 기다리므로, 다른 노드가 다 죽은 뒤에는 처리기가 안 돌고 run 을 못 닫는다
        (정비 4호: tmux kill-window 뒤 20 s 넘게 멈췄고 /events 한 건을 보내자 끝났다).
        SIGINT·SIGTERM 은 rclpy 의 C 처리기가 guard 를 직접 깨워서 이 문제가 없다. rclpy 에는 SIGHUP 을
        더 거는 API 가 없고, 처리기 안에서 guard 를 깨우는 것은 처리기가 돌아야 하므로 소용없다.
        노드 clock 은 use_sim_time 이면 sim time 이라 /clock 이 멈추면 타이머도 멈춘다. 그래서 steady clock 이다.
        """
        self._wake_timer = self.create_timer(
            WAKE_PERIOD_S, self._wake, clock=Clock(clock_type=ClockType.STEADY_TIME))

    def _wake(self):
        """spin 이 돌아오게 하고, 메시지가 없어도 drain 마감이 지난 이전 run 을 닫는다(최대 WAKE_PERIOD_S 늦게)."""
        self._book.expire(time.monotonic())

    def close(self):
        """열려 있는 run 을 모두 닫는다(drain 중인 이전 run 포함). 종료 경로에서 부른다. 두 번째는 아무것도 안 한다."""
        self._book.close_all()

    # 구독 ---------------------------------------------------------------

    def _on_event(self, msg):
        self._book.event({
            'stamp': stamp_seconds(msg.header.stamp),
            'epoch': msg.epoch,
            'name': msg.name,
            'request_id': msg.request_id,
            'order_id': msg.order_id,
            'robot_id': msg.robot_id,
            'detail': msg.detail,
        }, time.monotonic())

    def _on_order_status(self, msg):
        self._book.order_status({
            'stamp': stamp_seconds(msg.header.stamp),
            'request_id': msg.request_id,
            'order_id': msg.order_id,
            'state': run_log.state_name(msg.state),
            'reason': msg.reason,
        }, time.monotonic())

    def _on_cabinet(self, msg):
        """평가 전용 경로. run 기록의 SUCCESS 는 여기서만 나온다(계약 2.1절·8절)."""
        self._book.cabinet({
            'stamp': stamp_seconds(msg.header.stamp),
            'cabinet_id': msg.cabinet_id,
            'order_id': msg.order_id,
            'present': msg.present,
        }, time.monotonic())


def main(args=None):
    """콘솔 진입점. 어느 종료 경로로 나가도 run 을 한 번 닫는다.

    - SIGINT: rclpy 처리기가 Python 처리기로 넘겨 KeyboardInterrupt 가 난다.
    - SIGTERM: rclpy 처리기가 context 를 내린다. spin 이 돌아오거나 ExternalShutdownException 이 난다.
    - SIGHUP: raise_hangup 이 Hangup 을 낸다.
    """
    rclpy.init(args=args)
    signal.signal(signal.SIGHUP, raise_hangup)
    node = EventLoggerNode()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException, Hangup):
        pass
    finally:
        for signum in CLOSE_SIGNALS:
            signal.signal(signum, signal.SIG_IGN)
        node.close()
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
