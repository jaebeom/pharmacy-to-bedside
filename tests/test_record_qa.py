"""tools/record_qa.py: 패킷 읽기와 판정. ffmpeg 가 있으면 진짜 짧은 영상으로도 본다."""

import argparse
import contextlib
import importlib.util
import io
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

SPEC = importlib.util.spec_from_file_location('record_qa', Path(__file__).resolve().parents[1] / 'tools/record_qa.py')
Q = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(Q)


def args(**kw):
    base = {'wall_s': None, 'target_fps': 30.0, 'min_fps': 29.0, 'dur_tol': 0.02, 'max_drop': 0.02,
            'min_disk_gb': 20.0}
    base.update(kw)
    return argparse.Namespace(**base)


class Judge(unittest.TestCase):
    def test_parse_packets(self):
        self.assertEqual((4, 0.0, 0.1), Q.parse_packets('0.000000\n0.033333\nN/A\n0.100000\n'))
        self.assertEqual((0, None, None), Q.parse_packets(''))

    def test_good_clip(self):
        reasons, values = Q.judge(3001, 0.0, 100.0, 0, 120.0, args(wall_s=100.5))
        self.assertEqual([], reasons)
        self.assertIn('fps=30.01 frames=3001 dur=100.0s', values)

    def test_each_shortfall_is_named(self):
        reasons, _ = Q.judge(2000, 0.0, 100.0, 3, 5.0, args(wall_s=200.0))
        text = ' '.join(reasons)
        for word in ('fps 20.00', '벽시계', '손상 3줄', '드롭 1000', '디스크 여유'):
            self.assertIn(word, text)

    def test_a_recorder_that_closed_early_is_a_loss(self):
        """마클2 5a51804: 녹화기가 8 s 만에 닫혔다 — 회차 600 s 와 길이가 안 맞는다."""
        reasons, _ = Q.judge(240, 0.0, 8.0, 0, 100.0, args(wall_s=600.0))
        self.assertTrue(any('벽시계' in r for r in reasons))


class Wall(unittest.TestCase):
    def test_midnight_crossing_with_clock_only(self):
        """마클2 9/25 다중 PC 10건: 23:59 께 시작해 01:02 께 닫았다. 3789 s 여야 한다(음수가 아니라)."""
        self.assertEqual(3789.0, Q.wall_between('23:59:30', '01:02:39'))

    def test_dated_and_epoch_forms(self):
        self.assertEqual(3789.0, Q.wall_between('2026-09-24T23:59:30', '2026-09-25T01:02:39'))
        self.assertEqual(3789.0, Q.wall_between('1727222370', '1727226159'))

    def test_negative_wall_is_an_argument_error_not_a_loss(self):
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stderr(io.StringIO()), \
                self.assertRaises(SystemExit) as caught:
            Q.main(['--record', f'{tmp}/none.mkv', '--wall-s', '-82611'])
        self.assertEqual(2, caught.exception.code)


class Main(unittest.TestCase):
    def run_main(self, argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = Q.main(argv)
        return code, out.getvalue()

    def test_missing_file_is_a_loss_and_written_to_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, out = self.run_main(['--record', f'{tmp}/none.mkv'])
            self.assertEqual(5, code)
            self.assertIn('녹화 결손(파일 없음)', out)
            self.assertIn('record_qa: 파일 없음', (Path(tmp) / 'SUMMARY.txt').read_text(encoding='utf-8'))

    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'ffmpeg·ffprobe 가 없다')
    def test_a_real_three_second_clip(self):
        with tempfile.TemporaryDirectory() as tmp:
            clip = Path(tmp) / 'clip.mkv'
            subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'testsrc=size=160x120:rate=30',
                            '-t', '3', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(clip)], check=True, timeout=60)
            code, out = self.run_main(['--record', str(clip), '--wall-s', '3', '--min-disk-gb', '0'])
            self.assertEqual(0, code, out)
            self.assertIn('frames=90', out)


if __name__ == '__main__':
    unittest.main()
