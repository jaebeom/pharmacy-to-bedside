"""Deliver 서버와 트립 FSM 배선. 계약 1절·2.5절·5절·6절, ADR 0001.

이 파일에는 판단이 없다. 입력을 FSM 에 넣고 FSM 이 돌려준 명령을 ROS 로 옮긴다.
상태·전이·guard·이벤트 순서는 trip_fsm.py 에, 재고 규칙은 dispenser_inventory.py 에,
보충(Refill) 판단은 refill_planner.py 에 있다. 보충은 트립 FSM 밖에서 트립과 병렬로 돈다.

- 인터락 사전 확인은 FSM 의 guard 다. 실행하는 쪽(fleet, arm)도 같은 조건을 본다(계약 5절, 이중).
- epoch 는 이 노드만 발급한다(계약 4절). 리셋마다 +1 이고 /orchestrator/reset 요청의 epoch 는 쓰지 않는다.
  이전 epoch 의 액션 결과는 버린다.
- SUCCESS 는 내지 않는다. 주장은 DELIVERED 까지이고 판정은 event_logger 가 한다(계약 8절).
- 액션 서버·서비스가 아직 안 보이면 거부가 아니라 unknown 이다(계약 5절). server_wait_s(wall) 까지
  기다렸다 보내고, 넘으면 그때 거부로 넣는다. /sim/reset 호출은 reset_timeout_s 전체를 서버 탐색에 쓴다.
- goal·호출은 token(epoch, owner, seq) 으로 추적한다. 결과는 그 token 으로 FSM·보충 클라이언트에 넣고,
  goal 표에서도 그 token 항목만 지운다. 수락 전에 cancel 을 받으면 기억했다가 수락되자마자 cancel 하고
  결과(종결)까지 본다. 결과는 액션 wrapper status(CANCELED·ABORTED)를 payload 보다 먼저 본다.
- 리셋 barrier v2(계약 6절): /orchestrator/reset 은 곧바로 ok 를 돌려주고(barrier 완료가 아니다), FSM 이
  끊긴 주문 종료 → RESET_BEGIN → drain → /sim/reset → 재고 다시 읽기·RESET_DONE 을 차례로 낸다. 노드는 goal 표의
  token 을 drain 으로 넘기고, 종결(결과·거부)을 epoch 와 상관없이 FSM 에 알린다.
"""

import contextlib
import os
import threading
import time
from dataclasses import dataclass
from functools import partial

import rclpy
import yaml
from action_msgs.msg import GoalStatus
from ament_index_python.packages import get_package_share_directory
from rclpy.action import ActionClient, ActionServer, CancelResponse, GoalResponse
from rclpy.callback_groups import MutuallyExclusiveCallbackGroup, ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from rclpy.time import Time
from std_msgs.msg import Bool, String

from rokey_p3_interfaces.action import Deliver, GoToZone, PickPouch, Refill, ScanTag
from rokey_p3_interfaces.msg import (ArmClearance, BeltObservation, BeltState, DeliveryRequest, DispenserSlot,
                                     DispenserStatus, Event, OrderStatus, TagRead)
from rokey_p3_interfaces.srv import CheckContainer, Dispense, Reset
from rokey_p3_navigation import alerts
from rokey_p3_navigation.zones import is_zone_id
from rokey_p3_orchestrator import order_pool, pharmacy_db, refill_planner, trip_fsm, wait_report
from rokey_p3_orchestrator.dispenser_inventory import load_inventory
from rokey_p3_orchestrator.ros_qos import heartbeat_qos, latched_qos, reliable_qos

DEFAULT_ROBOT_ID = 'amr_1'
#: Deliver 실행이 트립 끝을 기다리며 종료 여부를 보는 주기(wall).
DELIVER_POLL_S = 0.2
#: close() 가 Deliver 실행이 abort 를 마치기를 기다리는 상한(wall). 액션 서버를 내리기 전에 abort 가 나가게 한다.
CLOSE_WAIT_S = 1.0
STATE_FRESH_S = 1.0          # 계약 4절: 상태 토픽(H)의 신선도는 wall 로 잰다
RESET_SETTLE_S = 3.0         # 계약 6절 5: RESET_DONE 뒤 3 s wall

MODE_NAMES = {
    DeliveryRequest.MODE_SINGLE: trip_fsm.MODE_SINGLE,
    DeliveryRequest.MODE_URGENT: trip_fsm.MODE_URGENT,
    DeliveryRequest.MODE_BATCH_ROOM: trip_fsm.MODE_BATCH_ROOM,
    DeliveryRequest.MODE_BATCH_WARD: trip_fsm.MODE_BATCH_WARD,
}

# OrderStatus.msg 의 값. STATE_SUCCESS(10) 는 없다. 오케스트레이터는 그것을 발행하지 않는다.
ORDER_STATE_VALUES = {
    trip_fsm.ORDER_ACCEPTED: OrderStatus.STATE_ACCEPTED,
    trip_fsm.ORDER_DISPENSED: OrderStatus.STATE_IN_PROGRESS,
    trip_fsm.ORDER_LOADED: OrderStatus.STATE_IN_PROGRESS,
    trip_fsm.ORDER_DELIVERED: OrderStatus.STATE_DELIVERED,
    'HOLD_RETURN': OrderStatus.STATE_HOLD_RETURN,
    'ABORT': OrderStatus.STATE_ABORT,
    'TIMEOUT': OrderStatus.STATE_TIMEOUT,
}

TAG_KINDS = {trip_fsm.KIND_PATIENT: TagRead.KIND_PATIENT,
             trip_fsm.KIND_STATION: TagRead.KIND_STATION}

PICK_SOURCES = {trip_fsm.SOURCE_BELT: PickPouch.Goal.SOURCE_BELT,
                trip_fsm.SOURCE_DECK: PickPouch.Goal.SOURCE_DECK}


def share_config(name):
    """설치된 패키지 share 의 설정 파일. 경로를 하드코딩하지 않는다."""
    return os.path.join(get_package_share_directory('rokey_p3_orchestrator'), 'config', name)


def read_yaml(path):
    """YAML 한 파일."""
    with open(path, encoding='utf-8') as handle:
        return yaml.safe_load(handle)


class ServerWait:
    """아직 안 보이는 액션 서버·서비스로 갈 명령을 잡아 둔다. ROS 를 모른다.

    discovery 는 부하가 있거나 PC 가 여러 대면 몇 초 늦는다. 그 사이의 명령을 거부로 세면
    재시도 두 번이 금방 지나가 주문이 닫힌다. token 마다 명령 하나를 둔다. 같은 액션의 다른 token 을
    덮거나 지우지 않는다. 시간은 wall 이다(계약 4절: 서비스 응답·단절 판정은 수신 쪽 wall).
    """

    def __init__(self, limit_s):
        self.limit_s = float(limit_s)
        self._held = {}          # token → (명령, 잡은 시각, 기다리는 시간)

    def tokens(self):
        """기다리는 token."""
        return tuple(self._held)

    def hold(self, token, command, now, limit_s=None):
        """limit_s 를 주면 이 명령만 그 시간까지 기다린다(없으면 limit_s)."""
        self._held[token] = (command, now, self.limit_s if limit_s is None else float(limit_s))

    def drop(self, token):
        """그 token 만 버린다. 있었으면 True."""
        return self._held.pop(token, None) is not None

    def due(self, epoch, now, ready):
        """(보낼 것, 거부할 것, 버릴 것). ready(명령) 가 True 면 보낸다. epoch 가 바뀐 token 은 버린다."""
        send, expired, stale = [], [], []
        for token, (command, since, limit_s) in list(self._held.items()):
            if token.epoch != epoch:
                stale.append(command)
            elif ready(command):
                send.append(command)
            elif now - since >= limit_s:
                expired.append(command)
            else:
                continue
            del self._held[token]
        return send, expired, stale


@dataclass
class GoalEntry:
    """보낸(또는 서버를 기다리는) goal 하나. handle 은 수락되면 생긴다."""

    action: str
    handle: object = None
    cancel_requested: bool = False
    #: 보충 goal 의 품목. `refill_overlap done` 이 **그 goal 의** 품목을 적게 goal 마다 들고 있는다.
    item_id: str = ''


class OrchestratorNode(Node):
    """orchestrator 노드. Deliver 서버 하나, 트립 FSM 하나."""

    def __init__(self, **kwargs):
        super().__init__('orchestrator', **kwargs)
        self.declare_parameter('robot_id', DEFAULT_ROBOT_ID)
        # 액션 서버·서비스가 안 보일 때 거부로 보기 전에 기다리는 시간(wall).
        self.declare_parameter('server_wait_s', 10.0)
        self.declare_parameter('order_pool_file', '')
        self.declare_parameter('dispenser_file', '')
        # 구역 파일. 병실 테이블(kind station + room)이 있으면 병실 묶음을 그 테이블 한 곳에 놓는다(재범 9/25).
        # 비우면 예전처럼 병실 묶음이 침상마다 선다.
        self.declare_parameter('zones_file', '')
        self.declare_parameter('load_zone', 'load')
        self.declare_parameter('dock_zone', 'dock_1')
        self.declare_parameter('arriving_distance_m', 3.0)
        self.declare_parameter('trip_limit_s', 600.0)
        # true 면 조제실 구간만 돈다. 적재 뒤 도크로 복귀하고 실은 주문은 HOLD_RETURN 이다.
        self.declare_parameter('pharmacy_only', False)
        # cancel 한 goal 의 종결을 기다리는 상한(wall). 대체 goal·리셋 drain 이 같이 쓴다(계약 6절 1).
        self.declare_parameter('cancel_wait_s', 10.0)
        # /sim/reset 응답을 기다리는 상한(wall). 넘으면 리셋 실패로 멈춘다(계약 7절).
        self.declare_parameter('reset_timeout_s', 30.0)
        # 계약 11.3·11.6 관측 guard(시험용, 기본 꺼짐). 켜면 /pharmacy/belt/observation 과 <robot>/arm/clear_of_belt 를
        # 구독하고, 피킹·다음 배출에 그 관측을 더 요구한다(trip_fsm.TripConfig.observation_guard).
        # ArmClearance 의 CLEAR 는 L3 에서 FK 와 TCP 를 대조하기 전에는 믿지 않는다(계약 11.6).
        self.declare_parameter('observation_guard', False)
        # AMR 상판에 실을 수 있는 봉투 수. 자리가 없으면 그 주문은 deck_full 로 닫는다.
        # 기본 5 는 칸막이 다섯이던 상판이고, 통짜 트레이는 셋이다(시뮬 #445). 장면마다 다르다.
        self.declare_parameter('deck_slots', 5)
        # 조제 뒤 봉투가 벨트 끝에 닿기를 기다리는 시한(sim s). 빈월드 벨트는 몇 초지만, 병원 씬 컨베이어는
        # 스폰에서 A1 롤러 끝까지 약 35 s 다(실습38 probe06 34.567 s) — 기본 20 이면 병원에서는 ABORT 가 확정이다.
        self.declare_parameter('belt_timeout_s', 20.0)
        self.declare_parameter('dispense_while_dispatching', False)
        self._robot_id = str(self.get_parameter('robot_id').value or DEFAULT_ROBOT_ID)

        self._pool_path = self.get_parameter('order_pool_file').value or share_config('order_pool.yaml')
        self._dispenser_path = (self.get_parameter('dispenser_file').value
                                or share_config('dispenser.yaml'))
        self._pool = {order.order_id: order
                      for order in order_pool.load_pool(read_yaml(self._pool_path))}

        self._lock = threading.RLock()
        self._epoch = 1
        self._accept_after = 0.0
        self._used_requests = set()
        self._used_orders = set()
        self._states = {}
        self._pushed = {}
        self._observed = {}              # 관측 이름 → 마지막으로 앞으로 간 (epoch, seq)
        self._goals = {}              # token → GoalEntry. 결과가 오면 그 token 만 지운다
        self._drain_tokens = []       # 진행 중 리셋 drain 이 기다리는 token. drain 이 끝나면 비운다
        self._unsent_cancels = []     # 보내기 전에 cancel 한 goal. 다음 tick 에 종결로 알린다
        self._status = {}
        self._deliver_done = threading.Event()
        self._closing = threading.Event()     # 노드를 내리는 중. Deliver 실행이 기다림을 풀고 abort 한다
        self._deliver_idle = threading.Event()  # Deliver 실행 콜백이 돌고 있지 않다
        self._deliver_idle.set()
        self._deliver_result = None
        self._server_wait = ServerWait(float(self.get_parameter('server_wait_s').value))

        self._fsm = trip_fsm.TripFsm(
            config=trip_fsm.TripConfig(
                load_zone=str(self.get_parameter('load_zone').value),
                dock_zone=str(self.get_parameter('dock_zone').value),
                load_at_dock=self._load_at_dock(),
                dispense_while_dispatching=bool(self.get_parameter('dispense_while_dispatching').value),
                arriving_distance_m=float(self.get_parameter('arriving_distance_m').value),
                trip_limit_s=float(self.get_parameter('trip_limit_s').value),
                pharmacy_only=bool(self.get_parameter('pharmacy_only').value),
                cancel_wait_s=float(self.get_parameter('cancel_wait_s').value),
                reset_timeout_s=float(self.get_parameter('reset_timeout_s').value),
                observation_guard=bool(self.get_parameter('observation_guard').value),
                deck_slots=int(self.get_parameter('deck_slots').value),
                belt_timeout_s=float(self.get_parameter('belt_timeout_s').value)),
            inventory=load_inventory(read_yaml(self._dispenser_path)),
            patient_beds={order.patient_id: order.bed for order in self._pool.values()},
            **self._room_maps())

        # 보충 클라이언트. 트립 FSM 밖에서 트립과 병렬로 돈다(refill_planner.py).
        self.declare_parameter('refill_retry_delay_s', 5.0)
        self.declare_parameter('refill_max_attempts', 3)
        # 장착한 캐니스터의 로트·유통기한·수량은 재고 파일의 선반에서 꺼낸다(A 안, 계약 2.1절 끝).
        # 리셋은 _fsm.inventory 를 파일에서 다시 읽으므로 선반도 함께 돌아간다.
        self._refill = refill_planner.RefillPlanner(
            self._fsm.inventory, source=refill_planner.ShelfSource(lambda: self._fsm.inventory),
            retry_delay_s=float(self.get_parameter('refill_retry_delay_s').value),
            max_attempts=int(self.get_parameter('refill_max_attempts').value),
            epoch=self._epoch,
            cancel_wait_s=float(self.get_parameter('cancel_wait_s').value))

        # 약 DB(QR·DB·카메라 계약 2절). 기본 꺼짐. 켜면 보충 전 약통 확인 서비스를 낸다(계약 2.3).
        self.declare_parameter('pharmacy_db', False)
        self.declare_parameter('pharmacy_catalog_file', '')
        self.declare_parameter('pharmacy_db_path', '')     # 비우면 메모리(run 이 끝나면 없어진다)
        self.declare_parameter('pharmacy_today', '')       # 비우면 카탈로그의 today
        self._db = self._open_pharmacy_db() if bool(self.get_parameter('pharmacy_db').value) else None

        group = ReentrantCallbackGroup()
        namespace = f'/{self._robot_id}'
        # 트립이 guard 로 멈춰 있을 때 5 s 마다 이유를 WARN 으로 남긴다(판정은 FSM 그대로, 로그만).
        self._wait_report = wait_report.WaitReport()
        self._wait_names = {trip_fsm.AT_HOME: f'{namespace}/arm/at_home',
                            trip_fsm.BASE_STOPPED: f'{namespace}/base/stopped',
                            trip_fsm.BELT: '/pharmacy/belt'}
        self._event_pub = self.create_publisher(Event, '/events', latched_qos(500))
        self._alert_pub = self.create_publisher(String, alerts.TOPIC, latched_qos(alerts.QOS_DEPTH))
        self._status_pub = self.create_publisher(OrderStatus, '/orders/status', latched_qos(50))
        self._dispenser_pub = self.create_publisher(
            DispenserStatus, '/pharmacy/dispenser/status', latched_qos(1))

        # 이름을 rclpy Node 의 내부 속성과 겹치게 두면 안 된다. 아래 액션 클라이언트 표를
        # `_clients` 로 두면 Node 가 create_client 에서 append 하는 목록을 덮어써서 깨진다.
        self._action_clients = {
            trip_fsm.GO_TO_ZONE: ActionClient(self, GoToZone, f'{namespace}/go_to_zone',
                                              callback_group=group),
            trip_fsm.PICK_POUCH: ActionClient(self, PickPouch, f'{namespace}/pick_pouch',
                                              callback_group=group),
            refill_planner.REFILL: ActionClient(self, Refill, '/m0609/refill', callback_group=group),
            trip_fsm.SCAN_TAG: ActionClient(self, ScanTag, f'{namespace}/scan_tag',
                                            callback_group=group),
        }
        self._dispense = self.create_client(Dispense, '/pharmacy/dispense', callback_group=group)
        self._sim_reset = self.create_client(Reset, '/sim/reset', callback_group=group)

        self.create_subscription(Bool, f'{namespace}/arm/at_home',
                                 partial(self._on_bool, trip_fsm.AT_HOME), heartbeat_qos())
        self.create_subscription(Bool, f'{namespace}/base/stopped',
                                 partial(self._on_bool, trip_fsm.BASE_STOPPED), heartbeat_qos())
        self.create_subscription(Bool, f'{namespace}/gripper/holding',
                                 partial(self._on_bool, trip_fsm.HOLDING), heartbeat_qos())
        self.create_subscription(BeltState, '/pharmacy/belt', self._on_belt, heartbeat_qos())
        if self._fsm.config.observation_guard:
            self._wait_names[trip_fsm.BELT_OBSERVATION] = '/pharmacy/belt/observation'
            self._wait_names[trip_fsm.ARM_CLEARANCE] = f'{namespace}/arm/clear_of_belt'
            self.create_subscription(BeltObservation, '/pharmacy/belt/observation', self._on_belt_observation,
                                     heartbeat_qos())
            self.create_subscription(ArmClearance, f'{namespace}/arm/clear_of_belt', self._on_arm_clearance,
                                     heartbeat_qos())
        self.create_subscription(TagRead, f'{namespace}/hand_camera/tag_reads',
                                 self._on_tag, reliable_qos())

        ActionServer(self, Deliver, '/deliver', goal_callback=self._on_deliver_goal,
                     cancel_callback=lambda _: CancelResponse.REJECT,
                     execute_callback=self._execute_deliver, callback_group=group)
        self.create_service(Reset, '~/reset', self._on_reset, callback_group=group)
        if self._db is not None:
            # 팔이 Refill 을 돌리는 **도중에** 묻는다. orchestrator 는 Refill 결과를 콜백으로 받으므로
            # (막고 기다리지 않는다) 되부름 교착은 없다. 그래도 이 서비스는 자기 그룹에서 돌게 해
            # 긴 콜백 뒤에 줄 서지 않게 한다.
            self.create_service(CheckContainer, '/orchestrator/check_container', self._on_check_container,
                                callback_group=MutuallyExclusiveCallbackGroup())

        self.create_timer(0.1, self._tick, callback_group=group)
        self.create_timer(1.0, self._publish_dispenser, callback_group=group)
        self.get_logger().info(f'orchestrator up. 주문 풀 {len(self._pool)}건, epoch={self._epoch}, '
                               f'pharmacy_only={self._fsm.config.pharmacy_only}')

    # 입력 ---------------------------------------------------------------

    def _on_bool(self, name, msg):
        with self._lock:
            self._states[name] = (bool(msg.data), time.monotonic())
            self._push(name)

    def _on_belt(self, msg):
        value = {'occupied': msg.occupied, 'at_end': msg.at_end, 'order_id': msg.order_id}
        with self._lock:
            self._states[trip_fsm.BELT] = (value, time.monotonic())
            self._push(trip_fsm.BELT)

    def _on_belt_observation(self, msg):
        self._observe(trip_fsm.BELT_OBSERVATION, msg, {
            'order_id': msg.order_id, 'occupancy': msg.occupancy, 'pouch_zone': msg.pouch_zone,
            'pouch_motion': msg.pouch_motion, 'belt_command_applied': msg.belt_command_applied})

    def _on_arm_clearance(self, msg):
        self._observe(trip_fsm.ARM_CLEARANCE, msg, {'clearance': msg.clearance})

    def _observe(self, name, msg, fields):
        """계약 11.6: seq 가 앞으로 갔을 때만 신선하다. 같은 표본의 반복은 신선도를 되살리지 않는다."""
        key = (msg.epoch, msg.seq)
        with self._lock:
            last = self._observed.get(name)
            if last is not None and key <= last:
                return
            self._observed[name] = key
            self._states[name] = ({'epoch': msg.epoch, 'seq': msg.seq, **fields}, time.monotonic())
            self._push(name)

    def _on_tag(self, msg):
        if msg.status != TagRead.STATUS_OK:
            return
        with self._lock:
            self._run(self._fsm.tag(msg.tag_id))

    def _push(self, name):
        value, seen = self._states[name]
        fresh = (time.monotonic() - seen) <= STATE_FRESH_S
        if self._pushed.get(name) == (repr(value), fresh):
            return
        self._pushed[name] = (repr(value), fresh)
        self._run(self._fsm.state_update(name, value, fresh))

    def _tick(self):
        with self._lock:
            self._finish_unsent_cancels()
            self._flush_waiting()
            for name in list(self._states):
                self._push(name)
            now = self.get_clock().now().nanoseconds * 1e-9
            wall = time.monotonic()
            self._run(self._fsm.tick(now, wall))
            self._report_wait(wall)
            if not self._fsm.resetting:
                self._run(self._refill.tick(now, wall))       # 리셋 barrier 중에는 새 보충 goal 을 안 낸다
            elif self._fsm.barrier_failed:
                self.get_logger().error(
                    '리셋 실패로 멈춰 있다. Deliver 를 거부한다. /orchestrator/reset 으로 다시 시작한다.',
                    throttle_duration_sec=10.0)

    def _report_wait(self, wall):
        """트립이 guard 로 멈춰 있으면 5 s 마다 WARN, 풀리면 INFO. 이벤트를 새로 내지 않는다."""
        wait = self._fsm.wait_reason(self._wait_names)
        for level, text in self._wait_report.update(wait, wall):
            log = self.get_logger()
            if level == wait_report.WARN:
                log.warning(f'{self._fsm.request_id or "-"}: {text}')
            else:
                log.info(f'{self._fsm.request_id or "-"}: {text}')

    # Deliver 서버 ---------------------------------------------------------

    def _to_fsm_request(self, request):
        return {
            'request_id': request.request_id,
            'mode': MODE_NAMES.get(request.mode, trip_fsm.MODE_SINGLE),
            'destination_id': request.destination_id,
            'orders': [{'order_id': o.order_id, 'patient_id': o.patient_id, 'item_id': o.item_id}
                       for o in request.orders],
        }

    def _refuse(self, reason, request_id=''):
        # 계약 2.5절: 거부는 goal 거부로 끝난다. 이벤트도 지표 분모도 없다. goal 거부에는 사유를 실을 자리가 없어
        # 로그(/rosout)에만 남는다. 웹이 request_id 로 이 줄을 찾을 수 있게 앞에 붙인다.
        self.get_logger().warning(f'Deliver goal 거부 {request_id or "-"}: {reason}')
        return GoalResponse.REJECT

    def _on_deliver_goal(self, goal):
        request = goal.request

        def refuse(reason):
            return self._refuse(reason, request.request_id)

        with self._lock:
            if self._fsm.resetting:
                return refuse('리셋 barrier 중이다' + (' (리셋 실패로 멈춤)' if self._fsm.barrier_failed else ''))
            if time.monotonic() < self._accept_after:
                return refuse('리셋 barrier 가 아직 안 끝났다')
            if not request.orders:
                return refuse('orders 가 비었다')
            if request.request_id in self._used_requests:
                return refuse(f'{request.request_id} 는 이미 받은 ID 다')
            if not is_zone_id(request.destination_id):
                return refuse(f'{request.destination_id} 는 구역 ID 가 아니다')
            for order in request.orders:
                if order.order_id not in self._pool:
                    return refuse(f'{order.order_id} 가 주문 풀에 없다')
                if order.order_id in self._used_orders:
                    return refuse(f'{order.order_id} 는 이미 쓴 주문이다')
            refusal = self._fsm.refusal(self._to_fsm_request(request))
            if refusal is not None:
                return refuse(refusal)
            self._used_requests.add(request.request_id)
            self._used_orders.update(order.order_id for order in request.orders)
        return GoalResponse.ACCEPT

    def _execute_deliver(self, goal_handle):
        self._deliver_idle.clear()
        try:
            return self._run_deliver(goal_handle)
        finally:
            self._deliver_idle.set()

    def _run_deliver(self, goal_handle):
        request = goal_handle.request.request
        self._deliver_done.clear()
        with self._lock:
            self._deliver_result = None
            self._status.clear()
            commands = self._fsm.request(self._to_fsm_request(request))
            self._run(commands)
        if not commands:
            self._end_goal(goal_handle, 'abort')
            return Deliver.Result(success=False)
        # 트립 끝(Finish)을 기다린다. 노드를 내리거나 rclpy 가 꺼지면 풀고 abort 한다. 시한 없이 기다리면
        # 실행 스레드가 안 끝나 인터프리터 종료(concurrent.futures join)가 멈춘다(정비 L2 관측).
        while not self._deliver_done.wait(DELIVER_POLL_S):
            if self._closing.is_set() or not rclpy.ok():
                return self._abort_on_shutdown(goal_handle, request.request_id)
        with self._lock:
            result, aborted = self._deliver_result
        self._end_goal(goal_handle, 'abort' if aborted else 'succeed')
        return result

    def _abort_on_shutdown(self, goal_handle, request_id):
        """종료는 리셋이 아니다. 주문 상태·이벤트를 새로 내지 않고 goal 만 abort 한다.

        결과의 orders 는 지금까지 발행한 마지막 상태 그대로다. Deliver.Result 에 사유 칸이 없어 로그에만 남긴다.
        """
        self.get_logger().info(f'{request_id}: 노드 종료(shutdown). 트립을 끝내지 않고 Deliver goal 을 abort 한다.')
        with self._lock:
            result = Deliver.Result(success=False, orders=list(self._status.values()))
        self._end_goal(goal_handle, 'abort')
        return result

    def _end_goal(self, goal_handle, how):
        """goal 을 succeed·abort·canceled 로 닫는다. 종료 중 발행이 실패하면 debug 한 줄로 넘긴다.

        종료 중 = close 가 불렸거나 context 가 내려갔다. SIGINT 에서는 rclpy 신호 처리기가 context 를 먼저 내려
        액션 서버 publisher 가 무효다. 그때 나는 RCLError("feedback publisher is invalid")는 고장이 아니라
        ERROR·traceback 을 남기지 않는다. 종료가 아니면 그대로 올린다.
        상태 전이를 아예 건너뛰지는 않는다. 실행 콜백이 종결 상태 없이 끝나면 rclpy 가 콜백 밖에서 다시
        abort 해서 거기서 예외가 나기 때문이다(정비 변형 시험으로 확인, 9/17).
        """
        try:
            getattr(goal_handle, how)()
        except Exception as error:
            if not (self._closing.is_set() or not rclpy.ok()):
                raise
            self.get_logger().debug(f'종료 중이라 goal {how} 를 보내지 못했다: {error}')

    def close(self):
        """종료 경로. Deliver 실행이 기다림을 풀고 abort 를 마치기를 CLOSE_WAIT_S 까지 기다린다. 여러 번 불러도 된다.

        플래그를 먼저 켠다. 이중 SIGINT 로 이 대기 중에 KeyboardInterrupt 가 나도 플래그는 이미 켜져 있어
        실행 스레드는 다음 주기(DELIVER_POLL_S)에 풀린다.
        대기는 abort 가 액션 서버를 내리기 전에 나가게 하려는 것뿐이다.
        """
        self._closing.set()
        try:
            if not self._deliver_idle.wait(CLOSE_WAIT_S):
                self.get_logger().warning(f'Deliver 실행이 {CLOSE_WAIT_S:g} s 안에 안 끝났다. 그대로 노드를 내린다.')
        except KeyboardInterrupt:
            pass        # 이중 SIGINT. 플래그는 이미 켜져 실행 스레드는 다음 주기에 풀린다. traceback 없이 넘긴다

    def destroy_node(self):
        self.close()
        return super().destroy_node()

    # 리셋 barrier ---------------------------------------------------------

    def _on_reset(self, request, response):
        """리셋 barrier 진입(계약 6절, v2). 응답은 곧바로 ok 다. barrier 완료를 뜻하지 않는다.

        진행 중 barrier 에 온 요청은 합류한다(epoch 를 다시 올리지 않는다). 리셋 실패로 멈춘 뒤의 요청은
        새 epoch 로 barrier 를 다시 시작한다. 재고·선반·사용 표는 /sim/reset 이 ok 한 뒤에 되돌린다(ReloadStores).
        새 epoch 는 항상 지금 epoch + 1 이다(계약 4절). 요청의 epoch 는 쓰지 않고, 응답 message 에 실제 epoch 를 적는다.
        """
        with self._lock:
            if self._fsm.barrier_running:
                response.ok = True
                response.message = f'epoch={self._epoch} (진행 중 barrier 에 합류)'
                return response
            new_epoch = self._epoch + 1
            now_sim = self.get_clock().now().nanoseconds * 1e-9
            drain = self._drain_for_reset()
            self._drain_tokens = [token for _, token in drain]
            self._epoch = new_epoch
            # 보충 클라이언트는 새 goal 을 멈추고 상태를 비운다. 활성 goal 의 cancel 은 FSM 이 drain 으로 낸다.
            self._refill.reset(new_epoch, self._refill.inventory)
            self._run(self._fsm.reset(new_epoch, now_sim=now_sim, now_wall=time.monotonic(), drain=drain))
        response.ok = True
        response.message = f'epoch={self._epoch}'
        if int(request.epoch) not in (0, self._epoch):
            response.message += f' (요청 epoch={request.epoch} 은 쓰지 않는다. epoch 는 리셋마다 +1)'
        return response

    def _drain_for_reset(self):
        """리셋 drain 이 기다릴 goal 들 (액션, token). 서버를 기다리며 아직 안 보낸 것은 대기에서 빼면 끝이다."""
        drain = []
        for token, entry in list(self._goals.items()):
            if self._server_wait.drop(token):
                self._goals.pop(token, None)
                continue
            drain.append((entry.action, token))
        return drain

    def _abandon_undrained(self):
        """리셋 drain 이 끝났다(모두 종결했거나 cancel_wait_s 를 넘겼다). 표에 남은 drain goal 은 종결이 안 온 것이다.

        표에서 뺀다. 두면 다음 리셋마다 drain 이 그 goal 을 또 cancel_wait_s 동안 기다린다.
        뺀 goal 이 늦게 수락되면 곧바로 cancel 하고 따라가지 않는다(_on_goal_response). 늦은 결과는 epoch 로 버린다.
        """
        tokens, self._drain_tokens = self._drain_tokens, []
        for token in tokens:
            entry = self._goals.pop(token, None)
            if entry is not None:
                self.get_logger().warning(
                    f'{entry.action} goal {token} 의 종결이 cancel_wait_s 안에 안 왔다. goal 표에서 뺀다.')

    def _load_at_dock(self):
        """zones_file 에서 적재 zone 과 도크 zone 이 같은 자리인가(병원 B안, 재범 9/29). 못 읽으면 거짓."""
        path = self.get_parameter('zones_file').value
        if not path:
            return False
        try:
            same = trip_fsm.load_is_dock(read_yaml(path), str(self.get_parameter('load_zone').value),
                                         str(self.get_parameter('dock_zone').value))
        except (OSError, yaml.YAMLError):
            return False
        if same:
            self.get_logger().info('적재 자리 = 도크: 도크에서 이동 없이 적재·파지한다(load_at_dock)')
        return same

    def _room_maps(self):
        """zones_file → TripFsm 키워드(병실 테이블·스테이션 자리). 비었거나 못 읽으면 빈 표(예전 동작)."""
        path = self.get_parameter('zones_file').value
        if not path:
            return {}
        try:
            maps = trip_fsm.zone_maps(read_yaml(path))
        except (OSError, yaml.YAMLError) as exc:
            self.get_logger().error(f'zones_file 을 못 읽었다({path}): {exc} — 병실 묶음은 침상마다 선다')
            return {}
        self.get_logger().info(f"zones_file={path} room_tables={maps['room_tables']} "
                               f"station_zones={sorted(maps['station_zones'])}")
        return maps

    def _open_pharmacy_db(self):
        """시드 세 파일로 약 DB 를 연다. 시드가 틀리면 CatalogError 로 기동을 거부한다(계약 2.1)."""
        catalog_path = self.get_parameter('pharmacy_catalog_file').value or share_config('pharmacy_catalog.yaml')
        today = self.get_parameter('pharmacy_today').value or None
        seed = pharmacy_db.build_seed(read_yaml(catalog_path), read_yaml(self._dispenser_path),
                                      read_yaml(self._pool_path), today=today, require_dispenser_lots=False)
        if seed['missing_lots']:
            # 현장 재고 파일이 카탈로그와 다른 로트를 쓴다. 그 로트는 약통 표에 없고, 확인은 선반 약통(cn-)으로 한다.
            self.get_logger().warning(f'재고 파일의 로트 중 카탈로그에 cn- ID 가 없는 것: {seed["missing_lots"]}')
        if seed['unmatched_catalog']:
            self.get_logger().warning(f'카탈로그 약통 중 재고 파일에 로트가 없어 뺀 것: {seed["unmatched_catalog"]}')
        path = self.get_parameter('pharmacy_db_path').value or ':memory:'
        db = pharmacy_db.PharmacyDb(path, seed)
        self.get_logger().info(f'약 DB 열림: {path} today={db.today} catalog={catalog_path}')
        return db

    def _on_check_container(self, request, response):
        """보충 전 약통 확인(계약 2.3). 거부 이유는 응답과 스캔 기록에 같이 남는다."""
        with self._lock:
            epoch = self._epoch
        response.allowed, response.reason = self._db.check_container(
            request.container_id, robot=request.robot_id or 'm0609', epoch=request.epoch, current_epoch=epoch,
            cell_id=request.cell_id or None, stamp=self.get_clock().now().nanoseconds * 1e-9)
        # 등급마다 호출 자리를 따로 둔다. rclpy 는 한 호출 자리에서 등급이 바뀌면 예외를 낸다
        # (9/23 L3 957347a: 거부 뒤 허용에서 ValueError 로 서비스가 죽었다).
        if response.allowed:
            self.get_logger().info(f'약통 확인 {request.container_id!r} cell={request.cell_id} → 장착 허용 '
                                   f'({response.reason})')
        else:
            self.get_logger().warning(f'약통 확인 {request.container_id!r} cell={request.cell_id} → 장착 거부 '
                                      f'({response.reason})')
        return response

    def _reload_stores(self):
        """/sim/reset 이 ok 한 뒤. 재고·선반을 파일 값으로, 요청·주문 사용 표를 비운다(계약 6절 3)."""
        if self._db is not None:
            self._db.reseed()                  # 약통·모듈·봉투 표만 되돌린다. 스캔 기록은 남긴다
        inventory = load_inventory(read_yaml(self._dispenser_path))
        self._fsm.inventory = inventory
        self._refill.inventory = inventory
        self._used_requests.clear()
        self._used_orders.clear()

    # 명령 실행 ------------------------------------------------------------

    def _run(self, commands):
        for command in commands:
            if isinstance(command, trip_fsm.SendGoal):
                self._send_goal(command)
            elif isinstance(command, trip_fsm.Cancel):
                self._cancel(command)
            elif isinstance(command, trip_fsm.Call):
                self._call(command)
            elif isinstance(command, trip_fsm.Emit):
                self._emit(command)
            elif isinstance(command, trip_fsm.OrderState):
                self._publish_order(command)
            elif isinstance(command, trip_fsm.Finish):
                self._finish(command)
            elif isinstance(command, trip_fsm.ReloadStores):
                self._reload_stores()
            elif isinstance(command, trip_fsm.Note):
                self._note(command)
            elif isinstance(command, trip_fsm.Alert):
                self._alert(command)

    def _note(self, command):
        """Note 를 로그로 남긴다. **수준마다 호출 지점이 달라야 한다.**

        rclpy 의 로거는 호출 지점(파일·줄)마다 severity 를 기억하고, 같은 지점에서 다른 수준으로
        부르면 `ValueError: Logger severity cannot be changed between calls` 를 던진다. 한 줄에서
        수준을 골라 부르면 두 번째 수준이 나오는 순간 노드가 죽는다(9/20 실습13, #240).
        """
        log = self.get_logger()
        if command.level == 'info':
            log.info(command.text)
        elif command.level == 'error':
            log.error(command.text)
        else:
            log.warning(command.text)

    def _alert(self, command):
        """관제 웹 알림 한 건. 형식이 틀려도 트립은 계속 간다(로그만)."""
        try:
            text = alerts.encode(command.kind, self._robot_id, command.detail,
                                 self.get_clock().now().nanoseconds * 1e-9, time.time())
        except ValueError as error:
            self.get_logger().warning(f'alert 버림: {error}')
            return
        msg = String()
        msg.data = text
        self._alert_pub.publish(msg)

    def _stamp(self, seconds):
        """명령에 snapshot stamp 가 있으면 그 sim 시각, 없으면 지금."""
        if seconds is None:
            return self.get_clock().now().to_msg()
        return Time(nanoseconds=int(round(seconds * 1e9))).to_msg()

    def _emit(self, command):
        msg = Event()
        msg.header.stamp = self._stamp(command.stamp)
        msg.name = command.event
        msg.request_id = command.request_id
        msg.order_id = command.order_id
        msg.robot_id = command.robot_id or self._robot_id
        msg.epoch = command.epoch if command.epoch is not None else self._epoch
        msg.detail = command.detail
        self._event_pub.publish(msg)
        if command.event == trip_fsm.EVENT_RESET_DONE:
            # 계약 6절 5: RESET_DONE 뒤 3 s wall 지나야 새 요청을 받는다.
            self._accept_after = time.monotonic() + RESET_SETTLE_S

    def _publish_order(self, command):
        msg = OrderStatus()
        msg.header.stamp = self._stamp(command.stamp)
        # 리셋으로 끊긴 주문은 FSM 이 트립을 비우기 전의 request_id 를 명령에 담아 온다.
        msg.request_id = command.request_id if command.request_id is not None else self._fsm.request_id
        msg.order_id = command.order_id
        msg.state = ORDER_STATE_VALUES[command.state]
        msg.reason = command.reason
        self._status[command.order_id] = msg
        self._status_pub.publish(msg)

    def _finish(self, command):
        result = Deliver.Result()
        result.orders = list(self._status.values())
        result.success = command.success
        self._deliver_result = (result, command.aborted)
        self._deliver_done.set()

    def _send_goal(self, command):
        token = command.token
        self._goals.setdefault(token, GoalEntry(command.action))
        client = self._action_clients[command.action]
        if not client.server_is_ready():
            self._hold(command.action, command)
            return
        if command.action == refill_planner.REFILL:
            # **보내기 직전**에 적는다. 서버를 기다리며 `_hold` 로 돌아간 횟수만큼 `send` 가 찍히면
            # 한 번 보충한 것이 여러 번으로 읽힌다. 실제로 나간 goal 하나에 `send` 한 줄이다.
            item_id = command.goal.get('item_id') or ''
            # 품목은 **그 token 의 goal** 에 단다. 노드 필드 하나에 두면 다음 send 가 덮어써서 앞 goal 의
            # 결과가 뒤 품목으로 적힌다(커서 #604 재검토 ③).
            self._goals[token].item_id = item_id
            self._log_refill_overlap('send', item_id, detail=f"slot={command.goal.get('slot')}")
        goal = self._build_goal(command)
        future = client.send_goal_async(
            goal, feedback_callback=partial(self._on_feedback, command.action, token))
        future.add_done_callback(partial(self._on_goal_response, command.action, token))

    def _build_goal(self, command):
        if command.action == trip_fsm.GO_TO_ZONE:
            return GoToZone.Goal(zone_id=command.goal['zone_id'])
        if command.action == trip_fsm.PICK_POUCH:
            return PickPouch.Goal(order_id=command.goal['order_id'],
                                  source=PICK_SOURCES[command.goal['source']],
                                  target_slot=command.goal['target_slot'],
                                  zone_id=command.goal.get('zone_id', ''))
        if command.action == refill_planner.REFILL:
            return Refill.Goal(item_id=command.goal['item_id'], slot=command.goal['slot'])
        return ScanTag.Goal(kind=TAG_KINDS[command.goal['kind']], zone_id=command.goal['zone_id'])

    def _log_refill_overlap(self, phase, item_id, detail=''):
        """보충이 배송과 **겹쳤는지** 한 줄로 남긴다(재범 카드 9/23).

        보충은 트립 FSM 밖에서 트립과 병렬로 돈다. 그런데 "겹쳤다" 는 것을 보려면 지금까지는 REFILL 줄과
        DEPARTED→ARRIVED 줄의 **시각을 사람이 맞춰 봐야** 했다. 그래서 보충 goal 이 나갈 때와 결과가 올 때
        그 순간의 트립 상태를 같이 적는다.

        **`overlap=` 을 직접 적는다.** 전에는 `trip=IDLE` 이 아니면 겹친 것으로 읽으라고 뒀는데 그것은
        틀렸다 — `DOCKED_LOAD`·`WAIT_BELT`·`PICKING_BELT` 는 트립이 있어도 AMR 이 조제실에 서 있고,
        `RETURNING`·`RESETTING` 은 배송이 끝난 뒤다. 판단을 읽는 사람에게 넘기지 않는다
        (`trip_fsm.DELIVERY_STATES`).
        """
        # `stops` 는 **메서드**다. 속성으로 알고 len() 을 걸어 TypeError 가 났고, 이 줄이 `_send_goal`
        # 안에 있어서 **보충 goal 이 아예 안 나갔다**(#604 CI: `Refill 이 오지 않았다`).
        # 남은 정거장 수는 FSM 이 센다 — 여기서 내부를 헤아리지 않는다. 그리고 진단 한 줄이 본 경로를
        # 막지 못하게 감싼다. 관측이 동작을 바꾸면 그것은 관측이 아니다.
        # 판정·글자 만들기·info 까지 **전부** 한 try 안이다. info 가 던져도 `send_goal_async` 와
        # `_on_result` 의 `_feed` 는 그대로 간다(커서 #604 재검토 ②: 전에는 stops_left 만 감쌌다).
        try:
            trip = getattr(self._fsm, 'state', '?')
            stops_left = self._fsm.stops_left()
            overlap = 'yes' if trip in trip_fsm.DELIVERY_STATES else 'no'
            self.get_logger().info(
                f'refill_overlap {phase} item={item_id or "-"} overlap={overlap} trip={trip} '
                f'stops_left={stops_left}' + (f' {detail}' if detail else ''))
        except Exception as error:          # 진단은 어떤 이유로도 goal 전송·결과 전달을 막지 않는다
            with contextlib.suppress(Exception):   # 로거까지 죽었으면 조용히 넘어간다 — 본 경로가 먼저다
                self.get_logger().warn(f'refill_overlap {phase} 를 못 적었다: {type(error).__name__}: {error}')

    def _cancel(self, command):
        """그 token 의 goal 만 cancel 한다. token 이 없으면 그 액션의 goal 전부.

        - 서버를 기다리며 아직 안 보냈으면 대기에서 빼고, 다음 tick 에 종결(canceled)로 알린다.
        - 보냈지만 수락 전이면 표시만 해 두고 수락되자마자 cancel 한다.
        - 수락됐으면 cancel 을 보낸다. cancel 응답은 종결이 아니다. 결과가 와야 표에서 지운다.
        """
        if command.token is not None:
            tokens = [command.token]
        else:
            tokens = [token for token, entry in self._goals.items() if entry.action == command.action]
        for token in tokens:
            if self._server_wait.drop(token):
                self._goals.pop(token, None)
                self._unsent_cancels.append((token, command.action))
                continue
            entry = self._goals.get(token)
            if entry is None:
                continue
            entry.cancel_requested = True
            if entry.handle is not None:
                entry.handle.cancel_goal_async()

    def _call(self, command):
        token = command.token
        if command.service == trip_fsm.RESET:
            # FSM 은 drain 이 끝나야 /sim/reset 을 부른다.
            self._abandon_undrained()
        if command.service == trip_fsm.DISPENSE:
            client, request = self._dispense, Dispense.Request(**command.request)
        else:
            client, request = self._sim_reset, Reset.Request(epoch=command.request['epoch'])
        if not client.service_is_ready():
            self._hold(command.service, command)
            return
        client.call_async(request).add_done_callback(
            partial(self._on_service, command.service, token))

    # 서버 대기 ------------------------------------------------------------

    def _hold(self, name, command):
        """서버가 아직 안 보인다. 거부로 세지 않고 기다린다. FSM 의 액션 시한은 SendGoal 때 이미 걸렸다."""
        limit_s = self._wait_limit(command)
        self.get_logger().warning(f'{name} 서버가 아직 안 보인다. 최대 {limit_s:g} s 기다린다.')
        self._server_wait.hold(command.token, command, time.monotonic(), limit_s)

    def _wait_limit(self, command):
        """서버를 기다리는 시간(wall). /sim/reset 은 reset_timeout_s 가 서버 탐색을 포함한다(FSM 시한과 같이 만료)."""
        if isinstance(command, trip_fsm.Call) and command.service == trip_fsm.RESET:
            return self._fsm.config.reset_timeout_s
        return self._server_wait.limit_s

    def _server_ready(self, command):
        if isinstance(command, trip_fsm.SendGoal):
            return self._action_clients[command.action].server_is_ready()
        client = self._dispense if command.service == trip_fsm.DISPENSE else self._sim_reset
        return client.service_is_ready()

    def _finish_unsent_cancels(self):
        """보내기 전에 cancel 한 goal 을 종결(canceled)로 알린다.

        cancel 명령을 실행하는 도중에 FSM 을 다시 돌리면 뒤따르는 명령(ORDER_DONE 등)보다 새 명령이 앞선다.
        그래서 다음 tick 으로 미룬다.
        """
        pending, self._unsent_cancels = self._unsent_cancels, []
        for token, action in pending:
            self._feed(token, action, trip_fsm.CANCELED, {})

    def _flush_waiting(self):
        """기다리던 명령 중 서버가 보인 것은 보내고, 기다리는 시간(_wait_limit)을 넘은 것은 거부로 넣는다."""
        send, expired, stale = self._server_wait.due(self._epoch, time.monotonic(), self._server_ready)
        for command in stale:
            self._goals.pop(command.token, None)
            self.get_logger().info(f'{command} 는 이전 epoch 의 명령이다. 서버를 기다리지 않고 버린다.')
        self._run(send)
        for command in expired:
            if isinstance(command, trip_fsm.SendGoal):
                self._goals.pop(command.token, None)
                self.get_logger().error(
                    f'{command.action} 서버가 {self._wait_limit(command):g} s 안에 안 보였다. 거부로 본다.')
                self._feed(command.token, command.action, trip_fsm.REJECTED, {})
            else:
                self.get_logger().error(
                    f'{command.service} 서비스가 {self._wait_limit(command):g} s 안에 안 보였다.')
                outcome = trip_fsm.REJECTED if command.service == trip_fsm.DISPENSE else trip_fsm.FAILED
                self._feed(command.token, command.service, outcome, {'message': 'no_server'})

    # 액션·서비스 응답 ------------------------------------------------------

    def _on_goal_response(self, action, token, future):
        handle = future.result()
        with self._lock:
            if not handle.accepted:
                self._goals.pop(token, None)
                self._feed(token, action, trip_fsm.REJECTED, {})
                return
            entry = self._goals.get(token)
            if entry is None:
                # 리셋 drain 이 상한을 넘겨 표에서 뺀 goal 이 이제야 수락됐다. 곧바로 cancel 하고 따라가지 않는다.
                self.get_logger().warning(f'{action} goal {token} 이 drain 뒤에 수락됐다. 곧바로 cancel 한다.')
                handle.cancel_goal_async()
                return
            entry.handle = handle
            if entry.cancel_requested:
                # 수락 전에 cancel 을 받았다. 받자마자 cancel 하고 결과(종결)까지 표에 둔다.
                handle.cancel_goal_async()
        handle.get_result_async().add_done_callback(partial(self._on_result, action, token))
        self._feed(token, action, trip_fsm.ACCEPTED, {})

    def _on_feedback(self, action, token, message):
        if action != trip_fsm.GO_TO_ZONE:
            return
        with self._lock:
            if token.epoch != self._epoch:
                return
            self._run(self._fsm.feedback(action, message.feedback.distance_remaining, token))

    def _on_result(self, action, token, future):
        response = future.result()
        outcome, detail = self._read_result(action, response.status, response.result)
        with self._lock:
            entry = self._goals.pop(token, None)  # 그 token 만. 같은 액션의 새 goal 은 그대로 둔다
        if action == refill_planner.REFILL:
            # `done` 은 token 을 아는 여기서 적는다 — 그 goal 의 품목이고, **취소도 남는다**.
            # `_read_result` 에서 적으면 token 이 없어 품목을 노드 필드에서 빌려야 했고, 취소는 그 전에 return 했다.
            result = 'canceled' if outcome == trip_fsm.CANCELED else 'ok' if outcome == trip_fsm.OK else 'failed'
            self._log_refill_overlap('done', entry.item_id if entry is not None else '',
                                     detail=f'outcome={result}')
        self._feed(token, action, outcome, detail)

    def _read_result(self, action, status, result):
        """wrapper status 를 payload 보다 먼저 본다. canceled·aborted 를 성공으로 읽지 않는다."""
        if status == GoalStatus.STATUS_CANCELED:
            return trip_fsm.CANCELED, {}
        succeeded = status == GoalStatus.STATUS_SUCCEEDED
        if action == trip_fsm.GO_TO_ZONE:
            arrived = succeeded and result.arrived
            return (trip_fsm.ARRIVED if arrived else trip_fsm.NOT_ARRIVED), {'message': result.message}
        if action == trip_fsm.PICK_POUCH:
            outcome = result.outcome or (trip_fsm.OK if result.success else trip_fsm.TIMED_OUT)
            if outcome == trip_fsm.OK and not succeeded:
                outcome = trip_fsm.TIMED_OUT
            return outcome, {}
        if action == refill_planner.REFILL:
            ok = succeeded and result.success
            return (trip_fsm.OK if ok else refill_planner.FAILED), {'lot_id': result.lot_id}
        ok = succeeded and result.status == TagRead.STATUS_OK
        return (trip_fsm.OK if ok else trip_fsm.UNREADABLE), {'tag_id': result.tag_id}

    def _on_service(self, service, token, future):
        try:
            response = future.result()
        except Exception as error:
            self.get_logger().error(f'{service} 호출이 예외로 끝났다: {error}')
            outcome = trip_fsm.REJECTED if service == trip_fsm.DISPENSE else trip_fsm.FAILED
            self._feed(token, service, outcome, {'message': 'exception'})
            return
        if service == trip_fsm.DISPENSE:
            outcome = trip_fsm.ACCEPTED if response.accepted else trip_fsm.REJECTED
        else:
            outcome = trip_fsm.OK if response.ok else trip_fsm.FAILED
        self._feed(token, service, outcome, {'message': response.message})

    def _feed(self, token, name, outcome, detail):
        with self._lock:
            if token is not None and outcome != trip_fsm.ACCEPTED:
                # 리셋 drain 이 기다리던 goal 이면 뺀다. 이전 epoch 의 결과도 종결 확인에는 쓴다.
                self._run(self._fsm.terminated(token))
            epoch = token.epoch if token is not None else self._epoch
            if epoch != self._epoch:
                # 계약 4절: 이전 epoch 의 결과는 버린다.
                self.get_logger().info(f'{name} 결과를 버린다. epoch {epoch} != {self._epoch}')
                return
            if name == refill_planner.REFILL:
                # 보충 결과는 트립 FSM 이 아니라 보충 클라이언트로 간다.
                now = self.get_clock().now().nanoseconds * 1e-9
                self._run(self._refill.result(outcome, now, detail, epoch, token))
                return
            self._run(self._fsm.result(name, outcome, detail, token))

    # 조제기 상태 ----------------------------------------------------------

    def _publish_dispenser(self):
        with self._lock:
            inventory = self._fsm.inventory
            if inventory is None:
                return
            msg = DispenserStatus()
            msg.header.stamp = self.get_clock().now().to_msg()
            active = {item_id: inventory.active_slot(item_id) for item_id in inventory.items()}
            msg.slots = [
                DispenserSlot(item_id=slot.item_id, slot=slot.slot, lot_id=slot.lot_id,
                              expiry=slot.expiry, count=slot.count,
                              active=bool(active[slot.item_id])
                              and active[slot.item_id].slot == slot.slot)
                for slot in inventory.slots()]
            msg.paused_item_ids = list(inventory.paused_items())
            msg.queue_length = 0
            belt = self._states.get(trip_fsm.BELT, ({}, 0.0))[0]
            msg.belt_occupied = bool(belt.get('occupied')) if isinstance(belt, dict) else False
        self._dispenser_pub.publish(msg)


def main(args=None):
    """콘솔 진입점."""
    rclpy.init(args=args)
    node = OrchestratorNode()
    # 액션 실행 콜백이 스레드를 오래 잡는다. 코어 수가 적은 기계에서도 굶지 않게 고정한다.
    executor = MultiThreadedExecutor(num_threads=8)
    executor.add_node(node)
    try:
        executor.spin()
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
