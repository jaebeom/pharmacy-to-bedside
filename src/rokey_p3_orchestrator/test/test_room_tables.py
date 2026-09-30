"""병실 주문 → 그 방 테이블(C), 스테이션 자리 → st- 인식표 (재범 9/25 03:3x). L1."""

from rokey_p3_orchestrator import trip_fsm as fsm

ZONES = {'zones': {
    'bed_a1': {'kind': 'bed', 'room': 'C1'},
    'bed_b1': {'kind': 'bed', 'room': 'C2'},
    'bed_b2': {'kind': 'bed', 'room': 'C2'},
    'bed_b3': {'kind': 'bed', 'room': 'C2'},
    'station_a': {'kind': 'station'},
    'station_b': {'kind': 'station'},
    'station_c': {'kind': 'station', 'room': 'C1'},
    'station_d': {'kind': 'station', 'room': 'C2'},
    'load': {'kind': 'load'},
}}
BEDS = {'2001': 'bed_a1', '2005': 'bed_b1', '2006': 'bed_b2', '2007': 'bed_b3',
        '2011': 'station_b', '2012': 'station_c', '2013': 'station_d'}
C2_BATCH = [{'order_id': f'ord-000{n}', 'patient_id': f'200{n}', 'item_id': 'drug-amox'} for n in (5, 6, 7)]


def make(zones=ZONES):
    machine = fsm.TripFsm(patient_beds=BEDS, **fsm.zone_maps(zones))
    machine.tick(0.0)
    machine.state_update(fsm.AT_HOME, True, True)
    machine.state_update(fsm.BASE_STOPPED, True, True)
    machine.state_update(fsm.BELT, {'occupied': False, 'at_end': False, 'order_id': ''}, True)
    return machine


def request(mode, orders, destination=''):
    return {'request_id': 'r001-0001', 'mode': mode, 'destination_id': destination, 'orders': orders}


def single(order_id, patient):
    return request(fsm.MODE_SINGLE, [{'order_id': order_id, 'patient_id': patient, 'item_id': 'drug-amox'}])


def events(commands):
    return [c.event for c in commands if isinstance(c, fsm.Emit)]


def goals(commands, action):
    return [c.goal for c in commands if isinstance(c, fsm.SendGoal) and c.action == action]


def load(machine, body):
    out = machine.request(body)
    out += machine.result(fsm.GO_TO_ZONE, fsm.ACCEPTED)
    out += machine.result(fsm.GO_TO_ZONE, fsm.ARRIVED)
    for row in body['orders']:
        out += machine.result(fsm.DISPENSE, fsm.ACCEPTED)
        out += machine.state_update(fsm.BELT, {'occupied': True, 'at_end': True, 'order_id': row['order_id']}, True)
        out += machine.result(fsm.PICK_POUCH, fsm.ACCEPTED)
        out += machine.state_update(fsm.BELT, {'occupied': False, 'at_end': False, 'order_id': ''}, True)
        out += machine.result(fsm.PICK_POUCH, fsm.OK)
    return out


def deliver_at_one_stop(machine, tag_id, count):
    out = machine.result(fsm.GO_TO_ZONE, fsm.ACCEPTED)
    out += machine.result(fsm.GO_TO_ZONE, fsm.ARRIVED)
    out += machine.result(fsm.SCAN_TAG, fsm.ACCEPTED)
    out += machine.result(fsm.SCAN_TAG, fsm.OK, {'tag_id': tag_id})
    for _ in range(count):
        out += machine.result(fsm.PICK_POUCH, fsm.ACCEPTED)
        out += machine.result(fsm.PICK_POUCH, fsm.OK)
    out += machine.result(fsm.GO_TO_ZONE, fsm.ACCEPTED)
    out += machine.result(fsm.GO_TO_ZONE, fsm.ARRIVED)
    return out


def test_zone_maps_reads_rooms_tables_and_station_zones():
    maps = fsm.zone_maps(ZONES)
    assert maps['room_tables'] == {'C1': 'station_c', 'C2': 'station_d'}
    assert maps['zone_rooms']['bed_b2'] == 'C2'
    assert maps['station_zones'] == {'station_a', 'station_b', 'station_c', 'station_d'}
    assert fsm.zone_maps(None) == {'zone_rooms': {}, 'room_tables': {}, 'station_zones': frozenset()}


def test_room_batch_goes_to_the_room_table_once_with_all_three_pouches():
    machine = make()
    run = load(machine, request(fsm.MODE_BATCH_ROOM, C2_BATCH, 'bed_b1'))
    assert machine.stops() == (fsm.Stop('station_d', 'station', 'st-station_d', ('ord-0005', 'ord-0006', 'ord-0007')),)
    run += deliver_at_one_stop(machine, 'st-station_d', 3)
    assert events(run).count('ARRIVED') == 1
    assert events(run).count('AUTH_OK') == 1
    assert events(run).count('CABINET_LOCKED') == 3
    assert goals(run, fsm.GO_TO_ZONE) == [{'zone_id': z} for z in ('load', 'station_d', 'dock_1')]
    assert goals(run, fsm.SCAN_TAG) == [{'kind': 'station', 'zone_id': 'station_d'}]
    assert [g['zone_id'] for g in goals(run, fsm.PICK_POUCH) if g['source'] == 'DECK'] == ['station_d'] * 3
    assert set(machine.order_states().values()) == {'DELIVERED'}
    assert fsm.Finish(True) in run


def test_room_batch_without_a_table_still_stops_at_every_bed():
    no_tables = {'zones': {k: v for k, v in ZONES['zones'].items() if k not in ('station_c', 'station_d')}}
    machine = make(no_tables)
    machine.request(request(fsm.MODE_BATCH_ROOM, C2_BATCH, 'bed_b1'))
    assert [s.zone_id for s in machine.stops()] == ['bed_b1', 'bed_b2', 'bed_b3']
    assert [s.tag_id for s in machine.stops()] == ['pt-2005', 'pt-2006', 'pt-2007']
    plain = fsm.TripFsm(patient_beds=BEDS)
    plain.tick(0.0)
    plain.state_update(fsm.AT_HOME, True, True)
    plain.state_update(fsm.BASE_STOPPED, True, True)
    plain.state_update(fsm.BELT, {'occupied': False, 'at_end': False, 'order_id': ''}, True)
    plain.request(request(fsm.MODE_BATCH_ROOM, C2_BATCH, 'bed_b1'))
    assert [s.kind for s in plain.stops()] == ['patient'] * 3


def test_room_batch_across_two_rooms_is_refused_when_tables_exist():
    machine = make()
    mixed = [{'order_id': 'ord-0001', 'patient_id': '2001', 'item_id': 'drug-amox'}, C2_BATCH[0]]
    reason = machine.refusal(request(fsm.MODE_BATCH_ROOM, mixed, 'bed_a1'))
    assert reason is not None and '병실이 하나가 아니다' in reason and "['C1', 'C2']" in reason


def test_single_orders_to_station_zones_authenticate_with_the_station_tag():
    """station_b 1인 주문(ord-0011)은 pt-2011 이 아니라 st-station_b 로 인증한다. 침상은 그대로 pt-."""
    for patient, zone in (('2011', 'station_b'), ('2012', 'station_c'), ('2013', 'station_d')):
        machine = make()
        run = load(machine, single('ord-0099', patient))
        assert machine.stops() == (fsm.Stop(zone, 'station', f'st-{zone}', ('ord-0099',)),)
        run += deliver_at_one_stop(machine, f'st-{zone}', 1)
        assert goals(run, fsm.SCAN_TAG) == [{'kind': 'station', 'zone_id': zone}]
        assert events(run)[-3:] == ['ORDER_DONE', 'RETURNED', 'DOCKED']
    machine = make()
    machine.request(single('ord-0001', '2001'))
    assert machine.stops() == (fsm.Stop('bed_a1', 'patient', 'pt-2001', ('ord-0001',)),)


def test_patient_tag_at_a_station_zone_fails_authentication():
    machine = make()
    run = load(machine, single('ord-0011', '2011'))
    run += machine.result(fsm.GO_TO_ZONE, fsm.ACCEPTED)
    run += machine.result(fsm.GO_TO_ZONE, fsm.ARRIVED)
    run += machine.result(fsm.SCAN_TAG, fsm.ACCEPTED)
    run += machine.result(fsm.SCAN_TAG, fsm.OK, {'tag_id': 'pt-2011'})
    assert 'AUTH_OK' not in events(run)
