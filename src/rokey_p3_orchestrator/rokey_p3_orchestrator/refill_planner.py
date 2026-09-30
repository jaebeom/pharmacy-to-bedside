"""조제기 보충(Refill) 클라이언트의 판단. ROS 를 import 하지 않는다.

orchestrator 노드 안, 트립 FSM 밖에 있다. 노드가 tick·액션 결과·리셋을 넣고 돌려받은 명령
(trip_fsm 의 `SendGoal`·`Cancel`·`Emit` 과 여기의 `Note`)을 ROS 로 옮긴다. 트립과 병렬로 돈다.

계약 2.3절 `/m0609/refill` (90 s sim), 2.6절(`REFILL_DONE` 은 m0609/arm, `DISPENSER_RESUMED` 는
orchestrator 가 낸다), 4절(이전 epoch 의 결과는 버린다), 6절 1(리셋은 활성 `Refill` 을 cancel 한다).

- 보낼 약품은 재고의 `refill_requests()` 순서다. 이벤트가 아니라 상태를 읽으므로 실패 뒤 재시도,
  0/0 으로 시작한 재고, 리셋 뒤 새 재고를 같은 길로 본다.
- goal 은 한 번에 하나다. M0609 는 한 대다.
- 보충할 슬롯은 그 약품의 빈 슬롯 중 A 먼저다. 비지 않은 슬롯은 대상이 아니다. `inventory.refill` 은
  슬롯을 덮어쓰고, 보충은 추가이지 교체가 아니다(시나리오 4절 단계 1). 빈 슬롯이 없으면 기다린다.
  둘 다 비었으면 A 만 채운다. 재개가 빠르고, B 는 다음 요청 때 채운다.
- 실패(거부·서버 없음·success=false·시한 초과)는 재고를 건드리지 않는다. `retry_delay_s` 뒤 다시 보내고
  `max_attempts` 번째 실패면 리셋 전까지 그 약품을 포기한다.
- goal 마다 `Token(epoch, 'refill', seq)` 을 붙인다. 결과의 token 이 지금 활성 goal 과 다르면 버린다.
  시한 초과로 cancel 한 goal 의 늦은 성공이 재시도 goal 대신 재고·선반을 바꾸지 못한다.
- 시한 초과로 cancel 한 goal 이 종결될 때까지(또는 `cancel_wait_s` wall) 재시도 goal 을 보내지 않는다.
  M0609 한 대에 goal 두 개가 겹치지 않게 한다(트립 FSM 과 같은 규칙).
- 장착한 캐니스터의 로트·유통기한·수량은 `source` 가 준다. source 가 없으면 goal 을 보내지 않는다.
  지금 출처는 `ShelfSource` 다. 재고 파일의 선반(orchestrator 데이터, 계약 2.1절 끝)에서 꺼내고,
  arm 결과의 `lot_id` 는 기록용이라 로그에만 남긴다.
"""

from rokey_p3_orchestrator.dispenser_inventory import SLOT_NAMES
from rokey_p3_orchestrator.trip_fsm import ACCEPTED, OK, ROBOT_DISPENSER, Cancel, Emit, Note, SendGoal, Token

REFILL = 'refill'
FAILED = 'failed'
OWNER_REFILL = 'refill'


class ShelfSource:
    """A 안 출처: 재고 파일의 선반. 전송 때 peek, 성공 때 pop 한다.

    `inventory()` 는 지금 재고를 돌려주는 함수다. 리셋하면 노드가 재고를 파일에서 다시 읽으므로
    선반도 그 값으로 돌아간다. arm 결과의 `lot_id` 는 재고에 쓰지 않는다(재고는 선반 값).
    """

    def __init__(self, inventory):
        self._inventory = inventory

    def available(self, item_id):
        return self._inventory().shelf_peek(item_id) is not None

    def canister(self, item_id, detail):
        return self._inventory().shelf_peek(item_id)

    def consumed(self, item_id):
        self._inventory().shelf_pop(item_id)


class RefillPlanner:
    """보충 goal 을 언제·무엇으로 보내고 결과를 재고에 어떻게 넣을지.

    `source` 는 세 메서드를 갖는다.

    - `available(item_id)`: 이 약품의 캐니스터를 지금 줄 수 있는가.
    - `canister(item_id, detail)`: 성공한 결과로 장착된 `dispenser_inventory.Canister`. 모르면 None.
      `detail` 은 액션 결과(`lot_id`)다.
    - `consumed(item_id)`: 재고에 반영한 뒤 한 번 부른다.
    """

    def __init__(self, inventory, source=None, retry_delay_s=5.0, max_attempts=3, timeout_s=90.0, epoch=1,
                 cancel_wait_s=10.0):
        self.inventory = inventory
        self.source = source
        self._retry_delay_s = float(retry_delay_s)
        self._max_attempts = int(max_attempts)
        self._timeout_s = float(timeout_s)
        self._cancel_wait_s = float(cancel_wait_s)
        self._epoch = epoch
        self._seq = 0
        self._clear()

    def _clear(self):
        self._active = None          # (item_id, slot, deadline, token)
        self._attempts = {}
        self._retry_at = {}
        self._given_up = set()
        self._noted_unavailable = set()
        self._draining = {}          # 시한 초과로 cancel 한 token → 종결을 기다리는 wall 상한(None 이면 모름)

    @property
    def active_item(self):
        """보충 중인 약품. 없으면 빈 문자열."""
        return self._active[0] if self._active else ''

    def target_slot(self, item_id):
        """빈 슬롯 중 A 먼저. 빈 슬롯이 없으면 None."""
        empty = [slot.slot for slot in self.inventory.slots(item_id) if slot.empty]
        return min(empty) if empty else None

    # 입력 ---------------------------------------------------------------

    def tick(self, now, now_wall=None):
        """시한 초과를 보고, 한가하면 다음 goal 을 낸다. `now` 는 sim time(계약 4절), `now_wall` 은 cancel 대기 상한."""
        if self._active is not None:
            if now < self._active[2]:
                return []
            token = self._active[3]
            self._draining[token] = None if now_wall is None else now_wall + self._cancel_wait_s
            return [Cancel(REFILL, token=token)] + self._failed(now, f'timeout {self._timeout_s:g} s')
        if now_wall is not None:
            for token, until in list(self._draining.items()):
                if until is not None and now_wall >= until:
                    del self._draining[token]
        if self._draining:
            return []                # cancel 한 goal 이 아직 안 끝났다. 대체 goal 을 보내지 않는다
        if self.inventory is None or self.source is None:
            return []
        out = []
        for item_id in self.inventory.refill_requests():
            if item_id in self._given_up or now < self._retry_at.get(item_id, now):
                continue
            slot = self.target_slot(item_id)
            if slot is None:
                continue
            if not self.source.available(item_id):
                if item_id not in self._noted_unavailable:     # 리셋 전까지 한 번만 남긴다
                    self._noted_unavailable.add(item_id)
                    out.append(Note(f'Refill {item_id}: 선반에 캐니스터가 없다. 보충하지 않는다.'))
                continue
            self._seq += 1
            token = Token(self._epoch, OWNER_REFILL, self._seq)
            self._active = (item_id, slot, now + self._timeout_s, token)
            return out + [SendGoal(REFILL, {'item_id': item_id, 'slot': slot}, token=token)]
        return out

    def result(self, outcome, now, detail=None, epoch=None, token=None):
        """goal 수락·거부 또는 결과 하나. 성공이면 재고에 넣고 재고가 낸 이벤트를 돌려준다."""
        if epoch is not None and epoch != self._epoch:
            return []            # 계약 4절: 이전 epoch 의 결과는 버린다
        if token is not None and token in self._draining:
            if outcome != ACCEPTED:
                del self._draining[token]      # cancel 한 goal 이 끝났다. 다음 tick 에 재시도할 수 있다
            return []
        if token is not None and (self._active is None or token != self._active[3]):
            return []            # 같은 epoch 의 이전 goal 이다. 재고·선반을 건드리지 않는다
        if outcome == ACCEPTED or self._active is None:
            return []            # 시한 초과로 이미 닫은 goal 의 늦은 결과도 여기서 버린다
        if outcome != OK:
            return self._failed(now, outcome)
        item_id, slot, _, _ = self._active
        canister = self.source.canister(item_id, detail or {}) if self.source is not None else None
        if canister is None or canister.count <= 0:
            return self._failed(now, '장착한 캐니스터의 데이터가 없다')
        events = self.inventory.refill(item_id, slot, canister.lot_id, canister.expiry, canister.count)
        self.source.consumed(item_id)
        self._active = None
        self._attempts.pop(item_id, None)
        self._retry_at.pop(item_id, None)
        reported = (detail or {}).get('lot_id', '')
        mismatch = ' (다르다. 재고는 선반 값)' if reported and reported != canister.lot_id else ''
        note = Note(f'Refill {item_id} 슬롯 {SLOT_NAMES[slot]}: {canister.lot_id} {canister.count}개 장착. '
                    f'arm lot_id={reported or "-"}{mismatch}', level='info')
        return [note] + [Emit(name, robot_id=ROBOT_DISPENSER) for name in events]

    def reset(self, epoch, inventory):
        """리셋 barrier 1단계(계약 6절). 활성 goal 을 cancel 하고 새 재고로 처음부터 본다."""
        out = [Cancel(REFILL, token=self._active[3])] if self._active is not None else []
        self._clear()
        self._epoch = epoch
        self.inventory = inventory
        return out

    # 내부 ---------------------------------------------------------------

    def _failed(self, now, reason):
        item_id = self._active[0]
        self._active = None
        attempts = self._attempts.get(item_id, 0) + 1
        self._attempts[item_id] = attempts
        if attempts >= self._max_attempts:
            self._given_up.add(item_id)
            return [Note(f'Refill {item_id}: {attempts}/{self._max_attempts} 번째 실패({reason}). '
                         '리셋 전까지 보충하지 않는다. 재고는 그대로다.')]
        self._retry_at[item_id] = now + self._retry_delay_s
        return [Note(f'Refill {item_id}: {attempts}/{self._max_attempts} 번째 실패({reason}). '
                     f'{self._retry_delay_s:g} s 뒤 다시 보낸다.')]
