"""tools/judge_run.py. 9/21 회차의 **실제 로그 원문**을 fixture 로 쓴다.

줄은 맥마클2(실습22·23)와 맥마클1(실습21d·20b)이 보낸 원문 그대로다. 출처를 시험마다 적었다.
여기서 잠그는 것은 "그날 사람이 손으로 세다 틀린 자리" 다.
"""

import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))

import judge_run  # noqa: E402

# 실습22 kit 로그 10649·10709·10711 (맥마클2)
KIT = [
    '2026-09-21T03:06:40Z [9,191ms] [Warning] [omni.hydra] Mesh '
    "'/World/P3Pharmacy/Arm/Mount/m0609/link_2/visuals/MF0609_2_1/Scene/mesh' update topology/point "
    'without updating normal, fallback to smooth normal.',
    '2026-09-21T03:06:40Z [9,246ms] [Info] [omni.kit.app._impl] [py stdout]: '
    '[pharmacy_stage] timeline_event type=PLAY sim_time=0.000',
    '2026-09-21T03:06:40Z [9,248ms] [Warning] [omni.timeline.plugin] Deprecated: direct use of '
    'ITimeline callbacks is deprecated. Use ITimeline::getTimeline '
    '(Python: omni.timeline.get_timeline_interface) instead.',
]

# 실습22 stage.log 558·654·661 (맥마클2). 654 는 PLAY 보다 아래 줄인데 ms 는 더 이르다.
STAGE_MIXED = [
    '[pharmacy_stage] timeline_event type=PLAY sim_time=0.000',
    '2026-09-21T03:06:39Z [8,316ms] [Warning] [omni.usd] Warning: in _ReportErrors at line 3172 of '
    '/builds/omniverse/usd-ci/USD/pxr/usd/usd/stage.cpp -- In '
    '</World/P3Pharmacy/Arm/Mount/m0609/onrobot_rg2ft/world/visuals>: Unresolved reference prim path',
    '2026-09-21T03:06:40Z [9,248ms] [Warning] [omni.timeline.plugin] Deprecated: direct use of '
    'ITimeline callbacks is deprecated. Use ITimeline::getTimeline '
    '(Python: omni.timeline.get_timeline_interface) instead.',
]

# 실습22 arm 로그 17·18 (맥마클2)
ARM_WARNS = [
    '[WARN] [1789960243.218919203] [m0609_arm]: joint_states 수신 공백 0.21 s(wall). '
    'stale 은 1.0 s, 유예 3.0 s.',
    '[WARN] [1789960243.219404633] [m0609_arm]: rail/joint_states 수신 공백 0.22 s(wall). '
    'stale 은 1.0 s, 유예 3.0 s.',
]

# 실습22 stack 로그 62 (맥마클2). 노드 이름표가 없어 노드별 집계에서 통째로 빠지던 줄이다.
STACK_SIGINT = '[WARNING] [launch]: user interrupted with ctrl-c (SIGINT)'

# 실습21d stage.log 23233·23297·23311 (맥마클1). 낙하 한 건이 이 구간 안에 있다.
DROP_SPAN = [
    '[pharmacy_stage] refill_ros released cell=upper_left/r0c1 type=module target=module '
    'canister=[1.1531, 0.7193, 1.0174] sim_time=697.433 respawn_in_s=2.0',
    '[pharmacy_stage] contact found touch a=/World/P3Pharmacy/Shelf/upper_left_r0c1 '
    'b=/World/P3Pharmacy/GroundPlane/geom impulse=0.4122 sep=0.0695 at=[1.088, 0.555, 0.000] '
    'count=1 sim_time=698.800',
    '[pharmacy_stage] refill_ros respawn cell=upper_left/r0c1 '
    'canister_home=[-0.8500, 0.9100, 1.2400]',
]

# 실습21d stage.log 17208·17209 (맥마클1). 낙하가 아니다 — near, impulse 0.
NEAR_LINES = [
    '[pharmacy_stage] contact found near a=/World/P3Pharmacy/Shelf/upper_left_r0c0 '
    'b=/World/P3Pharmacy/GroundPlane/collisionPlane impulse=0.0000 sep=0.0785 '
    'at=[1.156, 0.559, 0.000] count=1 sim_time=514.500',
    '[pharmacy_stage] contact found near a=/World/P3Pharmacy/Shelf/upper_left_r0c0 '
    'b=/World/P3Pharmacy/GroundPlane/geom impulse=0.0000 sep=0.0785 '
    'at=[1.156, 0.559, -0.000] count=1 sim_time=514.500',
]

# 실습23b stage.log 524 (맥마클2). 바닥이 아니라 선반 판이다.
SHELF_TOUCH = (
    '[pharmacy_stage] contact found touch a=/World/P3Pharmacy/Shelf/floor_right_r0c1 '
    'b=/World/P3Pharmacy/Room/FloorRightShelfBoard0 impulse=0.0163 sep=-0.0000 '
    'at=[-0.128, 0.937, 0.550] count=1 sim_time=0.000')

# 실습22 stage.log 10984 (맥마클2)
STOP_22 = ('[pharmacy_stage] stop reason=sigint updates=19992 wall_s=334.942 loop_hz=59.69 '
           'sim_s=333.200 rtf=0.995 dispensed=4 render_products=0 ur5=off '
           'pick_notices_ignored_ur5=0 gripper_bool_ignored=0 contact_watch=on')

# 실습20 B arm 로그 13·14 / 실습21d arm 로그 12 (맥마클1)
REFILL_FAILED = ('[INFO] [1789.0] [m0609_arm]: Refill drug-ibu 단계 시간(sim s, 마지막은 결과 전 '
                 '복귀 포함, failed): plan 0.00, rail_to_shelf_z 1.53, rail_to_shelf_xy 1.35')
REFILL_FAILED_WHY = '[WARN] [1789.0] [m0609_arm]: Refill drug-ibu: 실패. rail_to_inlet_xy: 레일 이동 실패'
REFILL_OK = ('[INFO] [1789.0] [m0609_arm]: Refill drug-ibu 단계 시간(sim s, 마지막은 결과 전 '
             '복귀 포함, ok): plan 0.00, rail_to_shelf_z 1.53, rail_to_shelf_xy 1.37')

# 9/20 실습13 web 로그 13 (맥마클1)
WEB_409 = 'INFO:     127.0.0.1:45976 - "POST /api/requests HTTP/1.1" 409 Conflict'
WEB_200 = 'INFO:     127.0.0.1:40996 - "GET /api/state HTTP/1.1" 200 OK'

# 실습22 run 디렉토리 (맥마클2)
EVENT_ACCEPTED = {'detail': '', 'epoch': 1, 'name': 'REQUEST_ACCEPTED', 'order_id': '',
                  'request_id': 'r001-0001', 'robot_id': 'amr_1', 'stale': False,
                  'stamp': 69.000003598}
EVENT_DOCKED_LOAD = {'epoch': 1, 'name': 'AMR_DOCKED_LOAD', 'order_id': 'ord-0002',
                     'request_id': 'r001-0001', 'stale': False, 'stamp': 75.0}
EVENT_DOCKED = {'epoch': 1, 'name': 'DOCKED', 'order_id': 'ord-0002',
                'request_id': 'r001-0001', 'stale': False, 'stamp': 101.5}


class PlayCutTests(unittest.TestCase):
    """PLAY 를 줄 번호로 자르면 틀린다. ms 카운터로 자른다."""

    def test_play_comes_from_the_kit_counter(self):
        self.assertEqual(9246, judge_run.play_ms(KIT))

    def test_stage_lines_without_a_head_have_no_counter(self):
        self.assertIsNone(judge_run.kit_ms(STAGE_MIXED[0]))
        self.assertEqual(8316, judge_run.kit_ms(STAGE_MIXED[1]))

    def test_a_warning_below_play_can_still_be_before_it(self):
        # 654 행은 558 행(PLAY)보다 아래인데 8,316ms 라 PLAY(9,246ms) 이전이다. 세지 않는다.
        kinds = judge_run.warn_kinds(STAGE_MIXED, after_ms=9246)
        self.assertEqual(1, len(kinds))
        self.assertIn('ITimeline', kinds[0]['evidence']['text'])

    def test_without_a_cut_both_warnings_are_counted(self):
        self.assertEqual(2, len(judge_run.warn_kinds(STAGE_MIXED)))


class WarnKindTests(unittest.TestCase):
    def test_the_two_arm_warnings_are_two_kinds(self):
        kinds = judge_run.warn_kinds(ARM_WARNS)
        self.assertEqual(2, len(kinds))

    def test_the_same_warning_with_other_numbers_is_one_kind(self):
        other = ARM_WARNS[0].replace('0.21', '0.47').replace('218919203', '918919203')
        self.assertEqual(judge_run.warn_kind(ARM_WARNS[0]), judge_run.warn_kind(other))

    def test_the_launch_sigint_line_is_counted_even_without_a_node_label(self):
        # 9/20-9/21 의 "새 종류 WARN 0" 이 이 줄을 빠뜨린 값이었다.
        kinds = judge_run.warn_kinds([STACK_SIGINT])
        self.assertEqual(1, len(kinds))
        self.assertIn('SIGINT', kinds[0]['evidence']['text'])

    def test_a_baseline_kind_is_marked_known(self):
        baseline = {judge_run.warn_kind(STACK_SIGINT)}
        kinds = judge_run.warn_kinds([STACK_SIGINT, ARM_WARNS[0]], baseline)
        known = {row['kind']: row['known'] for row in kinds}
        self.assertEqual([True, False], [known[judge_run.warn_kind(STACK_SIGINT)],
                                         known[judge_run.warn_kind(ARM_WARNS[0])]])


class DropTests(unittest.TestCase):
    """#397 의 낙하 정의. `grep GroundPlane` 으로 세면 near 가 섞인다."""

    def test_one_drop_between_released_and_respawn(self):
        found = judge_run.drops(DROP_SPAN)
        self.assertEqual(1, len(found))
        self.assertEqual('upper_left/r0c1', found[0]['cell'])
        self.assertEqual(2, found[0]['hits'][0]['line_no'])

    def test_near_with_zero_impulse_is_not_a_drop(self):
        lines = [DROP_SPAN[0], *NEAR_LINES, DROP_SPAN[2]]
        self.assertEqual([], judge_run.drops(lines))

    def test_touching_a_shelf_board_is_not_a_drop(self):
        lines = [DROP_SPAN[0], SHELF_TOUCH, DROP_SPAN[2]]
        self.assertEqual([], judge_run.drops(lines))

    def test_two_floor_colliders_in_one_span_are_one_drop(self):
        # geom 과 collisionPlane 은 같은 바닥의 두 충돌체다(구간당 1 건으로 접는다).
        both = DROP_SPAN[1].replace('/GroundPlane/geom', '/GroundPlane/collisionPlane')
        found = judge_run.drops([DROP_SPAN[0], DROP_SPAN[1], both, DROP_SPAN[2]])
        self.assertEqual(1, len(found))
        self.assertEqual(2, len(found[0]['hits']))

    def test_a_contact_outside_the_span_is_not_counted(self):
        lines = [DROP_SPAN[0], DROP_SPAN[2], DROP_SPAN[1]]
        self.assertEqual([], judge_run.drops(lines))

    def test_the_span_is_taken_by_line_order_not_by_sim_time(self):
        # 같은 칸의 released 가 여러 번 나온다. 앞선 released 의 sim 시각이 더 크더라도
        # 낙하 줄이 든 구간은 바로 위의 released 다(맥마클1 이 sim 시각으로 짝지어 틀렸다).
        earlier = DROP_SPAN[0].replace('sim_time=697.433', 'sim_time=923.100')
        found = judge_run.drops([earlier, DROP_SPAN[2], DROP_SPAN[0], DROP_SPAN[1], DROP_SPAN[2]])
        self.assertEqual(1, len(found))
        self.assertEqual(3, found[0]['released']['line_no'])


class RefillTests(unittest.TestCase):
    def test_ok_and_failed_are_told_apart_by_the_result_token(self):
        counted = judge_run.refills([DROP_SPAN[0]], [REFILL_OK, REFILL_FAILED, REFILL_FAILED_WHY])
        self.assertEqual((1, 1, 1), (counted['released'], counted['ok'], counted['failed']))
        self.assertIn('failed', counted['failed_evidence'][0]['text'])

    def test_released_is_counted_from_the_stage_log_only(self):
        counted = judge_run.refills(DROP_SPAN * 3, [])
        self.assertEqual(3, counted['released'])      # 바퀴 수에 곱하지 않는다


class HttpTests(unittest.TestCase):
    def test_a_port_number_is_not_a_status_code(self):
        # `grep 409` 가 포트 45976·40996 에 걸려 거부 19 건이 나왔던 자리다.
        rejects = judge_run.http_rejects([WEB_409, WEB_200])
        self.assertEqual([409], [row['code'] for row in rejects])


class TracebackTests(unittest.TestCase):
    def test_only_the_real_traceback_header_is_counted(self):
        lines = ['[INFO] a1_probe {"stack": ["frame"]}',
                 '  warnings.warn(traceback.format_stack())',
                 'Traceback (most recent call last):']
        _, traces = judge_run.errors(lines)
        self.assertEqual(1, len(traces))


class TripTests(unittest.TestCase):
    def test_docked_load_does_not_close_a_trip(self):
        # `grep "DOCKED.*<request_id>"` 가 AMR_DOCKED_LOAD 에 먼저 걸렸던 자리다.
        found = judge_run.trips([EVENT_ACCEPTED, EVENT_DOCKED_LOAD, EVENT_DOCKED])
        self.assertEqual(1, len(found))
        self.assertAlmostEqual(32.5, found[0]['seconds'], places=2)

    def test_an_unfinished_trip_is_reported_without_a_duration(self):
        found = judge_run.trips([EVENT_ACCEPTED, EVENT_DOCKED_LOAD])
        self.assertEqual([None], [row['seconds'] for row in found])

    def test_event_order_mismatch_points_at_the_first_difference(self):
        events = [EVENT_ACCEPTED, EVENT_DOCKED]
        mismatch = judge_run.order_mismatch(events, ['REQUEST_ACCEPTED', 'AMR_DOCKED_LOAD'])
        self.assertEqual({'at': 1, 'expected': 'AMR_DOCKED_LOAD', 'got': 'DOCKED'}, mismatch)

    def test_laps_count_only_closed_trips(self):
        # 미완료 요청도 laps 에 넣으면 출발만 세 번이 min:3 을 통과한다(F01 J1).
        found = judge_run.trips([
            {**EVENT_ACCEPTED, 'request_id': 'r1', 'stamp': 1.0},
            {**EVENT_ACCEPTED, 'request_id': 'r2', 'stamp': 2.0},
            {**EVENT_ACCEPTED, 'request_id': 'r3', 'stamp': 3.0},
        ])
        self.assertEqual(3, len(found))
        self.assertEqual(0, len(judge_run.closed_trips(found)))
        self.assertEqual(3, len(judge_run.open_trips(found)))


class ReachedStageTests(unittest.TestCase):
    """도달 단계는 손으로 세던 것이다(도달표). 이벤트에서 바로 뽑는다."""

    def lap(self, count):
        return [{'name': name, 'stale': False, 'stamp': float(index)}
                for index, name in enumerate(judge_run.LAP_ORDER[:count])]

    def test_no_events_means_the_run_did_not_start(self):
        got = judge_run.reached([])
        self.assertEqual('기동(이벤트 0)', got['stage'])
        self.assertEqual('REQUEST_ACCEPTED', got['expected_next'])

    def test_a_full_lap_reaches_the_last_stage(self):
        got = judge_run.reached(self.lap(len(judge_run.LAP_ORDER)))
        self.assertEqual('⑩ 도킹', got['stage'])
        self.assertIsNone(got['expected_next'])

    def test_the_stage_is_the_last_completed_one(self):
        """⑧ 의 첫 이벤트만 왔으면 아직 ⑦ 이다. 반쯤 간 단계를 도달로 세지 않는다."""
        upto_auth = judge_run.LAP_ORDER.index('AUTH_OK') + 1
        self.assertEqual('⑦ 환자 인증', judge_run.reached(self.lap(upto_auth))['stage'])
        got = judge_run.reached(self.lap(upto_auth + 1))          # + POUCH_DETECTED
        self.assertEqual('⑦ 환자 인증', got['stage'])
        self.assertEqual('PICK_ATTEMPT', got['expected_next'])

    def test_a_repeated_event_name_is_followed_by_position(self):
        """PICK_ATTEMPT·ARM_HOME 은 두 번 나온다. 이름으로 찾으면 ⑧ 의 픽을 ⑤ 로 센다."""
        got = judge_run.reached(self.lap(judge_run.LAP_ORDER.index('PICK_ATTEMPT') + 1))
        self.assertEqual('④ 벨트 끝', got['stage'])               # ⑤ 는 ARM_HOME 까지 가야 끝난다
        self.assertEqual('POUCH_PICKED', got['expected_next'])

    def test_what_actually_came_instead_is_reported(self):
        rows = self.lap(judge_run.LAP_ORDER.index('AUTH_OK') + 1)
        rows.append({'name': 'AUTH_FAIL', 'stale': False, 'stamp': 99.0})
        got = judge_run.reached(rows)
        self.assertEqual('⑦ 환자 인증', got['stage'])
        self.assertEqual(['AUTH_FAIL'], got['seen_after'])

    def test_stale_events_do_not_advance_the_stage(self):
        rows = self.lap(1) + [{'name': 'AMR_DOCKED_LOAD', 'stale': True, 'stamp': 2.0}]
        self.assertEqual('① 요청 접수', judge_run.reached(rows)['stage'])


class StopLineTests(unittest.TestCase):
    def test_flags_come_from_the_stop_line(self):
        flags = judge_run.stop_flags(['[pharmacy_stage] ...', STOP_22])
        self.assertEqual(('sigint', '0.995', 'on', 'off'),
                         (flags['reason'], flags['rtf'], flags['contact_watch'], flags['ur5']))

    def test_a_run_without_a_stop_line_is_not_guessed(self):
        self.assertIsNone(judge_run.stop_flags(['[pharmacy_stage] timeline_event type=PLAY']))


class EndToEndTests(unittest.TestCase):
    """로그 디렉토리와 run 디렉토리를 만들어 한 번 돌린다. 빈 cabinet.jsonl 도 있음으로 센다."""

    def write_run(self, root):
        run_dir = Path(root) / 'runs' / '20260921T030746Z-master02-c445420a'
        run_dir.mkdir(parents=True)
        with open(run_dir / 'events.jsonl', 'w', encoding='utf-8') as handle:
            for row in (EVENT_ACCEPTED, EVENT_DOCKED_LOAD, EVENT_DOCKED):
                handle.write(json.dumps(row) + '\n')
        (run_dir / 'cabinet.jsonl').write_text('', encoding='utf-8')      # 0 바이트, 정상이다
        (run_dir / 'order_status.jsonl').write_text('', encoding='utf-8')
        with open(run_dir / 'orders.jsonl', 'w', encoding='utf-8') as handle:
            handle.write(json.dumps({'order_id': 'ord-0002', 'state': 'HOLD_RETURN',
                                     'observed': False, 'reason': 'pharmacy_only'}) + '\n')
        (run_dir / 'meta.json').write_text('{}', encoding='utf-8')
        return run_dir

    def write_logs(self, root):
        logs = Path(root) / 'logs'
        logs.mkdir()
        (logs / 'p22-kit.log').write_text('\n'.join(KIT), encoding='utf-8')
        (logs / 'p22-stage.log').write_text('\n'.join([*STAGE_MIXED, *DROP_SPAN, STOP_22]),
                                            encoding='utf-8')
        (logs / 'p22-arm.log').write_text('\n'.join([*ARM_WARNS, REFILL_OK]), encoding='utf-8')
        (logs / 'p22-stack.log').write_text(STACK_SIGINT, encoding='utf-8')
        (logs / 'p22-web.log').write_text('\n'.join([WEB_200, WEB_409]), encoding='utf-8')
        return logs

    def test_counts_and_verdicts(self):
        with tempfile.TemporaryDirectory() as root:
            logs, run_dir = self.write_logs(root), self.write_run(root)
            criteria = {'warn_baseline': [judge_run.warn_kind(line) for line in ARM_WARNS]
                        + [judge_run.warn_kind(STACK_SIGINT)],
                        'gates': {'drops': {'max': 0}, 'laps': {'min': 1},
                                  'http_rejects': {'max': 0}}}
            counted = judge_run.collect(str(logs), 'p22', str(run_dir), criteria)
            judged, new_warn = judge_run.verdicts(counted, criteria)

        self.assertEqual(1, len(counted['trips']))
        self.assertEqual(0, len(counted['drops']))          # run 구간(69-101.5 s) 밖이다
        self.assertEqual(1, counted['refills']['ok'])       # 팔 로그는 세션 전체다
        self.assertEqual([409], [row['code'] for row in counted['http_rejects']])
        self.assertEqual('sigint', counted['stop']['reason'])
        self.assertTrue(all(counted['run_files'].values()))          # 빈 파일도 있음이다
        by_name = {row['name']: row for row in judged}
        self.assertTrue(by_name['drops']['ok'])                      # run 구간 안에는 낙하가 없다
        self.assertTrue(by_name['laps']['ok'])
        self.assertFalse(by_name['http_rejects']['ok'])
        self.assertIsNone(by_name['errors']['ok'])                   # 기준이 없으면 판정하지 않는다
        # arm 둘과 stack SIGINT 는 기준 목록에 있다. 남는 것은 PLAY 뒤 Kit 경고 한 종류다.
        # 그 줄은 stage 로그와 kit 로그에 **같은 줄로 두 번** 들어 있다. 종류는 하나로 센다.
        self.assertEqual(1, len(new_warn))
        self.assertIn('ITimeline', new_warn[0]['evidence']['text'])
        self.assertEqual(['kit', 'stage'], sorted(new_warn[0]['roles']))
        self.assertEqual(1, new_warn[0]['count'])           # 두 로그에 있어도 한 줄이다

    def test_the_table_carries_evidence_lines(self):
        with tempfile.TemporaryDirectory() as root:
            logs, run_dir = self.write_logs(root), self.write_run(root)
            counted = judge_run.collect(str(logs), 'p22', str(run_dir), {})
            judged, new_warn = judge_run.verdicts(counted, {})
            table = judge_run.render(counted, judged, new_warn)
        self.assertIn('근거', table)
        self.assertIn('contact_watch=on', table)
        self.assertIn('기준 없음', table)                  # 기준 파일이 없으면 판정하지 않는다
        self.assertIn('세션 전체다', table)                # 팔 로그의 범위를 표에 밝힌다
        self.assertIn('도달', table)                      # 도달 단계가 표 앞에 나온다

    def test_the_drop_evidence_is_shown_when_it_is_inside_the_window(self):
        with tempfile.TemporaryDirectory() as root:
            logs = self.write_logs(root)
            counted = judge_run.collect(str(logs), 'p22', '', {})
            judged, new_warn = judge_run.verdicts(counted, {})
            table = judge_run.render(counted, judged, new_warn)
        self.assertIn('GroundPlane/geom', table)          # 낙하 판정의 원문

    def test_missing_logs_are_not_an_error(self):
        with tempfile.TemporaryDirectory() as root:
            counted = judge_run.collect(root, 'no-such-stamp', '', {})
            judged, new_warn = judge_run.verdicts(counted, {})
            table = judge_run.render(counted, judged, new_warn)
        self.assertEqual([], counted['trips'])
        self.assertIsNone(counted['play_ms'])
        # --run 을 안 주면 "0/5 없음" 이 아니라 "해당 없음" 이다(스테이지 단독 회차).
        self.assertIsNone(counted['run_files'])
        self.assertIn('run 파일 해당 없음', table)

    def test_a_drop_outside_the_run_window_is_not_counted(self):
        """stage.log 는 두 run 을 한 파일에 담는다. run 을 주면 그 sim 구간만 센다(맥마클2, 실습22 대조)."""
        with tempfile.TemporaryDirectory() as root:
            logs, run_dir = self.write_logs(root), self.write_run(root)
            scoped = judge_run.collect(str(logs), 'p22', str(run_dir), {})
            whole = judge_run.collect(str(logs), 'p22', '', {})
        # fixture 의 낙하는 sim 697-698 s 이고 run 구간은 69-101.5 s 다.
        self.assertEqual((69.000003598, 101.5), scoped['sim_window'])
        self.assertEqual(0, len(scoped['drops']))
        self.assertEqual(0, scoped['refills']['released'])
        self.assertIsNone(whole['sim_window'])
        self.assertEqual(1, len(whole['drops']))
        self.assertEqual(1, whole['refills']['released'])


class LapGateTests(unittest.TestCase):
    """F01 J1/J2. 미완료·순서 불일치가 종료 코드 0 이 되면 안 된다.

    예시 YAML 의 min:3 은 재현용 숫자다. 최종 acceptance 시행 수를 승인한 것이 아니다.
    """

    def write_probe(self, root, events, criteria):
        logs = Path(root) / 'logs'
        logs.mkdir()
        run_dir = Path(root) / 'run'
        run_dir.mkdir()
        with open(run_dir / 'events.jsonl', 'w', encoding='utf-8') as handle:
            for row in events:
                handle.write(json.dumps(row) + '\n')
        path = os.path.join(root, 'c.json')
        with open(path, 'w', encoding='utf-8') as handle:
            json.dump(criteria, handle)
        return logs, run_dir, path

    def run_main(self, logs, stamp, run_dir, criteria_path):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = judge_run.main(['--logs', str(logs), '--stamp', stamp,
                                   '--run', str(run_dir), '--criteria', criteria_path])
        return code, buf.getvalue()

    def test_three_unfinished_requests_do_not_satisfy_laps_min(self):
        # J1: REQUEST_ACCEPTED 세 건, DOCKED 없음, 나머지 로그 없음. 예시와 같은 활성 gate.
        criteria = {
            'event_order': [],
            'gates': {
                'laps': {'min': 3},
                'drops': {'max': 0},
                'errors': {'max': 0},
                'tracebacks': {'max': 0},
                'http_rejects': {'max': 0},
                'new_warn_kinds': {'max': 0},
                'refill_failed': {'max': 0},
            },
        }
        events = [{**EVENT_ACCEPTED, 'request_id': f'r{i}', 'stamp': float(i)} for i in range(3)]
        with tempfile.TemporaryDirectory() as root:
            logs, run_dir, path = self.write_probe(root, events, criteria)
            counted = judge_run.collect(str(logs), 'missing', str(run_dir), criteria)
            judged, _ = judge_run.verdicts(counted, criteria)
            code, table = self.run_main(logs, 'missing', run_dir, path)

        by_name = {row['name']: row for row in judged}
        self.assertEqual(0, by_name['laps']['value'])
        self.assertEqual(3, by_name['open_trips']['value'])
        self.assertFalse(by_name['laps']['ok'])
        self.assertEqual(1, code)
        self.assertIn('미완료 3', table)

    def test_event_order_mismatch_fails_even_when_laps_pass(self):
        # J2: ACCEPTED→DOCKED 한 바퀴는 끝났지만 기준 차례와 다르다. 출력만 하고 넘어가지 않는다.
        criteria = {
            'event_order': ['REQUEST_ACCEPTED', 'LOAD_DONE', 'DOCKED'],
            'gates': {'laps': {'min': 1}},
        }
        with tempfile.TemporaryDirectory() as root:
            logs, run_dir, path = self.write_probe(
                root, [EVENT_ACCEPTED, EVENT_DOCKED], criteria)
            counted = judge_run.collect(str(logs), 'j2', str(run_dir), criteria)
            judged, _ = judge_run.verdicts(counted, criteria)
            code, table = self.run_main(logs, 'j2', run_dir, path)

        by_name = {row['name']: row for row in judged}
        self.assertTrue(by_name['laps']['ok'])
        self.assertEqual(1, by_name['laps']['value'])
        self.assertFalse(by_name['event_order']['ok'])
        self.assertEqual(1, by_name['event_order']['value'])
        self.assertEqual(1, code)
        self.assertIn('LOAD_DONE', table)

    def test_empty_event_order_does_not_judge_sequence(self):
        criteria = {'event_order': [], 'gates': {'laps': {'min': 1}}}
        with tempfile.TemporaryDirectory() as root:
            logs, run_dir, _path = self.write_probe(
                root, [EVENT_ACCEPTED, EVENT_DOCKED], criteria)
            counted = judge_run.collect(str(logs), 'j2', str(run_dir), criteria)
            judged, _ = judge_run.verdicts(counted, criteria)
        names = [row['name'] for row in judged]
        self.assertNotIn('event_order', names)

    def test_matching_event_order_passes(self):
        criteria = {
            'event_order': ['REQUEST_ACCEPTED', 'AMR_DOCKED_LOAD', 'DOCKED'],
            'gates': {'laps': {'min': 1}},
        }
        with tempfile.TemporaryDirectory() as root:
            logs, run_dir, path = self.write_probe(
                root, [EVENT_ACCEPTED, EVENT_DOCKED_LOAD, EVENT_DOCKED], criteria)
            judged, _ = judge_run.verdicts(
                judge_run.collect(str(logs), 'ok', str(run_dir), criteria), criteria)
            code, _table = self.run_main(logs, 'ok', run_dir, path)
        by_name = {row['name']: row for row in judged}
        self.assertTrue(by_name['event_order']['ok'])
        self.assertEqual(0, by_name['event_order']['value'])
        self.assertEqual(0, code)


class CriteriaFileTests(unittest.TestCase):
    def test_json_criteria_load_without_pyyaml(self):
        with tempfile.TemporaryDirectory() as root:
            path = os.path.join(root, 'c.json')
            with open(path, 'w', encoding='utf-8') as handle:
                json.dump({'gates': {'drops': {'max': 0}}}, handle)
            self.assertEqual({'drops': {'max': 0}}, judge_run.load_criteria(path)['gates'])

    def test_no_criteria_means_no_gates(self):
        self.assertEqual({}, judge_run.load_criteria(''))


if __name__ == '__main__':
    unittest.main()
