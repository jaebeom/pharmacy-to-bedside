"""L2. M0609 닫힌 루프. stub_sim 의 M0609 흉내와 실물 m0609_arm(open_loop=false).

stub_sim 이 /m0609/arm/joint_command 를 /m0609/joint_states 로 되돌리고,
/m0609/gripper/command 뒤에 /m0609/gripper/holding 을 낸다. 그러면 m0609_arm 이
Refill 을 success=true 로 끝내고 /events 에 REFILL_DONE 을 한 번 낸다.
대조: emulate_m0609=false 면 joint_states 가 없어서 같은 goal 이 실패한다.
리셋: goal 도중 cancel 한 뒤 복귀가 끊긴 채(홈 밖, 명령 없음) 리셋이 오는 경우를 만든다.
m0609_reset_homes=false 면 스텁이 관절을 두므로 m0609_arm 이 RESET_DONE 을 보고 스스로 홈으로 가야
at_home 이 true 가 된다. 스텁은 스스로 움직이지 않으니 홈에 닿았다면 노드가 옮긴 것이다.
울타리(계약 6절 0): 실물 orchestrator 의 /orchestrator/reset 이 RESET_BEGIN(e2) → /sim/reset(e2) → RESET_DONE(e2) 를
낸다. stub_sim 의 reset_delay_s 로 barrier 를 잠시 열어 둔다.
- 관절: goal 도중 cancel 해 m0609_arm 의 홈 복귀 명령이 나가는 중에 리셋. 울타리 구간 joint_command·gripper/command 0건,
  RESET_DONE 뒤 스스로 홈.
- 그리퍼: grasp(gripper/command true) 직후에 리셋. 울타리가 없으면 이어서 삽입의 gripper/command false 가 나가는
  구간에서 0건이고, goal 은 barrier 로 끝난다.
울타리 구간은 m0609_arm.fenced() 가 true 로 보인 순간부터 false 로 보인 순간까지다. joint_command 는 header.stamp
(sim time)로 울타리가 닫힌 뒤 보낸 것만, 끝은 받은 시각으로 자른다(sim 시계 60 Hz).

launch 대신 한 프로세스에서 노드를 띄운다. m0609_arm 은 생성자로 파라미터를 못 받아서
--params-file 로 준다. waypoint 가 0 이 아니어야 되돌림을 실제로 쓴다(기본값 0 은 홈과 같다).
"""

import contextlib
import threading
import time

import rclpy
from action_msgs.msg import GoalStatus
from rclpy.action import ActionClient
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from rclpy.parameter import Parameter
from sensor_msgs.msg import JointState
from std_msgs.msg import Bool

from l2_teardown import assert_no_leftovers, teardown_nodes
from rokey_p3_bringup.stubs.stub_sim import StubSim
from rokey_p3_interfaces.action import Refill
from rokey_p3_interfaces.msg import Event
from rokey_p3_interfaces.srv import Reset
from rokey_p3_manipulation.m0609_arm_node import M0609ArmNode
from rokey_p3_orchestrator.orchestrator_node import OrchestratorNode
from rokey_p3_orchestrator.ros_qos import latched_qos, reliable_qos, sensor_qos

POOL = """version: 1
orders:
  - {order_id: ord-0001, patient_id: "1001", item_id: drug-amox, bed: bed_a1}
"""

# 가장 큰 관절값이 0.65 rad 다. 되돌림이 없으면 도착 판정(0.05 rad)을 못 넘는다.
ARM_PARAMS = """m0609_arm:
  ros__parameters:
    use_sim_time: true
    shelf_approach_joints: [0.4, -0.3, 0.5, 0.0, 0.2, 0.0]
    shelf_grasp_joints: [0.4, -0.45, 0.65, 0.0, 0.2, 0.0]
    slot_a_approach_joints: [-0.4, -0.3, 0.5, 0.0, 0.2, 0.0]
    slot_a_insert_joints: [-0.4, -0.45, 0.65, 0.0, 0.2, 0.0]
"""
PEAK_RAD = 0.65
HOME_TOLERANCE_RAD = 0.05       # m0609_arm 의 home_tolerance_rad 기본값

REFILL_TIMEOUT_S = 60.0
# 울타리를 닫아 두는 시간(wall, stub_sim reset_delay_s). 울타리가 없으면 cancel 뒤 홈 복귀 명령(20 Hz)이 이 동안 나간다.
FENCE_HOLD_S = 1.0
# grasp 직후 리셋에서 barrier 를 열어 두는 시간. 울타리가 없으면 grasp 에서 약 2.7 s 뒤 삽입의 gripper false 가 나간다.
GRIPPER_HOLD_S = 4.0


class Probe(Node):
    """Refill 을 보내고 /events 와 /m0609/joint_states 를 모은다."""

    def __init__(self):
        super().__init__('m0609_probe')
        self.events = []
        self.peak = 0.0
        self.latest = None
        self.commands = []      # (받은 wall, header.stamp sim 초 또는 None, 토픽, gripper 값 또는 None)
        self.client = ActionClient(self, Refill, '/m0609/refill')
        self.reset_client = self.create_client(Reset, '/sim/reset')
        self.orchestrator_reset = self.create_client(Reset, '/orchestrator/reset')
        self.event_pub = self.create_publisher(Event, '/events', latched_qos(500))
        self.create_subscription(Event, '/events', self.events.append, latched_qos(500))
        self.create_subscription(JointState, '/m0609/joint_states', self._on_joints, sensor_qos())
        self.create_subscription(JointState, '/m0609/arm/joint_command', self._on_joint_command, reliable_qos())
        self.create_subscription(Bool, '/m0609/gripper/command', self._on_gripper_command, reliable_qos())

    def _on_joints(self, msg):
        self.latest = tuple(msg.position)
        self.peak = max([self.peak] + [abs(value) for value in msg.position])

    def _on_joint_command(self, msg):
        stamp = msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9
        self.commands.append((time.monotonic(), stamp, 'joint_command', None))

    def _on_gripper_command(self, msg):
        self.commands.append((time.monotonic(), None, 'gripper/command', bool(msg.data)))

    def farthest(self):
        """지금 관절값 중 홈(0)에서 가장 먼 값. 아직 못 받았으면 0."""
        return max((abs(value) for value in self.latest), default=0.0) if self.latest else 0.0

    def reset_sim(self, epoch):
        """계약 6절 2 의 orchestrator 몫: /sim/reset(epoch)."""
        assert self.reset_client.wait_for_service(timeout_sec=5.0), '/sim/reset 서버가 없다'
        future = self.reset_client.call_async(Reset.Request(epoch=epoch))
        wait_until(future.done, 5.0, '/sim/reset 응답이 없다')
        assert future.result().ok

    def reset_through_orchestrator(self, epoch):
        """/orchestrator/reset. 응답은 곧바로 ok 다(barrier 완료가 아니다)."""
        assert self.orchestrator_reset.wait_for_service(timeout_sec=5.0), '/orchestrator/reset 서버가 없다'
        future = self.orchestrator_reset.call_async(Reset.Request(epoch=epoch))
        wait_until(future.done, 5.0, '/orchestrator/reset 응답이 없다')
        assert future.result().ok

    def events_named(self, name, epoch):
        return [event for event in self.events if event.name == name and event.epoch == epoch]

    def publish_reset_done(self, epoch):
        """계약 6절 3 의 orchestrator 몫: RESET_DONE(새 epoch)."""
        self.publish_event(Event.RESET_DONE, epoch)

    def publish_event(self, name, epoch):
        """orchestrator 이름으로 barrier 이벤트 하나. RESET_BEGIN 은 계약 6절 0, RESET_DONE 은 3."""
        event = Event()
        event.header.stamp = self.get_clock().now().to_msg()
        event.name = name
        event.robot_id = 'orchestrator'
        event.epoch = epoch
        self.event_pub.publish(event)

    def refill_done(self):
        return [event for event in self.events if event.name == Event.REFILL_DONE]


def wait_until(condition, timeout_s, message):
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if condition():
            return
        time.sleep(0.05)
    raise AssertionError(f'{timeout_s} s: {message}')


def send_refill(probe):
    """drug-amox 를 슬롯 a 에 보낸다. 수락된 goal handle."""
    assert probe.client.wait_for_server(timeout_sec=10.0), '/m0609/refill 서버가 없다'
    sent = probe.client.send_goal_async(Refill.Goal(item_id='drug-amox', slot=0))
    wait_until(sent.done, 10.0, 'goal 응답이 없다')
    handle = sent.result()
    assert handle.accepted
    return handle


def refill(probe):
    """보내고 결과 응답(status, result)까지 기다린다."""
    result = send_refill(probe).get_result_async()
    wait_until(result.done, REFILL_TIMEOUT_S, 'Refill 결과가 오지 않았다')
    return result.result()


@contextlib.contextmanager
def m0609_loop(tmp_path, emulate, reset_homes=True, orchestrator=False, sim_params=None):
    """stub_sim, m0609_arm, probe(와 원하면 실물 orchestrator) 를 한 executor 로 돌린다."""
    pool_path = tmp_path / 'order_pool.yaml'
    pool_path.write_text(POOL, encoding='utf-8')
    params_path = tmp_path / 'm0609_arm.yaml'
    params_path.write_text(ARM_PARAMS, encoding='utf-8')

    assert_no_leftovers()
    rclpy.init(args=['test_m0609_loop', '--ros-args', '--params-file', str(params_path)])
    executor = MultiThreadedExecutor(num_threads=12)
    nodes = []
    thread = None
    try:
        nodes.append(StubSim(parameter_overrides=[
            Parameter('order_pool_file', value=str(pool_path)),
            Parameter('emulate_m0609', value=emulate),
            Parameter('m0609_reset_homes', value=reset_homes)]
            + [Parameter(name, value=value) for name, value in (sim_params or {}).items()]))
        if orchestrator:
            nodes.append(OrchestratorNode(parameter_overrides=[Parameter('order_pool_file', value=str(pool_path))]))
        arm = M0609ArmNode()
        nodes.append(arm)
        probe = Probe()
        nodes.append(probe)
        for node in nodes:
            executor.add_node(node)
        thread = threading.Thread(target=executor.spin, daemon=True)
        thread.start()
        yield arm, probe
    finally:
        for node in nodes:
            if isinstance(node, M0609ArmNode):
                node.stop_homing()
        teardown_nodes(executor, thread, nodes)


def test_refill_succeeds_on_the_loop_closed_by_stub_sim(tmp_path):
    with m0609_loop(tmp_path, emulate=True) as (arm, probe):
        wait_until(lambda: arm.joint_positions() is not None, 5.0,
                   'm0609_arm 이 /m0609/joint_states 를 받지 못했다')
        response = refill(probe)
        wait_until(lambda: arm.at_home() is True, 10.0, '결과 뒤 홈으로 돌아오지 않았다')
        time.sleep(0.5)                 # 늦게 도착하는 이벤트
        done = probe.refill_done()
        peak = probe.peak

    assert response.status == GoalStatus.STATUS_SUCCEEDED
    assert response.result.success
    assert response.result.lot_id == ''
    assert len(done) == 1, f'REFILL_DONE 이 {len(done)}건이다'
    assert done[0].robot_id == 'm0609'
    assert peak >= PEAK_RAD - 0.01, f'joint_states 가 waypoint 까지 가지 않았다. 최대 {peak} rad'


def test_without_emulation_the_same_refill_fails(tmp_path):
    with m0609_loop(tmp_path, emulate=False) as (arm, probe):
        time.sleep(2.0)
        assert arm.joint_positions() is None, 'emulate_m0609=false 인데 joint_states 가 왔다'
        response = refill(probe)
        time.sleep(0.5)
        done = probe.refill_done()

    assert response.status == GoalStatus.STATUS_ABORTED
    assert not response.result.success
    assert not done


def test_arm_homes_itself_after_reset_when_the_sim_does_not(tmp_path):
    with m0609_loop(tmp_path, emulate=True, reset_homes=False) as (arm, probe):
        wait_until(lambda: arm.joint_positions() is not None, 5.0,
                   'm0609_arm 이 /m0609/joint_states 를 받지 못했다')
        handle = send_refill(probe)
        wait_until(lambda: probe.farthest() >= 0.45, 10.0, 'goal 이 홈을 떠나지 않았다')

        # 계약 6절 1: cancel 하고 완료를 기다린다.
        cancel_done = handle.cancel_goal_async()
        wait_until(cancel_done.done, 5.0, 'cancel 응답이 없다')
        result = handle.get_result_async()
        wait_until(result.done, 10.0, 'cancel 뒤 결과가 오지 않았다')
        # m0609_arm 은 cancel 뒤 바로 복귀를 시작한다. 그 복귀가 리셋 전에 끊긴 경우를 만든다
        # (m0609_arm.on_reset docstring: 복귀가 리셋 중에 끊겼을 수 있다). 명령이 멎었는지 본다.
        arm.stop_homing()
        time.sleep(0.3)
        stopped_at = probe.farthest()
        time.sleep(0.3)
        assert probe.farthest() == stopped_at, '복귀를 멈췄는데 관절이 계속 움직인다'
        assert arm.at_home() is False

        # 계약 6절 2·3: /sim/reset 뒤 RESET_DONE. 스텁이 관절을 두었는지는 그 사이에 본다.
        probe.reset_sim(epoch=2)
        time.sleep(0.2)                 # joint_states 몇 주기
        after_reset = probe.farthest()
        probe.publish_reset_done(epoch=2)
        wait_until(lambda: arm.epoch() == 2, 5.0, 'm0609_arm 이 RESET_DONE 을 받지 못했다')
        wait_until(lambda: arm.at_home() is True, 15.0, '리셋 뒤 스스로 홈으로 가지 않았다')
        time.sleep(0.2)
        final = probe.farthest()
        done = probe.refill_done()

    assert result.result().status == GoalStatus.STATUS_CANCELED
    assert stopped_at > HOME_TOLERANCE_RAD, f'복귀가 끊기기 전에 이미 홈이었다({stopped_at} rad)'
    assert after_reset == stopped_at, f'm0609_reset_homes=false 인데 리셋이 관절을 바꿨다({stopped_at} → {after_reset})'
    assert final <= HOME_TOLERANCE_RAD, f'at_home 인데 joint_states 가 홈이 아니다({final} rad)'
    assert not done


def wait_fence_open(arm, timeout_s):
    """울타리가 열린 순간(wall). 열린 직후 나가는 복귀 명령을 구간에 넣지 않으려고 2 ms 마다 본다."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if not arm.fenced():
            return time.monotonic()
        time.sleep(0.002)
    raise AssertionError(f'{timeout_s} s: 울타리가 열리지 않았다(RESET_DONE 이 안 왔다)')


def fenced_commands(commands, fenced_sim, fenced_wall, open_wall):
    """울타리 구간의 (joint_command, gripper/command). joint 는 stamp 로 시작을, 받은 시각으로 끝을 자른다."""
    joint = [c for c in commands if c[2] == 'joint_command' and c[1] > fenced_sim and c[0] <= open_wall]
    gripper = [c for c in commands if c[2] == 'gripper/command' and fenced_wall <= c[0] <= open_wall]
    return joint, gripper


def test_reset_begin_fences_m0609_commands_until_reset_done(tmp_path):
    with m0609_loop(tmp_path, emulate=True, reset_homes=False, orchestrator=True,
                    sim_params={'reset_delay_s': FENCE_HOLD_S}) as (arm, probe):
        wait_until(lambda: arm.joint_positions() is not None, 5.0,
                   'm0609_arm 이 /m0609/joint_states 를 받지 못했다')
        handle = send_refill(probe)
        wait_until(lambda: probe.farthest() >= 0.45, 10.0, 'goal 이 홈을 떠나지 않았다')

        cancel_wall = time.monotonic()
        cancel_done = handle.cancel_goal_async()
        wait_until(cancel_done.done, 5.0, 'cancel 응답이 없다')
        result = handle.get_result_async()
        wait_until(result.done, 10.0, 'cancel 뒤 결과가 오지 않았다')
        # cancel 뒤 m0609_arm 은 바로 홈 복귀를 시작한다. 그 명령이 나가는 중에 orchestrator 로 리셋한다.
        wait_until(lambda: any(c[2] == 'joint_command' and c[0] > cancel_wall for c in probe.commands), 2.0,
                   'cancel 뒤 홈 복귀 명령이 나가지 않았다(울타리가 막을 것이 없다)')

        probe.reset_through_orchestrator(2)
        wait_until(arm.fenced, 5.0, 'm0609_arm 이 orchestrator 의 RESET_BEGIN 을 받지 못했다')
        fenced_sim = arm.sim_now()
        fenced_wall = time.monotonic()
        open_wall = wait_fence_open(arm, FENCE_HOLD_S + 10.0)
        held_at = probe.farthest()

        wait_until(lambda: arm.at_home() is True, 15.0, 'RESET_DONE 뒤 스스로 홈으로 가지 않았다')
        time.sleep(0.2)
        final = probe.farthest()
        commands = list(probe.commands)
        begins = probe.events_named(Event.RESET_BEGIN, 2)
        dones = probe.events_named(Event.RESET_DONE, 2)

    joint, gripper = fenced_commands(commands, fenced_sim, fenced_wall, open_wall)
    after_open = [c for c in commands if c[2] == 'joint_command' and c[0] > open_wall]
    assert result.result().status == GoalStatus.STATUS_CANCELED
    assert len(begins) == 1 and begins[0].robot_id != 'orchestrator', 'orchestrator 가 낸 RESET_BEGIN(e2) 이 아니다'
    assert len(dones) == 1, f'RESET_DONE(e2) 가 {len(dones)}건이다'
    assert open_wall - fenced_wall >= FENCE_HOLD_S * 0.8, f'울타리가 {open_wall - fenced_wall:.2f} s 만 닫혔다'
    assert not joint, f'울타리 구간 joint_command {len(joint)}건'
    assert not gripper, f'울타리 구간 gripper/command {len(gripper)}건'
    assert held_at > HOME_TOLERANCE_RAD, f'울타리 중 관절이 이미 홈이다({held_at} rad). 막은 것을 못 본다'
    assert after_open, 'RESET_DONE 뒤 복귀 명령이 없다'
    assert final <= HOME_TOLERANCE_RAD, f'at_home 인데 joint_states 가 홈이 아니다({final} rad)'


def test_reset_begin_fences_m0609_gripper_right_after_grasp(tmp_path):
    with m0609_loop(tmp_path, emulate=True, reset_homes=False, orchestrator=True,
                    sim_params={'reset_delay_s': GRIPPER_HOLD_S}) as (arm, probe):
        wait_until(lambda: arm.joint_positions() is not None, 5.0,
                   'm0609_arm 이 /m0609/joint_states 를 받지 못했다')
        handle = send_refill(probe)
        wait_until(lambda: any(c[2] == 'gripper/command' and c[3] is True for c in probe.commands), 20.0,
                   'grasp 의 gripper/command true 가 나가지 않았다')

        probe.reset_through_orchestrator(2)
        wait_until(arm.fenced, 5.0, 'm0609_arm 이 orchestrator 의 RESET_BEGIN 을 받지 못했다')
        fenced_sim = arm.sim_now()
        fenced_wall = time.monotonic()
        open_wall = wait_fence_open(arm, GRIPPER_HOLD_S + 10.0)
        result = handle.get_result_async()
        wait_until(result.done, 10.0, '리셋 뒤 Refill 결과가 오지 않았다')
        time.sleep(0.5)
        commands = list(probe.commands)
        done = probe.refill_done()

    joint, gripper = fenced_commands(commands, fenced_sim, fenced_wall, open_wall)
    assert open_wall - fenced_wall >= GRIPPER_HOLD_S * 0.8, f'울타리가 {open_wall - fenced_wall:.2f} s 만 닫혔다'
    assert not gripper, f'울타리 구간 gripper/command {len(gripper)}건: {[c[3] for c in gripper]}'
    assert not joint, f'울타리 구간 joint_command {len(joint)}건'
    assert result.result().status == GoalStatus.STATUS_ABORTED
    assert not result.result().result.success
    assert not done, 'barrier 로 끝난 보충인데 REFILL_DONE 이 나왔다'
