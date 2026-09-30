"""`Note` 를 수준마다 다른 호출 지점에서 내는지.

9/20 실습13(#240)에서 보충 grasp 가 실패하자 orchestrator 가 죽었다:
`ValueError: Logger severity cannot be changed between calls`.
한 줄에서 수준을 골라 부르면(`{'info': log.info, ...}.get(level, log.warning)(text)`)
rclpy 가 그 호출 지점(파일·줄)의 severity 를 기억하고 있다가 다른 수준에서 예외를 던진다.
평소 Note 는 기본 수준이라 안 터지고, 다른 수준의 Note 가 처음 나오는 순간 노드가 죽었다.

- 앞 절(L1): rclpy 의 그 규칙만 흉내 낸 대역 로거로 본다. rclpy 없이 어디서나 돈다.
- 뒤 절(L2): 진짜 rclpy 로거로 같은 순서를 낸다. rclpy 가 있을 때만 돈다(CI colcon).
"""

import importlib.util
import inspect

import pytest
import test_server_wait as sw

from rokey_p3_orchestrator import trip_fsm as fsm

#: rclpy·인터페이스가 없는 곳에서 대역을 넣고 orchestrator_node 를 읽어 주는 fixture.
orch = sw.orch

LEVELS = ('info', 'warning', 'error')
HAS_RCLPY = importlib.util.find_spec('rclpy') is not None


class CallSiteLogger:
    """rclpy `rcutils_logger` 의 규칙만 흉내 낸다: 호출 지점마다 severity 가 고정된다.

    부르는 쪽의 (파일, 줄)을 기억하고, 같은 지점에서 다른 수준으로 부르면 rclpy 와 같은
    `ValueError` 를 낸다. 실제 로거는 첫 호출에 지점을 기억하고 그 뒤 수준이 바뀌면 던진다.
    """

    def __init__(self):
        self.seen = {}
        self.lines = []

    def _log(self, level, text):
        caller = inspect.stack()[2]
        site = (caller.filename, caller.lineno)
        if self.seen.setdefault(site, level) != level:
            raise ValueError('Logger severity cannot be changed between calls.')
        self.lines.append((level, text))

    def info(self, text):
        self._log('info', text)

    def warning(self, text):
        self._log('warning', text)

    def error(self, text):
        self._log('error', text)


def note_holder(orch, logger):
    """`_note` 만 빌려 쓰는 최소 객체. 노드를 띄우지 않는다."""
    holder = type('Holder', (), {'get_logger': lambda self: logger})()
    holder._note = orch.OrchestratorNode._note.__get__(holder)
    return holder


@pytest.fixture
def stub_logger():
    return CallSiteLogger()


def test_every_level_can_follow_every_other_level(orch, stub_logger):
    """같은 경로로 info → warning → error 를 연달아 내도 예외가 없다."""
    holder = note_holder(orch, stub_logger)
    for first in LEVELS:
        for second in LEVELS:
            holder._note(fsm.Note(f'{first} 먼저', level=first))
            holder._note(fsm.Note(f'{second} 다음', level=second))
    assert len(stub_logger.lines) == 2 * len(LEVELS) ** 2


def test_the_refill_failure_sequence_does_not_raise(orch, stub_logger):
    """실습13 의 순서 그대로: 기본 수준 Note 뒤에 보충 결과 Note 가 온다."""
    holder = note_holder(orch, stub_logger)
    holder._note(fsm.Note('리셋 drain: goal 1건이 3 s 안에 끝나지 않았다'))          # 기본 warning
    holder._note(fsm.Note('Refill drug-ibu 슬롯 B: lot-ibu-03 5개 장착.', level='info'))
    holder._note(fsm.Note('Refill drug-ibu: 실패. grasp', level='error'))
    assert [level for level, _ in stub_logger.lines] == ['warning', 'info', 'error']


def test_an_unknown_level_is_a_warning(orch, stub_logger):
    """모르는 수준은 경고로 낸다(`Note.level` 기본값과 같다). 예외로 죽지 않는다."""
    holder = note_holder(orch, stub_logger)
    holder._note(fsm.Note('모르는 수준', level='verbose'))
    holder._note(fsm.Note('그 뒤 info', level='info'))
    assert [level for level, _ in stub_logger.lines] == ['warning', 'info']


@pytest.mark.skipif(not HAS_RCLPY, reason='rclpy 가 있어야 진짜 로거의 severity 규칙을 본다')
def test_the_real_rclpy_logger_takes_every_level(orch):
    """진짜 rclpy 로거로 같은 순서를 낸다. 고치기 전에는 여기서 ValueError 가 났다."""
    import rclpy

    holder = note_holder(orch, rclpy.logging.get_logger('p3_note_levels'))
    for level in LEVELS:
        holder._note(fsm.Note(f'{level} 한 번', level=level))
    holder._note(fsm.Note('모르는 수준', level='verbose'))
