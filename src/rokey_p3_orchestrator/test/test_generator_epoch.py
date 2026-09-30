"""order_generator 가 이전 epoch 요청의 결과를 새 epoch 의 보낸 수로 세지 않는지. ROS 없이 돈다.

관측(마클, master02 네이티브, main fd13a46): 트립 도중 /orchestrator/reset →
"epoch 5 -> 6. 요청 큐를 다시 채운다." → 0.7 ms 뒤 "Deliver 결과 success=False [ord-0002=ABORT]" →
"max_requests=1 만큼 보냈다. 더 안 보낸다." → 61 s 동안 r006 없음. 집계기는 epoch 6 을 trial_without_start.
끊긴 r005 의 abort 결과가 epoch 상승 뒤에 도착해 새 epoch 의 1건으로 세어졌다.

order_generator_node 의 콜백 메서드를 빌린 Harness 에 가짜 액션 클라이언트·시계를 붙인다.
"""

import importlib
import sys
import types

import pytest
import test_server_wait as sw

from rokey_p3_orchestrator import order_pool
from rokey_p3_orchestrator.request_pacer import RequestPacer

MODULE = 'rokey_p3_orchestrator.order_generator_node'
POOL = {'orders': [
    {'order_id': 'ord-0001', 'patient_id': '1001', 'item_id': 'drug-amox', 'bed': 'bed_a1'},
    {'order_id': 'ord-0002', 'patient_id': '1002', 'item_id': 'drug-ibu', 'bed': 'bed_a2', 'mode': 'urgent'},
]}


@pytest.fixture(scope='module')
def gen():
    fakes = sw._fake_modules()
    added = [name for name in fakes if name not in sys.modules]
    for name in added:
        sys.modules[name] = fakes[name]
    try:
        yield importlib.import_module(MODULE)
    finally:
        sys.modules.pop(MODULE, None)
        if added:
            for name in added + ['rokey_p3_orchestrator.ros_qos']:
                sys.modules.pop(name, None)


class _Future:
    def __init__(self):
        self._callbacks = []

    def add_done_callback(self, callback):
        self._callbacks.append(callback)

    def resolve(self, value):
        for callback in self._callbacks:
            callback(types.SimpleNamespace(result=lambda value=value: value))


class _Client:
    def __init__(self):
        self.sent = []           # (request_id, 수락 응답 future)

    def server_is_ready(self):
        return True

    def send_goal_async(self, goal):
        future = _Future()
        self.sent.append((goal.request.request_id, future))
        return future


class _Logger:
    def __init__(self):
        self.lines = []

    def info(self, text, **kwargs):
        self.lines.append(text)

    warning = error = info


def harness(gen, monkeypatch, max_requests=1, settle_s=3.5):
    borrowed = ('_on_event', '_tick', '_announce_drained', '_on_goal_response', '_on_result', '_release')
    node = type('Harness', (), {name: getattr(gen.OrderGeneratorNode, name) for name in borrowed})()
    clock = types.SimpleNamespace(now=0.0)
    monkeypatch.setattr(gen, 'time', types.SimpleNamespace(monotonic=lambda: clock.now))
    node.clock = clock
    node._max_requests = max_requests
    node._ready_at = 0.0
    node._pacer = RequestPacer(order_pool.build_requests(order_pool.load_pool(POOL)), settle_s=settle_s)
    node._sent = 0
    node._active = None
    node._drained = False
    node.last_result = None
    node._client = _Client()
    node.logger = _Logger()
    node.get_logger = lambda: node.logger
    node._build_goal = lambda request_id, pending: types.SimpleNamespace(
        request=types.SimpleNamespace(request_id=request_id))
    return node


def event(name, epoch):
    return types.SimpleNamespace(name=name, epoch=epoch)


def sent_ids(node):
    return [request_id for request_id, _ in node._client.sent]


def accept(node, index):
    """index 번째로 보낸 goal 을 수락하고, 그 결과 future 를 돌려준다."""
    handle = types.SimpleNamespace(accepted=True, result_future=_Future())
    handle.get_result_async = lambda: handle.result_future
    node._client.sent[index][1].resolve(handle)
    return handle.result_future


def finish(result_future, success):
    order = types.SimpleNamespace(order_id='ord-0002', state=0)
    result_future.resolve(types.SimpleNamespace(result=types.SimpleNamespace(success=success, orders=[order])))


def test_old_epoch_abort_after_the_raise_does_not_use_up_the_new_epoch(gen, monkeypatch):
    node = harness(gen, monkeypatch)
    node._tick()
    assert sent_ids(node) == ['r001-0001']
    trip = accept(node, 0)

    # 리셋: epoch 상승이 먼저 오고, 끊긴 r001 의 abort 결과가 그 뒤에 온다(마클 관측 순서).
    node.clock.now = 100.0
    node._on_event(event('RESET_BEGIN', 2))
    finish(trip, success=False)
    node._on_event(event('RESET_DONE', 2))

    node.clock.now = 103.4
    node._tick()
    assert sent_ids(node) == ['r001-0001']                     # settle 전
    assert not any('max_requests' in line for line in node.logger.lines)
    node.clock.now = 103.5
    node._tick()
    assert sent_ids(node) == ['r001-0001', 'r002-0001']        # 새 epoch 에서 settle 뒤 1건

    # 새 epoch 자기 결과는 센다. max_requests=1 이면 더 안 보낸다.
    finish(accept(node, 1), success=True)
    node.clock.now = 110.0
    node._tick()
    assert sent_ids(node) == ['r001-0001', 'r002-0001']
    assert any('max_requests=1' in line for line in node.logger.lines)


def test_other_arrival_orders_of_the_old_request_leave_one_send_for_the_new_epoch(gen, monkeypatch):
    # 결과가 epoch 상승보다 먼저 와도(반대 순서) 새 epoch 는 1건을 보낸다.
    node = harness(gen, monkeypatch)
    node._tick()
    finish(accept(node, 0), success=False)
    node.clock.now = 100.0
    node._on_event(event('RESET_BEGIN', 2))
    node._on_event(event('RESET_DONE', 2))
    node.clock.now = 103.5
    node._tick()
    assert sent_ids(node) == ['r001-0001', 'r002-0001']

    # 수락 응답 전에 epoch 가 오르고 이전 요청이 거부돼도 새 epoch 의 대기·보낸 수를 안 바꾼다.
    node = harness(gen, monkeypatch)
    node._tick()
    node.clock.now = 100.0
    node._on_event(event('RESET_BEGIN', 2))
    node._client.sent[0][1].resolve(types.SimpleNamespace(accepted=False))
    node._tick()
    assert sent_ids(node) == ['r001-0001']                     # RESET_DONE 전
    node._on_event(event('RESET_DONE', 2))
    node.clock.now = 103.5
    node._tick()
    assert sent_ids(node) == ['r001-0001', 'r002-0001']

    # 보낸 뒤 epoch 가 오르고 수락 응답·abort 결과가 그 뒤에 와도, 보낸 때의 epoch 로 본다.
    node = harness(gen, monkeypatch)
    node._tick()
    node.clock.now = 100.0
    node._on_event(event('RESET_BEGIN', 2))
    finish(accept(node, 0), success=False)
    node._on_event(event('RESET_DONE', 2))
    node.clock.now = 103.5
    node._tick()
    assert sent_ids(node) == ['r001-0001', 'r002-0001']
