"""보충 전 약통 확인 서비스(`/orchestrator/check_container`, QR·DB·카메라 계약 2.3). ROS 없이 돈다.

노드의 서비스 콜백과 리셋 경로만 빌린 Harness 에 실제 약 DB 를 붙인다. 되부름 교착(팔이 Refill 도중에 묻는다)은
노드가 Refill 결과를 콜백으로 받고 이 서비스가 자기 그룹이라 생기지 않는다 — 여기서는 "Refill 결과를 기다리는
중(goal 표에 Refill 이 있다)에도 서비스가 바로 답한다"를 본다. 실제 실행기의 L2 는 test_container_check_l2.py.
"""

import threading
import types
from pathlib import Path

import pytest
import test_server_wait as sw
import yaml

from rokey_p3_orchestrator import pharmacy_db

orch = sw.orch
CONFIG = Path(__file__).resolve().parents[1] / 'config'


def _read(name):
    return yaml.safe_load((CONFIG / name).read_text(encoding='utf-8'))


class _RclpyLikeLogger:
    """rclpy 처럼 **한 호출 자리에서 등급이 바뀌면** ValueError 를 낸다(9/23 L3 에서 서비스를 죽인 규칙)."""

    def __init__(self, lines):
        self.lines, self.sites = lines, {}

    def _log(self, severity, text):
        import inspect

        caller = inspect.stack()[2]
        site = (caller.filename, caller.lineno)
        if self.sites.setdefault(site, severity) != severity:
            raise ValueError('Logger severity cannot be changed between calls.')
        self.lines.append(text)

    def info(self, text):
        self._log('info', text)

    def warning(self, text):
        self._log('warning', text)


_LOGGERS = {}


def _logger(lines):
    """노드 하나에 로거 하나(호출 자리 기록이 이어져야 등급 변경을 잡는다)."""
    return _LOGGERS.setdefault(id(lines), _RclpyLikeLogger(lines))


@pytest.fixture
def node(orch):
    harness = type('Harness', (), {name: getattr(orch.OrchestratorNode, name)
                                    for name in ('_on_check_container', '_reload_stores')})()
    harness._lock = threading.RLock()
    harness._epoch = 1
    harness._db = pharmacy_db.PharmacyDb(':memory:', pharmacy_db.build_seed(
        _read('pharmacy_catalog.yaml'), _read('dispenser.yaml'), _read('order_pool.yaml')))
    harness.lines = []
    harness.get_logger = lambda: _logger(harness.lines)
    harness.get_clock = lambda: types.SimpleNamespace(now=lambda: types.SimpleNamespace(nanoseconds=5_000_000_000))
    harness._goals = {'refill-token': 'Refill 진행 중'}        # Refill 결과를 기다리는 중
    yield harness
    harness._db.close()


def _ask(node, container_id, epoch=1, cell='floor_right/r0c1'):
    request = types.SimpleNamespace(container_id=container_id, robot_id='m0609', cell_id=cell, epoch=epoch)
    return node._on_check_container(request, types.SimpleNamespace(allowed=None, reason=None))


def test_expired_canister_is_refused_while_the_refill_is_still_running(node):
    response = _ask(node, 'cn-0106')
    assert (response.allowed, response.reason) == (False, 'expired')
    assert node._goals                                       # Refill 은 그대로 기다리는 중
    [scan] = node._db.scans()
    assert (scan['robot'], scan['zone_id'], scan['stamp'], scan['result']) == (
        'm0609', 'floor_right/r0c1', 5.0, 'expired')
    assert '장착 거부' in node.lines[-1]


def test_fresh_canister_is_allowed(node):
    response = _ask(node, 'cn-0105', cell='floor_right/r0c0')
    assert (response.allowed, response.reason) == (True, 'ok')


def test_request_from_another_epoch_is_refused(node):
    response = _ask(node, 'cn-0105', epoch=node._epoch + 1)
    assert (response.allowed, response.reason) == (False, 'stale_epoch')


def test_epoch_zero_from_an_arm_that_has_not_seen_events_yet_is_taken(node):
    """회차33(5a51804): 팔 'epoch 0 에서 다시 안 고른다', orchestrator 'epoch=1' → 모듈 3/3 stale_epoch 였다."""
    response = _ask(node, 'cn-0105', epoch=0)
    assert (response.allowed, response.reason) == (True, 'ok')


def test_reset_restores_the_tables_but_keeps_the_scans(node, monkeypatch, orch):
    _ask(node, 'cn-0106')
    node._fsm = types.SimpleNamespace(inventory=None)
    node._refill = types.SimpleNamespace(inventory=None)
    node._used_requests, node._used_orders = set(), set()
    node._dispenser_path = str(CONFIG / 'dispenser.yaml')
    node._reload_stores()
    assert len(node._db.scans()) == 1


def test_refusal_then_allowance_both_answer(node):
    """9/23 L3: 거부 뒤 허용에서 로그 등급이 바뀌어 서비스가 죽었다. 번갈아 세 번 물어도 답해야 한다."""
    assert (_ask(node, 'cn-0106').allowed, _ask(node, 'cn-0105', cell='floor_right/r0c0').allowed,
            _ask(node, 'cn-0106').allowed) == (False, True, False)
