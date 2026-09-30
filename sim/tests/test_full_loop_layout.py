"""전 구간 한 바퀴(빈월드)의 복도·병상·도크 배치와 zone 자세. Isaac 없음.

K1 (작전 9/21, 재범 "구현부터"): 조제실 밖으로 복도·병상·보관함·도크를 상자로 얹는다. 치수는 전부 임시값이고
세준 USD 가 오면 값만 바뀐다 — 그래서 이 시험은 **값 자체가 아니라 관계**를 잡는다. AMR 이 지나갈 수 있는가,
접근 자리가 상자 안에 있지 않은가, zone 이름이 계약 3절 규칙인가.

    python3 -m unittest discover -s sim/tests -p 'test_[fmp]*.py'
"""

import math
import re
import sys
import unittest
from pathlib import Path

STANDALONE = Path(__file__).resolve().parents[1] / "standalone"
sys.path.insert(0, str(STANDALONE))

from p3sim import layout as L  # noqa: E402
from p3sim import zones as Z  # noqa: E402

#: 계약 3절·zones.yaml 의 구역 ID 규칙(rokey_p3_navigation/zones.py 의 정규식과 같은 뜻).
ZONE_ID = re.compile(r"^(pharm|load|dock_\d+|ward_[a-z]|station_[a-z]|room_[a-z]\d+|bed_[a-z]\d+)$")
#: AMR 이 지나려면 필요한 폭. 회전 외접 반경(실측 footprint, 박세준 #408) + 여유의 두 배다 —
#: 침상 접근 자리는 같은 자리에서 yaw 만 돌기 때문에 반폭이 아니라 회전 반경으로 봐야 한다.
AMR_WIDTH = 2.0 * L.amr_required_clearance()


def extent(box, axis):
    return (box.center[axis] - box.size[axis] / 2.0, box.center[axis] + box.size[axis] / 2.0)


def inside_xy(point, box):
    return all(abs(point[i] - box.center[i]) <= box.size[i] / 2.0 for i in (0, 1))


class Corridor(unittest.TestCase):
    def setUp(self):
        self.boxes, self.line = L.corridor_boxes()

    def test_two_walls_and_a_floor(self):
        kinds = {b.name: b.kind for b in self.boxes}
        self.assertEqual(kinds["CorridorFloor"], "visual")
        self.assertEqual(kinds["CorridorWallNorth"], "fixed")
        self.assertEqual(kinds["CorridorWallSouth"], "fixed")

    def test_walls_leave_more_than_the_amr_width(self):
        north = next(b for b in self.boxes if b.name == "CorridorWallNorth")
        south = next(b for b in self.boxes if b.name == "CorridorWallSouth")
        gap = extent(north, 1)[0] - extent(south, 1)[1]
        self.assertGreater(gap, AMR_WIDTH)

    def test_the_centre_line_runs_between_the_walls(self):
        north = next(b for b in self.boxes if b.name == "CorridorWallNorth")
        south = next(b for b in self.boxes if b.name == "CorridorWallSouth")
        for x, y in self.line:
            self.assertLess(y, extent(north, 1)[0])
            self.assertGreater(y, extent(south, 1)[1])
            self.assertTrue(extent(north, 0)[0] <= x <= extent(north, 0)[1])

    def test_it_starts_east_of_the_loading_area(self):
        """조제실 벽은 x 2.7, 적재 구역(UR5·상판)은 x 3.0-3.7 이다. 복도는 그 동쪽이어야 겹치지 않는다."""
        room = L.default_layout()
        deck_east = room["deck_center"][0] + 0.32 + room["deck_slot_size"][0] / 2.0
        self.assertGreater(L.CORRIDOR["origin_x"], max(room["wall_x"], deck_east))


class Ward(unittest.TestCase):
    def setUp(self):
        self.boxes, self.frames = L.ward_boxes()
        self.corridor, _line = L.corridor_boxes()

    def test_every_place_has_a_model_and_a_frame(self):
        """자리마다 상자를 둔다. 없는 상자는 여유 시험이 못 본다 — 통로가 비어 있는 것처럼 계산된다."""
        self.assertEqual(len(self.frames), len(L.bed_zones()))
        self.assertEqual(L.WARD["model_beds"], len(L.bed_zones()), "모형 없는 자리는 여유 시험의 사각이다")
        self.assertEqual(len(self.boxes), 3 * len(L.bed_zones()))

    def test_it_sits_beyond_the_corridor_so_no_wall_blocks_it(self):
        """병상을 복도 옆에 두면 복도 벽이 접근을 막는다. 끝 너머에 둔다."""
        corridor_end = max(extent(b, 0)[1] for b in self.corridor)
        for box in self.boxes:
            self.assertGreaterEqual(extent(box, 0)[0], corridor_end)

    def test_every_approach_pose_is_not_inside_any_box(self):
        """AMR 이 서는 자리다. 상자 안이면 설 수 없다."""
        for zone, poses in self.frames.items():
            for box in self.boxes + self.corridor:
                if box.kind != "fixed":
                    continue
                self.assertFalse(inside_xy(poses["bed"], box), f"{zone} 가 {box.name} 안이다")

    def test_the_approach_poses_share_one_aisle(self):
        """두 줄의 접근 자리가 한 통로에 모여야 AMR 이 복도 축에서 벗어나지 않는다."""
        ys = {round(poses["bed"][1], 6) for poses in self.frames.values()}
        self.assertEqual(len(ys), 1, f"통로가 갈라졌다: {ys}")

    def test_every_stop_yaw_is_the_corridor_yaw(self):
        """**기하가 yaw 0 을 강제한다**(주행 9/21): 회전하면 모서리가 중심에서 0.612 m 까지 나가는데
        보관함 면까지가 0.52 라 닿는다. 회전을 허용하려면 간격이 0.892 여야 하고 그러면 도달 밖이다.
        전방향 베이스라 돌지 않고 옆으로 밀어 넣는다."""
        for zone, poses in self.frames.items():
            self.assertAlmostEqual(poses["bed"][3], 0.0, places=9, msg=zone)

    def test_no_two_zones_share_the_same_pose(self):
        """자리와 방향이 모두 같으면 서로 다른 침상으로 갈 수 없다."""
        poses = [tuple(round(v, 6) for v in f["bed"]) for f in self.frames.values()]
        self.assertEqual(len(set(poses)), len(poses), poses)

    def test_there_is_room_to_leave_the_corridor_before_the_first_box(self):
        """복도 끝과 병실 사이에 AMR 이 통로로 내려설 자리가 있어야 한다.

        여기가 좁으면 경로가 복도 벽 모서리와 보관함 사이에 끼어 어떤 waypoint 로도 못 빠져나간다
        (주행 routes 쌍 검토 9/21: 여유 0.50 m 에서 0.15 m 까지 줄었던 자리다. 실측 footprint 로 바꾸니
        그 0.50 m 도 모자랐다 — 회전 외접 반경이 0.612 다.)
        """
        corridor_end = max(extent(b, 0)[1] for b in self.corridor)
        first_box = min(extent(b, 0)[0] for b in self.boxes)
        self.assertGreaterEqual(first_box - corridor_end, AMR_WIDTH, "복도를 빠져나올 자리가 없다")

    def test_the_tag_sits_above_the_cabinet(self):
        cabinet = next(b for b in self.boxes if b.name == "BedCabinet")
        tag = next(b for b in self.boxes if b.name == "BedTag")
        self.assertGreater(extent(tag, 2)[0], extent(cabinet, 2)[1])
        self.assertTrue(inside_xy(tag.center, cabinet))

    def test_the_cabinet_frame_is_its_top_face(self):
        """계약 3절의 `<zone>/cabinet` 은 놓는 면이다. 상자 중심이 아니다."""
        cabinet = next(b for b in self.boxes if b.name == "BedCabinet")
        first = L.bed_zones()[0]
        self.assertAlmostEqual(self.frames[first]["cabinet"][2], extent(cabinet, 2)[1], places=6)


class Dock(unittest.TestCase):
    def test_every_dock_has_a_frame_and_a_marker(self):
        boxes, frames = L.dock_boxes()
        self.assertEqual(len(boxes), L.DOCK["count"])
        self.assertEqual(len(frames), L.DOCK["count"])
        for name, box in zip(sorted(frames), boxes, strict=True):
            self.assertTrue(ZONE_ID.match(name), name)
            self.assertTrue(inside_xy(frames[name], box))

    def test_the_marker_is_flat_and_visual(self):
        boxes, _frames = L.dock_boxes()
        for box in boxes:
            self.assertEqual(box.kind, "visual")
            self.assertLess(box.size[2], 0.05)


class Zones(unittest.TestCase):
    def setUp(self):
        self.zones = L.full_loop_zones()

    def test_every_name_follows_the_contract_rule(self):
        for name in self.zones:
            head = name.split("/", 1)[0]
            self.assertTrue(ZONE_ID.match(head), name)

    def test_the_whole_loop_is_covered(self):
        """요청 → 적재 → 이송 → 전달 → 복귀 한 바퀴에 필요한 자리."""
        for name in ("load", "dock_1", "bed_a1", "bed_a1/cabinet", "bed_a1/tag"):
            self.assertIn(name, self.zones)

    def test_each_pose_is_x_y_z_yaw(self):
        for name, pose in self.zones.items():
            self.assertEqual(len(pose), 4, name)
            for value in pose:
                self.assertIsInstance(value, float)

    def test_load_sits_by_the_belt_end(self):
        """적재 자리는 UR5 가 봉투를 올려 두는 상판 옆이다."""
        room = L.default_layout()
        belt_end_x = 1.35 + room["belt_length"]
        self.assertGreater(self.zones["load"][0], belt_end_x - 0.5)
        self.assertLess(self.zones["load"][0], L.CORRIDOR["origin_x"])

    def test_the_scene_parameters_are_the_only_source(self):
        """zones 값은 레이아웃에서 나온다. 두 곳에 손으로 적으면 어긋난다."""
        _boxes, frames = L.ward_boxes()
        for zone, poses in frames.items():
            self.assertEqual(self.zones[zone], poses["bed"])
            self.assertEqual(self.zones[f"{zone}/cabinet"], poses["cabinet"])
            self.assertEqual(self.zones[f"{zone}/tag"], poses["tag"])
        _dboxes, dframes = L.dock_boxes()
        self.assertEqual(self.zones["dock_1"], dframes["dock_1"])


class ZonesYaml(unittest.TestCase):
    """zones.yaml 과 같은 모양의 월드별 파일. 기본 zones.yaml 은 심월드 자리라 건드리지 않는다."""

    def setUp(self):
        self.doc = L.zones_yaml()

    def test_frame_and_shape(self):
        self.assertEqual(self.doc["frame"], "map")
        for name, entry in self.doc["zones"].items():
            self.assertTrue(ZONE_ID.match(name), name)
            for key in ("kind", "x", "y", "yaw", "tol_xy", "tol_yaw"):
                self.assertIn(key, entry, name)

    def test_tolerances_are_positive(self):
        """0 이면 fleet 가 arrived 를 영원히 안 낸다(주행 9/21)."""
        for name, entry in self.doc["zones"].items():
            self.assertGreater(entry["tol_xy"], 0.0, name)
            self.assertGreater(entry["tol_yaw"], 0.0, name)

    def test_belt_end_frame_sits_on_the_belt_top_at_the_stage_belt_end(self):
        """팔의 벨트 관측 자세(`belt_view_frame`)가 쓰는 프레임. 스테이지 belt_end_xy() 와 같은 자리여야 한다."""
        room = L.default_layout()
        end = self.doc["pharmacy"]["belt_end"]
        self.assertAlmostEqual(end["x"], 1.35 + room["belt_length"], places=4)
        self.assertAlmostEqual(end["z"], room["belt_top"], places=4)
        self.assertEqual((end["x"], end["y"]), L.BELT_END_XY)
        self.assertEqual(end["yaw"], 0.0)

    def test_bed_carries_cabinet_and_tag(self):
        bed = self.doc["zones"]["bed_a1"]
        for extra in ("cabinet", "tag"):
            self.assertEqual(sorted(bed[extra]), ["x", "y", "yaw", "z"])

    def test_values_come_from_the_layout(self):
        """파일로 나가는 값은 네 자리로 자른다(부동소수 잡음이 diff 를 더럽힌다). 그 자릿수까지만 같으면 된다."""
        zones = L.full_loop_zones()
        for name, entry in self.doc["zones"].items():
            self.assertAlmostEqual(entry["x"], zones[name][0], places=4)
            self.assertAlmostEqual(entry["y"], zones[name][1], places=4)
            self.assertAlmostEqual(entry["yaw"], zones[name][3], places=4)

    def test_slash_names_are_not_top_level_zones(self):
        """`bed_a1/cabinet` 은 zone 이 아니라 그 zone 의 하위 자세다."""
        self.assertNotIn("bed_a1/cabinet", self.doc["zones"])


class ZoneTfIsDiagnosticOnly(unittest.TestCase):
    """구역 TF 의 계약 단일 작성자는 주행의 `zones_tf` 다(계약 v1 59·436–442줄).

    스테이지가 같이 내면 한 변환의 작성자가 둘이 된다 — 계약 3절 위반이다. 실습23a 에서 스테이지가
    `P3Pharmacy` 아래로 내고 있던 것이 드러났다. 그래서 기본을 끄고, 켤 때도 부모를 `map` 으로 둔다.
    """

    def setUp(self):
        sys.path.insert(0, str(STANDALONE))
        import pharmacy_stage

        self.stage = pharmacy_stage
        self.source = (STANDALONE / "pharmacy_stage.py").read_text()

    def test_it_is_off_by_default_and_in_the_empty_world_preset(self):
        self.assertFalse(self.stage.parse_args([]).zones_tf)
        self.assertFalse(self.stage.parse_args(["--preset", "emptyworld-loop"]).zones_tf)

    def test_the_flag_turns_it_on(self):
        self.assertTrue(self.stage.parse_args(["--zones-tf"]).zones_tf)

    def test_publishing_is_gated_on_the_flag(self):
        self.assertIn('zones_state["paths"] and args.zones_tf', self.source)

    def test_the_parent_frame_is_map_not_the_stage_root(self):
        """프림 이름이 곧 프레임 이름이다. 스테이지 루트를 주면 frame_id 가 `P3Pharmacy` 로 나간다."""
        self.assertEqual(Z.PARENT_FRAME, "map")
        self.assertIn("zoneslib.parent_prim(stage, STAGE_ROOT)", self.source)

    def test_the_module_says_the_names_differ_from_the_contract(self):
        """`bed_a1/cabinet`(계약) vs `bed_a1_cabinet`(여기). 프림 이름에 `/` 를 못 쓴다."""
        source = (STANDALONE / "p3sim/zones.py").read_text()
        self.assertIn("bed_a1/cabinet", source)
        self.assertIn("zones_tf", source)


class Ur5SpawnReady(unittest.TestCase):
    """`--mode ros` 에서 팔이 USD 의 0 자세(수평으로 다 편 자세)로 서 있던 것(비전 9/21, 실습23a).

    팔 노드는 기동 때 홈으로 가지 않으므로 **첫 픽이 그 자세에서 출발**하고, `move_to_pose` 는 관절 공간
    직선이라 중간 충돌 검사가 없다. selfdemo 만 돌던 실습12 는 이 구간을 본 적이 없다.
    """

    def setUp(self):
        sys.path.insert(0, str(STANDALONE))
        import pharmacy_stage

        self.stage = pharmacy_stage
        self.source = (STANDALONE / "pharmacy_stage.py").read_text()

    def test_selfdemo_and_every_existing_preset_keep_their_behaviour(self):
        """작전 조건 ①. 기본이 꺼져 있어야 기존 회차가 안 바뀐다."""
        self.assertFalse(self.stage.parse_args([]).ur5_spawn_ready)
        self.assertFalse(self.stage.parse_args(["--mode", "selfdemo"]).ur5_spawn_ready)
        for name in self.stage.PRESETS:
            expected = name == "emptyworld-loop"
            self.assertEqual(self.stage.parse_args(["--preset", name]).ur5_spawn_ready, expected, name)

    def test_the_empty_world_preset_turns_it_on(self):
        self.assertTrue(self.stage.parse_args(["--preset", "emptyworld-loop"]).ur5_spawn_ready)

    def test_the_spawn_joints_are_logged(self):
        """작전 조건 ②. 이 줄이 K4 L3 의 판정 근거가 된다."""
        self.assertIn('log(f"ur5 spawn_ready solved=', self.source)
        self.assertIn('log(f"ur5 home_positions=', self.source)

    def test_the_settled_joints_are_logged_not_just_the_written_ones(self):
        """비전이 params 에 넣는 home_joint_positions 는 **정착한** 값이어야 한다(작전 9/21, 공차 0.05 rad).

        중력 처짐이 있으면 쓴 값과 다르고, 그 차이가 at_home 공차를 넘으면 주행이 GoToZone 을 전부 거부한다.
        """
        self.assertIn('log(f"ur5 spawn_immediate joints=', self.source)
        self.assertIn('log(f"ur5 spawn_settled steps=', self.source)
        self.assertIn("sag_rad=", self.source)
        self.assertIn("at_home_tol=0.05", self.source)
        # 1~2 s 뒤 값을 원한다(비전 9/21). 60 Hz 기준 90 스텝 = 1.5 s.
        self.assertGreaterEqual(self.stage.parse_args([]).ur5_spawn_settle_steps, 60)

    def test_a_drift_past_the_at_home_tolerance_is_called_out(self):
        self.assertIn("WARN sag exceeds the at_home tolerance", self.source)

    def test_a_failed_ik_leaves_the_arm_alone_and_says_so(self):
        """반쯤 옮긴 자세가 제일 나쁘다. 못 풀면 아무것도 쓰지 않는다."""
        cell_source = (STANDALONE / "p3sim/ur5_cell.py").read_text()
        self.assertIn("if not solved or not targets:\n            return (False, targets)", cell_source)
        self.assertIn("WARN ur5 spawn_ready IK failed", self.source)


class Ur5BaseFrame(unittest.TestCase):
    """받침대 UR5 의 밑동 프레임 이름 — **결정 47(재범 9/21): `amr_1/ur_arm_base_link`.**

    `amr_1/base_link` 는 base_driver 가 이동 베이스용으로 내는 이름이다(계약 420–434줄). 스테이지가 그것을
    child 로 내면 같은 child 에 부모가 둘이 되어 tf2 트리가 메시지마다 뒤집히고, fleet 의
    `map → amr_1/base_link` 조회(도착 판정의 유일한 위치 출처, 계약 827줄)가 받침대 자리를 읽거나 실패한다.
    """

    def setUp(self):
        sys.path.insert(0, str(STANDALONE))
        import pharmacy_stage

        self.stage = pharmacy_stage
        self.cell_source = (STANDALONE / "p3sim/ur5_cell.py").read_text()

    def test_the_default_is_the_decided_name(self):
        from p3sim import sensors as S
        from p3sim import ur5_cell as U

        self.assertEqual(S.frame("/amr_1", U.UR5_BASE_LINK), "amr_1/ur_arm_base_link")

    def test_the_stage_never_publishes_the_mobile_base_name(self):
        """이 이름의 작성자는 base_driver 하나다. 어느 조합에서든 스테이지가 내면 계약 3절 위반이다."""
        self.assertNotIn('S.frame(ns, "base_link")', self.cell_source)

    def test_the_argument_still_overrides_it(self):
        self.assertIn('base_frame = cfg.get("base_frame") or S.frame(ns, UR5_BASE_LINK)', self.cell_source)
        self.assertIn('"base_frame": args.ur5_base_frame,', (STANDALONE / "pharmacy_stage.py").read_text())
        self.assertEqual(self.stage.parse_args(["--ur5-base-frame", "other/name"]).ur5_base_frame, "other/name")

    def test_the_base_frame_is_attached_to_map(self):
        """밑동은 두 발행기에서 parentPrim 이라 **child 로 안 나간다** — 부모가 없다.

        전에는 이름이 `amr_1/base_link` 라 base_driver 의 `odom → amr_1/base_link` 가 **우연히** 부모를
        붙여 줬다(값은 AMR 자세라 틀렸다). 이름을 가르면 그 우연도 없어져 팔이 `<zone>/cabinet`(부모 `map`)을
        조회할 때 끊긴 두 트리 사이가 된다. 그래서 스테이지가 `map → 밑동` 을 낸다.
        """
        self.assertIn("BaseFrameGraph", self.cell_source)
        self.assertIn('("TfBase.inputs:topicName", "tf_static")', self.cell_source)
        self.assertIn("world_root=zoneslib.parent_prim(stage, STAGE_ROOT)",
                      (STANDALONE / "pharmacy_stage.py").read_text())


class ContactWatch(unittest.TestCase):
    """K3 판정선이 "접촉 0" 이다. 팔이 없는 빈월드에서도 감시가 돌아야 한다(작전 9/21: 꺼져 있었다)."""

    def setUp(self):
        self.source = (STANDALONE / "pharmacy_stage.py").read_text()

    def test_it_no_longer_requires_the_m0609_arm(self):
        self.assertNotIn("if arm is not None and not args.no_contact_log:", self.source)

    def test_the_amr_bodies_are_watched(self):
        self.assertIn("rigid_bodies_under(AMR_ROOT)", self.source)

    def test_the_startup_line_says_what_is_watched(self):
        """회차가 끝나야 아는 `stop reason=` 줄로는 기동 직후 판정을 못 한다(작전 9/21, #415)."""
        self.assertIn('log(f"observers contact_watch=', self.source)
        for field in ("watch_bodies=", "ur5=", "amr=", "m0609=", "zones_tf=", "hand_camera="):
            self.assertIn(field, self.source, field)

    def test_it_says_so_when_there_is_nothing_to_watch(self):
        """조용히 꺼지면 "접촉 0" 이 "감시가 없었다" 와 구별되지 않는다."""
        self.assertIn("contact_watch off: no bodies to watch", self.source)


class ZoneFrames(unittest.TestCase):
    """스테이지가 tf_static 으로 내는 구역 프레임."""

    def setUp(self):
        self.prims = Z.zone_prims(L.full_loop_zones())

    def test_the_prim_name_loses_the_slash_but_the_frame_keeps_it(self):
        """프림 경로에는 `/` 를 못 쓴다. **프레임 이름은 `isaac:nameOverride` 가 정한다.**

        9/21 에 내가 "이름을 바꿀 입력이 없다" 고 잘못 보고했다. `ur5_cell` 이 `amr_1/base_link` 같은 이름을
        이미 그 속성으로 내고 있었다. 계약 표기는 `bed_a1/cabinet`(슬래시)이다.
        """
        prims = [p for p, _f, _xyz, _q in self.prims]
        frames = [f for _p, f, _xyz, _q in self.prims]
        self.assertIn("bed_a1_cabinet", prims)
        self.assertIn("bed_a1/cabinet", frames)
        for name in prims:
            self.assertNotIn("/", name)

    def test_the_stage_sets_the_name_override(self):
        """이 속성이 없으면 프레임 이름이 프림 이름(밑줄)으로 떨어진다."""
        source = (STANDALONE / "p3sim/zones.py").read_text()
        self.assertIn('CreateAttribute("isaac:nameOverride"', source)

    def test_parent_is_map_and_never_odom(self):
        """`odom→amr_1/base_link` 의 작성자는 base_driver 하나다(재범 결정 (나))."""
        self.assertEqual(Z.PARENT_FRAME, "map")
        for _prim, frame, _xyz, _q in self.prims:
            self.assertNotIn("odom", frame)
            self.assertNotIn("base_link", frame)

    def test_yaw_round_trips_through_the_quaternion(self):
        for yaw in (0.0, 1.5707963267948966, -0.7853981633974483, 3.0):
            w, x, y, z = Z.yaw_quat(yaw)
            self.assertAlmostEqual(x, 0.0)
            self.assertAlmostEqual(y, 0.0)
            self.assertAlmostEqual(2.0 * math.atan2(z, w), yaw, places=9)

    def test_every_zone_becomes_one_prim(self):
        self.assertEqual(len(self.prims), len(L.full_loop_zones()))

    def test_heights_match_the_layout(self):
        """`cabinet` 은 놓는 면이라 바닥이 아니다."""
        by_name = {f: xyz for _p, f, xyz, _q in self.prims}
        self.assertGreater(by_name["bed_a1/cabinet"][2], 0.0)
        self.assertAlmostEqual(by_name["bed_a1"][2], 0.0)


class ZonesFileMatchesTheCode(unittest.TestCase):
    """저장된 zones.emptyworld.yaml 과 코드가 어긋나면 잡는다. 그 파일은 자동 생성물이다.

    PyYAML 로 읽지 않고 **본문을 다시 찍어 대조**한다 — L1 의 sim 잡에는 usd-core 만 있고 PyYAML 이 없다
    (#401 CI, 2026-09-21). 파서를 못 쓰니 생성기가 파서 없이 찍을 수 있어야 하고, 그래서 대조도 본문으로 한다.
    """

    PATH = Path(__file__).resolve().parents[2] / "src/rokey_p3_description/config/zones.emptyworld.yaml"

    def test_the_file_exists(self):
        self.assertTrue(self.PATH.is_file(), self.PATH)
        text = self.PATH.read_text()
        self.assertIn("\nframe: map\n", text)
        self.assertIn("자동 생성물", text, "손으로 고치지 말라는 머리말이 사라졌다")

    def test_it_is_what_the_code_produces(self):
        """손으로 고쳤거나 레이아웃을 바꾸고 다시 안 만들었으면 여기서 걸린다."""
        self.assertEqual(self.PATH.read_text(), L.zones_yaml_text())

    def test_every_zone_appears_in_the_file(self):
        text = self.PATH.read_text()
        for name in L.zones_yaml()["zones"]:
            self.assertIn(f"\n  {name}:\n", text, name)

    def test_the_default_zones_file_is_untouched(self):
        """기본 zones.yaml 은 심월드 자리다. 빈월드 값을 거기 쓰면 어느 월드 값인지 섞인다."""
        default = self.PATH.with_name("zones.yaml")
        if not default.is_file():
            self.skipTest("기본 zones.yaml 이 없다")
        for value in re.findall(r"^\s*x:\s*(\S+)$", default.read_text(), re.M):
            self.assertEqual(float(value), 0.0, "심월드 값은 아직 0 이어야 한다")


class OrderPoolDestinations(unittest.TestCase):
    """주문 풀이 가리키는 곳이 빈월드에 없으면 배송이 fleet 에서 막힌다(통합&정비 K0-b).

    없는 zone 은 웹·orchestrator 를 그냥 통과하고 fleet 에서만 거부되므로 화면에서 원인이 안 보인다.
    그래서 값이 아니라 **주문 풀과 zones 의 관계**를 여기서 잡는다. PyYAML 없이 읽는다(L1 sim 잡에 없다).
    """

    POOL = Path(__file__).resolve().parents[2] / "src/rokey_p3_orchestrator/config/order_pool.yaml"
    #: `bed: bed_a1` 과 `destination_id: bed_a1` 둘 다 목적지다(주문 풀 스키마가 아직 둘 다 쓴다).
    DESTINATION = re.compile(r"\b(?:bed|destination_id):\s*[\"']?([a-z_0-9]+)[\"']?")

    def destinations(self):
        if not self.POOL.is_file():
            self.skipTest("주문 풀이 없다")
        found = set(self.DESTINATION.findall(self.POOL.read_text()))
        self.assertTrue(found, "주문 풀에서 목적지를 못 읽었다")
        return found

    def test_every_destination_exists_in_the_empty_world_zones(self):
        missing = self.destinations() - set(L.zones_yaml()["zones"])
        self.assertEqual(missing, set(), f"빈월드에 없는 목적지: {sorted(missing)}")

    def test_the_destinations_are_bed_ids(self):
        """ID 규칙이 바뀌면 zone 이름도 같이 바뀌어야 한다."""
        for destination in self.destinations():
            self.assertRegex(destination, ZONE_ID)


if __name__ == "__main__":
    unittest.main()
