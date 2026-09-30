"""tools/boot_check.py: 읽기(파서)와 판정. X·ROS·Isaac 없이 본다."""

import contextlib
import importlib.util
import io
import tempfile
import threading
import time
import unittest
from pathlib import Path

SPEC = importlib.util.spec_from_file_location('boot_check', Path(__file__).resolve().parents[1] / 'tools/boot_check.py')
B = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(B)


class Parsers(unittest.TestCase):
    def test_locked_hint(self):
        self.assertTrue(B.parse_locked_hint('LockedHint=yes\n'))
        self.assertFalse(B.parse_locked_hint('LockedHint=no\n'))
        self.assertIsNone(B.parse_locked_hint('Failed to get session'))

    def test_screensaver(self):
        self.assertTrue(B.parse_screensaver('(true,)\n'))
        self.assertFalse(B.parse_screensaver('(false,)\n'))
        self.assertIsNone(B.parse_screensaver('Error: GDBus.Error'))

    def test_seat_session_from_the_table(self):
        table = ('      3 1000 romanty seat0 5711   user    tty2 yes  2h 45min ago\n'
                 '      4 1000 romanty -     5979   manager -    no   -\n')
        self.assertEqual('3', B.parse_seat_session(table, 1000))
        self.assertIsNone(B.parse_seat_session(table, 1001))

    def test_viewport_takes_the_last_line(self):
        log = ('[pharmacy_stage] viewport camera resolution=(1024, 1152) fill_frame=False\n'
               '[pharmacy_stage] viewport camera resolution=(640, 720) fill_frame=False focal=7.0\n')
        self.assertEqual((640, 720), B.parse_viewport(log))
        self.assertIsNone(B.parse_viewport('stage ready ur5=on'))

    def test_clock_publishers(self):
        self.assertEqual(1, B.parse_publisher_count('Type: rosgraph_msgs/msg/Clock\nPublisher count: 1\n'))
        self.assertEqual(0, B.parse_publisher_count('Unknown topic \'/clock\''))
        self.assertEqual(0, B.parse_publisher_count(''))
        self.assertIsNone(B.parse_publisher_count('something else'))

    def test_clock_csv(self):
        self.assertAlmostEqual(12.5, B.parse_clock_csv('12,500000000\n'))
        self.assertIsNone(B.parse_clock_csv('WARNING: topic [/clock] does not appear to be published yet'))

    def test_costmap_info_reads_the_three_fields(self):
        text = ('map_load_time:\n  sec: 0\n  nanosec: 0\nresolution: 0.05000000074505806\n'
               'width: 859\nheight: 534\norigin:\n  position:\n    x: -12.25\n    y: -6.5\n')
        self.assertEqual({'width': 859, 'height': 534, 'resolution': 0.05000000074505806},
                         B.parse_costmap_info(text))

    def test_costmap_info_needs_all_three_fields(self):
        self.assertIsNone(B.parse_costmap_info('width: 859\nheight: 534\n'))  # resolution 없음
        self.assertIsNone(B.parse_costmap_info(''))
        self.assertIsNone(B.parse_costmap_info(None))

    def test_costmap_size_ok(self):
        self.assertFalse(B.costmap_size_ok({'width': 100, 'height': 100, 'resolution': 0.05}, 10.0))  # 5x5 m
        self.assertTrue(B.costmap_size_ok({'width': 859, 'height': 534, 'resolution': 0.05}, 10.0))
        self.assertFalse(B.costmap_size_ok(None, 10.0))
        # 가로만 넓고 세로가 좁으면(예: 회랑 하나만 받은 잘못된 지도) 걸린다 — 둘 다 넘어야 한다
        self.assertFalse(B.costmap_size_ok({'width': 1000, 'height': 100, 'resolution': 0.05}, 10.0))


class Checks(unittest.TestCase):
    def args(self, **kw):
        base = {'stage_log': None, 'record': None, 'skip': [], 'clock_wait_s': 0.0, 'record_wait_s': 0.3,
                'window_wait_s': 0.0, 'lock_unknown_ok': False, 'isaac': None, 'web': None,
                'max_recorders': 1, 'tmux_prefix': 'p3v2-', 'load_baseline': None, 'min_disk_gb': 20.0,
                'costmap_topic': None, 'costmap_min_m': 10.0, 'costmap_wait_s': 0.0, 'costmap_retry_s': 0.0,
                'nav_log': None}
        base.update(kw)
        return type('Args', (), base)()

    def test_viewport_needs_the_line_and_a_positive_size(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / 'stage.log'
            log.write_text('stage ready\n', encoding='utf-8')
            self.assertFalse(B.check_viewport(self.args(stage_log=str(log)))[0])
            log.write_text('viewport camera resolution=(0, 0)\n', encoding='utf-8')
            self.assertFalse(B.check_viewport(self.args(stage_log=str(log)))[0])
            log.write_text('viewport camera resolution=(640, 720)\n', encoding='utf-8')
            self.assertTrue(B.check_viewport(self.args(stage_log=str(log)))[0])
        self.assertFalse(B.check_viewport(self.args())[0])

    def test_disk_needs_the_free_space(self):
        with tempfile.TemporaryDirectory() as tmp:
            clip = Path(tmp) / 'clip.mkv'
            self.assertTrue(B.check_disk(self.args(record=str(clip), min_disk_gb=0.0))[0])
            passed, detail = B.check_disk(self.args(record=str(clip), min_disk_gb=1e9))
            self.assertFalse(passed)
            self.assertIn('여유', detail)

    def test_record_must_grow(self):
        with tempfile.TemporaryDirectory() as tmp:
            clip = Path(tmp) / 'clip.mkv'
            clip.write_bytes(b'x' * 10)
            self.assertFalse(B.check_record(self.args(record=str(clip)))[0])  # 멈춘 녹화(0 B 회차의 모양)

            def grow():
                time.sleep(0.1)
                with clip.open('ab') as handle:
                    handle.write(b'y' * 10)

            writer = threading.Thread(target=grow)
            writer.start()
            passed, detail = B.check_record(self.args(record=str(clip)))
            writer.join()
            self.assertTrue(passed, detail)
        self.assertFalse(B.check_record(self.args(record='/no/such/clip.mkv'))[0])

    def test_window_tool_missing_says_so(self):
        saved = B.WINDOW_TOOL
        B.WINDOW_TOOL = Path('/no/such/demo_window_layout.py')
        try:
            passed, detail = B.check_window(self.args())
        finally:
            B.WINDOW_TOOL = saved
        self.assertFalse(passed)
        self.assertIn('tools/ 째', detail)

    def test_unknown_lock_fails_unless_allowed(self):
        saved = B.locked_state
        try:
            B.locked_state = lambda: (None, 'test')
            self.assertFalse(B.check_lock(self.args())[0])
            self.assertTrue(B.check_lock(self.args(lock_unknown_ok=True))[0])
            B.locked_state = lambda: (True, 'test')
            self.assertFalse(B.check_lock(self.args(lock_unknown_ok=True))[0])
            B.locked_state = lambda: (False, 'test')
            self.assertTrue(B.check_lock(self.args())[0])
        finally:
            B.locked_state = saved


class Lock(unittest.TestCase):
    def test_seat0_wins_over_the_shell_session(self):
        """셸의 XDG_SESSION_ID(pts 세션)가 아니라 화면의 seat0 세션을 본다(마클1 9/24)."""
        calls = []

        def fake_run(cmd, timeout):
            calls.append(cmd)
            if cmd[:2] == ['loginctl', 'list-sessions']:
                uid = B.os.getuid()  # CI 러너의 uid 는 1000 이 아니다
                return True, 0, f'      2 {uid} rokey seat0 1 user tty2 no -\n     11 {uid} rokey - 2 user pts/3 no -\n'
            if cmd[:2] == ['loginctl', 'show-session']:
                return True, 0, 'LockedHint=yes\n' if cmd[2] == '2' else 'LockedHint=no\n'
            return False, None, 'no'

        saved_run, saved_env = B.run, B.os.environ.get('XDG_SESSION_ID')
        B.run = fake_run
        B.os.environ['XDG_SESSION_ID'] = '11'
        try:
            state, source = B.locked_state()
        finally:
            B.run = saved_run
            if saved_env is None:
                B.os.environ.pop('XDG_SESSION_ID', None)
            else:
                B.os.environ['XDG_SESSION_ID'] = saved_env
        self.assertTrue(state)
        self.assertIn('session 2', source)


class Retries(unittest.TestCase):
    """마클1 9/24 회차33 오탐 둘: 창이 아직 없음, discovery 전 /clock 발행자 0."""

    def setUp(self):
        self.saved = (B.run, B.time.sleep, B.clock_now)
        B.time.sleep = lambda s: None

    def tearDown(self):
        B.run, B.time.sleep, B.clock_now = self.saved

    def args(self, **kw):
        return Checks.args(self, **kw)

    def test_clock_zero_then_one_passes(self):
        counts = iter(['Publisher count: 0', 'Publisher count: 1', 'Publisher count: 1'])
        B.run = lambda cmd, timeout: (True, 0, next(counts))
        times = iter([36.2, 38.4])
        B.clock_now = lambda: next(times)
        passed, detail = B.check_clock(self.args())
        self.assertTrue(passed, detail)
        self.assertIn('[0, 1, 1]', detail)

    def test_clock_zero_but_moving_passes(self):
        B.run = lambda cmd, timeout: (True, 0, 'Publisher count: 0')
        times = iter([1.0, 2.0])
        B.clock_now = lambda: next(times)
        self.assertTrue(B.check_clock(self.args())[0])

    def test_two_publishers_fail_even_if_moving(self):
        B.run = lambda cmd, timeout: (True, 0, 'Publisher count: 2')
        times = iter([1.0, 2.0])
        B.clock_now = lambda: next(times)
        passed, detail = B.check_clock(self.args())
        self.assertFalse(passed)
        self.assertIn('둘 이상', detail)

    def test_clock_not_moving_fails(self):
        B.run = lambda cmd, timeout: (True, 0, 'Publisher count: 1')
        B.clock_now = lambda: 5.0
        self.assertFalse(B.check_clock(self.args())[0])

    def test_window_retries_until_the_browser_appears(self):
        codes = iter([3, 3, 0])
        B.run = lambda cmd, timeout: (True, next(codes), '[demo_window_layout] ok')
        passed, detail = B.check_window(self.args(window_wait_s=60.0))
        self.assertTrue(passed, detail)
        self.assertIn('시도 3', detail)

    def test_window_patterns_are_passed_through(self):
        seen = []

        def fake(cmd, timeout):
            seen.append(cmd)
            return True, 0, 'ok'

        B.run = fake
        B.check_window(self.args(web='chrome', isaac='isaac sim python'))
        self.assertIn('--web', seen[0])
        self.assertEqual('chrome', seen[0][seen[0].index('--web') + 1])
        self.assertEqual('isaac sim python', seen[0][seen[0].index('--isaac') + 1])

    def test_window_gives_up_with_a_hint(self):
        B.run = lambda cmd, timeout: (True, 3, '[demo_window_layout] 창을 못 찾음')
        passed, detail = B.check_window(self.args(window_wait_s=0.0))
        self.assertFalse(passed)
        self.assertIn('demo_window_layout.py 를 한 번 돌리고', detail)

    def test_costmap_off_by_default_calls_nothing(self):
        def fail(cmd, timeout):
            raise AssertionError('costmap 이 꺼져 있으면 run() 을 부르면 안 된다')

        B.run = fail
        passed, detail = B.check_costmap(self.args())
        self.assertTrue(passed)
        self.assertIn('꺼짐', detail)

    def test_costmap_default_grid_fails(self):
        """Nav2 기본 빈 격자(100x100 @ 0.05 m/px = 5x5 m)로 남으면 지도를 못 받은 것이다."""
        echo = 'resolution: 0.05\nwidth: 100\nheight: 100\n'
        B.run = lambda cmd, timeout: (True, 0, echo)
        passed, detail = B.check_costmap(self.args(costmap_topic='/amr_1/global_costmap/costmap'))
        self.assertFalse(passed)
        self.assertIn('기본 격자로 남음', detail)

    def test_costmap_retries_until_the_real_map_arrives(self):
        """회차133(#240 5848721883): 처음엔 기본 격자, 지도가 오면 병원 크기(859x534 @ 0.05 m/px)."""
        replies = iter(['resolution: 0.05\nwidth: 100\nheight: 100\n',
                        'resolution: 0.05\nwidth: 859\nheight: 534\n'])
        B.run = lambda cmd, timeout: (True, 0, next(replies))
        passed, detail = B.check_costmap(self.args(costmap_topic='/amr_1/global_costmap/costmap',
                                                    costmap_wait_s=60.0))
        self.assertTrue(passed, detail)
        self.assertIn('시도 2', detail)
        self.assertIn('43.0x26.7 m', detail)

    def test_costmap_unreadable_output_is_treated_as_not_received(self):
        B.run = lambda cmd, timeout: (False, None, 'ros2 없음')
        passed, detail = B.check_costmap(self.args(costmap_topic='/amr_1/global_costmap/costmap'))
        self.assertFalse(passed)
        self.assertIn('못 읽음', detail)

    def test_costmap_nav_log_phrase_fails_even_if_the_map_size_is_fine(self):
        """보조 판정(시뮬통합 9/27): 크기는 맞아도 nav.log 에 지도를 못 받은 흔적이 있으면 걸린다."""
        echo = 'resolution: 0.05\nwidth: 859\nheight: 534\n'
        B.run = lambda cmd, timeout: (True, 0, echo)
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / 'nav.log'
            log.write_text("global_costmap: Can't update static costmap layer, no map received\n",
                           encoding='utf-8')
            passed, detail = B.check_costmap(self.args(costmap_topic='/amr_1/global_costmap/costmap',
                                                        nav_log=str(log)))
        self.assertFalse(passed)
        self.assertIn('지도를 못 받은 흔적', detail)

    def test_costmap_nav_log_without_the_phrase_passes(self):
        echo = 'resolution: 0.05\nwidth: 859\nheight: 534\n'
        B.run = lambda cmd, timeout: (True, 0, echo)
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / 'nav.log'
            log.write_text('nav2 up\n', encoding='utf-8')
            passed, detail = B.check_costmap(self.args(costmap_topic='/amr_1/global_costmap/costmap',
                                                        nav_log=str(log)))
        self.assertTrue(passed, detail)


class Stale(unittest.TestCase):
    """master02 9/24: 관제 창 60개와 15시간 된 녹화기가 남아 load 19.7 이었다.
    마클1 회차50: 자기 회차의 래퍼 bash·pgrep·캡처·demo_v2 세션을 잔류로 잘못 세었다 — 그것도 여기서 막는다."""

    WINDOWS = ("0x02800004 class='127.0.0.1 Google-chrome' title='P3 관제 · 개발자'\n"
               "0x02a00009 class='IsaacSim Isaac Sim Python 5.1.0' title='Isaac Sim Python 5.1.0'\n")
    # pid ppid etimes comm args
    CURRENT = '4242 4200 120 ffmpeg ffmpeg -f x11grab -framerate 30 -i :0 clip.mp4\n'
    OLD = '1111 1 54000 gst-launch-1.0 gst-launch-1.0 -e ximagesrc ! x264enc ! filesink location=old.mkv\n'
    NOT_RECORDERS = ('4200 300 120 bash bash -c ffmpeg -f x11grab -framerate 30 -i :0 clip.mp4\n'
                     '5000 4900 1 pgrep pgrep -fc ximagesrc|x11grab\n'
                     '5100 310 1 gst-launch-1.0 gst-launch-1.0 -q ximagesrc num-buffers=1 ! pngenc ! filesink\n')
    # demo_v2 역할 pane: 셸(300)이 bash -c trap … 아래 python3(301)을 자식으로 둔다. 끝난 pane 셸(400)은 자식이 없다.
    ROLES = '301 300 100 python3 python3 pharmacy_stage.py\n'
    PANES_LIVE = 'p3v2-stage 300\nother 310\n'
    PANES_ENDED = 'p3v2-stage 300\np3v2-arm 400\n'

    def setUp(self):
        self.saved = B.run

    def tearDown(self):
        B.run = self.saved

    def fake(self, windows, ps, panes):
        def run(cmd, timeout):
            if '--list' in cmd:
                return True, 0, windows
            if cmd[0] == 'ps':
                return True, 0, ps
            if cmd[0] == 'tmux':
                return True, 0, panes
            return False, None, 'no'
        B.run = run

    def test_only_real_recorders_count(self):
        rows = B.parse_processes(self.CURRENT + self.NOT_RECORDERS)
        self.assertEqual([4242], [pid for pid, _, _ in B.recorders_of(rows)])
        rows = B.parse_processes(self.CURRENT + self.OLD)
        self.assertEqual([4242, 1111], [pid for pid, _, _ in B.recorders_of(rows)])

    def test_a_running_role_pane_is_not_idle(self):
        rows = B.parse_processes(self.ROLES + self.NOT_RECORDERS)
        self.assertEqual([], B.idle_sessions(self.PANES_LIVE, rows, 'p3v2-'))
        self.assertEqual(['p3v2-arm'], B.idle_sessions(self.PANES_ENDED, rows, 'p3v2-'))

    def test_clean_passes(self):
        self.fake(self.WINDOWS, self.CURRENT + self.NOT_RECORDERS + self.ROLES, self.PANES_LIVE)
        passed, detail = B.check_stale(Checks.args(self))
        self.assertTrue(passed, detail)

    def test_load_over_twice_the_baseline_fails(self):
        saved = B.read_load
        try:
            self.fake(self.WINDOWS, '', '')
            B.read_load = lambda: 19.7
            passed, detail = B.check_stale(Checks.args(self, load_baseline=3.0))
            self.assertFalse(passed)
            self.assertIn('load 19.70 > 기준선 3 의 2 배', detail)
            self.assertTrue(B.check_stale(Checks.args(self))[0])  # 기준선이 없으면 적기만 한다
            B.read_load = lambda: 5.9
            self.assertTrue(B.check_stale(Checks.args(self, load_baseline=3.0))[0])
        finally:
            B.read_load = saved

    def test_read_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'loadavg'
            path.write_text('19.65 19.80 18.86 3/1234 5678\n', encoding='ascii')
            self.assertEqual(19.65, B.read_load(str(path)))
        self.assertIsNone(B.read_load('/no/such/loadavg'))

    def test_leftovers_fail_with_a_list_and_nothing_is_killed(self):
        many = self.WINDOWS + "0x03000001 class='127.0.0.1 Google-chrome' title='P3 관제 · 개발자'\n"
        calls = []
        self.fake(many, self.CURRENT + self.OLD + self.ROLES, self.PANES_ENDED)
        inner = B.run

        def spy(cmd, timeout):
            calls.append(cmd[0])
            return inner(cmd, timeout)
        B.run = spy
        passed, detail = B.check_stale(Checks.args(self))
        self.assertFalse(passed)
        self.assertIn('관제 창 2개', detail)
        self.assertIn('녹화기 2개', detail)
        self.assertIn('pid 1111 900분', detail)
        self.assertIn("p3v2-arm", detail)
        self.assertNotIn('kill', calls)


class Tree(unittest.TestCase):
    """트리 게이트(작전 9/24): 카드의 SHA·깨끗한 트리·트리 안 도구·요구한 도구/프로필. 임시 git 저장소로 본다."""

    def setUp(self):
        import argparse
        import subprocess
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / 'repo'
        (self.root / 'tools').mkdir(parents=True)
        (self.root / 'tools' / 'boot_check.py').write_text('# copy\n', encoding='utf-8')
        (self.root / 'tools' / 'hospital_orders.py').write_text(
            'PROFILES = ("default", "beds-all", "station-b")\n', encoding='utf-8')
        git = ['git', '-C', str(self.root), '-c', 'user.name=t', '-c', 'user.email=t@t']
        subprocess.run([*git, 'init', '-q'], check=True)
        subprocess.run([*git, 'add', '.'], check=True)
        subprocess.run([*git, 'commit', '-qm', 'init'], check=True)
        self.sha = subprocess.run([*git, 'rev-parse', 'HEAD'], capture_output=True, text=True,
                                  check=True).stdout.strip()
        self.ns = argparse.Namespace
        self.saved_run = B.run

        def run(cmd, timeout):
            if cmd[0] == 'ps':
                return True, 0, ''
            return self.saved_run(cmd, timeout)
        B.run = run

    def tearDown(self):
        B.run = self.saved_run
        self.tmp.cleanup()

    def args(self, **kw):
        base = {'tree_sha': self.sha, 'tree_root': str(self.root), 'need': [],
                'self_path': str(self.root / 'tools' / 'boot_check.py')}
        base.update(kw)
        return self.ns(**base)

    def check(self, **kw):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            passed, detail = B.check_tree(self.args(**kw))
        return passed, detail, out.getvalue()

    def test_matching_clean_tree_passes_and_prints_the_line(self):
        passed, detail, out = self.check(need=['tools/hospital_orders.py', 'profile:beds-all'])
        self.assertTrue(passed, detail)
        self.assertIn(f'[boot_check] tree={self.sha[:12]} clean=y tools=in-tree need=ok', out)

    def test_other_sha_fails(self):
        passed, detail, _ = self.check(tree_sha='0' * 40)
        self.assertFalse(passed)
        self.assertIn('≠ --tree-sha', detail)

    def test_dirty_tree_fails(self):
        (self.root / 'tools' / 'hospital_orders.py').write_text('# 고침\n', encoding='utf-8')
        passed, detail, out = self.check()
        self.assertFalse(passed)
        self.assertIn('clean=n', out)
        self.assertIn('깨끗하지 않다', detail)

    def test_a_copied_boot_check_is_a_copy(self):
        passed, detail, out = self.check(self_path=str(Path(self.tmp.name) / 'boot_check.py'))
        self.assertFalse(passed)
        self.assertIn('tools=copy', out)

    def test_missing_file_or_profile_fails(self):
        passed, detail, out = self.check(need=['tools/record_qa.py', 'profile:all-rooms'])
        self.assertFalse(passed)
        self.assertIn('need=missing:tools/record_qa.py,profile:all-rooms', out)

    def test_no_tree_sha_only_reports(self):
        passed, detail, out = self.check(tree_sha=None)
        self.assertTrue(passed)
        self.assertIn('게이트 꺼짐', detail)
        self.assertIn('[boot_check] tree=', out)

    def test_tree_cannot_be_skipped_and_sha_must_be_40_hex(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            B.main(['--skip', 'tree'])
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            B.main(['--tree-sha', 'abc123'])


class Main(unittest.TestCase):
    def run_main(self, results, argv=()):
        saved = dict(B.RUNNERS)
        try:
            for name in B.CHECKS:
                B.RUNNERS[name] = (lambda r: (lambda args: r))(results.get(name, (True, 'ok')))
            out = io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
                code = B.main(list(argv))
            return code, out.getvalue()
        finally:
            B.RUNNERS.update(saved)

    def test_all_pass_is_zero(self):
        code, out = self.run_main({})
        self.assertEqual(0, code)
        self.assertIn('[boot_check] OK', out)

    def test_one_fail_is_five_and_the_rest_still_run(self):
        code, out = self.run_main({'lock': (False, '잠김')})
        self.assertEqual(5, code)
        self.assertIn('lock FAIL', out)
        self.assertIn('record PASS', out)  # 걸린 뒤에도 나머지를 본다
        self.assertIn('[boot_check] FAIL lock — 회차 중단', out.splitlines()[-2])  # 막대 두 줄 사이
        self.assertTrue(out.splitlines()[-1].startswith('#'))

    def test_summary_gets_one_line_next_to_the_stage_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / 'stage.log'
            code, _ = self.run_main({'record': (False, 'x')}, ['--stage-log', str(log)])
            self.assertEqual(5, code)
            self.run_main({}, ['--stage-log', str(log)])
            lines = (Path(tmp) / 'SUMMARY.txt').read_text(encoding='utf-8').splitlines()
        self.assertEqual(2, len(lines))
        self.assertTrue(lines[0].endswith('[boot_check] FAIL record — 회차 중단'))
        self.assertTrue(lines[1].endswith('[boot_check] OK'))

    def test_summary_that_cannot_be_written_does_not_change_the_code(self):
        code, out = self.run_main({}, ['--summary', '/no/such/dir/SUMMARY.txt'])
        self.assertEqual(0, code)
        self.assertIn('SUMMARY 를 못 씀', out)

    def test_skip(self):
        code, out = self.run_main({'record': (False, 'x')}, ['--skip', 'record'])
        self.assertEqual(0, code)
        self.assertIn('record SKIP', out)

    def test_a_crashing_check_counts_as_fail(self):
        def boom(args):
            raise RuntimeError('boom')

        saved = B.RUNNERS['viewport']
        B.RUNNERS['viewport'] = boom
        try:
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = B.main(['--skip', 'window', '--skip', 'lock', '--skip', 'clock', '--skip', 'record'])
        finally:
            B.RUNNERS['viewport'] = saved
        self.assertEqual(5, code)
        self.assertIn('viewport FAIL RuntimeError: boom', out.getvalue())

if __name__ == '__main__':
    unittest.main()
