"""tools/hospital_orders.py — 병원 주문 10건 계획·확인·판정과, 가짜 웹으로 한 바퀴."""

import json
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import hospital_orders as ho  # noqa: E402

BEDS = ['bed_a1', 'bed_a2', 'bed_a3', 'bed_a4', 'bed_b1', 'bed_b2', 'bed_b3', 'bed_b4', 'bed_b5', 'bed_b6']
POOL = [{'order_id': f'ord-{n:04d}', 'bed': bed, 'mode': 'urgent' if n == 2 else 'single', 'used': False}
        for n, bed in enumerate(BEDS, 1)]
ROOMS = {bed: ('C1' if bed.startswith('bed_a') else 'C2') for bed in BEDS}
LABELS = {bed: f'D{n}' for n, bed in enumerate(BEDS, 1)}
#: 재범 9/25: 병동 B·병실 C 테이블 주문 셋을 더한 풀(order_pool.hospital.yaml 과 같은 모양).
TABLES = [('ord-0011', 'station_b'), ('ord-0012', 'station_c'), ('ord-0013', 'station_d')]
POOL13 = POOL + [{'order_id': o, 'bed': bed, 'mode': 'single', 'used': False} for o, bed in TABLES]
ROOMS13 = {**ROOMS, 'station_b': None, 'station_c': 'C1', 'station_d': 'C2'}


class PlanTests(unittest.TestCase):
    def test_default_plan_puts_the_urgent_after_the_first_trip_and_one_room_batch(self):
        plan = ho.build_plan(POOL)
        self.assertEqual([s['orders'] for s in plan], [
            ['ord-0001'], ['ord-0002'], ['ord-0003'], ['ord-0004'], ['ord-0005', 'ord-0006', 'ord-0007'],
            ['ord-0008'], ['ord-0009'], ['ord-0010']])
        self.assertEqual([s['mode'] for s in plan], [0, 1, 0, 0, 2, 0, 0, 0])
        self.assertEqual(plan[1]['request_id'], 'v2-02-urgent')
        self.assertEqual(plan[4]['request_id'], 'v2-05-room')
        self.assertEqual(ho.check_plan(plan, POOL, ROOMS), [])

    def test_urgent_position_and_no_batch(self):
        plan = ho.build_plan(POOL, batch=(), urgent_after=0)
        self.assertEqual(plan[0]['orders'], ['ord-0002'])
        self.assertEqual(len(plan), 10)
        self.assertTrue(all(s['mode'] in (0, 1) for s in plan))

    def test_check_plan_catches_used_orders_mixed_rooms_and_missing_ones(self):
        used = [{**o, 'used': o['order_id'] == 'ord-0003'} for o in POOL]
        self.assertIn('이미 쓴 주문 ord-0003', ' '.join(ho.check_plan(ho.build_plan(used), used, ROOMS)))
        mixed = ho.build_plan(POOL, batch=('ord-0004', 'ord-0005'))
        self.assertIn('한 병실이 아니다', ' '.join(ho.check_plan(mixed, POOL, ROOMS)))
        short = ho.build_plan(POOL)[:-1]
        self.assertIn('계획에 없는 풀 주문', ' '.join(ho.check_plan(short, POOL, ROOMS)))


class TimeoutTests(unittest.TestCase):
    def test_a_room_batch_gets_one_trip_timeout_per_bed(self):
        """9/24 master02: 정거장 셋인 병실 묶음이 1인 기준 900 s 에 걸려 멈췄다."""
        plan = ho.build_plan(POOL)
        self.assertEqual([ho.stops(s) for s in plan], [1, 1, 1, 1, 3, 1, 1, 1])


class ProfileTests(unittest.TestCase):
    """재범 9/24 "병상 병실 다 테스트" — beds-all·station-b 프로필."""

    def test_beds_all_visits_every_bed_of_both_rooms_once_with_one_urgent(self):
        plan = ho.profile_plan('beds-all', POOL, ho.DEFAULT_BATCH, urgent_after=1)
        self.assertEqual(len(plan), 10)
        self.assertEqual([s['orders'][0] for s in plan][1], 'ord-0002')
        self.assertEqual({s['mode'] for s in plan}, {0, 1})
        beds = [POOL[int(s['orders'][0][-2:]) - 1]['bed'] for s in plan]
        self.assertEqual(sorted(beds), sorted(BEDS))
        self.assertEqual({ROOMS[b] for b in beds}, {'C1', 'C2'})
        self.assertTrue(all(s['request_id'].startswith('beds-') for s in plan))
        self.assertEqual(ho.check_plan(plan, POOL, ROOMS), [])

    def test_beds_all_adds_the_two_room_tables_and_the_ward_table(self):
        """재범 9/25 03:3x: D1–D10 + C1 + C2 + B = 요청 13(그중 긴급 1). C 는 병실 묶음 1건, B 는 1인."""
        plan = ho.profile_plan('beds-all', POOL13, ho.DEFAULT_BATCH, urgent_after=1)
        self.assertEqual(len(plan), 13)
        self.assertEqual(sum(s['urgent'] for s in plan), 1)
        self.assertEqual([(s['mode'], s['destination_id'], s['orders']) for s in plan[-3:]],
                         [(2, 'station_c', ['ord-0012']), (2, 'station_d', ['ord-0013']),
                          (0, 'station_b', ['ord-0011'])])
        self.assertEqual([s['request_id'] for s in plan[-3:]], ['beds-11-room', 'beds-12-room', 'beds-13-single'])
        self.assertEqual(ho.check_plan(plan, POOL13, ROOMS13), [])
        self.assertIn('계획에 없는 풀 주문', ' '.join(ho.check_plan(plan[:-1], POOL13, ROOMS13)))

    def test_default_plan_ignores_table_orders_and_still_needs_every_bed(self):
        plan = ho.build_plan(POOL13)
        self.assertEqual([s['orders'] for s in plan], [s['orders'] for s in ho.build_plan(POOL)])
        self.assertEqual(ho.check_plan(plan, POOL13, ROOMS13), [])
        self.assertIn('계획에 없는 풀 주문', ' '.join(ho.check_plan(plan[:-1], POOL13, ROOMS13)))

    def test_station_b_waits_for_the_zone(self):
        plan = ho.profile_plan('station-b', POOL, ho.DEFAULT_BATCH, urgent_after=1)
        self.assertEqual([(s['mode'], s['destination_id'], s['orders']) for s in plan],
                         [(3, 'station_b', ['ord-0005', 'ord-0006', 'ord-0007'])])
        self.assertEqual(ho.stops(plan[0]), 1)
        missing = ho.check_plan(plan, POOL, ROOMS, require_all=False)
        self.assertEqual(len(missing), 1)
        self.assertIn('station_b 가 zones 에 없다', missing[0])
        with_zone = {**ROOMS, 'station_b': None}
        self.assertEqual(ho.check_plan(plan, POOL, with_zone, require_all=False), [], '3건만 넣어도 된다')


class SummaryTests(unittest.TestCase):
    def test_times_and_verdict(self):
        plan = ho.build_plan(POOL)[:2]
        events = [{'name': 'REQUEST_ACCEPTED', 'request_id': 'v2-01-single', 'stamp': 10.0},
                  {'name': 'CABINET_LOCKED', 'request_id': 'v2-01-single', 'order_id': 'ord-0001', 'stamp': 15.5},
                  {'name': 'DOCKED', 'request_id': 'v2-01-single', 'stamp': 17.0},
                  {'name': 'REQUEST_ACCEPTED', 'request_id': 'v2-02-urgent', 'stamp': 20.0}]
        timing = {'v2-01-single': {'queued_wall': 100.0, 'accepted_wall': 101.25},
                  'v2-02-urgent': {'queued_wall': 108.0, 'accepted_wall': 108.5, 'retries': 2}}
        result = ho.summarize(plan, events, {'ord-0001': 'delivered', 'ord-0002': 'held'}, timing, POOL, LABELS)
        first, second = result['orders']
        self.assertEqual((first['wait_s'], first['deliver_sim_s'], first['label']), (1.25, 5.5, 'D1'))
        self.assertEqual((second['wait_s'], second['deliver_sim_s'], second['outcome']), (0.5, None, 'held'))
        self.assertEqual(result['requests'][0]['trip_sim_s'], 7.0)
        self.assertEqual((result['verdict'], result['delivered'], result['total']), ('FAIL', 1, 2))
        self.assertIn('**FAIL** (1/2 delivered)', ho.summary_markdown(result))


class FakeWeb:
    """트립을 흉내 내는 웹. 스냅숏을 몇 번 부르면 트립이 도크로 닫힌다. 첫 요청은 한 번 보충 중으로 거부한다."""

    def __init__(self, queue=True, held=None, lag=0, hide_orders=False, stuck=None, refuse_first=True):
        self.queue, self.held = queue, held or {}   # held: {order_id: reason} — 그 주문은 회수로 끝난다
        # lag: 수락 이벤트는 바로 나오는데 스냅숏은 그 스냅숏 수만큼 아직 앞 트립(한가함)을 보인다(실물의 늦은 반영).
        # hide_orders: 스냅숏이 트립 주문을 안 싣는다(폴링 사이에 트립을 통째로 놓친 경우).
        self.lag, self.hide_orders, self.lagging = lag, hide_orders, 0
        self.stuck = stuck   # 이 요청의 트립은 닫히지 않는다(실물의 이동 중 정지)
        self.events, self.outcomes, self.trip, self.polls = [], {}, None, 0
        self.stamp, self.refused_once, self.lock = 0.0, not refuse_first, threading.Lock()

    def event(self, name, rid, order_id=''):
        self.stamp += 1.0
        self.events.append({'seq': len(self.events) + 1, 'epoch': 1, 'name': name, 'request_id': rid,
                            'order_id': order_id, 'stamp': self.stamp})

    def snapshot(self):
        orders = []
        if self.lagging > 0:
            self.lagging -= 1
            return {'epoch': 1, 'accepting_requests': True, 'trip': None}
        if self.trip is not None:
            self.polls += 1
            rid, ids = self.trip
            if self.polls == 2:          # 트립이 열린 채로 주문이 닫힌다(실물의 ORDER_DONE 자리)
                for order_id in ids:
                    if order_id in self.held:
                        self.outcomes[order_id] = 'held'
                    else:
                        self.event('CABINET_LOCKED', rid, order_id)
                        self.outcomes[order_id] = 'delivered'
            orders = [{'order_id': o, 'outcome': self.outcomes.get(o, 'in_progress'), 'reason': self.held.get(o, '')}
                      for o in ids]
            if self.polls == 3 and rid != self.stuck:
                self.event('DOCKED', rid)
                self.trip = None
        trip = {'request_id': self.trip[0], 'phase': 'order_done', 'phase_label': '주문 닫힘',
                'orders': [] if self.hide_orders else orders} if self.trip else None
        return {'epoch': 1, 'accepting_requests': True, 'trip': trip}

    def request(self, body):
        if not self.refused_once:
            self.refused_once = True
            return 409, {'error': {'code': 'refill_in_progress', 'message': '보충 중'}}
        if self.trip is not None:
            return 409, {'error': {'code': 'trip_in_progress', 'message': '트립 중'}}
        orders = [o['order_id'] for o in body['orders']]
        self.trip, self.polls, self.lagging = (body['request_id'], orders), 0, self.lag
        self.event('REQUEST_ACCEPTED', body['request_id'])
        return 200, {'ok': True}

    def serve(self):
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def reply(self, code, body):
                data = json.dumps(body).encode()
                self.send_response(code)
                self.send_header('content-type', 'application/json')
                self.send_header('content-length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                with fake.lock:
                    path = self.path.split('?')[0]
                    if path == '/api/order_pool':
                        used = {e['order_id'] for e in fake.events if e['order_id']}
                        return self.reply(200, {'orders': [{**o, 'used': o['order_id'] in used} for o in POOL]})
                    if path == '/api/destinations':
                        return self.reply(200, {'destinations': [
                            {'destination_id': b, 'group': ROOMS[b], 'label': LABELS[b]} for b in BEDS]})
                    if path == '/api/snapshot':
                        return self.reply(200, fake.snapshot())
                    if path == '/api/events':
                        return self.reply(200, {'events': fake.events, 'has_more': False, 'next_since': 0})
                    if path == '/api/queue' and fake.queue:
                        done = [{'order_id': k, 'outcome': v} for k, v in fake.outcomes.items()]
                        return self.reply(200, {'waiting': [], 'in_progress': [], 'done': done})
                    return self.reply(404, {})

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers['content-length'])))
                with fake.lock:
                    self.reply(*fake.request(body))

        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        return server


class RunTests(unittest.TestCase):
    def test_ten_orders_through_a_fake_web_pass_and_leave_logs(self):
        fake = FakeWeb()
        server = fake.serve()
        try:
            with tempfile.TemporaryDirectory() as out:
                code = ho.main(['--web', f'http://127.0.0.1:{server.server_port}', '--out', out])
                orders = [json.loads(line) for line in Path(out, 'orders.jsonl').read_text().splitlines()]
                requests = [json.loads(line) for line in Path(out, 'requests.jsonl').read_text().splitlines()]
                summary = Path(out, 'summary.md').read_text(encoding='utf-8')
        finally:
            server.shutdown()
        self.assertEqual(code, 0)
        self.assertEqual(len(orders), 10)
        self.assertTrue(all(o['outcome'] == 'delivered' and o['deliver_sim_s'] is not None for o in orders))
        self.assertEqual(requests[0]['retries'], 1, '보충 중 거부는 기다렸다 다시 보낸다')
        self.assertEqual([r['request_id'] for r in requests][1], 'v2-02-urgent')
        self.assertIn('**PASS** (10/10 delivered)', summary)

    def run_fake(self, fake, *extra):
        server = fake.serve()
        try:
            with tempfile.TemporaryDirectory() as out:
                code = ho.main(['--web', f'http://127.0.0.1:{server.server_port}', '--out', out, *extra])
                orders = [json.loads(line) for line in Path(out, 'orders.jsonl').read_text().splitlines()]
                summary = Path(out, 'summary.md').read_text(encoding='utf-8')
        finally:
            server.shutdown()
        return code, orders, summary

    def test_a_web_without_the_queue_api_is_judged_from_the_snapshot(self):
        """9/23 골든(4d01333)의 웹에는 /api/queue(#586)가 없다. 스냅숏의 트립 주문으로 판정한다."""
        code, orders, summary = self.run_fake(FakeWeb(queue=False))
        self.assertEqual(code, 0)
        self.assertTrue(all(o['outcome'] == 'delivered' for o in orders))
        self.assertIn('**PASS** (10/10 delivered)', summary)

    def test_a_held_order_fails_with_its_reason_and_the_run_goes_on(self):
        code, orders, summary = self.run_fake(FakeWeb(queue=False, held={'ord-0004': 'tag_unreadable'}))
        self.assertEqual(code, 1)
        held = [o for o in orders if o['outcome'] != 'delivered']
        self.assertEqual([(o['order_id'], o['outcome'], o['reason']) for o in held],
                         [('ord-0004', 'held', 'tag_unreadable')])
        self.assertEqual(sum(o['outcome'] == 'delivered' for o in orders), 9, '회수 뒤에도 나머지를 계속 넣는다')
        self.assertIn('**FAIL** (9/10 delivered)', summary)
        self.assertIn('| 주문 닫힘 |', summary)

    def test_a_late_snapshot_does_not_end_the_trip_early(self):
        """커서 검토(#616): 수락 이벤트가 이미 있는데 스냅숏은 아직 한가하면 트립을 끝났다고 읽었다.
        트립이 끝났다는 것은 그 요청의 DOCKED 로만 본다."""
        code, orders, summary = self.run_fake(FakeWeb(queue=False, lag=2))
        self.assertEqual(code, 0, summary)
        self.assertTrue(all(o['outcome'] == 'delivered' for o in orders), orders)

    def test_without_the_queue_api_a_locked_cabinet_counts_as_delivered(self):
        """커서 검토(#616): /api/queue 가 없고 스냅숏이 주문을 못 봤으면 결말이 비어 FAIL 이었다.
        그 주문의 CABINET_LOCKED 가 있으면 delivered 로 보고, 출처를 적는다."""
        code, orders, summary = self.run_fake(FakeWeb(queue=False, hide_orders=True))
        self.assertEqual(code, 0, summary)
        self.assertTrue(all(o['outcome'] == 'delivered' and o['outcome_source'] == 'cabinet_locked' for o in orders))

    def test_a_stuck_trip_stops_the_run_and_the_summary_says_where_why_and_when(self):
        """9/24 master02: 병실 묶음이 이동 중에 시한에 걸렸다.

        막힌 건·사유·시각과 보내지 않은 주문이 맨 위에 나와야 한다(작전).
        """
        fake = FakeWeb(queue=False, stuck='v2-05-room', refuse_first=False)
        code, orders, summary = self.run_fake(fake, '--trip-timeout', '4')
        self.assertEqual(code, 1)
        head = summary.splitlines()[2]
        self.assertRegex(head, r'^\*\*멈춤\*\* \d{4}-\d\d-\d\dT\d\d:\d\d:\d\d — '
                               r'v2-05-room\(ord-0005 ord-0006 ord-0007\): 트립 시한\(12 s\), '
                               r'마지막 단계 주문 닫힘\. 보내지 않은 주문: ord-0008 ord-0009 ord-0010$')
        self.assertEqual([o['order_id'] for o in orders if o['outcome_source'] == 'not_sent'],
                         ['ord-0008', 'ord-0009', 'ord-0010'])
        self.assertIn('| ord-0008 | D8 | v2-06-single |  | 미실행 |', summary)

    def test_station_b_without_the_zone_sends_nothing(self):
        fake = FakeWeb()
        server = fake.serve()
        try:
            with tempfile.TemporaryDirectory() as out:
                web = f'http://127.0.0.1:{server.server_port}'
                code = ho.main(['--web', web, '--out', out, '--profile', 'station-b'])
        finally:
            server.shutdown()
        self.assertEqual(code, 2)
        self.assertEqual(fake.events, [])

    def test_dry_run_sends_nothing(self):
        fake = FakeWeb()
        server = fake.serve()
        try:
            with tempfile.TemporaryDirectory() as out:
                code = ho.main(['--web', f'http://127.0.0.1:{server.server_port}', '--out', out, '--dry-run'])
        finally:
            server.shutdown()
        self.assertEqual(code, 0)
        self.assertEqual(fake.events, [])


if __name__ == '__main__':
    unittest.main()
