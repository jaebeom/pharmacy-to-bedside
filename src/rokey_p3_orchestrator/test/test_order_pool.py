import pytest

from rokey_p3_orchestrator import order_pool


def pool_document(**overrides):
    row = {'order_id': 'ord-0001', 'patient_id': '1001', 'item_id': 'drug-amox', 'bed': 'bed_a1'}
    row.update(overrides)
    return {'version': 1, 'orders': [row]}


def test_request_id_is_contract_format():
    assert order_pool.request_id(1, 7) == 'r001-0007'
    assert order_pool.request_id(12, 1234) == 'r012-1234'


def test_order_id_needs_the_ord_prefix():
    assert order_pool.is_order_id('ord-0001')
    assert not order_pool.is_order_id('0001')
    assert not order_pool.is_order_id('pt-1001')
    assert not order_pool.is_order_id('')


def test_tag_ids_get_the_contract_prefix():
    assert order_pool.patient_tag_id('1001') == 'pt-1001'
    assert order_pool.station_tag_id('station_a') == 'st-station_a'


def test_load_pool_reads_the_four_fields():
    orders = order_pool.load_pool(pool_document())
    assert len(orders) == 1
    assert orders[0].order_id == 'ord-0001'
    assert orders[0].patient_id == '1001'
    assert orders[0].item_id == 'drug-amox'
    assert orders[0].bed == 'bed_a1'
    assert orders[0].mode == 'single'


@pytest.mark.parametrize('overrides', [
    {'order_id': '0001'},
    {'patient_id': 'pt-1001'},
    {'bed': 'ward_a'},
    {'bed': 'station_b1'},
    {'bed': 'room_a1'},
    {'mode': 'batch_room'},
    {'patient_id': 1001},
])
def test_load_pool_rejects_contract_violations(overrides):
    with pytest.raises(order_pool.PoolError):
        order_pool.load_pool(pool_document(**overrides))


def test_a_nursing_station_is_a_destination_like_a_bed():
    """9/24 재범: 목적지는 간호스테이션 B 테이블이다. `bed` 칸에 station_b 를 받는다."""
    orders = order_pool.load_pool(pool_document(bed='station_b'))
    assert orders[0].bed == 'station_b'
    request = order_pool.build_requests(orders)[0]
    assert request.destination_id == 'station_b'


def test_a_room_table_is_a_destination_like_a_bed():
    """재범 9/25: 병실 주문 → 그 방 테이블(station_c·station_d). 병상 ID 모양이 아닌 room_a1 은 여전히 거부한다."""
    for zone in ('station_c', 'station_d'):
        assert order_pool.load_pool(pool_document(bed=zone))[0].bed == zone


def test_the_hospital_pool_has_ten_beds_and_three_tables():
    import pathlib

    import yaml

    path = pathlib.Path(__file__).resolve().parents[1] / 'config' / 'order_pool.hospital.yaml'
    beds = [order.bed for order in order_pool.load_pool(yaml.safe_load(path.read_text()))]
    assert len(beds) == 13
    assert beds[-3:] == ['station_b', 'station_c', 'station_d']
    assert all(bed.startswith('bed_') for bed in beds[:10])


def test_load_pool_rejects_duplicate_order_id():
    document = pool_document()
    document['orders'] = document['orders'] * 2
    with pytest.raises(order_pool.PoolError):
        order_pool.load_pool(document)


def test_load_pool_rejects_empty_orders():
    with pytest.raises(order_pool.PoolError):
        order_pool.load_pool({'version': 1, 'orders': []})


def test_build_requests_makes_one_request_per_order():
    orders = order_pool.load_pool({'version': 1, 'orders': [
        {'order_id': 'ord-0001', 'patient_id': '1001', 'item_id': 'a', 'bed': 'bed_a1'},
        {'order_id': 'ord-0002', 'patient_id': '1002', 'item_id': 'b', 'bed': 'bed_a2', 'mode': 'urgent'},
    ]})
    requests = order_pool.build_requests(orders)
    assert [r.destination_id for r in requests] == ['bed_a1', 'bed_a2']
    assert [r.order_ids for r in requests] == [('ord-0001',), ('ord-0002',)]
    assert [r.mode_value for r in requests] == [order_pool.MODE_SINGLE, order_pool.MODE_URGENT]


def _request(name, mode='single'):
    return order_pool.PendingRequest(mode=mode, destination_id='bed_a1', order_ids=(name,))


def test_queue_puts_urgent_in_front_of_normal():
    queue = order_pool.RequestQueue([_request('a'), _request('b')])
    queue.push(_request('u', mode='urgent'))
    assert [r.order_ids[0] for r in queue.pending()] == ['u', 'a', 'b']


def test_queue_keeps_urgent_order_among_themselves():
    queue = order_pool.RequestQueue([_request('a')])
    queue.push(_request('u1', mode='urgent'))
    queue.push(_request('u2', mode='urgent'))
    assert [r.order_ids[0] for r in queue.pending()] == ['u1', 'u2', 'a']
    assert queue.pop().order_ids[0] == 'u1'
    assert len(queue) == 2


def test_empty_queue_pops_none():
    assert order_pool.RequestQueue().pop() is None
