"""조제기 재고. 약품마다 슬롯 2개, FEFO, 임계값, 정지·재개, 보충 선반. ROS 를 import 하지 않는다.

계약 2.1절: 조제기의 데이터는 orchestrator 가 갖고 isaac 은 물리만 맡는다.
계약 5절: 슬롯 둘 다 0 이면 Dispense 를 호출하지 않고 DISPENSER_PAUSED 와 REFILL_REQUESTED 를 낸다.
"""

from dataclasses import dataclass, replace

SLOT_A = 0
SLOT_B = 1
SLOT_NAMES = {SLOT_A: 'A', SLOT_B: 'B'}

EVENT_PAUSED = 'DISPENSER_PAUSED'
EVENT_RESUMED = 'DISPENSER_RESUMED'
EVENT_REFILL_REQUESTED = 'REFILL_REQUESTED'

REASON_OUT_OF_STOCK = 'out_of_stock'
REASON_UNKNOWN_ITEM = 'unknown_item'


class InventoryError(ValueError):
    """재고 설정이 계약의 2슬롯 규칙을 어겼다."""


@dataclass(frozen=True)
class Slot:
    """캐니스터 하나. DispenserSlot.msg 와 같은 항목이다."""

    item_id: str
    slot: int
    lot_id: str
    expiry: str          # ISO 8601 date. 물리 없이 데이터로만 쓴다
    count: int

    @property
    def empty(self):
        """남은 봉투가 없는가."""
        return self.count <= 0


@dataclass(frozen=True)
class Canister:
    """선반의 캐니스터 하나. 보충하면 빈 슬롯 하나가 이 값이 된다."""

    lot_id: str
    expiry: str          # ISO 8601 date. 물리 없이 데이터로만 쓴다
    count: int


@dataclass(frozen=True)
class TakeResult:
    """배출 한 번의 결과와 그때 내야 할 이벤트."""

    ok: bool
    slot: int = -1
    lot_id: str = ''
    reason: str = ''
    events: tuple = ()


def _slot_key(slot):
    # FEFO: 유통기한이 이른 것부터. 같으면 슬롯 A 를 먼저 쓴다.
    return (slot.expiry, slot.slot)


class DispenserInventory:
    """약품마다 슬롯 2개를 갖는 재고 데이터."""

    def __init__(self, slots, refill_threshold=1, shelf=None):
        self._slots = {}
        for slot in slots:
            self._slots.setdefault(slot.item_id, {})[slot.slot] = slot
        for item_id, by_slot in self._slots.items():
            if set(by_slot) != {SLOT_A, SLOT_B}:
                raise InventoryError(f'{item_id}: 슬롯은 A 와 B 둘이어야 한다. 지금 {sorted(by_slot)}')
        self._threshold = int(refill_threshold)
        # 보충 선반. 약품 ID → 꺼내는 순서대로의 Canister 목록. 없는 약품은 빈 선반이다.
        self._shelf = {item_id: list(canisters) for item_id, canisters in (shelf or {}).items()}
        unknown = sorted(set(self._shelf) - set(self._slots))
        if unknown:
            raise InventoryError(f'선반에 슬롯이 없는 약품이 있다: {unknown}')
        self._paused = {item_id for item_id in self._slots if self._total(item_id) == 0}
        # 보충 요청. 순서가 보충 순서라서 set 이 아니라 dict(삽입 순서) 로 둔다. 값은 쓰지 않는다.
        self._requested = dict.fromkeys(item_id for item_id in self._slots if item_id in self._paused)

    # 조회 ---------------------------------------------------------------

    def items(self):
        """아는 약품 ID."""
        return tuple(sorted(self._slots))

    def knows(self, item_id):
        """이 약품을 아는가."""
        return item_id in self._slots

    def slots(self, item_id=None):
        """슬롯 목록. item_id 를 주면 그 약품만."""
        if item_id is not None:
            return tuple(sorted(self._slots[item_id].values(), key=_slot_key))
        out = []
        for by_slot in self._slots.values():
            out.extend(by_slot.values())
        return tuple(sorted(out, key=lambda s: (s.item_id, s.slot)))

    def active_slot(self, item_id):
        """FEFO 로 지금 쓰는 슬롯. 둘 다 비었으면 None."""
        candidates = [s for s in self._slots.get(item_id, {}).values() if not s.empty]
        return min(candidates, key=_slot_key) if candidates else None

    def is_paused(self, item_id):
        """이 약품의 배출이 멈춰 있는가."""
        return item_id in self._paused

    def paused_items(self):
        """멈춰 있는 약품 ID. DispenserStatus.paused_item_ids 다."""
        return tuple(sorted(self._paused))

    def refill_requests(self):
        """보충을 기다리는 약품 ID, 요청한 순서대로. 이벤트를 한 번만 내도 요청은 풀릴 때까지 남는다."""
        return tuple(self._requested)

    def shelf_peek(self, item_id):
        """다음에 꺼낼 캐니스터. 선반이 비었거나 모르는 약품이면 None. 꺼내지 않는다."""
        canisters = self._shelf.get(item_id)
        return canisters[0] if canisters else None

    def shelf_pop(self, item_id):
        """다음 캐니스터를 선반에서 뺀다. 보충이 성공한 뒤에만 부른다. 비었으면 None."""
        canisters = self._shelf.get(item_id)
        return canisters.pop(0) if canisters else None

    def _total(self, item_id):
        return sum(s.count for s in self._slots[item_id].values())

    # 변경 ---------------------------------------------------------------

    def take(self, item_id):
        """봉투 하나를 활성 슬롯에서 뺀다. 못 빼면 ok=False 와 이유."""
        if not self.knows(item_id):
            return TakeResult(ok=False, reason=REASON_UNKNOWN_ITEM)
        slot = self.active_slot(item_id)
        if slot is None:
            events = ()
            if item_id not in self._paused:
                self._paused.add(item_id)
                events = (EVENT_PAUSED,)
            if item_id not in self._requested:
                self._requested[item_id] = None
                events += (EVENT_REFILL_REQUESTED,)
            return TakeResult(ok=False, reason=REASON_OUT_OF_STOCK, events=events)

        self._slots[item_id][slot.slot] = replace(slot, count=slot.count - 1)
        events = ()
        if self._total(item_id) == 0:
            # 방금 마지막 봉투를 뺐다. 다음 요청 전에 보충이 필요하다.
            self._paused.add(item_id)
            self._requested[item_id] = None
            events = (EVENT_PAUSED, EVENT_REFILL_REQUESTED)
        elif self._total(item_id) <= self._threshold and item_id not in self._requested:
            self._requested[item_id] = None
            events = (EVENT_REFILL_REQUESTED,)
        return TakeResult(ok=True, slot=slot.slot, lot_id=slot.lot_id, events=events)

    def refill(self, item_id, slot, lot_id, expiry, count):
        """빈 슬롯에 캐니스터를 장착한다. 멈춰 있었으면 재개 이벤트를 낸다."""
        if not self.knows(item_id):
            raise InventoryError(f'{item_id}: 모르는 약품이다')
        if slot not in (SLOT_A, SLOT_B):
            raise InventoryError(f'{item_id}: 슬롯은 A(0) 또는 B(1) 다. 받은 값 {slot}')
        if count <= 0:
            raise InventoryError(f'{item_id}: 장착 수량은 1 이상이어야 한다')
        self._slots[item_id][slot] = Slot(item_id=item_id, slot=slot, lot_id=lot_id,
                                          expiry=expiry, count=int(count))
        events = ()
        if item_id in self._paused:
            self._paused.discard(item_id)
            events = (EVENT_RESUMED,)
        if self._total(item_id) > self._threshold:
            self._requested.pop(item_id, None)
        return events


SLOT_KEYS = {'a': SLOT_A, 'b': SLOT_B}
_SLOT_FIELDS = ('slot', 'lot_id', 'expiry', 'count')
_SHELF_FIELDS = ('lot_id', 'expiry', 'count')


def _load_shelf(document):
    """최상위 `shelf:` 를 읽는다. 없으면 빈 선반. 캐니스터 수량은 1 이상이어야 한다."""
    shelf = document.get('shelf')
    if shelf is None:
        return {}
    if not isinstance(shelf, dict):
        raise InventoryError('shelf 는 약품 ID → 캐니스터 목록의 mapping 이어야 한다')
    out = {}
    for item_id, rows in shelf.items():
        if not isinstance(rows, list):
            raise InventoryError(f'shelf.{item_id}: 캐니스터 목록이어야 한다')
        canisters = []
        for row in rows:
            if not isinstance(row, dict):
                raise InventoryError(f'shelf.{item_id}: 캐니스터 한 줄은 mapping 이어야 한다')
            missing = [field for field in _SHELF_FIELDS if field not in row]
            if missing:
                raise InventoryError(f'shelf.{item_id}: {missing} 가 없다')
            if int(row['count']) <= 0:
                raise InventoryError(f'shelf.{item_id}: 캐니스터 수량은 1 이상이어야 한다. 받은 값 {row["count"]!r}')
            canisters.append(Canister(lot_id=str(row['lot_id']), expiry=str(row['expiry']),
                                      count=int(row['count'])))
        out[item_id] = canisters
    return out


def load_inventory(document):
    """읽어 둔 mapping 을 DispenserInventory 로. 규칙을 어기면 InventoryError."""
    if not isinstance(document, dict):
        raise InventoryError('재고 파일의 최상위는 mapping 이어야 한다')
    items = document.get('items')
    if not isinstance(items, dict) or not items:
        raise InventoryError('items 는 비어 있지 않은 mapping 이어야 한다')
    slots = []
    for item_id, rows in items.items():
        if not isinstance(rows, list) or len(rows) != 2:
            raise InventoryError(f'{item_id}: 슬롯 두 줄을 적어야 한다(A 와 B)')
        for row in rows:
            if not isinstance(row, dict):
                raise InventoryError(f'{item_id}: 슬롯 한 줄은 mapping 이어야 한다')
            missing = [field for field in _SLOT_FIELDS if field not in row]
            if missing:
                raise InventoryError(f'{item_id}: {missing} 가 없다')
            key = str(row['slot']).lower()
            if key not in SLOT_KEYS:
                raise InventoryError(f'{item_id}: slot 은 a 또는 b 여야 한다. 받은 값 {row["slot"]!r}')
            slots.append(Slot(item_id=item_id, slot=SLOT_KEYS[key], lot_id=str(row['lot_id']),
                              expiry=str(row['expiry']), count=int(row['count'])))
    return DispenserInventory(slots, document.get('refill_threshold', 1), _load_shelf(document))
