"""event_logger 의 run 경계. 토픽마다 도착 순서가 달라도 이전 요청의 기록이 이전 run 에 남는지. ROS 없이 돈다.

관측(정비, main fd13a46·#84, L2):
- 결함 1: 끊긴 주문의 ABORT(reset_interrupted)가 RESET_BEGIN 보다 늦게 오면 이전 run orders.jsonl 은
  IN_PROGRESS/run_ended_before_terminal 로 닫히고, 새 run order_status.jsonl 첫 줄에 이전 request_id 가 들어갔다.
  주행 중 리셋 5회 중 4회, 벨트 픽 중 2회 중 2회.
- 결함 2: 느린 리셋(stub_sim reset_delay_s 3.0)에서 RESET_DONE 전 /evaluator/cabinet 관측 3건이 새 run 에 들어가
  같은 order_id 의 새 트립이 SUCCESS 가 됐다. 리셋 실패 때는 트립 없는 run 에 claim "" SUCCESS 가 생겼다.

orchestrator 는 OrderState(ABORT) → ORDER_DONE(이전 epoch) → RESET_BEGIN(새 epoch) 순으로 낸다. /events 안의 순서는
지켜지지만 /orders/status 와의 순서는 정해지지 않는다.
"""

import datetime
import itertools
import json
import os
import pathlib

import pytest

from rokey_p3_orchestrator import run_log

RID = 'r001-0001'
NEW_RID = 'r002-0001'
ORDER = 'ord-0002'
CABINET = 'bed_a2/cabinet'


def book(tmp_path, drain_s=2.0):
    nonces = (f'{n:08x}' for n in itertools.count(1))
    return run_log.RunBook(str(tmp_path), 'master02', drain_s,
                           now_utc=lambda: datetime.datetime(2026, 9, 17, 1, 2, 3, tzinfo=datetime.timezone.utc),
                           nonce=lambda: next(nonces))


def event(name, epoch, request_id='', order_id=''):
    return {'stamp': 0.0, 'epoch': epoch, 'name': name, 'request_id': request_id, 'order_id': order_id,
            'robot_id': 'amr_1', 'detail': ''}


def status(state, request_id=RID, reason='', order_id=ORDER):
    return {'stamp': 0.0, 'request_id': request_id, 'order_id': order_id, 'state': state, 'reason': reason}


def cabinet(present=True, order_id=ORDER):
    return {'stamp': 0.0, 'cabinet_id': CABINET, 'order_id': order_id, 'present': present}


def rows(run, name):
    path = os.path.join(run.dir, f'{name}.jsonl')
    with open(path, encoding='utf-8') as handle:
        return [json.loads(line) for line in handle if line.strip()]


def meta(run):
    with open(os.path.join(run.dir, 'meta.json'), encoding='utf-8') as handle:
        return json.loads(handle.read())


def trip_in_progress(runs):
    """epoch 1 에서 r001 이 ord-0002 를 싣고 가는 중."""
    runs.event(event('REQUEST_ACCEPTED', 1, RID), 0.0)
    runs.order_status(status('ACCEPTED'), 0.0)
    runs.event(event('LOAD_DONE', 1, RID), 0.0)
    runs.order_status(status('IN_PROGRESS'), 0.0)


# 결함 1 ------------------------------------------------------------------------

@pytest.mark.parametrize('arrival', ['status_first', 'reset_begin_first'])
def test_interrupted_order_is_closed_in_the_previous_run_for_both_arrival_orders(tmp_path, arrival):
    runs = book(tmp_path)
    trip_in_progress(runs)
    previous = runs.current
    abort = status('ABORT', reason='reset_interrupted')
    closing = [event('ORDER_DONE', 1, RID, ORDER), event('RESET_BEGIN', 2)]     # /events 안의 순서는 지켜진다
    if arrival == 'status_first':
        runs.order_status(abort, 10.0)
        for item in closing:
            runs.event(item, 10.0)
    else:
        for item in closing:
            runs.event(item, 10.0)
        runs.order_status(abort, 10.1)
    new = runs.current
    assert new is not previous and new.epoch == 2

    runs.expire(12.0)                                              # run_drain_s 뒤 이전 run 을 닫는다
    assert previous.closed and not new.closed
    [order] = rows(previous, 'orders')
    assert (order['request_id'], order['claim'], order['state'], order['reason']) == (
        RID, 'ABORT', 'ABORT', 'reset_interrupted')
    assert meta(previous)['closed_by_reset_epoch'] == 2
    assert [e['name'] for e in rows(previous, 'events')][-1] == 'ORDER_DONE'

    runs.close_all()
    assert all(row['request_id'] != RID for row in rows(new, 'order_status'))
    assert all(row['request_id'] != RID for row in rows(new, 'events'))
    assert rows(new, 'orders') == []
    assert [e['name'] for e in rows(new, 'events')] == ['RESET_BEGIN']
    assert meta(new)['closed_by_reset_epoch'] is None


# 결함 2 ------------------------------------------------------------------------

def test_cabinet_before_reset_done_never_makes_the_new_run_success(tmp_path):
    runs = book(tmp_path)
    trip_in_progress(runs)
    runs.event(event('POUCH_PLACED', 1, '', ORDER), 5.0)              # 이전 트립이 봉투를 놓았다
    runs.order_status(status('ABORT', reason='reset_interrupted'), 10.0)
    runs.event(event('ORDER_DONE', 1, RID, ORDER), 10.0)
    runs.event(event('RESET_BEGIN', 2), 10.0)
    previous, new = runs.draining[0], runs.current

    runs.cabinet(cabinet(), 11.0)                                     # drain 중: 이전 run 의 관측
    runs.cabinet(cabinet(), 12.5)                                     # drain 뒤, RESET_DONE 전(느린 리셋)
    runs.cabinet(cabinet(), 13.0)
    runs.event(event('RESET_DONE', 2), 13.2)
    runs.cabinet(cabinet(), 13.4)                                     # RESET_DONE 뒤라도 새 run 에 주장이 없다

    # 새 트립이 같은 order_id 로 오지만 배달하지 못하고 끝난다.
    runs.event(event('REQUEST_ACCEPTED', 2, NEW_RID), 17.0)
    runs.order_status(status('ACCEPTED', request_id=NEW_RID), 17.0)
    runs.order_status(status('ABORT', request_id=NEW_RID, reason='belt_blocked'), 40.0)
    runs.close_all()

    [old] = rows(previous, 'orders')
    assert old['request_id'] == RID and old['observed'] is True       # 리셋 전 관측은 이전 트립의 것이다
    [order] = rows(new, 'orders')
    assert (order['request_id'], order['observed'], order['state'], order['reason']) == (
        NEW_RID, False, 'ABORT', 'belt_blocked')
    marks = [(row['pre_reset'], row['used']) for row in rows(new, 'cabinet')]
    assert marks == [(True, False), (True, False), (False, False)]
    assert meta(new)['counts']['pre_reset'] == 2


def test_failed_reset_run_without_a_trip_has_no_success(tmp_path):
    runs = book(tmp_path)
    trip_in_progress(runs)
    runs.order_status(status('DELIVERED'), 5.0)
    runs.event(event('RESET_BEGIN', 2), 10.0)                        # /sim/reset 실패: RESET_DONE 이 안 온다
    for now in (12.0, 13.0, 14.0):
        runs.cabinet(cabinet(), now)
    new = runs.current
    runs.close_all()
    assert rows(new, 'orders') == []
    assert all(row['pre_reset'] and not row['used'] for row in rows(new, 'cabinet'))


def test_observation_of_an_order_this_run_never_claimed_is_not_judged(tmp_path):
    runs = book(tmp_path)
    runs.cabinet(cabinet(), 0.0)                                      # 시작 run: 관측은 열려 있지만 주장이 없다
    runs.order_status(status('DELIVERED'), 1.0)
    runs.cabinet(cabinet(), 2.0)
    run = runs.current
    runs.close_all()
    [order] = rows(run, 'orders')
    assert order['state'] == 'SUCCESS' and order['claim'] == 'DELIVERED'
    assert [row['used'] for row in rows(run, 'cabinet')] == [False, True]


# drain 뒤·종료 --------------------------------------------------------------------

def test_late_messages_after_the_drain_do_not_change_the_closed_run(tmp_path):
    runs = book(tmp_path)
    trip_in_progress(runs)
    runs.event(event('RESET_BEGIN', 2), 10.0)
    previous, new = runs.draining[0], runs.current
    runs.expire(12.0)
    before = {name: pathlib.Path(previous.dir, name).read_bytes()
              for name in ('orders.jsonl', 'meta.json', 'order_status.jsonl', 'events.jsonl', 'cabinet.jsonl')}

    runs.order_status(status('ABORT', reason='reset_interrupted'), 12.5)
    runs.event(event('ORDER_DONE', 1, RID, ORDER), 12.5)
    after = {name: pathlib.Path(previous.dir, name).read_bytes() for name in before}
    assert after == before

    runs.close_all()
    [late] = rows(new, 'order_status')
    assert late['request_id'] == RID and late['late'] is True
    assert [(e['name'], e['stale']) for e in rows(new, 'events')] == [('RESET_BEGIN', False), ('ORDER_DONE', True)]
    assert rows(new, 'orders') == []                                  # 원장에는 안 들어간다
    assert meta(new)['counts']['late'] == 1 and meta(new)['counts']['stale'] == 1


def test_shutdown_closes_the_draining_and_the_current_run_once(tmp_path):
    runs = book(tmp_path)
    trip_in_progress(runs)
    runs.event(event('RESET_BEGIN', 2), 10.0)
    previous, new = runs.draining[0], runs.current
    runs.close_all()                                                  # drain 이 끝나기 전 SIGINT
    assert previous.closed and new.closed and runs.draining == []
    assert meta(previous)['closed_by_reset_epoch'] == 2 and meta(new)['closed_by_reset_epoch'] is None
    written = {run.dir: pathlib.Path(run.dir, 'meta.json').read_bytes() for run in (previous, new)}
    runs.close_all()
    runs.expire(100.0)
    # 종료 뒤에 온 메시지는 버린다. 닫힌 run 을 고치지도, 새 run 을 열지도 않는다.
    assert runs.event(event('RESET_BEGIN', 3), 101.0) is None and runs.current is new
    assert runs.order_status(status('ABORT', reason='reset_interrupted'), 101.0) is None
    assert runs.cabinet(cabinet(), 101.0) is None
    assert sorted(os.listdir(tmp_path)) == sorted(os.path.basename(run.dir) for run in (previous, new))
    assert {run.dir: pathlib.Path(run.dir, 'meta.json').read_bytes() for run in (previous, new)} == written


def test_two_resets_inside_the_drain_keep_each_request_in_its_own_run(tmp_path):
    """리셋 실패 뒤 곧바로 다시 리셋해도(epoch 2 → 3) 각 run 은 자기 epoch 이벤트만 받는다."""
    runs = book(tmp_path)
    trip_in_progress(runs)
    runs.event(event('RESET_BEGIN', 2), 10.0)
    runs.event(event('RESET_BEGIN', 3), 11.0)
    first, second, third = runs.runs()
    runs.order_status(status('ABORT', reason='reset_interrupted'), 11.5)
    runs.event(event('ORDER_DONE', 1, RID, ORDER), 11.5)
    runs.close_all()
    assert [r.epoch for r in (first, second, third)] == [1, 2, 3]
    assert rows(first, 'orders')[0]['state'] == 'ABORT'
    assert [e['name'] for e in rows(first, 'events')][-1] == 'ORDER_DONE'
    assert rows(second, 'order_status') == [] and rows(third, 'order_status') == []
    assert meta(first)['closed_by_reset_epoch'] == 2 and meta(second)['closed_by_reset_epoch'] == 3
