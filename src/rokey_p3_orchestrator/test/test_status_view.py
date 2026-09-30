"""status_monitor 화면(status_view). ROS 없이 돈다. 한글 폭은 맞추지 않는다(고정폭·한 글자 한 칸 가정)."""

from rokey_p3_orchestrator import status_view as view


def event(name, epoch=1, stamp=0.0, request_id='', order_id='', robot_id='amr_1', detail=''):
    return {'stamp': stamp, 'epoch': epoch, 'name': name, 'request_id': request_id, 'order_id': order_id,
            'robot_id': robot_id, 'detail': detail}


def order(state, request_id='r001-0001', order_id='ord-0001', reason=''):
    return {'request_id': request_id, 'order_id': order_id, 'state': state, 'reason': reason}


def section(lines, title):
    """제목 줄부터 빈 줄 전까지."""
    start = next(i for i, line in enumerate(lines) if line.startswith(title))
    end = next((i for i in range(start + 1, len(lines)) if lines[i] == ''), len(lines))
    return lines[start:end]


def test_empty_state_shows_every_section_with_placeholders():
    lines = view.render(view.StatusModel(), now=100.0)
    assert lines[0] == 'P3 status_monitor  epoch 0  sim -, /clock never'
    assert lines[1] == 'trip (estimated from events): -'
    assert section(lines, 'ORDERS')[1:] == ['  (none)']
    assert section(lines, 'DISPENSER')[1:] == ['  (no status yet)']
    assert section(lines, 'INTERLOCK')[1:] == [f'  {label:<16} unknown (never)' for _, label in view.SIGNALS]
    assert section(lines, 'EVENTS')[1:] == ['  (none)']
    assert not any('evaluator' in line for line in lines)


def test_signals_and_clock_go_unknown_after_their_wall_limits():
    model = view.StatusModel()
    model.note_clock(42.5, wall=10.0)
    model.note_signal('arm_at_home', True, wall=10.0)
    model.note_signal('belt', {'occupied': True, 'at_end': True, 'order_id': 'ord-0002'}, wall=10.0)

    fresh = view.render(model, now=11.0)
    assert 'sim 42.5 s, /clock ok (age 1.0 s)' in fresh[0]
    signals = section(fresh, 'INTERLOCK')
    assert signals[1] == '  arm/at_home      True  (1.0 s)'
    assert signals[4] == '  belt             occupied=True at_end=True order_id=ord-0002  (1.0 s)'
    assert signals[2] == '  base/stopped     unknown (never)'

    stale = view.render(model, now=12.1)
    assert 'sim 42.5 s, /clock STOPPED (age 2.1 s)' in stale[0]
    signals = section(stale, 'INTERLOCK')
    assert signals[1] == '  arm/at_home      unknown (age 2.1 s)'
    assert signals[4] == '  belt             unknown (age 2.1 s)'
    assert '/clock ok' in view.render(model, now=12.0)[0]                 # 2.0 s 까지는 멈춤이 아니다
    assert 'unknown' not in section(view.render(model, now=11.0), 'INTERLOCK')[1]


def test_reset_boundary_draws_separators_and_keeps_late_orders_in_their_epoch():
    model = view.StatusModel()
    model.note_event(event('REQUEST_ACCEPTED', 1, 3.0, 'r001-0001'))
    model.note_order(order('IN_PROGRESS'))
    model.note_event(event('ORDER_DONE', 1, 9.0, 'r001-0001', 'ord-0001'))
    model.note_event(event('RESET_BEGIN', 2, 9.0, robot_id='amr_1'))
    model.note_order(order('ABORT', reason='reset_interrupted'))           # 늦게 온 이전 요청의 상태
    model.note_event(event('RESET_DONE', 2, 0.5, detail='drain_timeout'))
    model.note_event(event('REQUEST_ACCEPTED', 2, 4.0, 'r002-0001'))
    model.note_order(order('ACCEPTED', 'r002-0001', 'ord-0002'))

    lines = view.render(model, now=0.0)
    assert lines[0].startswith('P3 status_monitor  epoch 2 ')
    assert lines[1] == 'trip (estimated from events): 적재 위치로 이동 <- REQUEST_ACCEPTED'
    events = section(lines, 'EVENTS')
    assert '  ---- RESET_BEGIN epoch 2 ----' in events
    assert '  ---- RESET_DONE epoch 2 drain_timeout ----' in events
    orders = section(lines, 'ORDERS')
    assert orders[2].startswith('      2  r002-0001    ord-0002   ACCEPTED')
    assert orders[3].startswith('  *   1  r001-0001    ord-0001   ABORT        reset_interrupted')
    assert orders[-1] == '  * = request from an earlier epoch'


def test_long_lists_and_details_are_cut():
    model = view.StatusModel()
    for index in range(20):
        model.note_event(event('PICK_ATTEMPT', 1, float(index), detail='x' * 100))
    for index in range(11):
        model.note_order(order('ACCEPTED', f'r001-{index + 1:04d}', f'ord-{index + 1:04d}'))
    lines = view.render(model, now=0.0)
    events = section(lines, 'EVENTS')
    assert len(events) == 1 + view.MAX_EVENTS
    assert events[1].startswith('       8.00')                              # 앞의 8건은 밀려났다
    assert events[-1].endswith('x' * (view.DETAIL_WIDTH - 2) + '..')
    orders = section(lines, 'ORDERS')
    assert len(orders) == 2 + view.MAX_ORDERS + 1
    assert 'r001-0011' in orders[2] and orders[-1] == '  .. 3 older rows hidden'


def test_trip_phase_ignores_dispenser_and_refill_events():
    model = view.StatusModel()
    model.note_event(event('LOAD_DONE', 1, 5.0, 'r001-0001'))
    model.note_event(event('REFILL_REQUESTED', 1, 6.0, robot_id='dispenser'))
    model.note_event(event('REFILL_DONE', 1, 7.0, robot_id='m0609'))
    assert view.render(model, now=0.0)[1] == 'trip (estimated from events): 적재 끝 <- LOAD_DONE'


def test_dispenser_shows_both_slots_active_lot_and_paused_items():
    model = view.StatusModel()
    model.note_dispenser({
        'slots': [
            {'item_id': 'drug-amox', 'slot': 0, 'lot_id': 'lot-amox-01', 'count': 4, 'active': True},
            {'item_id': 'drug-amox', 'slot': 1, 'lot_id': 'lot-amox-02', 'count': 5, 'active': False},
            {'item_id': 'drug-ibu', 'slot': 0, 'lot_id': '', 'count': 0, 'active': False},
        ],
        'paused_item_ids': ['drug-ibu'], 'queue_length': 1, 'belt_occupied': False,
    }, wall=3.0)
    dispenser = section(view.render(model, now=3.5), 'DISPENSER')
    assert dispenser[0] == 'DISPENSER (/pharmacy/dispenser/status)  age 0.5 s  queue 1  belt_occupied False'
    assert dispenser[1] == '  drug-amox    A* lot-amox-01    x4    B  lot-amox-02    x5  '
    assert dispenser[2] == '  drug-ibu     A                 x0    B: -  PAUSED'


def test_evaluator_column_only_with_the_option():
    model = view.StatusModel()
    model.note_order(order('DELIVERED'))
    model.note_cabinet('ord-0001', 'bed_a1/cabinet', True)
    model.note_cabinet('ord-0009', 'bed_a2/cabinet', False)
    assert '[' not in ''.join(section(view.render(model, now=0.0), 'ORDERS'))
    lines = view.render(model, 0.0, {'with_evaluator': True})
    assert lines[2].startswith('evaluator: /evaluator/cabinet subscribed')
    assert section(lines, 'ORDERS')[2].endswith('[bed_a1/cabinet]')
    assert model.observed == {'ord-0001': 'bed_a1/cabinet'}


def test_options_and_frame():
    options = view.parse_options([])
    assert (options.once, options.no_clear, options.with_evaluator, options.robot_id) == (False, False, False, 'amr_1')
    options = view.parse_options(['--once', '--no-clear', '--with-evaluator', '--robot-id', 'amr_2'])
    assert (options.once, options.no_clear, options.with_evaluator, options.robot_id) == (True, True, True, 'amr_2')
    assert view.frame(['a', 'b'], clear=True) == '\x1b[H\x1b[2Ja\nb\n'
    assert view.frame(['a'], clear=False) == '=' * 60 + '\na\n'


# 이벤트 순서 ---------------------------------------------------------------------
# 정비 실제 실행(--once, 기본 구성) 원문 순서:
#   "7.88 POUCH_DETECTED, 3.01 REQUEST_ACCEPTED, 4.38 AMR_DOCKED_LOAD, 6.24 LOAD_DONE …".
# /events 는 latched 라 늦게 붙으면 작성자별 이력이 작성자 단위로 뭉쳐 온다.
# 최근 창에서 DISPENSED·POUCH_PLACED·ARM_HOME 이 빠졌다.

def event_lines(lines):
    return section(lines, 'EVENTS')[1:]


def names(lines):
    return [line.split()[2] if not line.startswith('  ----') else line.split()[1] for line in event_lines(lines)]


def test_events_arriving_grouped_by_author_are_drawn_in_stamp_order():
    model = view.StatusModel()
    arm = [('POUCH_DETECTED', 7.88), ('PICK_ATTEMPT', 8.10), ('POUCH_PLACED', 9.40), ('ARM_HOME', 9.90)]
    orchestrator = [('REQUEST_ACCEPTED', 3.01), ('AMR_DOCKED_LOAD', 4.38), ('LOAD_DONE', 6.24), ('DEPARTED', 6.50),
                    ('ARRIVED', 7.20), ('AUTH_OK', 7.60), ('CABINET_LOCKED', 9.60), ('ORDER_DONE', 9.70)]
    dispenser = [('DISPENSED', 5.02), ('POUCH_AT_END', 5.80)]
    older = [('PICK_ATTEMPT', float(stamp)) for stamp in (0.5, 1.0, 1.5)]
    for group in (arm, orchestrator, dispenser, older):                 # 작성자 단위로 도착한다
        for name, stamp in group:
            model.note_event(event(name, 1, stamp))

    lines = view.render(model, now=0.0)
    stamps = [float(line.split()[0]) for line in event_lines(lines)]
    everything = sorted(stamp for group in (arm, orchestrator, dispenser, older) for _, stamp in group)
    assert stamps == everything[-view.MAX_EVENTS:]                      # stamp 순, 가장 늦은 12건
    assert {'DISPENSED', 'POUCH_PLACED', 'ARM_HOME'} <= set(names(lines))
    assert lines[1] == 'trip (estimated from events): 팔 홈 <- ARM_HOME'  # 마지막 도착(PICK_ATTEMPT 1.5)이 아니다


def test_events_with_the_same_stamp_keep_their_arrival_order():
    model = view.StatusModel()
    for name in ('LOAD_DONE', 'ORDER_DONE', 'ARM_HOME'):
        model.note_event(event(name, 1, 6.24))
    model.note_event(event('AMR_DOCKED_LOAD', 1, 4.38))
    assert names(view.render(model, now=0.0)) == ['AMR_DOCKED_LOAD', 'LOAD_DONE', 'ORDER_DONE', 'ARM_HOME']
    assert view.render(model, now=0.0)[1] == 'trip (estimated from events): 팔 홈 <- ARM_HOME'


def test_reset_separators_stay_between_epochs_after_sorting():
    model = view.StatusModel()
    # 새 epoch 이벤트가 먼저, 리셋 구분선과 이전 epoch 이력이 나중에 도착한다.
    # RESET_BEGIN 은 이전 epoch 의 sim stamp(24.0)를, RESET_DONE 은 되감긴 뒤의 stamp(0.4)를 싣는다.
    model.note_event(event('AMR_DOCKED_LOAD', 2, 19.8, 'r002-0001'))
    model.note_event(event('REQUEST_ACCEPTED', 2, 4.1, 'r002-0001'))
    model.note_event(event('RESET_DONE', 2, 0.4))
    model.note_event(event('RESET_BEGIN', 2, 24.0))
    model.note_event(event('ORDER_DONE', 1, 24.0, 'r001-0001', 'ord-0002'))
    model.note_event(event('DISPENSED', 1, 19.1, 'r001-0001', 'ord-0002', 'dispenser'))

    lines = view.render(model, now=0.0)
    assert names(lines) == [
        'DISPENSED', 'ORDER_DONE', 'RESET_BEGIN', 'RESET_DONE', 'REQUEST_ACCEPTED', 'AMR_DOCKED_LOAD']
    assert event_lines(lines)[2] == '  ---- RESET_BEGIN epoch 2 ----'
    assert lines[1] == 'trip (estimated from events): 배출 <- AMR_DOCKED_LOAD'

    # 실패한 barrier 뒤 다시 리셋: epoch 2 에는 RESET_BEGIN 만 있다.
    model.note_event(event('RESET_BEGIN', 3, 20.0))
    assert names(view.render(model, now=0.0))[-2:] == ['AMR_DOCKED_LOAD', 'RESET_BEGIN']
    assert view.render(model, now=0.0)[1] == 'trip (estimated from events): 리셋 중 <- RESET_BEGIN'


def test_the_event_buffer_drops_the_earliest_by_order_not_by_arrival():
    model = view.StatusModel(max_events=3, event_buffer=4)
    for stamp in (10.0, 11.0, 12.0, 13.0):
        model.note_event(event('PICK_ATTEMPT', 1, stamp))
    model.note_event(event('REQUEST_ACCEPTED', 1, 1.0))                  # 늦게 도착한 가장 이른 이벤트
    assert len(model.events) == 4
    assert min(e['stamp'] for e in model.events) == 10.0                 # 1.0 을 버렸다(13.0 이 아니라)
    assert [float(line.split()[0]) for line in event_lines(view.render(model, now=0.0))] == [11.0, 12.0, 13.0]


def test_a_long_request_accepted_detail_does_not_break_the_event_line():
    """REQUEST_ACCEPTED detail 은 요청 요약 JSON 이다. 묶음 배송이면 길어도 이벤트 한 줄은 detail 40자에서 잘린다."""
    import json

    orders = [{'order_id': f'ord-{n:04d}', 'patient_id': str(1000 + n), 'item_id': 'drug-amox'} for n in range(1, 21)]
    detail = json.dumps({'mode': 3, 'destination_id': 'station_a', 'orders': orders}, separators=(',', ':'))
    assert len(detail) > 1000
    model = view.StatusModel()
    model.note_event(event('REQUEST_ACCEPTED', 1, 3.0, 'r001-0001', detail=detail))
    [line] = event_lines(view.render(model, now=0.0))
    assert '\n' not in line and line.endswith(detail[:view.DETAIL_WIDTH - 2] + '..')
    fixed = len('  ') + 9 + len('  ') + 9 + 1 + 17 + 1 + 10 + 1          # stamp·robot_id·name·order_id 칸
    assert len(line) == fixed + view.DETAIL_WIDTH                        # 1000 자 넘는 detail 이어도 한 줄 92 자
