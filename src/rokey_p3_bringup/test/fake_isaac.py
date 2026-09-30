"""테스트용 가짜 Isaac. sim/README.md 의 JSON 표(v1)대로만 말한다. 조제실 스테이지를 대신한다.

- /isaac/pharmacy/dispense_request 에 표의 판정 순서로 답한다(unknown_order → belt_occupied → 수락).
  수락하면 벨트에 봉투를 올리고 DISPENSED, belt_travel_s(wall) 뒤 at_end 와 POUCH_AT_END 를 낸다.
- /isaac/sim/reset_request 에 벨트를 비우고 epoch 를 그대로 돌려준다.
  이후 belt·events 에 그 epoch 를 싣는다. 첫 리셋 전은 1(sim/README 889d895).
- /isaac/pharmacy/pick_notice 를 받으면 epoch 가 같고 벨트 끝 봉투의 order_id 와 같을 때만 벨트를 비운다(415e4ae).
- /isaac/pharmacy/belt 를 5 Hz(wall) 로 낸다. stamp 는 sim time(use_sim_time, 스텁의 /clock)이다.
  publish_clock=True 면 실물 스테이지처럼 /clock 을 스스로 낸다(60 Hz, 기동 뒤 wall 경과를 sim time 으로).
  그때는 use_sim_time 을 쓰지 않고 자기 시계로 stamp 를 찍는다.
- 형식 오류인 요청에는 답하지 않는다(표와 같다).
- publish_belt_observation=True 면 /isaac/pharmacy/belt_observation(계약 11.6, 시뮬 #276 의 JSON v1)도
  belt 와 같은 주기로 낸다.
  물리가 없으므로 mode 는 STUB 다. 벨트 끝 봉투는 zone END·STOPPED·APPLIED_STOP, 이동 중은 ON_BELT·MOVING·APPLIED_RUN,
  빈 벨트는 EMPTY·zone/motion UNKNOWN·APPLIED_STOP 이다. belt_motion 은 항상 UNKNOWN. seq 는 발행마다 +1(리셋에서 0).
- gripper_command_seq=True 면 /isaac/amr_1/gripper/command_seq(JSON, 시뮬 #278)를 받아 적용하고
  /isaac/amr_1/gripper/state 를 10 Hz 로 낸다. 다른 epoch 와 마지막 적용 seq 이하의 명령은 무시한다. mode 는 VIRTUAL,
  close 면 HELD(쥘 봉투를 따지지 않는다). seq 는 벨트 관측과 같은 카운터를 쓴다. 리셋에서 적용 seq 를 0 으로.

가짜 Isaac 은 계약 토픽을 구독하지 않는다. 봉투가 집힌 것은 pick_notice 로만 안다.
"""

import time

from builtin_interfaces.msg import Time
from rclpy.clock import Clock, ClockType
from rclpy.node import Node
from rclpy.parameter import Parameter
from rosgraph_msgs.msg import Clock as ClockMsg
from std_msgs.msg import String

from rokey_p3_bringup import isaac_json
from rokey_p3_bringup.stubs import common
from rokey_p3_orchestrator.ros_qos import heartbeat_qos, latched_qos, reliable_qos


class FakeIsaac(Node):
    """fake_isaac 노드."""

    def __init__(self, pool_path, belt_travel_s=0.3, publish_clock=False, publish_belt_observation=False,
                 gripper_command_seq=False):
        super().__init__('fake_isaac', parameter_overrides=[Parameter('use_sim_time', value=not publish_clock)])
        self._publish_clock = publish_clock
        self._started = time.monotonic()
        self._pool = common.load_pool_index(pool_path)
        self._travel_s = belt_travel_s
        self.epoch = 1
        self.responses = []          # 보낸 dispense_response 원문
        self.notices = []            # 받은 pick_notice 원문
        self.requests = []           # 받은 JSON 원문(형식 오류 포함)
        self._belt = {'occupied': False, 'at_end': False, 'order_id': ''}
        self._request_id = ''
        self._at_end_wall = None
        self._seq = 0
        self.gripper = {'last_applied': 0, 'state': 1}     # RELEASED
        self.gripper_commands = []  # 받은 command_seq 원문

        self._dispense_pub = self.create_publisher(String, '/isaac/pharmacy/dispense_response', reliable_qos(10))
        self._reset_pub = self.create_publisher(String, '/isaac/sim/reset_response', reliable_qos(10))
        self._belt_pub = self.create_publisher(String, '/isaac/pharmacy/belt', heartbeat_qos())
        self._event_pub = self.create_publisher(String, '/isaac/events', latched_qos(500))
        self._observation_pub = (self.create_publisher(String, '/isaac/pharmacy/belt_observation', heartbeat_qos())
                                 if publish_belt_observation else None)
        self.create_subscription(String, '/isaac/pharmacy/dispense_request', self._on_dispense, reliable_qos(10))
        self.create_subscription(String, '/isaac/sim/reset_request', self._on_reset, reliable_qos(10))
        self.create_subscription(String, '/isaac/pharmacy/pick_notice', self._on_pick_notice, reliable_qos(10))
        if gripper_command_seq:
            self._gripper_pub = self.create_publisher(String, '/isaac/amr_1/gripper/state', heartbeat_qos())
            self.create_subscription(String, '/isaac/amr_1/gripper/command_seq', self._on_gripper_command,
                                     reliable_qos(10))
        # 스텁 /clock 이면 노드 시계 타이머라 /clock 이 오기 전에는 돌지 않는다(stamp 0 으로 내지 않는다).
        timer_clock = None
        if publish_clock:
            timer_clock = Clock(clock_type=ClockType.STEADY_TIME)
            self._clock_pub = self.create_publisher(ClockMsg, '/clock', reliable_qos(10))
            self.create_timer(1.0 / 60.0, self._publish_clock_tick, clock=timer_clock)
        self.create_timer(0.2, self._publish_belt, clock=timer_clock)
        self.create_timer(0.05, self._advance, clock=timer_clock)
        if gripper_command_seq:
            self.create_timer(0.1, self._publish_gripper, clock=timer_clock)

    def _now(self):
        if self._publish_clock:
            seconds = time.monotonic() - self._started
            return int(seconds), int((seconds % 1.0) * 1e9)
        stamp = self.get_clock().now().to_msg()
        return stamp.sec, stamp.nanosec

    def _publish_clock_tick(self):
        sec, nanosec = self._now()
        self._clock_pub.publish(ClockMsg(clock=Time(sec=sec, nanosec=nanosec)))

    def _emit(self, name, order_id):
        self._event_pub.publish(String(data=isaac_json.event(*self._now(), name, self._request_id, order_id,
                                                             self.epoch)))

    def _on_dispense(self, msg):
        self.requests.append(msg.data)
        try:
            request = isaac_json.parse_dispense_request(msg.data)
        except isaac_json.IsaacJsonError as error:
            self.get_logger().warning(f'dispense_request 형식 오류, 답하지 않는다: {error}')
            return
        if request['order_id'] not in self._pool:
            accepted, message = False, 'unknown_order'
        elif self._belt['occupied']:
            accepted, message = False, 'belt_occupied'
        else:
            accepted, message = True, ''
            self._belt = {'occupied': True, 'at_end': False, 'order_id': request['order_id']}
            self._request_id = request['request_id']
            self._at_end_wall = time.monotonic() + self._travel_s
            self._emit('DISPENSED', request['order_id'])
        text = isaac_json.dispense_response(request['request_id'], request['order_id'], accepted, message)
        self.responses.append(text)
        self._dispense_pub.publish(String(data=text))

    def _on_reset(self, msg):
        self.requests.append(msg.data)
        try:
            request = isaac_json.parse_reset_request(msg.data)
        except isaac_json.IsaacJsonError as error:
            self.get_logger().warning(f'reset_request 형식 오류, 답하지 않는다: {error}')
            return
        self.epoch = request['epoch']
        self._belt = {'occupied': False, 'at_end': False, 'order_id': ''}
        self._request_id = ''
        self._at_end_wall = None
        self._seq = 0
        self.gripper = {'last_applied': 0, 'state': 1}
        self._reset_pub.publish(String(data=isaac_json.reset_response(request['epoch'], True)))

    def _on_pick_notice(self, msg):
        self.notices.append(msg.data)
        try:
            notice = isaac_json.parse_pick_notice(msg.data)
        except isaac_json.IsaacJsonError as error:
            self.get_logger().warning(f'pick_notice 형식 오류, 무시한다: {error}')
            return
        if notice['epoch'] != self.epoch or not self._belt['at_end'] or notice['order_id'] != self._belt['order_id']:
            self.get_logger().info(f'pick_notice 무시: {notice} epoch={self.epoch} belt={self._belt}')
            return
        self._belt = {'occupied': False, 'at_end': False, 'order_id': ''}
        self._at_end_wall = None

    def _advance(self):
        if self._at_end_wall is None or time.monotonic() < self._at_end_wall:
            return
        self._at_end_wall = None
        self._belt['at_end'] = True
        self._emit('POUCH_AT_END', self._belt['order_id'])

    def _publish_belt(self):
        self._belt_pub.publish(String(data=isaac_json.belt(
            *self._now(), self._belt['occupied'], self._belt['at_end'], self._belt['order_id'], self.epoch)))
        if self._observation_pub is not None:
            self._publish_observation()

    def _on_gripper_command(self, msg):
        self.gripper_commands.append(msg.data)
        try:
            command = isaac_json.parse_gripper_command(msg.data)
        except isaac_json.IsaacJsonError as error:
            self.get_logger().warning(f'gripper command_seq 형식 오류, 무시한다: {error}')
            return
        if command['epoch'] != self.epoch or command['command_seq'] <= self.gripper['last_applied']:
            return
        self.gripper = {'last_applied': command['command_seq'], 'state': 2 if command['close'] else 1}

    def _publish_gripper(self):
        self._seq += 1
        self._gripper_pub.publish(String(data=isaac_json.gripper_state(
            *self._now(), self.epoch, self._seq, self.gripper['last_applied'], self.gripper['state'], mode=1)))

    def _publish_observation(self):
        # 정수값은 BeltObservation.msg 상수와 같다: MODE_STUB=1, OCCUPANCY_EMPTY=1/OCCUPIED=2,
        # ZONE_ON_BELT=1/END=2, MOTION_MOVING=1/STOPPED=2, APPLIED_RUN=1/STOP=2.
        self._seq += 1
        occupied, at_end = self._belt['occupied'], self._belt['at_end']
        zone, motion = (2, 2) if at_end else ((1, 1) if occupied else (0, 0))
        applied = 1 if occupied and not at_end else 2
        self._observation_pub.publish(String(data=isaac_json.belt_observation(
            *self._now(), self.epoch, self._seq, self._request_id if occupied else '', self._belt['order_id'],
            mode=1, occupancy=2 if occupied else 1, pouch_zone=zone, pouch_motion=motion,
            belt_command_applied=applied)))
