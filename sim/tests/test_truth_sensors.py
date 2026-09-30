"""참값 센서(봉투 검출·인식표 판독)의 판정과 메시지. Isaac 없음.

K4·K5 (비전·작전 9/21). **스텁이 아니라 센서**라는 것이 여기서 지켜야 할 성질이다 — 판정 영역 안에
실제로 있는 것만 내고, 없으면 빈 목록이다. 그래야 음성 사례(`not_detected`·`AUTH_FAIL`)가 선다.

    python3 -m unittest discover -s sim/tests -p 'test_truth_sensors.py'
"""

import math
import sys
import unittest
from pathlib import Path

STANDALONE = Path(__file__).resolve().parents[1] / "standalone"
sys.path.insert(0, str(STANDALONE))

from p3sim import bridge as B  # noqa: E402
from p3sim import layout as L  # noqa: E402
from p3sim import truth_sensors as T  # noqa: E402

IDENTITY = (0.0, 0.0, 0.0, 1.0)


class Detection(unittest.TestCase):
    def test_the_slot_index_is_always_minus_one(self):
        """계약 319줄. 칸 번호를 안 쓰면 0/1 기준(미결 결정 28)에 안 걸린다."""
        item = T.detection("ord-0001", (0.5, 0.1, 0.3), IDENTITY)
        self.assertEqual(item["slot_index"], -1)
        self.assertEqual(B.SLOT_INDEX_V1, -1)

    def test_an_element_carries_no_version_or_stamp(self):
        """v·stamp·frame_id 는 최상위에만 있다(비전 9/21)."""
        self.assertEqual(set(T.detection("ord-0001", (0.5, 0.1, 0.3), IDENTITY)),
                         {"order_id", "confidence", "pose", "slot_index"})

    def test_a_truth_detection_has_confidence_one(self):
        self.assertEqual(T.detection("x", (1.0, 0.0, 0.0), IDENTITY)["confidence"], 1.0)

    def test_a_missing_order_id_becomes_an_empty_string(self):
        self.assertEqual(T.detection(None, (1.0, 0.0, 0.0), IDENTITY)["order_id"], "")


class PoseIsNeverZero(unittest.TestCase):
    """팔은 `abs(x)+abs(y)+abs(z) < 1e-6` 이면 "거리를 못 정했다" 로 닫는다(비전 9/21).

    지금 스텁 검출기가 정확히 이 자리에서 걸린다. 참값 센서가 같은 값을 내면 아무것도 나아지지 않는다.
    """

    def message(self, base_xyz):
        item = T.detection("ord-0001", base_xyz, IDENTITY)
        return T.pouches_message(1.5, 1, "amr_1/base_link", [item])

    def test_a_real_pose_validates(self):
        self.assertEqual(B.validate(B.POUCHES, self.message((0.5, 0.1, 0.3))), [])

    def test_a_zero_pose_is_rejected_by_the_schema(self):
        problems = B.validate(B.POUCHES, self.message((0.0, 0.0, 0.0)))
        self.assertTrue(any("zero" in p for p in problems), problems)

    def test_the_belt_end_is_not_at_the_arm_base(self):
        """벨트 끝이 팔 밑동과 같은 자리면 참 자세가 0 이 되어 팔이 거부한다."""
        import pharmacy_stage

        args = pharmacy_stage.parse_args(["--preset", "emptyworld-loop"])
        layout = pharmacy_stage.room(args)
        belt_end = (1.35 + args.belt_length, layout["belt_start"][1], 0.75)
        offset = T.to_base(belt_end, args.ur5_base)
        self.assertGreater(sum(abs(v) for v in offset), 1e-6)


class BeltEndAndSlots(unittest.TestCase):
    def test_only_what_is_inside_the_belt_end_counts(self):
        end = (2.95, 1.00)
        self.assertTrue(T.in_belt_end((2.95, 1.00, 0.75), end))
        self.assertTrue(T.in_belt_end((2.95 + T.BELT_END_RADIUS, 1.00, 0.75), end))
        self.assertFalse(T.in_belt_end((2.95 + T.BELT_END_RADIUS + 0.01, 1.00, 0.75), end))

    def test_the_belt_end_test_ignores_height(self):
        """봉투 두께로 판정이 갈리면 안 된다."""
        end = (2.95, 1.00)
        self.assertTrue(T.in_belt_end((2.95, 1.00, 5.0), end))

    def test_a_slot_uses_the_same_aabb_as_the_in_slot_truth(self):
        slot, size = (3.25, 0.20, 0.47), (0.14, 0.11, 0.04)
        self.assertTrue(T.in_slot(slot, slot, size))
        self.assertFalse(T.in_slot((slot[0] + 0.08, slot[1], slot[2]), slot, size))


class MovingPouchesAreHeld(unittest.TestCase):
    """**아직 굴러가는 봉투는 검출로 내지 않는다.** lap5 의 ⑤ 실패 원인이다.

    센서 영역(0.25)이 벨트 정지 구역(0.15)보다 넓어 봉투가 **정지 0.667 s 전에** 잡힌다. 그 사이에
    0.10 m 를 더 간다. 팔이 그 자세로 풀면 봉투가 실제로 서는 자리와 어긋나고, lap5 에서 그 값이
    **0.0988 m**(계산 0.1000)였다 — 앞팔↔벨트 여유가 +0.087 → +0.001 로 깎여 닿았다.

    `PouchDetection` 에는 속도 자리가 없고 팔에는 추종 파지가 없다 — **못 잡을 목표를 주지 않는다.**
    """

    def test_the_limit_is_near_the_belt_settle_speed(self):
        """`--settle-speed`(0.01)와 같은 뜻이고 그보다 넉넉하다."""
        self.assertGreater(T.POUCH_STILL_SPEED, 0.01)
        self.assertLess(T.POUCH_STILL_SPEED, 0.05)

    def test_the_lead_time_explains_the_observed_gap(self):
        """검출이 정지보다 앞서는 시간 × 벨트 속도 = lap5 의 어긋남."""
        import pharmacy_stage

        args = pharmacy_stage.parse_args(["--preset", "emptyworld-loop"])
        lead = (T.BELT_END_RADIUS - args.end_zone) / args.belt_speed
        self.assertAlmostEqual(lead * args.belt_speed, 0.100, places=3)

    def test_the_stage_checks_the_speed_and_says_so(self):
        source = (STANDALONE / "pharmacy_stage.py").read_text()
        self.assertIn("speed > sensorlib.POUCH_STILL_SPEED", source)
        self.assertIn("pouch detection held order_id=", source)

    def test_an_unreadable_speed_does_not_block(self):
        """진단이 센서를 멈추면 안 된다 — 못 읽으면 막지 않는다."""
        source = (STANDALONE / "pharmacy_stage.py").read_text()
        self.assertIn("speed is not None and speed > sensorlib.POUCH_STILL_SPEED:", source)

    def test_a_pouch_in_a_deck_slot_is_not_held_by_its_world_speed(self):
        """상판 칸에 든 봉투는 차체와 같이 움직인다. 세계 속도로 막으면 AMR 이 정차·정렬 중일 때 검출이 0 이다.

        9/23 bed_a1: `pouch detection held … speed=0.1056 limit=0.02` 뒤
        `PickPouch ord-0001: not_detected (검출 0건)`. 칸 안이라는 것 자체가 놓였다는 증거다.
        """
        source = (STANDALONE / "pharmacy_stage.py").read_text()
        self.assertIn("if not on_deck and speed is not None and speed > sensorlib.POUCH_STILL_SPEED:", source)
        body = source.split("def pouch_detections():", 1)[1].split("def pouches_payload", 1)[0]
        self.assertLess(body.index("on_deck = "), body.index("if not on_deck and speed is not None"))


class TheSettledPouchStaysInTheZone(unittest.TestCase):
    """봉투는 벨트 **끝**이 아니라 정지 구역 어귀에 선다. 센서 영역이 그보다 좁으면 안 된다.

    실습25 에서 내가 자세를 예상하며 "봉투가 벨트 끝(x 2.95)에 선다" 고 했는데 틀렸다 — 관측은 2.805 였고,
    계산하면 `끝 − end_zone` = 2.800 에 정착 밀림 0.005 다. 벨트는 봉투가 정지 구역에 **들어서는 순간**
    서기 때문이다. y·z 는 맞았고 x 만 0.145 어긋났는데, 그 값이 정확히 `end_zone` 이다.
    """

    def setUp(self):
        import pharmacy_stage

        self.args = pharmacy_stage.parse_args(["--preset", "emptyworld-loop"])

    def test_the_sensor_zone_is_wider_than_the_stop_zone(self):
        """좁으면 **벨트가 선 바로 그 순간 검출이 끊긴다** — 팔이 집으러 오는 그때다."""
        self.assertGreater(T.BELT_END_RADIUS, self.args.end_zone,
                           "정착한 봉투가 판정 영역 밖에 선다")

    def test_the_settled_pouch_is_inside_by_a_margin(self):
        end_x = 1.35 + self.args.belt_length
        settled = (end_x - self.args.end_zone, self.args.belt_start[1] if self.args.belt_start else 1.0, 0.755)
        self.assertTrue(T.in_belt_end(settled, (end_x, settled[1])))

    def test_moving_the_stop_zone_past_the_sensor_would_be_caught(self):
        """관계를 잡는 것이지 값을 잡는 것이 아니다 — `--end-zone` 을 키우면 여기서 걸린다."""
        self.assertFalse(T.in_belt_end((2.95 - (T.BELT_END_RADIUS + 0.01), 1.0, 0.755), (2.95, 1.0)))


class ParkedZoneTellsBedsApart(unittest.TestCase):
    """침상을 가리는 근거가 **yaw 에서 자리로** 바뀌었다(9/21).

    전에는 두 줄이 통로를 공유해 `bed_a1`·`bed_b1` 이 같은 (x, y) 에 yaw 만 반대였고, 그래서 yaw 판정이
    음성 사례의 열쇠였다. 그런데 **기하가 정차 yaw 0 을 강제한다**(회전하면 보관함에 닿는다, 주행 9/21).
    yaw 로 못 가르니 **한 줄로 늘어놓고 자리로 가른다.** 판정은 여전히 위치 + yaw 둘 다이고,
    yaw 가 안 맞으면(다른 방향으로 서 있으면) **아무것도 안 낸다** — 그 성질은 그대로다.
    """

    def setUp(self):
        self.zones = L.full_loop_zones()
        self.beds = {zone: self.zones[zone] for zone in L.bed_zones()}
        self.tol_xy, self.tol_yaw = T.TAG_READ_RADIUS, L.ZONE_TOL["tol_yaw"]

    def at(self, zone_id, dyaw=0.0, dx=0.0):
        x, y, _z, yaw = self.zones[zone_id]
        return T.parked_zone((x + dx, y, yaw + dyaw), self.beds, self.tol_xy, self.tol_yaw)

    def test_every_bed_has_its_own_pose(self):
        """자리로 가르므로 둘이 겹치면 못 가른다."""
        poses = [tuple(round(v, 6) for v in self.zones[z][:2]) for z in L.bed_zones()]
        self.assertEqual(len(set(poses)), len(poses), poses)

    def test_each_bed_is_recognised_from_its_own_pose(self):
        for zone_id in L.bed_zones():
            self.assertEqual(self.at(zone_id), zone_id)

    def test_facing_the_wrong_way_matches_nothing(self):
        """방향이 틀리면 **아무것도 안 낸다** — 팔이 시한까지 기다려 UNREADABLE 이 된다."""
        self.assertIsNone(self.at(L.bed_zones()[0], dyaw=math.pi))

    def test_a_yaw_outside_the_tolerance_matches_nothing(self):
        self.assertIsNone(self.at(L.bed_zones()[0], dyaw=self.tol_yaw + 0.05))

    def test_standing_between_two_beds_picks_the_nearer_one(self):
        """자리로 가르므로 중간에 서면 가까운 쪽이다. 침상 간격의 절반보다 반경이 작아야 한다."""
        first, second = L.bed_zones()[0], L.bed_zones()[1]
        gap = self.zones[second][0] - self.zones[first][0]
        self.assertEqual(self.at(first, dx=gap * 0.25), first)
        self.assertEqual(self.at(second, dx=-gap * 0.25), second)

    def test_a_pose_far_from_every_zone_is_none(self):
        self.assertIsNone(T.parked_zone((0.0, 0.0, 0.0), self.beds, self.tol_xy, self.tol_yaw))

    def test_sub_frames_are_never_returned(self):
        for zone_id in self.zones:
            if "/" in zone_id:
                x, y, _z, yaw = self.zones[zone_id]
                self.assertNotEqual(T.parked_zone((x, y, yaw), self.beds, 10.0, 10.0), zone_id)


class TagReadRadius(unittest.TestCase):
    """센서의 판정 반경은 **주행의 도착 공차와 다른 값**이다. 같은 숫자로 두면 여유가 mm 단위가 된다.

    실습26(9/21): 추종기가 공차 원에 **들어서는 즉시** 멈춰 여섯 번 모두 목표에서 0.1396–0.1461 m 였다.
    공차 0.15 를 그대로 쓰면 여유가 4–10 mm 다 — 추종 오차가 조금만 늘면 인식표가 안 나오고 인증이
    `UNREADABLE` 로 닫힌다. 값이 아니라 **관계**를 잡는다.
    """

    OBSERVED_STOP_ERROR = 0.1461  # 실습26 여섯 회 중 최대

    def setUp(self):
        self.zones = L.full_loop_zones()
        self.beds = {zone: self.zones[zone] for zone in L.bed_zones()}

    def test_it_is_wider_than_the_navigation_tolerance(self):
        self.assertGreater(T.TAG_READ_RADIUS, L.ZONE_TOL["tol_xy"],
                           "주행 공차와 같거나 좁으면 도착하고도 인식표가 안 나온다")

    def test_it_leaves_room_beyond_the_observed_stop_error(self):
        """관측 0.1461 에 붙여 두면 다음 회차에서 조금만 늘어도 닫힌다."""
        self.assertGreater(T.TAG_READ_RADIUS - self.OBSERVED_STOP_ERROR, 0.15)

    def test_it_never_reaches_the_next_bed(self):
        """자리가 다른 침상 사이 거리의 절반을 넘으면 옆 침상과 헷갈린다."""
        import itertools
        import math

        spread = [math.dist(a[:2], b[:2]) for a, b in itertools.combinations(self.beds.values(), 2)]
        apart = [d for d in spread if d > 1e-9]
        self.assertTrue(apart)
        self.assertLess(T.TAG_READ_RADIUS, min(apart) / 2.0)

    def test_a_pose_at_the_observed_stop_error_is_recognised(self):
        x, y, _z, yaw = self.zones["bed_a1"]
        at = T.parked_zone((x - self.OBSERVED_STOP_ERROR, y, yaw), self.beds,
                           T.TAG_READ_RADIUS, L.ZONE_TOL["tol_yaw"])
        self.assertEqual(at, "bed_a1")

    def test_the_yaw_tolerance_is_not_widened(self):
        """자리로 가르게 됐어도 yaw 는 여전히 본다 — 엉뚱한 방향으로 선 것을 통과시키면 안 된다.

        도착 yaw 오차는 관측 0.019 라 0.2 로 충분하다(주행 L3).
        """
        import math

        x, y, _z, yaw = self.zones["bed_a1"]
        self.assertIsNone(T.parked_zone((x, y, yaw + math.pi), self.beds,
                                        T.TAG_READ_RADIUS, L.ZONE_TOL["tol_yaw"]))
        self.assertLess(L.ZONE_TOL["tol_yaw"], math.pi / 4)

    def test_the_stage_passes_only_beds_as_candidates(self):
        """안 좁히면 가장 가까운 것이 load·dock_1(0.60 m 사이)로 나와 침상 앞인데도 안 낸다."""
        source = (STANDALONE / "pharmacy_stage.py").read_text()
        self.assertIn("if zone in sensor_beds", source)
        self.assertIn("sensorlib.TAG_READ_RADIUS", source)


class TagsComeFromTheOrderPool(unittest.TestCase):
    POOL = Path(__file__).resolve().parents[2] / "src/rokey_p3_orchestrator/config/order_pool.yaml"

    def table(self):
        if not self.POOL.is_file():
            self.skipTest("주문 풀이 없다")
        return T.bed_patients(self.POOL.read_text())

    def test_every_order_bed_has_a_patient(self):
        table = self.table()
        self.assertEqual(set(table), set(L.bed_zones()))

    def test_no_bed_is_ambiguous(self):
        """한 침상에 환자가 둘이면 어느 인식표를 낼지 모른다 — 기동을 거부한다."""
        self.assertEqual(T.ambiguous_beds(self.table()), [])

    def test_two_patients_in_one_bed_are_reported(self):
        self.assertEqual(T.ambiguous_beds({"bed_a1": {"1001", "1002"}, "bed_a2": {"1003"}}), ["bed_a1"])

    def test_the_tag_id_follows_the_contract(self):
        self.assertEqual(T.patient_tag("1001"), "pt-1001")
        self.assertEqual(T.station_tag("station_a"), "st-station_a")

    def test_it_reads_without_pyyaml(self):
        """Isaac 의 python 에는 PyYAML 이 없다."""
        source = (STANDALONE / "p3sim/truth_sensors.py").read_text()
        self.assertNotIn("import yaml", source)


class TagMessage(unittest.TestCase):
    def test_a_normal_read_validates(self):
        message = T.tag_message(1.5, 1, "amr_1/base_link", "bed_a1", T.patient_tag("1001"))
        self.assertEqual(B.validate(B.TAG_READS, message), [])

    def test_an_empty_tag_id_is_rejected(self):
        """비우면 orchestrator 가 스텁 태그로 비교해 인증이 거짓 통과한다(#417 4절)."""
        message = T.tag_message(1.5, 1, "amr_1/base_link", "bed_a1", "")
        self.assertTrue(any("tag_id" in p for p in B.validate(B.TAG_READS, message)))

    def test_kind_and_status_are_strings(self):
        """정수는 .msg 상수가 바뀌면 조용히 다른 뜻이 된다(비전 9/21)."""
        message = T.tag_message(1.5, 1, "amr_1/base_link", "bed_a1", "pt-1001")
        self.assertIsInstance(message["kind"], str)
        self.assertIsInstance(message["status"], str)
        self.assertIn(message["kind"], B.TAG_KINDS)
        self.assertIn(message["status"], B.TAG_STATUSES)


class EmptyIsStillAMessage(unittest.TestCase):
    def test_no_detections_is_an_empty_list_not_a_missing_message(self):
        """"검출 0건" 으로 팔이 빨리 닫는다. 안 내면 시한까지 기다린다(비전 9/21)."""
        message = T.pouches_message(1.5, 1, "amr_1/base_link", [])
        self.assertEqual(B.validate(B.POUCHES, message), [])
        self.assertEqual(message["detections"], [])

    def test_the_epoch_travels_so_the_adapter_can_drop_stale_reads(self):
        """리셋 뒤 옛 검출로 집으면 안 된다. PouchDetection 에 epoch 자리가 없어 어댑터가 건다."""
        self.assertEqual(T.pouches_message(1.5, 7, "f", [])["epoch"], 7)
        self.assertEqual(T.tag_message(1.5, 7, "f", "bed_a1", "pt-1")["epoch"], 7)


class CabinetTruth(unittest.TestCase):
    """보관함 참값. **이벤트가 아니라 자세로 본다.**

    지금 `/evaluator/cabinet` 의 작성자는 `stub_sim` 하나이고, 그것은 팔의 `POUCH_PLACED` **주장**을 받아
    주문 풀의 기대 cabinet 으로 `present=true` 를 지어낸다(#444 F03) — **참값이 아니다.**
    여기서는 봉투가 실제로 그 부피 안에 있는지만 본다. 상판 칸의 `in_slot` 과 같은 AABB 판정이다.
    """

    CAB = (12.80, 0.30, 0.70)
    SIZE = (0.36, 0.36)

    def test_a_pouch_resting_on_top_counts(self):
        """지금 보관함은 **속이 찬 상자**라 봉투가 윗면에 얹힌다. 열린 칸이 되면 칸 부피로 바뀐다."""
        self.assertTrue(T.in_cabinet((12.80, 0.30, 0.705), self.CAB, self.SIZE))

    def test_sliding_off_makes_it_false(self):
        """#444 F04: 한 번 true 가 영구 성공이 되면 안 된다. **true→false 도 낸다.**"""
        self.assertFalse(T.in_cabinet((13.10, 0.30, 0.705), self.CAB, self.SIZE))

    def test_something_below_the_top_face_is_not_in_it(self):
        self.assertFalse(T.in_cabinet((12.80, 0.30, 0.60), self.CAB, self.SIZE))

    def test_the_message_validates(self):
        message = T.cabinet_message(1.5, 1, "bed_a1/cabinet", "ord-0001", True)
        self.assertEqual(B.validate(B.CABINET, message), [])

    def test_an_empty_cabinet_id_is_rejected(self):
        message = T.cabinet_message(1.5, 1, "", "", False)
        self.assertTrue(any("cabinet_id" in p for p in B.validate(B.CABINET, message)))

    def test_an_empty_cabinet_is_a_message_too(self):
        """안 내면 "아직 안 놨다" 와 "센서가 죽었다" 가 구별되지 않는다."""
        self.assertEqual(B.validate(B.CABINET, T.cabinet_message(1.5, 1, "bed_a1/cabinet", "", False)), [])

    def test_it_is_latched_so_a_late_subscriber_sees_it(self):
        """event_logger 가 늦게 붙어도 지난 값을 봐야 한다(stub 이 쓰던 자리와 같다)."""
        self.assertEqual(B.QOS[B.CABINET][1], "transient_local")

    def test_the_stage_reads_poses_not_events(self):
        source = (STANDALONE / "pharmacy_stage.py").read_text()
        self.assertIn("sensorlib.in_cabinet(", source)
        self.assertIn("pool_objects[index].get_world_pose()", source)


class Rates(unittest.TestCase):
    def test_the_pouch_rate_fits_the_arms_detection_age(self):
        """팔의 detection_max_age_s 는 1 s 다."""
        self.assertGreaterEqual(T.POUCHES_HZ, 2.0)

    def test_the_tag_rate_is_continuous_not_on_change(self):
        """변할 때만 내면 한 번 놓쳤을 때 못 살아난다."""
        self.assertGreater(T.TAG_READS_HZ, 0.0)


class StageWiring(unittest.TestCase):
    """스테이지 배선. Isaac 을 띄우지 않는다(인자·검증·소스만 본다)."""

    def setUp(self):
        import pharmacy_stage

        self.stage = pharmacy_stage
        self.source = (STANDALONE / "pharmacy_stage.py").read_text()

    def test_it_is_off_unless_asked(self):
        self.assertFalse(self.stage.parse_args([]).sim_sensors)
        self.assertFalse(self.stage.parse_args(["--preset", "emptyworld-loop"]).sim_sensors)

    def test_it_needs_the_json_bridge_and_the_order_pool(self):
        problems = self.stage.validate(self.stage.parse_args(["--sim-sensors"]))
        self.assertTrue(any("--mode ros" in p for p in problems), problems)
        self.assertTrue(any("--order-pool" in p for p in problems), problems)

    def test_two_patients_in_one_bed_refuse_startup(self):
        """fail-closed: 어느 인식표를 낼지 모르는 채로 하나를 고르면 인증이 조용히 틀린다."""
        import tempfile

        text = ("- {order_id: ord-0001, patient_id: \"1001\", item_id: drug-amox, bed: bed_a1}\n"
                "- {order_id: ord-0002, patient_id: \"1002\", item_id: drug-ibu, bed: bed_a1}\n")
        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as handle:
            handle.write(text)
            path = handle.name
        args = self.stage.parse_args(["--sim-sensors", "--mode", "ros", "--order-pool", path])
        problems = self.stage.bed_patient_problems(args)
        self.assertTrue(any("more than one patient" in p for p in problems), problems)

    def test_the_real_pool_is_accepted(self):
        pool = Path(__file__).resolve().parents[2] / "src/rokey_p3_orchestrator/config/order_pool.yaml"
        if not pool.is_file():
            self.skipTest("주문 풀이 없다")
        args = self.stage.parse_args(["--sim-sensors", "--mode", "ros", "--order-pool", str(pool)])
        self.assertEqual(self.stage.bed_patient_problems(args), [])

    def test_the_refusals_carry_a_marker_word(self):
        """프로필이 "설정 오류" 와 "장면 결함" 을 가를 수 있어야 한다(통합&정비 9/21)."""
        for problem in self.stage.validate(self.stage.parse_args(["--sim-sensors"])):
            self.assertTrue(problem.startswith("sim_sensors config error:"), problem)

    def test_the_ready_line_always_prints(self):
        """`timeline_event type=PLAY` 는 스폰·센서 전에 나오고 `ur5 spawn_settled` 는 IK 가 풀려야 나온다.

        둘 다 준비 줄로 못 쓴다. `stage ready` 는 조각이 실패해도 나온다 — 루프 직전, 조건 밖이다.
        """
        marker = '        log(f"stage ready ur5='
        self.assertIn(marker, self.source, "준비 줄이 없거나 더 깊이 들여쓰여 있다(조건 안이다)")
        # `start mode=` 줄과 같은 깊이여야 조건 밖이다 — 그 줄은 루프 직전에 언제나 나온다.
        self.assertIn('        log(f"start mode=', self.source)

    def test_the_sensor_topics_match_every_other_isaac_publish(self):
        """실습27(9/21): best_effort 로 냈다가 어댑터(RELIABLE 구독)와 **호환되지 않아 한 건도 못 갔다.**

        best_effort 발행은 RELIABLE 구독자를 **조용히** 끊는다 — WARN 한 줄이고 증상은 "검출이 안 온다" 다.
        RELIABLE 발행은 양쪽 구독자를 다 받는다. 그래서 **다른 `/isaac/*` 와 같은 값**으로 묶는다.
        """
        from p3sim import bridge as bridgemod

        others = {reliability for topic, (reliability, _d, _depth) in bridgemod.QOS.items()
                  if topic not in (bridgemod.POUCHES, bridgemod.TAG_READS)}
        self.assertEqual(others, {"reliable"}, "기존 /isaac/* 가 전부 reliable 이어야 이 비교가 뜻을 갖는다")
        for topic in (bridgemod.POUCHES, bridgemod.TAG_READS):
            reliability, durability, depth = bridgemod.QOS[topic]
            self.assertEqual(reliability, "reliable", topic)
            self.assertEqual((durability, depth), ("volatile", 1), topic)

    def test_the_frame_default_is_the_decided_name(self):
        """결정 47. 팔의 `arm_base_frame` 과 같은 이름이어야 팔이 변환 없이 쓴다."""
        self.assertEqual(self.stage.sensorlib_frame_default(), "amr_1/ur_arm_base_link")

    def test_tags_need_the_amr(self):
        """AMR 이 없으면 "서 있는 침상" 이 없다. 아무것도 안 내는 편이 낫다."""
        self.assertIn("if sensors_on and amr is not None and now >= next_tags:", self.source)

    def test_cabinets_report_every_order_inside(self):
        """campaign 1 attempt 6: 보관함마다 첫 주문에서 `break` 해 C2 테이블 3봉투 중 하나만 냈다."""
        start = self.source.index("def cabinet_payloads():")
        body = self.source[start:self.source.index("def tag_payload():", start)]
        self.assertIn("sensorlib.cabinet_updates(", body)
        self.assertNotIn("break", body)

    def test_a_zone_without_a_patient_publishes_nothing(self):
        """풀에 없는 침상 앞에서는 아무것도 안 낸다 → 팔이 시한까지 기다려 UNREADABLE 이 된다.

        빈 `tag_id` 를 내면 orchestrator 가 스텁 태그로 비교해 인증이 **거짓 통과**한다(비전 #417 4절).
        그래서 이 줄 뒤에는 메시지를 만드는 코드가 오면 안 된다.
        """
        guard = self.source.index("if read is None:")
        end = self.source.index("return None", guard)
        # 판정 줄과 `return None` **사이**만 본다. 그 뒤는 성공 경로라 `tag_message` 가 있는 것이 맞다.
        self.assertNotIn("sensorlib.tag_message(", self.source[guard:end],
                         "안 내기로 한 자리에서 메시지를 만들고 있다")

    def test_the_silence_says_why(self):
        """**안 내는 것은 맞지만 조용하면 안 된다.** lap8 이 ⑥ 도착 뒤 ⑦ AUTH_FAIL 로 닫혔는데
        스캔 줄이 없어 거리인지 yaw 인지 환자 표인지 로그로 갈리지 않았다 — 슬롯 한 번이 그렇게 갔다.
        """
        self.assertIn("tag_reads none base=", self.source)
        self.assertIn("sensorlib.nearest_zone_diagnosis(", self.source)


    def test_the_slot_centres_are_read_live_not_from_the_build(self):
        """K2b 로 상판이 베이스 위로 가면 빌드 값과 지금 자리가 갈린다.

        지금은 상판이 월드 고정이라 두 값이 같아 **거동이 안 바뀐다.** 그때 가서 고치면 이미
        "AMR 이 움직인 만큼 틀린" 검출이 나간 뒤다 — 조회 실패가 아니라 조용히 틀린 값이다.
        """
        self.assertIn("cell.slot_centres()", self.source)
        self.assertNotIn("cell.slots if cell is not None", self.source)
        cell_source = (STANDALONE / "p3sim/ur5_cell.py").read_text()
        self.assertIn("def slot_centres(self):", cell_source)
        self.assertIn("return list(self.slots)", cell_source)  # 못 읽으면 물러난다

    def test_the_combined_arm_base_is_not_a_subtraction(self):
        """합본의 밑동은 **움직이고 축이 `Rz(pi)`** 다. 받침대처럼 뺄셈만 하면 안 된다.

        회차 lap2(9/21): 검출값이 받침대 회차(27b)와 **소수 셋째 자리까지 같았다.** 프레임 이름만 합본
        것이라 아무도 못 알아챘고, 팔은 그 값으로 엉뚱한 데를 짚었다. 이름이 맞으면 값도 맞다고 읽힌다.
        """
        self.assertIn("amr.world_to_arm_base(world)", self.source)
        base_source = (STANDALONE / "p3sim/amr_base.py").read_text()
        self.assertIn("def world_to_arm_base(", base_source)
        # 회전을 실제로 푼다 — 뺄셈만이면 yaw 가 안 들어간다.
        body = base_source[base_source.index("def world_to_arm_base("):base_source.index("def apply_arm_positions(")]
        self.assertIn("math.atan2", body)
        self.assertIn("math.cos(-yaw)", body)

    def test_the_pedestal_path_still_subtracts(self):
        """받침대는 월드 고정이고 축이 나란해서 뺄셈이 맞다. 두 길이 갈라진 것이 맞다."""
        self.assertIn("sensorlib.to_base(world, args.ur5_base)", self.source)

    def test_a_missing_frame_drops_the_detection(self):
        """못 읽으면 **안 낸다.** 틀린 좌표를 내는 것보다 안 내는 것이 낫다."""
        self.assertIn("if in_base is None:\n                        continue", self.source)

    def test_the_moving_deck_is_transformed_every_time(self):
        """합본에서는 상판이 **실제로 움직인다.** 빌드 때 세계 좌표를 굳히면 AMR 이 간 만큼 조용히 틀린다."""
        self.assertIn("amr.slots_in_world(amr_slots)", self.source)
        base_source = (STANDALONE / "p3sim/amr_base.py").read_text()
        self.assertIn("def slots_in_world(", base_source)
        self.assertIn("return list(local_slots)", base_source)  # 못 읽으면 로컬로 물러난다

    def test_only_what_is_really_in_a_zone_is_reported(self):
        self.assertIn("sensorlib.in_belt_end(", self.source)
        self.assertIn("sensorlib.in_slot(", self.source)

    def test_the_quaternion_order_is_converted(self):
        """Isaac 은 (w, x, y, z), 메시지는 (x, y, z, w) 다. 섞으면 자세가 조용히 틀린다."""
        self.assertEqual(T.wxyz_to_xyzw((1.0, 0.0, 0.0, 0.0)), (0.0, 0.0, 0.0, 1.0))
        self.assertEqual(T.wxyz_to_xyzw((0.0, 0.0, 0.0, 1.0)), (0.0, 0.0, 1.0, 0.0))
        self.assertIn("sensorlib.wxyz_to_xyzw(quat)", self.source)


class AgreedWithTheOtherSessions(unittest.TestCase):
    """세션 사이에 **말로** 정한 값을 상대 코드에서 읽어 대조한다(#435).

    9/21 에 같은 모양으로 세 번 틀렸다 — 두 쪽이 각자 맞다고 믿는 값이 달랐고 증상은 전부 "조용히 안 된다"
    였다(QoS 는 실습27 을 기동 전 확인에서 멈춰 세웠다). 두 벌을 각자 지키는 것으로는 **두 벌이 어긋나는 것**을
    아무도 못 본다. `test_clearance.py` 가 이미 쓰는 방식(상대 정의를 직접 임포트)을 따른다.

    상대 패키지가 없으면 건너뛴다 — 이 저장소 밖에서도 sim/tests 는 돌아야 한다.
    """

    SRC = Path(__file__).resolve().parents[2] / "src"

    def load(self, package, module):
        path = self.SRC / package
        if not path.is_dir():
            self.skipTest(f"{package} 가 없다")
        sys.path.insert(0, str(path))
        try:
            return __import__(f"{package}.{module}", fromlist=[module])
        except ImportError as error:
            self.skipTest(f"{package}.{module} 를 못 읽는다: {error}")
        finally:
            sys.path.remove(str(path))

    def test_the_tag_id_matches_the_orchestrators_own_builder(self):
        """`pt-` 접두를 양쪽이 각자 붙인다 — 두 벌이다. 어긋나면 인증이 전부 AUTH_FAIL 이고,
        **양쪽 다 유효한 문자열이라 값만 보는 시험으로는 안 잡힌다.**"""
        pool = self.load("rokey_p3_orchestrator", "order_pool")
        self.assertEqual(T.patient_tag("1001"), pool.patient_tag_id("1001"))
        self.assertEqual(T.station_tag("station_a"), pool.STATION_PREFIX + "station_a")

    def test_the_epoch_the_sensors_carry_is_the_one_reset_advances(self):
        """어댑터가 **`epoch` 이 어긋나면 버린다.** 그러려면 내가 싣는 값이 리셋마다 실제로 올라야 한다.

        안 오르면 그쪽 필터가 아무것도 못 거르고, 리셋 뒤 옛 검출로 집는 일이 **조용히** 생긴다.
        여기서는 "센서가 스테이지의 epoch 을 그대로 싣는다" 와 "리셋이 그 값을 올린다" 를 본다.
        """
        source = (STANDALONE / "pharmacy_stage.py").read_text()
        # 센서 둘 다 state["epoch"] 을 싣는다 — 따로 세는 값이 아니다.
        self.assertIn('sensorlib.pouches_message(sim_now(), state["epoch"]', source)
        self.assertIn('sensorlib.tag_message(sim_now(), state["epoch"]', source)
        # 리셋이 그 값을 요청받은 epoch 으로 옮긴다.
        self.assertIn('state["epoch"] = epoch', source)
        # 그리고 메시지는 그 값을 그대로 낸다(따로 가공하지 않는다).
        self.assertEqual(T.pouches_message(0.0, 7, "f", [])["epoch"], 7)
        self.assertEqual(T.tag_message(0.0, 7, "f", "bed_a1", "pt-1")["epoch"], 7)

    def test_the_first_epoch_is_never_zero(self):
        """계약 4절: epoch 은 1 부터다. 0 은 `/events` 에 stale 로 닿는다."""
        from p3sim import belt as beltlib

        self.assertEqual(beltlib.FIRST_EPOCH, 1)

    def test_the_pouch_rate_beats_the_arms_detection_age(self):
        """팔은 `detection_max_age_s` 보다 오래된 검출을 버린다. 주기가 그보다 길면 **늘 버려진다.**"""
        readme = (self.SRC / "rokey_p3_manipulation/README.md")
        if not readme.is_file():
            self.skipTest("팔 README 가 없다")
        import re

        found = re.search(r"detection_max_age_s`\(`([0-9.]+)`", readme.read_text())
        self.assertIsNotNone(found, "팔 README 에서 detection_max_age_s 를 못 읽었다")
        max_age = float(found.group(1))
        period = 1.0 / T.POUCHES_HZ
        self.assertLess(period, max_age / 2.0,
                        f"주기 {period:.3f} s 가 팔의 검출 유효기간 {max_age} s 의 절반보다 길다")


if __name__ == "__main__":
    unittest.main()


class CabinetUpdates(unittest.TestCase):
    """9/25 campaign 1 attempt 6(#240 5824830092): C2 테이블 3봉투 중 ord-0005 만 present 로 남았다."""

    def test_every_order_on_one_table_is_reported(self):
        updates, entered, seen = T.cabinet_updates(["ord-0005", "ord-0006", "ord-0007"], set())
        self.assertEqual([("ord-0005", True), ("ord-0006", True), ("ord-0007", True)], updates)
        self.assertEqual(["ord-0005", "ord-0006", "ord-0007"], entered)
        self.assertEqual({"ord-0005", "ord-0006", "ord-0007"}, seen)

    def test_a_pouch_that_slips_out_gets_one_false(self):
        updates, entered, _seen = T.cabinet_updates(["ord-0005"], {"ord-0005", "ord-0006"})
        self.assertEqual([("ord-0005", True), ("ord-0006", False)], updates)
        self.assertEqual([], entered)
        self.assertEqual([("ord-0005", False)], T.cabinet_updates([], {"ord-0005"})[0])   # 빈 줄 없이 false 만

    def test_an_empty_cabinet_is_one_blank_false_like_before(self):
        self.assertEqual(([("", False)], [], set()), T.cabinet_updates([], set()))
