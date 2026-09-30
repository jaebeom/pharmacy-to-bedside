"""fleet 이 Nav2 에 보내는 하위 goal 의 token·epoch·종결 판정. ROS 를 import 하지 않는다. 계약 v1 6절·7절.

GoToZone 하나에 Nav2 goal 하나를 붙이고, 그 goal 이 지금 것인지 token(epoch, seq)으로 가린다.

- 보내기 전: 이미 닫히기 시작했으면(취소·제한 시간·리셋) 보내지 않는다.
- 수락 응답: 지금 token 이 아니거나 닫히는 중이면 곧바로 cancel 한다. 리셋 뒤 늦게 수락된 goal 이 이것이다.
- 결과: 지금 token 이 아니면 버린다.
- 닫기: cancel 을 보낸 뒤 종결을 `cancel_wait_s`(wall)까지만 기다린다. 넘으면 Nav2 답 없이 끝낸다.
- `RESET_DONE`: 마지막으로 본 epoch 보다 크지 않으면 버린다. 새 epoch 이면 진행 중인 goal 을 `reset` 으로 닫는다.

`RESET_BEGIN` 은 다루지 않는다. 계약 6절 0단계가 navigation 의 처리를 아직 정하지 않았다.
시각은 부르는 쪽이 넣는다(steady clock 초). fleet 에는 아직 연결하지 않았다.
"""

import math
from collections import namedtuple

#: 계약 v1 7절 "cancel 종결 대기(wall)" 10 s 를 옮긴 것이다. 새 합격선이 아니다.
CANCEL_WAIT_S = 10.0

#: 닫는 이유. fleet 의 `GoToZone` 결과 `message` 와 같은 낱말이다.
CANCELED = 'canceled'
TIMEOUT = 'timeout'
RESET = 'reset'

#: 수락 응답·닫기 요청에 대한 할 일.
TRACK = 'track'      # 지금 goal 이다. 결과를 기다린다
CANCEL = 'cancel'    # Nav2 goal 에 cancel 을 보낸다
WAIT = 'wait'        # 보냈지만 수락 응답이 아직 없다. 오면 cancel 한다
NOTHING = 'nothing'  # Nav2 로 나간 것이 없거나 이미 닫는 중이다
IGNORED = 'ignored'  # 이전·중복 epoch 의 RESET_DONE

#: `epoch` 은 goal 을 시작할 때 마지막으로 본 RESET_DONE epoch 이다(아직 없으면 None).
Token = namedtuple('Token', ('epoch', 'seq'))


class GoalGuard:
    """GoToZone 하나의 하위 Nav2 goal 을 따라간다. 동시에 하나만."""

    def __init__(self, cancel_wait_s=CANCEL_WAIT_S):
        if not (math.isfinite(cancel_wait_s) and cancel_wait_s > 0.0):
            raise ValueError(f'cancel_wait_s 는 양의 유한값이어야 한다: {cancel_wait_s!r}')
        self._cancel_wait_s = float(cancel_wait_s)
        self._epoch = None
        self._seq = 0
        self._clear()

    def _clear(self):
        self._token = None
        self._sent = False
        self._accepted = False
        self._reason = None
        self._close_deadline = None

    @property
    def token(self):
        return self._token

    @property
    def epoch(self):
        return self._epoch

    @property
    def reason(self):
        """닫는 이유. 닫는 중이 아니면 None."""
        return self._reason

    def begin(self):
        """새 goal 의 token. 진행 중인 goal 이 있으면 None."""
        if self._token is not None:
            return None
        self._seq += 1
        self._token = Token(self._epoch, self._seq)
        return self._token

    def should_send(self, token):
        """Nav2 에 보내도 되는가. 보내기 직전에 본다. 참이면 보낸 것으로 적는다."""
        if token != self._token or self._reason is not None:
            return False
        self._sent = True
        return True

    def on_accepted(self, token):
        """Nav2 수락 응답. `TRACK` 이 아니면 그 goal 에 cancel 을 보낸다."""
        if token != self._token:
            return CANCEL
        self._accepted = True
        return TRACK if self._reason is None else CANCEL

    def on_result(self, token):
        """이 결과가 지금 goal 의 것인가. 아니면 버린다."""
        return token == self._token and self._sent

    def close(self, reason, now):
        """취소·제한 시간·리셋으로 닫기 시작한다. 처음 부른 이유와 마감이 남는다."""
        if self._token is None or self._reason is not None:
            return NOTHING
        self._reason = reason
        self._close_deadline = now + self._cancel_wait_s
        if self._accepted:
            return CANCEL
        return WAIT if self._sent else NOTHING

    def expired(self, now):
        """닫는 중인데 `cancel_wait_s` 안에 종결이 안 왔는가. 참이면 Nav2 답 없이 끝낸다."""
        return self._close_deadline is not None and now >= self._close_deadline

    def finish(self, token):
        """goal 을 끝내고 다음 goal 을 받을 수 있게 한다. 닫는 이유를 돌려준다(정상 종료면 None)."""
        if token != self._token:
            return None
        reason = self._reason
        self._clear()
        return reason

    def on_reset_done(self, epoch, now):
        """`RESET_DONE`. 이전·중복 epoch 은 `IGNORED`. 아니면 진행 중인 goal 을 `reset` 으로 닫는다."""
        if self._epoch is not None and epoch <= self._epoch:
            return IGNORED
        self._epoch = epoch
        return self.close(RESET, now)
