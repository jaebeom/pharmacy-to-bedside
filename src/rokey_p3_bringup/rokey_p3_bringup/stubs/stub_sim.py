"""스텁 시뮬레이터. isaac_standalone 을 계약과 같은 이름으로 대신한다(계약 8절).

내는 것: /clock, /pharmacy/belt, /amr_1/gripper/holding, /evaluator/cabinet, DISPENSED, POUCH_AT_END.
받는 것: /pharmacy/dispense, /sim/reset.

/clock 작성자는 하나다(계약 4절). 브릿지가 /clock 을 내는 구성에서는 publish_clock=false 로
/clock 을 내지 않고, use_sim_time=true 로 브릿지 시계를 따라 stamp 를 찍는다.
publish_clock 과 use_sim_time 은 서로 반대여야 한다. launch 가 그렇게 묶는다.

지름길 둘:
- 봉투가 어느 보관함에 들어갔는지는 주문 풀 파일로 안다. 스텁은 볼 수 없다.
- /clock 을 되감지 않는다. 리셋 때 씬 상태만 지운다. sim time 되감기는 Isaac 것이고 L3 에서 본다.

M0609(emulate_m0609=true, 기본). 브릿지가 M0609 를 아직 안 낼 때 m0609_arm 의 닫힌 루프를 닫는다.
- 내는 것: /m0609/joint_states(S 30 Hz, 시작은 전부 0 = 홈), /m0609/gripper/holding(H 10 Hz).
- 받는 것: /m0609/arm/joint_command, /m0609/gripper/command.
- 관절은 받은 position 을 다음 발행부터 그대로 되돌린다. 보간·지연·관절 한계가 없다. 스텁은 물리가 아니다.
- 그리퍼는 닫기 뒤 m0609_settle_s 가 지나면 holding true, 열기면 바로 false.
  캐니스터가 그 자리에 있는지는 보지 않는다. 이것도 지름길이다.
- /sim/reset 이면 그리퍼를 열고(holding false), m0609_reset_homes=true(기본)면 관절도 0 으로 둔다.
  계약 6절 2 가 M0609 홈·그리퍼·캐니스터를 isaac 리셋 범위에 둔다(PR docs/contract-v1-reset-m0609-dispense 기준).
  false 면 관절을 그대로 둔다. m0609_arm 이 RESET_DONE 뒤 스스로 홈으로 가는 경로를 L2 에서 보기 위한 것이다.
브릿지가 M0609 를 내면 emulate_m0609=false. 안 그러면 /m0609/joint_states 작성자가 둘이 된다.

Isaac 어댑터(isaac_adapter)가 조제기·리셋을 맡을 때는 기능별로 끈다. 기본값은 모두 true(지금 거동)다.
- serve_dispense=false: /pharmacy/dispense 서버를 열지 않는다. 그러면 DISPENSED·POUCH_AT_END 도 내지 않는다
  (Isaac 이 낸다).
- serve_reset=false: /sim/reset 서버를 열지 않는다. 스텁에 남은 씬 상태(그리퍼 holding, 보관함 관측, M0609, 벨트)는
  새 epoch 의 RESET_DONE 을 보면 /sim/reset 때와 같은 규칙으로 비운다.
  RESET_DONE 은 /sim/reset ok 뒤에만 나온다(계약 6절 3).
- publish_belt=false: /pharmacy/belt 를 내지 않는다(작성자는 어댑터 하나).
- publish_cabinet=false: /evaluator/cabinet 을 내지 않는다. Isaac 이 보관함 참값을 낼 때 쓴다(K5).
  run 기록의 SUCCESS 근거가 이 토픽 하나뿐이라(계약 8절) 끄면 **그 회차는 관측이 없다** —
  Isaac 쪽 작성자가 실제로 낼 때만 끈다. 스텁은 관측을 만들지 않을 뿐 상태(_cabinet)는 그대로 둔다.
"""

import time

import rclpy
from builtin_interfaces.msg import Time
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from rosgraph_msgs.msg import Clock
from sensor_msgs.msg import JointState
from std_msgs.msg import Bool

from rokey_p3_bringup.shutdown import spin_until_interrupted
from rokey_p3_bringup.stubs import common
from rokey_p3_interfaces.msg import BeltState, CabinetObservation
from rokey_p3_interfaces.srv import Dispense, Reset
from rokey_p3_orchestrator.ros_qos import heartbeat_qos, latched_qos, reliable_qos, sensor_qos

#: m0609_arm(PR #51) 의 DEFAULT_JOINT_NAMES 와 같은 문자열이다. USD 조인트의 실제 이름은 아직 모른다.
#: 마스터에서 확인하면 양쪽 파라미터(m0609_joint_names, joint_names)로 덮는다.
M0609_JOINT_NAMES = ('joint_1', 'joint_2', 'joint_3', 'joint_4', 'joint_5', 'joint_6')
M0609_JOINT_RATE_HZ = 30.0      # 계약 2.1절: joint_states 는 S, 30 Hz


class StubSim(Node):
    """stub_sim 노드."""

    def __init__(self, **kwargs):
        super().__init__('stub_sim', **kwargs)
        self.declare_parameter('order_pool_file', '')
        self.declare_parameter('belt_travel_s', 1.0)
        self.declare_parameter('clock_rate_hz', 60.0)
        self.declare_parameter('publish_clock', True)
        # 리셋 실패 주입(검증용). 기본값이면 지금 거동이다. /sim/reset 마다 다시 읽어서 ros2 param set 으로 켜고 끈다.
        self.declare_parameter('reset_fail', False)      # true 면 씬을 건드리지 않고 ok=false
        # 응답 전 wall 대기. orchestrator reset_timeout_s 보다 길면 무응답과 같다
        self.declare_parameter('reset_delay_s', 0.0)
        self.declare_parameter('serve_dispense', True)
        self.declare_parameter('serve_reset', True)
        self.declare_parameter('publish_belt', True)
        self.declare_parameter('publish_cabinet', True)
        self._serve_dispense = bool(self.get_parameter('serve_dispense').value)
        self._serve_reset = bool(self.get_parameter('serve_reset').value)
        self._publishes_belt = bool(self.get_parameter('publish_belt').value)
        self._publishes_cabinet = bool(self.get_parameter('publish_cabinet').value)
        self._scene_reset_epoch = 1     # serve_reset=false 일 때 RESET_DONE 으로 비운 마지막 epoch
        self._pool = common.load_pool_index(
            self.get_parameter('order_pool_file').value or common.default_pool_path())
        self._travel_s = float(self.get_parameter('belt_travel_s').value)
        self._publishes_clock = bool(self.get_parameter('publish_clock').value)
        use_sim_time = bool(self.get_parameter('use_sim_time').value)
        if self._publishes_clock == use_sim_time:
            # 둘 다 true 면 자기 /clock 을 기다리느라 타이머가 서고, 둘 다 false 면 stamp 가 wall 이 된다.
            self.get_logger().warning(
                f'publish_clock={self._publishes_clock} 인데 use_sim_time={use_sim_time} 이다. '
                '서로 반대여야 한다(계약 4절).')

        self._started = time.monotonic()
        self._belt = BeltState()
        self._holding = False
        self._cabinet = {}
        self._pending_at_end = None
        self._belt_request_id = ''       # 벨트 위 봉투를 배출한 요청. POUCH_AT_END 에 싣는다(Isaac 과 같다)
        group = ReentrantCallbackGroup()

        if self._publishes_clock:
            self._clock_pub = self.create_publisher(Clock, '/clock', reliable_qos())
        if self._publishes_belt:
            self._belt_pub = self.create_publisher(BeltState, '/pharmacy/belt', heartbeat_qos())
        self._holding_pub = self.create_publisher(
            Bool, f'/{common.NAMESPACE}/gripper/holding', heartbeat_qos())
        self._cabinet_pub = (self.create_publisher(
            CabinetObservation, '/evaluator/cabinet', latched_qos(50))
            if self._publishes_cabinet else None)

        self._events = common.EventIo(self, 'dispenser', self._on_event, self._stamp)
        if self._serve_dispense:
            self.create_service(Dispense, '/pharmacy/dispense', self._on_dispense, callback_group=group)
        if self._serve_reset:
            self.create_service(Reset, '/sim/reset', self._on_reset, callback_group=group)
        self._setup_m0609()

        if self._publishes_clock:
            rate = float(self.get_parameter('clock_rate_hz').value)
            self.create_timer(1.0 / rate, self._publish_clock)
        if self._publishes_belt:
            self.create_timer(0.2, self._publish_belt)  # H = 5 Hz
        self.create_timer(0.1, self._publish_holding)   # H = 10 Hz
        self.create_timer(1.0, self._publish_cabinet)
        self.create_timer(0.05, self._advance_belt)
        if self._publishes_clock:
            self.get_logger().info('stub_sim up. /clock 을 낸다. use_sim_time 은 쓰지 않는다.')
        else:
            self.get_logger().info('stub_sim up. /clock 은 내지 않고 브릿지 /clock 을 따른다.')
        off = [name for name, on in (('/pharmacy/dispense', self._serve_dispense), ('/sim/reset', self._serve_reset),
                                     ('/pharmacy/belt', self._publishes_belt)) if not on]
        if off:
            self.get_logger().info(f'stub_sim: {", ".join(off)} 는 맡지 않는다(Isaac 어댑터).')

    # 시간 ---------------------------------------------------------------

    def _seconds(self):
        """벨트 이동 판정용 wall 경과. 스텁 내부 타이밍이지 측정값이 아니다."""
        return time.monotonic() - self._started

    def _stamp(self):
        """sim time stamp(계약 4절). /clock 을 내지 않으면 브릿지 /clock 을 따른 노드 시계다."""
        if not self._publishes_clock:
            return self.get_clock().now().to_msg()
        seconds = self._seconds()
        return Time(sec=int(seconds), nanosec=int((seconds % 1.0) * 1e9))

    def _publish_clock(self):
        self._clock_pub.publish(Clock(clock=self._stamp()))

    # 상태 토픽 ------------------------------------------------------------

    def _publish_belt(self):
        self._belt.header.stamp = self._stamp()
        self._belt_pub.publish(self._belt)

    def _publish_holding(self):
        self._holding_pub.publish(Bool(data=self._holding))

    def _publish_cabinet(self):
        for order_id, cabinet in sorted(self._cabinet.items()):
            self._emit_cabinet(order_id, cabinet)

    def _emit_cabinet(self, order_id, cabinet):
        if self._cabinet_pub is None:      # 작성자가 Isaac 하나다. 상태는 그대로 두고 내지만 않는다.
            return
        msg = CabinetObservation()
        msg.header.stamp = self._stamp()
        msg.cabinet_id = cabinet
        msg.order_id = order_id
        msg.present = True
        self._cabinet_pub.publish(msg)

    # 벨트 ---------------------------------------------------------------

    def _advance_belt(self):
        if self._pending_at_end is None or self._seconds() < self._pending_at_end:
            return
        self._pending_at_end = None
        self._belt.at_end = True
        self._events.emit('POUCH_AT_END', self._belt_request_id, self._belt.order_id)

    def _on_dispense(self, request, response):
        if self._belt.occupied:
            response.accepted = False
            response.message = 'belt_occupied'
            return response
        if request.order_id not in self._pool:
            response.accepted = False
            response.message = 'unknown_order'
            return response
        self._belt.occupied = True
        self._belt.at_end = False
        self._belt.order_id = request.order_id
        self._pending_at_end = self._seconds() + self._travel_s
        self._belt_request_id = request.request_id
        self._events.emit('DISPENSED', request.request_id, request.order_id)
        response.accepted = True
        response.message = ''
        return response

    def _on_reset(self, request, response):
        """계약 6절 2. 봉투 prim 삭제, 벨트 정지, 그리퍼 열기.

        실패 주입: reset_delay_s 만큼 응답을 늦추고(그동안 씬은 그대로), reset_fail 이면 씬을 건드리지 않고
        ok=false 로 답한다. 늦춘 응답도 결국 보낸다. 시한을 넘긴 orchestrator 에게는 늦은 응답이다.
        """
        delay = float(self.get_parameter('reset_delay_s').value)
        if delay > 0.0:
            self.get_logger().warning(
                f'reset epoch={request.epoch}: reset_delay_s={delay:g} 만큼 응답을 늦춘다(실패 주입).')
            deadline = time.monotonic() + delay
            while rclpy.ok(context=self.context) and time.monotonic() < deadline:
                time.sleep(0.05)
        if bool(self.get_parameter('reset_fail').value):
            self.get_logger().warning(f'reset epoch={request.epoch}: reset_fail=true. ok=false 로 답한다(실패 주입).')
            response.ok = False
            response.message = 'reset_fail'
            return response
        self._reset_scene()
        homed = '홈' if self._m0609_reset_homes else '관절 그대로'
        self.get_logger().info(f'reset epoch={request.epoch}. 벨트와 보관함을 비웠다. M0609 는 {homed}, 그리퍼 열림.')
        response.ok = True
        response.message = ''
        return response

    def _reset_scene(self):
        """계약 6절 2 중 스텁이 가진 씬 상태를 비운다."""
        self._belt = BeltState()
        self._belt_request_id = ''
        self._holding = False
        self._cabinet.clear()
        self._pending_at_end = None
        # 계약 6절 2 가 M0609 홈·그리퍼·캐니스터를 isaac 리셋 범위에 둔다
        # (PR docs/contract-v1-reset-m0609-dispense 기준).
        # 스텁은 그대로 리셋 때 관절 0·holding false. m0609_reset_homes=false 면 관절은 두고 그리퍼만 연다.
        if self._m0609_reset_homes:
            self._m0609_joints = [0.0] * len(self._m0609_names)
        self._m0609_closed_at = None

    # 팔이 낸 이벤트로 물리를 흉내 낸다 ------------------------------------

    def _on_event(self, msg):
        if msg.name == 'RESET_DONE' and not self._serve_reset and msg.epoch > self._scene_reset_epoch:
            # /sim/reset 을 Isaac 이 맡는다. 스텁에 남은 씬 상태도 같은 리셋을 따른다.
            self._scene_reset_epoch = msg.epoch
            self._reset_scene()
            self.get_logger().info(
                f'RESET_DONE epoch={msg.epoch}. /sim/reset 은 Isaac 이 맡았다. 스텁 씬 상태를 비웠다.')
        elif msg.name == 'POUCH_PICKED':
            self._holding = True
            if self._belt.occupied and msg.order_id == self._belt.order_id:
                self._belt = BeltState()
        elif msg.name == 'POUCH_LOADED':
            self._holding = False
        elif msg.name == 'POUCH_PLACED':
            self._holding = False
            cabinet = common.cabinet_id(self._pool, msg.order_id)
            if cabinet:
                self._cabinet[msg.order_id] = cabinet
                self._emit_cabinet(msg.order_id, cabinet)

    # M0609 관절·그리퍼를 되돌려 준다 ------------------------------------

    def _setup_m0609(self):
        """emulate_m0609=false 면 상태만 두고 토픽은 열지 않는다(브릿지가 M0609 를 낼 때)."""
        self.declare_parameter('emulate_m0609', True)
        self.declare_parameter('m0609_joint_names', list(M0609_JOINT_NAMES))
        self.declare_parameter('m0609_settle_s', 0.2)
        self.declare_parameter('m0609_reset_homes', True)
        self._m0609_names = [str(name) for name in self.get_parameter('m0609_joint_names').value]
        self._m0609_index = {name: index for index, name in enumerate(self._m0609_names)}
        self._m0609_settle_s = float(self.get_parameter('m0609_settle_s').value)
        self._m0609_reset_homes = bool(self.get_parameter('m0609_reset_homes').value)
        self._m0609_joints = [0.0] * len(self._m0609_names)
        self._m0609_closed_at = None    # 닫기 명령을 받은 _seconds(). 열려 있으면 None
        if not self.get_parameter('emulate_m0609').value:
            return

        self._m0609_joint_pub = self.create_publisher(JointState, '/m0609/joint_states', sensor_qos())
        self._m0609_holding_pub = self.create_publisher(Bool, '/m0609/gripper/holding', heartbeat_qos())
        self.create_subscription(JointState, '/m0609/arm/joint_command',
                                 self._on_m0609_joint_command, reliable_qos())
        self.create_subscription(Bool, '/m0609/gripper/command',
                                 self._on_m0609_gripper_command, reliable_qos())
        self.create_timer(1.0 / M0609_JOINT_RATE_HZ, self._publish_m0609_joints)
        self.create_timer(0.1, self._publish_m0609_holding)     # H = 10 Hz
        self.get_logger().info(f'M0609 흉내: joint_states·gripper/holding. 관절 {self._m0609_names}')

    def _on_m0609_joint_command(self, msg):
        """자기 관절 이름만 받는다. 다른 이름이 섞이면 통째로 버린다(계약 2.1절, isaac 과 같다)."""
        unknown = [name for name in msg.name if name not in self._m0609_index]
        if unknown or len(msg.position) != len(msg.name):
            self.get_logger().warning(
                f'/m0609/arm/joint_command 를 버린다. 모르는 이름 {unknown}, '
                f'name {len(msg.name)}개 position {len(msg.position)}개',
                throttle_duration_sec=5.0)
            return
        joints = list(self._m0609_joints)
        for name, position in zip(msg.name, msg.position, strict=True):
            joints[self._m0609_index[name]] = float(position)
        self._m0609_joints = joints

    def _on_m0609_gripper_command(self, msg):
        if not msg.data:
            self._m0609_closed_at = None
        elif self._m0609_closed_at is None:
            self._m0609_closed_at = self._seconds()

    def _publish_m0609_joints(self):
        msg = JointState()
        msg.header.stamp = self._stamp()
        msg.name = list(self._m0609_names)
        msg.position = list(self._m0609_joints)
        self._m0609_joint_pub.publish(msg)

    def _publish_m0609_holding(self):
        """settle 은 벨트 이동처럼 wall 로 잰다. 스텁 내부 타이밍이다."""
        closed_at = self._m0609_closed_at
        holding = closed_at is not None and self._seconds() - closed_at >= self._m0609_settle_s
        self._m0609_holding_pub.publish(Bool(data=holding))


def main(args=None):
    """콘솔 진입점."""
    rclpy.init(args=args)
    node = StubSim()
    # 액션 실행 콜백이 스레드를 오래 잡는다. 코어 수가 적은 기계에서도 굶지 않게 고정한다.
    executor = MultiThreadedExecutor(num_threads=8)
    executor.add_node(node)
    spin_until_interrupted(node, executor)


if __name__ == '__main__':
    main()
