"""L2. 리셋 barrier v2(계약 6절)를 스텁 한 바퀴 위에서 본다. orchestrator·order_generator·event_logger 는 실물이다.

- test_reset_barrier_cancel_races[pick|drive|return]: 트립 도중 /orchestrator/reset.
  pick 은 벨트 PickPouch 실행 중, drive 는 침상으로 GoToZone 주행 중, return 은 도크로 복귀 주행 중이다.
  확인하는 것:
  - /sim/reset 이 끊긴 goal 의 종결보다 먼저 불리지 않는다.
  - 끊긴 주문의 ABORT(reset_interrupted)·ORDER_DONE 이 이전 epoch run 에 기록된다.
    ORDER_DONE 은 RESET_BEGIN 과 같은 stamp 이고, RESET_BEGIN 보다 앞에 온다.
  - 늦은 결과가 새 epoch 트립을 건드리지 않는다.
- test_pharmacy_reset_three_laps: pharmacy_only 로 (reset → 트립)×3. epoch 2·3·4 run 디렉토리마다 확인한다.
  - 집계기(tools/aggregate_runs.py, protocol pharmacy-lap-pilot-v1)가 lap_success 1 이다.
  - 첫 요청(rNNN-0001)이 수락된다. 거부로 버려진 요청이 없다는 뜻이다.
  - run 경계가 깨끗하다: epoch 가 섞이지 않고, stale 0, RESET_BEGIN 으로 시작한다.
- test_reset_failure_stops_and_a_new_reset_recovers[fail|hang]: stub_sim 이 /sim/reset 에 ok=false 로 답하거나
  reset_timeout_s 보다 늦게 답하는 경우다.
  - barrier 가 실패로 멈춘다: Deliver 거부, 그 epoch 의 RESET_DONE 없음. 늦은 ok 도 무시한다.
  - 새 /orchestrator/reset 으로 복구되어 다음 트립이 끝난다.

- test_generator_sends_after_a_reset_that_interrupted_a_trip: protocol 설정(max_requests=1)에서 트립을 끊은 리셋 뒤
  새 epoch 에도 요청 1건이 나간다(정비 9호·마클이 본 발행기 결함, #84 에서 고침. 회귀 테스트).
- test_interrupted_order_is_closed_in_the_previous_epoch_run: 끊긴 주문의 ABORT(reset_interrupted)가 이전 epoch run 에만
  남는다(정비 9호가 본 event_logger run 경계 결함, #87 에서 고침. 회귀 테스트).
- test_observation_before_reset_done_is_not_judged_in_the_new_run: 느린 리셋(stub_sim reset_delay_s 3 s)에서
  RESET_DONE 전의 보관함 관측이 새 run 에 pre_reset 으로만 남고 판정에 쓰이지 않는다
  (같은 결함의 둘째, #87 에서 고침. 회귀 테스트).

goal 실행 시각과 /sim/reset 호출 시각은 스텁을 감싼 하위 클래스가 기록한다. 스텁 동작은 바꾸지 않는다.
"""

import contextlib
import importlib.util
import json
import pathlib
import threading
import time

import pytest
import rclpy
import yaml
from rclpy.action import ActionClient
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from rclpy.parameter import Parameter

from l2_discovery import wait_for_discovery
from l2_teardown import assert_no_leftovers, teardown_nodes
from rokey_p3_bringup.stubs.stub_arm import StubArm
from rokey_p3_bringup.stubs.stub_detector import StubDetector
from rokey_p3_bringup.stubs.stub_fleet import StubFleet
from rokey_p3_bringup.stubs.stub_sim import StubSim
from rokey_p3_interfaces.action import Deliver
from rokey_p3_interfaces.msg import Event, Order
from rokey_p3_interfaces.srv import Reset
from rokey_p3_orchestrator import order_pool
from rokey_p3_orchestrator.event_logger_node import EventLoggerNode
from rokey_p3_orchestrator.order_generator_node import OrderGeneratorNode
from rokey_p3_orchestrator.orchestrator_node import OrchestratorNode
from rokey_p3_orchestrator.ros_qos import latched_qos

POOL = """version: 1
orders:
  - {order_id: ord-0001, patient_id: "1001", item_id: drug-amox, bed: bed_a1}
"""

REPO = pathlib.Path(__file__).resolve().parents[3]
PROTOCOL = REPO / 'experiments' / 'protocols' / 'pharmacy-lap-pilot-v1.json'

TRIP_TIMEOUT_S = 90.0
RESET_TIMEOUT_S = 2.0       # 실패 케이스에서 orchestrator reset_timeout_s(기본 30 s)를 줄인다
HANG_S = 4.0                # stub_sim 이 늦게 답하는 시간. RESET_TIMEOUT_S 보다 길다

SLOW_RESET_S = 3.0          # event_logger run_drain_s(2 s)보다 길어야 RESET_DONE 전 관측이 새 run 으로 간다


def overrides(values):
    return [Parameter(name, value=value) for name, value in values.items()]


class Marks:
    """스텁이 남기는 (wall, 종류, 값). 여러 executor 스레드가 쓴다."""

    def __init__(self):
        self._lock = threading.Lock()
        self.rows = []

    def add(self, kind, value=''):
        with self._lock:
            self.rows.append((time.monotonic(), kind, value))

    def of(self, kind):
        with self._lock:
            return [row for row in self.rows if row[1] == kind]


class TimedStubSim(StubSim):
    def __init__(self, marks, **kwargs):
        self._marks = marks
        super().__init__(**kwargs)

    def _on_reset(self, request, response):
        self._marks.add('sim_reset_called', request.epoch)
        return super()._on_reset(request, response)


class TimedStubArm(StubArm):
    def __init__(self, marks, **kwargs):
        self._marks = marks
        super().__init__(**kwargs)

    def _execute_pick(self, goal_handle):
        self._marks.add('pick_start', goal_handle.request.order_id)
        try:
            return super()._execute_pick(goal_handle)
        finally:
            self._marks.add('pick_end', goal_handle.request.order_id)


class TimedStubFleet(StubFleet):
    def __init__(self, marks, **kwargs):
        self._marks = marks
        super().__init__(**kwargs)

    def _execute(self, goal_handle):
        self._marks.add('goto_start', goal_handle.request.zone_id)
        try:
            return super()._execute(goal_handle)
        finally:
            self._marks.add('goto_end', goal_handle.request.zone_id)


class RecordingGenerator(OrderGeneratorNode):
    """Deliver 결과를 전부 남긴다(last_result 는 마지막 하나뿐이다)."""

    def __init__(self, **kwargs):
        self.results = []
        super().__init__(**kwargs)

    def _on_result(self, *args):
        # 시그니처는 발행기 쪽이 정한다(#84 부터 request_id, epoch, future). future 는 마지막 인자다.
        response = args[-1].result()
        self.results.append((response.status, response.result))
        super()._on_result(*args)


class Probe(Node):
    """/events 를 모으고 /orchestrator/reset 과 Deliver goal 을 보낸다."""

    def __init__(self):
        super().__init__('barrier_probe')
        self.events = []
        self.reset_client = self.create_client(Reset, '/orchestrator/reset')
        self.deliver = ActionClient(self, Deliver, '/deliver')
        self.create_subscription(Event, '/events', self.events.append, latched_qos(500))

    def named(self, name, epoch=None):
        return [e for e in self.events if e.name == name and (epoch is None or e.epoch == epoch)]

    def reset(self, epoch):
        """/orchestrator/reset. 호출 **직전** wall 을 돌려준다. orchestrator 는 응답 전에 cancel 을 보내므로
        응답 뒤 시각을 쓰면 빨리 끝난 goal 이 리셋 전에 끝난 것처럼 보인다."""
        assert self.reset_client.wait_for_service(timeout_sec=5.0), '/orchestrator/reset 서버가 없다'
        called = time.monotonic()
        future = self.reset_client.call_async(Reset.Request(epoch=epoch))
        wait_until(future.done, 5.0, '/orchestrator/reset 응답이 없다')
        assert future.result().ok, future.result().message
        return called

    def deliver_accepted(self, request_id):
        """주문 풀의 첫 요청으로 Deliver goal 하나. 수락됐으면 True(수락된 goal 은 곧 cancel 한다)."""
        assert self.deliver.wait_for_server(timeout_sec=5.0), '/deliver 서버가 없다'
        orders = order_pool.load_pool(yaml.safe_load(POOL))
        pending = order_pool.build_requests(orders)[0]
        goal = Deliver.Goal()
        goal.request.request_id = request_id
        goal.request.mode = pending.mode_value
        goal.request.destination_id = pending.destination_id
        goal.request.orders = [Order(order_id=o.order_id, patient_id=o.patient_id, item_id=o.item_id)
                               for o in orders if o.order_id in pending.order_ids]
        sent = self.deliver.send_goal_async(goal)
        wait_until(sent.done, 5.0, 'Deliver goal 응답이 없다')
        return sent.result().accepted


def wait_until(condition, timeout_s, message):
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if condition():
            return
        time.sleep(0.05)
    raise AssertionError(f'{timeout_s} s: {message}')


@contextlib.contextmanager
def barrier_loop(tmp_path, orchestrator=None, sim=None, fleet=None, arm=None, generator=None):
    """스텁 넷 + 실물 orchestrator·order_generator·event_logger + probe."""
    pool_path = tmp_path / 'order_pool.yaml'
    pool_path.write_text(POOL, encoding='utf-8')
    pool = {'order_pool_file': str(pool_path)}
    log_dir = tmp_path / 'runs'
    marks = Marks()

    assert_no_leftovers()
    rclpy.init()
    executor = MultiThreadedExecutor(num_threads=16)
    nodes = {}
    thread = None
    try:
        nodes['sim'] = TimedStubSim(marks, parameter_overrides=overrides({**pool, 'belt_travel_s': 0.3, **(sim or {})}))
        nodes['fleet'] = TimedStubFleet(marks, parameter_overrides=overrides({'travel_s': 0.3, **(fleet or {})}))
        nodes['arm'] = TimedStubArm(marks, parameter_overrides=overrides(
            {**pool, 'motion_s': 0.1, 'home_s': 0.1, **(arm or {})}))
        nodes['detector'] = StubDetector(parameter_overrides=overrides(pool))
        nodes['orchestrator'] = OrchestratorNode(parameter_overrides=overrides({**pool, **(orchestrator or {})}))
        nodes['logger'] = EventLoggerNode(parameter_overrides=overrides({'log_dir': str(log_dir)}))
        nodes['generator'] = RecordingGenerator(parameter_overrides=overrides(
            {**pool, 'max_requests': 1, 'start_delay_s': 1.0, 'gap_s': 0.2, **(generator or {})}))
        nodes['probe'] = Probe()
        for node in nodes.values():
            executor.add_node(node)
        thread = threading.Thread(target=executor.spin, daemon=True)
        thread.start()
        wait_for_discovery(nodes)
        yield nodes, marks, log_dir
    finally:
        if 'logger' in nodes:
            nodes['logger'].close()
        teardown_nodes(executor, thread, list(nodes.values()))


def wait_results(generator, count, timeout_s=TRIP_TIMEOUT_S):
    wait_until(lambda: len(generator.results) >= count, timeout_s, f'Deliver 결과가 {count}건이 되지 않았다')
    return generator.results[count - 1]


def read_jsonl(path):
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]


def runs_by_epoch(log_dir):
    """event_logger run 디렉토리를 meta.json 의 epoch 로. 같은 epoch 가 둘이면 실패다."""
    runs = {}
    for run in sorted(p for p in log_dir.iterdir() if p.is_dir()):
        meta = json.loads((run / 'meta.json').read_text(encoding='utf-8'))
        assert meta['epoch'] not in runs, f'epoch {meta["epoch"]} run 이 둘이다: {runs[meta["epoch"]].name}, {run.name}'
        runs[meta['epoch']] = run
    return runs


def summary(run):
    """실패 메시지에 넣을 run 요약."""
    events = [(round(e['stamp'], 3), e['epoch'], e['name'], e['request_id'], e['order_id'], e['stale'])
              for e in read_jsonl(run / 'events.jsonl')]
    statuses = [(s['request_id'], s['order_id'], s['state'], s['reason'])
                for s in read_jsonl(run / 'order_status.jsonl')]
    return f'{run.name}\n  events={events}\n  order_status={statuses}\n  orders={read_jsonl(run / "orders.jsonl")}'


# 트립 도중 리셋 ------------------------------------------------------------

RACES = {
    # 이 이벤트(epoch 1)를 보면 리셋한다. 그때 실행 중이어야 하는 goal 표시.
    'pick': ('PICK_ATTEMPT', 'pick'),
    'drive': ('DEPARTED', 'goto'),
    'return': ('RETURNED', 'goto'),
}


@pytest.mark.parametrize('moment', list(RACES))
def test_reset_barrier_cancel_races(tmp_path, moment):
    trigger, goal_kind = RACES[moment]
    with barrier_loop(tmp_path, fleet={'travel_s': 3.0}, arm={'motion_s': 1.0}) as (nodes, marks, log_dir):
        probe, generator = nodes['probe'], nodes['generator']
        wait_until(lambda: probe.named(trigger, 1), TRIP_TIMEOUT_S, f'{trigger} 가 나오지 않았다')
        reset_wall = probe.reset(2)
        wait_until(lambda: probe.named(Event.RESET_DONE, 2), 30.0, 'RESET_DONE(e2) 가 나오지 않았다')
        first = wait_results(generator, 1)
        second = wait_results(generator, 2)
        time.sleep(1.5)                     # 평가 관측(1 Hz)
        nodes['logger'].close()
        starts, ends = marks.of(f'{goal_kind}_start'), marks.of(f'{goal_kind}_end')
        sim_resets = marks.of('sim_reset_called')

    runs = runs_by_epoch(log_dir)
    assert set(runs) == {1, 2}, f'run epoch 가 {sorted(runs)} 다'
    old, new = runs[1], runs[2]
    old_events, new_events = read_jsonl(old / 'events.jsonl'), read_jsonl(new / 'events.jsonl')
    detail = (f'\nreset_wall={reset_wall:.3f} {goal_kind} start={[round(s[0], 3) for s in starts]} '
              f'end={[round(e[0], 3) for e in ends]} sim_reset={[(round(r[0], 3), r[2]) for r in sim_resets]}'
              f'\n{summary(old)}\n{summary(new)}')

    # 1. /sim/reset 은 리셋 때 실행 중이던 goal 이 끝난 뒤에 불린다.
    active = [(s, e) for s, e in zip(starts, ends + [None] * (len(starts) - len(ends)), strict=True)
              if s[0] < reset_wall and (e is None or e[0] > reset_wall)]
    assert active, f'리셋 때 실행 중인 {goal_kind} goal 이 없다(경합을 못 만들었다){detail}'
    assert all(e is not None for _, e in active), f'끊긴 goal 이 끝나지 않았다{detail}'
    called = [row for row in sim_resets if row[2] == 2]
    assert len(called) == 1, f'/sim/reset(e2) 호출이 {len(called)}번이다'
    assert all(e[0] <= called[0][0] for _, e in active), \
        f'/sim/reset 이 goal 종결보다 먼저 불렸다: 종결 {[e[0] for _, e in active]}, 호출 {called[0][0]}{detail}'

    # 2. 끊긴 주문은 이전 epoch 로 닫히고(ORDER_DONE 은 이전 run, RESET_BEGIN 과 같은 stamp),
    #    RESET_BEGIN 이 새 run 을 연다.
    #    ABORT 상태가 어느 run 파일에 들어가는지는 test_interrupted_order_is_closed_in_the_previous_epoch_run 이 본다.
    assert new_events and new_events[0]['name'] == 'RESET_BEGIN', f'새 run 이 RESET_BEGIN 으로 시작하지 않는다{detail}'
    begin = new_events[0]
    old_status = read_jsonl(old / 'order_status.jsonl')
    new_status = read_jsonl(new / 'order_status.jsonl')
    if moment == 'return':
        # 복귀 중에는 주문이 이미 DELIVERED 로 끝났다. 끊긴 주문이 없다.
        assert not [s for s in old_status + new_status if s['reason'] == 'reset_interrupted'], detail
    else:
        interrupted = [s for s in old_status + new_status
                       if s['state'] == 'ABORT' and s['reason'] == 'reset_interrupted']
        assert [s['request_id'] for s in interrupted] == ['r001-0001'], \
            f'끊긴 주문의 ABORT(reset_interrupted) 가 없다{detail}'
        done = [e for e in old_events if e['name'] == 'ORDER_DONE' and e['request_id'] == 'r001-0001']
        assert len(done) == 1 and done[0]['epoch'] == 1, f'이전 epoch ORDER_DONE 이 이전 run 에 없다{detail}'
        assert done[0]['stamp'] == begin['stamp'], f'ORDER_DONE 과 RESET_BEGIN 의 stamp 가 다르다{detail}'
        old_orders = {o['order_id']: o for o in read_jsonl(old / 'orders.jsonl')}
        assert old_orders['ord-0001']['state'] == 'ABORT', detail

    # 3. 늦은 결과가 새 epoch 트립을 건드리지 않는다.
    assert not first[1].success, f'끊긴 트립의 Deliver 결과가 success 다{detail}'
    assert second[1].success, f'리셋 뒤 트립이 성공하지 않았다{detail}'
    trip = [e for e in new_events if e['request_id']]
    assert trip and all(e['request_id'] == 'r002-0001' for e in trip), f'새 run 에 다른 요청의 이벤트가 있다{detail}'
    assert all(e['epoch'] == 2 for e in new_events if not e['stale']), detail
    new_orders = read_jsonl(new / 'orders.jsonl')
    assert [(o['request_id'], o['state']) for o in new_orders] == [('r002-0001', 'SUCCESS')], detail


def test_generator_sends_after_a_reset_that_interrupted_a_trip(tmp_path):
    """protocol 설정(max_requests=1)에서 벨트 픽 도중 리셋하면 새 epoch 에도 요청 1건이 나가야 한다."""
    with barrier_loop(tmp_path, fleet={'travel_s': 3.0}, arm={'motion_s': 1.0}) as (nodes, marks, log_dir):
        probe, generator = nodes['probe'], nodes['generator']
        wait_until(lambda: probe.named('PICK_ATTEMPT', 1), TRIP_TIMEOUT_S, 'PICK_ATTEMPT 가 나오지 않았다')
        probe.reset(2)
        wait_until(lambda: probe.named(Event.RESET_DONE, 2), 30.0, 'RESET_DONE(e2) 가 나오지 않았다')
        wait_results(generator, 1)
        wait_results(generator, 2, timeout_s=30.0)


def test_interrupted_order_is_closed_in_the_previous_epoch_run(tmp_path):
    """주행 중 리셋으로 끊긴 주문의 상태는 이전 epoch run 에만 있어야 한다."""
    with barrier_loop(tmp_path, fleet={'travel_s': 3.0}) as (nodes, marks, log_dir):
        probe, generator = nodes['probe'], nodes['generator']
        wait_until(lambda: probe.named('DEPARTED', 1), TRIP_TIMEOUT_S, 'DEPARTED 가 나오지 않았다')
        probe.reset(2)
        wait_until(lambda: probe.named(Event.RESET_DONE, 2), 30.0, 'RESET_DONE(e2) 가 나오지 않았다')
        wait_results(generator, 1)
        time.sleep(1.0)
        nodes['logger'].close()

    runs = runs_by_epoch(log_dir)
    old, new = runs[1], runs[2]
    detail = f'\n{summary(old)}\n{summary(new)}'
    old_status = read_jsonl(old / 'order_status.jsonl')
    assert [s['reason'] for s in old_status if s['state'] == 'ABORT'] == ['reset_interrupted'], detail
    assert not [s for s in read_jsonl(new / 'order_status.jsonl') if s['request_id'] == 'r001-0001'], detail
    old_orders = {o['order_id']: o for o in read_jsonl(old / 'orders.jsonl')}
    assert old_orders['ord-0001']['reason'] == 'reset_interrupted', detail


def test_observation_before_reset_done_is_not_judged_in_the_new_run(tmp_path):
    """배달한 트립 뒤 느린 리셋. 씬 리셋 전까지 1 Hz 로 오는 이전 봉투 관측은 새 run 판정에 쓰이지 않아야 한다."""
    with barrier_loop(tmp_path) as (nodes, marks, log_dir):
        probe, generator, sim = nodes['probe'], nodes['generator'], nodes['sim']
        first = wait_results(generator, 1)
        sim.set_parameters(overrides({'reset_delay_s': SLOW_RESET_S}))
        probe.reset(2)
        wait_until(lambda: probe.named(Event.RESET_DONE, 2), 30.0, 'RESET_DONE(e2) 가 나오지 않았다')
        sim.set_parameters(overrides({'reset_delay_s': 0.0}))
        second = wait_results(generator, 2)
        time.sleep(1.5)
        nodes['logger'].close()

    runs = runs_by_epoch(log_dir)
    new = runs[2]
    detail = f'\n{summary(runs[1])}\n{summary(new)}\n  cabinet={read_jsonl(new / "cabinet.jsonl")}'
    assert first[1].success and second[1].success, detail
    cabinet = read_jsonl(new / 'cabinet.jsonl')
    pre_reset = [row for row in cabinet if row.get('pre_reset')]
    assert pre_reset, f'RESET_DONE 전 관측이 새 run 에 pre_reset 으로 남지 않았다{detail}'
    assert not [row for row in pre_reset if row.get('used')], f'RESET_DONE 전 관측이 새 run 판정에 쓰였다{detail}'
    meta = json.loads((new / 'meta.json').read_text(encoding='utf-8'))
    assert meta['counts']['pre_reset'] == len(pre_reset), detail
    orders = read_jsonl(new / 'orders.jsonl')
    assert [(o['request_id'], o['state']) for o in orders] == [('r002-0001', 'SUCCESS')], detail


# pharmacy_only 세 바퀴 ------------------------------------------------------

def load_aggregator():
    path = REPO / 'tools' / 'aggregate_runs.py'
    assert path.is_file(), f'{path} 가 없다. 저장소 전체 checkout 에서 돌려야 한다'
    spec = importlib.util.spec_from_file_location('aggregate_runs', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_pharmacy_reset_three_laps(tmp_path):
    aggregator = load_aggregator()
    with barrier_loop(tmp_path, orchestrator={'pharmacy_only': True}) as (nodes, marks, log_dir):
        probe, generator = nodes['probe'], nodes['generator']
        wait_results(generator, 1)                  # 기동 직후 epoch 1 트립(시행 아님)
        for lap, epoch in enumerate((2, 3, 4), start=2):
            probe.reset(epoch)
            wait_until(lambda epoch=epoch: probe.named(Event.RESET_DONE, epoch), 30.0, f'RESET_DONE(e{epoch}) 가 없다')
            wait_results(generator, lap)
        time.sleep(1.0)
        nodes['logger'].close()
        results = list(generator.results)

    runs = runs_by_epoch(log_dir)
    assert set(runs) == {1, 2, 3, 4}, f'run epoch 가 {sorted(runs)} 다'
    for epoch in (2, 3, 4):
        run = runs[epoch]
        detail = f'\n{summary(run)}'
        events = read_jsonl(run / 'events.jsonl')
        meta = json.loads((run / 'meta.json').read_text(encoding='utf-8'))
        assert events[0]['name'] == 'RESET_BEGIN', detail
        assert [e['name'] for e in events].count('RESET_DONE') == 1, detail
        assert all(e['epoch'] == epoch for e in events), f'run 에 다른 epoch 이벤트가 있다{detail}'
        assert meta['counts']['stale'] == 0, detail
        accepted = [e['request_id'] for e in events if e['name'] == 'REQUEST_ACCEPTED']
        assert accepted == [f'r{epoch:03d}-0001'], f'첫 요청이 수락되지 않았다(거부로 버려진 요청): {accepted}{detail}'
        assert not [s for s in read_jsonl(run / 'order_status.jsonl') if s['reason'] == 'reset_interrupted'], detail
        result = aggregator.aggregate(run, PROTOCOL)
        lap_success = next(m for m in result['metrics'] if m['name'] == 'lap_success')
        assert result['status'] == 'trial' and lap_success['value'] == 1, f'집계기: {result}{detail}'
    assert [r[1].success for r in results] == [False] * 4, 'pharmacy_only 트립의 Deliver 결과는 success=false 다'


# 리셋 실패 주입 --------------------------------------------------------------

FAILURES = {
    'fail': {'reset_fail': True},
    'hang': {'reset_delay_s': HANG_S},
}


@pytest.mark.parametrize('failure', list(FAILURES))
def test_reset_failure_stops_and_a_new_reset_recovers(tmp_path, failure):
    with barrier_loop(tmp_path, orchestrator={'reset_timeout_s': RESET_TIMEOUT_S}) as (nodes, marks, log_dir):
        probe, generator, sim = nodes['probe'], nodes['generator'], nodes['sim']
        wait_results(generator, 1)
        sim.set_parameters(overrides(FAILURES[failure]))
        probe.reset(2)
        wait_until(lambda: probe.named(Event.RESET_BEGIN, 2), 5.0, 'RESET_BEGIN(e2) 가 없다')
        time.sleep(HANG_S + 1.0)                    # 시한(2 s)과 늦은 ok(4 s)가 모두 지나도록
        assert not probe.named(Event.RESET_DONE, 2), '리셋 실패인데 RESET_DONE(e2) 가 나왔다'
        assert nodes['orchestrator']._fsm.barrier_failed, 'orchestrator 가 리셋 실패 상태가 아니다'
        assert not probe.deliver_accepted('r002-9001'), '리셋 실패로 멈췄는데 Deliver goal 이 수락됐다'
        assert len(generator.results) == 1, '리셋 실패 중에 트립이 돌았다'

        sim.set_parameters(overrides({'reset_fail': False, 'reset_delay_s': 0.0}))
        probe.reset(3)
        wait_until(lambda: probe.named(Event.RESET_DONE, 3), 10.0, '새 리셋의 RESET_DONE(e3) 가 없다')
        second = wait_results(generator, 2)
        time.sleep(1.5)
        nodes['logger'].close()
        sim_resets = marks.of('sim_reset_called')

    runs = runs_by_epoch(log_dir)
    assert set(runs) == {1, 2, 3}, f'run epoch 가 {sorted(runs)} 다'
    failed_events = [e['name'] for e in read_jsonl(runs[2] / 'events.jsonl')]
    recovered = read_jsonl(runs[3] / 'events.jsonl')
    detail = f'\n{summary(runs[2])}\n{summary(runs[3])}'
    assert failed_events == ['RESET_BEGIN'], f'실패한 barrier 의 run 은 RESET_BEGIN 뿐이어야 한다{detail}'
    assert not [o for o in read_jsonl(runs[2] / 'orders.jsonl') if o['state'] == 'SUCCESS'], \
        f'트립이 없는 실패 epoch run 에 관측만으로 SUCCESS 가 생겼다{detail}'
    assert recovered[0]['name'] == 'RESET_BEGIN' and 'RESET_DONE' in [e['name'] for e in recovered], detail
    assert [e['request_id'] for e in recovered if e['name'] == 'REQUEST_ACCEPTED'] == ['r003-0001'], detail
    assert second[1].success, f'복구 뒤 트립이 성공하지 않았다{detail}'
    assert [row[2] for row in sim_resets] == [2, 3], f'/sim/reset 호출 epoch: {[row[2] for row in sim_resets]}'
