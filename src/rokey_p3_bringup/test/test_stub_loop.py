"""L2. 스텁 한 바퀴. 계약 8절의 v0.2.0 판정을 그대로 검사한다.

요청 1건이 Deliver 결과 success=true 로 끝나고, event_logger 가 스텁 sim 의
/evaluator/cabinet 관측으로 run 기록에 SUCCESS 를 쓰고, /events 순서가 계약 2.6절과 같다.

launch 대신 한 프로세스 안에서 노드 일곱을 띄운다. 오가는 것은 진짜 액션·서비스·토픽이다.
launch 조합 자체는 test_skeleton.py 가 따로 본다.
"""

import importlib.util
import json
import threading
import time

import pytest

# 모듈 수준 importorskip 을 쓰지 않는다. #258 첫 CI(pytest + launch_testing 플러그인)에서 모듈 수준 Skipped 가
# 패키지 시험 전체로 번져 "collected 0 items / 1 skipped" 인 초록이 났다(추정, 로컬 재현 안 됨).
# skipif 는 이 파일의 시험만 하나씩 skip 으로 센다. ROS 가 있는 CI 에서는 둘 다 돈다.
RCLPY_MISSING = importlib.util.find_spec('rclpy') is None
pytestmark = pytest.mark.skipif(RCLPY_MISSING, reason='rclpy 없음(ROS 환경 밖) — L2 스텁 한 바퀴 미실행')

if not RCLPY_MISSING:
    import rclpy
    from l2_discovery import ReadyWatch, wait_for_discovery
    from l2_teardown import assert_no_leftovers, teardown_nodes

# 계약 2.6절 1인 배송 SUCCESS 한 바퀴. ARRIVING 은 긴급만이라 여기 없다.
CONTRACT_ORDER = [
    'REQUEST_ACCEPTED', 'AMR_DOCKED_LOAD', 'DISPENSED', 'POUCH_AT_END',
    'PICK_ATTEMPT', 'POUCH_PICKED', 'POUCH_LOADED', 'LOAD_DONE', 'ARM_HOME',
    'DEPARTED', 'ARRIVED', 'AUTH_OK', 'POUCH_DETECTED',
    'PICK_ATTEMPT', 'POUCH_PICKED', 'POUCH_PLACED', 'CABINET_LOCKED', 'ORDER_DONE',
    'ARM_HOME', 'RETURNED', 'DOCKED',
]

POOL = """version: 1
orders:
  - {order_id: ord-0001, patient_id: "1001", item_id: drug-amox, bed: bed_a1}
"""

LAP_TIMEOUT_S = 90.0


def overrides(values):
    from rclpy.parameter import Parameter
    return [Parameter(name, value=value) for name, value in values.items()]


def build_nodes(pool_path, log_dir):
    from rokey_p3_bringup.stubs.stub_arm import StubArm
    from rokey_p3_bringup.stubs.stub_detector import StubDetector
    from rokey_p3_bringup.stubs.stub_fleet import StubFleet
    from rokey_p3_bringup.stubs.stub_sim import StubSim
    from rokey_p3_orchestrator.event_logger_node import EventLoggerNode
    from rokey_p3_orchestrator.order_generator_node import OrderGeneratorNode
    from rokey_p3_orchestrator.orchestrator_node import OrchestratorNode

    pool = {'order_pool_file': pool_path}
    return {
        'sim': StubSim(parameter_overrides=overrides({**pool, 'belt_travel_s': 0.3})),
        'fleet': StubFleet(parameter_overrides=overrides({'travel_s': 0.3})),
        'arm': StubArm(parameter_overrides=overrides({**pool, 'motion_s': 0.1, 'home_s': 0.1})),
        'detector': StubDetector(parameter_overrides=overrides(pool)),
        'orchestrator': OrchestratorNode(parameter_overrides=overrides(pool)),
        'logger': EventLoggerNode(parameter_overrides=overrides({'log_dir': log_dir})),
        'generator': OrderGeneratorNode(parameter_overrides=overrides(
            {**pool, 'max_requests': 1, 'start_delay_s': 1.0, 'gap_s': 0.2})),
    }


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line]


@pytest.fixture(name='lap')
def run_one_lap(tmp_path):
    """스텁 한 바퀴를 돌리고 run 기록 디렉토리를 돌려준다."""
    from rclpy.executors import MultiThreadedExecutor

    pool_path = tmp_path / 'order_pool.yaml'
    pool_path.write_text(POOL, encoding='utf-8')
    log_dir = tmp_path / 'runs'

    assert_no_leftovers()
    rclpy.init()
    nodes = None
    thread = None
    executor = MultiThreadedExecutor(num_threads=16)
    try:
        nodes = build_nodes(str(pool_path), str(log_dir))
        for node in nodes.values():
            executor.add_node(node)
        thread = threading.Thread(target=executor.spin, daemon=True)
        thread.start()
        discovery_s = wait_for_discovery(nodes)   # 발견 실패는 트립 시한(90 s) 전에 원인을 밝히고 실패한다

        generator = nodes['generator']
        watch = ReadyWatch(generator, observer=nodes['logger'])
        deadline = time.monotonic() + LAP_TIMEOUT_S
        while time.monotonic() < deadline and generator.last_result is None:
            watch.sample_from_test_thread()
            time.sleep(0.05)
        result = generator.last_result
        diagnosis = watch.report(discovery_s) if result is None else ''
        watch.stop()
        time.sleep(1.5)                 # 평가 관측(1 Hz)이 한 번 더 올 시간
        nodes['logger'].close()
    finally:
        teardown_nodes(executor, thread, list((nodes or {}).values()))

    assert result is not None, f'{LAP_TIMEOUT_S} s 안에 Deliver 결과가 오지 않았다\n{diagnosis}'
    runs = sorted(log_dir.iterdir())
    assert len(runs) == 1, f'run 디렉토리가 하나여야 한다. {runs}'
    return {'result': result, 'run': runs[0]}


def test_deliver_result_is_success(lap):
    result = lap['result']
    assert result.success
    assert [order.order_id for order in result.orders] == ['ord-0001']
    assert result.orders[0].state == 2      # OrderStatus.STATE_DELIVERED, 주장이다


def test_event_order_matches_the_contract(lap):
    events = read_jsonl(lap['run'] / 'events.jsonl')
    assert [event['name'] for event in events] == CONTRACT_ORDER
    assert not any(event['stale'] for event in events)
    assert {event['epoch'] for event in events} == {1}


def test_run_record_writes_success_from_the_evaluator_observation(lap):
    orders = read_jsonl(lap['run'] / 'orders.jsonl')
    assert len(orders) == 1
    assert orders[0]['order_id'] == 'ord-0001'
    assert orders[0]['claim'] == 'DELIVERED'
    assert orders[0]['observed']
    assert orders[0]['cabinet_id'] == 'bed_a1/cabinet'
    assert orders[0]['state'] == 'SUCCESS'


def test_cabinet_observation_is_recorded(lap):
    cabinet = read_jsonl(lap['run'] / 'cabinet.jsonl')
    assert cabinet, '/evaluator/cabinet 관측이 하나도 없다'
    assert all(row['order_id'] == 'ord-0001' and row['present'] for row in cabinet)
