"""L1: map_server 활성화 감시(회차133 — configure 응답 유실로 map_server 가 active 가 못 됨). ROS 없이 본다."""

import pathlib

from rokey_p3_navigation import map_activation as M

LAUNCH = pathlib.Path(__file__).resolve().parents[1] / 'launch' / 'nav2.launch.py'


def test_leaves_a_healthy_bringup_alone():
    assert M.next_transition(M.ACTIVE, 0.5) is None
    assert M.next_transition(M.ACTIVE, 999.0) is None
    assert M.next_transition(M.INACTIVE, M.WAIT_S - 0.1) is None        # 관리자에게 먼저 맡긴다
    assert M.next_transition(M.UNCONFIGURED, 1.0) is None


def test_brings_map_server_up_itself_after_the_wait():
    """회차133: configure 는 됐는데(inactive) 관리자가 멈췄다 → activate. 아예 안 됐으면 configure 부터."""
    assert M.next_transition(M.INACTIVE, M.WAIT_S) == M.ACTIVATE
    assert M.next_transition(M.UNCONFIGURED, M.WAIT_S + 5) == M.CONFIGURE
    assert M.next_transition(10, M.WAIT_S + 5) is None                   # 전이 중 등 다른 상태는 건드리지 않는다


def test_launch_starts_the_guard_next_to_map_server():
    text = LAUNCH.read_text(encoding='utf-8')
    assert "executable='map_activation_guard'" in text
    assert "'target': 'map_server'" in text


NODE = pathlib.Path(__file__).resolve().parents[1] / 'rokey_p3_navigation' / 'map_activation_guard_node.py'


def test_a_lost_reply_does_not_freeze_the_guard():
    """통합검증 #743 5854169997: change_state 응답이 안 오면 `_pending` 이 영원히 남아 가드가 멈췄다.
    고치려는 고장이 바로 그 응답 유실이다. 시한이 지나면 버리고 다시 본다."""
    assert not M.pending_expired(None, 100.0)                        # 기다리는 것이 없다
    assert not M.pending_expired(10.0, 10.0 + M.PENDING_TIMEOUT_S - 0.01)
    assert M.pending_expired(10.0, 10.0 + M.PENDING_TIMEOUT_S)
    source = NODE.read_text(encoding='utf-8')
    tick = source[source.index('def _tick'):source.index('def _await')]
    assert 'pending_expired' in tick and 'cancel()' in tick and 'MAX_TIMEOUTS' in tick
    # 버린 호출의 늦은 응답은 지금 기다리는 것이 아니면 무시한다.
    assert 'done is self._pending' in source
