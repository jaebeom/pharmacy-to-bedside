"""빈월드의 경로 경유점. Isaac 없음.

주행 routes.py 스키마(#407, 9/21). 값이 아니라 **관계**를 잡는다: 모든 쌍의 끝이 zones 에 있는가,
선분이 고정 상자에서 AMR 반폭 + 여유만큼 떨어져 있는가, 왕복이 서로의 역순인가.

여기서 계산하는 여유는 **정지 기하**다. 추종 오차도 위치 추정 오차도 들어 있지 않다(주행 9/21) —
실제 최소 이격은 L3 에서 잰다. 이 시험이 지키는 것은 "장면이 움직였는데 경로가 안 따라왔다" 뿐이다.

    python3 -m unittest discover -s sim/tests -p 'test_full_loop_routes.py'
"""

import math
import sys
import unittest
from pathlib import Path

STANDALONE = Path(__file__).resolve().parents[1] / "standalone"
sys.path.insert(0, str(STANDALONE))

from p3sim import layout as L  # noqa: E402

#: 필요 여유는 layout 이 계산한다: 회전 외접 반경(실측 footprint) + 추종 여유(주행) + 안전 여유.
#: 여기서 더 더하지 않는다 — 두 곳에 여유를 적으면 어느 쪽이 근거인지 알 수 없게 된다.
def required():
    return L.amr_required_clearance()


def service_skip():
    """접안 구간 — 주행 여유 대신 접안 여유로 본다. `dock_clearance` 시험이 그 구간을 맡는다.

    적재 자리와 **침상 정차 자리** 둘 다다. 침상은 보관함에서 0.70 m 에 서야 팔이 닿고, 이동 차선에서
    거기로 들어가는 **마지막 직선**이 접안 구간이다. 차선을 달리는 구간은 그대로 주행 여유로 본다.
    """
    zones = L.full_loop_zones()
    skip = [(zones[name][:2], L.SERVICE_RADIUS) for name in L.SERVICE_POSES if name in zones]
    skip += [(zones[name][:2], L.WARD["travel_offset"] + 0.25) for name in L.bed_zones()]
    return skip


def fixed_boxes():
    """빈월드 장면의 **모든** 고정 상자. 조제실 것까지 넣는다.

    복도·병실·도크만 보면 시험이 거짓으로 통과한다 — 실제로 제일 가까운 것은 조제실의 벨트 벽이었다
    (9/21: 복도만 볼 때 1.000 m 였던 자리가 전체를 보면 0.550 m 였다).
    """
    import pharmacy_stage

    args = pharmacy_stage.parse_args(["--preset", "emptyworld-loop"])
    return [box for box in pharmacy_stage.room(args)["boxes"] if box.kind == "fixed"]


def ur5_cell_boxes():
    """UR5 적재 셀의 상자(받침대·상판). `room()` 의 상자 목록에 **없다** — ur5_cell 이 따로 만든다.

    **이것들은 주행 여유 규칙(`amr_required_clearance`)에서 뺀다.** 예외이고, 이유는 이렇다:
    적재 자리는 UR5 가 봉투를 놓는 자리라 **팔 길이 안에 들어와야** 한다. 그런데 받침대가 곧 UR5 의 자리다.
    "받침대에서 0.936 m 떨어져라" 와 "UR5 기준 0.817 m 안에 있어라" 는 동시에 만족될 수 없다.
    그래서 이 상자들에는 다른 규칙을 적용한다 — 아래 `LoadingCell` 이 그것이다. 뺀 것을 안 보는 것이 아니다.
    """
    from p3sim import ur5_cell as U
    import pharmacy_stage

    args = pharmacy_stage.parse_args(["--preset", "emptyworld-loop"])
    bx, by, _bz = args.ur5_base
    px, py = U.pedestal_footprint(tuple(args.ur5_pedestal_size))
    ph = U.pedestal_height(args.ur5_pedestal_height, args.ur5_base[2])
    pedestal = L.Box("Pedestal", (bx, by, ph / 2.0), (px, py, ph), L.COLORS["carriage"], "fixed")
    deck, _slots = L.deck_boxes(tuple(args.deck_center), args.deck_count,
                               pharmacy_stage.ROOM["deck_slot_size"], pharmacy_stage.ROOM["deck_wall"])
    return [pedestal, *deck]


class Schema(unittest.TestCase):
    def setUp(self):
        self.pairs = L.routes()
        self.zones = L.zones_yaml()["zones"]

    def test_both_ends_are_zone_ids_that_exist(self):
        """없는 zone 이면 주행이 로드에서 거부한다(주행 9/21)."""
        for source, target in self.pairs:
            self.assertIn(source, self.zones, f"{source} -> {target}")
            self.assertIn(target, self.zones, f"{source} -> {target}")

    def test_a_pair_is_directed(self):
        """방향이 다르면 다른 쌍이다. 같은 쌍이 두 번 나오면 안 된다."""
        self.assertEqual(len(set(self.pairs)), len(self.pairs))

    def test_the_return_leg_is_the_reverse_of_the_shared_part(self):
        """빈월드는 **복도·차선 구간이** 왕복 같다. 한쪽만 고치면 돌아오는 길이 벽을 지난다.

        9/21 전까지는 통째로 뒤집은 것과 같았는데, 나가는 길에 **복도 중심선으로 내려서는 경유점**이
        하나 붙으면서 갈렸다. 돌아오는 길의 끝은 `dock_1` 이고 그것이 이미 중심선 위에 있어 내려설
        자리가 필요 없다 — 양끝이 달라진 것이지 가운데가 달라진 것이 아니다. 그래서 **가운데만** 묶는다.
        (양끝을 포함한 여유는 `Clearance` 가 모든 쌍에 대해 따로 본다.)
        """
        corridor_y = L.CORRIDOR["centre_y"]
        load_x = L.full_loop_zones()["load"][0]
        for bed in L.bed_zones():
            out = self.pairs[("load", bed)]
            back = self.pairs[(bed, "dock_1")]
            self.assertEqual(out[0], (load_x, corridor_y), f"{bed}: 내려서는 경유점이 첫 자리여야 한다")
            self.assertEqual(back, list(reversed(out[1:])), bed)

    def test_every_bed_leg_goes_through_the_travel_lane(self):
        """정차선으로 곧장 달리면 보관함 줄과 0.12 m 로 나란히 간다(주행 9/21 ②)."""
        zones = L.full_loop_zones()
        lane_y = zones[L.bed_zones()[0]][1] - L.WARD["travel_offset"]
        for (source, target), waypoints in self.pairs.items():
            if source not in L.bed_zones() and target not in L.bed_zones():
                continue
            self.assertTrue(waypoints, f"{source} -> {target}: 직선이면 보관함에 붙어 달린다")
            self.assertTrue(any(abs(point[1] - lane_y) < 1e-6 for point in waypoints),
                            f"{source} -> {target}: 차선을 안 지난다")

    def test_the_last_leg_into_a_bed_is_one_straight_line(self):
        """꺾이는 자리를 틈 안에 두지 않는다 — 경유점 옆 오차가 0.065 다(주행 9/21)."""
        zones = L.full_loop_zones()
        for bed in L.bed_zones():
            last = self.pairs[("load", bed)][-1]
            self.assertAlmostEqual(last[0], zones[bed][0], places=6, msg=bed)

    def test_every_order_destination_can_be_reached_from_load(self):
        """적재 뒤 첫 침상이 트립의 시작이다(주행 15쌍의 2번)."""
        for bed in L.bed_zones():
            self.assertIn(("load", bed), self.pairs)

    def test_waypoints_are_xy_only(self):
        """yaw 는 두지 않는다 — 목표 yaw 는 zones 에서 온다(주행 9/21)."""
        for waypoints in self.pairs.values():
            for point in waypoints:
                self.assertEqual(len(point), 2, point)


class Clearance(unittest.TestCase):
    """손으로 계산한 여유 표를 시험이 대신 계산한다(작전 9/21). 장면이 또 움직이면 여기서 걸린다."""

    def setUp(self):
        self.pairs = L.routes()
        self.zones = L.full_loop_zones()
        self.boxes = fixed_boxes()

    def clearance(self, source, target):
        waypoints = self.pairs[(source, target)]
        return L.route_clearance(waypoints, self.zones[source][:2], self.zones[target][:2], self.boxes,
                                 skip_near=service_skip())

    def test_every_route_clears_the_amr_half_width(self):
        need = required()
        for source, target in self.pairs:
            gap = self.clearance(source, target)
            self.assertGreater(gap, need, f"{source} -> {target}: 여유 {gap:.3f} m < {need:.3f} m")

    def test_the_straight_line_to_a_bed_does_not_clear_the_corridor_wall(self):
        """경유점이 왜 필요한지. 직선은 복도 남쪽 벽 모서리를 필요 여유보다 가깝게 지난다.

        이 여유가 필요값을 넘게 되면 경유점을 지워도 된다는 뜻이다 — 그때 이 시험이 알려준다.
        """
        need = required()
        bed = L.WARD["beds"][0][0]
        straight = L.route_clearance([], self.zones["load"][:2], self.zones[bed][:2], self.boxes,
                                     skip_near=service_skip())
        self.assertLess(straight, need, f"직선 여유가 {straight:.3f} m 다 — 경유점을 다시 보라")

    def test_an_empty_pair_really_is_straight(self):
        """`waypoints: []` 는 따져 본 결과여야 한다. 안 따져 본 것과 구별되게."""
        need = required()
        for (source, target), waypoints in self.pairs.items():
            if waypoints:
                continue
            gap = self.clearance(source, target)
            self.assertGreater(gap, need, f"{source} -> {target}: 직선인데 여유가 {gap:.3f} m 다")


class DockingAtTheLoadPose(unittest.TestCase):
    """적재 자리는 **벨트 끝에 붙어야 팔이 닿는다.** 주행 여유(0.936)를 요구할 수 없다.

    받침대 셀에 쓴 접안 규칙과 같은 모양이지만 **값도 이유도 다르다**: 저쪽은 팔이 기둥에 걸리는 문제고
    이쪽은 AMR 몸체가 고정물에 닿는 문제다. 틈 0.10 은 주행 도착 오차 0.02 + 여유다(작전 9/21).

    ⚠️ 이 틈이 성립하는 것은 **빈월드 추측항법에 드리프트가 없기 때문**이다. 심월드에서 Nav2·AMCL 로
    갈아 끼우면 위치추정 오차만으로 0.10 이 사라진다(주행 9/21) — 심월드 배치에 그대로 옮기지 않는다.
    """

    def setUp(self):
        self.zones = L.full_loop_zones()
        # 받침대 셀은 합본 구성에서 **안 만들어진다**(위 클래스 참조). 그래서 여기 상자에 없다.
        self.boxes = fixed_boxes()
        self.aabb = L.amr_aabb(self.zones["load"])

    def test_the_parked_body_clears_everything(self):
        for box in self.boxes:
            dx, dy, dz = L.box_gap(self.aabb, box)
            if dz > 0.0:
                continue   # 몸체보다 위다 — 밑으로 지나간다
            self.assertGreaterEqual(max(dx, dy), L.DOCK_CLEARANCE,
                                    f"{box.name}: 틈 {max(dx, dy):.4f} < {L.DOCK_CLEARANCE}")

    def test_the_belt_end_pouch_is_within_reach(self):
        """합본 팔은 AMR 위 z 0.28 이다 — 받침대(0.90)보다 62 cm 낮아 도달 예산이 완전히 다르다."""
        import pharmacy_stage
        from p3sim import amr_base as A

        args = pharmacy_stage.parse_args(["--preset", "emptyworld-loop"])
        belt_start = pharmacy_stage.room(args)["belt_start"]
        end_x = 1.35 + args.belt_length
        pouch = (end_x - args.end_zone, belt_start[1], 0.75 + args.pouch_size[2] / 2.0)
        # **AMR 중심이 아니라 어깨의 자리**로 잰다. 9/21 확정안에서 팔이 몸체 뒤끝으로 갔고(로컬 −0.35)
        # 정차 자리는 그만큼 앞으로 밀렸다 — 둘 중 하나만 반영하면 0.35 가 조용히 틀린다.
        # 정차 yaw 는 0 이라 로컬 x 가 월드 x 다.
        x, y, _z, yaw = self.zones["load"]
        self.assertAlmostEqual(yaw, 0.0, places=9, msg="yaw 가 0 이 아니면 아래 덧셈이 성립하지 않는다")
        shoulder = (x + A.ARM_MOUNT_LOCAL[0], y + A.ARM_MOUNT_LOCAL[1], A.shoulder_world_z())
        reach = math.dist(shoulder, pouch)
        self.assertLess(reach, 0.817, f"도달 밖이다: {reach:.3f}")
        self.assertLess(reach / 0.817, 0.92, f"편 길이의 {reach / 0.817:.0%} — 오차가 커지는 구간이다")

    def test_the_stop_yaw_matches_the_corridor_so_nothing_rotates_into_the_gap(self):
        """주행 9/21: 제자리 회전은 모서리를 0.622 m 까지 내민다 — 0.10 틈이면 닿는다.

        적재 자리의 yaw 가 통로와 같으면 **돌지 않고 옆으로 밀어 넣는다**(베이스가 전방향이다).
        """
        self.assertAlmostEqual(self.zones["load"][3], 0.0, places=9)
        self.assertAlmostEqual(self.zones["dock_1"][3], 0.0, places=9)

    def test_the_service_radius_covers_the_parked_body(self):
        """경로 시험이 빼는 구간이 몸체보다 작으면 접안 자리가 주행 규칙에 걸린다."""
        length, _width = L.AMR_FOOTPRINT
        self.assertGreater(L.SERVICE_RADIUS, length / 2.0)


class Footprint(unittest.TestCase):
    """치수의 근거가 바뀌면 여기서 걸린다. 여유를 반폭으로 되돌리는 것이 제일 위험한 되돌림이다."""

    def test_the_bbox_is_the_measured_asset_not_a_placeholder(self):
        """ridgeback_ur5.usd 의 base_link 외형 bbox(박세준 #408 6.5절)."""
        length, width = L.AMR_BBOX
        self.assertAlmostEqual(length, 0.93251, places=5)
        self.assertAlmostEqual(width, 0.79320, places=5)

    def test_the_planning_footprint_is_never_smaller_than_the_body(self):
        """여유는 큰 쪽으로 잡는다(주행 9/21). 계획 footprint 가 실측보다 작아지면 Nav2 에서 통로가 모자란다.

        둘이 왜 다른지는 **확인하지 못했다** — 값을 맞추지 말고 이 관계만 지킨다.
        """
        for plan, measured in zip(L.AMR_FOOTPRINT, L.AMR_BBOX, strict=True):
            self.assertGreaterEqual(plan, measured)

    def test_the_requirement_uses_the_turn_radius_not_the_half_width(self):
        """접근 자리는 같은 자리에서 yaw 만 ±pi/2 로 돈다. 반폭으로 보면 회전에서 벽을 친다."""
        length, width = L.AMR_FOOTPRINT
        self.assertGreater(L.amr_turn_radius(), width / 2.0)
        self.assertGreater(L.amr_turn_radius(), length / 2.0)
        self.assertGreater(L.amr_required_clearance(), L.amr_turn_radius())

    def test_the_follower_allowance_is_the_drive_sessions_number(self):
        """주행 9/21 오후(PR #453 `400f706e`): 공차 0.05 + `v^2/2a` 0.10 + 한 주기 0.02 = 0.17.

        80 % 속도 지시로 가속 상한이 생기면서 0.065 에서 올랐다. **이 값은 주행이 정한다** —
        여기서 내가 줄이면 여유가 있는 것처럼 보이고 실제로는 꺾임에서 바깥으로 나간다.
        """
        self.assertAlmostEqual(L.FOLLOWER_ALLOWANCE, 0.17, places=6)

    def test_the_corridor_is_wide_enough_for_the_base_to_turn(self):
        need = 2.0 * L.amr_required_clearance()
        self.assertGreater(L.CORRIDOR["width"], need, f"복도 폭이 {need:.3f} m 보다 넓어야 한다")

    def test_the_stage_body_is_the_measured_bbox(self):
        """장면의 몸체는 **실제 크기**여야 접촉 관측이 뜻을 갖는다. 여유 쪽 값(계획 footprint)을 쓰면 안 된다."""
        from p3sim import amr_base as A

        self.assertEqual(A.body_size()[:2], tuple(L.AMR_BBOX))

    def test_the_turn_radius_comes_from_the_planning_footprint(self):
        """작은 쪽으로 여유를 잡으면 Nav2 로 갈아 끼울 때 통로가 모자란다(주행 9/21)."""
        self.assertAlmostEqual(L.amr_turn_radius(), L.amr_turn_radius(L.AMR_FOOTPRINT), places=9)
        self.assertGreater(L.amr_turn_radius(), L.amr_turn_radius(L.AMR_BBOX))


class ThePedestalCellAndTheAmrDoNotCoexist(unittest.TestCase):
    """적재 자리를 **AMR 합본 기준**으로 옮긴 뒤(작전 승인 9/21), 받침대 셀과는 같이 설 수 없다.

    옛 자리 (4.00, 0.55)는 받침대 UR5(조제실 옆 z 0.90)가 팔을 뻗는 자리였다. 합본 팔은 AMR 위 z 0.28 라
    **62 cm 낮아** 벨트 끝에 못 닿았고(회차 lap2: 1.24 m), 자리를 (3.40, 0.95)로 당겼다.
    그 자리는 받침대 기둥·상판과 겹친다 — 그래서 **두 구성은 배타적**이고, 스테이지가 그것을 강제한다.

    옛 시험(`LoadingCell`)은 "AMR 이 받침대 셀 옆에 선다" 를 보던 것인데, 그 조합이 이제 없다.
    지우는 대신 **왜 없는지**를 남긴다 — 값만 지우면 다음 사람이 되살린다.
    """

    def test_the_stage_refuses_to_build_both_arms(self):
        source = (STANDALONE / "pharmacy_stage.py").read_text()
        self.assertIn("if args.ur5 and not args.amr_combined:", source)
        self.assertIn("ur5 pedestal disabled reason=--amr-combined", source)

    def test_the_load_pose_is_now_inside_the_pedestal_cell(self):
        """겹친다는 것 자체를 기록한다 — 받침대 구성에서 이 자리를 쓰면 안 된다는 뜻이다."""
        aabb = L.amr_aabb(L.full_loop_zones()["load"])
        overlapping = [box.name for box in ur5_cell_boxes()
                       if max(L.box_gap(aabb, box)) < L.DOCK_CLEARANCE]
        self.assertTrue(overlapping, "안 겹치면 두 구성이 공존할 수 있다는 뜻이라 이 시험을 지워야 한다")


class LoadZone(unittest.TestCase):
    """적재 자리는 두 제약 사이에 있다: 조제실 벽에서 멀어야 하고, UR5 도달 거리 안이어야 한다."""


    def test_it_is_east_of_the_belt_end(self):
        """벨트 끝에서 +x 로 떨어진 자리다. 벨트 위로 올라가면 안 된다."""
        self.assertGreater(L.LOAD_OFFSET[0], 0.0)


class RoutesFileMatchesTheCode(unittest.TestCase):
    """저장된 routes.emptyworld.yaml 과 코드가 어긋나면 잡는다. PyYAML 없이 본문으로 대조한다."""

    PATH = Path(__file__).resolve().parents[2] / "src/rokey_p3_description/config/routes.emptyworld.yaml"

    def test_it_is_what_the_code_produces(self):
        self.assertTrue(self.PATH.is_file(), self.PATH)
        self.assertEqual(self.PATH.read_text(), L.routes_yaml_text())

    def test_every_ordered_pair_of_stop_poses_is_in_the_table(self):
        """**빠진 쌍은 조용히 직선이 된다**(주행 9/21). 빈 목록과 쌍 없음을 로더가 구별하지 못한다.

        한 바퀴 정상 흐름(dock→load→bed→dock)에 안 쓰이는 쌍도 쓰인다: 리셋 직후 첫 목표가 침상이면
        `dock_1 → bed_*` 가, 연속 배송이면 `bed_* → load` 가 그대로 쓰인다. 둘 다 복도를 무시하고
        병동까지 대각선이라 고정물을 지난다. 그래서 **정차 자리의 모든 순서쌍**을 적는다.
        """
        stops = ["load", "dock_1", *L.bed_zones()]
        pairs = L.routes()
        for source in stops:
            for target in stops:
                if source != target:
                    self.assertIn((source, target), pairs, f"{source} -> {target} 가 표에 없다")
        self.assertEqual(len(pairs), len(stops) * (len(stops) - 1))

    def test_every_pair_has_a_line_even_when_it_is_straight(self):
        """빈 쌍도 적는다 — 빼면 '안 따져 봤다' 와 구별되지 않는다(작전 9/21)."""
        text = self.PATH.read_text()
        for source, target in L.routes():
            self.assertIn(f"{{from: {source}, to: {target},", text)


if __name__ == "__main__":
    unittest.main()
