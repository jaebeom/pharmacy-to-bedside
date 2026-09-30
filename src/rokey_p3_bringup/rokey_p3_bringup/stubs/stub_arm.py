"""스텁 팔. arm 과 m0609/arm 을 계약과 같은 이름으로 대신한다(계약 8절).

내는 것: /amr_1/arm/at_home, PickPouch·ScanTag·Refill 서버, Refill 을 맡을 때 /m0609/arm/at_home,
이벤트 PICK_ATTEMPT, POUCH_PICKED, POUCH_LOADED, POUCH_PLACED, ARM_HOME, REFILL_DONE.

계약 5절의 팔 인터락을 여기서도 본다. base/stopped 가 true 이고 1.0 s 이내여야 하고,
source=BELT 면 belt.at_end 이고 belt.order_id 가 goal 과 같아야 한다.

인터락 위반은 **goal 을 받은 뒤 바로 abort** 하고 outcome 을 rejected_interlock 으로 낸다.
계약 5절은 "REJECT" 라고 쓰지만 ROS 2 는 거부한 goal 에 result 를 못 싣고, 계약 2.3절이
rejected_interlock 을 outcome 목록에 두고 있다. 실물 arm 도 같은 선택이다(PR #37).
스텁이 실물과 다르게 움직이면 스텁을 실물로 바꿀 때 거동이 바뀐다.
ScanTag 는 result 에 outcome 이 없어서 status=UNREADABLE 로 닫는다. 이것도 실물과 같다.
goal 거부는 형식 오류(order_id 없음, 모르는 source), 활성 goal, 리셋 barrier 뿐이다(아래).

UR5 쪽 홈 복귀는 액션 결과를 돌려준 **뒤**에 끝난다. 그래서 계약 2.6절 한 바퀴처럼
LOAD_DONE 다음에 ARM_HOME 이 오고, ORDER_DONE 다음에 ARM_HOME 이 온다.
스캔은 홈을 벗어나지만 바로 전달 픽으로 이어져서 그 사이에 ARM_HOME 이 없다.

Refill 은 m0609_arm 과 같은 형식을 쓴다. REFILL_DONE detail 은 "<item_id> slot <a|b>" 이고 lot 이 있을 때만
" lot <lot_id>" 를 붙인다. 결과 lot_id 는 지어내지 않는다.
goal 에 lot 이 있으면 그대로, 없으면(지금 Refill goal) 빈 값이다(실물 #99 와 같다. 로트 데이터는 orchestrator 선반 값,
계약 2.1절 끝). item_id 가 비었거나 slot 이 0·1 이 아니면 goal 을 거부한다.
형식 함수는 rokey_p3_manipulation.refill_sequence 의 것을 그대로 쓴다(스텁과 실물이 갈라지지 않게).

goal 수락도 실물과 같은 순서로 본다. 형식 오류, 이미 활성 goal 이 있음(UR5 는 PickPouch·ScanTag 가 하나를
나눠 쓰고 M0609 Refill 은 따로), 리셋 barrier 중(RESET_BEGIN 뒤 같은 epoch 의 RESET_DONE 전, 계약 6절 0)이면
거부한다. barrier 판정은 실물과 같은 rokey_p3_manipulation.reset_fence.ResetFence 로 한다.
스텁은 관절·그리퍼 명령을 내지 않으므로 barrier 가 막을 명령은 없다. 실행 중인 goal 을 barrier 로 멈추지도 않는다.

/m0609/arm/at_home 은 실물 m0609_arm 처럼 5 Hz(H)로 낸다. serve_refill 이 false 면(실물이 /m0609/refill 을 맡을 때)
publisher 를 만들지 않는다. 같은 이름을 둘이 내지 않게 한다. 결과·홈 순서는 실물(#99)과 같다(UR5 쪽과 다르다).
- 성공: motion_s 뒤 REFILL_DONE, home_s 동안 홈으로 간 **뒤** 결과를 낸다. 결과를 받을 때 at_home 은 true 다.
- 취소: motion_s 가 끝난 시점에 취소 요청이 있으면 결과(canceled)를 먼저 내고 home_s 뒤 true 가 된다.
  실물은 이동 중에도 취소를 보지만 스텁은 motion_s 끝에서 한 번만 본다.
- 스텁 Refill 에는 실패 경로가 없다.
리셋은 실물과 같게 한다.
- RESET_BEGIN 이 오면(goal 시작 뒤 barrier 경계를 지났거나 barrier 중이면) 결과 전 홈 복귀를 하지 않고 결과를 낸다.
  결과 뒤 예약한 복귀도 barrier 중에는 홈에 닿지 않는다(false 로 남는다).
- 같은 epoch 의 RESET_DONE 을 처음 받으면, 홈 밖이고 실행 중인 Refill 이 없으면
  다시 home_s 복귀한다.
실물은 /sim/reset 이 관절을 홈으로 옮기면 RESET_DONE 전에도 true 가 될 수 있다.
스텁은 관절을 모르므로 RESET_DONE 을 기다린다.
"""

import threading
import time

import rclpy
from rclpy.action import ActionServer, CancelResponse, GoalResponse
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from std_msgs.msg import Bool

from rokey_p3_bringup.shutdown import spin_until_interrupted
from rokey_p3_bringup.stubs import common
from rokey_p3_interfaces.action import PickPouch, Refill, ScanTag
from rokey_p3_interfaces.msg import BeltState, Event, PouchDetectionArray, TagRead
from rokey_p3_manipulation import refill_sequence
from rokey_p3_manipulation.reset_fence import ResetFence
from rokey_p3_orchestrator.ros_qos import heartbeat_qos, reliable_qos

FRESH_S = 1.0
OUTCOME_OK = 'ok'
OUTCOME_NOT_DETECTED = 'not_detected'
OUTCOME_REJECTED = 'rejected_interlock'


class StubArm(Node):
    """stub_arm 노드."""

    def __init__(self, **kwargs):
        super().__init__('stub_arm', **kwargs)
        self.declare_parameter('order_pool_file', '')
        self.declare_parameter('motion_s', 0.3)
        self.declare_parameter('home_s', 0.3)
        self.declare_parameter('detection_wait_s', 5.0)
        self.declare_parameter('tag_wait_s', 5.0)
        # false 면 /m0609/refill 서버를 열지 않는다. 실물 m0609_arm 이 그 이름을 맡을 때.
        self.declare_parameter('serve_refill', True)
        self._pool = common.load_pool_index(
            self.get_parameter('order_pool_file').value or common.default_pool_path())
        self._motion_s = float(self.get_parameter('motion_s').value)
        self._home_s = float(self.get_parameter('home_s').value)
        self._detection_wait_s = float(self.get_parameter('detection_wait_s').value)
        self._tag_wait_s = float(self.get_parameter('tag_wait_s').value)

        self._at_home = True
        self._serve_refill = bool(self.get_parameter('serve_refill').value)
        self._m0609_at_home = True
        self._lock = threading.Lock()
        self._fence = ResetFence()
        self._arm_active = False        # UR5: PickPouch·ScanTag 가 나눠 쓴다
        self._refill_active = False     # M0609: Refill
        self._stopped = None
        self._stopped_wall = 0.0
        self._belt = None
        self._belt_wall = 0.0
        self._detected = set()
        self._tag = None
        self._tag_wall = 0.0
        group = ReentrantCallbackGroup()

        self._home_pub = self.create_publisher(
            Bool, f'/{common.NAMESPACE}/arm/at_home', heartbeat_qos())
        self.create_subscription(Bool, f'/{common.NAMESPACE}/base/stopped',
                                 self._on_stopped, heartbeat_qos())
        self.create_subscription(BeltState, '/pharmacy/belt', self._on_belt, heartbeat_qos())
        self.create_subscription(PouchDetectionArray, f'/{common.NAMESPACE}/hand_camera/pouches',
                                 self._on_pouches, reliable_qos(5))
        self.create_subscription(TagRead, f'/{common.NAMESPACE}/hand_camera/tag_reads',
                                 self._on_tag, reliable_qos())
        self._events = common.EventIo(self, common.NAMESPACE, self._on_event)

        ActionServer(self, PickPouch, f'/{common.NAMESPACE}/pick_pouch',
                     goal_callback=self._on_pick_goal,
                     cancel_callback=lambda _: CancelResponse.ACCEPT,
                     execute_callback=self._execute_pick, callback_group=group)
        # ScanTag 인터락은 실행에서 보고 UNREADABLE 로 닫는다. 수락에서는 zone_id·활성 goal·barrier 만 본다.
        ActionServer(self, ScanTag, f'/{common.NAMESPACE}/scan_tag',
                     goal_callback=self._on_scan_goal,
                     cancel_callback=lambda _: CancelResponse.ACCEPT,
                     execute_callback=self._execute_scan, callback_group=group)
        self._m0609_home_pub = None
        if self._serve_refill:
            ActionServer(self, Refill, '/m0609/refill',
                         goal_callback=self._on_refill_goal,
                         cancel_callback=lambda _: CancelResponse.ACCEPT,
                         execute_callback=self._execute_refill, callback_group=group)
            self._m0609_home_pub = self.create_publisher(Bool, '/m0609/arm/at_home', heartbeat_qos())
        self.create_timer(0.2, self._publish_home)      # H = 5 Hz
        if self._serve_refill:
            self.get_logger().info('stub_arm up. PickPouch·ScanTag·Refill 서버와 arm/at_home·m0609/arm/at_home.')
        else:
            self.get_logger().info('stub_arm up. PickPouch·ScanTag 서버와 arm/at_home.')

    # 구독 ---------------------------------------------------------------

    def _on_event(self, msg):
        """리셋 barrier 경계. 중복·이전 epoch 신호는 ResetFence 가 무시한다."""
        if msg.name == Event.RESET_BEGIN:
            with self._lock:
                closed = self._fence.begin(msg.epoch)
            if closed:
                self.get_logger().info(f'RESET_BEGIN epoch={msg.epoch}. RESET_DONE 까지 새 goal 을 거부한다.')
        elif msg.name == Event.RESET_DONE:
            with self._lock:
                first = self._fence.done(msg.epoch)
                rehome = first and self._serve_refill and not self._m0609_at_home and not self._refill_active
            if rehome:
                self._schedule_m0609_home()

    def _on_stopped(self, msg):
        self._stopped = bool(msg.data)
        self._stopped_wall = time.monotonic()

    def _on_belt(self, msg):
        self._belt = msg
        self._belt_wall = time.monotonic()

    def _on_pouches(self, msg):
        self._detected = {d.order_id for d in msg.detections if d.order_id}

    def _on_tag(self, msg):
        self._tag = msg
        self._tag_wall = time.monotonic()

    def _publish_home(self):
        self._home_pub.publish(Bool(data=self._at_home))
        if self._m0609_home_pub is not None:
            self._m0609_home_pub.publish(Bool(data=self._m0609_at_home))

    # 인터락 ---------------------------------------------------------------

    def _base_is_stopped(self):
        return bool(self._stopped) and (time.monotonic() - self._stopped_wall) <= FRESH_S

    def _belt_ready(self, order_id):
        fresh = (time.monotonic() - self._belt_wall) <= FRESH_S
        return bool(self._belt) and fresh and self._belt.at_end and self._belt.order_id == order_id

    def _on_pick_goal(self, goal):
        """형식만 본다. 인터락은 실행에서 보고 outcome 으로 돌려준다."""
        if not goal.order_id:
            self.get_logger().warning('PickPouch goal 에 order_id 가 없다. 거부한다.')
            return GoalResponse.REJECT
        if goal.source not in (PickPouch.Goal.SOURCE_BELT, PickPouch.Goal.SOURCE_DECK):
            self.get_logger().warning(f'PickPouch source={goal.source} 를 모른다. 거부한다.')
            return GoalResponse.REJECT
        return self._accept_unless_busy('_arm_active')

    def _on_scan_goal(self, goal):
        """실물 arm 과 같다. zone_id 가 없거나, 활성 goal 이 있거나, 리셋 barrier 중이면 거부한다."""
        if not goal.zone_id:
            self.get_logger().warning('ScanTag goal 에 zone_id 가 없다. 거부한다.')
            return GoalResponse.REJECT
        return self._accept_unless_busy('_arm_active')

    def _accept_unless_busy(self, flag):
        """형식 검사 뒤의 공통 순서(실물과 같다): 활성 goal 이 있으면, 리셋 barrier 중이면 거부."""
        with self._lock:
            busy = getattr(self, flag)
            fenced = self._fence.fenced
        if busy:
            self.get_logger().warning('이미 활성 goal 이 있다. 거부한다.')
            return GoalResponse.REJECT
        if fenced:
            self.get_logger().warning('리셋 barrier 중이다. 거부한다.')
            return GoalResponse.REJECT
        return GoalResponse.ACCEPT

    def _run_active(self, flag, run, goal_handle):
        """실행하는 동안 활성 goal 로 표시한다. 결과를 돌려주기 전에 푼다(실물 finally 와 같다)."""
        with self._lock:
            setattr(self, flag, True)
        try:
            return run(goal_handle)
        finally:
            with self._lock:
                setattr(self, flag, False)

    def _pick_interlock(self, goal):
        """계약 5절 팔 동작 guard. 통과하면 빈 문자열, 아니면 사람이 읽을 이유."""
        if not self._base_is_stopped():
            return f'base/stopped={self._stopped} 가 true 가 아니거나 오래됐다'
        if goal.source == PickPouch.Goal.SOURCE_BELT and not self._belt_ready(goal.order_id):
            return f'벨트 끝에 {goal.order_id} 의 봉투가 없다'
        return ''

    # 실행 ---------------------------------------------------------------

    def _phase(self, goal_handle, action, name):
        feedback = action.Feedback()
        feedback.phase = name
        goal_handle.publish_feedback(feedback)

    def _schedule_home(self):
        """결과를 돌려준 뒤에 홈 복귀를 끝낸다. 콜백 안에서 기다리면 ARM_HOME 이
        LOAD_DONE·ORDER_DONE 을 앞질러 계약 2.6절의 순서가 어긋난다."""
        timer = None

        def arrive_home():
            self.destroy_timer(timer)
            self._at_home = True
            self._events.emit('ARM_HOME')

        timer = self.create_timer(self._home_s, arrive_home)

    def _execute_pick(self, goal_handle):
        return self._run_active('_arm_active', self._run_pick, goal_handle)

    def _run_pick(self, goal_handle):
        goal = goal_handle.request
        reason = self._pick_interlock(goal)
        if reason:
            self.get_logger().warning(f'픽 인터락: {reason}')
            goal_handle.abort()
            return PickPouch.Result(success=False, outcome=OUTCOME_REJECTED)

        self._at_home = False
        from_belt = goal.source == PickPouch.Goal.SOURCE_BELT
        if not from_belt and not self._wait_for_detection(goal.order_id):
            self._events.emit('PICK_ATTEMPT', order_id=goal.order_id)
            goal_handle.abort()
            self._schedule_home()
            return PickPouch.Result(success=False, outcome=OUTCOME_NOT_DETECTED)

        self._phase(goal_handle, PickPouch, 'approach')
        self._events.emit('PICK_ATTEMPT', order_id=goal.order_id)
        time.sleep(self._motion_s)
        self._events.emit('POUCH_PICKED', order_id=goal.order_id)
        self._phase(goal_handle, PickPouch, 'place')
        time.sleep(self._motion_s)
        self._events.emit('POUCH_LOADED' if from_belt else 'POUCH_PLACED', order_id=goal.order_id)
        goal_handle.succeed()
        self._schedule_home()
        return PickPouch.Result(success=True, outcome=OUTCOME_OK)

    def _wait_for_detection(self, order_id):
        deadline = time.monotonic() + self._detection_wait_s
        while time.monotonic() < deadline:
            if order_id in self._detected:
                return True
            time.sleep(0.05)
        return False

    def _execute_scan(self, goal_handle):
        return self._run_active('_arm_active', self._run_scan, goal_handle)

    def _run_scan(self, goal_handle):
        zone_id = goal_handle.request.zone_id
        if not self._base_is_stopped():
            # ScanTag result 에는 outcome 이 없다. 실물과 같이 UNREADABLE 로 닫는다.
            self.get_logger().warning('스캔 인터락: base/stopped 가 true 가 아니거나 오래됐다.')
            goal_handle.abort()
            return ScanTag.Result(tag_id='', status=TagRead.STATUS_UNREADABLE)

        self._at_home = False
        self._phase(goal_handle, ScanTag, 'aim')
        expected = common.zone_tag_id(self._pool, zone_id)
        deadline = time.monotonic() + self._tag_wait_s
        while time.monotonic() < deadline:
            fresh = (time.monotonic() - self._tag_wall) <= FRESH_S
            if self._tag is not None and fresh and self._tag.tag_id == expected:
                goal_handle.succeed()
                return ScanTag.Result(tag_id=self._tag.tag_id, status=TagRead.STATUS_OK)
            time.sleep(0.05)
        # 못 읽었으면 다음 동작(놓기)이 없다 — 여기서 홈 복귀를 예약한다. 안 하면 arm/at_home 이 false 로
        # 남아 orchestrator 가 복귀를 영영 기다리고, 리셋 뒤 다음 트립까지 막힌다(#576, 9/23 스텁 한 바퀴).
        self._schedule_home()
        goal_handle.succeed()
        return ScanTag.Result(tag_id='', status=TagRead.STATUS_UNREADABLE)

    def _on_refill_goal(self, goal):
        """m0609_arm 과 같은 형식 검사. item_id 가 비었거나 slot 이 0·1 이 아니면 거부한다."""
        if not goal.item_id:
            self.get_logger().warning('Refill goal 에 item_id 가 없다. 거부한다.')
            return GoalResponse.REJECT
        try:
            refill_sequence.slot_letter(goal.slot)
        except refill_sequence.RefillPlanError as error:
            self.get_logger().warning(f'Refill goal 거부: {error}')
            return GoalResponse.REJECT
        return self._accept_unless_busy('_refill_active')

    def _schedule_m0609_home(self):
        """home_s 뒤 M0609 가 홈에 닿는다. barrier 경계를 지났거나, barrier 중이거나, 새 Refill 이 돌면 닿지 않는다
        (실물은 barrier 중 복귀 명령을 내지 않고 RESET_DONE 에서 다시 시작한다)."""
        with self._lock:
            generation = self._fence.generation
        timer = None

        def arrive_home():
            self.destroy_timer(timer)
            with self._lock:
                if self._fence.generation == generation and not self._fence.fenced and not self._refill_active:
                    self._m0609_at_home = True

        timer = self.create_timer(self._home_s, arrive_home)

    def _execute_refill(self, goal_handle):
        return self._run_active('_refill_active', self._run_refill, goal_handle)

    def _run_refill(self, goal_handle):
        goal = goal_handle.request
        with self._lock:
            generation = self._fence.generation
        self._m0609_at_home = False
        time.sleep(self._motion_s)
        # lot 은 지어내지 않는다. goal 에 lot 이 있으면 그대로, 없으면 빈 값이다(실물 m0609_arm 과 같다).
        lot_id = str(getattr(goal, 'lot_id', '') or '')
        if goal_handle.is_cancel_requested:
            # 실물 #99: 취소는 결과를 먼저 내고 그 뒤 홈으로 간다.
            goal_handle.canceled()
            self._schedule_m0609_home()
            return Refill.Result(success=False, lot_id=lot_id)
        letter = refill_sequence.slot_letter(goal.slot)
        detail = f'{goal.item_id} slot {letter}' + (f' lot {lot_id}' if lot_id else '')
        self._events.emit('REFILL_DONE', detail=detail, robot_id='m0609')
        self._return_m0609_home(generation)
        goal_handle.succeed()
        return Refill.Result(success=True, lot_id=lot_id)

    def _return_m0609_home(self, generation):
        """실물 #99: 성공 결과를 내기 전에 홈으로 간다(home_s). barrier 경계를 지났거나 barrier 중이면 가지 않는다
        (RESET_DONE 뒤 다시 복귀한다). 도착했으면 True."""
        deadline = time.monotonic() + self._home_s
        while True:
            with self._lock:
                stopped = self._fence.generation != generation or self._fence.fenced
            if stopped or not rclpy.ok(context=self.context):
                return False
            if time.monotonic() >= deadline:
                break
            time.sleep(0.02)
        with self._lock:
            self._m0609_at_home = True
        return True


def main(args=None):
    """콘솔 진입점."""
    rclpy.init(args=args)
    node = StubArm()
    # 액션 실행 콜백이 스레드를 오래 잡는다. 코어 수가 적은 기계에서도 굶지 않게 고정한다.
    executor = MultiThreadedExecutor(num_threads=8)
    executor.add_node(node)
    spin_until_interrupted(node, executor)


if __name__ == '__main__':
    main()
