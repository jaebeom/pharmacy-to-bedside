"""order_generator 가 리셋 뒤 barrier 동안 요청을 보내지 않는지. 입력 순서 → 보낸 요청 표.

관측(정비 4호, docker 2회): /orchestrator/reset 뒤 발행기가 epoch 상승만 보고 곧바로 보내서
r002-0001(긴급 ord-0002)·0002·0003 이 "리셋 barrier 가 아직 안 끝났다" 로 거부되고 버려졌다.
"""

from rokey_p3_orchestrator.order_pool import build_requests, load_pool
from rokey_p3_orchestrator.request_pacer import RequestPacer

# config/order_pool.yaml 과 같은 꼴. ord-0002 가 긴급이라 큐 맨 앞이다.
POOL = {'orders': [
    {'order_id': 'ord-0001', 'patient_id': '1001', 'item_id': 'drug-amox', 'bed': 'bed_a1'},
    {'order_id': 'ord-0002', 'patient_id': '1002', 'item_id': 'drug-ibu', 'bed': 'bed_a2', 'mode': 'urgent'},
    {'order_id': 'ord-0003', 'patient_id': '1003', 'item_id': 'drug-amox', 'bed': 'bed_b1'},
    {'order_id': 'ord-0004', 'patient_id': '1004', 'item_id': 'drug-ibu', 'bed': 'bed_b2'},
]}


def pacer(settle_s=3.5):
    return RequestPacer(build_requests(load_pool(POOL)), settle_s=settle_s)


def sent(item):
    """take 결과를 (request_id, 주문) 으로."""
    if item is None:
        return None
    request_id, pending = item
    return request_id, pending.order_ids[0]


def test_start_epoch_is_open_without_a_reset():
    assert sent(pacer().take(0.0)) == ('r001-0001', 'ord-0002')


def test_nothing_right_after_reset_done_then_the_urgent_request_first():
    p = pacer()
    p.take(0.0)
    p.take(1.0)
    assert p.observe('RESET_DONE', 2, now=100.0) is True
    assert p.take(100.0) is None                        # 관측된 버그는 여기서 r002-0001 을 보냈다
    assert p.take(103.4) is None                        # orchestrator 의 3 s barrier + 여유
    assert sent(p.take(103.5)) == ('r002-0001', 'ord-0002')
    assert sent(p.take(103.6)) == ('r002-0002', 'ord-0001')


def test_epoch_raised_without_reset_done_sends_nothing():
    p = pacer()
    assert p.observe('DOCKED', 2, now=100.0) is True    # RESET_DONE 보다 다른 이벤트가 먼저 왔다
    assert p.take(1000.0) is None
    assert 'RESET_DONE' in p.holding(1000.0)
    assert p.observe('RESET_DONE', 2, now=1000.0) is False
    assert p.take(1003.4) is None
    assert sent(p.take(1003.5)) == ('r002-0001', 'ord-0002')


def test_repeated_or_old_reset_done_does_not_reopen_the_wait():
    p = pacer()
    p.observe('RESET_DONE', 2, now=100.0)
    assert p.take(104.0) is not None
    assert p.observe('RESET_DONE', 2, now=200.0) is False    # 래치로 다시 온 같은 RESET_DONE
    assert p.observe('RESET_DONE', 1, now=200.0) is False    # 이전 epoch
    assert p.holding(200.0) == ''


def test_new_epoch_refills_the_queue_and_restarts_seq():
    p = pacer(settle_s=0.0)
    for now in (0.0, 1.0, 2.0, 3.0):
        p.take(now)
    assert p.take(4.0) is None and len(p.queue) == 0
    p.observe('RESET_DONE', 3, now=10.0)
    assert len(p.queue) == 4
    assert sent(p.take(10.0)) == ('r003-0001', 'ord-0002')
