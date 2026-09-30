"""belt.RouteBeltModel: 여러 트랙 컨베이어 경로의 봉투 상태(#527 H1). Isaac 없음. 트랙 AABB 는 합성값이다.

    python3 -m unittest sim.tests.test_route_belt
"""

import math
import sys
import unittest
from pathlib import Path

STANDALONE = Path(__file__).resolve().parents[1] / "standalone"
sys.path.insert(0, str(STANDALONE))

from p3sim import belt, common, observation  # noqa: E402

POUCH = (0.10, 0.07, 0.01)
TOP = 0.80
# L 자 경로(합성): +x 로 가는 트랙, 모퉁이에서 -y 로 꺾는 트랙, 그 끝의 마지막 롤러(-y 가 출구).
TRACKS = [{"min": [0.0, -0.15, TOP - 0.05], "max": [2.0, 0.15, TOP]},
          {"min": [1.70, -2.0, TOP - 0.05], "max": [2.0, -0.15, TOP]}]
TERMINAL = {"min": [1.70, -2.30, TOP - 0.01], "max": [2.0, -2.0, TOP]}
REST_Z = TOP + POUCH[2] / 2.0  # 봉투 중심이 윗면에 놓인 높이
YAW_90 = (math.cos(math.pi / 4), 0.0, 0.0, math.sin(math.pi / 4))


def model(**kwargs):
    return belt.RouteBeltModel(TRACKS, TERMINAL, "-y", POUCH, edge_margin=0.03, height_tolerance=0.02, **kwargs)


def at(x, y, z=REST_Z, orientation=(1.0, 0.0, 0.0, 0.0)):
    return belt.route_point((x, y, z), orientation)


class ReceiverTests(unittest.TestCase):
    def receiver_model(self):
        return model(receiver={"min": [1.7, -2.6, 0.0], "max": [2.0, -2.25, TOP]},
                     settle_time_s=1.0, fail_closed=True)

    def test_table_support_allows_xy_overlap_with_roller(self):
        m = self.receiver_model()
        self.assertFalse(m.in_end_zone(at(1.85, -2.27)))
        self.assertTrue(m.in_end_zone(at(1.85, -2.32)))  # supported by table despite roller XY overlap
        self.assertTrue(m.in_end_zone(at(1.85, -2.4)))
        self.assertTrue(m.on_belt(at(1.85, -2.4)))

    def test_stationary_supported_overlap_emits_arrival(self):
        m = self.receiver_model()
        m.accept('table-overlap', 'ord-1', 0.0)
        point = at(1.85, -2.32)
        self.assertLess(m.end_status(point)['edge_gap_m'], 0.0)
        m.observe(point, 0.0, 1.0)
        self.assertIn(belt.POUCH_AT_END, m.observe(point, 0.0, 2.1)[0])

    def test_requires_continuous_rest_and_keeps_occupancy(self):
        m = self.receiver_model()
        m.accept("receiver-test", "ord-1", 0.0)
        point = at(1.85, -2.4)
        self.assertNotIn(belt.POUCH_AT_END, m.observe(point, 0.1, 1.0)[0])
        self.assertNotIn(belt.POUCH_AT_END, m.observe(point, 0.0, 2.0)[0])
        self.assertNotIn(belt.POUCH_AT_END, m.observe(point, None, 2.7)[0])
        self.assertNotIn(belt.POUCH_AT_END, m.observe(point, 0.0, 3.0)[0])
        self.assertIn(belt.POUCH_AT_END, m.observe(point, 0.0, 4.1)[0])
        self.assertTrue(m.occupied)
        self.assertFalse(m.observe_held(point))
        self.assertTrue(m.observe_held(at(1.4, -2.4, 1.1)))

    def test_floor_is_not_arrival(self):
        self.assertFalse(self.receiver_model().in_end_zone(at(1.85, -2.4, .005)))


class RouteGeometryTests(unittest.TestCase):
    def test_on_route(self):
        m = model()
        self.assertTrue(m.on_belt(at(0.5, 0.0)))  # 첫 트랙
        self.assertTrue(m.on_belt(at(1.85, -1.0)))  # 꺾인 뒤 트랙
        self.assertTrue(m.on_belt(at(1.85, -0.15)))  # 이음매
        self.assertTrue(m.on_belt(at(1.85, -2.15)))  # 마지막 롤러 위
        self.assertTrue(m.on_belt(at(0.5, 0.0, REST_Z + 0.04)))  # 높이 띠 안(튀어 오름)

    def test_off_route_fell(self):
        m = model()
        self.assertFalse(m.on_belt(at(0.5, 0.40)))  # 옆으로 떨어짐
        self.assertFalse(m.on_belt(at(1.0, -1.0)))  # 모퉁이 안쪽 빈 자리(두 AABB 의 합집합 밖)
        self.assertFalse(m.on_belt(at(0.5, 0.0, 0.005)))  # xy 는 트랙 안인데 바닥에 있다
        self.assertFalse(m.on_belt(at(1.85, -2.60)))  # 출구 너머
        self.assertEqual(observation.ZONE_OFF_BELT, observation.pouch_zone(m, at(0.5, 0.40)))

    def test_reached_end(self):
        m = model()
        # 앞 끝(-y 쪽)이 출구에서 0.03 안: 중심 y = -2.30 + 0.035 + 0.01
        point = at(1.85, -2.255)
        self.assertTrue(m.in_end_zone(point))
        self.assertEqual(observation.ZONE_END, observation.pouch_zone(m, point))
        # 90° 돌아 있어도 전체가 롤러 위면 도착이다(앞 끝은 이제 x 치수 0.10 의 반)
        self.assertTrue(m.in_end_zone(at(1.85, -2.24, orientation=YAW_90)))

    def test_not_yet_at_end(self):
        m = model()
        for point in (at(0.5, 0.0), at(1.85, -1.0),
                      at(1.85, -2.10),  # 롤러 위지만 출구에서 0.03 보다 멀다
                      at(1.85, -2.02),  # 뒤 끝이 아직 앞 트랙에 걸쳐 있다
                      at(1.72, -2.255)):  # 옆으로 비어져 나와 전체가 롤러 위가 아니다
            self.assertFalse(m.in_end_zone(point), point)
            self.assertNotEqual(observation.ZONE_END, observation.pouch_zone(m, point))
        self.assertEqual(observation.ZONE_ON_BELT, observation.pouch_zone(m, at(1.85, -1.0)))
        self.assertTrue(m.on_belt(at(1.85, -2.10)))
        self.assertFalse(m.end_status(at(1.85, -2.10))["reached"])

    def test_bad_inputs_are_refused(self):
        with self.assertRaises(ValueError):
            belt.RouteBeltModel([], TERMINAL, "-y", POUCH)
        with self.assertRaises(ValueError):
            belt.RouteBeltModel([{"min": [1, 0, 0], "max": [0, 1, 1]}], TERMINAL, "-y", POUCH)
        with self.assertRaises(ValueError):
            belt.RouteBeltModel(TRACKS, TERMINAL, "down", POUCH)
        with self.assertRaises(ValueError):
            belt.RouteBeltModel(TRACKS, TERMINAL, "-y", POUCH, edge_margin=0.0)

    def test_route_point_prints_in_stage_logs(self):
        self.assertEqual("[1.0000, 2.0000, 0.8050, 1.0000, 0.0000, 0.0000, 0.0000]",
                         common.format_values(at(1.0, 2.0)))
        self.assertTrue(model().on_belt(tuple(at(0.5, 0.0))))  # 그냥 튜플도 받는다


class RouteObserveTests(unittest.TestCase):
    """BeltModel 과 같은 필드(occupied·at_end·order_id·running)와 알림을 낸다. 속도 표본은 없다."""

    def accepted(self, **kwargs):
        m = model(**kwargs)
        self.assertEqual("", m.decide_dispense("order-1", True, True))
        self.assertEqual([belt.DISPENSED], m.accept("req-1", "order-1", 0.0))
        return m

    def test_speed_sampling_is_off(self):
        self.assertFalse(model().speed_sampling)
        self.assertTrue(belt.BeltModel(1.6, 0.25, 0.15).speed_sampling)

    def test_travel_then_at_end(self):
        m = self.accepted()
        self.assertEqual(([], []), m.observe(at(0.5, 0.0), 0.3, 1.0))
        self.assertEqual(([], []), m.observe(at(1.85, -1.0), 0.3, 5.0))
        events, notes = m.observe(at(1.85, -2.255), 0.2, 8.0)
        self.assertEqual(([], ["stop_belt"]), (events, notes))
        self.assertFalse(m.running)
        self.assertEqual(([], []), m.observe(at(1.85, -2.255), 0.0, 8.1))
        events, _notes = m.observe(at(1.85, -2.255), 0.0, 8.5)
        self.assertEqual([belt.POUCH_AT_END], events)
        self.assertEqual({"occupied": True, "at_end": True, "order_id": "order-1"}, m.state())

    def test_moving_pouch_in_the_end_zone_is_not_at_end(self):
        """도착은 끝 롤러 위 + settle_time 정지다(작전 9/23). 끝 구역이어도 움직이면 아니다."""
        m = self.accepted()
        m.observe(at(1.85, -2.255), 0.2, 8.0)
        self.assertEqual(([], []), m.observe(at(1.85, -2.255), 0.15, 9.0))
        self.assertFalse(m.at_end)

    def test_leaving_the_end_zone_restarts_the_settle_timer(self):
        m = self.accepted()
        m.observe(at(1.85, -2.255), 0.2, 8.0)                                     # stop_belt
        m.observe(at(1.85, -2.255), 0.0, 8.1)                                     # 정지, 타이머 시작
        self.assertEqual(([], []), m.observe(at(1.85, -2.0), 0.0, 8.3))          # 구역 밖
        self.assertEqual(([], []), m.observe(at(1.85, -2.255), 0.0, 8.35))       # 다시 시작
        self.assertEqual(([], []), m.observe(at(1.85, -2.255), 0.0, 8.6))        # 0.25 s 만 지났다
        events, _notes = m.observe(at(1.85, -2.255), 0.0, 8.7)
        self.assertEqual([belt.POUCH_AT_END], events)

    def test_fell_frees_the_belt(self):
        m = self.accepted()
        events, notes = m.observe(at(0.5, 0.40, 0.005), 0.5, 2.0)
        self.assertEqual(([], ["pouch_left_belt"]), (events, notes))
        self.assertFalse(m.occupied)

    def test_fell_fail_closed_holds_the_belt(self):
        m = self.accepted(fail_closed=True)
        _events, notes = m.observe(at(0.5, 0.40, 0.005), 0.5, 2.0)
        self.assertEqual(["pouch_lost"], notes)
        self.assertTrue(m.occupied and m.lost)
        self.assertEqual(observation.OCCUPANCY_UNKNOWN, observation.occupancy(m))

    def test_not_yet_at_end_times_out(self):
        m = self.accepted()
        _events, notes = m.observe(at(1.85, -1.0), 0.0, 25.0)  # 멈췄지만 끝이 아니다
        self.assertEqual(["at_end_timeout"], notes)
        self.assertFalse(m.at_end)

    def test_held_pouch_frees_only_off_route(self):
        m = self.accepted()
        self.assertFalse(m.observe_held(at(1.85, -2.255)))  # 아직 롤러 위
        self.assertTrue(m.observe_held(at(1.85, -2.255, REST_Z + 0.20)))  # 들어 올림
        self.assertFalse(m.occupied)


if __name__ == "__main__":
    unittest.main()
