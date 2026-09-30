import pytest

from rokey_p3_orchestrator.dispenser_inventory import (
    DispenserInventory, InventoryError, Slot, SLOT_A, SLOT_B)

ITEM = 'drug-amox'


def inventory(count_a=3, count_b=3, threshold=1, expiry_a='2027-01-01', expiry_b='2027-06-01'):
    return DispenserInventory([
        Slot(ITEM, SLOT_A, 'lot-a', expiry_a, count_a),
        Slot(ITEM, SLOT_B, 'lot-b', expiry_b, count_b),
    ], refill_threshold=threshold)


def test_two_slots_are_required():
    with pytest.raises(InventoryError):
        DispenserInventory([Slot(ITEM, SLOT_A, 'lot-a', '2027-01-01', 1)])


def test_fefo_uses_the_earliest_expiry_first():
    stock = inventory(expiry_a='2027-06-01', expiry_b='2027-01-01')
    assert stock.active_slot(ITEM).slot == SLOT_B
    assert stock.take(ITEM).slot == SLOT_B


def test_fefo_falls_back_to_slot_a_on_a_tie():
    stock = inventory(expiry_a='2027-01-01', expiry_b='2027-01-01')
    assert stock.take(ITEM).slot == SLOT_A


def test_take_moves_to_the_other_slot_when_one_empties():
    stock = inventory(count_a=1, count_b=2)
    assert stock.take(ITEM).slot == SLOT_A
    assert stock.take(ITEM).slot == SLOT_B
    assert stock.active_slot(ITEM).slot == SLOT_B


def test_last_pouch_pauses_and_asks_for_a_refill():
    stock = inventory(count_a=1, count_b=0)
    result = stock.take(ITEM)
    assert result.ok
    assert result.events == ('DISPENSER_PAUSED', 'REFILL_REQUESTED')
    assert stock.is_paused(ITEM)
    assert stock.paused_items() == (ITEM,)


def test_take_on_an_empty_dispenser_fails_without_dispensing():
    stock = inventory(count_a=0, count_b=0)
    result = stock.take(ITEM)
    assert not result.ok
    assert result.reason == 'out_of_stock'
    assert stock.active_slot(ITEM) is None


def test_threshold_fires_once_before_the_slots_run_out():
    stock = inventory(count_a=3, count_b=0, threshold=2)
    assert stock.take(ITEM).events == ('REFILL_REQUESTED',)   # 남은 2개가 임계값이다
    assert stock.take(ITEM).events == ()                      # 이미 요청했다. 다시 내지 않는다
    assert stock.take(ITEM).events == ('DISPENSER_PAUSED', 'REFILL_REQUESTED')
    assert not stock.take(ITEM).ok


def test_threshold_can_fire_again_after_a_refill():
    stock = inventory(count_a=3, count_b=0, threshold=2)
    stock.take(ITEM)
    assert stock.refill(ITEM, SLOT_B, 'lot-c', '2027-09-01', 5) == ()
    for _ in range(4):
        stock.take(ITEM)
    assert stock.take(ITEM).events == ('REFILL_REQUESTED',)


def test_refill_resumes_a_paused_item():
    stock = inventory(count_a=0, count_b=0)
    assert stock.is_paused(ITEM)
    assert stock.refill(ITEM, SLOT_A, 'lot-c', '2027-09-01', 5) == ('DISPENSER_RESUMED',)
    assert not stock.is_paused(ITEM)
    assert stock.take(ITEM).lot_id == 'lot-c'


def test_refill_requests_keep_the_request_order():
    stock = DispenserInventory([
        Slot(ITEM, SLOT_A, 'lot-a', '2027-01-01', 1), Slot(ITEM, SLOT_B, 'lot-b', '2027-06-01', 0),
        Slot('drug-ibu', SLOT_A, 'lot-c', '2027-01-01', 1), Slot('drug-ibu', SLOT_B, 'lot-d', '2027-06-01', 0),
    ])
    assert stock.refill_requests() == ()
    stock.take('drug-ibu')
    stock.take(ITEM)
    assert stock.refill_requests() == ('drug-ibu', ITEM)


def test_refill_request_stays_until_a_refill_lifts_it():
    stock = inventory(count_a=3, count_b=0, threshold=2)
    stock.take(ITEM)
    assert stock.refill_requests() == (ITEM,)
    assert stock.take(ITEM).events == ()                      # 이벤트는 한 번이지만 요청은 남는다
    assert stock.refill_requests() == (ITEM,)
    stock.refill(ITEM, SLOT_B, 'lot-c', '2027-09-01', 5)
    assert stock.refill_requests() == ()


def test_an_empty_item_in_the_file_is_already_requested():
    assert inventory(count_a=0, count_b=0).refill_requests() == (ITEM,)


def test_refill_of_a_running_item_emits_nothing():
    stock = inventory()
    assert stock.refill(ITEM, SLOT_B, 'lot-c', '2027-09-01', 5) == ()


@pytest.mark.parametrize('kwargs', [
    {'item_id': 'drug-other', 'slot': SLOT_A, 'count': 1},
    {'item_id': ITEM, 'slot': 7, 'count': 1},
    {'item_id': ITEM, 'slot': SLOT_A, 'count': 0},
])
def test_refill_rejects_bad_arguments(kwargs):
    stock = inventory()
    with pytest.raises(InventoryError):
        stock.refill(kwargs['item_id'], kwargs['slot'], 'lot-c', '2027-09-01', kwargs['count'])


def test_unknown_item_is_reported_not_raised():
    result = inventory().take('drug-other')
    assert not result.ok
    assert result.reason == 'unknown_item'


def test_slots_view_is_sorted_and_carries_the_lot_data():
    stock = inventory()
    assert [s.slot for s in stock.slots(ITEM)] == [SLOT_A, SLOT_B]
    assert [s.lot_id for s in stock.slots()] == ['lot-a', 'lot-b']
    assert stock.items() == (ITEM,)


def test_load_inventory_reads_two_slots_per_item():
    from rokey_p3_orchestrator.dispenser_inventory import load_inventory
    stock = load_inventory({'refill_threshold': 2, 'items': {ITEM: [
        {'slot': 'a', 'lot_id': 'lot-a', 'expiry': '2027-01-01', 'count': 4},
        {'slot': 'b', 'lot_id': 'lot-b', 'expiry': '2027-02-01', 'count': 4},
    ]}})
    assert stock.items() == (ITEM,)
    assert stock.active_slot(ITEM).lot_id == 'lot-a'


@pytest.mark.parametrize('document', [
    {'items': {}},
    {'items': {ITEM: [{'slot': 'a', 'lot_id': 'x', 'expiry': '2027-01-01', 'count': 1}]}},
    {'items': {ITEM: ['not-a-mapping', 'nor-this']}},
    {'items': {ITEM: [{'slot': 'c', 'lot_id': 'x', 'expiry': '2027-01-01', 'count': 1},
                      {'slot': 'b', 'lot_id': 'y', 'expiry': '2027-01-01', 'count': 1}]}},
])
def test_load_inventory_rejects_bad_documents(document):
    from rokey_p3_orchestrator.dispenser_inventory import load_inventory
    with pytest.raises(InventoryError):
        load_inventory(document)


def shelf_document(shelf):
    return {'items': {ITEM: [
        {'slot': 'a', 'lot_id': 'lot-a', 'expiry': '2027-01-01', 'count': 1},
        {'slot': 'b', 'lot_id': 'lot-b', 'expiry': '2027-02-01', 'count': 1},
    ]}, 'shelf': shelf}


def test_load_inventory_reads_the_shelf_in_order():
    from rokey_p3_orchestrator.dispenser_inventory import load_inventory
    stock = load_inventory(shelf_document({ITEM: [
        {'lot_id': 'lot-c', 'expiry': '2028-01-01', 'count': 5},
        {'lot_id': 'lot-d', 'expiry': '2028-06-01', 'count': 4},
    ]}))
    assert stock.shelf_peek(ITEM).lot_id == 'lot-c'
    assert stock.shelf_peek(ITEM).lot_id == 'lot-c'            # peek 는 꺼내지 않는다
    assert stock.shelf_pop(ITEM).lot_id == 'lot-c'
    assert stock.shelf_pop(ITEM).count == 4
    assert stock.shelf_pop(ITEM) is None
    assert stock.shelf_peek('drug-other') is None


def test_missing_shelf_is_an_empty_shelf():
    from rokey_p3_orchestrator.dispenser_inventory import load_inventory
    document = shelf_document(None)
    del document['shelf']
    assert load_inventory(document).shelf_peek(ITEM) is None


@pytest.mark.parametrize('shelf', [
    ['not-a-mapping'],
    {ITEM: 'not-a-list'},
    {ITEM: ['not-a-mapping']},
    {ITEM: [{'lot_id': 'lot-c', 'count': 5}]},
    {ITEM: [{'lot_id': 'lot-c', 'expiry': '2028-01-01', 'count': 0}]},
    {'drug-other': [{'lot_id': 'lot-c', 'expiry': '2028-01-01', 'count': 5}]},
])
def test_load_inventory_rejects_bad_shelves(shelf):
    from rokey_p3_orchestrator.dispenser_inventory import load_inventory
    with pytest.raises(InventoryError):
        load_inventory(shelf_document(shelf))



def test_hospital_v0_file_asks_for_one_module_and_one_cylinder_refill():
    """재범 v0(9/23): 한 바퀴에 약통(원통)과 약 모듈을 각각 집어 넣는 것이 보여야 한다.

    모듈(drug-ibu)은 두 슬롯이 비어 기동 때부터 요청이고, 원통(drug-amox)은 첫 봉투를 내면 요청이다.
    문턱 아래로만 둔 재고는 `take()` 없이는 요청이 안 난다 — 그래서 ibu 는 0/0 이어야 한다.
    """
    import os

    import yaml

    from rokey_p3_orchestrator.dispenser_inventory import load_inventory

    path = os.path.join(os.path.dirname(__file__), '..', 'config', 'dispenser.hospital-v0.yaml')
    with open(path, encoding='utf-8') as fh:
        stock = load_inventory(yaml.safe_load(fh))
    assert stock.refill_requests() == ('drug-ibu',)      # 모듈: 주문 없이 기동 직후
    result = stock.take('drug-amox')                     # ord-0001 한 봉투
    assert result.ok and result.slot == SLOT_A
    assert result.events == ('REFILL_REQUESTED',)
    assert stock.refill_requests() == ('drug-ibu', 'drug-amox')
    assert not stock.is_paused('drug-amox')              # 조제는 멈추지 않는다


def test_concurrent_refill_file_asks_for_a_refill_on_the_first_pouch():
    """발표 평가 '다중 로봇 조율'(#527 R): 첫 amox 봉투를 내는 순간 보충을 요청해야 한 바퀴 안에서
    M0609 보충과 AMR 이송이 겹친다. 조제는 멈추지 않는다(슬롯 a 에 하나가 남는다)."""
    import os

    import yaml

    from rokey_p3_orchestrator.dispenser_inventory import load_inventory

    path = os.path.join(os.path.dirname(__file__), '..', 'config', 'dispenser.concurrent-refill.yaml')
    with open(path, encoding='utf-8') as fh:
        stock = load_inventory(yaml.safe_load(fh))
    result = stock.take('drug-amox')
    assert result.ok and result.slot == SLOT_A
    assert result.events == ('REFILL_REQUESTED',)
    assert not stock.is_paused('drug-amox')
    assert stock.take('drug-ibu').events == ()


def test_hospital_v0_overlaps_the_cylinder_refill_with_the_delivery():
    """재범 카드 9/23: 한 바퀴 안에서 보충과 배송이 겹쳐야 한다.

    원통 보충 요청이 **첫 봉투를 내는 순간** 나야 AMR 이 그 봉투를 싣고 가는 동안 M0609 가 움직인다.
    조제가 멈추면 안 된다(슬롯 a 에 하나가 남는다) — 멈추면 다음 주문이 거부된다.
    겹쳤는지는 회차의 오케스트레이터 info 로그 `refill_overlap send … overlap=yes` 로 본다
    (`trip_fsm.DELIVERY_STATES`, `events.jsonl` 에는 없다).
    """
    import os

    import yaml

    from rokey_p3_orchestrator.dispenser_inventory import load_inventory

    path = os.path.join(os.path.dirname(__file__), '..', 'config', 'dispenser.hospital-v0.yaml')
    with open(path, encoding='utf-8') as fh:
        stock = load_inventory(yaml.safe_load(fh))
    result = stock.take('drug-amox')
    assert result.events == ('REFILL_REQUESTED',)      # 봉투를 내는 그 순간이다
    assert not stock.is_paused('drug-amox')            # 조제는 멈추지 않는다
    assert stock.take('drug-amox').ok                  # 다음 조제도 받는다(거부 0)
