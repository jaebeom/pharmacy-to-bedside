"""L2. 팔이 Refill 을 돌리는 **도중에** `/orchestrator/check_container` 가 답하는가(되부름 교착 없음, 작전 9/23).

실물 orchestrator(pharmacy_db 켬) + 가짜 M0609 Refill 서버 한 프로세스, MultiThreadedExecutor.
- 재고 파일에서 drug-amox 두 슬롯을 0 으로 두면 orchestrator 가 기동하자마자 Refill 을 보낸다.
- 가짜 서버는 execute 콜백 안에서(= orchestrator 가 그 Refill 결과를 기다리는 중에) 만료 약통 cn-0106 을 묻는다.
- 응답이 2 s(팔의 시한, #521 과 같은 값) 안에 `expired` 로 와야 한다. 이어서 허용 약통 cn-0105 를 물어 `ok` 가 와야 한다
  (9/23 L3: 거부 뒤 허용에서 로그 등급 예외로 서비스가 죽었다). 그다음 Refill 을 success=false 로 닫는다.
"""

import threading
import time

import rclpy
from rclpy.action import ActionServer
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from rclpy.parameter import Parameter

from l2_teardown import assert_no_leftovers, teardown_nodes
from rokey_p3_interfaces.action import Refill
from rokey_p3_interfaces.srv import CheckContainer
from rokey_p3_orchestrator.orchestrator_node import OrchestratorNode

POOL = """version: 1
orders:
  - {order_id: ord-0001, patient_id: "1001", item_id: drug-amox, bed: bed_a1}
"""
# drug-amox 는 두 슬롯이 비어 기동 때 보충 요청이 선다. 로트는 카탈로그에 없어도 된다(현장 재고 파일과 같다).
DISPENSER = """version: 1
refill_threshold: 1
items:
  drug-amox:
    - {slot: a, lot_id: lot-l2-a, expiry: "2027-03-31", count: 0}
    - {slot: b, lot_id: lot-l2-b, expiry: "2027-09-30", count: 0}
  drug-ibu:
    - {slot: a, lot_id: lot-ibu-01, expiry: "2027-05-31", count: 5}
    - {slot: b, lot_id: lot-ibu-02, expiry: "2027-11-30", count: 5}
shelf:
  drug-amox:
    - {lot_id: lot-l2-s, expiry: "2028-03-31", count: 5}
"""
CHECK_LIMIT_S = 2.0


class FakeM0609(Node):
    """Refill 서버. execute 안에서 약통을 묻고, 답을 적은 뒤 실패로 닫는다."""

    def __init__(self):
        super().__init__('fake_m0609')
        group = ReentrantCallbackGroup()
        self.answers = []                 # (allowed, reason, 걸린 wall 초)
        self.check = self.create_client(CheckContainer, '/orchestrator/check_container', callback_group=group)
        ActionServer(self, Refill, '/m0609/refill', execute_callback=self._execute, callback_group=group)

    def _ask(self, container_id, cell_id):
        request = CheckContainer.Request(container_id=container_id, robot_id='m0609', cell_id=cell_id, epoch=1)
        started = time.monotonic()
        future = self.check.call_async(request)
        done = threading.Event()
        future.add_done_callback(lambda _f: done.set())
        if done.wait(CHECK_LIMIT_S):
            answer = future.result()
            self.answers.append((answer.allowed, answer.reason, time.monotonic() - started))
        else:
            self.answers.append((None, 'timeout', time.monotonic() - started))

    def _execute(self, goal_handle):
        if self.check.wait_for_service(timeout_sec=5.0):
            self._ask('cn-0106', 'floor_right/r0c1')
            self._ask('cn-0105', 'floor_right/r0c0')
        else:
            self.answers.append((None, 'no_service', 0.0))
        goal_handle.abort()
        return Refill.Result(success=False, lot_id='cn-0106')


def test_check_container_answers_while_the_refill_goal_is_running(tmp_path):
    pool = tmp_path / 'order_pool.yaml'
    pool.write_text(POOL, encoding='utf-8')
    dispenser = tmp_path / 'dispenser.yaml'
    dispenser.write_text(DISPENSER, encoding='utf-8')

    assert_no_leftovers()
    rclpy.init(args=['test_container_check_loop'])
    executor = MultiThreadedExecutor(num_threads=8)
    nodes, thread = [], None
    try:
        nodes.append(OrchestratorNode(parameter_overrides=[
            Parameter('order_pool_file', value=str(pool)),
            Parameter('dispenser_file', value=str(dispenser)),
            Parameter('pharmacy_db', value=True)]))
        fake = FakeM0609()
        nodes.append(fake)
        for node in nodes:
            executor.add_node(node)
        thread = threading.Thread(target=executor.spin, daemon=True)
        thread.start()
        deadline = time.monotonic() + 30.0
        while len(fake.answers) < 2 and time.monotonic() < deadline:
            time.sleep(0.05)
        assert fake.answers, 'Refill 이 오지 않았다(보충 요청이 안 섰거나 서버를 못 찾았다)'
        assert [(allowed, reason) for allowed, reason, _ in fake.answers[:2]] == [
            (False, 'expired'), (True, 'ok')], fake.answers
        assert all(elapsed < CHECK_LIMIT_S for _, _, elapsed in fake.answers[:2])
    finally:
        teardown_nodes(executor, thread, nodes)
