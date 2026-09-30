"""M0609 잡기 직전 약통 확인의 노드 배선(계약 2.3). ROS 없이 돈다(test_reset_fence 의 노드 대역).

판독(`/m0609/hand_camera/tag_reads`) → `/orchestrator/check_container` → 허용이면 계속, 아니면 닫지 않고 끝낸다.
"""

import threading
import types

import test_reset_fence as rf

from rokey_p3_manipulation import container_gate as gate

nodes = rf.nodes
KIND_CONTAINER = 3


class _Future:
    def __init__(self, response):
        self._response = response

    def add_done_callback(self, callback):
        if self._response is not None:
            callback(self)

    def result(self):
        return self._response


class _Client:
    """서비스 대역. answer 가 None 이면 답하지 않는다(시한 초과)."""

    def __init__(self, answer, available=True):
        self.answer, self.available, self.requests = answer, available, []

    def wait_for_service(self, timeout_sec=None):
        return self.available

    def call_async(self, request):
        self.requests.append(request)
        if self.answer is None:
            return _Future(None)
        return _Future(types.SimpleNamespace(allowed=self.answer[0], reason=self.answer[1]))


def harness(nodes, client, reads=(), epoch=1):
    _arm, m0609 = nodes
    cls = m0609.M0609ArmNode
    node = type('Harness', (), {name: getattr(cls, name) for name in ('_check_container',)})()
    node._lock = threading.RLock()
    node._epoch = epoch
    node._v2_done = {'cell': 'floor_right/r0c1'}
    node._container_reads = list(reads)
    node._container_read_timeout = 0.2
    node._container_check_timeout = 0.2
    node._refused_cells = gate.RefusedCells()
    node._read_container = ''
    node._check_client = client
    node.clock = 10.0
    node.sim_now = lambda: node.clock
    node.warnings = []
    node.get_logger = lambda: types.SimpleNamespace(info=lambda *_: None, warn=node.warnings.append)

    def wait(seconds, cancelled=None):
        node.clock += seconds
        return True

    node.wait = wait
    node._stopped = lambda handle, deadline, detail: (m0609.STATUS_FAILED, detail, '')
    return node, m0609


def check(node):
    return node._check_container(types.SimpleNamespace(), 100.0, lambda: False)


def test_allowed_canister_continues_and_is_remembered_for_the_result(nodes):
    client = _Client((True, 'ok'))
    node, _ = harness(nodes, client, reads=[gate.Read(10.1, 'cn-0105')])
    assert check(node) is None
    assert node._read_container == 'cn-0105'
    [request] = client.requests
    assert (request.container_id, request.robot_id, request.cell_id, request.epoch) == (
        'cn-0105', 'm0609', 'floor_right/r0c1', 1)


def test_expired_canister_ends_without_grasping_and_the_cell_is_skipped_this_epoch(nodes):
    node, m0609 = harness(nodes, _Client((False, 'expired')), reads=[gate.Read(10.1, 'cn-0106')])
    status, detail, lot = check(node)
    assert status == m0609.STATUS_FAILED and 'reason=expired' in detail and lot == 'cn-0106'
    assert node._refused_cells.of(1) == ['floor_right/r0c1']
    assert node._refused_cells.of(2) == []


def test_old_read_from_before_arrival_is_not_used(nodes):
    client = _Client((True, 'ok'))
    node, m0609 = harness(nodes, client, reads=[gate.Read(9.0, 'cn-0105')])
    status, detail, _ = check(node)
    assert status == m0609.STATUS_FAILED and 'reason=unreadable' in detail
    assert client.requests == []                         # 못 읽었으면 묻지 않는다


def test_no_answer_in_time_is_a_refusal(nodes):
    node, m0609 = harness(nodes, _Client(None), reads=[gate.Read(10.1, 'cn-0105')])
    status, detail, _ = check(node)
    assert status == m0609.STATUS_FAILED and 'reason=check_timeout' in detail


def test_missing_service_is_a_refusal(nodes):
    node, m0609 = harness(nodes, _Client((True, 'ok'), available=False), reads=[gate.Read(10.1, 'cn-0105')])
    status, detail, _ = check(node)
    assert status == m0609.STATUS_FAILED and 'reason=check_timeout' in detail


def test_every_check_logs_latency_and_read_count_in_the_vision_format(nodes):
    """재범 9/25 점수판 AI 비전: 봉투 `vision pouch` 줄과 같은 형식의 한 줄 — 결과·지연(ms)·도착 뒤 판독 수."""
    node, _ = harness(nodes, _Client((True, 'ok')),
                      reads=[gate.Read(9.5, 'cn-0105'), gate.Read(10.1, 'cn-0105'), gate.Read(10.2, 'cn-0105')])
    infos = []
    node.get_logger = lambda: types.SimpleNamespace(info=infos.append, warn=node.warnings.append)
    assert check(node) is None
    line = next(text for text in infos if text.startswith('vision container'))
    assert line.startswith('vision container cn-0105: ok 지연 ')
    assert '판독 2건(도착 뒤)' in line                            # 9.5 는 도착(10.0) 전이라 세지 않는다
