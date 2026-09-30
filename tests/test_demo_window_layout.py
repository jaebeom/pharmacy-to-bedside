"""tools/demo_window_layout.py 의 순수 계산(반반 나누기)·창 고르기·X 가 없을 때. X 서버 없이 돈다.

실제 배치(창을 옮기는 것)는 L3 이고 이 테스트에 없다.
"""

import importlib.util
import os
import subprocess
import sys
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / 'tools/demo_window_layout.py'
spec = importlib.util.spec_from_file_location('demo_window_layout', SCRIPT)
layout = importlib.util.module_from_spec(spec)
spec.loader.exec_module(layout)

MASTER01 = (0, 32, 1920, 1048)        # 1920x1080, GNOME 위 막대 32(관측 세션 9/20 새벽)
MASTER02 = (0, 32, 2048, 1120)        # 2048x1152, 같은 막대 가정(마클2 9/18)


class HalvesTests(unittest.TestCase):
    def test_left_and_right_fill_the_work_area(self):
        for area in (MASTER01, MASTER02):
            left, right = layout.halves(area)
            self.assertEqual(area[0], left[0])
            self.assertEqual(left[0] + left[2], right[0])              # 사이가 벌어지지 않는다
            self.assertEqual(area[0] + area[2], right[0] + right[2])   # 오른쪽 끝이 화면 끝
            for rect in (left, right):
                self.assertEqual(area[1], rect[1])                     # 위 막대 아래에서 시작
                self.assertEqual(area[3], rect[3])

    def test_master01_and_master02_halves(self):
        self.assertEqual(((0, 32, 960, 1048), (960, 32, 960, 1048)), layout.halves(MASTER01))
        self.assertEqual(((0, 32, 1024, 1120), (1024, 32, 1024, 1120)), layout.halves(MASTER02))

    def test_odd_width_gives_the_extra_pixel_to_the_right(self):
        left, right = layout.halves((0, 0, 1921, 1000))
        self.assertEqual(960, left[2])
        self.assertEqual((960, 961), (right[0], right[2]))


class VerdictTests(unittest.TestCase):
    """9/20 master01 실습13b 관측(#240 댓글 5746506532). 작업 영역 (66, 32, 1854, 1048)."""

    LEFT, RIGHT = layout.halves((66, 32, 1854, 1048))          # (66,32,927,1048) · (993,32,927,1048)

    def test_the_observed_failure_is_caught(self):
        ok, why = layout.verdict(self.RIGHT, (116, 69, 960, 1011))
        self.assertFalse(ok)
        self.assertIn('중심 x=596', why)                        # 요청이 통째로 무시돼 반대쪽에 남았다
        self.assertIn('-877', why)

    def test_the_wnck_placement_passes(self):
        for rect, actual in ((self.LEFT, (66, 32, 894, 1048)), (self.RIGHT, (1026, 32, 894, 1048))):
            ok, why = layout.verdict(rect, actual)
            self.assertTrue(ok, why)

    def test_window_manager_nudges_pass(self):
        # 관측된 밀림: y +9(master02), y +37·크기 +33 안팎(master01 프레임·CSD 여백)
        self.assertTrue(layout.verdict(self.LEFT, (66, 41, 927, 1048))[0])
        self.assertTrue(layout.verdict(self.LEFT, (66, 69, 960, 990))[0])

    def test_tolerance_edges(self):
        x, y, w, h = self.LEFT
        self.assertTrue(layout.verdict(self.LEFT, (x + 80, y, w, h))[0])
        self.assertFalse(layout.verdict(self.LEFT, (x, y + 81, w, h))[0])
        self.assertTrue(layout.verdict(self.LEFT, (x, y, w - 120, h))[0])
        self.assertFalse(layout.verdict(self.LEFT, (x, y, w, h - 121))[0])

    def test_center_check_names_the_half_when_the_window_sits_on_the_other_side(self):
        """반쪽 크기가 같으면 위치가 허용 안인데 중심만 넘어갈 수는 없다. 중심 판정은 크게 어긋난 경우의 이름표다."""
        ok, why = layout.verdict(self.LEFT, (1026, 32, 894, 1048))     # 왼쪽 몫인데 오른쪽에 있다
        self.assertFalse(ok)
        self.assertIn('맡은 반쪽(66..993) 밖', why)
        self.assertIn('위치 차이 +960', why)

    def test_unreadable_geometry_fails(self):
        ok, why = layout.verdict(self.LEFT, None)
        self.assertFalse(ok)
        self.assertIn('읽지 못함', why)


class RequestTests(unittest.TestCase):
    """창 관리자에게 보내는 EWMH 요청의 순수 부분(실제 전송은 L3)."""

    def test_move_flags_carry_all_four_coordinates_and_the_pager_source(self):
        flags = layout.move_flags()
        self.assertEqual(10, flags & 0xFF)                         # STATIC: 좌표를 클라이언트 창 기준으로 읽는다
        self.assertEqual(0b1111, (flags >> 8) & 0xF)               # x·y·w·h 를 모두 준다
        self.assertEqual(2, flags >> 12)                           # 보낸 쪽: 도구(pager)
        self.assertEqual(3, layout.move_flags(source=3) >> 12)
        self.assertEqual(0, layout.move_flags(gravity=0) & 0xFF)   # 0 이면 창의 기본 중력

    def test_only_blocking_states_are_cleared(self):
        names = ['_NET_WM_STATE_FOCUSED', '_NET_WM_STATE_MAXIMIZED_VERT', '_NET_WM_STATE_SKIP_TASKBAR',
                 '_NET_WM_STATE_TILED_LEFT', '_NET_WM_STATE_FULLSCREEN']
        self.assertEqual(['_NET_WM_STATE_MAXIMIZED_VERT', '_NET_WM_STATE_TILED_LEFT', '_NET_WM_STATE_FULLSCREEN'],
                         layout.states_to_clear(names))

    def test_a_plain_window_has_nothing_to_clear(self):
        self.assertEqual([], layout.states_to_clear(['_NET_WM_STATE_FOCUSED']))
        self.assertEqual([], layout.states_to_clear([]))


class PickTests(unittest.TestCase):
    """master02 실측 WM_CLASS·제목(마클2 9/18)."""

    ISAAC = (0x2a00009, 'Isaac Sim Python 5.1.0', 'IsaacSim Isaac Sim Python 5.1.0')
    FIREFOX = (0x4c00017, 'ROKEY P3 관제 — Mozilla Firefox', 'Navigator firefox_firefox')
    DIALOG = (0x4c00100, 'Firefox', 'Firefox firefox_firefox')        # 번역 팝업 같은 대화상자
    TERMINAL = (0x1000001, 'rokey@master02: ~', 'gnome-terminal-server Gnome-terminal')

    def test_isaac_and_browser_are_found_among_other_windows(self):
        windows = [self.TERMINAL, self.DIALOG, self.ISAAC, self.FIREFOX]
        self.assertEqual(self.ISAAC[0], layout.pick(windows, layout.ISAAC_DEFAULT))
        self.assertEqual(self.FIREFOX[0], layout.pick(windows, layout.WEB_DEFAULT))

    def test_chrome_app_window_is_the_web(self):
        """master02 는 Chrome --app 이다(마클2 9/24)."""
        chrome = (0x3a00004, 'P3 관제 · 개발자', '127.0.0.1 Google-chrome')
        self.assertEqual(chrome[0], layout.pick([self.TERMINAL, self.ISAAC, chrome], layout.WEB_DEFAULT))

    def test_browser_dialog_alone_is_not_taken(self):
        self.assertIsNone(layout.pick([self.TERMINAL, self.DIALOG], layout.WEB_DEFAULT))

    def test_a_terminal_on_a_host_named_isaacsim_is_not_isaac(self):
        """master01 은 호스트 이름이 IsaacSim14 다. 그 터미널 창을 Isaac 으로 고르면 안 된다(마클1 9/24)."""
        host_terminal = (0x1600007, 'rokey@IsaacSim14: ~', 'gnome-terminal-server Gnome-terminal')
        self.assertIsNone(layout.pick([host_terminal], layout.ISAAC_DEFAULT))
        self.assertEqual(self.ISAAC[0], layout.pick([host_terminal, self.ISAAC], layout.ISAAC_DEFAULT))

    def test_nothing_matches_gives_none(self):
        self.assertIsNone(layout.pick([], layout.ISAAC_DEFAULT))
        self.assertIsNone(layout.pick([self.TERMINAL], layout.ISAAC_DEFAULT))


class WithoutXTests(unittest.TestCase):
    def test_no_display_says_why_and_how_to_do_it_by_hand(self):
        env = {k: v for k, v in os.environ.items() if k not in ('DISPLAY', 'XAUTHORITY')}
        result = subprocess.run([sys.executable, str(SCRIPT)], capture_output=True, text=True, env=env, timeout=30)
        self.assertEqual(3, result.returncode, result.stdout + result.stderr)
        self.assertIn('창을 옮기지 못한다', result.stdout)
        self.assertIn('Super+', result.stdout)                         # 손으로 하는 법


class WaitForWindowsTests(unittest.TestCase):
    """up 직후 웹 창이 늦게 뜨는 경우(마클1 9/25 회차73). X 없이 목록 함수와 시계를 흉내 낸다."""

    PATTERNS = (('isaac', layout.ISAAC_DEFAULT), ('web', layout.WEB_DEFAULT))
    ISAAC = (1, 'Isaac Sim Python 5.1.0', 'IsaacSim Isaac Sim Python 5.1.0')
    WEB = (2, 'ROKEY P3 관제 — Mozilla Firefox', 'Navigator firefox_firefox')

    def run_wait(self, snapshots, wait_s):
        now = [0.0]
        lists = iter(snapshots)
        last = [None]

        def list_windows():
            last[0] = next(lists, last[0])
            return last[0]

        def sleep(seconds):
            now[0] += seconds

        windows, missing = layout.wait_for_windows(list_windows, self.PATTERNS, wait_s, sleep=sleep,
                                                   clock=lambda: now[0])
        return windows, missing, now[0]

    def test_late_web_window_is_found_after_retries(self):
        windows, missing, waited = self.run_wait([[self.ISAAC], [self.ISAAC], [self.ISAAC, self.WEB]], 30.0)
        self.assertEqual([], missing)
        self.assertIn(self.WEB, windows)
        self.assertEqual(2 * layout.FIND_RETRY_S, waited)

    def test_gives_up_at_the_deadline_and_names_the_missing(self):
        _, missing, waited = self.run_wait([[self.ISAAC]], 5.0)
        self.assertEqual(['web'], missing)
        self.assertGreaterEqual(waited, 5.0)
        self.assertLess(waited, 5.0 + layout.FIND_RETRY_S + 1e-9)

    def test_zero_wait_reads_once(self):
        _, missing, waited = self.run_wait([[self.ISAAC], [self.ISAAC, self.WEB]], 0.0)
        self.assertEqual(['web'], missing)
        self.assertEqual(0.0, waited)

    def test_both_present_returns_without_sleeping(self):
        _, missing, waited = self.run_wait([[self.ISAAC, self.WEB]], 30.0)
        self.assertEqual(([], 0.0), (missing, waited))


if __name__ == '__main__':
    unittest.main()
