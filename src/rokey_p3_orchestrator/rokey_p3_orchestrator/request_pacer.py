"""order_generator 가 언제 어느 요청을 보낼지. ROS 를 import 하지 않는다.

큐 순서는 order_pool.RequestQueue(긴급 먼저), request_id 는 order_pool.request_id 다.
여기서 더하는 것은 epoch 를 따라 큐를 다시 채우는 것과 리셋 barrier 동안 보내지 않는 것이다.

계약 6절 5: orchestrator 는 RESET_DONE 뒤 3 s wall 동안 새 요청을 거부한다. 거부는 계약 2.5절대로
그 요청을 버리는 것이라, 발행기가 그 사이에 보내면 긴급 요청까지 사라진다. 그래서 발행기는
새 epoch 의 RESET_DONE 을 본 뒤 settle_s(wall) 가 지나야 보낸다. epoch 만 오르고 RESET_DONE 을
아직 못 봤으면(이벤트 순서) 그때도 보내지 않는다. 시작 epoch 는 리셋 없이 열려 있다.
"""

from rokey_p3_orchestrator.order_pool import RequestQueue, request_id
from rokey_p3_orchestrator.trip_fsm import EVENT_RESET_DONE


class RequestPacer:
    """요청 큐와 리셋 대기. 노드는 /events 를 observe 로 넣고 tick 마다 take 한다."""

    def __init__(self, requests, settle_s, epoch=1):
        self._requests = tuple(requests)
        self._settle_s = float(settle_s)
        self.epoch = epoch
        self._reset_done_epoch = epoch      # 이 epoch 의 RESET_DONE 을 봤다. 시작 epoch 는 본 것으로 친다
        self._open_at = float('-inf')
        self._refill()

    def _refill(self):
        self.queue = RequestQueue(self._requests)
        self.seq = 0

    def observe(self, name, epoch, now):
        """/events 한 건. epoch 가 올랐으면 True 이고 큐와 seq 를 처음부터 다시 쓴다(계약 6절 3)."""
        raised = epoch > self.epoch
        if raised:
            self.epoch = epoch
            self._refill()
        if name == EVENT_RESET_DONE and epoch == self.epoch and self._reset_done_epoch != epoch:
            # 같은 RESET_DONE 이 래치로 다시 와도 대기를 늘리지 않는다.
            self._reset_done_epoch = epoch
            self._open_at = now + self._settle_s
        return raised

    def holding(self, now):
        """지금 보내면 안 되는 이유. 보내도 되면 빈 문자열."""
        if self._reset_done_epoch != self.epoch:
            return f'epoch {self.epoch} 의 RESET_DONE 을 아직 못 봤다'
        if now < self._open_at:
            return f'RESET_DONE 뒤 {self._settle_s:g} s 를 기다린다'
        return ''

    def take(self, now):
        """보낼 요청 하나와 그 request_id. 기다려야 하거나 큐가 비었으면 None."""
        if self.holding(now) or not self.queue:
            return None
        pending = self.queue.pop()
        self.seq += 1
        return request_id(self.epoch, self.seq), pending
