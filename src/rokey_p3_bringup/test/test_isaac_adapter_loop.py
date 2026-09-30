"""L2. pharmacy_only 한 바퀴 + 리셋 1회 + 한 바퀴를 두 구성으로 돌려 이벤트 순서를 맞춘다.

- adapter: stub_sim(serve_dispense·serve_reset·publish_belt=false) + isaac_adapter + 가짜 Isaac(test/fake_isaac.py).
- stub: stub_sim 기본값(지금 거동).
나머지(orchestrator·order_generator·event_logger 실물, stub_fleet·stub_arm·stub_detector)는 같다.
run 마다 events.jsonl 의 이름 순서가 두 구성에서 같아야 한다. adapter 구성에서는 /pharmacy/belt 작성자와
/pharmacy/dispense·/sim/reset 서버가 isaac_adapter 하나인지도 본다(stub_sim 과 겹치지 않는다).
그래프 캐시에 앞 구성의 노드가 남지 않게 adapter 구성을 먼저 돈다.
"""

import contextlib
import json
import threading
import time

import pytest
import rclpy
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from rclpy.parameter import Parameter

from fake_isaac import FakeIsaac
from l2_discovery import wait_for_discovery
from l2_teardown import assert_no_leftovers, teardown_nodes
from rokey_p3_bringup.isaac_adapter import IsaacAdapter
from rokey_p3_bringup.stubs.stub_arm import StubArm
from rokey_p3_bringup.stubs.stub_detector import StubDetector
from rokey_p3_bringup.stubs.stub_fleet import StubFleet
from rokey_p3_bringup.stubs.stub_sim import StubSim
from rokey_p3_interfaces.msg import BeltObservation, Event, GripperCommand, GripperState
from rokey_p3_interfaces.srv import Reset
from rokey_p3_orchestrator.event_logger_node import EventLoggerNode
from rokey_p3_orchestrator.order_generator_node import OrderGeneratorNode
from rokey_p3_orchestrator.orchestrator_node import OrchestratorNode
from rokey_p3_orchestrator.ros_qos import heartbeat_qos, latched_qos, reliable_qos

POOL = """version: 1
orders:
  - {order_id: ord-0001, patient_id: "1001", item_id: drug-amox, bed: bed_a1}
"""
POOL_TWO = """version: 1
orders:
  - {order_id: ord-0001, patient_id: "1001", item_id: drug-amox, bed: bed_a1}
  - {order_id: ord-0002, patient_id: "1002", item_id: drug-ibu, bed: bed_a2}
"""
TRIP_TIMEOUT_S = 60.0


def overrides(values):
    return [Parameter(name, value=value) for name, value in values.items()]


class RecordingGenerator(OrderGeneratorNode):
    def __init__(self, **kwargs):
        self.results = []
        super().__init__(**kwargs)

    def _on_result(self, *args):
        response = args[-1].result()
        self.results.append((response.status, response.result))
        super()._on_result(*args)


class Probe(Node):
    def __init__(self):
        super().__init__('isaac_loop_probe')
        self.events = []
        self.observations = []
        self.reset_client = self.create_client(Reset, '/orchestrator/reset')
        self.create_subscription(Event, '/events', self.events.append, latched_qos(500))
        self.create_subscription(BeltObservation, '/pharmacy/belt/observation', self.observations.append,
                                 heartbeat_qos())
        self.gripper_states = []
        self.create_subscription(GripperState, '/amr_1/gripper/state', self.gripper_states.append, heartbeat_qos())
        self.gripper_command = self.create_publisher(GripperCommand, '/amr_1/gripper/command_seq', reliable_qos(10))

    def named(self, name, epoch):
        return [e for e in self.events if e.name == name and e.epoch == epoch]

    def reset(self, epoch):
        assert self.reset_client.wait_for_service(timeout_sec=5.0), '/orchestrator/reset 서버가 없다'
        future = self.reset_client.call_async(Reset.Request(epoch=epoch))
        wait_until(future.done, 5.0, '/orchestrator/reset 응답이 없다')
        assert future.result().ok, future.result().message


def wait_until(condition, timeout_s, message):
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if condition():
            return
        time.sleep(0.05)
    raise AssertionError(f'{timeout_s} s: {message}')


@contextlib.contextmanager
def pharmacy_loop(tmp_path, use_adapter, pool_text=POOL, max_requests=1, pick_notice=True, belt_observation=False,
                  gripper_command_seq=False):
    tmp_path.mkdir(parents=True, exist_ok=True)
    pool_path = tmp_path / 'order_pool.yaml'
    pool_path.write_text(pool_text, encoding='utf-8')
    pool = {'order_pool_file': str(pool_path)}
    log_dir = tmp_path / 'runs'
    sim = {**pool, 'belt_travel_s': 0.3}
    if use_adapter:
        sim.update({'serve_dispense': False, 'serve_reset': False, 'publish_belt': False})

    assert_no_leftovers()
    rclpy.init()
    executor = MultiThreadedExecutor(num_threads=16)
    nodes = {}
    thread = None
    try:
        nodes['sim'] = StubSim(parameter_overrides=overrides(sim))
        if use_adapter:
            nodes['adapter'] = IsaacAdapter(parameter_overrides=overrides(
                {'pick_notice': pick_notice, 'belt_observation': belt_observation,
                 'gripper_command_seq': gripper_command_seq}))
            nodes['isaac'] = FakeIsaac(str(pool_path), belt_travel_s=0.3, publish_belt_observation=belt_observation,
                                       gripper_command_seq=gripper_command_seq)
        nodes['fleet'] = StubFleet(parameter_overrides=overrides({'travel_s': 0.3}))
        # home_s 0.5: ARM_HOME 이 LOAD_DONE 뒤에 온다(계약 2.6절). 0.1 s 면 부하에서 도착 순서가 뒤집혔다(9/17).
        nodes['arm'] = StubArm(parameter_overrides=overrides({**pool, 'motion_s': 0.1, 'home_s': 0.5}))
        nodes['detector'] = StubDetector(parameter_overrides=overrides(pool))
        nodes['orchestrator'] = OrchestratorNode(parameter_overrides=overrides({**pool, 'pharmacy_only': True}))
        nodes['logger'] = EventLoggerNode(parameter_overrides=overrides({'log_dir': str(log_dir)}))
        nodes['generator'] = RecordingGenerator(parameter_overrides=overrides(
            {**pool, 'max_requests': max_requests, 'start_delay_s': 1.0, 'gap_s': 0.2}))
        nodes['probe'] = Probe()
        for node in nodes.values():
            executor.add_node(node)
        thread = threading.Thread(target=executor.spin, daemon=True)
        thread.start()
        wait_for_discovery(nodes)
        yield nodes, log_dir
    finally:
        if 'logger' in nodes:
            nodes['logger'].close()
        teardown_nodes(executor, thread, list(nodes.values()))


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]


def lap_and_reset(tmp_path, use_adapter):
    """한 바퀴, /orchestrator/reset(2), 한 바퀴. {epoch: 이벤트 dict 목록}, Deliver 결과, 그래프 확인값."""
    graph = {}
    with pharmacy_loop(tmp_path, use_adapter) as (nodes, log_dir):
        probe, generator = nodes['probe'], nodes['generator']
        wait_until(lambda: len(generator.results) >= 1, TRIP_TIMEOUT_S, '첫 바퀴 Deliver 결과가 없다')
        wait_until(lambda: probe.named('DOCKED', 1), 10.0, '첫 바퀴 DOCKED 가 없다')
        probe.reset(2)
        wait_until(lambda: probe.named(Event.RESET_DONE, 2), 40.0, 'RESET_DONE(e2) 가 없다')
        wait_until(lambda: len(generator.results) >= 2, TRIP_TIMEOUT_S, '리셋 뒤 바퀴 Deliver 결과가 없다')
        wait_until(lambda: probe.named('DOCKED', 2), 10.0, '리셋 뒤 바퀴 DOCKED 가 없다')
        time.sleep(1.0)
        nodes['logger'].close()
        results = [(status, result.success, [f'{o.order_id}={o.state}' for o in result.orders])
                   for status, result in generator.results]
        if use_adapter:
            graph['belt_writers'] = sorted(i.node_name for i in probe.get_publishers_info_by_topic('/pharmacy/belt'))
            for service in ('/pharmacy/dispense', '/sim/reset'):
                graph[service] = sorted(
                    name for name, namespace in probe.get_node_names_and_namespaces()
                    if service in dict(probe.get_service_names_and_types_by_node(name, namespace)))
            graph['isaac_requests'] = list(nodes['isaac'].requests)
    runs = {}
    for run in sorted(p for p in log_dir.iterdir() if p.is_dir()):
        meta = json.loads((run / 'meta.json').read_text(encoding='utf-8'))
        runs[meta['epoch']] = read_jsonl(run / 'events.jsonl')
    return runs, results, graph


def names(events):
    return [e['name'] for e in events]


def test_pharmacy_lap_and_reset_through_the_isaac_adapter_match_stub_sim(tmp_path):
    adapter_runs, adapter_results, graph = lap_and_reset(tmp_path / 'adapter', use_adapter=True)
    stub_runs, stub_results, _ = lap_and_reset(tmp_path / 'stub', use_adapter=False)

    detail = '\n'.join(f'{kind} epoch {epoch}: {names(events)}'
                       for kind, runs in (('adapter', adapter_runs), ('stub', stub_runs))
                       for epoch, events in sorted(runs.items()))
    print(detail)
    print(f'adapter Deliver: {adapter_results}\nstub Deliver: {stub_results}\ngraph: {graph}')
    assert sorted(adapter_runs) == sorted(stub_runs) == [1, 2], detail
    for epoch in (1, 2):
        assert names(adapter_runs[epoch]) == names(stub_runs[epoch]), f'epoch {epoch} 이벤트 순서가 다르다\n{detail}'
    assert [r[:2] for r in adapter_results] == [r[:2] for r in stub_results]
    assert [r[2] for r in adapter_results] == [r[2] for r in stub_results]
    dispenser = [e for e in adapter_runs[1] + adapter_runs[2] if e['robot_id'] == 'dispenser']
    assert [(e['epoch'], e['name'], e['request_id']) for e in dispenser] == [
        (1, 'DISPENSED', 'r001-0001'), (1, 'POUCH_AT_END', 'r001-0001'),
        (2, 'DISPENSED', 'r002-0001'), (2, 'POUCH_AT_END', 'r002-0001')], dispenser
    stub_dispenser = [e for e in stub_runs[1] + stub_runs[2] if e['robot_id'] == 'dispenser']
    assert [(e['epoch'], e['name'], e['request_id']) for e in stub_dispenser] == \
        [(e['epoch'], e['name'], e['request_id']) for e in dispenser], stub_dispenser  # stub_sim 도 request_id
    assert not [e for e in adapter_runs[1] + adapter_runs[2] if e['stale']], detail
    assert graph['belt_writers'] == ['isaac_adapter'], graph
    assert graph['/pharmacy/dispense'] == ['isaac_adapter'] and graph['/sim/reset'] == ['isaac_adapter'], graph
    assert '{"epoch":2,"v":1}' in graph['isaac_requests'], graph


@pytest.mark.parametrize('pick_notice', [True, False])
def test_second_dispense_in_one_epoch_needs_the_pick_notice(tmp_path, pick_notice):
    """가짜 Isaac 은 봉투가 집힌 것을 pick_notice 로만 안다.

    켜져 있으면 같은 epoch 의 두 번째 Dispense 가 바로 수락되고 두 트립이 끝난다.
    꺼져 있으면 벨트에 첫 봉투가 남는다. orchestrator 는 벨트가 비지 않으면 Dispense 를 부르지 않으므로(배출 조건)
    두 번째 트립은 적재 위치에서 기다리고 Isaac 에 두 번째 배출 요청이 가지 않는다.
    """
    with pharmacy_loop(tmp_path, True, pool_text=POOL_TWO, max_requests=2, pick_notice=pick_notice) as (nodes, _):
        generator, probe = nodes['generator'], nodes['probe']
        if pick_notice:
            wait_until(lambda: len(generator.results) >= 2, TRIP_TIMEOUT_S, 'Deliver 결과가 둘이 아니다')
        else:
            wait_until(lambda: len(probe.named('AMR_DOCKED_LOAD', 1)) >= 2, TRIP_TIMEOUT_S,
                       '두 번째 트립이 적재 위치에 안 왔다')
            time.sleep(5.0)                                    # Dispense 재시도 간격(2 s)보다 길게 본다
        results = [[f'{o.order_id}={o.state}' for o in result.orders] for _, result in generator.results]
        responses = [json.loads(text) for text in nodes['isaac'].responses]
        notices = list(nodes['isaac'].notices)
        if not pick_notice:
            # 기다리는 트립을 리셋으로 끝낸다. orchestrator 의 Deliver 실행 콜백은 트립이 끝날 때까지
            # 스레드를 잡고 있어서, 트립 도중에 끝내면 인터프리터 종료가 그 스레드를 기다리며 멈춘다(9/17 관측).
            probe.reset(2)
            wait_until(lambda: len(generator.results) >= 2, 40.0, '리셋 뒤 두 번째 Deliver 결과가 없다')

    detail = f'results={results} responses={responses} notices={notices}'
    first = [r for r in responses if r['order_id'] == 'ord-0001']
    second = [r for r in responses if r['order_id'] == 'ord-0002']
    assert [r['accepted'] for r in first] == [True], detail
    if pick_notice:
        assert [(r['accepted'], r['message']) for r in second] == [(True, '')], detail
        assert [json.loads(n)['order_id'] for n in notices] == ['ord-0001', 'ord-0002'], detail
        assert results == [['ord-0001=11'], ['ord-0002=11']], detail              # 11 = HOLD_RETURN
    else:
        assert second == [], detail                                               # 두 번째 배출 요청이 없다
        assert notices == [], detail
        assert results == [['ord-0001=11']], detail


def test_belt_observation_rides_along_a_lap_when_both_sides_opt_in(tmp_path):
    """fake Isaac(--belt-observation 흉내) → adapter(belt_observation) → /pharmacy/belt/observation. 계약 11.6.

    한 바퀴 동안 빈 벨트 → 이동 중 → 벨트 끝 정착을 모두 보고, seq 가 epoch 안에서 줄지 않는다.
    fake 는 물리가 없어 mode 가 STUB 다. 기존 /pharmacy/belt 경로와 한 바퀴 결과는 opt-in 과 무관하다.
    """
    with pharmacy_loop(tmp_path, True, belt_observation=True) as (nodes, _):
        generator, probe = nodes['generator'], nodes['probe']
        wait_until(lambda: len(generator.results) >= 1, TRIP_TIMEOUT_S, 'Deliver 결과가 없다')
        observations = list(probe.observations)
        dropped = dict(nodes['adapter'].dropped)
    at_end = [o for o in observations if o.pouch_zone == BeltObservation.ZONE_END]
    moving = [o for o in observations if o.pouch_zone == BeltObservation.ZONE_ON_BELT]
    empty = [o for o in observations if o.occupancy == BeltObservation.OCCUPANCY_EMPTY]
    assert at_end and moving and empty, [(o.seq, o.occupancy, o.pouch_zone) for o in observations]
    assert all(o.mode == BeltObservation.MODE_STUB and o.epoch == 1 for o in observations)
    assert all(o.belt_motion == BeltObservation.MOTION_UNKNOWN for o in observations)
    assert {(o.order_id, o.request_id, o.pouch_motion, o.belt_command_applied) for o in at_end} == {
        ('ord-0001', 'r001-0001', BeltObservation.MOTION_STOPPED, BeltObservation.APPLIED_STOP)}
    seqs = [o.seq for o in observations]
    assert seqs == sorted(seqs), seqs
    assert not any(v for k, v in dropped.items() if k.startswith('observation_')), dropped
    assert [result.success for _, result in generator.results] == [False]    # pharmacy_only: HOLD_RETURN 주장


def test_gripper_command_seq_round_trip_through_the_adapter(tmp_path):
    """arm 자리의 GripperCommand → adapter → fake Isaac(#278 흉내) → adapter → GripperState. 계약 11.6.

    흡착 확인 = HELD 이고 last_applied_command_seq ≥ 닫기 명령 seq. 같은 seq 재전송은 무시된다(멱등).
    """
    with pharmacy_loop(tmp_path, True, gripper_command_seq=True) as (nodes, _):
        probe = nodes['probe']

        def send(seq, close):
            msg = GripperCommand(epoch=1, command_seq=seq, close=close)
            msg.header.stamp = probe.get_clock().now().to_msg()
            probe.gripper_command.publish(msg)

        def latest():
            return (probe.gripper_states[-1].last_applied_command_seq, probe.gripper_states[-1].state) \
                if probe.gripper_states else None

        wait_until(lambda: latest() == (0, GripperState.STATE_RELEASED), 5.0, '첫 그리퍼 상태가 없다')
        send(1, True)
        wait_until(lambda: latest() == (1, GripperState.STATE_HELD), 5.0, '닫기가 적용되지 않았다')
        send(1, False)                                               # 같은 seq 재전송: 무시
        time.sleep(0.5)
        held = latest()
        send(2, False)
        wait_until(lambda: latest() == (2, GripperState.STATE_RELEASED), 5.0, '열기가 적용되지 않았다')
        states = list(probe.gripper_states)
        dropped = {k: v for k, v in nodes['adapter'].dropped.items() if k.startswith('gripper_')}
    assert held == (1, GripperState.STATE_HELD)
    assert all(s.mode == GripperState.MODE_VIRTUAL and s.epoch == 1 for s in states)
    assert [s.seq for s in states] == sorted(s.seq for s in states)
    assert not any(dropped.values()), dropped
