"""경로 위 정지 캡슐(#721 발동 시험 `--block-path`, `p3sim/path_block.py`)의 순수 부분. Isaac 쪽은 L3 미실행.

오프라인 확인: 자리가 load → 병동 공통 구간 위 빈 바닥이고 정차 자리·꺾임점·문·보행자 선·더미 루프에서 떨어짐,
발동 거리·유지 시간이 정지 규칙(0.6 m)·Nav2 progress_checker(10 s) 와 맞물림, 상태 기계가 한 번만 올라왔다 내려감.
"""

import math
import sys
import unittest
from pathlib import Path

STANDALONE = Path(__file__).resolve().parents[1] / "standalone"
REPO = STANDALONE.parents[1]
sys.path.insert(0, str(STANDALONE))
sys.path.insert(0, str(REPO / "src" / "rokey_p3_navigation"))
from p3sim import hospital_decor, hospital_zones  # noqa: E402
from p3sim import hospital_nav as hn  # noqa: E402
from p3sim import path_block as B  # noqa: E402
from p3sim import pedestrians as P  # noqa: E402
from p3sim import traffic_dummies as T  # noqa: E402
from rokey_p3_navigation import speed_governor as G  # noqa: E402

ZONES = REPO / "src" / "rokey_p3_description" / "config" / "zones.hospital.yaml"
ROUTES = REPO / "src" / "rokey_p3_description" / "config" / "routes.hospital.yaml"
ANCHORS = REPO / "sim" / "scenes" / "hospital_navigationv1.anchors.json"
NAV2_PARAMS = REPO / "src" / "rokey_p3_navigation" / "config" / "nav2_params.yaml"


def point_segment(p, a, b):
    ax, ay = b[0] - a[0], b[1] - a[1]
    t = max(0.0, min(1.0, ((p[0] - a[0]) * ax + (p[1] - a[1]) * ay) / (ax * ax + ay * ay)))
    return math.dist(p, (a[0] + ax * t, a[1] + ay * t))


def samples(a, b, n=40):
    return [(a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n) for k in range(n + 1)]


class Place(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.grid = hn.load_map()
        cls.zones = hospital_zones.zones_from_yaml(ZONES)
        cls.routes = hospital_decor.parse_routes_text(ROUTES.read_text(encoding="utf-8"))

    def route(self, start, end):
        return hospital_decor.full_route(self.routes, self.zones, start, end)

    def test_on_every_delivery_route_out_of_load(self):
        """첫 배송이 어느 병동·간호사실이든 캡슐 위를 지난다."""
        outbound = [r for r in self.routes if r["from"] == "load" and r["to"].startswith(("bed_", "station_"))]
        self.assertGreaterEqual(len(outbound), 10)
        for r in outbound:
            if r["to"] == "station_a":       # 간호사실 A 는 로비 서쪽에서 꺾어 캡슐 앞을 안 지난다
                continue
            points = self.route(r["from"], r["to"])
            nearest = min(point_segment(B.BLOCK_XY, a, b) for a, b in zip(points[:-1], points[1:], strict=True))
            self.assertLess(nearest, 0.05, r["to"])

    def test_heading_east_and_clear_of_route_corners(self):
        """지나는 마디는 동쪽 직선이고, 캡슐은 꺾임점(제자리 회전)에서 3 m 밖이다."""
        points = self.route("load", "bed_a1")
        segment = min(zip(points[:-1], points[1:], strict=True),
                      key=lambda ab: point_segment(B.BLOCK_XY, ab[0], ab[1]))
        self.assertGreater(segment[1][0] - segment[0][0], 5.0)
        self.assertLess(abs(segment[1][1] - segment[0][1]), 0.1)
        self.assertGreater(min(math.dist(B.BLOCK_XY, p) for p in points), 3.0)

    def test_free_floor_with_room_to_pass(self):
        """캡슐 둘레에 회전 원 + 사람 둘레만큼 빈 바닥이 있다(내려간 뒤 AMR 이 그대로 간다)."""
        x, y = B.BLOCK_XY
        room = hn.TURN_RADIUS + P.CLEARANCE_RADIUS
        self.assertEqual(T.loop_problems(self.grid, ((x, y), (x + 0.01, y)), 0.0, room), [])

    def test_away_from_stops(self):
        """적재·도크·간호사실·병상 정차 자리에서 2.5 m 밖 — 정차 접근 감속과 섞이지 않는다."""
        for zone, pose in self.zones.items():
            self.assertGreater(math.dist(B.BLOCK_XY, pose[:2]), 2.5, zone)

    def test_away_from_the_ward_doors(self):
        import json

        doors = json.loads(ANCHORS.read_text(encoding="utf-8"))["doors"]
        for door, box in doors.items():
            self.assertGreater(math.dist(B.BLOCK_XY, box["center"][:2]), 5.0, door)

    def test_away_from_pedestrian_lines_and_dummy_loops(self):
        """같이 켜도(시험은 0 으로 돈다) 보행자 선은 1.5 m 밖, 더미 루프는 겹치지 않는다(몸체 반폭 + 캡슐 반지름)."""
        for name, (a, b) in P.LINES:
            self.assertGreater(min(math.dist(B.BLOCK_XY, p) for p in samples(a, b)), 1.5, name)
        gap = hn.BODY_WIDTH / 2.0 + B.RADIUS
        for name, loop in T.LOOPS:
            for c, d in zip(loop, loop[1:] + loop[:1], strict=True):
                self.assertGreater(point_segment(B.BLOCK_XY, c, d), gap, name)


class Timing(unittest.TestCase):
    def test_appears_outside_the_stop_threshold(self):
        """몸체 앞끝에서 잰 첫 간격이 0.6 m 밖 — 멈춤은 '나타남'이 아니라 '다가감'으로 발동한다."""
        self.assertGreater(B.TRIGGER_M - G.BODY_HALF_LENGTH, G.STOP_M)
        self.assertLess(B.TRIGGER_M - G.BODY_HALF_LENGTH, G.RESUME_M + 0.5)     # 재계획이 끼어들 틈은 짧게

    def test_hold_fits_the_progress_checker(self):
        """유지 + 재개 지연이 movement_time_allowance 안 — 회복 행동(후진·회전) 없이 재개한다."""
        text = NAV2_PARAMS.read_text(encoding="utf-8")
        allowance = float(next(line.split(":")[1] for line in text.splitlines()
                               if line.strip().startswith("movement_time_allowance:")))
        self.assertLess(B.HOLD_S + G.RESUME_DELAY_S + 2.0, allowance)

    def test_parked_below_the_floor(self):
        self.assertLess(B.PARK_Z + 2 * B.RADIUS + B.HEIGHT, 0.0)


class Machine(unittest.TestCase):
    def test_places_once_then_lifts(self):
        rule = B.Blocker((0.0, 0.0), trigger_m=1.5, hold_s=5.0)
        self.assertEqual(rule.state, "armed")
        self.assertIsNone(rule.update(0.0, None))
        self.assertIsNone(rule.update(1.0, (3.0, 0.0)))
        self.assertEqual(rule.positions(), {})
        event, line = rule.update(2.0, (1.4, 0.3))
        self.assertEqual(event, "placed")
        self.assertIn("block_path placed at=(0.00, 0.00) sim=2.00 amr_dist=1.43", line)
        self.assertEqual(rule.positions(), {"block_1": (0.0, 0.0)})
        self.assertIsNone(rule.update(6.9, (0.8, 0.0)))
        self.assertTrue(rule.placed)
        event, line = rule.update(7.0, (0.8, 0.0))
        self.assertEqual(event, "lifted")
        self.assertIn("block_path lifted sim=7.00 held=5.00", line)
        self.assertEqual(rule.positions(), {})
        for t in (8.0, 20.0, 300.0):                       # 한 번뿐 — 돌아와도 다시 안 올라온다
            self.assertIsNone(rule.update(t, (0.5, 0.0)))
        self.assertEqual(rule.state, "lifted")

    def test_rejects_bad_values(self):
        with self.assertRaises(ValueError):
            B.Blocker(trigger_m=0.0)
        with self.assertRaises(ValueError):
            B.Blocker(hold_s=-1.0)

    def test_defaults(self):
        rule = B.Blocker()
        self.assertEqual((rule.xy, rule.trigger_m, rule.hold_s), (B.BLOCK_XY, 1.5, 5.0))


if __name__ == "__main__":
    unittest.main()
