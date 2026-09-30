"""L2. 스텁 팔의 /m0609/arm/at_home. 실물 m0609_arm 과 같은 이름·같은 거동(계약 2.1절 M0609, 8절).

- test_stub_arm_publishes_m0609_at_home_around_a_refill: serve_refill 이면 5 Hz 로 내고, Refill 실행 중 false.
  실물 #99 처럼 홈에 돌아온 뒤 결과를 내므로 결과는 motion_s + home_s 뒤에 오고, 결과를 받을 때 곧 true 다.
- test_cancelled_refill_answers_first_and_homes_after: 취소는 결과를 먼저 내고 home_s 뒤 true(실물 #99).
- test_m0609_at_home_waits_for_reset_done: 결과 전 홈 복귀(REFILL_DONE 뒤) 중에 RESET_BEGIN 이 오면
  홈에 닿지 않고 결과를 내고, 같은 epoch 의 RESET_DONE 뒤 home_s 에 닿는다.
  결과 lot_id 는 리셋 앞뒤 모두 빈 값이다(실물 #99 와 같다).
- test_refill_that_ends_inside_the_barrier_homes_only_after_reset_done: Refill 실행 중에 RESET_BEGIN 이 오고
  barrier 안에서 결과가 나도 RESET_DONE 전에는 홈에 닿지 않는다.
- test_one_writer_for_m0609_at_home[stub|real]: 토픽 작성자가 하나다.
  stub 은 기본 구성(stub_sim emulate_m0609 + stub_arm serve_refill)으로 stub_arm 하나,
  real 은 use_stub_m0609:=false 구성(stub_arm serve_refill=false + 실물 m0609_arm)으로 m0609_arm 하나.
  stub_sim 은 M0609 를 흉내 내도 at_home 은 내지 않는다.
"""

import contextlib
import threading
import time

import pytest
import rclpy
from action_msgs.msg import GoalStatus
from rclpy.action import ActionClient
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from rclpy.parameter import Parameter
from std_msgs.msg import Bool

from rokey_p3_bringup.stubs.stub_arm import StubArm
from rokey_p3_bringup.stubs.stub_sim import StubSim
from rokey_p3_interfaces.action import Refill
from rokey_p3_interfaces.msg import Event
from rokey_p3_manipulation.m0609_arm_node import M0609ArmNode
from rokey_p3_orchestrator.ros_qos import heartbeat_qos, latched_qos
from l2_discovery import missing_server_report, wait_for_discovery
from l2_teardown import assert_no_leftovers, teardown_nodes

POOL = """version: 1
orders:
  - {order_id: ord-0001, patient_id: "1001", item_id: drug-amox, bed: bed_a1}
"""
TOPIC = '/m0609/arm/at_home'
MOTION_S = 1.0
HOME_S = 1.0


class Probe(Node):
    """/m0609/arm/at_home 을 (받은 wall, 값) 으로 모으고 Refill·barrier 이벤트를 보낸다."""

    def __init__(self):
        super().__init__('m0609_at_home_probe')
        self.samples = []
        self.client = ActionClient(self, Refill, '/m0609/refill')
        self.events = []
        self.event_pub = self.create_publisher(Event, '/events', latched_qos(500))
        self.create_subscription(Event, '/events', self.events.append, latched_qos(500))
        self.create_subscription(Bool, TOPIC, self._on_at_home, heartbeat_qos())

    def _on_at_home(self, msg):
        self.samples.append((time.monotonic(), bool(msg.data)))

    def latest(self):
        return self.samples[-1][1] if self.samples else None

    def since(self, wall):
        return [value for received, value in self.samples if received >= wall]

    def publish_event(self, name, epoch):
        event = Event()
        event.header.stamp = self.get_clock().now().to_msg()
        event.name = name
        event.robot_id = 'orchestrator'
        event.epoch = epoch
        self.event_pub.publish(event)

    def send(self):
        """drug-amox 슬롯 a 를 보내고 수락된 goal handle."""
        if not self.client.wait_for_server(timeout_sec=10.0):
            raise AssertionError(f'/m0609/refill 서버가 없다(fixture 에서는 보였다)\n'
                                 f'{missing_server_report(self, "/m0609/refill")}')
        sent = self.client.send_goal_async(Refill.Goal(item_id='drug-amox', slot=0))
        wait_until(sent.done, 10.0, 'goal 응답이 없다')
        assert sent.result().accepted
        return sent.result()

    def refill(self, handle=None):
        """(결과 받은 wall, result). status 는 result_status 에 남긴다."""
        handle = handle or self.send()
        result = handle.get_result_async()
        wait_until(result.done, 30.0, 'Refill 결과가 오지 않았다')
        self.result_status = result.result().status
        return time.monotonic(), result.result().result


def wait_until(condition, timeout_s, message):
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if condition():
            return
        time.sleep(0.02)
    raise AssertionError(f'{timeout_s} s: {message}')


def first_true_after(probe, wall, timeout_s):
    """wall 뒤 처음 true 를 받은 wall."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        for received, value in list(probe.samples):
            if received > wall and value:
                return received
        time.sleep(0.02)
    raise AssertionError(f'{timeout_s} s 안에 {TOPIC} true 가 없다')


@contextlib.contextmanager
def running(tmp_path, serve_refill=True, real_arm=False):
    pool_path = tmp_path / 'order_pool.yaml'
    pool_path.write_text(POOL, encoding='utf-8')
    assert_no_leftovers()
    rclpy.init()
    executor = MultiThreadedExecutor(num_threads=8)
    nodes = []
    thread = None
    try:
        nodes.append(StubSim(parameter_overrides=[
            Parameter('order_pool_file', value=str(pool_path)),
            Parameter('emulate_m0609', value=True)]))
        nodes.append(StubArm(parameter_overrides=[
            Parameter('order_pool_file', value=str(pool_path)),
            Parameter('serve_refill', value=serve_refill),
            Parameter('motion_s', value=MOTION_S),
            Parameter('home_s', value=HOME_S)]))
        if real_arm:
            nodes.append(M0609ArmNode())
        probe = Probe()
        nodes.append(probe)
        for node in nodes:
            executor.add_node(node)
        thread = threading.Thread(target=executor.spin, daemon=True)
        thread.start()
        # 9/17 #137 CI: 결과 전에 "/m0609/refill 서버가 없다". 처음부터 못 본 것인지 도중에 놓친 것인지 가른다.
        wait_for_discovery({'probe': probe},
                           checks=[('m0609_at_home_probe → /m0609/refill', probe.client.server_is_ready)])
        yield probe
    finally:
        for node in nodes:
            if isinstance(node, M0609ArmNode):
                node.stop_homing()
        teardown_nodes(executor, thread, nodes)


def test_stub_arm_publishes_m0609_at_home_around_a_refill(tmp_path):
    with running(tmp_path) as probe:
        wait_until(lambda: probe.latest() is True, 5.0, f'{TOPIC} true 가 없다')
        start = time.monotonic()
        time.sleep(2.0)
        idle = probe.since(start)
        sent = time.monotonic()
        done_wall, result = probe.refill()
        during = [value for received, value in probe.samples if sent + 0.3 < received < done_wall - 0.3]
        home_wall = first_true_after(probe, done_wall - 0.3, HOME_S + 2.0)

    assert result.success and result.lot_id == ''
    assert 8 <= len(idle) <= 12 and all(idle), f'2 s 동안 {len(idle)}건(5 Hz 면 10): {idle}'
    assert during and not any(during), f'Refill 실행 중 at_home: {during}'
    assert done_wall - sent >= (MOTION_S + HOME_S) * 0.9, f'결과가 {done_wall - sent:.2f} s 만에 왔다(홈 복귀 전)'
    assert home_wall - done_wall <= 0.5, f'결과 뒤 {home_wall - done_wall:.2f} s 에야 홈이다(결과 전에 홈이어야 한다)'


def test_cancelled_refill_answers_first_and_homes_after(tmp_path):
    with running(tmp_path) as probe:
        wait_until(lambda: probe.latest() is True, 5.0, f'{TOPIC} true 가 없다')
        handle = probe.send()
        cancel = handle.cancel_goal_async()
        wait_until(cancel.done, 5.0, 'cancel 응답이 없다')
        done_wall, result = probe.refill(handle)
        status = probe.result_status
        home_wall = first_true_after(probe, done_wall, HOME_S + 2.0)
        refill_done = [e for e in probe.events if e.name == Event.REFILL_DONE]

    assert status == GoalStatus.STATUS_CANCELED and not result.success
    assert not refill_done, '취소한 보충인데 REFILL_DONE 이 나왔다'
    assert home_wall - done_wall >= HOME_S * 0.7, f'취소 결과 뒤 {home_wall - done_wall:.2f} s 만에 홈이다'


def test_m0609_at_home_waits_for_reset_done(tmp_path):
    with running(tmp_path) as probe:
        wait_until(lambda: probe.latest() is True, 5.0, f'{TOPIC} true 가 없다')
        handle = probe.send()
        wait_until(lambda: [e for e in probe.events if e.name == Event.REFILL_DONE], 10.0, 'REFILL_DONE 이 없다')
        probe.publish_event(Event.RESET_BEGIN, 2)       # 결과 전 홈 복귀(HOME_S) 도중
        begin_wall = time.monotonic()
        done_wall, first = probe.refill(handle)
        time.sleep(HOME_S + 1.0)
        fenced = probe.since(begin_wall)
        probe.publish_event(Event.RESET_DONE, 2)
        reset_done_wall = time.monotonic()
        home_wall = first_true_after(probe, reset_done_wall, HOME_S + 2.0)
        _, second = probe.refill()

    assert done_wall - begin_wall < HOME_S * 0.5, 'barrier 인데 결과가 홈 복귀를 기다렸다'
    assert fenced and not any(fenced), f'RESET_DONE 전에 홈에 닿았다: {fenced}'
    assert home_wall - reset_done_wall >= HOME_S * 0.7, f'RESET_DONE 뒤 {home_wall - reset_done_wall:.2f} s 만에 홈이다'
    assert first.lot_id == '' and second.lot_id == '', f'lot_id 를 지어냈다: {first.lot_id!r}, {second.lot_id!r}'


def test_refill_that_ends_inside_the_barrier_homes_only_after_reset_done(tmp_path):
    """RESET_BEGIN 뒤에 끝난 Refill(스텁은 실행 중 goal 을 멈추지 않는다)도 barrier 중에는 홈에 닿지 않는다."""
    with running(tmp_path) as probe:
        wait_until(lambda: probe.latest() is True, 5.0, f'{TOPIC} true 가 없다')
        assert probe.client.wait_for_server(timeout_sec=10.0)
        sent = probe.client.send_goal_async(Refill.Goal(item_id='drug-amox', slot=0))
        wait_until(sent.done, 10.0, 'goal 응답이 없다')
        assert sent.result().accepted
        probe.publish_event(Event.RESET_BEGIN, 2)       # 실행(MOTION_S) 도중
        result = sent.result().get_result_async()
        wait_until(result.done, 30.0, 'Refill 결과가 오지 않았다')
        done_wall = time.monotonic()
        time.sleep(HOME_S + 1.0)
        fenced = probe.since(done_wall)
        probe.publish_event(Event.RESET_DONE, 2)
        reset_done_wall = time.monotonic()
        home_wall = first_true_after(probe, reset_done_wall, HOME_S + 2.0)

    assert fenced and not any(fenced), f'barrier 중에 홈에 닿았다: {fenced}'
    assert home_wall - reset_done_wall >= HOME_S * 0.7, f'RESET_DONE 뒤 {home_wall - reset_done_wall:.2f} s 만에 홈이다'


@pytest.mark.parametrize('combination', ['stub', 'real'])
def test_one_writer_for_m0609_at_home(tmp_path, combination):
    real = combination == 'real'
    with running(tmp_path, serve_refill=not real, real_arm=real) as probe:
        wait_until(lambda: probe.count_publishers(TOPIC) >= 1, 10.0, f'{TOPIC} 작성자가 없다')
        time.sleep(1.5)                                 # 늦게 발견되는 작성자까지
        writers = sorted(info.node_name for info in probe.get_publishers_info_by_topic(TOPIC))

    assert writers == (['m0609_arm'] if real else ['stub_arm']), f'{TOPIC} 작성자: {writers}'
