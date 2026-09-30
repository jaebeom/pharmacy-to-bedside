from rokey_p3_perception.qr_payload import (
    KIND_CONTAINER,
    KIND_MODULE,
    KIND_PATIENT,
    KIND_POUCH,
    KIND_STATION,
    is_order_id,
    parse_tag,
    parse_tag_id,
    tag_kind,
)


def test_plain_ids_pass():
    assert parse_tag_id('order-0001') == 'order-0001'
    assert parse_tag_id('  bed_a1 ') == 'bed_a1'


def test_bad_payloads_are_none():
    assert parse_tag_id('') is None
    assert parse_tag_id(None) is None
    assert parse_tag_id('ORDER 1') is None


def test_prefix_decides_the_kind():
    # 계약 2.4절: TagRead.kind 는 QR 내용 접두로 정한다.
    assert tag_kind('ord-0001') == KIND_POUCH
    assert tag_kind('pt-p001') == KIND_PATIENT
    assert tag_kind('st-station_a') == KIND_STATION
    assert tag_kind('bed_a1') is None
    assert tag_kind('') is None


def test_pouch_id_keeps_the_prefix_and_the_others_drop_it():
    # 봉투는 QR 내용 전체가 주문 ID 다(Order.msg). 환자·스테이션은 접두 뒤가 ID 다(계약 7절).
    assert parse_tag('ord-0001') == (KIND_POUCH, 'ord-0001')
    assert parse_tag('pt-p001') == (KIND_PATIENT, 'p001')
    assert parse_tag('st-station_a') == (KIND_STATION, 'station_a')


def test_prefix_without_a_body_is_not_a_tag():
    assert parse_tag('ord-') == (None, None)
    assert parse_tag('pt-') == (None, None)


def test_order_id_format_is_the_contract_format():
    assert is_order_id('ord-0001')
    assert not is_order_id('ord-1')
    assert not is_order_id('order-0001')
    assert not is_order_id('')


def test_container_and_module_ids_keep_the_prefix():
    # QR·DB·카메라 계약 1절: 약통·모듈은 QR 내용 전체가 DB 키다.
    assert parse_tag('cn-0101') == (KIND_CONTAINER, 'cn-0101')
    assert parse_tag('md-0001') == (KIND_MODULE, 'md-0001')


def test_container_and_module_need_four_digits():
    for payload in ('cn-1', 'cn-01010', 'cn-abcd', 'md-', 'md-12'):
        assert parse_tag(payload) == (None, None), payload
