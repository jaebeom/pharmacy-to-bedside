"""Isaac 어댑터. Isaac 의 JSON 토픽(std_msgs/String)을 계약 v1 이름·타입으로 바꾼다.

Isaac Sim 5.1 내부 Python(3.11)은 rokey_p3_interfaces 를 import 하지 못한다. 그래서 Isaac 은 JSON 토픽만 내고
이 노드가 계약 타입으로 옮긴다. 켜면 orchestrator 입장에서 stub_sim 의 같은 기능과 구별이 안 돼야 한다.
형식은 sim/README.md "Isaac ↔ ROS 어댑터 인터페이스 (JSON, v1)" 표를 따른다(isaac_json.py).

내는 것: /pharmacy/dispense(srv Dispense), /sim/reset(srv Reset), /pharmacy/belt(BeltState, H), /events(Event, L 500),
켜면 /pharmacy/belt/observation(BeltObservation, H), /amr_1/gripper/state(GripperState, H).
Isaac 과 주고받는 것: /isaac/pharmacy/dispense_request·dispense_response, /isaac/sim/reset_request·reset_response,
/isaac/pharmacy/belt, /isaac/events, /isaac/pharmacy/pick_notice, 켜면 /isaac/pharmacy/belt_observation,
/isaac/amr_1/gripper/state·command_seq.

- 서비스 응답 시한은 이 노드가 wall 로 잰다(계약 7절: Dispense 2 s, Reset 30 s). Isaac 구독자가 안 보이는 시간도
  시한 안에 든다. 넘으면 Dispense 는 accepted=false(message not_ready), Reset 은 ok=false 로 답하고 로그 한 줄.
- 응답은 Dispense 는 (request_id, order_id), Reset 은 epoch 로 기다리는 요청에 맞춘다. 기다리는 요청이 없는 응답
  (늦은 응답 포함)은 버리고 로그 한 줄. request_id 는 트립 ID 라 한 트립의 주문들이 같은 값을 쓴다. 그래서 order_id 까지
  맞춰야 앞 주문의 늦은 응답이 다음 주문의 요청을 채우지 않는다. order_id 가 다른 응답도 기다리는 요청이 없는 응답이다.
- JSON 형식 오류는 버리고 로그 한 줄. 응답이면 그 요청은 시한으로 실패한다.
  거부 message 가 계약 2.1 의 네 값(belt_occupied·unknown_order·not_ready·pool_exhausted) 밖이면 형식 오류로 보지 않고
  그대로 넘기고 warn 한다. orchestrator 는 accepted=false 를 message 와 상관없이 같은 거부로 보고
  (2 s 뒤 재호출, 총 3회), 끝내 거부면 그 message 를 ABORT reason 으로 남긴다.
- stamp 는 JSON 의 sim time 을 header.stamp 로 옮긴다.
- epoch: 계약 4절의 epoch 는 1 부터다. Isaac 이 0(첫 리셋 전)을 실으면 방어로 이 노드가 /events 에서 본 가장 큰 epoch
  (시작 1)로 바꾸고 warn 로그를 남긴다(Isaac 쪽을 1 로 고치기로 했다).
- belt 의 epoch 가 이 노드의 현재 epoch 보다 작으면 버린다. BeltState 에 epoch 칸이 없어서 계약 4절
  "이전 epoch 의 BeltState 는 버린다"를 이 노드가 대신 지킨다.
  리셋 barrier 중에는 Isaac 이 새 epoch 를 받기 전까지 belt 가 끊긴다.
- /isaac/events 는 transient local 이라 이 노드나 Isaac 이 다시 뜨면 지난 이벤트가 다시 온다.
  (epoch, name, stamp, order_id, request_id) 가 이미 옮긴 것과 같으면 버린다.
  이 노드가 다시 떠도 막으려고 /events(latched)에서 받은 dispenser 이벤트도 같은 키로 기억한다.
  다만 Isaac 의 지난 이벤트가 /events 이력보다 먼저 도착하면 그 몇 건은 못 막는다.
- pick_notice(파라미터 pick_notice, 기본 true): 스텁 팔이 봉투를 실제로 집지 않아도 Isaac 이 벨트 끝 봉투를 치우게 한다.
  /events 의 POUCH_PICKED 중 robot_id 가 amr_* 이고, epoch 가 현재 epoch 이고, 마지막으로 옮긴 belt 가 at_end 이며 그
  order_id 가 같을 때만(적재 픽. 병동 픽은 아니다) 그 stamp·epoch·order_id 로 /isaac/pharmacy/pick_notice 를 낸다.
  같은 (epoch, order_id) 로는 한 번만 낸다. 진짜 UR5 가 Isaac 에서 봉투를 집는 구성에서는 false.
- Isaac 이 안 보이면 알린다. /isaac/pharmacy/dispense_request·/isaac/sim/reset_request 구독자가 둘 다 0 이고
  /isaac/pharmacy/belt 를 isaac_missing_after_s(기본 5 s wall) 넘게 못 받았으면
  isaac_missing_warn_every_s(기본 10 s)마다 WARN, 다시 보이면 INFO 한 줄.
  orchestrator 는 벨트 unknown 이면 배출을 조용히 기다리므로(9/17 정비 재현) 원인을 여기서 드러낸다.
  판정 타이머는 steady clock 이라 sim time(/clock)이 멈춰 있어도 돈다.
- belt_observation(파라미터, 기본 false): 계약 11.6 의 /isaac/pharmacy/belt_observation(JSON)을
  /pharmacy/belt/observation(BeltObservation, H)으로 옮긴다. 기존 /pharmacy/belt 경로는 그대로다.
  형식 오류, epoch 0(계약 11.6: epoch 를 추측하지 않는다), 지금 epoch 나 이미 옮긴 관측의 epoch 보다 이전 epoch,
  같은 epoch 안의 seq 역행은
  버리고 dropped 에 센다. 같은 seq 의 반복은 그대로 옮긴다(신선도 판정은 수신 쪽이 seq 증가로 한다).
- gripper_command_seq(파라미터, 기본 false): 계약 11.6 의 그리퍼 두 토픽을 옮긴다(시뮬 #278 의 JSON v1).
  /isaac/amr_1/gripper/state(JSON) → /amr_1/gripper/state(GripperState, H). 버리는 조건은 belt_observation 과 같다.
  /amr_1/gripper/command_seq(GripperCommand, R) → /isaac/amr_1/gripper/command_seq(JSON). epoch 0 과 지금 epoch 보다
  이전 epoch 의 명령은 버리고 센다. seq 멱등(마지막 적용 seq 이하 무시)은 Isaac 이 한다. 여기서는 판정하지 않는다.
  Isaac 스테이지를 --gripper-command-seq 로 띄울 때 켠다. 기존 gripper/command·holding(Bool)은 이 노드가 다루지 않는다.
- sim_pouches·sim_tag_reads(파라미터, 둘 다 기본 false): 시뮬 센서를 옮긴다(K4·K5, 비전 규격 v2).
  /isaac/amr_1/pouches(JSON) → /amr_1/sim/pouches(PouchDetectionArray, H),
  /isaac/amr_1/tag_reads(JSON) → /amr_1/sim/tag_reads(TagRead, H).
  **계약 토픽 hand_camera/pouches·hand_camera/tag_reads 에는 내지 않는다** — 그 작성자는 perception 하나다.
  팔은 pouch_source·scan_tag_source 가 sim 일 때만 이 둘을 구독한다.
  - header.frame_id 와 header.stamp 는 JSON 값 그대로다(팔이 그 stamp 의 TF 로 base 로 옮긴다).
    stamp 는 sim time 이다. wall 을 실으면 팔이 전부 "오래된 검출" 로 버린다.
    **frame_id 를 검사하지 않는다.** 시뮬의 말: "검사하면 어댑터가 옳다고 믿는 이름이 하나 더 생긴다.
    지금은 스테이지 하나가 틀리면 틀리는 구조이고, 그게 추적하기 쉽다."
    그 대가는 **스테이지가 틀린 이름을 내면 아무도 안 막는다**는 것이다. 그래서 기동 줄
    (`sim_sensors on … frame=…`)과 팔의 arm_base_frame 을 대조하는 것이 선택이 아니라 이 구조의 짝이다.
  - pose 를 0 으로 채우지 않는다. 키가 없거나 null 이면 형식 오류로 버리고, 값이 0 이면 그대로 옮긴다
    (거리를 못 정했다는 판정은 팔이 한다).
  - kind·status 는 문자열이다. 모르는 값은 버린다(기본값을 조용히 넣지 않는다).
  - 빈 목록(detections: [])도 그대로 옮긴다. 그래야 팔이 시한을 다 기다리지 않고 "검출 0건" 으로 닫는다.
  - epoch 0 과 지난 epoch 는 버린다(다른 아홉과 같다). 센서에는 seq 가 없어 역행 판정은 없다.
- sim_cabinet(파라미터, 기본 false): K5b 보관함 참값을 옮긴다.
  /isaac/evaluator/cabinet(JSON) → /evaluator/cabinet(CabinetObservation, L 50).
  **계약 토픽 그대로 낸다** — 계약 46줄이 이 관측의 작성자를 isaac 으로 둔다(센서 둘과 다른 점이다).
  QoS 는 stub_sim 이 쓰던 것과 같은 latched 50 이라 늦게 붙은 event_logger 도 지난 값을 받는다.
  `present` 의 true→false 전이도 그대로 옮긴다. **run 기록의 SUCCESS 는 이 관측만이 근거이고
  (계약 8절) 어댑터가 만들어 내지 않는다** — 형식 오류·epoch 어긋남은 버리고 채우지 않는다.
  - **QoS: H(reliable·volatile·depth 1)로 구독한다.** 스테이지가 best effort 로 내면 **한 건도 못 받는다**
    (RELIABILITY 불일치, 9/21 실습27 P6). 호환 규칙은 한 줄이다 — 구독이 RELIABLE 이면 발행도
    RELIABLE 이어야 한다(반대는 된다). 스테이지 쪽 표는 `sim/standalone/p3sim/bridge.py` 의 `QOS` 이고,
    그 표와 이 노드의 구독을 맞대는 시험이 `test_isaac_adapter.py` 에 있다.
"""

import collections
import threading
import time

import rclpy
from builtin_interfaces.msg import Time
from rclpy.callback_groups import MutuallyExclusiveCallbackGroup, ReentrantCallbackGroup
from rclpy.clock import Clock, ClockType
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from std_msgs.msg import String

from rokey_p3_bringup.shutdown import spin_until_interrupted
from rokey_p3_bringup import isaac_json
from rokey_p3_interfaces.msg import (BeltObservation, BeltState, CabinetObservation, Event,
                                     GripperCommand, GripperState, PouchDetection,
                                     PouchDetectionArray, TagRead)
from rokey_p3_interfaces.srv import Dispense, Reset
from rokey_p3_orchestrator.ros_qos import heartbeat_qos, latched_qos, reliable_qos

DISPENSE_REQUEST = '/isaac/pharmacy/dispense_request'
DISPENSE_RESPONSE = '/isaac/pharmacy/dispense_response'
RESET_REQUEST = '/isaac/sim/reset_request'
RESET_RESPONSE = '/isaac/sim/reset_response'
BELT = '/isaac/pharmacy/belt'
EVENTS = '/isaac/events'
PICK_NOTICE = '/isaac/pharmacy/pick_notice'
BELT_OBSERVATION = '/isaac/pharmacy/belt_observation'
GRIPPER_STATE = '/isaac/amr_1/gripper/state'
GRIPPER_COMMAND_SEQ = '/isaac/amr_1/gripper/command_seq'
POUCHES = '/isaac/amr_1/pouches'
TAG_READS = '/isaac/amr_1/tag_reads'
SIM_POUCHES = '/amr_1/sim/pouches'
SIM_TAG_READS = '/amr_1/sim/tag_reads'
CABINET = '/isaac/evaluator/cabinet'
POLL_S = 0.01
SEEN_EVENTS = 2000             # 중복 판정에 기억하는 이벤트 수(/isaac/events depth 500 의 네 배)
LOG_THROTTLE_S = 5.0


class Waiter:
    """응답 하나를 기다린다. 응답 콜백 스레드가 채운다."""

    def __init__(self):
        self.done = threading.Event()
        self.response = None

    def fill(self, response):
        self.response = response
        self.done.set()


class IsaacAdapter(Node):
    """isaac_adapter 노드."""

    def __init__(self, **kwargs):
        super().__init__('isaac_adapter', **kwargs)
        self.declare_parameter('dispense_timeout_s', 2.0)      # 계약 7절
        self.declare_parameter('reset_timeout_s', 30.0)        # 계약 7절
        self.declare_parameter('pick_notice', True)
        self.declare_parameter('belt_observation', False)
        self.declare_parameter('gripper_command_seq', False)
        self.declare_parameter('sim_pouches', False)
        self.declare_parameter('sim_tag_reads', False)
        self.declare_parameter('sim_cabinet', False)
        self.declare_parameter('isaac_missing_after_s', 5.0)
        self.declare_parameter('isaac_missing_warn_every_s', 10.0)
        self._missing_after_s = float(self.get_parameter('isaac_missing_after_s').value)
        self._missing_warn_every_s = float(self.get_parameter('isaac_missing_warn_every_s').value)
        self._pick_notice = bool(self.get_parameter('pick_notice').value)
        self._belt_observation = bool(self.get_parameter('belt_observation').value)
        self._gripper_command_seq = bool(self.get_parameter('gripper_command_seq').value)
        self._sim_pouches = bool(self.get_parameter('sim_pouches').value)
        self._sim_tag_reads = bool(self.get_parameter('sim_tag_reads').value)
        self._sim_cabinet = bool(self.get_parameter('sim_cabinet').value)
        self._dispense_timeout_s = float(self.get_parameter('dispense_timeout_s').value)
        self._reset_timeout_s = float(self.get_parameter('reset_timeout_s').value)

        self._lock = threading.Lock()
        self._dispense_waiters = {}      # (request_id, order_id) → [Waiter]
        self._reset_waiters = {}         # epoch → [Waiter]
        self._epoch = 1                  # /events 에서 본 가장 큰 epoch
        self._seen = collections.deque(maxlen=SEEN_EVENTS)
        self._seen_keys = set()
        self.dropped = {'stale_belt': 0, 'duplicate_event': 0, 'gripper_command_bad_epoch': 0,
                        'gripper_command_stale_epoch': 0}
        for prefix in ('observation', 'gripper_state'):
            for reason in ('malformed', 'bad_epoch', 'stale_epoch', 'seq_regression'):
                self.dropped[f'{prefix}_{reason}'] = 0
        for prefix in ('pouches', 'tag_read', 'cabinet'):      # 센서에는 seq 가 없다
            for reason in ('malformed', 'bad_epoch', 'stale_epoch'):
                self.dropped[f'{prefix}_{reason}'] = 0
        self._relayed_seq = {}           # 관측 종류 → 마지막으로 옮긴 (epoch, seq)
        self.relayed = {'observation': 0, 'gripper_state': 0, 'gripper_command': 0,
                        'pouches': 0, 'tag_read': 0, 'cabinet': 0}
        self._last_belt = None           # 마지막으로 옮긴 belt (at_end, order_id)
        self._noticed = set()            # pick_notice 를 낸 (epoch, order_id)
        self.pick_notices = 0
        self._started_wall = time.monotonic()
        self._belt_wall = None           # 마지막 /isaac/pharmacy/belt 를 받은 wall
        self.isaac_missing = False       # 지금 Isaac 이 안 보인다고 판정했나
        self.missing_warnings = 0
        self.recovered_notices = 0
        self._last_missing_warn = None
        services = ReentrantCallbackGroup()
        inbound = MutuallyExclusiveCallbackGroup()
        # Dispense·Reset 응답은 서비스 콜백이 **기다리는** 것이라 다른 입력 뒤에 줄 세우지 않는다.
        # 9/24 c95e8f7 10건 #6 ord-0009: 스테이지는 매번 곧바로 accepted 로 답했는데(stall 0.3 s 1줄) 어댑터는
        # 세 번 다 10 s 안에 못 받아 not_ready 로 답했다. 응답 구독이 벨트·이벤트·센서와 한 상호배타 그룹이라
        # 그 뒤에서 기다렸다고 본다(추정). 응답 처리는 `_deliver` 가 lock 안에서만 공유 상태를 만진다.
        answers = MutuallyExclusiveCallbackGroup()

        self._dispense_pub = self.create_publisher(String, DISPENSE_REQUEST, reliable_qos(10))
        self._reset_pub = self.create_publisher(String, RESET_REQUEST, reliable_qos(10))
        self._belt_pub = self.create_publisher(BeltState, '/pharmacy/belt', heartbeat_qos())
        self._event_pub = self.create_publisher(Event, '/events', latched_qos(500))
        self._pick_pub = self.create_publisher(String, PICK_NOTICE, reliable_qos(10)) if self._pick_notice else None
        self._observation_pub = (self.create_publisher(BeltObservation, '/pharmacy/belt/observation', heartbeat_qos())
                                 if self._belt_observation else None)
        if self._gripper_command_seq:
            self._gripper_state_pub = self.create_publisher(GripperState, '/amr_1/gripper/state', heartbeat_qos())
            self._gripper_command_pub = self.create_publisher(String, GRIPPER_COMMAND_SEQ, reliable_qos(10))
        # 시뮬 센서. 계약 토픽(hand_camera/*)이 아니라 /{ns}/sim/* 로 낸다.
        self._pouches_pub = (self.create_publisher(PouchDetectionArray, SIM_POUCHES, heartbeat_qos())
                             if self._sim_pouches else None)
        self._tag_read_pub = (self.create_publisher(TagRead, SIM_TAG_READS, heartbeat_qos())
                              if self._sim_tag_reads else None)
        # 계약 토픽 그대로 낸다. 보관함 관측은 계약이 isaac 을 작성자로 둔다(계약 46줄).
        # QoS 는 stub_sim 이 쓰던 것과 같다(latched 50) — 늦게 붙은 event_logger 도 지난 값을 받는다.
        self._cabinet_pub = (self.create_publisher(CabinetObservation, '/evaluator/cabinet', latched_qos(50))
                             if self._sim_cabinet else None)

        self.create_subscription(String, DISPENSE_RESPONSE, self._on_dispense_response, reliable_qos(10),
                                 callback_group=answers)
        self.create_subscription(String, RESET_RESPONSE, self._on_reset_response, reliable_qos(10),
                                 callback_group=answers)
        self.create_subscription(String, BELT, self._on_belt, heartbeat_qos(), callback_group=inbound)
        self.create_subscription(String, EVENTS, self._on_isaac_event, latched_qos(500), callback_group=inbound)
        self.create_subscription(Event, '/events', self._on_event, latched_qos(500), callback_group=inbound)
        if self._belt_observation:
            self.create_subscription(String, BELT_OBSERVATION, self._on_belt_observation, heartbeat_qos(),
                                     callback_group=inbound)
        if self._gripper_command_seq:
            self.create_subscription(String, GRIPPER_STATE, self._on_gripper_state, heartbeat_qos(),
                                     callback_group=inbound)
            self.create_subscription(GripperCommand, '/amr_1/gripper/command_seq', self._on_gripper_command,
                                     reliable_qos(10), callback_group=inbound)
        if self._sim_pouches:
            self.create_subscription(String, POUCHES, self._on_pouches, heartbeat_qos(), callback_group=inbound)
        if self._sim_tag_reads:
            self.create_subscription(String, TAG_READS, self._on_tag_read, heartbeat_qos(), callback_group=inbound)
        if self._sim_cabinet:
            self.create_subscription(String, CABINET, self._on_cabinet, latched_qos(50), callback_group=inbound)

        self.create_timer(1.0, self._check_isaac, clock=Clock(clock_type=ClockType.STEADY_TIME), callback_group=inbound)
        self.create_service(Dispense, '/pharmacy/dispense', self._on_dispense, callback_group=services)
        self.create_service(Reset, '/sim/reset', self._on_reset, callback_group=services)
        self.get_logger().info(
            f'isaac_adapter up. 시한 Dispense {self._dispense_timeout_s:g} s, Reset {self._reset_timeout_s:g} s(wall). '
            f'pick_notice={self._pick_notice} belt_observation={self._belt_observation} '
            f'gripper_command_seq={self._gripper_command_seq} '
            f'sim_pouches={self._sim_pouches} sim_tag_reads={self._sim_tag_reads} sim_cabinet={self._sim_cabinet}')

    # 서비스 ---------------------------------------------------------------

    def _send_and_wait(self, publisher, text, waiters, key, timeout_s):
        """구독자가 보이면 보내고 응답을 기다린다. 시한 안에 못 받으면 (None, 이유)."""
        deadline = time.monotonic() + timeout_s
        waiter = Waiter()
        with self._lock:
            waiters.setdefault(key, []).append(waiter)
        try:
            while publisher.get_subscription_count() == 0:
                if time.monotonic() >= deadline or not rclpy.ok(context=self.context):
                    return None, f'{publisher.topic_name} 구독자(Isaac)가 {timeout_s:g} s 안에 안 보였다'
                time.sleep(POLL_S)
            publisher.publish(String(data=text))
            if waiter.done.wait(max(0.0, deadline - time.monotonic())):
                return waiter.response, ''
            return None, f'{timeout_s:g} s 안에 응답이 없다'
        finally:
            with self._lock:
                pending = waiters.get(key, [])
                if waiter in pending:
                    pending.remove(waiter)
                if not pending:
                    waiters.pop(key, None)

    def _on_dispense(self, request, response):
        try:
            text = isaac_json.dispense_request(request.request_id, request.order_id)
        except isaac_json.IsaacJsonError as error:
            self.get_logger().warning(
                f'Dispense {request.request_id!r} {request.order_id}: 보내지 않고 거부한다. {error}')
            response.accepted, response.message = False, 'not_ready'
            return response
        answer, reason = self._send_and_wait(
            self._dispense_pub, text, self._dispense_waiters, (request.request_id, request.order_id),
            self._dispense_timeout_s)
        if answer is None:
            self.get_logger().warning(f'Dispense {request.request_id} {request.order_id}: 거부로 답한다. {reason}')
            response.accepted, response.message = False, 'not_ready'
        else:
            if not answer['contract_message']:
                self.get_logger().warning(
                    f'Dispense {request.request_id} {request.order_id}: 거부 message {answer["message"]!r} 는 '
                    f'계약 2.1 의 {isaac_json.DISPENSE_REJECT_MESSAGES} 밖이다. 그대로 넘긴다.')
            response.accepted, response.message = answer['accepted'], answer['message']
        return response

    def _on_reset(self, request, response):
        answer, reason = self._send_and_wait(
            self._reset_pub, isaac_json.reset_request(request.epoch), self._reset_waiters, int(request.epoch),
            self._reset_timeout_s)
        if answer is None:
            self.get_logger().warning(f'/sim/reset epoch={request.epoch}: 실패로 답한다. {reason}')
            response.ok, response.message = False, f'isaac_adapter: {reason}'
        else:
            response.ok, response.message = answer['ok'], answer['message']
        return response

    # Isaac → 어댑터 ---------------------------------------------------------------

    def _parse(self, parser, msg, topic):
        try:
            return parser(msg.data)
        except isaac_json.IsaacJsonError as error:
            self.get_logger().warning(f'{topic} 형식 오류로 버린다: {error} | {msg.data[:200]}')
            return None

    def _deliver(self, waiters, key, answer, topic):
        with self._lock:
            pending = list(waiters.get(key, []))
        if not pending:
            self.get_logger().warning(
                f'{topic}: 기다리는 요청이 없는 응답을 버린다({key!r}). 시한 뒤에 왔거나 다른 요청이다.')
            return
        for waiter in pending:
            waiter.fill(answer)

    def _on_dispense_response(self, msg):
        answer = self._parse(isaac_json.parse_dispense_response, msg, DISPENSE_RESPONSE)
        if answer is not None:
            self._deliver(self._dispense_waiters, (answer['request_id'], answer['order_id']), answer,
                          DISPENSE_RESPONSE)

    def _on_reset_response(self, msg):
        answer = self._parse(isaac_json.parse_reset_response, msg, RESET_RESPONSE)
        if answer is not None:
            self._deliver(self._reset_waiters, answer['epoch'], answer, RESET_RESPONSE)

    def _epoch_of(self, epoch, topic):
        """Isaac epoch 를 계약 epoch 로. 0 이면 현재 epoch 로 바꾸고 warn 한다."""
        with self._lock:
            current = self._epoch
        if epoch == 0:
            self.get_logger().warning(
                f'{topic}: Isaac epoch 0 을 현재 epoch {current} 로 바꾼다(계약 4절 epoch 는 1 부터).',
                throttle_duration_sec=LOG_THROTTLE_S)
            return current, current
        return epoch, current

    def _on_belt(self, msg):
        with self._lock:
            self._belt_wall = time.monotonic()
        belt = self._parse(isaac_json.parse_belt, msg, BELT)
        if belt is None:
            return
        epoch, current = self._epoch_of(belt['epoch'], BELT)
        if epoch < current:
            self.dropped['stale_belt'] += 1
            self.get_logger().info(
                f'{BELT}: epoch {epoch} belt 를 버린다(현재 epoch {current}, 계약 4절). '
                f'버린 수 {self.dropped["stale_belt"]}',
                throttle_duration_sec=LOG_THROTTLE_S)
            return
        out = BeltState()
        out.header.stamp = Time(sec=belt['stamp'][0], nanosec=belt['stamp'][1])
        out.occupied = belt['occupied']
        out.at_end = belt['at_end']
        out.order_id = belt['order_id']
        with self._lock:
            self._last_belt = (belt['at_end'], belt['order_id'])
        self._belt_pub.publish(out)

    def _on_belt_observation(self, msg):
        self._relay(msg, BELT_OBSERVATION, isaac_json.parse_belt_observation, 'observation', BeltObservation,
                    ('epoch', 'seq', 'request_id', 'order_id', *isaac_json.OBSERVATION_ENUMS), self._observation_pub)

    def _on_gripper_state(self, msg):
        self._relay(msg, GRIPPER_STATE, isaac_json.parse_gripper_state, 'gripper_state', GripperState,
                    ('epoch', 'seq', 'last_applied_command_seq', *isaac_json.GRIPPER_ENUMS), self._gripper_state_pub)

    def _sensor_epoch_ok(self, kind, topic, epoch):
        """센서 메시지의 epoch 판정. 다른 아홉과 같다 — 0 과 지난 epoch 는 버리고 다음 메시지에서 회복한다.

        리셋 직후 스테이지가 새 epoch 를 싣기 전까지는 버려진다(그 사이 센서는 끊긴 것처럼 보인다).
        10 Hz 로 계속 오므로 스테이지가 새 epoch 를 실으면 바로 이어진다.
        """
        with self._lock:
            current = self._epoch
        if epoch == 0:
            self._drop(f'{kind}_bad_epoch', f'{topic}: epoch 0 을 버린다(epoch 를 추측하지 않는다).')
            return False
        if epoch < current:
            self._drop(f'{kind}_stale_epoch', f'{topic}: epoch {epoch} < 현재 {current}. 버린다.')
            return False
        return True

    def _on_pouches(self, msg):
        """시뮬 봉투 센서. 빈 목록도 그대로 옮긴다(팔이 "검출 0건" 으로 빨리 닫는다)."""
        try:
            data = isaac_json.parse_pouches(msg.data)
        except isaac_json.IsaacJsonError as error:
            self._drop('pouches_malformed', f'{POUCHES} 형식 오류로 버린다: {error} | {msg.data[:200]}')
            return
        if not self._sensor_epoch_ok('pouches', POUCHES, data['epoch']):
            return
        stamp = Time(sec=data['stamp'][0], nanosec=data['stamp'][1])
        out = PouchDetectionArray()
        out.header.stamp = stamp
        out.header.frame_id = data['frame_id']
        for item in data['detections']:
            detection = PouchDetection()
            detection.header.stamp = stamp
            detection.header.frame_id = data['frame_id']      # 원소에는 프레임이 없다. 최상위 값을 쓴다
            detection.order_id = item['order_id']
            detection.confidence = item['confidence']
            detection.pose.position.x, detection.pose.position.y, detection.pose.position.z = item['pose']['position']
            (detection.pose.orientation.x, detection.pose.orientation.y,
             detection.pose.orientation.z, detection.pose.orientation.w) = item['pose']['orientation']
            detection.slot_index = item['slot_index']
            out.detections.append(detection)
        with self._lock:
            self.relayed['pouches'] += 1
        self._pouches_pub.publish(out)

    def _on_tag_read(self, msg):
        """시뮬 인식표 센서. kind·status 가 모르는 값이면 형식 오류로 버린다(기본값을 넣지 않는다).

        `zone_id` 는 `TagRead.msg` 에 자리가 없어 옮기지 않는다. 형식 검사만 한다.
        """
        try:
            data = isaac_json.parse_tag_read(msg.data)
        except isaac_json.IsaacJsonError as error:
            self._drop('tag_read_malformed', f'{TAG_READS} 형식 오류로 버린다: {error} | {msg.data[:200]}')
            return
        if not self._sensor_epoch_ok('tag_read', TAG_READS, data['epoch']):
            return
        out = TagRead()
        out.header.stamp = Time(sec=data['stamp'][0], nanosec=data['stamp'][1])
        out.header.frame_id = data['frame_id']
        out.kind = data['kind']
        out.tag_id = data['tag_id']
        out.status = data['status']
        with self._lock:
            self.relayed['tag_read'] += 1
        self._tag_read_pub.publish(out)

    def _on_cabinet(self, msg):
        """K5b 보관함 참값. `present` 의 true→false 전이도 그대로 옮긴다(봉투를 꺼낸 것이다).

        run 기록의 SUCCESS 는 이 관측만이 근거다(계약 8절). **어댑터가 만들어 내지 않는다** —
        형식이 틀리거나 epoch 가 어긋나면 버리고, 채워 넣지 않는다.
        """
        try:
            data = isaac_json.parse_cabinet(msg.data)
        except isaac_json.IsaacJsonError as error:
            self._drop('cabinet_malformed', f'{CABINET} 형식 오류로 버린다: {error} | {msg.data[:200]}')
            return
        if not self._sensor_epoch_ok('cabinet', CABINET, data['epoch']):
            return
        out = CabinetObservation()
        out.header.stamp = Time(sec=data['stamp'][0], nanosec=data['stamp'][1])
        out.cabinet_id = data['cabinet_id']
        out.order_id = data['order_id']
        out.present = data['present']
        with self._lock:
            self.relayed['cabinet'] += 1
        self._cabinet_pub.publish(out)

    def _relay(self, msg, topic, parser, kind, msg_type, fields, publisher):
        """계약 11.6 관측 하나를 옮긴다. 버리는 조건은 모듈 docstring. 필드와 enum 정수값은 JSON 과 msg 가 같다."""
        try:
            obs = parser(msg.data)
        except isaac_json.IsaacJsonError as error:
            self._drop(f'{kind}_malformed', f'{topic} 형식 오류로 버린다: {error} | {msg.data[:200]}')
            return
        with self._lock:
            current = self._epoch
            last = self._relayed_seq.get(kind)
        if obs['epoch'] == 0:
            self._drop(f'{kind}_bad_epoch', f'{topic}: epoch 0 을 버린다(epoch 를 추측하지 않는다).')
            return
        newest = max(current, last[0] if last is not None else 0)
        if obs['epoch'] < newest:
            self._drop(f'{kind}_stale_epoch',
                       f'{topic}: epoch {obs["epoch"]} < {newest}(현재 또는 이미 옮긴 관측). 버린다.')
            return
        if last is not None and last[0] == obs['epoch'] and obs['seq'] < last[1]:
            self._drop(f'{kind}_seq_regression',
                       f'{topic}: epoch {obs["epoch"]} 에서 seq {obs["seq"]} < {last[1]}. 버린다.')
            return
        out = msg_type()
        out.header.stamp = Time(sec=obs['stamp'][0], nanosec=obs['stamp'][1])
        for name in fields:
            setattr(out, name, obs[name])
        with self._lock:
            self._relayed_seq[kind] = (obs['epoch'], obs['seq'])
            self.relayed[kind] += 1
        publisher.publish(out)

    def _on_gripper_command(self, msg):
        """arm 의 GripperCommand 를 Isaac JSON 으로. epoch 만 본다. seq 멱등은 Isaac 이 한다."""
        with self._lock:
            current = self._epoch
        if msg.epoch == 0:
            self._drop('gripper_command_bad_epoch', '/amr_1/gripper/command_seq: epoch 0 명령을 버린다.')
            return
        if msg.epoch < current:
            self._drop('gripper_command_stale_epoch',
                       f'/amr_1/gripper/command_seq: epoch {msg.epoch} < 현재 {current}. 버린다.')
            return
        self._gripper_command_pub.publish(String(data=isaac_json.gripper_command(
            msg.header.stamp.sec, msg.header.stamp.nanosec, msg.epoch, msg.command_seq, msg.close)))
        with self._lock:
            self.relayed['gripper_command'] += 1

    def _drop(self, key, text):
        with self._lock:
            self.dropped[key] += 1
            count = self.dropped[key]
        self.get_logger().warning(f'{text} 버린 수 {count}', throttle_duration_sec=LOG_THROTTLE_S)

    def _check_isaac(self):
        """Isaac 이 안 보이는지 1 s 마다 판정한다(모듈 docstring). 형식 오류로 버린 belt 도 받은 것으로 친다."""
        now = time.monotonic()
        subscribers = self._dispense_pub.get_subscription_count() + self._reset_pub.get_subscription_count()
        with self._lock:
            belt_wall = self._belt_wall
        silent_s = now - (belt_wall if belt_wall is not None else self._started_wall)
        missing = subscribers == 0 and silent_s > self._missing_after_s
        if missing:
            if self._last_missing_warn is None or now - self._last_missing_warn >= self._missing_warn_every_s:
                self._last_missing_warn = now
                self.missing_warnings += 1
                heard = (f'{silent_s:.0f} s 무소식' if belt_wall is not None
                         else f'기동 뒤 {silent_s:.0f} s 동안 한 번도 없음')
                self.get_logger().warning(
                    f'Isaac 스테이지가 안 보인다(요청 토픽 구독자 0, {BELT} {heard}). '
                    f'pharmacy_stage(--mode ros)를 띄웠는지, ROS_DOMAIN_ID 가 같은지 확인한다. '
                    f'그동안 orchestrator 는 벨트 unknown 으로 배출을 기다린다.')
        elif self.isaac_missing:
            self.recovered_notices += 1
            self._last_missing_warn = None
            self.get_logger().info(f'Isaac 스테이지가 다시 보인다(요청 토픽 구독자 {subscribers}).')
        self.isaac_missing = missing

    def _on_isaac_event(self, msg):
        event = self._parse(isaac_json.parse_event, msg, EVENTS)
        if event is None:
            return
        key = (event['epoch'], event['name'], event['stamp'], event['order_id'], event['request_id'])
        if not self._remember(key):
            self.dropped['duplicate_event'] += 1
            self.get_logger().info(
                f'{EVENTS}: 이미 옮긴 이벤트를 버린다(재수신). 버린 수 {self.dropped["duplicate_event"]}',
                throttle_duration_sec=LOG_THROTTLE_S)
            return
        out = Event()
        out.header.stamp = Time(sec=event['stamp'][0], nanosec=event['stamp'][1])
        out.name = event['name']
        out.request_id = event['request_id']
        out.order_id = event['order_id']
        out.robot_id = event['robot_id']
        out.epoch, _ = self._epoch_of(event['epoch'], EVENTS)
        out.detail = event['detail']
        self._event_pub.publish(out)

    def _remember(self, key):
        """처음 본 키면 기억하고 True, 이미 본 키면 False."""
        with self._lock:
            if key in self._seen_keys:
                return False
            if len(self._seen) == self._seen.maxlen:
                self._seen_keys.discard(self._seen[0])
            self._seen.append(key)
            self._seen_keys.add(key)
            return True

    def _on_event(self, msg):
        with self._lock:
            if msg.epoch > self._epoch:
                self._epoch = msg.epoch
        if msg.robot_id == isaac_json.EVENT_ROBOT_ID and msg.name in isaac_json.EVENT_NAMES:
            self._remember((msg.epoch, msg.name, (msg.header.stamp.sec, msg.header.stamp.nanosec),
                            msg.order_id, msg.request_id))
        elif msg.name == Event.POUCH_PICKED and msg.robot_id.startswith('amr_'):
            self._maybe_notice_pick(msg)

    def _maybe_notice_pick(self, msg):
        """적재 픽이면 Isaac 에 pick_notice 한 번. 조건은 모듈 docstring."""
        if self._pick_pub is None or not msg.order_id:
            return
        key = (msg.epoch, msg.order_id)
        with self._lock:
            if (msg.epoch != self._epoch or self._last_belt != (True, msg.order_id) or key in self._noticed):
                return
            self._noticed.add(key)
            self.pick_notices += 1
        self._pick_pub.publish(String(data=isaac_json.pick_notice(
            msg.header.stamp.sec, msg.header.stamp.nanosec, msg.epoch, msg.order_id)))
        self.get_logger().info(f'{PICK_NOTICE}: epoch {msg.epoch} {msg.order_id} 봉투를 팔이 집었다고 알린다.')


def main(args=None):
    """콘솔 진입점."""
    rclpy.init(args=args)
    node = IsaacAdapter()
    # 서비스 콜백이 응답을 기다리며 스레드를 잡는다. 응답 구독은 다른 스레드에서 돈다.
    executor = MultiThreadedExecutor(num_threads=8)
    executor.add_node(node)
    spin_until_interrupted(node, executor)


if __name__ == '__main__':
    main()
