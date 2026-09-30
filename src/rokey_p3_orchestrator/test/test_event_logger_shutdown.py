"""event_logger 가 어느 종료 경로로 끝나도 run 을 한 번 닫는지. ROS 없이 돈다.

rclpy·인터페이스가 없는 곳에서는 이 모듈 안에서만 가짜 모듈을 넣고 import 한다(끝나면 뺀다).
노드는 띄우지 않는다. run 파일은 노드의 메서드를 빌린 Harness 로, 종료 경로는 main() 의 rclpy 를
가짜로 바꿔서 본다. 실제 신호로 rclpy 가 spin 을 끝내는 것(L2)은 ROS 가 있는 곳에서 따로 본다.
"""

import datetime
import importlib
import importlib.util
import json
import os
import signal
import sys
import time
import types

import pytest

from rokey_p3_orchestrator import run_log

MODULE = 'rokey_p3_orchestrator.event_logger_node'


def _fake_modules():
    """rclpy·rokey_p3_interfaces 가 없을 때만 쓰는 가짜. import 에 필요한 이름만 있다."""
    fakes = {}
    if importlib.util.find_spec('rclpy') is None:
        rclpy = types.ModuleType('rclpy')
        node = types.ModuleType('rclpy.node')
        node.Node = type('Node', (), {})
        executors = types.ModuleType('rclpy.executors')
        executors.ExternalShutdownException = type('ExternalShutdownException', (Exception,), {})
        qos = types.ModuleType('rclpy.qos')
        for name in ('DurabilityPolicy', 'HistoryPolicy', 'QoSProfile', 'ReliabilityPolicy'):
            setattr(qos, name, types.SimpleNamespace())
        clock = types.ModuleType('rclpy.clock')
        clock.ClockType = types.SimpleNamespace(ROS_TIME='ROS_TIME', STEADY_TIME='STEADY_TIME')
        clock.Clock = type('Clock', (), {'__init__': lambda self, clock_type='ROS_TIME': setattr(
            self, 'clock_type', clock_type)})
        fakes.update({'rclpy': rclpy, 'rclpy.node': node, 'rclpy.executors': executors, 'rclpy.qos': qos,
                      'rclpy.clock': clock})
    if importlib.util.find_spec('rokey_p3_interfaces') is None:
        msg = types.ModuleType('rokey_p3_interfaces.msg')
        for name in ('CabinetObservation', 'Event', 'OrderStatus'):
            setattr(msg, name, type(name, (), {}))
        fakes.update({'rokey_p3_interfaces': types.ModuleType('rokey_p3_interfaces'),
                      'rokey_p3_interfaces.msg': msg})
    return fakes


@pytest.fixture(scope='module')
def elog():
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


def make_harness(elog, root):
    """노드의 close 만 빌린 객체. Node 를 만들지 않는다. run 파일은 run_log.RunBook 이 쓴다."""

    class Harness:
        close = elog.EventLoggerNode.close

        def __init__(self):
            self._book = run_log.RunBook(
                str(root), 'master02', 2.0,
                now_utc=lambda: datetime.datetime.now(datetime.timezone.utc), nonce=lambda: os.urandom(4).hex())

    return Harness()


# run 파일 ---------------------------------------------------------------

def test_close_writes_the_judgement_files_and_a_second_close_changes_nothing(elog, tmp_path):
    node = make_harness(elog, tmp_path)
    run = node._book.current
    run_dir = run.dir
    run.ledger.note_status('ord-0001', 'HOLD_RETURN', 'pharmacy_only', 'r001-0001')
    run.write('events', {'name': 'LOAD_DONE'})
    events = run._files['events']

    node.close()
    orders = (tmp_path / os.path.basename(run_dir) / 'orders.jsonl').read_bytes()
    meta = (tmp_path / os.path.basename(run_dir) / 'meta.json').read_bytes()
    assert json.loads(orders)['order_id'] == 'ord-0001'
    assert json.loads(meta)['counts']['events'] == 1
    assert events.closed and run.closed

    time.sleep(1.1)                         # ended_utc 는 초 단위다. 다시 썼다면 값이 달라진다
    node.close()
    assert (tmp_path / os.path.basename(run_dir) / 'orders.jsonl').read_bytes() == orders
    assert (tmp_path / os.path.basename(run_dir) / 'meta.json').read_bytes() == meta


# 종료 경로 ---------------------------------------------------------------

def _spin_that(elog, exit_path):
    def spin(node):
        if exit_path == 'returns':          # SIGTERM: rclpy 가 context 를 내려 spin 이 돌아온다
            return
        if exit_path == 'sigint':
            raise KeyboardInterrupt()
        if exit_path == 'external_shutdown':
            raise elog.ExternalShutdownException()
        if exit_path == 'sighup':
            raise elog.Hangup()
        raise RuntimeError('콜백이 죽었다')
    return spin


@pytest.mark.parametrize('exit_path', ['returns', 'sigint', 'external_shutdown', 'sighup', 'crash'])
def test_main_closes_the_run_exactly_once_on_every_exit_path(elog, monkeypatch, exit_path):
    calls = []

    class FakeNode:
        def close(self):
            calls.append('close')

        def destroy_node(self):
            calls.append('destroy_node')

    def record_signal(signum, handler):
        name = signal.Signals(signum).name
        calls.append(f'{name}:ignore' if handler == signal.SIG_IGN else f'{name}:{handler.__name__}')

    fake_rclpy = types.SimpleNamespace(
        init=lambda args=None: calls.append('init'),
        spin=_spin_that(elog, exit_path),
        try_shutdown=lambda: calls.append('try_shutdown'))
    fake_signal = types.SimpleNamespace(SIGHUP=signal.SIGHUP, SIG_IGN=signal.SIG_IGN, signal=record_signal)
    monkeypatch.setattr(elog, 'rclpy', fake_rclpy)
    monkeypatch.setattr(elog, 'signal', fake_signal)
    monkeypatch.setattr(elog, 'EventLoggerNode', FakeNode)

    if exit_path == 'crash':
        with pytest.raises(RuntimeError):
            elog.main()
    else:
        elog.main()

    assert calls == [
        'init', 'SIGHUP:raise_hangup',
        'SIGINT:ignore', 'SIGTERM:ignore', 'SIGHUP:ignore',     # 닫는 동안 두 번째 신호에 끊기지 않게
        'close', 'destroy_node', 'try_shutdown',
    ]


def test_sighup_becomes_an_exception_in_the_main_thread(elog):
    previous = signal.signal(signal.SIGHUP, elog.raise_hangup)
    try:
        with pytest.raises(elog.Hangup):
            os.kill(os.getpid(), signal.SIGHUP)
            time.sleep(1.0)                 # 처리기는 main 스레드의 다음 바이트코드에서 돈다
    finally:
        signal.signal(signal.SIGHUP, previous)


# SIGHUP 이 spin 대기에 갇히지 않게 ------------------------------------------

def test_wake_timer_uses_a_steady_clock_so_it_runs_after_clock_stops(elog):
    """정비 4호: tmux kill-window 뒤 받을 메시지가 없어 spin 이 깨지 않고 SIGHUP 처리기가 안 돌았다."""
    created = []

    class Harness:
        _start_wake_timer = elog.EventLoggerNode._start_wake_timer
        _wake = elog.EventLoggerNode._wake

        def create_timer(self, period, callback, clock=None):
            created.append((period, callback, clock))
            return object()

    node = Harness()
    expired = []
    node._book = types.SimpleNamespace(expire=expired.append)
    node._start_wake_timer()
    [(period, callback, clock)] = created
    assert period == elog.WAKE_PERIOD_S == 0.5
    assert callback == node._wake
    assert clock.clock_type == elog.ClockType.STEADY_TIME      # sim time 이면 /clock 이 멈출 때 같이 멈춘다
    assert node._wake() is None
    assert len(expired) == 1                                    # 메시지가 없어도 drain 이 끝난 run 을 닫는다


def test_the_node_starts_the_wake_timer_and_main_installs_the_sighup_handler(elog):
    import inspect
    assert 'self._start_wake_timer()' in inspect.getsource(elog.EventLoggerNode.__init__)
    assert 'signal.signal(signal.SIGHUP, raise_hangup)' in inspect.getsource(elog.main)
