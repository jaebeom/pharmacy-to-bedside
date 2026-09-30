"""status_monitor 노드 배선. ROS 없이 돈다. 구독 목록, 콜백 → 모델, --once, Ctrl-C.

rclpy·인터페이스가 없으면 이 모듈 안에서만 가짜를 넣는다. 실제 실행(L2)은 정비·마클이 본다.
"""

import importlib
import importlib.util
import sys
import types

import pytest

from rokey_p3_orchestrator import status_view as view

MODULE = 'rokey_p3_orchestrator.status_monitor_node'


def _fake_modules():
    fakes = {}

    def missing(name):
        try:
            return importlib.util.find_spec(name) is None
        except ModuleNotFoundError:
            return True

    def module(name, **attrs):
        made = types.ModuleType(name)
        made.__dict__.update(attrs)
        return made

    def kinds(*names):
        return {name: type(name, (), {}) for name in names}

    if missing('rclpy'):
        fakes.update({
            'rclpy': module('rclpy'),
            'rclpy.node': module('rclpy.node', Node=type('Node', (), {'__init__': lambda self, *a, **k: None})),
            'rclpy.clock': module('rclpy.clock', ClockType=types.SimpleNamespace(STEADY_TIME='STEADY_TIME'),
                                  Clock=type('Clock', (), {'__init__': lambda self, clock_type=None: setattr(
                                      self, 'clock_type', clock_type)})),
            'rclpy.executors': module('rclpy.executors',
                                      ExternalShutdownException=type('ExternalShutdownException', (Exception,), {})),
            'rclpy.utilities': module('rclpy.utilities', remove_ros_args=lambda args: list(args)),
            'rclpy.qos': module('rclpy.qos', **{name: types.SimpleNamespace(KEEP_LAST=0, RELIABLE=0, BEST_EFFORT=0,
                                                                            VOLATILE=0, TRANSIENT_LOCAL=0)
                                                for name in ('DurabilityPolicy', 'HistoryPolicy', 'ReliabilityPolicy')},
                                QoSProfile=lambda **kwargs: kwargs),
        })
    if missing('rosgraph_msgs'):
        fakes.update({'rosgraph_msgs': module('rosgraph_msgs'),
                      'rosgraph_msgs.msg': module('rosgraph_msgs.msg', **kinds('Clock'))})
    if missing('std_msgs'):
        fakes.update({'std_msgs': module('std_msgs'), 'std_msgs.msg': module('std_msgs.msg', **kinds('Bool'))})
    if missing('rokey_p3_interfaces'):
        fakes.update({'rokey_p3_interfaces': module('rokey_p3_interfaces'),
                      'rokey_p3_interfaces.msg': module('rokey_p3_interfaces.msg', **kinds(
                          'BeltState', 'CabinetObservation', 'DispenserStatus', 'Event', 'OrderStatus'))})
    return fakes


@pytest.fixture(scope='module')
def mon():
    fakes = _fake_modules()
    added = [name for name in fakes if name not in sys.modules]
    for name in added:
        sys.modules[name] = fakes[name]
    try:
        yield importlib.import_module(MODULE)
    finally:
        sys.modules.pop(MODULE, None)
        for name in added + (['rokey_p3_orchestrator.ros_qos'] if added else []):
            sys.modules.pop(name, None)


def build(mon, monkeypatch, argv):
    """Node.__init__ 을 건너뛰고 노드 __init__ 이 무엇을 구독·생성하는지 적는다.

    기록용 속성 이름은 rclpy Node 의 이름(publishers·subscriptions·timers·clients·services·guards·waitables·
    executor·context·handle 등 읽기 전용 property)과 겹치면 안 된다. 진짜 rclpy 에서 `timers` 에 값을 넣다가
    AttributeError 로 깨졌다(정비 docker Jazzy, eed318a). 대역 Node 에는 그 property 가 없어 로컬에서는 통과했다.
    """
    monkeypatch.setattr(mon.Node, '__init__', lambda self, *args, **kwargs: None)
    node = mon.StatusMonitorNode.__new__(mon.StatusMonitorNode)
    node.seen_topics, node.seen_timers = [], []
    node.create_subscription = lambda kind, topic, callback, qos: node.seen_topics.append(topic)
    node.create_timer = lambda period, callback, clock=None: node.seen_timers.append((period, clock)) or object()
    for name in ('create_publisher', 'create_service', 'create_client'):
        setattr(node, name, lambda *args, _name=name, **kwargs: pytest.fail(f'{_name} 를 쓰지 않는다'))
    node.__init__(view.parse_options(argv))
    return node


BASE_TOPICS = ['/clock', '/events', '/orders/status', '/pharmacy/dispenser/status', '/amr_1/arm/at_home',
               '/amr_1/base/stopped', '/amr_1/gripper/holding', '/m0609/arm/at_home', '/pharmacy/belt']


def test_subscribes_only_and_skips_the_evaluator_by_default(mon, monkeypatch):
    node = build(mon, monkeypatch, [])
    assert node.seen_topics == BASE_TOPICS
    [(period, clock)] = node.seen_timers
    assert period == 1.0 and clock.clock_type == mon.ClockType.STEADY_TIME     # /clock 이 멈춰도 그린다

    node = build(mon, monkeypatch, ['--with-evaluator', '--robot-id', 'amr_2', '--once'])
    assert node.seen_topics[-1] == '/evaluator/cabinet'
    assert '/amr_2/arm/at_home' in node.seen_topics
    assert node.seen_timers == []                                                   # --once 는 타이머 없이 한 번


def test_callbacks_fill_the_model(mon, monkeypatch):
    node = build(mon, monkeypatch, [])
    monkeypatch.setattr(mon, 'time', types.SimpleNamespace(monotonic=lambda: 50.0))
    stamp = types.SimpleNamespace(sec=12, nanosec=500_000_000)
    node._on_clock(types.SimpleNamespace(clock=stamp))
    node._on_event(types.SimpleNamespace(header=types.SimpleNamespace(stamp=stamp), epoch=3, name='LOAD_DONE',
                                         request_id='r003-0001', order_id='', robot_id='amr_1', detail=''))
    node._on_order(types.SimpleNamespace(request_id='r003-0001', order_id='ord-0001', state=11,
                                         reason='pharmacy_only'))
    node._on_dispenser(types.SimpleNamespace(
        slots=[types.SimpleNamespace(item_id='drug-amox', slot=0, lot_id='lot-amox-01', count=4, active=True)],
        paused_item_ids=['drug-ibu'], queue_length=0, belt_occupied=True))
    node._signal_callback('arm_at_home')(types.SimpleNamespace(data=True))
    node._on_belt(types.SimpleNamespace(occupied=False, at_end=False, order_id=''))

    model = node._model
    assert model.clock == (12.5, 50.0) and model.epoch == 3
    assert model.orders[('r003-0001', 'ord-0001')]['state'] == 'HOLD_RETURN'
    assert model.dispenser[0]['paused_item_ids'] == ['drug-ibu']
    assert model.signals['arm_at_home'] == (True, 50.0)
    assert model.signals['belt'][0] == {'occupied': False, 'at_end': False, 'order_id': ''}
    assert node.screen()[1] == 'trip (estimated from events): 적재 끝 <- LOAD_DONE'


def fake_runtime(mon, monkeypatch, spin):
    calls = []
    clock = types.SimpleNamespace(now=0.0)

    class FakeNode:
        def __init__(self, options):
            calls.append(('node', options.once))

        def screen(self):
            return ['screen']

        def destroy_node(self):
            calls.append('destroy_node')

    def spin_once(node, timeout_sec=None):
        clock.now += 0.5
        calls.append('spin_once')

    monkeypatch.setattr(mon, 'StatusMonitorNode', FakeNode)
    monkeypatch.setattr(mon, 'time', types.SimpleNamespace(monotonic=lambda: clock.now))
    monkeypatch.setattr(mon, 'remove_ros_args', lambda args: list(args))
    monkeypatch.setattr(mon, 'rclpy', types.SimpleNamespace(
        init=lambda args=None: calls.append('init'), ok=lambda: True, spin_once=spin_once, spin=spin,
        try_shutdown=lambda: calls.append('try_shutdown')))
    return calls


def test_once_collects_briefly_prints_one_frame_and_shuts_down(mon, monkeypatch, capsys):
    calls = fake_runtime(mon, monkeypatch, spin=lambda node: pytest.fail('--once 는 spin 하지 않는다'))
    mon.main(['status_monitor', '--once'])
    assert calls == ['init', ('node', True)] + ['spin_once'] * 4 + ['destroy_node', 'try_shutdown']
    assert capsys.readouterr().out == '=' * 60 + '\nscreen\n'


def test_ctrl_c_ends_quietly_and_cleans_up(mon, monkeypatch):
    def interrupted(node):
        raise KeyboardInterrupt()

    calls = fake_runtime(mon, monkeypatch, spin=interrupted)
    mon.main(['status_monitor'])
    assert calls == ['init', ('node', False), 'destroy_node', 'try_shutdown']
