"""리셋 barrier 동안 팔 명령을 막는 울타리와 sim 정지 감시. ROS 를 import 하지 않는다.

계약 6절 0: orchestrator 가 `RESET_BEGIN`(새 epoch)을 내면 UR5·M0609 제어 노드는 같은 epoch 의 `RESET_DONE`
까지 기존 실행·홈 복귀의 명령 발행을 멈추고 초기 자세 복원을 isaac 에 양보한다.
관측(정비 4호): cancel 뒤 m0609_arm 의 홈 복귀 명령(20 Hz)이 스텁 리셋을 0.1 s 안에 덮어썼다.

노드는 `/events` 를 받을 때 `begin`·`done` 을 부르고, 명령을 내기 전에 `fenced` 를, 오래 도는 작업(goal 실행,
홈 복귀)은 시작할 때 잡은 `generation` 이 바뀌었는지를 본다. barrier 경계(begin·done)마다 세대가 바뀌므로
그 전에 시작한 작업은 울타리가 풀린 뒤에도 다시 명령을 내지 않는다.
"""

import time


class ResetFence:
    """RESET_BEGIN 부터 같은 epoch 의 RESET_DONE 까지 닫힌다. 중복·이전 epoch 신호는 멱등이다.

    지금 orchestrator 처럼 RESET_BEGIN 없이 RESET_DONE 만 오면 울타리는 닫히지 않고 세대만 바뀐다.
    """

    def __init__(self):
        self.fenced_epoch = None     # 닫힌 barrier 의 epoch. None 이면 열려 있다
        self.done_epoch = 0          # 처리한 RESET_DONE 중 가장 큰 epoch
        self.generation = 0

    @property
    def fenced(self):
        return self.fenced_epoch is not None

    def begin(self, epoch):
        """RESET_BEGIN. 새로 닫았으면 True. 이미 끝난 epoch 나 같은(또는 더 작은) barrier 는 False."""
        if epoch <= self.done_epoch or (self.fenced_epoch is not None and epoch <= self.fenced_epoch):
            return False
        self.fenced_epoch = epoch
        self.generation += 1
        return True

    def accepts_done(self, epoch):
        """이 RESET_DONE 을 아직 처리하지 않았나."""
        return epoch > self.done_epoch

    def done(self, epoch):
        """RESET_DONE. 처음이면 True. 그 epoch 이상을 막던 울타리면 연다. 더 새 barrier 가 닫혀 있으면 둔다."""
        if not self.accepts_done(epoch):
            return False
        self.done_epoch = epoch
        if self.fenced_epoch is not None and self.fenced_epoch <= epoch:
            self.fenced_epoch = None
        self.generation += 1
        return True


class ClockWatch:
    """sim time 이 wall 로 멈춰 있는지 본다. 계약 4절: `/clock` 2.0 s 미수신이면 시뮬 정지.

    sim time 이 바뀌면(리셋으로 작아져도) 진행으로 본다. RESET_DONE 에서 `rebase` 로 기준을 다시 잡는다.
    """

    def __init__(self, sim_now, limit_s=2.0, wall=time.monotonic):
        self._now_wall = wall
        self._limit_s = limit_s
        self.rebase(sim_now)

    def rebase(self, sim_now):
        """새 기준. 리셋 뒤 sim time 이 작아졌어도 여기서부터 잰다."""
        self._sim = sim_now
        self._wall = self._now_wall()

    def stalled(self, sim_now):
        if sim_now != self._sim:
            self._sim = sim_now
            self._wall = self._now_wall()
            return False
        return self._now_wall() - self._wall > self._limit_s
