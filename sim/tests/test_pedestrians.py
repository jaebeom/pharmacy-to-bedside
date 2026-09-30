"""보행자(재범 결정 9/25 회피 장면, `p3sim/pedestrians.py`)의 순수 부분. Isaac 쪽(`Pedestrians`)은 L3 미실행.

오프라인 확인: 왕복 선이 지도 빈 곳, 배송 경로를 넓은 곳에서 가로지름, 적재·도크·병상·간호사실 정차 자리와
더미 루프에서 떨어짐, 0.8 m/s 로 멈추지 않고 끝에서 돌아섬.
"""

import math
import sys
import unittest
from pathlib import Path

STANDALONE = Path(__file__).resolve().parents[1] / "standalone"
REPO = STANDALONE.parents[1]
sys.path.insert(0, str(STANDALONE))
from p3sim import hospital_decor, hospital_zones  # noqa: E402
from p3sim import hospital_nav as hn  # noqa: E402
from p3sim import pedestrians as P  # noqa: E402
from p3sim import traffic_dummies as T  # noqa: E402

ZONES = REPO / "src" / "rokey_p3_description" / "config" / "zones.hospital.yaml"
ROUTES = REPO / "src" / "rokey_p3_description" / "config" / "routes.hospital.yaml"
ANCHORS = REPO / "sim" / "scenes" / "hospital_navigationv1.anchors.json"


def crosses(a, b, c, d):
    def side(p, q, r):
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
    return side(a, b, c) * side(a, b, d) < 0 and side(c, d, a) * side(c, d, b) < 0


def point_segment(p, a, b):
    ax, ay = b[0] - a[0], b[1] - a[1]
    t = max(0.0, min(1.0, ((p[0] - a[0]) * ax + (p[1] - a[1]) * ay) / (ax * ax + ay * ay)))
    return math.dist(p, (a[0] + ax * t, a[1] + ay * t))


def samples(a, b, n=40):
    return [(a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n) for k in range(n + 1)]


class Lines(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.grid = hn.load_map()
        cls.zones = hospital_zones.zones_from_yaml(ZONES)
        routes = hospital_decor.parse_routes_text(ROUTES.read_text(encoding="utf-8"))
        cls.deliveries = [hospital_decor.full_route(routes, cls.zones, r["from"], r["to"]) for r in routes]

    def test_two_lines_on_free_floor(self):
        self.assertEqual(len(P.LINES), 2)
        for name, (a, b) in P.LINES:
            self.assertEqual(T.loop_problems(self.grid, (a, b), P.CLEARANCE_RADIUS, P.CLEARANCE_RADIUS), [], name)

    def test_each_line_crosses_deliveries_where_the_corridor_is_wide(self):
        """가로지르는 점마다 AMR 이 비껴갈 폭(회전 원 + 사람 둘레)이 지도상 비어 있다."""
        for name, (a, b) in P.LINES:
            hits = [(c, d) for route in self.deliveries for c, d in zip(route[:-1], route[1:], strict=True)
                    if crosses(a, b, c, d)]
            self.assertTrue(hits, name)
            for c, d in hits:
                v1, v2 = (b[0] - a[0], b[1] - a[1]), (d[0] - c[0], d[1] - c[1])
                cos = abs(v1[0] * v2[0] + v1[1] * v2[1]) / (math.hypot(*v1) * math.hypot(*v2))
                self.assertGreaterEqual(math.degrees(math.acos(min(1.0, cos))), 45.0, name)   # 비스듬히
                denom = (a[0] - b[0]) * (c[1] - d[1]) - (a[1] - b[1]) * (c[0] - d[0])
                t = ((a[0] - c[0]) * (c[1] - d[1]) - (a[1] - c[1]) * (c[0] - d[0])) / denom
                x, y = a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])
                room = hn.TURN_RADIUS + P.CLEARANCE_RADIUS
                self.assertEqual(T.loop_problems(self.grid, ((x, y), (x + 0.01, y)), 0.0, room), [], (name, x, y))

    def test_away_from_stops_and_approach_points(self):
        """적재·도크·간호사실·병상 정차 자리와 그 협탁·인식표에서 2 m 밖(문 앞·접근점 제외)."""
        for name, (a, b) in P.LINES:
            for zone, pose in self.zones.items():
                for p in samples(a, b):
                    self.assertGreater(math.dist(p, pose[:2]), 2.0, (name, zone))

    def test_away_from_the_ward_doors(self):
        import json

        doors = json.loads(ANCHORS.read_text(encoding="utf-8"))["doors"]
        for name, (a, b) in P.LINES:
            for door, box in doors.items():
                centre = box["center"][:2]
                self.assertGreater(min(math.dist(p, centre) for p in samples(a, b)), 3.0, (name, door))

    def test_clear_of_the_dummy_loops(self):
        """더미는 사람을 보고 서지 않는다 — 겹치지 않게 선을 떨어뜨렸다(몸체 반폭 + 사람 둘레)."""
        gap = hn.BODY_WIDTH / 2.0 + P.CLEARANCE_RADIUS
        for name, (a, b) in P.LINES:
            for _loop_name, loop in T.LOOPS:
                for c, d in zip(loop, loop[1:] + loop[:1], strict=True):
                    nearest = min(point_segment(p, c, d) for p in samples(a, b))
                    self.assertGreater(nearest, gap, (name, _loop_name))


class Walk(unittest.TestCase):
    a, b = (0.0, 0.0), (0.0, 2.0)

    def test_walks_there_and_back_without_stopping(self):
        x, y, yaw, lap = P.pose(self.a, self.b, 0.8)
        self.assertEqual((round(x, 6), round(y, 6), lap), (0.0, 0.8, 0))
        self.assertAlmostEqual(yaw, math.pi / 2)
        x, y, yaw, lap = P.pose(self.a, self.b, 2.5)             # 끝을 지나 돌아선다
        self.assertEqual(lap, 1)
        self.assertAlmostEqual(y, 1.5)
        self.assertAlmostEqual(yaw, -math.pi / 2)
        _x, y, _yaw, lap = P.pose(self.a, self.b, 4.2)
        self.assertEqual(lap, 2)
        self.assertAlmostEqual(y, 0.2)

    def test_stops_near_an_amr_and_resumes_like_the_dummies(self):
        """회차70: 멈추지 않던 보행자가 AMR 본체와 두 번 닿았다. 1.5 m 안 정지, 2 s·2.2 m 뒤 재개."""
        s, _p, stopped, held = P.walk(self.a, self.b, 0.5, 0.1, [(0.0, 1.9)])
        self.assertTrue(stopped)
        for _ in range(30):
            s, _p, stopped, held = P.walk(self.a, self.b, s, 0.1, [(0.0, 2.1)], stopped, held)
            self.assertTrue(stopped)
        for _ in range(3):
            s, _p, stopped, held = P.walk(self.a, self.b, s, 0.1, [(0.0, 5.0)], stopped, held)
        self.assertFalse(stopped)
        self.assertGreater(s, 0.5)

    def test_lobby_line_moved_off_the_contact_spot(self):
        a, b = dict(P.LINES)["lobby"]
        nearest = min(math.dist(p, (5.6, 4.5)) for p in samples(a, b))
        self.assertGreater(nearest, 1.0)

    def test_speed_and_count(self):
        self.assertEqual(P.SPEED, 0.8)
        self.assertEqual(P.plan(0), [])
        self.assertEqual([n for n, _l in P.plan(2)], ["lobby", "ward_crossing"])
        with self.assertRaises(ValueError):
            P.plan(3)


if __name__ == "__main__":
    unittest.main()
