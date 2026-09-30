"""L2 내림 도우미(l2_teardown)가 액션 서버·클라이언트를 없애고, 남은 것을 잡는지.

destroy_node 만 하면 액션 서버가 남는 것(9/18 #168 CI 원인)을 먼저 보이고, 그 테스트가 스스로 치운다.
실행 중 goal 이 있을 때: close() 로 빠져나오면 깨끗이 내려가고, close 를 무시하는 goal 은 다 내린 뒤 실패로 알린다
(9/18 외부 검토 #185 A3: 협력 종료·join 뒤 확인·실행 중 goal 을 가진 종료 테스트).
"""

import threading
import time
import uuid

import pytest
import rclpy
from rclpy.action import ActionClient, ActionServer
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node

from l2_teardown import assert_no_leftovers, leftover_action_entities, teardown_nodes
from rokey_p3_interfaces.action import Deliver


class ActionNode(Node):
    """execute 는 close() 가 불리거나 run_s 가 지나면 끝난다. honour_close=False 면 close 를 무시한다."""

    def __init__(self, name, run_s=0.0, honour_close=True):
        super().__init__('l2_teardown_probe')
        self._closing = threading.Event()
        self.run_s, self.honour_close = run_s, honour_close
        self.outcome = None
        self.server = ActionServer(self, Deliver, name, execute_callback=self._execute)
        self.client = ActionClient(self, Deliver, name)

    def _execute(self, goal_handle):
        deadline = time.monotonic() + self.run_s
        while time.monotonic() < deadline:
            if self.honour_close and self._closing.is_set():
                goal_handle.abort()
                self.outcome = 'abort'
                return Deliver.Result()
            time.sleep(0.02)
        goal_handle.succeed()
        self.outcome = 'succeed'
        return Deliver.Result()

    def close(self):
        self._closing.set()

    def send_and_wait_accepted(self):
        assert self.client.wait_for_server(timeout_sec=5.0)
        sent = self.client.send_goal_async(Deliver.Goal())
        deadline = time.monotonic() + 5.0
        while not sent.done() and time.monotonic() < deadline:
            time.sleep(0.02)
        assert sent.done() and sent.result().accepted


def start(**kwargs):
    assert_no_leftovers()
    rclpy.init()
    executor = MultiThreadedExecutor(num_threads=4)
    node = ActionNode(f'/l2_teardown_{uuid.uuid4().hex[:8]}', **kwargs)
    executor.add_node(node)
    thread = threading.Thread(target=executor.spin, daemon=True)
    thread.start()
    return executor, thread, node


def test_destroy_node_alone_leaves_the_action_entities_and_the_check_names_them():
    executor, thread, node = start()
    server, client = node.server, node.client
    executor.shutdown()
    thread.join(timeout=5.0)
    node.destroy_node()                                       # 전의 fixture 와 같은 내림
    rclpy.try_shutdown()
    try:
        leftovers = leftover_action_entities()
        with pytest.raises(AssertionError) as failure:
            assert_no_leftovers()
    finally:
        server.destroy()                                      # 뒤 테스트를 위해 스스로 치운다
        client.destroy()
    assert leftovers == ['ActionNode: ActionClient /' + client._action_name.lstrip('/'),
                         'ActionNode: ActionServer Deliver'], leftovers
    assert '앞 테스트가 내리지 않은 액션 서버·클라이언트' in str(failure.value)
    assert 'gc 전 [' in str(failure.value) and 'gc 뒤 [' in str(failure.value)
    assert leftover_action_entities() == []


def test_teardown_leaves_nothing():
    executor, thread, node = start()
    teardown_nodes(executor, thread, [node])
    assert leftover_action_entities() == []
    assert_no_leftovers()


def test_close_lets_a_running_goal_end_before_the_executor_stops():
    executor, thread, node = start(run_s=30.0)
    node.send_and_wait_accepted()
    started = time.monotonic()
    teardown_nodes(executor, thread, [node])
    assert node.outcome == 'abort'                           # close 로 빠져나왔다(30 s 를 다 돌지 않았다)
    assert time.monotonic() - started < 5.0
    assert not thread.is_alive()
    assert leftover_action_entities(collect=False) == []


def test_goal_that_ignores_close_fails_after_everything_is_torn_down():
    executor, thread, node = start(run_s=1.5, honour_close=False)
    node.send_and_wait_accepted()
    with pytest.raises(AssertionError) as failure:
        teardown_nodes(executor, thread, [node], goal_wait_s=0.3)
    assert '끝나지 않은 goal' in str(failure.value) and 'ActionNode: goal' in str(failure.value)
    assert node.outcome == 'succeed'                         # 작업 스레드 join 으로 그 callback 이 끝나기를 기다렸다
    assert not thread.is_alive()
    assert leftover_action_entities(collect=False) == []     # 실패로 알려도 정리는 다 했다
