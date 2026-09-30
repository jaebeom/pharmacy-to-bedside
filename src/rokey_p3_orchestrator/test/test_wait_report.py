"""트립이 guard 로 멈춰 기다리는 이유를 5 s 마다 로그로 남기는지. ROS 없이 돈다.

관측(정비, docker): stub_loop 를 먼저 띄우고 Isaac 을 늦게 띄우면 첫 트립은 AMR_DOCKED_LOAD 뒤 벨트가 unknown 이라
배출하지 않고 기다린다(계약 5절, 맞는 동작). 그동안 orchestrator 가 한 줄도 안 남겨
"Isaac 을 안 띄웠다" 를 로그로 몰랐다.
"""

import types

import test_server_wait as sw
import test_trip_fsm as tf

from rokey_p3_orchestrator import trip_fsm as fsm
from rokey_p3_orchestrator import wait_report as wr

orch = sw.orch
NAMES = {fsm.AT_HOME: '/amr_1/arm/at_home', fsm.BASE_STOPPED: '/amr_1/base/stopped', fsm.BELT: '/pharmacy/belt'}


def at_load_with_belt_unknown():
    machine = tf.make()
    machine.request(tf.request())
    machine.state_update(fsm.BELT, tf.belt(), False)                  # Isaac 이 아직 없다: 벨트 소식 끊김
    machine.result(fsm.GO_TO_ZONE, fsm.ACCEPTED)
    assert machine.result(fsm.GO_TO_ZONE, fsm.ARRIVED) == [fsm.Emit('AMR_DOCKED_LOAD', 'r001-0001')]
    assert machine.state == fsm.DOCKED_LOAD
    return machine


# WaitReport(순수) -----------------------------------------------------------------

def test_report_warns_every_period_and_says_when_the_wait_ends():
    report = wr.WaitReport(period_s=5.0)
    wait = ('배출', '/pharmacy/belt unknown')
    lines = []
    for tenth in range(0, 121):                                        # 0 - 12.0 s, 0.1 s tick
        lines += [(tenth / 10, level, text) for level, text in report.update(wait, tenth / 10)]
    lines += [(12.3, level, text) for level, text in report.update(None, 12.3)]
    assert lines == [
        (5.0, wr.WARN, '배출 대기 5 s: /pharmacy/belt unknown'),
        (10.0, wr.WARN, '배출 대기 10 s: /pharmacy/belt unknown'),
        (12.3, wr.INFO, '배출 대기 끝. 12 s 기다렸다.'),
    ]


def test_short_waits_and_no_wait_log_nothing():
    report = wr.WaitReport(period_s=5.0)
    assert report.update(None, 0.0) == []
    for tenth in range(0, 49):
        assert report.update(('출발(적재 위치로)', 'arm/at_home false'), tenth / 10) == []
    assert report.update(None, 4.9) == []                               # 5 s 전에 풀렸다: 끝 줄도 없다


def test_a_new_kind_of_wait_starts_its_own_clock():
    report = wr.WaitReport(period_s=5.0)
    report.update(('배출', 'a'), 0.0)
    assert report.update(('배출', 'a'), 5.0) == [(wr.WARN, '배출 대기 5 s: a')]
    assert report.update(('벨트 픽', 'b'), 6.0) == [(wr.INFO, '배출 대기 끝. 6 s 기다렸다.')]
    assert report.update(('벨트 픽', 'b'), 10.9) == []
    assert report.update(('벨트 픽', 'b'), 11.0) == [(wr.WARN, '벨트 픽 대기 5 s: b')]


# FSM + WaitReport ------------------------------------------------------------------

def test_belt_unknown_at_the_load_zone_logs_every_5_s_then_once_when_it_clears():
    machine = at_load_with_belt_unknown()
    report = wr.WaitReport()
    lines = []
    for tenth in range(0, 201):                                        # 20 s 동안 Isaac 이 없다
        now = tenth / 10
        machine.tick(now, now)
        lines += report.update(machine.wait_reason(NAMES), now)
    assert [level for level, _ in lines] == [wr.WARN] * 4
    assert lines[0] == (wr.WARN, '배출 대기 5 s: /pharmacy/belt unknown(1.0 s 넘게 소식 없음. '
                                 '발행하는 노드·Isaac 이 떠 있는지 확인)')

    commands = machine.state_update(fsm.BELT, tf.belt(), True)          # Isaac 이 떴다
    assert any(isinstance(c, fsm.Call) for c in commands)               # 판정은 그대로: 곧바로 배출
    lines = report.update(machine.wait_reason(NAMES), 21.0)
    assert lines == [(wr.INFO, '배출 대기 끝. 21 s 기다렸다.')]
    for tenth in range(211, 400):                                       # 그 뒤로는 기다림이 없어 0줄
        assert report.update(machine.wait_reason(NAMES), tenth / 10) == []


def test_wait_reasons_for_the_other_guards_and_none_when_not_waiting():
    machine = tf.make()
    assert machine.wait_reason(NAMES) is None                           # IDLE
    machine.state_update(fsm.AT_HOME, False, True)
    machine.request(tf.request())
    assert machine.wait_reason(NAMES) == ('출발(적재 위치로)', '/amr_1/arm/at_home false')
    machine.state_update(fsm.AT_HOME, True, False)
    assert machine.wait_reason(NAMES)[1].startswith('/amr_1/arm/at_home unknown')
    machine.state_update(fsm.AT_HOME, True, True)                       # 출발한다
    assert machine.wait_reason(NAMES) is None

    machine = tf.make()
    machine.request(tf.request())
    machine.state_update(fsm.BELT, tf.belt(True, False, 'ord-9999'), True)
    machine.result(fsm.GO_TO_ZONE, fsm.ACCEPTED)
    machine.result(fsm.GO_TO_ZONE, fsm.ARRIVED)
    assert machine.wait_reason(NAMES) == ('배출', '벨트에 봉투가 있다(order_id=ord-9999). 치워지거나 픽될 때까지')

    machine = tf.make(pharmacy_only=True)
    machine.state = fsm.DEPARTING
    machine._entered = False
    assert machine.wait_reason(NAMES) is None                            # pharmacy_only 는 병동으로 안 간다


def test_wait_reason_changes_nothing():
    machine = at_load_with_belt_unknown()
    machine._draining = {fsm.Token(1, 'trip', 99): 5.0}
    machine.tick(10.0, 10.0)
    before = (machine.state, machine._entered, dict(machine._draining), machine._trip.stop_index, machine._version)
    for _ in range(3):
        machine.wait_reason(NAMES)
    assert (machine.state, machine._entered, dict(machine._draining), machine._trip.stop_index,
            machine._version) == before


# 노드 배선 -------------------------------------------------------------------------

def test_node_prefixes_the_request_id_and_uses_warning_then_info(orch):
    lines = []
    logger = types.SimpleNamespace(warning=lambda text: lines.append(('warning', text)),
                                   info=lambda text: lines.append(('info', text)))
    waits = iter([('배출', '/pharmacy/belt unknown'), ('배출', '/pharmacy/belt unknown'), None])
    node = types.SimpleNamespace(
        _fsm=types.SimpleNamespace(wait_reason=lambda names: next(waits), request_id='r001-0001'),
        _wait_report=wr.WaitReport(period_s=5.0), _wait_names=NAMES, get_logger=lambda: logger)
    for wall in (0.0, 5.0, 6.0):
        orch.OrchestratorNode._report_wait(node, wall)
    assert lines == [('warning', 'r001-0001: 배출 대기 5 s: /pharmacy/belt unknown'),
                     ('info', 'r001-0001: 배출 대기 끝. 6 s 기다렸다.')]
