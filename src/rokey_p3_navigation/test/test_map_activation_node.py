"""L1: map_activation_guard 노드를 가짜 rclpy·lifecycle_msgs 로 **실제로 돌린다**.

마1검증 #743 5854403546: 3766b47 은 기동 시각 속성 `self._start` 와 새 메서드 `_start()` 이름이 겹쳐 첫 틱에
`TypeError: 'float' object is not callable` 로 죽었다. 소스 문자열만 보던 시험은 못 잡았다. 그래서 노드를 돌린다.
"""

import importlib
import json
import sys
import types

import pytest

from rokey_p3_navigation import map_activation as M


class _Future:
    def __init__(self):
        self._callbacks, self._result, self._cancelled = [], None, False

    def add_done_callback(self, callback):
        self._callbacks.append(callback)

    def cancel(self):
        self._cancelled = True

    def cancelled(self):
        return self._cancelled

    def result(self):
        return self._result

    def finish(self, result):
        self._result = result
        for callback in self._callbacks:
            callback(self)


class _Client:
    def __init__(self):
        self.calls = []

    def service_is_ready(self):
        return True

    def call_async(self, request):
        future = _Future()
        self.calls.append((request, future))
        return future


class _Timer:
    def __init__(self):
        self.cancelled = False

    def cancel(self):
        self.cancelled = True


class _Logger:
    def __init__(self):
        self.lines = []

    def info(self, text):
        self.lines.append(('info', text))

    def warn(self, text):
        self.lines.append(('warn', text))

    def error(self, text):
        self.lines.append(('error', text))


class _Publisher:
    def __init__(self):
        self.sent = []

    def publish(self, msg):
        self.sent.append(json.loads(msg.data))


class _Node:
    def __init__(self, name):
        self.log = _Logger()
        self.clients = {}
        self.publishers = {}
        self.timer = None

    def create_publisher(self, _type, topic, _qos):
        self.publishers[topic] = _Publisher()
        return self.publishers[topic]

    def get_clock(self):
        return types.SimpleNamespace(now=lambda: types.SimpleNamespace(nanoseconds=42_500_000_000))

    def get_namespace(self):
        return '/amr_1'

    def declare_parameter(self, name, default):
        return types.SimpleNamespace(value=default)

    def create_client(self, _type, name):
        self.clients[name.rsplit('/', 1)[-1]] = _Client()
        return self.clients[name.rsplit('/', 1)[-1]]

    def create_timer(self, _period, callback):
        self.tick = callback
        self.timer = _Timer()
        return self.timer

    def get_logger(self):
        return self.log

    def resolve_topic_name(self, name):
        return f'/amr_1/{name}'


@pytest.fixture
def guard_module(monkeypatch):
    rclpy = types.ModuleType('rclpy')
    rclpy_node = types.ModuleType('rclpy.node')
    rclpy_node.Node = _Node
    rclpy.node = rclpy_node
    msg = types.ModuleType('lifecycle_msgs.msg')
    msg.Transition = lambda id: types.SimpleNamespace(id=id)                  # noqa: A006
    srv = types.ModuleType('lifecycle_msgs.srv')
    srv.GetState = types.SimpleNamespace(Request=lambda: 'get_state')
    srv.ChangeState = types.SimpleNamespace(Request=lambda: types.SimpleNamespace(transition=None))
    lifecycle = types.ModuleType('lifecycle_msgs')
    qos = types.ModuleType('rclpy.qos')
    qos.QoSProfile = lambda **kw: kw
    qos.DurabilityPolicy = qos.HistoryPolicy = qos.ReliabilityPolicy = types.SimpleNamespace(
        RELIABLE='reliable', TRANSIENT_LOCAL='transient_local', KEEP_LAST='keep_last')
    std_msgs = types.ModuleType('std_msgs')
    std_msgs_msg = types.ModuleType('std_msgs.msg')
    std_msgs_msg.String = lambda: types.SimpleNamespace(data=None)
    for name, module in (('rclpy', rclpy), ('rclpy.node', rclpy_node), ('lifecycle_msgs', lifecycle),
                         ('lifecycle_msgs.msg', msg), ('lifecycle_msgs.srv', srv), ('rclpy.qos', qos),
                         ('std_msgs', std_msgs), ('std_msgs.msg', std_msgs_msg)):
        monkeypatch.setitem(sys.modules, name, module)
    sys.modules.pop('rokey_p3_navigation.map_activation_guard_node', None)
    module = importlib.import_module('rokey_p3_navigation.map_activation_guard_node')
    clock = {'now': 0.0}
    monkeypatch.setattr(module.time, 'monotonic', lambda: clock['now'])
    yield module, clock
    sys.modules.pop('rokey_p3_navigation.map_activation_guard_node', None)


def _state(state_id):
    return types.SimpleNamespace(current_state=types.SimpleNamespace(id=state_id))


def test_a_healthy_bringup_reads_active_once_and_stops(guard_module):
    module, clock = guard_module
    node = module.MapActivationGuard()
    clock['now'] = 1.0
    node.tick()                                                  # 3766b47 은 여기서 TypeError 로 죽었다
    [(_request, future)] = node.clients['get_state'].calls
    future.finish(_state(M.ACTIVE))
    assert node.timer.cancelled
    assert any('개입 없음' in text for level, text in node.get_logger().lines if level == 'info')
    assert node.clients['change_state'].calls == []
    assert node.publishers['/p3/alerts'].sent == []              # 정상 기동은 알림 없음


def test_a_lost_reply_is_dropped_then_the_guard_activates_map_server(guard_module):
    module, clock = guard_module
    node = module.MapActivationGuard()
    clock['now'] = M.WAIT_S + 1.0
    node.tick()
    [(_r, lost)] = node.clients['get_state'].calls                # 응답이 안 온다
    clock['now'] += M.PENDING_TIMEOUT_S
    node.tick()                                                  # 시한 → 버리고 곧바로 다시 조회
    assert lost.cancelled()
    assert any('응답' in text for level, text in node.get_logger().lines if level == 'warn')
    assert len(node.clients['get_state'].calls) == 2
    lost.finish(_state(M.INACTIVE))                              # 늦은 옛 응답은 무시
    assert node.clients['change_state'].calls == []
    node.clients['get_state'].calls[1][1].finish(_state(M.INACTIVE))
    [(request, change)] = node.clients['change_state'].calls
    assert request.transition.id == M.ACTIVATE
    change.finish(types.SimpleNamespace(success=True))
    clock['now'] += 1.0
    node.tick()
    node.clients['get_state'].calls[2][1].finish(_state(M.ACTIVE))
    assert node.timer.cancelled
    assert any('직접 전이 1번 뒤' in text for _level, text in node.get_logger().lines)
    [alert] = node.publishers['/p3/alerts'].sent                 # 개입 한 번 = 알림 한 건
    assert (alert['kind'], alert['robot'], alert['sim']) == ('MAP_GUARD_INTERVENE', 'amr_1', 42.5)
    assert 'activate' in alert['detail']


def test_giving_up_after_lost_replies_sends_one_giveup_alert(guard_module):
    module, clock = guard_module
    node = module.MapActivationGuard()
    for _ in range(M.MAX_TIMEOUTS):
        node.tick()
        clock['now'] += M.PENDING_TIMEOUT_S
    node.tick()
    assert node.timer.cancelled
    assert [a['kind'] for a in node.publishers['/p3/alerts'].sent] == ['MAP_GUARD_GIVEUP']
