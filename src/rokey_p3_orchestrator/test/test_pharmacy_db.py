from pathlib import Path

import pytest
import yaml

from rokey_p3_orchestrator import pharmacy_db
from rokey_p3_orchestrator.pharmacy_db import CatalogError, PharmacyDb, build_seed

CONFIG = Path(__file__).resolve().parents[1] / 'config'


def read(name):
    return yaml.safe_load((CONFIG / name).read_text(encoding='utf-8'))


def shipped(**overrides):
    docs = {'catalog': read('pharmacy_catalog.yaml'), 'dispenser': read('dispenser.yaml'),
            'pool': read('order_pool.yaml')}
    docs.update(overrides)
    return docs


@pytest.fixture
def db():
    docs = shipped()
    database = PharmacyDb(':memory:', build_seed(docs['catalog'], docs['dispenser'], docs['pool']))
    yield database
    database.close()


def test_shipped_seeds_load_and_join_dispenser_lots(db):
    row = db.container('cn-0001')
    assert (row['item_id'], row['lot_id'], row['location'], row['status']) == (
        'drug-amox', 'lot-amox-01', 'slot_a', 'in_use')
    assert db.container('cn-0005')['location'] == 'shelf'
    assert db.container('cn-0005')['status'] == 'standby'
    assert db.drug('drug-ibu')['high_risk'] == 0
    assert db.pouch('ord-0002')['urgent'] == 1


def test_classify_uses_contract_prefixes():
    assert pharmacy_db.classify('cn-0001') == ('container', 'cn-0001')
    assert pharmacy_db.classify('md-0002') == ('module', 'md-0002')
    assert pharmacy_db.classify('ord-0001') == ('pouch', 'ord-0001')
    assert pharmacy_db.classify('pt-1001') == ('patient', '1001')
    assert pharmacy_db.classify('st-station_a') == ('station', 'station_a')
    assert pharmacy_db.classify('cn-1') == (None, None)
    assert pharmacy_db.classify('drug-amox') == (None, None)
    assert pharmacy_db.classify('') == (None, None)


def test_expired_and_recalled_containers_are_refused(db):
    assert db.can_mount('cn-0005') == (True, 'ok')
    assert db.can_mount('cn-0009') == (False, 'expired')
    assert db.container('cn-0009')['status'] == 'expired'
    assert db.can_mount('cn-9999') == (False, 'unknown_id')


def test_recalled_container_is_refused_even_before_expiry():
    docs = shipped()
    docs['catalog']['containers'].append(
        {'container_id': 'cn-0010', 'lot_id': 'lot-ibu-99', 'item_id': 'drug-ibu', 'expiry': '2030-01-01',
         'count': 5, 'location': 'quarantine', 'status': 'recalled'})
    database = PharmacyDb(':memory:', build_seed(docs['catalog'], docs['dispenser'], docs['pool']))
    assert database.can_mount('cn-0010') == (False, 'recalled')


def test_today_decides_expiry_not_the_wall_clock():
    docs = shipped()
    early = PharmacyDb(':memory:', build_seed(docs['catalog'], docs['dispenser'], docs['pool'],
                                              today='2026-06-01'))
    late = PharmacyDb(':memory:', build_seed(docs['catalog'], docs['dispenser'], docs['pool'],
                                             today='2027-04-01'))
    assert early.can_mount('cn-0009') == (True, 'ok')
    assert late.can_mount('cn-0001') == (False, 'expired')


def test_scan_results_are_recorded_in_order(db):
    assert db.record_scan('ord-0001', robot='amr_1', epoch=1, zone_id='pharmacy', stamp=12.5) == 'ok'
    assert db.record_scan('ord-0999', robot='amr_1', epoch=1) == 'unknown_id'
    assert db.record_scan('hello', robot='amr_1', epoch=1) == 'bad_format'
    assert db.record_scan('cn-0009', robot='m0609', epoch=1) == 'expired'
    assert db.record_scan('ord-0002', robot='amr_1', epoch=1, expected='ord-0001') == 'mismatch'
    assert db.record_scan('pt-1001', robot='amr_1', epoch=1) == 'ok'
    assert db.record_scan('pt-9999', robot='amr_1', epoch=1) == 'unknown_id'
    rows = db.scans()
    assert [row['result'] for row in rows] == [
        'ok', 'unknown_id', 'bad_format', 'expired', 'mismatch', 'ok', 'unknown_id']
    assert (rows[0]['robot'], rows[0]['zone_id'], rows[0]['stamp'], rows[0]['kind']) == (
        'amr_1', 'pharmacy', 12.5, 'pouch')


def test_reseed_restores_tables_but_keeps_scans(db):
    db.record_scan('ord-0001', robot='amr_1', epoch=1)
    db.add_pouch_status('ord-0001', 'DISPENSED', epoch=1, stamp=3.0)
    db.reseed()
    db.record_scan('ord-0001', robot='amr_1', epoch=2)
    assert db.pouch_history('ord-0001') == []
    assert [row['epoch'] for row in db.scans()] == [1, 2]
    assert len(db.scans(epoch=2)) == 1


def test_reopen_starts_a_fresh_run(tmp_path):
    docs = shipped()
    seed = build_seed(docs['catalog'], docs['dispenser'], docs['pool'])
    path = str(tmp_path / 'pharmacy.sqlite')
    first = PharmacyDb(path, seed)
    first.record_scan('ord-0001', robot='amr_1', epoch=1)
    first.close()
    second = PharmacyDb(path, seed)
    assert second.scans() == []


def test_unknown_pouch_status_is_refused(db):
    with pytest.raises(CatalogError):
        db.add_pouch_status('ord-0999', 'DISPENSED', epoch=1)


def test_every_dispenser_lot_needs_a_container_id():
    docs = shipped()
    docs['catalog']['containers'] = [row for row in docs['catalog']['containers'] if row['container_id'] != 'cn-0002']
    with pytest.raises(CatalogError, match='lot-amox-02'):
        build_seed(docs['catalog'], docs['dispenser'], docs['pool'])


def test_dispenser_values_are_not_written_twice():
    docs = shipped()
    docs['catalog']['containers'][0]['expiry'] = '2027-03-31'
    with pytest.raises(CatalogError, match='dispenser.yaml 이 정한다'):
        build_seed(docs['catalog'], docs['dispenser'], docs['pool'])


@pytest.mark.parametrize('bad', [
    {'container_id': 'cn-01', 'lot_id': 'x', 'received': '2026-01-01'},
    {'container_id': 'cn-0001', 'lot_id': 'lot-dup', 'received': '2026-01-01'},
    {'container_id': 'cn-0011', 'lot_id': 'lot-new', 'received': '2026-01-01'},
])
def test_bad_container_rows_are_refused(bad):
    docs = shipped()
    docs['catalog']['containers'].append(bad)
    with pytest.raises(CatalogError):
        build_seed(docs['catalog'], docs['dispenser'], docs['pool'])


def test_bad_today_and_unknown_module_item_are_refused():
    docs = shipped()
    with pytest.raises(CatalogError, match='today'):
        build_seed(docs['catalog'], docs['dispenser'], docs['pool'], today='23/09/2026')
    docs['catalog']['modules'].append({'module_id': 'md-0003', 'item_id': 'drug-none'})
    with pytest.raises(CatalogError, match='md-0003'):
        build_seed(docs['catalog'], docs['dispenser'], docs['pool'])


def test_broken_dispenser_seed_is_a_catalog_error():
    docs = shipped()
    docs['dispenser']['items']['drug-amox'] = docs['dispenser']['items']['drug-amox'][:1]
    with pytest.raises(CatalogError, match='dispenser.yaml'):
        build_seed(docs['catalog'], docs['dispenser'], docs['pool'])


def test_recalled_scan_is_recorded_as_recalled_not_expired():
    docs = shipped()
    docs['catalog']['containers'][4]['status'] = 'recalled'          # cn-0005 는 dispenser 선반 로트다
    database = PharmacyDb(':memory:', build_seed(docs['catalog'], docs['dispenser'], docs['pool']))
    assert database.container('cn-0005')['status'] == 'recalled'
    assert database.can_mount('cn-0005') == (False, 'recalled')
    assert database.record_scan('cn-0005', robot='m0609', epoch=1) == 'recalled'


def test_dispenser_lot_status_other_than_recalled_is_refused():
    docs = shipped()
    docs['catalog']['containers'][4]['status'] = 'standby'
    with pytest.raises(CatalogError, match='recalled 만'):
        build_seed(docs['catalog'], docs['dispenser'], docs['pool'])


@pytest.mark.parametrize('mutate', [
    lambda c: c['modules'].append(dict(c['modules'][0])),                                  # 모듈 ID 중복
    lambda c: c['modules'][0].update(source_container='cn-0003'),                          # 약품이 다른 출처 약통
    lambda c: c['modules'].append('md-0009'),                                               # mapping 아님
    lambda c: c['containers'].append(7),                                                    # mapping 아님
    lambda c: c['containers'][8].update(count='many'),                                      # 정수 아님
    lambda c: c['containers'].append({'container_id': 'cn-0012', 'lot_id': '', 'received': '2026-01-01'}),
])
def test_bad_seed_shapes_are_catalog_errors(mutate):
    docs = shipped()
    mutate(docs['catalog'])
    with pytest.raises(CatalogError):
        build_seed(docs['catalog'], docs['dispenser'], docs['pool'])


def test_shelf_canisters_carry_their_stage_cell_and_one_is_expired(db):
    # Q1(9/23): 선반 16칸 = cn-0101..0116. M0609 가 읽은 QR 로 장착 여부를 묻는다.
    assert db.container('cn-0101')['location'] == 'shelf:floor_left/r0c0'
    assert db.can_mount('cn-0105') == (True, 'ok')
    assert db.can_mount('cn-0106') == (False, 'expired')          # floor_right/r0c1
    assert db.container('cn-0116')['item_id'] == 'drug-ibu'


def test_check_container_answers_and_records_one_scan(db):
    assert db.check_container('cn-0105', robot='m0609', epoch=1, current_epoch=1, cell_id='floor_right/r0c0') == (
        True, 'ok')
    assert db.check_container('cn-0106', robot='m0609', epoch=1, current_epoch=1) == (False, 'expired')
    assert db.check_container('cn-9999', robot='m0609', epoch=1, current_epoch=1) == (False, 'unknown_id')
    assert db.check_container('ord-0001', robot='m0609', epoch=1, current_epoch=1) == (False, 'bad_format')
    assert db.check_container('cn-0105', robot='m0609', epoch=1, current_epoch=2) == (False, 'stale_epoch')
    rows = db.scans()
    assert [row['result'] for row in rows] == ['ok', 'expired', 'unknown_id', 'bad_format', 'stale_epoch']
    assert rows[0]['zone_id'] == 'floor_right/r0c0'


def test_epoch_zero_means_not_seen_yet_and_is_taken_as_current(db):
    """회차33(5a51804): 팔은 epoch 0 으로 시작해 /events 를 받아야 올린다. 기동 직후 첫 확인이 0 이면 받는다.

    다른 epoch(리셋 전 요청)는 여전히 stale_epoch 다 — /sim/reset 요청과 같은 규칙(0 또는 현재).
    """
    assert db.check_container('cn-0105', robot='m0609', epoch=0, current_epoch=1) == (True, 'ok')
    assert db.check_container('cn-0106', robot='m0609', epoch=0, current_epoch=1) == (False, 'expired')
    assert db.check_container('cn-0105', robot='m0609', epoch=1, current_epoch=2) == (False, 'stale_epoch')
    assert db.check_container('cn-0105', robot='m0609', epoch=3, current_epoch=2) == (False, 'stale_epoch')


def test_db_can_be_used_from_another_thread(db):
    """노드는 MultiThreadedExecutor 라 서비스가 DB 를 만든 스레드가 아닌 곳에서 온다."""
    import threading

    answers = []
    worker = threading.Thread(target=lambda: answers.append(
        db.check_container('cn-0105', robot='m0609', epoch=1, current_epoch=1)))
    worker.start()
    worker.join(5.0)
    assert answers == [(True, 'ok')]


def test_site_dispenser_lots_without_ids_can_be_allowed():
    docs = shipped()
    docs['dispenser']['shelf']['drug-amox'].append({'lot_id': 'lot-site-99', 'expiry': '2029-01-31', 'count': 5})
    with pytest.raises(CatalogError):
        build_seed(docs['catalog'], docs['dispenser'], docs['pool'])
    seed = build_seed(docs['catalog'], docs['dispenser'], docs['pool'], require_dispenser_lots=False)
    assert seed['missing_lots'] == ['lot-site-99']



def test_site_dispenser_file_with_other_lots_still_opens_the_shelf_canisters():
    """#546 L2 에서 드러났다: 현장 재고 파일은 카탈로그의 cn-0001..0008 로트를 안 쓴다. 기동은 되고 선반 약통은 있다."""
    docs = shipped()
    site = {'version': 1, 'refill_threshold': 1, 'items': {
        'drug-amox': [{'slot': 'a', 'lot_id': 'lot-l2-a', 'expiry': '2027-03-31', 'count': 0},
                      {'slot': 'b', 'lot_id': 'lot-l2-b', 'expiry': '2027-09-30', 'count': 0}],
        'drug-ibu': [{'slot': 'a', 'lot_id': 'lot-ibu-01', 'expiry': '2027-05-31', 'count': 5},
                     {'slot': 'b', 'lot_id': 'lot-ibu-02', 'expiry': '2027-11-30', 'count': 5}]},
        'shelf': {'drug-amox': [{'lot_id': 'lot-l2-s', 'expiry': '2028-03-31', 'count': 5}]}}
    with pytest.raises(CatalogError):
        build_seed(docs['catalog'], site, docs['pool'])
    seed = build_seed(docs['catalog'], site, docs['pool'], require_dispenser_lots=False)
    assert seed['missing_lots'] == ['lot-l2-a', 'lot-l2-b', 'lot-l2-s']
    assert 'cn-0001' in seed['unmatched_catalog'] and 'cn-0003' not in seed['unmatched_catalog']
    database = PharmacyDb(':memory:', seed)
    assert database.check_container('cn-0106', robot='m0609', epoch=1, current_epoch=1) == (False, 'expired')
    assert database.container('cn-0003')['lot_id'] == 'lot-ibu-01'


def test_hospital_workcell_canisters_are_in_the_db(db):
    # 재범 9/23: 병원 워크셀 18칸(cn-0201..0218)에도 약통 QR. shelf_72/r0c0 은 만료.
    assert db.container('cn-0211')['location'] == 'shelf:shelf_72/r0c0'
    assert db.can_mount('cn-0211') == (False, 'expired')
    assert db.can_mount('cn-0201') == (True, 'ok')
