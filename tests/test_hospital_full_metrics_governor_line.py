"""감속기 현황 줄이 지표 도구의 SPEED_LIMIT 정규식에 잡히는가.

마1검증 9/27 e88b8bd 리뷰: 괄호 안에 문구를 끼워 넣어 판정선 (b) G1·G2 지표가 0이 될 뻔했다.
"""

import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'src' / 'rokey_p3_navigation'))

import hospital_full_metrics as metrics  # noqa: E402
from rokey_p3_navigation import speed_governor as governor  # noqa: E402


class GovernorLineShape(unittest.TestCase):
    def test_status_line_with_stop_rule_text_still_matches_the_metrics_regex(self):
        for percent, free in ((100.0, '≥1.80 m'), (50.0, '0.65 m'),
                              (1.0, '0.80 m'), (50.0, '모름(코스트맵 끊김)')):
            for stop in (None, '정지 규칙 감시, 앞 비었음', '정지 규칙 정지 중, 앞 0.42 m'):
                with self.subTest(percent=percent, free=free, stop=stop):
                    line = governor.status_line(percent, 1.0, free, 12, stop)
                    match = metrics.SPEED_LIMIT.search(line)
                    self.assertIsNotNone(match, line)
                    self.assertEqual((f'{percent:.0f}', free, '12'), match.groups())


if __name__ == '__main__':
    unittest.main()
