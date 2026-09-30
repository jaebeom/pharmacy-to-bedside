"""액션 서버·서비스가 아직 안 보일 때 거부로 세지 않고 기다리는지. ROS 없이 돈다.

앞 절은 ServerWait 표다. 뒤 절은 orchestrator_node 의 전송 메서드를 빌린 Harness 에 가짜 클라이언트를
붙여 배선을 본다. rclpy·인터페이스·navigation 이 없는 곳에서는 이 모듈 안에서만 대역을 넣고 끝나면 뺀다.
서버를 늦게 띄우는 실제 실행(L2)은 따로 본다.
"""

import importlib
import importlib.util
import sys
import threading
import types

import pytest

from rokey_p3_orchestrator import refill_planner as rp
from rokey_p3_orchestrator import trip_fsm as fsm

MODULE = 'rokey_p3_orchestrator.orchestrator_node'


class _StubType(type):
    """상수(대문자)는 문자열로, 중첩 타입(Goal·Request 등)은 또 다른 대역 타입으로 돌려준다."""

    def __getattr__(cls, name):
        if name.startswith('__'):
            raise AttributeError(name)
        if name.isupper():
            return f'{cls.__name__}.{name}'
        nested = _StubType(name, (), {'__init__': _stub_init})
        setattr(cls, name, nested)
        return nested


def _stub_init(self, **fields):
    self.__dict__.update(fields)


def _stub_module(name, **attrs):
    module = types.ModuleType(name)
    module.__dict__.update(attrs)
    return module


def _stub_types(module_name, names):
    """names 는 미리 만들고, 그 밖의 타입 이름도 import 할 때 만든다(다른 PR 이 import 를 늘려도 돈다)."""
    module = _stub_module(module_name, **{n: _StubType(n, (), {'__init__': _stub_init}) for n in names})

    def make(name):
        if name.startswith('__'):
            raise AttributeError(name)
        stub = _StubType(name, (), {'__init__': _stub_init})
        setattr(module, name, stub)
        return stub

    module.__getattr__ = make
    return module


def _fake_modules():
    """없는 것만 대역으로. import 에 필요한 이름만 있다."""
    fakes = {}

    def missing(name):
        return importlib.util.find_spec(name) is None

    if missing('rclpy'):
        fakes.update({
            'rclpy': _stub_module('rclpy'),
            'rclpy.action': _stub_types('rclpy.action',
                                        ('ActionClient', 'ActionServer', 'CancelResponse', 'GoalResponse')),
            'rclpy.callback_groups': _stub_types('rclpy.callback_groups', ('ReentrantCallbackGroup',)),
            'rclpy.executors': _stub_types('rclpy.executors', ('MultiThreadedExecutor',)),
            'rclpy.node': _stub_types('rclpy.node', ('Node',)),
            'rclpy.time': _stub_types('rclpy.time', ('Time',)),
            'rclpy.qos': _stub_types('rclpy.qos',
                                     ('DurabilityPolicy', 'HistoryPolicy', 'QoSProfile', 'ReliabilityPolicy')),
        })
    if missing('action_msgs'):
        goal_status = types.SimpleNamespace(STATUS_UNKNOWN=0, STATUS_SUCCEEDED=4, STATUS_CANCELED=5, STATUS_ABORTED=6)
        fakes.update({'action_msgs': _stub_module('action_msgs'),
                      'action_msgs.msg': _stub_module('action_msgs.msg', GoalStatus=goal_status)})
    if missing('std_msgs'):
        fakes.update({'std_msgs': _stub_module('std_msgs'), 'std_msgs.msg': _stub_types('std_msgs.msg', ('Bool',))})
    if missing('yaml'):
        fakes['yaml'] = _stub_module('yaml', safe_load=lambda handle: {})
    if missing('ament_index_python'):
        fakes.update({
            'ament_index_python': _stub_module('ament_index_python'),
            'ament_index_python.packages': _stub_module('ament_index_python.packages',
                                                        get_package_share_directory=lambda name: ''),
        })
    if missing('rokey_p3_interfaces'):
        fakes.update({
            'rokey_p3_interfaces': _stub_module('rokey_p3_interfaces'),
            'rokey_p3_interfaces.action': _stub_types('rokey_p3_interfaces.action',
                                                      ('Deliver', 'GoToZone', 'PickPouch', 'ScanTag')),
            'rokey_p3_interfaces.msg': _stub_types('rokey_p3_interfaces.msg', (
                'BeltState', 'DeliveryRequest', 'DispenserSlot', 'DispenserStatus', 'Event', 'OrderStatus',
                'TagRead')),
            'rokey_p3_interfaces.srv': _stub_types('rokey_p3_interfaces.srv', ('Dispense', 'Reset')),
        })
    if missing('rokey_p3_navigation'):
        fakes.update({
            'rokey_p3_navigation': _stub_module('rokey_p3_navigation'),
            'rokey_p3_navigation.zones': _stub_module('rokey_p3_navigation.zones', is_zone_id=lambda zone: True),
        })
    return fakes


@pytest.fixture(scope='module')
def orch():
    fakes = _fake_modules()
    added = [name for name in fakes if name not in sys.modules]
    for name in added:
        sys.modules[name] = fakes[name]
    try:
        yield importlib.import_module(MODULE)
    finally:
        if added:
            for name in added + [MODULE, 'rokey_p3_orchestrator.ros_qos']:
                sys.modules.pop(name, None)


# ServerWait 표 -----------------------------------------------------------

GOTO = fsm.SendGoal(fsm.GO_TO_ZONE, {'zone_id': 'load'}, token=fsm.Token(1, 'trip', 1))
DISPENSE = fsm.Call(fsm.DISPENSE, {'request_id': 'r001-0001', 'order_id': 'ord-0001'}, token=fsm.Token(1, 'trip', 2))


def never(command):
    return False


def always(command):
    return True


def test_held_command_is_sent_once_the_server_appears(orch):
    wait = orch.ServerWait(10.0)
    wait.hold(GOTO.token, GOTO, now=0.0)
    assert wait.due(1, 5.0, never) == ([], [], [])
    assert wait.due(1, 6.0, always) == ([GOTO], [], [])
    assert wait.due(1, 7.0, always) == ([], [], [])


def test_held_command_expires_at_the_limit(orch):
    wait = orch.ServerWait(10.0)
    wait.hold(GOTO.token, GOTO, now=0.0)
    assert wait.due(1, 9.9, never) == ([], [], [])
    assert wait.due(1, 10.0, never) == ([], [GOTO], [])
    assert wait.tokens() == ()


def test_held_command_from_an_old_epoch_is_dropped(orch):
    wait = orch.ServerWait(10.0)
    wait.hold(DISPENSE.token, DISPENSE, now=0.0)
    assert wait.due(2, 1.0, always) == ([], [], [DISPENSE])


def test_commands_of_the_same_action_are_held_per_token(orch):
    """이름으로 덮거나 지우지 않는다. 같은 액션의 다른 goal 이 대기를 잃지 않는다."""
    wait = orch.ServerWait(10.0)
    newer = fsm.SendGoal(fsm.GO_TO_ZONE, {'zone_id': 'dock_1'}, token=fsm.Token(1, 'trip', 3))
    wait.hold(GOTO.token, GOTO, now=0.0)
    wait.hold(newer.token, newer, now=1.0)
    assert wait.tokens() == (GOTO.token, newer.token)
    assert wait.drop(GOTO.token) and not wait.drop(GOTO.token)
    assert wait.due(1, 2.0, always) == ([newer], [], [])


# 노드 배선(가짜 클라이언트) ---------------------------------------------------

class _Future:
    def add_done_callback(self, callback):
        pass


class _ActionClient:
    def __init__(self):
        self.ready = False
        self.sent = []

    def server_is_ready(self):
        return self.ready

    def send_goal_async(self, goal, feedback_callback=None):
        self.sent.append(goal)
        return _Future()


class _ServiceClient:
    def __init__(self):
        self.ready = False
        self.calls = []

    def service_is_ready(self):
        return self.ready

    def call_async(self, request):
        self.calls.append(request)
        return _Future()


class _Fsm:
    config = fsm.TripConfig()
    state = fsm.IDLE

    def __init__(self):
        self.results = []

    def stops_left(self):
        """진짜 FSM 과 같은 이름·모양. 이 가짜가 실물보다 적게 가지고 있어서 #604 CI 가 났다."""
        return 0

    def result(self, name, outcome, detail=None, token=None):
        self.results.append((name, outcome, dict(detail or {})))
        return []

    def terminated(self, token):
        return []


class _Logger:
    def __getattr__(self, level):
        return lambda text: None


@pytest.fixture
def node(orch, monkeypatch):
    clock = {'now': 0.0}
    monkeypatch.setattr(orch, 'time', types.SimpleNamespace(monotonic=lambda: clock['now']))
    borrowed = ('_run', '_send_goal', '_build_goal', '_cancel', '_call', '_feed', '_hold', '_server_ready',
                '_flush_waiting', '_finish_unsent_cancels', '_on_feedback', '_on_goal_response', '_on_service',
                '_abandon_undrained', '_wait_limit', '_log_refill_overlap')
    harness_type = type('Harness', (), {name: getattr(orch.OrchestratorNode, name) for name in borrowed})
    harness = harness_type()
    harness._lock = threading.RLock()
    harness._epoch = 1
    harness._goals = {}
    harness._drain_tokens = []
    harness._unsent_cancels = []
    harness._action_clients = {name: _ActionClient() for name in (fsm.GO_TO_ZONE, fsm.PICK_POUCH, fsm.SCAN_TAG)}
    harness._dispense = _ServiceClient()
    harness._sim_reset = _ServiceClient()
    harness._fsm = _Fsm()
    harness._server_wait = orch.ServerWait(10.0)
    harness.get_logger = lambda: _Logger()
    harness.clock = clock
    return harness


def test_goal_waits_for_the_server_instead_of_being_rejected(node):
    goto = node._action_clients[fsm.GO_TO_ZONE]
    node._run([GOTO])
    assert goto.sent == [] and node._fsm.results == []
    node.clock['now'] = 6.5                  # CI 관측: discovery 가 6 s 넘게 늦었다
    node._flush_waiting()
    assert goto.sent == []
    goto.ready = True
    node._flush_waiting()
    assert len(goto.sent) == 1
    assert [r for r in node._fsm.results if r[1] == fsm.REJECTED] == []


def test_goal_is_rejected_once_after_server_wait_s(node):
    node._run([GOTO])
    node.clock['now'] = 10.0
    node._flush_waiting()
    node.clock['now'] = 20.0
    node._flush_waiting()
    assert node._fsm.results == [(fsm.GO_TO_ZONE, fsm.REJECTED, {})]
    assert node._action_clients[fsm.GO_TO_ZONE].sent == []


def test_service_waits_then_calls_and_reset_expires_at_reset_timeout_s(node):
    """/sim/reset 은 server_wait_s 가 아니라 reset_timeout_s(서버 탐색 포함) 에 만료한다."""
    node._run([DISPENSE, fsm.Call(fsm.RESET, {'epoch': 1}, token=fsm.Token(1, 'trip', 4))])
    node._dispense.ready = True
    node._flush_waiting()
    assert len(node._dispense.calls) == 1 and node._sim_reset.calls == []
    node.clock['now'] = 10.0
    node._flush_waiting()
    assert node._fsm.results == []
    node.clock['now'] = 29.9
    node._flush_waiting()
    assert node._fsm.results == []
    node.clock['now'] = 30.0
    node._flush_waiting()
    assert node._fsm.results == [(fsm.RESET, 'failed', {'message': 'no_server'})]


def test_expired_dispense_is_rejected_with_no_server(node):
    node._run([DISPENSE])
    node.clock['now'] = 10.0
    node._flush_waiting()
    assert node._fsm.results == [(fsm.DISPENSE, fsm.REJECTED, {'message': 'no_server'})]


def test_reset_while_waiting_sends_nothing_from_the_old_epoch(node):
    node._run([GOTO, DISPENSE])
    # 리셋 barrier: epoch 이 오르고 FSM 이 활성 goal 을 cancel 하고 /sim/reset 을 부른다.
    node._epoch = 2
    reset_call = fsm.Call(fsm.RESET, {'epoch': 2}, token=fsm.Token(2, 'trip', 5))
    node._run([fsm.Cancel(fsm.GO_TO_ZONE, token=GOTO.token), reset_call])
    for client in node._action_clients.values():
        client.ready = True
    node._dispense.ready = True
    node._sim_reset.ready = True
    node._finish_unsent_cancels()           # 이전 epoch 의 canceled 알림은 노드가 버린다
    node._flush_waiting()
    assert node._action_clients[fsm.GO_TO_ZONE].sent == []
    assert node._dispense.calls == []
    assert len(node._sim_reset.calls) == 1
    assert node._fsm.results == []


class _Planner:
    """보충 클라이언트 대역. 노드가 넣은 결과만 적는다."""

    def __init__(self):
        self.results = []

    def result(self, outcome, now, detail=None, epoch=None, token=None):
        self.results.append((outcome, epoch))
        return []


def test_refill_goal_waits_for_the_m0609_server_the_same_way(node):
    """Refill(#58)도 같은 _send_goal 을 지난다. 기다렸다 보내고, 만료 거부는 FSM 이 아니라 보충 클라이언트로 간다."""
    refill = _ActionClient()
    node._action_clients[rp.REFILL] = refill
    node._refill = _Planner()
    node.get_clock = lambda: types.SimpleNamespace(now=lambda: types.SimpleNamespace(nanoseconds=0))
    goal = fsm.SendGoal(rp.REFILL, {'item_id': 'drug-amox', 'slot': 0}, token=fsm.Token(1, 'refill', 1))

    node._run([goal])
    node.clock['now'] = 6.5
    node._flush_waiting()
    assert refill.sent == [] and node._refill.results == []
    refill.ready = True
    node._flush_waiting()
    assert len(refill.sent) == 1

    refill.ready = False
    node._run([goal])
    node.clock['now'] = 20.0
    node._flush_waiting()
    assert node._refill.results == [(fsm.REJECTED, 1)]
    assert node._fsm.results == []

