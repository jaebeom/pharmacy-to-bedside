"""L2. 스텁 한 바퀴 — 병동 묶음(mode 3) 스테이션 인증과, 스캔 실패 뒤 팔의 홈 복귀.

#576 v1(9/23, 병원 주문 풀 스텁 한 바퀴)에서 잡은 스텁 결함 둘을 고정한다.
① stub_detector 가 스테이션 정거장에서도 실린 주문의 환자 인식표(pt-)를 보여, stub_arm 이 기다리는
   st-station_a 를 못 읽고 병동 묶음이 늘 AUTH_FAIL 이었다.
② stub_arm 이 스캔 실패 뒤 홈 복귀를 예약하지 않아 arm/at_home 이 false 로 남았다. orchestrator 는
   복귀(도크로)를 영영 기다렸고, 리셋 뒤 다음 트립도 시한(600 s)까지 멈췄다.

묶음은 주문 풀만으로 못 만든다(order_pool.build_requests: 주문 하나 = 요청 하나). 그래서 발행기 대신
이 시험이 /deliver 에 goal 을 직접 보낸다. 나머지는 test_stub_loop.py 와 같은 조합이다.
"""

import importlib.util
import json
import threading
import time

import pytest

RCLPY_MISSING = importlib.util.find_spec('rclpy') is None
pytestmark = pytest.mark.skipif(RCLPY_MISSING, reason='rclpy 없음(ROS 환경 밖) — L2 스텁 한 바퀴 미실행')

if not RCLPY_MISSING:
    import rclpy
    from l2_discovery import client_checks, wait_for_discovery
    from l2_teardown import assert_no_leftovers, teardown_nodes

POOL = """version: 1
orders:
  - {order_id: ord-0001, patient_id: "1001", item_id: drug-amox, bed: bed_a1}
  - {order_id: ord-0002, patient_id: "1002", item_id: drug-ibu, bed: bed_b1}
"""
#: 인식표를 못 보게 하는 풀 — 검출기만 이것을 읽는다. 요청의 주문이 없어서 보여 줄 인식표가 없다.
BLIND_POOL = """version: 1
orders:
  - {order_id: ord-0099, patient_id: "1099", item_id: drug-amox, bed: bed_a4}
"""

LAP_TIMEOUT_S = 90.0
START_DELAY_S = 1.0


def overrides(values):
    from rclpy.parameter import Parameter
    return [Parameter(name, value=value) for name, value in values.items()]


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line]


def run_lap(tmp_path, *, mode, destination_id, order_ids, detector_pool=POOL):
    """발행기 없이 스텁 한 바퀴를 돌리고 (Deliver 결과, run 기록의 이벤트 이름 목록) 을 돌려준다."""
    from rclpy.action import ActionClient
    from rclpy.executors import MultiThreadedExecutor
    from rclpy.node import Node

    from rokey_p3_bringup.stubs.stub_arm import StubArm
    from rokey_p3_bringup.stubs.stub_detector import StubDetector
    from rokey_p3_bringup.stubs.stub_fleet import StubFleet
    from rokey_p3_bringup.stubs.stub_sim import StubSim
    from rokey_p3_interfaces.action import Deliver
    from rokey_p3_interfaces.msg import Order
    from rokey_p3_orchestrator.event_logger_node import EventLoggerNode
    from rokey_p3_orchestrator.orchestrator_node import OrchestratorNode

    pool_path = tmp_path / 'order_pool.yaml'
    pool_path.write_text(POOL, encoding='utf-8')
    detector_path = tmp_path / 'detector_pool.yaml'
    detector_path.write_text(detector_pool, encoding='utf-8')
    log_dir = tmp_path / 'runs'
    pool = {'order_pool_file': str(pool_path)}
    patients = {'ord-0001': ('1001', 'drug-amox'), 'ord-0002': ('1002', 'drug-ibu')}

    assert_no_leftovers()
    rclpy.init()
    nodes = None
    thread = None
    executor = MultiThreadedExecutor(num_threads=16)
    try:
        nodes = {
            'sim': StubSim(parameter_overrides=overrides({**pool, 'belt_travel_s': 0.3})),
            'fleet': StubFleet(parameter_overrides=overrides({'travel_s': 0.3})),
            'arm': StubArm(parameter_overrides=overrides(
                {**pool, 'motion_s': 0.1, 'home_s': 0.1, 'tag_wait_s': 1.0})),
            'detector': StubDetector(parameter_overrides=overrides({'order_pool_file': str(detector_path)})),
            'orchestrator': OrchestratorNode(parameter_overrides=overrides(pool)),
            'logger': EventLoggerNode(parameter_overrides=overrides({'log_dir': str(log_dir)})),
            'client': Node('test_deliver_client'),
        }
        client = ActionClient(nodes['client'], Deliver, '/deliver')
        for node in nodes.values():
            executor.add_node(node)
        thread = threading.Thread(target=executor.spin, daemon=True)
        thread.start()
        wait_for_discovery(nodes, checks=[*client_checks(nodes), ('test → /deliver', client.server_is_ready)])
        time.sleep(START_DELAY_S)   # 발행기의 start_delay_s 자리 — 신호(arm/at_home·base/stopped)가 한 번은 와야 한다

        goal = Deliver.Goal()
        goal.request.request_id = 'l2-station'
        goal.request.mode = mode
        goal.request.destination_id = destination_id
        for order_id in order_ids:
            patient_id, item_id = patients[order_id]
            goal.request.orders.append(Order(order_id=order_id, patient_id=patient_id, item_id=item_id))
        sent = client.send_goal_async(goal)
        deadline = time.monotonic() + LAP_TIMEOUT_S
        while time.monotonic() < deadline and not sent.done():
            time.sleep(0.05)
        assert sent.done() and sent.result().accepted, 'orchestrator 가 goal 을 받지 않았다'
        result_future = sent.result().get_result_async()
        while time.monotonic() < deadline and not result_future.done():
            time.sleep(0.05)
        result = result_future.result().result if result_future.done() else None
        time.sleep(0.5)
        nodes['logger'].close()
    finally:
        teardown_nodes(executor, thread, list((nodes or {}).values()))

    runs = sorted(log_dir.iterdir()) if log_dir.exists() else []
    names = [event['name'] for event in read_jsonl(runs[0] / 'events.jsonl')] if runs else []
    assert result is not None, f'{LAP_TIMEOUT_S} s 안에 Deliver 결과가 오지 않았다. 이벤트: {names}'
    return result, names


def test_a_ward_batch_is_authenticated_at_the_station(tmp_path):
    """병동 묶음 — 두 병실의 주문을 스테이션 하나로. 스테이션 인식표를 읽어 둘 다 넣는다."""
    result, names = run_lap(tmp_path, mode=3, destination_id='station_a', order_ids=['ord-0001', 'ord-0002'])
    assert 'AUTH_FAIL' not in names, names
    assert names.count('AUTH_OK') == 1, names       # 정거장은 스테이션 하나다
    assert names.count('POUCH_PLACED') == 2, names
    assert result.success, [(o.order_id, o.state, o.reason) for o in result.orders]
    assert names[-1] == 'DOCKED', names


def test_a_failed_scan_sends_the_arm_home_and_the_amr_docks(tmp_path):
    """인식표를 못 읽으면 회수(HOLD_RETURN)다. 팔이 홈으로 돌아와야 AMR 이 도크로 간다."""
    result, names = run_lap(tmp_path, mode=0, destination_id='bed_a1', order_ids=['ord-0001'],
                            detector_pool=BLIND_POOL)
    assert 'AUTH_FAIL' in names, names
    after = names[names.index('AUTH_FAIL'):]
    assert 'ARM_HOME' in after and after[-1] == 'DOCKED', after
    assert [(o.order_id, o.reason) for o in result.orders] == [('ord-0001', 'tag_unreadable')]
    assert not result.success
