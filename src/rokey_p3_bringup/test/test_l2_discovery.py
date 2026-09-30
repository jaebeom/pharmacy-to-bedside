"""L2 발견 확인 도우미(l2_discovery)가 서버가 없을 때 시한 안에 원인을 싣고 실패하는지.

colcon test 는 패키지 테스트를 동시에 돌려 같은 DDS 도메인에 다른 패키지의 /deliver 서버가 있을 수 있다.
그래서 이 테스트는 아무도 만들지 않는 이름의 액션으로 본다.
"""

import threading
import uuid

import pytest
import rclpy
from rclpy.action import ActionClient
from rclpy.executors import MultiThreadedExecutor

from l2_discovery import client_checks, missing_server_report, wait_for_discovery
from l2_teardown import assert_no_leftovers, teardown_nodes
from rokey_p3_interfaces.action import Deliver


def test_missing_server_fails_fast_with_the_graph():
    assert_no_leftovers()
    rclpy.init()
    executor = MultiThreadedExecutor(num_threads=4)
    node = rclpy.create_node('l2_discovery_probe')
    name = f'/l2_discovery_missing_{uuid.uuid4().hex[:8]}'
    client = ActionClient(node, Deliver, name)
    executor.add_node(node)
    thread = threading.Thread(target=executor.spin, daemon=True)
    thread.start()
    try:
        with pytest.raises(AssertionError) as failure:
            wait_for_discovery({'probe': node}, timeout_s=1.0, checks=[(f'probe → {name}', client.server_is_ready)])
    finally:
        teardown_nodes(executor, thread, [node])
    message = str(failure.value)
    assert '1 s 안에 발견되지 않았다' in message and name in message
    assert '노드 [' in message and '/l2_discovery_probe' in message


def test_ready_clients_return_immediately():
    assert wait_for_discovery({}, timeout_s=1.0, checks=[('항상 준비', lambda: True)]) < 0.5


def test_client_checks_cover_generator_and_orchestrator_clients():
    """노드 내부 속성 이름이 바뀌면 여기서 먼저 깨진다(ROS 그래프 없이 이름만 본다)."""
    class Stub:
        def __init__(self, **attrs):
            self.__dict__.update(attrs)

    ready = Stub(server_is_ready=lambda: True, service_is_ready=lambda: True)
    nodes = {'generator': Stub(_client=ready),
             'orchestrator': Stub(_action_clients={'go_to_zone': ready, 'pick_pouch': ready}, _dispense=ready,
                                  _sim_reset=ready)}
    labels = [label for label, _ in client_checks(nodes)]
    assert labels == ['order_generator → /deliver', 'orchestrator → go_to_zone 액션', 'orchestrator → pick_pouch 액션',
                      'orchestrator → /pharmacy/dispense', 'orchestrator → /sim/reset']


def test_ready_watch_reports_both_threads_and_the_graph():
    """두 스레드 표본, 같은 객체, /deliver 그래프·shm·그래프 덤프가 보고에 실린다.

    colcon 이 다른 패키지 테스트를 동시에 돌리면 같은 도메인에 /deliver 서버가 있을 수 있어 ready 값은 보지 않는다.
    """
    import time

    from rokey_p3_orchestrator.order_generator_node import OrderGeneratorNode
    from l2_discovery import ReadyWatch

    assert_no_leftovers()
    rclpy.init()
    executor = MultiThreadedExecutor(num_threads=4)
    generator = OrderGeneratorNode()
    executor.add_node(generator)
    thread = threading.Thread(target=executor.spin, daemon=True)
    thread.start()
    try:
        watch = ReadyWatch(generator)
        deadline = time.monotonic() + 2.5
        while time.monotonic() < deadline:
            watch.sample_from_test_thread()
            time.sleep(0.05)
        report = watch.report(0.0)
        watch.stop()
    finally:
        teardown_nodes(executor, thread, [generator])
    assert '같은 객체: True' in report
    assert 'executor: 표본 0' not in report and 'test: 표본 0' not in report, report   # 두 스레드 모두 적었다
    assert "'MainThread'" in report, report                                           # 테스트 스레드 이름
    assert '/orchestrator: 액션' in report and '/order_generator: 액션' in report, report
    assert '/deliver 그래프' in report and '/dev/shm fastrtps 세그먼트' in report, report


def test_missing_server_report_names_the_action_graph_and_shm():
    rclpy.init()
    node = rclpy.create_node('l2_discovery_report_probe')
    name = f'/l2_discovery_report_{uuid.uuid4().hex[:8]}'
    try:
        report = missing_server_report(node, name)
    finally:
        node.destroy_node()
        rclpy.try_shutdown()
    assert f'{name} 그래프(status pub, feedback pub, send_goal 서비스): (0, 0, False)' in report
    assert '노드 [' in report and '/dev/shm fastrtps 세그먼트 지금' in report and '앞선 L2' in report
