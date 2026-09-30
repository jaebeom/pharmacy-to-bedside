"""기다리는 이유를 사람이 읽는 로그로. ROS 를 import 하지 않는다.

트립이 guard(계약 5절 인터락, 벨트 상태 등)로 멈춰 있으면 period_s(wall)마다 WARN 한 줄을 낸다.
풀리면, WARN 을 한 번이라도 냈을 때만 INFO 한 줄을 낸다. 짧게 기다리고 풀린 경우는 0줄이다.
Isaac 이나 스텁을 안 띄워 벨트·인터락 신호가 끊긴 것을 시연 로그(관제 웹의 /rosout)에서 바로 알 수 있게 한다.
"""

WARN = 'warn'
INFO = 'info'


class WaitReport:
    """TripFsm.wait_reason() 의 결과를 tick 마다 넣으면 낼 로그 줄 목록을 돌려준다."""

    def __init__(self, period_s=5.0):
        self.period_s = float(period_s)
        self._kind = None
        self._started = None
        self._warned_at = None

    def update(self, wait, now_wall):
        """wait: (대기 이름, 이유) 또는 None. 반환: [(WARN 또는 INFO, 문장)]."""
        out = []
        kind = wait[0] if wait else None
        if self._kind is not None and kind != self._kind:
            if self._warned_at is not None:
                out.append((INFO, f'{self._kind} 대기 끝. {now_wall - self._started:.0f} s 기다렸다.'))
            self._kind = self._started = self._warned_at = None
        if wait is None:
            return out
        if self._kind is None:
            self._kind, self._started = kind, now_wall
        last = self._started if self._warned_at is None else self._warned_at
        if now_wall - last >= self.period_s:
            self._warned_at = now_wall
            out.append((WARN, f'{kind} 대기 {now_wall - self._started:.0f} s: {wait[1]}'))
        return out
