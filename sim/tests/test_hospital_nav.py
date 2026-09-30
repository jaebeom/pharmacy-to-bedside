"""병원 씬 zones·routes 가 앵커·지도에서 만든 것과 같고, 몸체가 고정물에 닿지 않는가. Isaac·ROS·PyYAML 없이 돈다.

지키는 것:
- 저장된 `zones.hospital.yaml`·`routes.hospital.yaml` 이 `hospital_nav.py` 가 지금 만드는 것과 같다
  (손으로 고치면 걸린다).
- 앵커 JSON·지도 yaml 이 저장소의 `hospital_navigationv1.usda` 에서 나왔다(sha256).
- 주문 풀의 병상이 zones 에 있다(없는 zone 은 fleet 에서만 거부된다 — 한 바퀴가 ② 에서 끊긴다).
- 정차 자세 몸체가 지도의 막힌 칸과 겹치지 않고, 경로 위 몸체 중심이 장애물에서 반폭 이상 떨어져 있다.
- PDF(P3_Map, 9/22)의 기대 경로 셋이 있다: A4 → D4, A3 → C2 병실, A1 → B.

- 접근점(각 zone 으로 드는 마지막 경유점)에서 제자리 회전 반경이 나오고(막힌 칸 가장자리·침상·협탁 상자 기준),
  거기서 yaw 를 고정한 채 정차 자리로 옮기는 동안 몸체가 막힌 칸과 겹치지 않는다(9/24 10건 D3 협탁 접촉).

지키지 않는 것(미실행): 병원 높이에서 팔 IK, Isaac 의 PhysX 충돌 기반 지도와의 대조, 접근점 밖(Nav2 구간) 회전 스윕.
"""
import hashlib
import math
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "standalone"))
from p3sim import hospital_nav as hn  # noqa: E402
import hospital_nav_files as generator  # noqa: E402

REPO = hn.REPO
CONFIG = os.path.join(REPO, "src", "rokey_p3_description", "config")
USDA = os.path.join(REPO, "sim", "scenes", "hospital_navigationv1.usda")
ORDER_POOL = os.path.join(REPO, "src", "rokey_p3_orchestrator", "config", "order_pool.yaml")
HOSPITAL_ORDER_POOL = os.path.join(REPO, "src", "rokey_p3_orchestrator", "config", "order_pool.hospital.yaml")


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


class HospitalNavFiles(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.grid = hn.load_map()
        cls.anchors = hn.load_anchors()
        cls.poses = hn.zone_poses(cls.grid, cls.anchors)
        cls.doc = hn.zones_doc(cls.poses)
        cls.route_grid = cls.grid      # 병실 테이블(병동 입구 복도 협탁)은 씬 실물이라 지도에 이미 있다
        cls.pairs, cls.clear, cls.missing = hn.routes(cls.route_grid, cls.poses)

    def test_receiver_profile_preserves_docks_and_has_connected_clear_routes(self):
        """성공 회차 적재점을 써도 왼쪽 도크를 유지하고 지도에서 모든 목적지로 연결된다."""
        import copy

        poses = copy.deepcopy(self.poses)
        poses["load"]["pose"] = generator.RECEIVER_LOAD
        poses[hn.LOAD_DOCK] = dict(poses["load"])     # 재범 9/29 B안: A1 충전 도크 = 적재 자리
        self.assertTrue(hn.footprint_free(self.grid, *generator.RECEIVER_LOAD))
        for zone in hn.DOCK_ZONE.values():
            if zone != hn.LOAD_DOCK:
                self.assertEqual(poses[zone], self.poses[zone])
        pairs, _clear, missing = hn.routes(self.grid, poses)
        self.assertEqual(missing, [])
        self.assertEqual(_read(os.path.join(CONFIG, "routes.hospital-receiver.yaml")),
                         hn.routes_yaml_text(pairs))
        doc = hn.zones_doc(poses)
        for zone in ("load", hn.LOAD_DOCK):
            doc["zones"][zone].update(zip(("x", "y", "yaw"), generator.RECEIVER_LOAD, strict=True))
        doc["pharmacy"]["belt_end"] = generator.RECEIVER_BELT_END
        self.assertEqual(_read(os.path.join(CONFIG, "zones.hospital-receiver.yaml")), hn.zones_yaml_text(doc))
        self.assertEqual(doc["zones"]["load"], dict(doc["zones"][hn.LOAD_DOCK], kind="load"))

    def test_receiver_dock_reaches_the_table_pouch_without_moving(self):
        """재범 9/29 "그 자리에서 바로": 탁자 정착점이 도크(= 적재)에서 팔 적재 한도 안이고, 옛 dock_1 에서는 밖이다.
        도크 접근점에서 A1 모듈까지 도크 회전 규칙(반경 + 0.10) 밖이다."""
        target = (generator.RECEIVER_BELT_END["x"], generator.RECEIVER_BELT_END["y"])

        def reach(pose):
            ax, ay = hn._rot(pose[2], hn.ARM_X, 0.0)
            return math.hypot(target[0] - pose[0] - ax, target[1] - pose[1] - ay)

        self.assertLessEqual(reach(generator.RECEIVER_LOAD), hn.REACH_MAX_LOAD)
        self.assertGreater(reach(self.poses[hn.LOAD_DOCK]["pose"]), hn.REACH_MAX_LOAD)
        near = hn.approach_point(self.grid, generator.RECEIVER_LOAD, margin=hn.DOCK_TURN_MARGIN)
        shelf = self.anchors["outlets"]["A1"]["shelf"]
        self.assertGreaterEqual(hn._box_distance(shelf, *near), hn.TURN_RADIUS + hn.DOCK_TURN_MARGIN)

    def test_sources_are_the_committed_scene(self):
        with open(USDA, "rb") as fh:
            sha = hashlib.sha256(fh.read()).hexdigest()
        self.assertEqual(self.anchors["source"]["sha256"], sha, "앵커 JSON 이 저장소의 씬에서 나온 것이 아니다")
        self.assertIn(sha, _read(hn.MAP_YAML_PATH), "지도가 저장소의 씬에서 나온 것이 아니다")

    def test_zones_file_matches_the_generator(self):
        self.assertEqual(_read(os.path.join(CONFIG, "zones.hospital.yaml")), hn.zones_yaml_text(self.doc))

    def test_routes_file_matches_the_generator(self):
        self.assertEqual(self.missing, [], "경로를 못 이은 쌍이 있다")
        self.assertEqual(_read(os.path.join(CONFIG, "routes.hospital.yaml")), hn.routes_yaml_text(self.pairs))

    def test_order_pool_beds_are_zones(self):
        beds = set(re.findall(r"bed:\s*(bed_[a-z][0-9]+)", _read(ORDER_POOL)))
        self.assertTrue(beds)
        self.assertLessEqual(beds, set(self.doc["zones"]), "주문 풀의 병상이 zones 에 없다")

    def test_hospital_order_pool_covers_every_bed_once(self):
        """병원 전체 시나리오(#527): 병원 주문 풀은 침상 10개에 하나씩이다. 없는 zone 은 fleet 에서만 거부된다."""
        text = _read(HOSPITAL_ORDER_POOL)
        beds = re.findall(r"bed:\s*(bed_[a-z][0-9]+)", text)
        zone_beds = sorted(z for z in self.doc["zones"] if z.startswith("bed_"))
        self.assertEqual(sorted(beds), zone_beds)
        ids = re.findall(r"order_id:\s*(ord-[0-9]{4})", text)
        self.assertEqual(len(ids), len(set(ids)))

    def test_tolerances_are_positive(self):
        for name, z in self.doc["zones"].items():
            self.assertGreater(z["tol_xy"], 0, name)
            self.assertGreater(z["tol_yaw"], 0, name)

    def test_beds_have_cabinet_and_tag(self):
        for name, z in self.doc["zones"].items():
            if name.startswith("bed_"):
                self.assertIn("cabinet", z, name)
                self.assertGreater(z["tag"]["z"], z["cabinet"]["z"], name)

    def test_stop_footprints_are_free(self):
        """9/29 부터 도크도 벽에서 떨어진 적재 자리 줄에 서서, 모든 정차 자리를 같은 여유로 본다."""
        for name, e in self.poses.items():
            if e["pose"] is not None:
                self.assertTrue(hn.footprint_free(self.grid, *e["pose"], clearance=hn.STOP_CLEARANCE), name)

    def test_docks_stand_left_of_their_module_like_the_a1_dock(self):
        """재범 9/29 "도킹 스테이션 옮길꺼면 다 옮겨야지": A2–A4 도크도 제 모듈에 대해 A1 도크(적재 자리)와 같은
        상대 자리다. 떠날 때 접근점에서 모듈·벽이 도크 회전 규칙(반경 + 0.10) 밖이다(회차77)."""
        ref = self.anchors["outlets"][hn.LOAD_OUTLET]["shelf"]
        rx, ry, ryaw = self.poses[hn.LOAD_DOCK]["pose"]
        for label, zone in hn.DOCK_ZONE.items():
            x, y, yaw = self.poses[zone]["pose"]
            shelf = self.anchors["outlets"][label]["shelf"]
            self.assertAlmostEqual(x - shelf["min"][0], rx - ref["min"][0], delta=0.001, msg=zone)
            self.assertAlmostEqual(y - shelf["min"][1], ry - ref["min"][1], delta=0.001, msg=zone)
            self.assertEqual(yaw, ryaw, zone)
            self.assertLess(x + hn.BODY_WIDTH / 2, shelf["min"][0], zone)     # 모듈 왼쪽
            near = hn.approach_point(self.grid, (x, y, yaw), margin=hn.DOCK_TURN_MARGIN)
            self.assertGreaterEqual(hn._box_distance(shelf, *near), hn.TURN_RADIUS + hn.DOCK_TURN_MARGIN, zone)
            self.assertGreaterEqual(5.350 - near[1], hn.TURN_RADIUS + hn.DOCK_TURN_MARGIN, zone)
            self.assertLess(hn._box_distance(shelf, x, y), hn.TURN_RADIUS, zone)   # 도크 자리에서는 못 돈다 — 물러난다

    def test_pick_and_place_targets_sit_beside_the_body(self):
        """재범 9/23: 집기(load: A1 끝)·내려놓기(bed_*: 협탁)는 대상이 팔 밑동 왼쪽(차체 긴 변)에 온다."""
        targets = {"load": hn.pharmacy_frames()["belt_end"][:2]}
        targets.update({n: e["cabinet"][:2] for n, e in self.poses.items() if n.startswith("bed_") and e["pose"]})
        for name, (tx, ty) in targets.items():
            x, y, yaw = self.poses[name]["pose"]
            ax, ay = hn._rot(yaw, hn.ARM_X, 0.0)
            lx, ly = hn._rot(-yaw, tx - (x + ax), ty - (y + ay))
            self.assertGreater(ly, abs(lx), f"{name}: 대상이 옆이 아니다 (밑동 로컬 {lx:.2f}, {ly:.2f})")

    def _approaches(self):
        for name, e in self.poses.items():
            if e["pose"] is None:
                continue
            margin = hn.DOCK_TURN_MARGIN if name in hn.DOCK_ZONE.values() else 0.02   # routes() 와 같은 규칙
            point = hn.approach_point(self.route_grid, e["pose"], margin=margin)
            if point is not None:
                yield name, e["pose"], point

    def test_the_a1_dock_is_the_load_pose_and_leaves_room_to_turn(self):
        """재범 9/29 B안 "도크에서 AMR 이 이동하지 않고 그 자리에서 바로 파지": dock_1 = load(같은 자세).
        팔 밑동↔봉투 정착 자리 수평이 적재 한도 안이다.
        떠날 때 접근점에서 모듈·벽이 도크 회전 규칙(반경 + 0.10) 밖이다."""
        dock, load = self.poses[hn.LOAD_DOCK], self.poses["load"]
        self.assertEqual(dock["pose"], load["pose"])
        self.assertLessEqual(dock["reach"], hn.REACH_MAX_LOAD)
        x, y, yaw = dock["pose"]
        near = hn.approach_point(self.grid, (x, y, yaw), margin=hn.DOCK_TURN_MARGIN)
        shelf = self.anchors["outlets"]["A1"]["shelf"]
        self.assertGreaterEqual(hn._box_distance(shelf, *near), hn.TURN_RADIUS + hn.DOCK_TURN_MARGIN)
        self.assertGreaterEqual(hn.edge_clearance(self.grid, *near), hn.TURN_RADIUS + hn.DOCK_TURN_MARGIN)
        # 도크에서 봉투까지 팔이 안 닿던 옛 자리(-7.272, 4.784)가 아니다.
        self.assertLess(x, shelf["min"][0])

    def test_routes_end_at_the_approach_point(self):
        for name, _, point in self._approaches():
            for (a, b), wps in self.pairs.items():
                if b == name and wps:
                    self.assertEqual(tuple(wps[-1]), point, f"{a}→{b}")

    def test_approach_points_leave_room_to_turn(self):
        """9/24 병원 10건: bed_a3 접근점은 칸 중심 거리로 0.673 m 였지만 D3 협탁 상자까지 0.594 m 였고, 돌다 닿았다."""
        boxes = {f"bed {k}": v for k, v in self.anchors["beds"].items()}
        boxes.update({f"bedside {k}": v for k, v in self.anchors["bedside_tables"].items()})
        for name, _, (x, y) in self._approaches():
            self.assertGreaterEqual(hn.edge_clearance(self.route_grid, x, y), hn.TURN_RADIUS + 0.02, name)
            for what, box in boxes.items():
                dx = max(box["min"][0] - x, 0.0, x - box["max"][0])
                dy = max(box["min"][1] - y, 0.0, y - box["max"][1])
                self.assertGreaterEqual(math.hypot(dx, dy), hn.TURN_RADIUS, f"{name} 접근점 ({x}, {y}) ↔ {what}")

    def test_slide_from_the_approach_point_is_free(self):
        """추종기는 접근점에서 yaw 를 맞춘 뒤 그 yaw 그대로 정차 자리로 옮긴다(turn_first). 그 길의 몸체가 비어 있다."""
        for name, (sx, sy, yaw), (x, y) in self._approaches():
            for k in range(21):
                px, py = x + (sx - x) * k / 20, y + (sy - y) * k / 20
                clearance = 0.0 if name.startswith("dock_") else hn.STOP_CLEARANCE
                self.assertTrue(hn.footprint_free(self.grid, px, py, yaw, clearance=clearance),
                                f"{name} 옆걸음 ({px:.3f}, {py:.3f})")

    def test_station_b_puts_the_place_point_beside_the_body_like_the_beds(self):
        """9/24 재범: 간호스테이션 B 테이블(SM_SideTable_02a4_01) 윗면에 놓는다."""
        e = self.poses["station_b"]
        x, y, yaw = e["pose"]
        self.assertTrue(hn.footprint_free(self.grid, x, y, yaw))
        px, py, pz = e["cabinet"]
        lo, hi = hn.STATION_B_TABLE["min"], hn.STATION_B_TABLE["max"]
        self.assertTrue(lo[0] < px < hi[0] and lo[1] < py < hi[1], "놓는 점이 테이블 위가 아니다")
        self.assertEqual(hi[2], pz)
        ax, ay = hn._rot(yaw, hn.ARM_X, 0.0)
        self.assertLessEqual(math.hypot(px - (x + ax), py - (y + ay)), hn.REACH_MAX_CABINET)
        # 놓는 점은 팔 밑동 왼쪽(병상과 같은 상대 기하). 회차48: 몸체 뒤에 두면 위팔이 테이블 모서리에 걸렸다.
        lx, ly = hn._rot(-yaw, px - (x + ax), py - (y + ay))
        self.assertGreater(ly, abs(lx))
        self.assertAlmostEqual(self.poses["bed_a1"]["reach"], e["reach"], places=3)
        z = self.doc["zones"]["station_b"]
        self.assertEqual("station", z["kind"])
        self.assertGreater(z["tag"]["z"], z["cabinet"]["z"])

    def test_station_b_did_not_move_the_golden_routes(self):
        """station_b 는 골든 경로표 뒤에 더했다. 그 zone 이 안 낀 쌍의 경로는 station_b 없이 만든 것과 같다."""
        without = {k: v for k, v in self.poses.items() if k not in hn.ISOLATED_STOPS}
        pairs, _clear, missing = hn.routes(self.grid, without)
        self.assertEqual([], missing)
        for key, wps in pairs.items():
            self.assertEqual(wps, self.pairs[key], key)

    def test_room_tables_are_the_ward_entrance_corridor_tables(self):
        """재범 9/25(오버헤드 컷의 원): C1·C2 = 병동 입구 위·아래 복도 협탁. 씬 실물이라 지도에서 막혀 있고, 바로 서쪽
        복도는 비었다. 놓는 기하는 station_b 와 같다(놓는 점이 몸체 왼쪽, 밑동↔놓는 점 0.70 m)."""
        tables = hn.room_tables()
        self.assertEqual({"station_c": "C1", "station_d": "C2"}, {z: t["room"] for z, t in tables.items()})
        for zone, table in tables.items():
            lo, hi = table["min"], table["max"]
            door = self.anchors["doors"][table["room"]]
            self.assertLess(hi[0], door["min"][0])                          # 문 벽 서쪽(복도)
            self.assertLess(abs((lo[1] + hi[1]) / 2 - door["center"][1]), 2.5)  # 그 병실 입구 옆
            for i in range(1, 10):
                for j in range(1, 10):
                    x = lo[0] + (hi[0] - lo[0]) * i / 10
                    y = lo[1] + (hi[1] - lo[1]) * j / 10
                    self.assertTrue(self.grid.is_blocked(x, y), f"{zone} 협탁 ({x:.2f}, {y:.2f}) 가 지도에 없다")
            e = self.poses[zone]
            x, y, yaw = e["pose"]
            self.assertAlmostEqual(self.poses["station_b"]["reach"], e["reach"], places=3)
            self.assertLess(x + hn.BODY_WIDTH / 2, lo[0])                 # 협탁 서쪽 복도에 선다
            ax, ay = hn._rot(yaw, hn.ARM_X, 0.0)
            lx, ly = hn._rot(-yaw, e["cabinet"][0] - (x + ax), e["cabinet"][1] - (y + ay))
            self.assertGreater(ly, abs(lx))                                  # 놓는 점이 몸체 왼쪽
            self.assertEqual("station", self.doc["zones"][zone]["kind"])
            self.assertEqual(table["room"], self.doc["zones"][zone]["room"])
            self.assertAlmostEqual(hn.SIDE_TABLE_TOP, e["cabinet"][2], places=3)

    def test_route_legs_keep_half_width(self):
        for (a, b), wps in self.pairs.items():
            pts = [self.poses[a]["pose"][:2], *wps, self.poses[b]["pose"][:2]]
            for p, q in zip(pts[:-1], pts[1:], strict=True):
                self.assertGreaterEqual(hn.segment_min_clearance(self.grid, p, q), hn.BODY_WIDTH / 2,
                                        f"{a}→{b} 구간 {p}→{q} 가 몸체 반폭보다 가깝다")

    def test_doors_are_crossed_with_the_riser_margin(self):
        """9/23 L3: C2 문에서 여유가 정확히 0 이라 팔 받침이 문틀에 닿았다. 문 1 m 안에서는 PATH_RADIUS 를 지킨다."""
        need = hn.BODY_LENGTH / 2 + hn.RISER_OVERHANG + 0.03   # 받침 끝에서 3 cm(추종 오차 0.02 + 1 cm)
        doors = [d["center"][:2] for d in self.anchors["doors"].values()]
        stops = [e["pose"][:2] for e in self.poses.values() if e["pose"] is not None]
        for (a, b), wps in self.pairs.items():
            pts = [self.poses[a]["pose"][:2], *wps, self.poses[b]["pose"][:2]]
            for p, q in zip(pts[:-1], pts[1:], strict=True):
                n = max(1, int(math.hypot(q[0] - p[0], q[1] - p[1]) / 0.025))
                for k in range(n + 1):
                    x, y = p[0] + (q[0] - p[0]) * k / n, p[1] + (q[1] - p[1]) * k / n
                    near_door = any(math.hypot(x - d[0], y - d[1]) < 1.0 for d in doors)
                    near_stop = any(math.hypot(x - s[0], y - s[1]) < 1.2 for s in stops)
                    if near_door and not near_stop:
                        self.assertGreaterEqual(self.grid.clearance(x, y), need, f"{a}→{b} 문 근처 ({x:.2f}, {y:.2f})")

    def _passes(self, a, b, door):
        d = self.anchors["doors"][door]["center"]
        pts = [self.poses[a]["pose"][:2], *self.pairs[(a, b)], self.poses[b]["pose"][:2]]
        for p, q in zip(pts[:-1], pts[1:], strict=True):
            n = max(1, int(math.hypot(q[0] - p[0], q[1] - p[1]) / 0.05))
            if any(math.hypot(p[0] + (q[0] - p[0]) * k / n - d[0], p[1] + (q[1] - p[1]) * k / n - d[1]) < 0.8
                   for k in range(n + 1)):
                return True
        return False

    def test_pdf_expected_navigations(self):
        self.assertTrue(self._passes("dock_4", "bed_a4", "C1"),
                        "A4→D4 가 C1 문을 안 지난다")
        self.assertTrue(self._passes("dock_3", "bed_b1", "C2"), "A3→C2 병실(D5)이 C2 문을 안 지난다")
        self.assertIn(("dock_1", "station_a"), self.pairs)

    def test_bed_rooms_match_the_scene_doors(self):
        """병상마다 room·ward·label 이 있고, 적재에서 그 병상까지 가는 길이 자기 병실 문만 지난다.

        room 은 작전이 정한 표(ROOM_BEDS)다. 표를 잘못 적으면 씬의 문 기하와 어긋나 여기서 걸린다.
        """
        doors = set(self.anchors["doors"])
        self.assertEqual(set(hn.ROOM_BEDS), doors, "병실 표와 씬의 문 앵커가 다르다")
        for label, zone in hn.BED_ZONE.items():
            z = self.doc["zones"][zone]
            self.assertEqual((z["ward"], z["label"]), (hn.WARD, label), zone)
            self.assertTrue(self._passes("load", zone, z["room"]), f"load→{zone} 가 {z['room']} 문을 안 지난다")
            for other in doors - {z["room"]}:
                self.assertFalse(self._passes("load", zone, other), f"load→{zone} 가 다른 병실 문 {other} 를 지난다")


if __name__ == "__main__":
    unittest.main()
