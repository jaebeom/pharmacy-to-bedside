"""`ArmClearance` 발행과 `GripperState`·`GripperCommand` 에 쓰는 순수 규칙. ROS 를 import 하지 않는다. 계약 v1 11.6절.

- epoch: 발행 노드가 본 **마지막 `RESET_DONE` 의 epoch**(리셋 전은 1). `RESET_BEGIN` 으로 올리지 않는다.
  이벤트를 하나도 못 받았으면 epoch 를 모른다 → 발행하지 않는다(orchestrator 의 값을 추측하지 않는다).
- seq: 판정에 쓴 `joint_states` 의 stamp 가 sim time 으로 앞으로 갔을 때만 +1. 발행 주기와 무관하다.
- holding: 물리 경로의 흡착 입력은 `GripperState` 뿐이다(기존 Bool 은 쓰지 않는다). epoch 가 다르거나, 1.0 s(wall)
  안에 받지 못했거나, seq 가 1.0 s 동안 늘지 않았거나, state 가 UNKNOWN 이면 "모름"(None)이다.
- 흡착 명령: `command_seq` 는 epoch 마다 1 부터 명령마다 +1(`CommandSeq`). 흡착 확인 = HELD ∧ `last_applied ≥ 닫기 seq`,
  해제 확인 = RELEASED ∧ `last_applied ≥ 열기 seq`(`command_result`). 명령 전의 HELD 는 파지가 아니다.
"""

import math
from collections import namedtuple

EpochView = namedtuple('EpochView', ('epoch', 'fenced', 'reason'))

#: `command_result` 의 값
CONFIRMED = 'confirmed'        # 명령이 적용됐고 원하는 상태다
CONTRADICTED = 'contradicted'  # 명령이 적용됐는데 반대 상태다(닫았는데 RELEASED = 못 잡음·떨어뜨림)
PENDING = 'pending'            # 관측은 신선하지만 아직 그 명령을 적용하지 않았다
UNKNOWN = 'unknown'            # 관측이 없거나 오래됐거나 다른 epoch 거나 state UNKNOWN 이다(관측 소실)


def publish_epoch(seen_epoch, done_epoch, fenced):
    """(본 이벤트 중 가장 큰 epoch, 마지막 RESET_DONE epoch, barrier 중인가) → EpochView.

    epoch 가 None 이면 발행하지 않는다. fenced 면 발행은 하되 clearance 는 UNKNOWN 이다.
    """
    if not seen_epoch or seen_epoch < 1:
        return EpochView(None, False, 'epoch 를 모른다(이벤트를 아직 못 받았다)')
    epoch = max(int(done_epoch or 0), 1)
    if fenced:
        return EpochView(epoch, True, '리셋 barrier 중')
    return EpochView(epoch, False, '')


class StampSeq:
    """판정에 쓴 입력 stamp(sim 초)가 앞으로 갔을 때만 seq 를 올린다. epoch 가 바뀌면 0 부터 다시 센다."""

    def __init__(self):
        self.seq = 0
        self._stamp = None
        self._epoch = None

    def next(self, stamp_s, epoch):
        if epoch != self._epoch:
            self._epoch, self._stamp, self.seq = epoch, None, 0
        if stamp_s is not None and math.isfinite(stamp_s) and (self._stamp is None or stamp_s > self._stamp):
            self._stamp = stamp_s
            self.seq += 1
        return self.seq


class GripperView:
    """`GripperState` 마지막 수신과 seq 증가 시각(wall). holding() 은 True/False/None."""

    def __init__(self, stale_after_s, held, released):
        self._stale_after_s = stale_after_s
        self._held, self._released = held, released
        self._state = self._epoch = self._seq = None
        self._received_at = self._advanced_at = None
        self._last_applied = 0

    def update(self, epoch, seq, state, wall_now, last_applied=0):
        if self._epoch != epoch or self._seq is None or seq > self._seq:
            self._advanced_at = wall_now
        self._epoch, self._seq, self._state, self._received_at = epoch, seq, state, wall_now
        self._last_applied = int(last_applied)

    def clear(self):
        self._state = self._epoch = self._seq = None
        self._received_at = self._advanced_at = None
        self._last_applied = 0

    def observe(self, epoch, wall_now):
        """(신선한 state 또는 None, last_applied_command_seq, 이유). state 는 HELD·RELEASED 만 신선한 값으로 준다."""
        if self._received_at is None:
            return None, 0, 'GripperState 를 받은 적이 없다'
        if self._epoch != epoch:
            return None, 0, f'GripperState epoch {self._epoch} ≠ {epoch}'
        if wall_now - self._received_at > self._stale_after_s:
            return None, 0, 'GripperState 가 오래됐다'
        if wall_now - self._advanced_at > self._stale_after_s:
            return None, 0, 'GripperState seq 가 늘지 않는다'
        if self._state not in (self._held, self._released):
            return None, self._last_applied, 'GripperState state 가 UNKNOWN 이다'
        return self._state, self._last_applied, ''

    def holding(self, epoch, wall_now):
        """(파지 여부 또는 None, 이유)."""
        state, _applied, reason = self.observe(epoch, wall_now)
        if state is None:
            return None, reason
        return state == self._held, ''

    def command_result(self, epoch, wall_now, command_seq, close):
        """(CONFIRMED·CONTRADICTED·PENDING·UNKNOWN, 이유). command_seq 가 None 이면 명령을 못 냈다 → UNKNOWN."""
        if command_seq is None:
            return UNKNOWN, '흡착 명령을 epoch 없이 낼 수 없었다'
        state, applied, reason = self.observe(epoch, wall_now)
        if state is None:
            return UNKNOWN, reason
        if applied < command_seq:
            return PENDING, f'last_applied {applied} < command_seq {command_seq}'
        want = self._held if close else self._released
        if state == want:
            return CONFIRMED, ''
        return CONTRADICTED, 'HELD' if state == self._held else 'RELEASED'


class CommandSeq:
    """`GripperCommand.command_seq`. epoch 마다 1 부터, 명령마다 +1. `reset()` 은 RESET_DONE 에서 부른다."""

    def __init__(self):
        self.seq = 0
        self._epoch = None

    def next(self, epoch):
        if epoch != self._epoch:
            self._epoch, self.seq = epoch, 0
        self.seq += 1
        return self.seq

    def reset(self):
        self.seq, self._epoch = 0, None
