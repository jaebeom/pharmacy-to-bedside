"""가짜 AMR(재범 채택 9/24 부가 장면, `p3sim/traffic_dummies.py`)의 순수 부분. Isaac 쪽(`Dummies`)은 L3 미실행.

오프라인 확인: 루프가 지도 빈 곳, 배송 경로 밖(회차107), 진짜 AMR 1.5 m 안이면 멈춤·멀어지면 재개.
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
from p3sim import traffic_dummies as T  # noqa: E402

ZONES = REPO / "src" / "rokey_p3_description" / "config" / "zones.hospital.yaml"
ROUTES = REPO / "src" / "rokey_p3_description" / "config" / "routes.hospital.yaml"


def segments(points, closed=False):
    out = list(zip(points[:-1], points[1:], strict=True))
    return out + [(points[-1], points[0])] if closed else out


def crosses(a, b, c, d):
    def side(p, q, r):
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
    return side(a, b, c) * side(a, b, d) < 0 and side(c, d, a) * side(c, d, b) < 0


def point_segment(p, a, b):
    ax, ay = b[0] - a[0], b[1] - a[1]
    t = max(0.0, min(1.0, ((p[0] - a[0]) * ax + (p[1] - a[1]) * ay) / (ax * ax + ay * ay)))
    return math.dist(p, (a[0] + ax * t, a[1] + ay * t))


class Loops(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.grid = hn.load_map()
        zones = hospital_zones.zones_from_yaml(ZONES)
        routes = hospital_decor.parse_routes_text(ROUTES.read_text(encoding="utf-8"))
        cls.deliveries = [hospital_decor.full_route(routes, zones, r["from"], r["to"]) for r in routes]

    def test_two_loops_on_free_floor_with_room_to_turn(self):
        self.assertEqual(len(T.LOOPS), 2)                       # 재범: 가짜 2대
        for name, points in T.LOOPS:
            self.assertEqual(T.loop_problems(self.grid, points, hn.PATH_RADIUS, hn.TURN_RADIUS), [], name)

    def test_loops_stay_off_every_delivery_route(self):
        """회차107: 로비 루프가 배송선과 겹쳐 선 더미가 경로 위에 있었고 진짜 AMR 트레이가 12 s 닿았다.
        루프 어디에 서도 더미 중심이 배송 경로에서 `ROUTE_CLEARANCE` 밖이다."""
        for name, loop in T.LOOPS:
            nearest = min(point_segment(p, a, b) for p in walk_loop(loop)
                          for route in self.deliveries for a, b in segments(route))
            self.assertGreaterEqual(nearest, T.ROUTE_CLEARANCE, name)
            for route in self.deliveries:                        # 가로지르지도 않는다
                for a, b in segments(route):
                    for c, d in segments(loop, closed=True):
                        self.assertFalse(crosses(a, b, c, d), (name, a, b))

    def test_route_clearance_keeps_both_bodies_apart(self):
        """진짜 AMR 경로 반경(반길이 + 받침 + 여유) + 더미 반길이 + 여유."""
        self.assertGreaterEqual(T.ROUTE_CLEARANCE, hn.PATH_RADIUS + hn.BODY_LENGTH / 2 + 0.05 - 1e-9)

    def test_corridor_runs_beside_the_ward_a_delivery(self):
        _name, loop = T.LOOPS[1]
        nearest = min(point_segment(p, a, b) for route in self.deliveries for a, b in segments(route)
                      for p in [(x / 10.0, loop[0][1]) for x in range(int(loop[0][0] * 10), int(loop[1][0] * 10))])
        self.assertLess(nearest, T.STOP_DISTANCE)               # 진짜 AMR 이 지나가면 선다
        self.assertGreaterEqual(nearest, T.ROUTE_CLEARANCE)     # 그래도 경로 밖에서


def walk_loop(loop, step_m=0.05):
    """루프 위 점들(`pose_at` 을 `step_m` 간격으로)."""
    total = T.loop_length(loop)
    return [T.pose_at(loop, k * step_m)[:2] for k in range(int(total / step_m) + 1)]


class Walk(unittest.TestCase):
    loop = ((0.0, 0.0), (2.0, 0.0), (2.0, 1.0), (0.0, 1.0))

    def test_moves_at_half_a_metre_a_second_along_the_loop(self):
        s, pose, stopped, _held = T.step(self.loop, 0.0, 1.0, [])
        self.assertFalse(stopped)
        self.assertAlmostEqual(s, 0.5)
        self.assertAlmostEqual(pose[0], 0.5)
        self.assertAlmostEqual(pose[2], 0.0)
        _s, pose, _stopped, _held = T.step(self.loop, 2.4, 0.2, [])    # 모서리를 돌면 yaw 가 바뀐다
        self.assertAlmostEqual(pose[2], math.pi / 2)

    def test_stops_within_one_and_a_half_metres(self):
        s, _pose, stopped, held = T.step(self.loop, 0.5, 1.0, [(0.5, 1.4)])
        self.assertTrue(stopped)
        self.assertAlmostEqual(s, 0.5)                           # 제자리
        self.assertEqual(held, 0.0)

    def test_does_not_chatter_at_the_stop_boundary(self):
        """회차69: 1.5 m 언저리에서 stop↔go 10번. 재개는 2.2 m 밖 + 멈춘 뒤 2 s 가 지나야 한다."""
        s, _pose, stopped, held = T.step(self.loop, 0.5, 0.1, [(0.5, 1.4)])
        self.assertTrue(stopped)
        for _ in range(30):                                      # 3 s 동안 AMR 이 1.6 m(멈춤·재개 사이)에 있다
            s, _pose, stopped, held = T.step(self.loop, s, 0.1, [(0.5, 1.6)], stopped, held)
            self.assertTrue(stopped)
        self.assertAlmostEqual(s, 0.5)

    def test_resumes_only_after_the_wait_and_beyond_the_resume_distance(self):
        s, _pose, stopped, held = T.step(self.loop, 0.5, 0.1, [(0.5, 1.4)])
        for _ in range(10):                                      # 1 s 뒤 AMR 이 멀어졌지만 아직 2 s 안
            s, _pose, stopped, held = T.step(self.loop, s, 0.1, [(0.5, 3.0)], stopped, held)
        self.assertTrue(stopped)
        for _ in range(11):
            s, _pose, stopped, held = T.step(self.loop, s, 0.1, [(0.5, 3.0)], stopped, held)
        self.assertFalse(stopped)                                # 2 s 넘고 2.2 m 밖 → 간다
        self.assertGreater(s, 0.5)

    def test_unknown_real_pose_does_not_stop_it(self):
        _s, _pose, stopped, _held = T.step(self.loop, 0.0, 0.1, [None])
        self.assertFalse(stopped)

    def test_count_is_bounded_by_the_loops(self):
        self.assertEqual(T.plan(0), [])
        self.assertEqual([name for name, _pts in T.plan(2)], ["lobby", "corridor_a"])
        with self.assertRaises(ValueError):
            T.plan(3)


if __name__ == "__main__":
    unittest.main()
