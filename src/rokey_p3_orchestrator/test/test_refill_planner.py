"""보충 클라이언트의 입력 → 명령 표. 앞 절은 가짜 출처(Shelf), 끝 절은 A 안 출처(ShelfSource)다."""

import pytest

from rokey_p3_orchestrator import refill_planner as rp
from rokey_p3_orchestrator.dispenser_inventory import (SLOT_A, SLOT_B, Canister, DispenserInventory, Slot,
                                                      load_inventory)
from rokey_p3_orchestrator.trip_fsm import ACCEPTED, OK, REJECTED, Cancel, Emit, SendGoal

ITEM = 'drug-amox'
OTHER = 'drug-ibu'
NEW = Canister('lot-new', '2028-01-01', 5)


class Shelf:
    """가짜 출처. 캐니스터 하나를 계속 준다."""

    def __init__(self, canister=NEW, available=True):
        self._canister = canister
        self._available = available
        self.consumed_items = []

    def available(self, item_id):
        return self._available

    def canister(self, item_id, detail):
        return self._canister

    def consumed(self, item_id):
        self.consumed_items.append(item_id)


def slots(item, a, b, expiry_a='2027-01-01', expiry_b='2027-06-01'):
    return [Slot(item, SLOT_A, f'lot-{item}-a', expiry_a, a), Slot(item, SLOT_B, f'lot-{item}-b', expiry_b, b)]


def stock(a=3, b=3, threshold=1, **expiry):
    return DispenserInventory(slots(ITEM, a, b, **expiry), refill_threshold=threshold)


def send(item, slot):
    return SendGoal(rp.REFILL, {'item_id': item, 'slot': slot})


def notes(commands, level='warning'):
    return [c.text for c in commands if isinstance(c, rp.Note) and c.level == level]


def without_notes(commands):
    return [c for c in commands if not isinstance(c, rp.Note)]


# 무엇을 언제 보내나 ------------------------------------------------------

def test_threshold_request_sends_one_goal_to_the_empty_slot():
    inventory = stock(a=2, b=0)
    assert inventory.take(ITEM).events == ('REFILL_REQUESTED',)
    planner = rp.RefillPlanner(inventory, Shelf())
    assert planner.tick(0.0) == [send(ITEM, SLOT_B)]
    assert planner.tick(1.0) == []          # 한 번에 하나
    assert planner.active_item == ITEM


def test_no_empty_slot_waits_until_one_empties():
    inventory = stock(a=2, b=1, threshold=2)
    assert inventory.take(ITEM).events == ('REFILL_REQUESTED',)     # A 1, B 1
    planner = rp.RefillPlanner(inventory, Shelf())
    assert planner.tick(0.0) == []           # 덮어쓸 수 없다
    inventory.take(ITEM)                     # A 0
    assert planner.tick(0.1) == [send(ITEM, SLOT_A)]


def test_both_empty_fills_slot_a_only_and_resumes():
    inventory = stock(a=1, b=0)
    assert inventory.take(ITEM).events == ('DISPENSER_PAUSED', 'REFILL_REQUESTED')
    planner = rp.RefillPlanner(inventory, Shelf())
    assert planner.tick(0.0) == [send(ITEM, SLOT_A)]
    assert planner.result(ACCEPTED, 0.1) == []
    assert without_notes(planner.result(OK, 30.0, {'lot_id': 'lot-from-arm'})) == [
        Emit('DISPENSER_RESUMED', robot_id='dispenser')]           # 조제기 이벤트의 robot_id
    assert not inventory.is_paused(ITEM)
    assert inventory.refill_requests() == ()
    assert planner.tick(30.1) == []          # B 는 다음 요청 때


def test_empty_stock_from_the_file_is_refilled_without_an_event():
    planner = rp.RefillPlanner(stock(a=0, b=0), Shelf())
    assert planner.tick(0.0) == [send(ITEM, SLOT_A)]


def test_one_goal_at_a_time_in_request_order():
    inventory = DispenserInventory(slots(ITEM, 1, 0) + slots(OTHER, 1, 0))
    inventory.take(OTHER)
    inventory.take(ITEM)
    assert inventory.refill_requests() == (OTHER, ITEM)
    planner = rp.RefillPlanner(inventory, Shelf())
    assert planner.tick(0.0) == [send(OTHER, SLOT_A)]
    assert planner.tick(1.0) == []
    assert without_notes(planner.result(OK, 20.0)) == [Emit('DISPENSER_RESUMED', robot_id='dispenser')]
    assert planner.tick(20.1) == [send(ITEM, SLOT_A)]


def test_success_writes_the_canister_and_fefo_still_decides():
    shelf = Shelf()
    inventory = stock(a=0, b=2, expiry_b='2027-06-01')
    assert inventory.take(ITEM).events == ('REFILL_REQUESTED',)     # B 1 이 남았다
    planner = rp.RefillPlanner(inventory, shelf)
    assert planner.tick(0.0) == [send(ITEM, SLOT_A)]
    assert without_notes(planner.result(OK, 10.0)) == []    # 멈춘 적이 없어서 재개 이벤트가 없다
    slot_a = [s for s in inventory.slots(ITEM) if s.slot == SLOT_A][0]
    assert (slot_a.lot_id, slot_a.expiry, slot_a.count) == ('lot-new', '2028-01-01', 5)
    assert shelf.consumed_items == [ITEM]
    assert inventory.take(ITEM).slot == SLOT_B          # B 의 유통기한이 더 이르다
    assert inventory.take(ITEM).lot_id == 'lot-new'


@pytest.mark.parametrize(('a', 'b', 'target'), [(0, 0, SLOT_A), (1, 0, SLOT_B), (0, 1, SLOT_A), (1, 1, None)])
def test_a_slot_with_stock_is_never_the_target(a, b, target):
    assert rp.RefillPlanner(stock(a=a, b=b), Shelf()).target_slot(ITEM) == target


# 실패·시한·출처 -----------------------------------------------------------

def test_failure_keeps_the_stock_retries_after_the_delay_then_gives_up():
    inventory = stock(a=0, b=0)
    planner = rp.RefillPlanner(inventory, Shelf(), retry_delay_s=5.0, max_attempts=3)
    assert planner.tick(0.0) == [send(ITEM, SLOT_A)]
    assert len(notes(planner.result(REJECTED, 0.0))) == 1          # 서버 없음도 노드가 거부로 넣는다
    assert inventory.is_paused(ITEM)
    assert planner.tick(4.9) == []
    assert planner.tick(5.0) == [send(ITEM, SLOT_A)]
    planner.result(rp.FAILED, 10.0)
    assert planner.tick(15.0) == [send(ITEM, SLOT_A)]
    gave_up = planner.result(REJECTED, 15.0)
    assert '3/3' in notes(gave_up)[0]
    assert planner.tick(1000.0) == []
    assert inventory.is_paused(ITEM)
    assert [s.count for s in inventory.slots(ITEM)] == [0, 0]


def test_timeout_cancels_and_a_late_result_changes_nothing():
    inventory = stock(a=0, b=0)
    planner = rp.RefillPlanner(inventory, Shelf(), timeout_s=90.0)
    [first] = planner.tick(0.0)
    assert planner.tick(89.9) == []
    commands = planner.tick(90.0)
    assert commands[0] == Cancel(rp.REFILL) and len(notes(commands)) == 1
    assert planner.tick(95.0) == []                                  # cancel 한 goal 이 아직 안 끝났다
    assert planner.result(OK, 96.0, token=first.token) == []         # 늦게 온 성공도 재고를 안 바꾼다
    assert inventory.is_paused(ITEM)
    assert planner.tick(96.1) == [send(ITEM, SLOT_A)]


def test_retry_waits_for_the_cancelled_goal_at_most_cancel_wait_s_wall():
    planner = rp.RefillPlanner(stock(a=0, b=0), Shelf(), timeout_s=90.0, cancel_wait_s=10.0)
    planner.tick(0.0, now_wall=0.0)
    planner.tick(90.0, now_wall=90.0)                                # cancel. 종결은 오지 않는다
    assert planner.tick(95.0, now_wall=99.9) == []
    assert planner.tick(95.0, now_wall=100.0) == [send(ITEM, SLOT_A)]


def test_nothing_is_sent_without_a_source_or_a_canister():
    assert rp.RefillPlanner(stock(a=0, b=0), source=None).tick(0.0) == []
    assert without_notes(rp.RefillPlanner(stock(a=0, b=0), Shelf(available=False)).tick(0.0)) == []


def test_success_without_canister_data_is_a_failure():
    inventory = stock(a=0, b=0)
    planner = rp.RefillPlanner(inventory, Shelf(canister=None))
    planner.tick(0.0)
    assert len(notes(planner.result(OK, 10.0))) == 1
    assert inventory.is_paused(ITEM)


# epoch·리셋 ---------------------------------------------------------------

def test_result_from_an_old_epoch_changes_nothing():
    inventory = stock(a=0, b=0)
    planner = rp.RefillPlanner(inventory, Shelf(), epoch=1)
    planner.tick(0.0)
    assert planner.reset(2, inventory) == [Cancel(rp.REFILL)]
    assert planner.result(OK, 10.0, epoch=1) == []
    assert inventory.is_paused(ITEM)
    assert planner.tick(10.0) == [send(ITEM, SLOT_A)]        # 새 epoch 에서 다시 본다


def test_reset_cancels_only_an_active_goal_and_forgets_given_up_items():
    planner = rp.RefillPlanner(stock(a=0, b=0), Shelf(), max_attempts=1)
    planner.tick(0.0)
    planner.result(REJECTED, 0.0)
    assert planner.tick(100.0) == []                         # 포기했다
    fresh = stock(a=0, b=0)
    assert planner.reset(2, fresh) == []                     # 활성 goal 이 없다
    assert planner.tick(100.0) == [send(ITEM, SLOT_A)]
    assert planner.reset(3, stock()) == [Cancel(rp.REFILL)]
    assert planner.tick(100.0) == []                         # 새 재고에는 요청이 없다


def test_orchestrator_never_emits_refill_done():
    inventory = stock(a=1, b=0)
    inventory.take(ITEM)
    planner = rp.RefillPlanner(inventory, Shelf())
    commands = planner.tick(0.0) + planner.result(ACCEPTED, 0.1) + planner.result(OK, 20.0) + planner.tick(20.1)
    emitted = [c.event for c in commands if isinstance(c, Emit)]
    assert emitted == ['DISPENSER_RESUMED']


# A 안 출처: 재고 파일의 선반 ----------------------------------------------

SHELF_DOCUMENT = {
    'refill_threshold': 1,
    'items': {ITEM: [
        {'slot': 'a', 'lot_id': 'lot-amox-01', 'expiry': '2027-03-31', 'count': 0},
        {'slot': 'b', 'lot_id': 'lot-amox-02', 'expiry': '2027-09-30', 'count': 2},
    ]},
    'shelf': {ITEM: [
        {'lot_id': 'lot-amox-03', 'expiry': '2028-03-31', 'count': 5},
        {'lot_id': 'lot-amox-04', 'expiry': '2028-09-30', 'count': 5},
    ]},
}


def shelf_planner(document=None, **kwargs):
    inventory = load_inventory(document or SHELF_DOCUMENT)
    holder = {'inventory': inventory}
    planner = rp.RefillPlanner(inventory, rp.ShelfSource(lambda: holder['inventory']), **kwargs)
    return planner, holder


def reset(planner, holder, epoch, document=None):
    """노드의 _on_reset 처럼 파일을 다시 읽어 두 곳에 같은 재고를 준다."""
    holder['inventory'] = load_inventory(document or SHELF_DOCUMENT)
    return planner.reset(epoch, holder['inventory'])


def test_shelf_is_peeked_at_send_and_popped_only_on_success():
    planner, holder = shelf_planner()
    inventory = holder['inventory']
    inventory.take(ITEM)                                       # B 1 → 요청
    assert planner.tick(0.0) == [send(ITEM, SLOT_A)]
    assert inventory.shelf_peek(ITEM).lot_id == 'lot-amox-03'  # 보냈지만 아직 선반에 있다
    planner.result(REJECTED, 0.0)
    assert inventory.shelf_peek(ITEM).lot_id == 'lot-amox-03'  # 실패는 꺼내지 않는다
    assert planner.tick(5.0) == [send(ITEM, SLOT_A)]
    commands = planner.result(OK, 30.0, {'lot_id': 'lot-drug-amox-01'})
    assert inventory.shelf_peek(ITEM).lot_id == 'lot-amox-04'
    slot_a = [s for s in inventory.slots(ITEM) if s.slot == SLOT_A][0]
    assert (slot_a.lot_id, slot_a.expiry, slot_a.count) == ('lot-amox-03', '2028-03-31', 5)
    assert 'arm lot_id=lot-drug-amox-01' in notes(commands, 'info')[0]     # arm 의 값은 기록만


def test_refill_adds_to_the_stock_and_leaves_the_other_slot_alone():
    planner, holder = shelf_planner()
    inventory = holder['inventory']
    inventory.take(ITEM)
    before = {s.slot: s.count for s in inventory.slots(ITEM)}
    planner.tick(0.0)
    planner.result(OK, 30.0)
    after = {s.slot: s.count for s in inventory.slots(ITEM)}
    assert after[SLOT_B] == before[SLOT_B] == 1               # 남은 약은 버리지 않는다
    assert sum(after.values()) == sum(before.values()) + 5


def test_empty_shelf_sends_nothing_and_says_so_once():
    document = dict(SHELF_DOCUMENT, shelf={ITEM: []})
    planner, holder = shelf_planner(document)
    holder['inventory'].take(ITEM)
    first = planner.tick(0.0)
    assert without_notes(first) == [] and len(notes(first)) == 1
    assert planner.tick(1.0) == []


def test_shelf_runs_out_after_its_canisters():
    planner, holder = shelf_planner(document=dict(SHELF_DOCUMENT, shelf={ITEM: SHELF_DOCUMENT['shelf'][ITEM][:1]}))
    inventory = holder['inventory']
    inventory.take(ITEM)
    planner.tick(0.0)
    planner.result(OK, 30.0)                                   # A 5, B 1
    for _ in range(5):
        inventory.take(ITEM)                                   # B 1 → A 5 중 4 → 합 1 이하로 요청
    assert inventory.refill_requests() == (ITEM,)
    commands = planner.tick(60.0)
    assert without_notes(commands) == [] and len(notes(commands)) == 1


def test_reset_restores_the_shelf_from_the_file():
    planner, holder = shelf_planner()
    holder['inventory'].take(ITEM)
    planner.tick(0.0)
    planner.result(OK, 30.0)
    assert holder['inventory'].shelf_peek(ITEM).lot_id == 'lot-amox-04'
    assert reset(planner, holder, 2) == []
    assert holder['inventory'].shelf_peek(ITEM).lot_id == 'lot-amox-03'

