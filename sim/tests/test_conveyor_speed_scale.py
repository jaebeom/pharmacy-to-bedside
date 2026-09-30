"""병원 씬 컨베이어 속도 배율(재범 9/29 "속도 올리기"). Isaac 없이 본다. 실제 운반 시간·튐·낙하는 L3 미실행.

잰 표면 속도(롤러 0.5 m/s)로 봉투가 출발→A1 에 34.58 sim s 걸렸다. 표면 속도에 같은 배율을 곱한다 — 방향은 그대로라
분기(Sorter)·끝 롤러 잡기(hold_terminal) 규칙이 같이 간다.
"""

import importlib.util
import sys
import unittest
from pathlib import Path

STANDALONE = Path(__file__).resolve().parents[1] / "standalone"
sys.path.insert(0, str(STANDALONE))
from p3sim import hospital_conveyor as C  # noqa: E402


def load_stage():
    spec = importlib.util.spec_from_file_location("pharmacy_stage_speed", STANDALONE / "pharmacy_stage.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SpeedScale(unittest.TestCase):
    def test_every_surface_is_scaled_in_the_same_direction(self):
        table = C.load_surfaces()
        fast = C.HospitalConveyor(None, surfaces=table, speed_scale=2.0)
        base = C.HospitalConveyor(None, surfaces=table)
        self.assertEqual(set(fast.surfaces), set(base.surfaces))
        for path, (linear, angular) in base.surfaces.items():
            self.assertEqual(tuple(2.0 * v for v in linear), fast.surfaces[path][0], path)
            self.assertEqual(tuple(2.0 * v for v in angular), fast.surfaces[path][1], path)
        self.assertEqual((-1.0, 0.0, 0.0), fast.surfaces[fast.terminal_path][0])   # 끝 롤러 0.5 → 1.0 m/s

    def test_scale_one_keeps_the_measured_values_and_zero_is_refused(self):
        table = C.load_surfaces()
        base = C.HospitalConveyor(None, surfaces=table)
        self.assertEqual(base.speed_scale, 1.0)
        self.assertEqual((-0.5, 0.0, 0.0), base.surfaces[base.terminal_path][0])
        with self.assertRaises(ValueError):
            C.HospitalConveyor(None, surfaces=table, speed_scale=0.0)

    def test_the_hospital_preset_doubles_it_and_the_argument_wins(self):
        stage = load_stage()
        self.assertEqual(2.0, stage.HOSPITAL_CONVEYOR_SPEED_SCALE)
        self.assertEqual(2.0, stage.parse_args(["--preset", "hospital"]).conveyor_speed_scale)
        self.assertEqual(1.0, stage.parse_args(["--preset", "hospital", "--conveyor-speed-scale", "1"])
                         .conveyor_speed_scale)
        self.assertEqual(1.0, stage.parse_args([]).conveyor_speed_scale)       # 병원 밖은 그대로


if __name__ == "__main__":
    unittest.main()
