"""Plain-Python checks for sim/standalone/pharmacy_stage.py and sim/standalone/p3sim; Isaac is not started.

    python3 -m unittest discover -s sim/tests -p 'test_*stage*.py'
"""

import contextlib
import importlib.util
import io
import json
import sys
import unittest
from pathlib import Path

STANDALONE = Path(__file__).resolve().parents[1] / "standalone"
sys.path.insert(0, str(STANDALONE))

from p3sim import belt, bridge, common, pouch, reset  # noqa: E402

ISAAC_MODULES = ("isaacsim", "omni", "pxr", "carb", "rclpy")
ROOM_OUTLET = (1.35, 1.0, 0.75)


def load_stage():
    spec = importlib.util.spec_from_file_location("pharmacy_stage", STANDALONE / "pharmacy_stage.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


STAGE = load_stage()


class ImportAndArgumentTests(unittest.TestCase):
    def test_import_does_not_touch_isaac(self):
        before = {name for name in sys.modules if name.split(".")[0] in ISAAC_MODULES}
        load_stage()
        self.assertEqual(before, {name for name in sys.modules if name.split(".")[0] in ISAAC_MODULES})

    def test_defaults_are_consistent(self):
        args = STAGE.parse_args([])
        self.assertEqual([-0.10, 0.33], args.rail_y_limits)
        self.assertEqual([1e7, 1e5, 1e8], args.rail_drive)
        self.assertEqual("selfdemo", args.mode)
        self.assertEqual([], STAGE.validate(args))
        layout = STAGE.room(args)
        self.assertEqual(15, len(layout["cells"]))  # 3 rows x 5 columns of canisters
        self.assertEqual(ROOM_OUTLET, layout["belt_start"])  # belt starts at the dispenser outlet

    def test_same_pose_decides_whether_a_qr_face_is_rewritten(self):
        """주차된 봉투는 자세가 그대로다. 같은 자세면 USD 를 다시 쓰지 않는다(최적화 9/23)."""
        pose = ((1.0, 2.0, 3.0), (1.0, 0.0, 0.0, 0.0))
        self.assertTrue(STAGE._same_pose(pose, ((1.0, 2.0, 3.0), (1.0, 0.0, 0.0, 0.0))))
        self.assertTrue(STAGE._same_pose(pose, ((1.0, 2.0, 3.000001), (1.0, 0.0, 0.0, 0.0))))
        self.assertFalse(STAGE._same_pose(pose, ((1.0, 2.0, 3.001), (1.0, 0.0, 0.0, 0.0))))
        self.assertFalse(STAGE._same_pose(pose, ((1.0, 2.0, 3.0), (0.9, 0.1, 0.0, 0.0))))

    def test_shelf_canisters_report_contacts_above_their_own_weight(self):
        """약통은 늘 선반에 얹혀 있다. 문턱 0 이면 그 쌍이 매 스텝 보고된다(9/23 경고 419,292 줄)."""
        self.assertEqual(5.0, STAGE.parse_args([]).canister_contact_threshold_n)
        self.assertEqual(0.0, STAGE.parse_args(
            ["--canister-contact-threshold-n", "0"]).canister_contact_threshold_n)

    def test_bad_spawn_ranges_are_reported(self):
        problems = STAGE.validate(STAGE.parse_args(["--spawn-along", "0.0 1.6", "--spawn-lateral", "-0.2 0.2"]))
        self.assertEqual(2, len(problems))

    def test_room_rules(self):
        self.assertTrue(any("--pick-cell" in p for p in STAGE.validate(STAGE.parse_args(["--pick-cell", "9", "9"]))))
        self.assertTrue(any("through the wall" in p for p in STAGE.validate(STAGE.parse_args(["--wall-x", "5"]))))
        self.assertTrue(any("canister-size" in p
                            for p in STAGE.validate(STAGE.parse_args(["--room-canister-size", "0.4 0.1 0.1"]))))

    def test_pair_rejects_reversed_range(self):
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            STAGE.build_parser().parse_args(["--spawn-yaw", "0.3 -0.3"])

    def test_known_orders(self):
        self.assertTrue(STAGE.is_known("ord-0001", None))
        self.assertFalse(STAGE.is_known("ORD-1", None))
        self.assertFalse(STAGE.is_known("ord-0009", {"ord-0001"}))


class BridgeTests(unittest.TestCase):
    README = (Path(__file__).resolve().parents[1] / "README.md").read_text()

    def test_readme_examples_validate(self):
        # The table in sim/README.md is the reference; every example line there must match its topic's schema.
        lines = self.README.split("\n")
        start = lines.index("예시(글자 그대로. 키 순서는 의미 없고 Isaac 은 키를 정렬해 낸다):")
        checked = 0
        topic = None
        for line in lines[start:]:
            if line.startswith("## "):
                break
            if line.startswith("/isaac/"):
                topic = line.split()[0]
            elif line.startswith("{") and topic:
                message = json.loads(line)
                problems = bridge.validate(topic, message)
                if topic == bridge.DISPENSE_REQUEST and message["request_id"] == "":
                    self.assertEqual(["request_id is empty"], problems)
                else:
                    self.assertEqual([], problems, line)
                    self.assertEqual(line, bridge.encode(topic, **{k: v for k, v in message.items() if k != "v"}))
                checked += 1
        self.assertEqual(13, checked)

    def test_decode_reports_problems(self):
        self.assertEqual(["not JSON: Expecting value: line 1 column 1 (char 0)"],
                         bridge.decode(bridge.RESET_REQUEST, "nope")[1])
        _msg, problems = bridge.decode(bridge.RESET_REQUEST, '{"v":1,"epoch":-1}')
        self.assertIn("epoch out of uint32 range", problems)
        _msg, problems = bridge.decode(bridge.RESET_REQUEST, '{"v":1,"epoch":true}')
        self.assertIn("epoch must be an integer", problems)
        _msg, problems = bridge.decode(bridge.RESET_REQUEST, '{"v":2,"epoch":1,"x":0}')
        self.assertIn("unexpected fields ['x']", problems)

    def test_pick_notice_schema_and_rules(self):
        good = {"v": 1, "stamp": {"sec": 1, "nanosec": 0}, "epoch": 3, "order_id": "ord-0001",
                "source": "POUCH_PICKED"}
        self.assertEqual([], bridge.validate(bridge.PICK_NOTICE, good))
        self.assertIn("source must be one of ['POUCH_PICKED']",
                      bridge.validate(bridge.PICK_NOTICE, {**good, "source": "gripper_command"}))
        self.assertIn("order_id is empty", bridge.validate(bridge.PICK_NOTICE, {**good, "order_id": ""}))
        self.assertEqual((True, ""), bridge.pick_notice_applies(good, 3, "ord-0001", True))
        self.assertFalse(bridge.pick_notice_applies({**good, "epoch": 2}, 3, "ord-0001", True)[0])
        self.assertFalse(bridge.pick_notice_applies(good, 3, "ord-0002", True)[0])
        self.assertFalse(bridge.pick_notice_applies(good, 3, "ord-0001", False)[0])

    def test_encode_refuses_bad_messages(self):
        with self.assertRaises(ValueError):
            bridge.encode(bridge.BELT, stamp={"sec": 1}, occupied=True, at_end=False, order_id="", epoch=0)

    def test_stamp_rounds_into_range(self):
        self.assertEqual({"sec": 2, "nanosec": 0}, bridge.stamp(1.9999999999))
        self.assertEqual({"sec": 118, "nanosec": 200000000}, bridge.stamp(118.2))

    def test_every_topic_has_qos_and_schema(self):
        topics = {bridge.DISPENSE_REQUEST, bridge.DISPENSE_RESPONSE, bridge.RESET_REQUEST, bridge.RESET_RESPONSE,
                  bridge.BELT, bridge.EVENTS, bridge.PICK_NOTICE, bridge.BELT_OBSERVATION,
                  bridge.GRIPPER_STATE, bridge.GRIPPER_COMMAND_SEQ, bridge.POUCHES, bridge.TAG_READS, bridge.CABINET,
                  bridge.FLEET_POSES}
        self.assertEqual(topics, set(bridge.QOS))
        self.assertEqual(topics, set(bridge.SCHEMAS))
        self.assertEqual(("reliable", "transient_local", 500), bridge.QOS[bridge.EVENTS])
        self.assertEqual(("reliable", "volatile", 1), bridge.QOS[bridge.BELT])


class BeltTests(unittest.TestCase):
    def model(self):
        return belt.BeltModel(length=1.2, width=0.2, end_zone_length=0.15, settle_speed=0.01, settle_time_s=0.3)

    def test_dispense_rule_order(self):
        model = self.model()
        self.assertEqual(belt.NOT_READY, model.decide_dispense("ord-0001", ready=False, known_order=False))
        self.assertEqual(belt.UNKNOWN_ORDER, model.decide_dispense("x", ready=True, known_order=False))
        self.assertEqual("", model.decide_dispense("ord-0001", ready=True, known_order=True))
        self.assertEqual([belt.DISPENSED], model.accept("r001-0001", "ord-0001", 0.0))
        self.assertEqual(belt.BELT_OCCUPIED, model.decide_dispense("ord-0002", ready=True, known_order=True))

    def test_pool_exhausted_comes_after_contract_rejections(self):
        model = self.model()
        self.assertEqual(belt.POOL_EXHAUSTED, model.decide_dispense("ord-0001", True, True, pouch_available=False))
        self.assertEqual(belt.UNKNOWN_ORDER, model.decide_dispense("x", True, False, pouch_available=False))
        self.assertIn(belt.POOL_EXHAUSTED, belt.DISPENSE_REJECTIONS)  # contract 2.1 since 9/24

    def test_first_epoch_is_one(self):
        self.assertEqual(1, belt.FIRST_EPOCH)
        source = (STANDALONE / "pharmacy_stage.py").read_text()
        self.assertIn('"epoch": beltlib.FIRST_EPOCH', source)
        self.assertNotIn("is exhausted; raise --pouch-pool", source)

    def test_stage_stand_in_and_reset_scope(self):
        args = STAGE.parse_args(["--mode", "ros", "--ros-pick-stand-in-s", "2"])
        self.assertEqual(2.0, args.ros_pick_stand_in_s)
        self.assertEqual(0.0, STAGE.parse_args([]).ros_pick_stand_in_s)
        source = (STANDALONE / "pharmacy_stage.py").read_text()
        reset_body = source[source.index("def do_reset"):source.index("def handle_ros")]
        for needle in ("set_joint_positions(arm[\"home_positions\"])", "cell.robot.set_joint_positions",
                       "obj.set_world_pose", "park(index)", "set_belt(0.0)"):
            self.assertIn(needle, reset_body)

    def test_travel_stop_settle_then_at_end_once(self):
        model = self.model()
        model.accept("r001-0001", "ord-0001", 0.0)
        events, notes = model.observe((0.5, 0.0, 0.0), 0.15, 1.0)
        self.assertEqual(([], []), (events, notes))
        self.assertTrue(model.running)
        events, notes = model.observe((1.10, 0.0, 0.0), 0.15, 2.0)
        self.assertEqual(["stop_belt"], notes)
        self.assertFalse(model.at_end)
        self.assertEqual([], model.observe((1.12, 0.0, 0.0), 0.005, 2.1)[0])
        self.assertEqual([belt.POUCH_AT_END], model.observe((1.12, 0.0, 0.0), 0.004, 2.5)[0])
        self.assertEqual({"occupied": True, "at_end": True, "order_id": "ord-0001"}, model.state())
        self.assertEqual([], model.observe((1.12, 0.0, 0.0), 0.0, 3.0)[0])

    def test_moving_again_restarts_settling(self):
        model = self.model()
        model.accept("r", "ord-0001", 0.0)
        model.observe((1.10, 0.0, 0.0), 0.2, 1.0)
        model.observe((1.12, 0.0, 0.0), 0.005, 1.1)
        model.observe((1.13, 0.0, 0.0), 0.05, 1.3)
        self.assertEqual([], model.observe((1.13, 0.0, 0.0), 0.0, 1.5)[0])
        self.assertEqual([belt.POUCH_AT_END], model.observe((1.13, 0.0, 0.0), 0.0, 1.8)[0])

    def test_pouch_off_the_belt_clears_state(self):
        model = self.model()
        model.accept("r", "ord-0001", 0.0)
        _events, notes = model.observe((1.5, 0.0, 0.0), 0.3, 1.0)
        self.assertEqual(["pouch_left_belt"], notes)
        self.assertEqual({"occupied": False, "at_end": False, "order_id": ""}, model.state())
        model.accept("r", "ord-0002", 2.0)
        self.assertEqual(["pouch_left_belt"], model.observe(None, 0.0, 2.1)[1])

    def test_at_end_timeout_note_once(self):
        model = self.model()
        model.accept("r", "ord-0001", 0.0)
        self.assertEqual(["at_end_timeout"], model.observe((0.1, 0.0, 0.0), 0.0, 20.5)[1])
        self.assertEqual([], model.observe((0.1, 0.0, 0.0), 0.0, 21.0)[1])

    def test_belt_frame_follows_yaw(self):
        along, lateral, up = belt.belt_frame((0.0, 1.0, 0.5), (0.0, 0.0, 0.1), 1.5707963267948966)
        self.assertAlmostEqual(1.0, along)
        self.assertAlmostEqual(0.0, lateral)
        self.assertAlmostEqual(0.4, up)

    def test_invalid_geometry(self):
        with self.assertRaises(ValueError):
            belt.BeltModel(length=1.0, width=0.2, end_zone_length=2.0)


class PouchTests(unittest.TestCase):
    def test_same_seed_epoch_index_gives_same_spawn(self):
        first = pouch.sample_spawn(pouch.spawn_rng(7, 3, 2), (0.05, 0.15), (-0.04, 0.04), (-0.3, 0.3))
        again = pouch.sample_spawn(pouch.spawn_rng(7, 3, 2), (0.05, 0.15), (-0.04, 0.04), (-0.3, 0.3))
        other = pouch.sample_spawn(pouch.spawn_rng(8, 3, 2), (0.05, 0.15), (-0.04, 0.04), (-0.3, 0.3))
        self.assertEqual(first, again)
        self.assertNotEqual(first, other)
        self.assertTrue(0.05 <= first[0] <= 0.15 and -0.04 <= first[1] <= 0.04 and -0.3 <= first[2] <= 0.3)

    def test_order_ids_from_pool_text(self):
        text = "orders:\n  - {order_id: ord-0001, bed: a}\n  - {order_id: 'ord-0002'}\n# order_id: bad\n"
        self.assertEqual({"ord-0001", "ord-0002"}, pouch.order_ids_from_pool_text(text))
        repo_pool = Path(__file__).resolve().parents[2] / "src/rokey_p3_orchestrator/config/order_pool.yaml"
        if repo_pool.is_file():
            self.assertIn("ord-0001", pouch.order_ids_from_pool_text(repo_pool.read_text()))

    def test_belt_to_world_and_prim_name(self):
        x, y, z = pouch.belt_to_world((1.0, 2.0, 0.1), 0.0, 0.2, -0.05, 0.03)
        self.assertEqual((1.2, 1.95, 0.13), (round(x, 6), round(y, 6), round(z, 6)))
        self.assertEqual("Pouch_ord_0001_0003", pouch.pouch_prim_name("ord-0001", 3))


class LayoutTests(unittest.TestCase):
    def setUp(self):
        from p3sim import layout
        self.layout = layout
        self.room = layout.default_layout()

    def test_shelf_cells_sit_on_boards(self):
        boxes, cells = self.layout.shelf_boxes((0.0, 1.0, 0.0), 3, 2, (0.3, 0.4), 0.3, plinth=0.2)
        self.assertEqual({(0, 0), (0, 1), (0, 2), (1, 0), (1, 1), (1, 2)}, set(cells))
        self.assertEqual((0.15, 1.15, 0.2), tuple(round(v, 6) for v in cells[(0, 0)]))
        self.assertAlmostEqual(0.6, cells[(1, 2)][2])
        self.assertEqual(3 + 2, len(boxes))  # back, two sides, two boards; open top
        closed, _cells = self.layout.shelf_boxes((0.0, 1.0, 0.0), 3, 2, (0.3, 0.4), 0.3, plinth=0.2, open_top=False)
        self.assertEqual(3 + 3, len(closed))

    def test_dispenser_inlets_face_the_rail_and_outlet_faces_the_corridor(self):
        _boxes, inlets, outlet = self.layout.dispenser_boxes((1.0, 1.0, 0.0), (0.7, 0.6, 1.6), (0.1, 0.1, 0.12), 0.85,
                                                              0.01, 0.75, (0.08, 0.2, 0.12))
        self.assertLess(inlets["a"][0], inlets["b"][0])
        self.assertLess(inlets["a"][1], 1.0 - 0.3)  # in front of the -y face
        self.assertEqual((1.35, 1.0, 0.75), outlet)

    def test_wall_leaves_the_belt_opening_and_door_empty(self):
        boxes = self.layout.wall_boxes(2.7, (-1.5, 1.6), 2.4, 0.1, (0.85, 1.15), (0.6, 0.95), -0.6, 0.9)
        names = {box.name for box in boxes}
        self.assertIn("Wall_belt_below", names)
        self.assertIn("Wall_door_above", names)
        for box in boxes:
            low = box.center[1] - box.size[1] / 2
            high = box.center[1] + box.size[1] / 2
            z_low = box.center[2] - box.size[2] / 2
            z_high = box.center[2] + box.size[2] / 2
            if box.name.startswith("Wall_belt"):
                continue
            self.assertFalse(low < 1.0 < high and z_low < 0.75 < z_high, box.name)  # belt passes
            self.assertFalse(low < -0.6 < high and z_low < 1.0 < z_high, box.name)  # door is open

    def test_rail_target_clamps_to_strokes(self):
        x, y = self.layout.rail_target((0.5, 0.6), (0.0, 0.5), (-1.2, 1.2), (-0.3, 0.3))
        self.assertEqual((0.5, 0.1), (round(x, 6), round(y, 6)))
        self.assertEqual((1.2, 0.3), self.layout.rail_target((3.0, 2.0), (0.0, 0.5), (-1.2, 1.2), (-0.3, 0.3)))


class RailRefillPlanTests(unittest.TestCase):
    def setUp(self):
        from p3sim import layout
        self.layout = layout
        room = layout.default_layout()
        _boxes, cells = layout.shelf_boxes(room["shelf_origin"], room["shelf_cols"], room["shelf_rows"],
                                           room["shelf_cell"], room["shelf_depth"], room["shelf_plinth"])
        _b, self.inlets, _o = layout.dispenser_boxes(room["dispenser_origin"], room["dispenser_size"],
                                                     room["inlet_size"], room["inlet_height"], room["inlet_wall"],
                                                     room["belt_top"], room["outlet_size"], room["inlet_gap"])
        cell = cells[room["pick_cell"]]
        self.canister = (cell[0], cell[1], cell[2] + room["canister_size"][2] / 2)
        self.room = room
        self.limits = ((-room["rail_x_stroke"] / 2, room["rail_x_stroke"] / 2),
                       tuple(room["rail_y_limits"]))
        self.plans = {letter: layout.plan_rail_refill(self.canister, room["canister_size"][2], self.inlets[letter],
                                                      room["inlet_size"], room["inlet_wall"], room["rail_origin"],
                                                      room["reach_offset"], *self.limits, room["clearance"],
                                                      room["grip_depth"], shelf_front_y=room["shelf_origin"][1],
                                                      pull_margin=0.12, inlet_offset=room["inlet_offset"])
                      for letter in ("a", "b")}
        self.plan = self.plans["a"]

    def test_phase_order_and_grippers(self):
        self.assertEqual(["rail_to_shelf", "shelf_front", "above_canister", "descend", "grasp", "lift", "pull_out",
                          "raise", "rail_to_inlet", "above_inlet", "insert", "release", "retreat", "rail_home"],
                         [s[0] for s in self.plan])
        self.assertEqual("close", {s[0]: s[3] for s in self.plan}["rail_to_inlet"])  # carries the canister
        self.assertEqual({"rail"}, {s[1] for s in self.plan if s[0].startswith("rail_")})

    def test_rail_targets_stay_within_strokes_and_park_the_base_near_the_target(self):
        for phase, kind, target, _g in self.plan:
            if kind == "rail":
                (xl, xh), (yl, yh) = self.limits
                self.assertTrue(xl <= target[0] <= xh and yl <= target[1] <= yh, phase)
        steps = {s[0]: s for s in self.plan}
        ox, oy, _oz = self.room["rail_origin"]
        base = (ox + steps["rail_to_shelf"][2][0], oy + steps["rail_to_shelf"][2][1])
        self.assertLess(((self.canister[0] - base[0]) ** 2 + (self.canister[1] - base[1]) ** 2) ** 0.5, 0.6)

    def test_rail_moves_only_with_the_canister_outside_the_shelf(self):
        steps = [s[0] for s in self.plan]
        front_y = self.room["shelf_origin"][1]
        tcp_before_rail = {s[0]: s[2] for s in self.plan}
        self.assertLess(tcp_before_rail["pull_out"][1], front_y)
        self.assertEqual(steps.index("pull_out") + 2, steps.index("rail_to_inlet"))
        self.assertEqual(tcp_before_rail["pull_out"][2], tcp_before_rail["lift"][2])  # straight out along y

    def test_without_front_there_is_no_pull_out(self):
        plan = self.layout.plan_rail_refill(self.canister, 0.12, self.inlets["a"], (0.1, 0.1, 0.12), 0.01,
                                            (0, 0.2, 0), (0, 0.4), (-1.2, 1.2), (-0.3, 0.3), 0.06, 0.05)
        self.assertNotIn("pull_out", [s[0] for s in plan])
        self.assertIn("raise", [s[0] for s in plan])

    def test_rail_targets_stay_inside_the_limits(self):
        (xl, xh), (yl, yh) = self.limits
        for _phase, kind, target, _g in self.plan:
            if kind == "rail":
                self.assertTrue(xl + 0.02 - 1e-9 <= target[0] <= xh - 0.02 + 1e-9)
                self.assertTrue(yl + 0.02 - 1e-9 <= target[1] <= yh - 0.02 + 1e-9)

    def test_every_arm_target_is_within_reach_and_off_the_base_axis(self):
        # 9/17 d38a2c2: above_canister stayed 5 cm short with the old rail. Distance check only (no IK): shoulder to
        # flange under 0.85 m (M0609 reach 0.9 m) and at least 0.1 m sideways from the base axis.
        for letter, plan in self.plans.items():
            for phase, distance, horizontal in self.layout.plan_reach(plan, self.room["rail_origin"],
                                                                        self.room["carriage_height"]):
                self.assertLess(distance, 0.85, (letter, phase))
                self.assertGreaterEqual(horizontal, 0.1, (letter, phase))

    def test_heights_split_shelf_carry_and_empty(self):
        steps = {s[0]: s[2] for s in self.plan}
        top = self.canister[2] + self.room["canister_size"][2] / 2
        self.assertAlmostEqual(top + self.room["clearance"], steps["above_canister"][2])
        self.assertEqual(steps["pull_out"][:2], steps["raise"][:2])
        self.assertGreater(steps["raise"][2], steps["pull_out"][2])  # rises only once out of the shelf
        self.assertEqual(steps["raise"][2], steps["above_inlet"][2])
        self.assertEqual(steps["retreat"][2], steps["above_inlet"][2])  # d38a2c2 inlet side: retreat at carry z

    def test_inlet_side_parks_the_base_where_d38a2c2_did(self):
        # 9/17 7ae2879: shelf side reached with the new standoff, inlet side 6 cm short; d38a2c2 inserted within
        # 0.0033 m with origin y 0.2 and standoff (0, 0.40). Same base world position for the inlets now.
        ox, oy, _oz = self.room["rail_origin"]
        for letter, plan in self.plans.items():
            rail = {s[0]: s[2] for s in plan}["rail_to_inlet"]
            inlet = self.inlets[letter]
            self.assertAlmostEqual(inlet[0] - 0.0, ox + rail[0], places=9)
            self.assertAlmostEqual(inlet[1] - self.room["inlet_offset"][1], oy + rail[1], places=9)
            self.assertAlmostEqual(-0.05, rail[1], places=9)  # same rail park as f796210 (base world y 0.25)
        shelf = {s[0]: s[2] for s in self.plan}["rail_to_shelf"]
        self.assertAlmostEqual(self.canister[0] - 0.15, ox + shelf[0], places=9)

    def test_shelf_park_is_where_the_rail_stopped_and_still_reached(self):
        # 9/17 4c07d8f/7ae2879/3b114c4: first rail_to_shelf stopped with the base at world y 0.48, shelf phases reached.
        rail = {s[0]: s[2] for s in self.plan}["rail_to_shelf"]
        self.assertAlmostEqual(0.48, self.room["rail_origin"][1] + rail[1], places=9)

    def test_ur5_world_joints_are_moved_to_the_pedestal(self):
        source = (Path(__file__).resolve().parents[1] / "standalone" / "p3sim" / "ur5_cell.py").read_text()
        build = source.split("    def build(self):", 1)[1].split("\n    def ", 1)[0]
        self.assertLess(build.index("self._pin_world_joints("), build.index("SingleArticulation(prim_path"))

    def test_rail_y_lower_limit_keeps_the_carriage_off_the_negative_side(self):
        # 9/17 7ae2879: with lower -0.33 the carriage got stuck at y -0.25.
        self.assertGreaterEqual(self.room["rail_y_limits"][0], -0.10)
        for plan in self.plans.values():
            for _phase, kind, target, _g in plan:
                if kind == "rail":
                    self.assertGreaterEqual(target[1], self.room["rail_y_limits"][0] + 0.02 - 1e-9)

    def test_heights_can_be_overridden(self):
        room = self.room
        plan = self.layout.plan_rail_refill(self.canister, room["canister_size"][2], self.inlets["a"],
                                            room["inlet_size"], room["inlet_wall"], room["rail_origin"],
                                            room["reach_offset"], *self.limits, room["clearance"], room["grip_depth"],
                                            shelf_front_y=room["shelf_origin"][1], carry_z=1.25, retreat_z=1.05)
        steps = {s[0]: s[2] for s in plan}
        self.assertEqual(1.25, steps["above_inlet"][2])
        self.assertEqual(1.25, steps["raise"][2])
        self.assertEqual(1.05, steps["retreat"][2])

    def test_retreat_backs_off_toward_the_rail(self):
        steps = {s[0]: s[2] for s in self.plan}
        self.assertLess(steps["retreat"][1], steps["insert"][1])

    def test_phase_tolerances(self):
        tol = self.layout.phase_tolerance
        self.assertEqual(0.01, tol("rail_to_inlet", "rail", 0.01, 0.01, 0.03))
        self.assertEqual(0.03, tol("above_canister", "tcp", 0.01, 0.01, 0.03))
        self.assertEqual(0.01, tol("insert", "tcp", 0.01, 0.01, 0.03))

    def test_carry_clears_inlet_rim_and_insert_lands_in_the_inlet(self):
        steps = {s[0]: s[2] for s in self.plan}
        size = self.room["canister_size"][2]
        below_tcp = size - self.room["grip_depth"]
        inlet = self.inlets["a"]
        rim = inlet[2] + self.room["inlet_size"][2] / 2
        self.assertGreaterEqual(steps["raise"][2] - below_tcp, rim + self.room["clearance"] - 1e-9)
        self.assertGreaterEqual(steps["above_inlet"][2] - below_tcp, rim + self.room["clearance"] - 1e-9)
        bottom = steps["insert"][2] - below_tcp
        self.assertGreater(bottom, inlet[2] - self.room["inlet_size"][2] / 2)
        self.assertLess(bottom, rim)
        self.assertEqual((inlet[0], inlet[1]), steps["insert"][:2])


class PouchPoolTests(unittest.TestCase):
    def test_acquire_release_reuses_lowest_free(self):
        pool = pouch.PouchPool(2)
        self.assertEqual(0, pool.acquire("ord-0001"))
        self.assertEqual(1, pool.acquire("ord-0002"))
        self.assertIsNone(pool.acquire("ord-0003"))
        pool.release(0)
        self.assertEqual(0, pool.acquire("ord-0003"))
        pool.release_all()
        self.assertEqual([0, 1], pool.free)
        with self.assertRaises(ValueError):
            pouch.PouchPool(0)

    def test_labelled_pool_prefers_the_matching_pouch(self):
        labels = pouch.pool_labels({"ord-0002", "ord-0001"}, 5)
        self.assertEqual(["ord-0001", "ord-0002", "ord-0001", "ord-0002", "ord-0001"], labels)
        pool = pouch.PouchPool(5, labels)
        self.assertEqual(1, pool.acquire("ord-0002"))
        self.assertEqual(3, pool.acquire("ord-0002"))
        self.assertEqual(0, pool.acquire("ord-0002"))  # no ord-0002 or blank left: any free pouch
        with self.assertRaises(ValueError):
            pouch.PouchPool(2, ["ord-0001"])
        self.assertEqual([None, None], pouch.pool_labels(set(), 2))

    def test_qr_generator_imports_without_opencv_and_reads_ids(self):
        spec = importlib.util.spec_from_file_location("make_qr_textures", STANDALONE / "make_qr_textures.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        args = module.build_parser().parse_args(["--order-pool", "x.yaml", "--out", "/tmp/qr"])
        self.assertEqual((512, 4), (args.pixels, args.border))
        try:
            import cv2  # noqa: F401
        except ImportError:
            return
        import tempfile

        with tempfile.TemporaryDirectory() as out:
            pool = Path(out) / "pool.yaml"
            pool.write_text("orders:\n  - {order_id: ord-0007}\n")
            with contextlib.redirect_stdout(io.StringIO()) as printed:
                self.assertEqual(0, module.main(["--order-pool", str(pool), "--out", out]))
            self.assertIn("decode=ok", printed.getvalue())

    def test_parking_row(self):
        self.assertEqual([(2.2, -1.3, 0.005), (2.2, -1.15, 0.005)],
                         [tuple(round(v, 6) for v in spot) for spot in pouch.parking_positions(2, (2.2, -1.3), 0.15,
                                                                                               0.005)])

    def test_stage_never_deletes_or_creates_prims_while_running(self):
        source = (STANDALONE / "pharmacy_stage.py").read_text()
        self.assertNotIn("RemovePrim", source)
        self.assertNotIn("SetCustomData", source)
        self.assertNotIn("GripAttach", source)

    def test_stage_subscribes_and_handles_pick_notice(self):
        source = (STANDALONE / "pharmacy_stage.py").read_text()
        for needle in ("bridge.PICK_NOTICE: []", "ros.take(bridge.PICK_NOTICE)", "bridge.pick_notice_applies(",
                       'remove_pouch("ros_pick_notice")', "ros pick_notice ignored"):
            self.assertIn(needle, source)

    def test_timeline_stop_is_logged_and_recovered(self):
        source = (STANDALONE / "pharmacy_stage.py").read_text()
        for needle in ('for name in ("PLAY", "PAUSE", "STOP")', 'timeline_flags["stopped"]', "world.play()",
                       'reason = "physics_view_lost"', "exit_code = 3", "refill respawn_retry"):
            self.assertIn(needle, source)

    def test_timeline_stop_recovers_every_articulation_the_loop_drives(self):
        """9/24 회차37: STOP 복구가 M0609·UR5 셀만 다시 잡고 합본 AMR 은 빼먹어 odom·joint_states 가 멈췄다."""
        source = (STANDALONE / "pharmacy_stage.py").read_text()
        block = source.split('log(f"physics_view lost by timeline STOP', 1)[1]
        block = block.split('log(f"physics_view recovered', 1)[0]
        for needle in ('arm["articulation"].initialize()', "cell.robot.initialize()", "amr.articulation.initialize()",
                       "amr.articulation.get_joint_positions() is not None", "amr.reset()"):
            self.assertIn(needle, block)

    def test_qr_quads_are_not_nested_under_pouch_gprims(self):
        source = (STANDALONE / "pharmacy_stage.py").read_text()
        self.assertIn('f"{STAGE_ROOT}/QrFaces/Qr_{index:02d}"', source)
        self.assertNotIn('add_top_texture(stage, f"{POUCH_ROOT}', source)


class LoadingCellTests(unittest.TestCase):
    def setUp(self):
        from p3sim import layout
        self.layout = layout
        self.room = layout.default_layout()

    def test_deck_slots_in_a_row(self):
        boxes, slots = self.layout.deck_boxes((3.3, 0.05, 0.45), 5, (0.14, 0.11, 0.04), 0.008)
        self.assertEqual(5, len(slots))
        self.assertEqual(1 + 5 * 5, len(boxes))  # plate + five open boxes
        pitches = {round(slots[i + 1][0] - slots[i][0], 6) for i in range(4)}
        self.assertEqual({0.16}, pitches)
        self.assertAlmostEqual(3.3, (slots[0][0] + slots[-1][0]) / 2)

    def test_suction_plan(self):
        room = self.room
        _boxes, slots = self.layout.deck_boxes(room["deck_center"], room["deck_count"], room["deck_slot_size"],
                                               room["deck_wall"])
        plan = self.layout.plan_suction_pick_place((2.87, 1.0, 0.755), 0.01, slots[0], room["deck_slot_size"],
                                                   room["deck_wall"], 0.06, room["ur5_ready"])
        self.assertEqual(["above_pouch", "touch", "suck", "lift", "above_slot", "lower", "drop", "retreat", "ready"],
                         [s[0] for s in plan])
        steps = {s[0]: s for s in plan}
        self.assertAlmostEqual(0.76, steps["touch"][2][2])  # suction face on the pouch top
        self.assertEqual("on", steps["lift"][3])
        self.assertEqual("off", steps["drop"][3])
        slot_top = slots[0][2] + room["deck_slot_size"][2] / 2
        self.assertGreater(steps["above_slot"][2][2] - 0.01, slot_top)  # carried pouch clears the slot rim
        self.assertLess(steps["lower"][2][2] - 0.01, slot_top)  # ends inside the slot

    def test_stage_ur5_arguments(self):
        args = STAGE.parse_args(["--ur5"])
        self.assertTrue(args.ur5)
        self.assertEqual(5, args.deck_count)
        self.assertGreaterEqual(args.pouch_pool, args.deck_count + 1)


class SensorNamingTests(unittest.TestCase):
    def setUp(self):
        from p3sim import sensors
        self.sensors = sensors

    def test_frames_carry_the_robot_namespace(self):
        self.assertEqual("amr_1/hand_camera_optical", self.sensors.frame("/amr_1", "hand_camera_optical"))
        self.assertEqual(["amr_1/deck_slot_1", "amr_1/deck_slot_2"], self.sensors.deck_frames("/amr_1", 2))
        self.assertEqual(6, len(self.sensors.UR5_LINKS))  # the end prim is searched separately

    def test_end_link_search_order(self):
        pick = self.sensors.pick_end_link
        self.assertEqual("tool0", pick({"tool0", "flange", "wrist_3_link"}))
        # 9/17 master02: Isaac 5.1 ur5.usd has flange and ft_frame but no tool0.
        self.assertEqual("flange", pick({"base_link", "flange", "ft_frame", "wrist_3_link"}))
        self.assertEqual("wrist_3_link", pick({"wrist_3_link"}))
        self.assertIsNone(pick({"base_link"}))

    def test_flange_to_tool_rotation_points_tool_z_along_flange_x(self):
        from p3sim import geometry

        tool_z_in_flange = geometry.quat_rotate(self.sensors.END_TO_TOOL["flange"], (0.0, 0.0, 1.0))
        for expected, actual in zip((1.0, 0.0, 0.0), tool_z_in_flange, strict=True):
            self.assertAlmostEqual(expected, actual)

    def test_frame_skip_keeps_rate_at_or_below_limit(self):
        for render_hz in (60.0, 30.0, 50.0, 10.0, 120.0):
            skip = self.sensors.frame_skip(render_hz, 10.0)
            self.assertLessEqual(self.sensors.published_rate(render_hz, skip), 10.0 + 1e-9)
            if skip:
                self.assertGreater(self.sensors.published_rate(render_hz, skip - 1), 10.0)
        self.assertEqual(5, self.sensors.frame_skip(60.0, 10.0))
        with self.assertRaises(ValueError):
            self.sensors.frame_skip(60.0, 0.0)

    def test_sensor_qos_is_best_effort_depth_two(self):
        qos = json.loads(self.sensors.SENSOR_QOS_DEPTH2)
        self.assertEqual(("keepLast", 2, "bestEffort", "volatile"),
                         (qos["history"], qos["depth"], qos["reliability"], qos["durability"]))
        self.assertEqual({"history", "depth", "reliability", "durability", "deadline", "lifespan", "liveliness",
                          "leaseDuration"}, set(qos))


class ResetTests(unittest.TestCase):
    def test_injection(self):
        self.assertEqual((True, ""), reset.ResetInjection().outcome())
        self.assertEqual((False, "injected_failure"), reset.ResetInjection(fail=True).outcome())
        self.assertEqual(0.0, reset.ResetInjection(delay_s=-1).delay_s)

    def test_epoch_note_and_steps(self):
        self.assertIsNone(reset.epoch_note(2, 3))
        self.assertIn("not greater", reset.epoch_note(3, 3))
        self.assertEqual("stop_belt", reset.STEPS[0])
        self.assertEqual("set_epoch", reset.STEPS[-1])

    def test_pose_line_reads_dock_error_from_the_dummy_axes(self):
        """#696 제안 4: dummy 3축 원점이 출발 도크라 값 자체가 도크 자세 오차다. 없는 팔은 `-`."""
        self.assertAlmostEqual(0.3, reset.max_joint_error([0.0, 1.0], [0.1, 0.7]))
        self.assertIsNone(reset.max_joint_error(None, [0.0]))
        self.assertIsNone(reset.max_joint_error([0.0], [0.0, 0.0]))
        line = reset.pose_line(3, (0.003, 0.004, -0.02), {"amr_arm": 0.0123, "m0609": None})
        self.assertEqual("reset pose epoch=3 after_s=1.0 amr_dxy=0.0050 amr_dyaw=0.0200 "
                         "amr_arm_max_rad=0.0123 m0609_max_rad=-", line)
        self.assertEqual("reset pose epoch=1 after_s=1.0 amr_dxy=- amr_dyaw=-", reset.pose_line(1, None, {}))


class CommonTests(unittest.TestCase):
    def test_keep_running_and_schedule(self):
        self.assertFalse(common.keep_running(False, False, False))
        self.assertTrue(common.keep_running(False, False, True))
        self.assertEqual(5.0, common.next_publish_time(1.0, 5.0, 5.0))
        self.assertAlmostEqual(1.2, common.next_publish_time(1.0, 1.05, 5.0))


if __name__ == "__main__":
    unittest.main()


class RailGeometryArgsTest(unittest.TestCase):
    def test_geometry_values_are_arguments(self):
        args = STAGE.parse_args(["--rail-origin-y", "0.2", "--inlet-standoff", "0.05", "0.45", "--shelf-standoff",
                                 "0.1", "0.35", "--carry-z", "1.2", "--retreat-z", "1.1", "--rail-y-limits", "-0.05",
                                 "0.30", "--rail-drive", "1e5", "1e4", "5000"])
        self.assertEqual(0.2, args.rail_origin[1])
        self.assertEqual([0.05, 0.45], args.inlet_standoff)
        self.assertEqual([0.1, 0.35], args.reach_offset)
        self.assertEqual((1.2, 1.1), (args.carry_z, args.retreat_z))
        self.assertEqual(0.10, STAGE.parse_args([]).retreat_back)
        self.assertEqual(0.0, STAGE.parse_args(["--retreat-back", "0"]).retreat_back)
        self.assertEqual([-0.05, 0.30], args.rail_y_limits)
        self.assertEqual(5000.0, args.rail_drive[2])

    def test_defaults_leave_heights_computed(self):
        args = STAGE.parse_args([])
        self.assertIsNone(args.carry_z)
        self.assertIsNone(args.retreat_z)
        self.assertEqual(0.30, args.rail_origin[1])

    def test_rail_y_limits_must_be_ordered(self):
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            STAGE.parse_args(["--rail-y-limits", "0.3", "-0.1"])


class Ur5TcpAndCameraArgsTest(unittest.TestCase):
    def test_quat_from_matrix_round_trips(self):
        import math

        from p3sim import geometry

        for q in [(1.0, 0.0, 0.0, 0.0), (0.0, 1.0, 0.0, 0.0), (0.0, 0.0, 1.0, 0.0), (0.0, 0.0, 0.0, 1.0),
                  (0.5, 0.5, 0.5, 0.5), (math.cos(0.3), 0.0, 0.0, math.sin(0.3))]:
            columns = [geometry.quat_rotate(q, axis) for axis in ((1, 0, 0), (0, 1, 0), (0, 0, 1))]
            rows = [[columns[c][r] for c in range(3)] for r in range(3)]
            back = geometry.quat_from_matrix(rows)
            sign = 1.0 if sum(a * b for a, b in zip(q, back, strict=True)) >= 0 else -1.0
            for a, b in zip(q, back, strict=True):
                self.assertAlmostEqual(a, sign * b, places=9)

    def test_camera_and_ur5_speed_defaults(self):
        args = STAGE.parse_args([])
        self.assertEqual([640, 480], args.camera_resolution)  # 9/17 7ae2879: 1280x720 gave 2.9 Hz
        self.assertEqual(0.003, args.ur5_tcp_speed)
        self.assertEqual(0.9, args.tcp_max_speed)  # 재범 9/24: 90% of the M0609 1.0 m/s TCP spec(실습1 부터 80%)

    def test_ur5_tcp_reads_forward_kinematics(self):
        source = (Path(__file__).resolve().parents[1] / "standalone" / "p3sim" / "ur5_cell.py").read_text()
        body = source.split("    def tcp(self):", 1)[1].split("\n    def ", 1)[0]
        self.assertIn("compute_end_effector_pose", body)
        self.assertNotIn("self.tool.get_world_pose", body)


class PresetTest(unittest.TestCase):
    def test_no_preset_keeps_plain_defaults(self):
        args = STAGE.parse_args([])
        self.assertIsNone(args.preset)
        self.assertEqual("selfdemo", args.mode)
        self.assertFalse(args.ros_refill_selfdemo)

    def test_demo_ros_sets_the_adapter_demo(self):
        args = STAGE.parse_args(["--preset", "demo-ros"])
        self.assertEqual("ros", args.mode)
        self.assertTrue(args.ros_refill_selfdemo)
        self.assertEqual(5.0, args.ros_pick_stand_in_s)
        self.assertEqual(0, args.refill_loop)
        self.assertEqual(STAGE.VERIFIED_RAIL_DRIVE, args.rail_drive)
        self.assertEqual([], STAGE.validate(args))

    def test_selfdemo_refill(self):
        args = STAGE.parse_args(["--preset", "selfdemo-refill"])
        self.assertEqual(("selfdemo", 0, 0), (args.mode, args.loop, args.refill_loop))
        self.assertEqual([1e5, 1e4, 5e4], args.rail_drive)

    def test_explicit_arguments_win_in_any_order(self):
        for argv in (["--preset", "demo-ros", "--ros-pick-stand-in-s", "2", "--rail-drive", "1e7", "1e5", "1e8"],
                     ["--ros-pick-stand-in-s", "2", "--rail-drive", "1e7", "1e5", "1e8", "--preset", "demo-ros"]):
            args = STAGE.parse_args(argv)
            self.assertEqual(2.0, args.ros_pick_stand_in_s)
            self.assertEqual([1e7, 1e5, 1e8], args.rail_drive)
            self.assertEqual("ros", args.mode)

    def test_the_hospital_presets_use_the_soft_rail_drive(self):
        """병원은 `VERIFIED_RAIL_DRIVE` 다(작전 9/23). 굳은 (1e7, 1e5, 1e8) 이 틱을 늘렸다 —
        회차 94f19fb-rail: `loop stall` 5줄 → 0줄, rtf 0.354 → 0.386, 보충·집기·내려놓기는 그대로 통과."""
        for preset in ("hospital", "hospital-full"):
            args = STAGE.parse_args(["--preset", preset])
            self.assertEqual(STAGE.VERIFIED_RAIL_DRIVE, args.rail_drive, preset)
        # 빈월드·조제실은 그대로다 — 이 카드는 병원만 건드린다.
        for preset in ("demo-ros-refill-v2", "emptyworld-loop", "hospital-v2"):
            self.assertEqual([1e7, 1e5, 1e8], STAGE.parse_args(["--preset", preset]).rail_drive, preset)

    def test_the_rail_follow_warning_has_a_default(self):
        """레일이 명령을 얼마나 따라가는지 재는 줄. 부드러운 드라이브의 대가를 본다(9/23 까지 미측정)."""
        self.assertEqual(0.02, STAGE.parse_args([]).rail_follow_warn_m)
        self.assertEqual(0.05, STAGE.parse_args(["--rail-follow-warn-m", "0.05"]).rail_follow_warn_m)

    def test_presets_only_name_real_arguments(self):
        known = set(vars(STAGE.parse_args([])))
        for name, values in STAGE.PRESETS.items():
            self.assertLessEqual(set(values), known, name)

    def test_unknown_preset_is_rejected(self):
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            STAGE.parse_args(["--preset", "nope"])

    def test_startup_line_names_preset_and_all_arguments(self):
        args = STAGE.parse_args(["--preset", "demo-ros", "--seed", "7"])
        line = STAGE.startup_line(args)
        self.assertTrue(line.startswith("preset=demo-ros resolved_args={"))
        resolved = json.loads(line.split("resolved_args=", 1)[1])
        self.assertEqual(set(vars(args)), set(resolved))
        self.assertEqual(("ros", 7, 5.0), (resolved["mode"], resolved["seed"], resolved["ros_pick_stand_in_s"]))
        self.assertTrue(STAGE.startup_line(STAGE.parse_args([])).startswith("preset=- "))

    def test_startup_line_is_logged_first(self):
        source = (Path(__file__).resolve().parents[1] / "standalone" / "pharmacy_stage.py").read_text()
        body = source.split("def run(args):", 1)[1]
        self.assertTrue(body.lstrip().startswith("log(startup_line(args))"))


class TextFilesTest(unittest.TestCase):
    def test_no_nul_bytes_in_sim_text_files(self):
        # 9/17: a file-writing tool turned the escape in `tr '\0' '\n'` into a real NUL byte in sim/README.md, and grep
        # then treated the README as binary.
        root = Path(__file__).resolve().parents[1]
        suffixes = {".md", ".py", ".yaml", ".yml", ".json", ".txt", ".toml", ".cfg", ".sh"}
        found = [str(path.relative_to(root)) for path in root.rglob("*")
                 if path.is_file() and path.suffix in suffixes and "__pycache__" not in path.parts
                 and "outputs" not in path.parts and b"\x00" in path.read_bytes()]
        self.assertEqual([], found)


class ShutdownPathTest(unittest.TestCase):
    def setUp(self):
        self.source = (Path(__file__).resolve().parents[1] / "standalone" / "pharmacy_stage.py").read_text()

    def test_no_clock_graph_reads_after_the_loop(self):
        after_loop = self.source.split("        elapsed = time.monotonic() - started", 1)[1]
        tail = after_loop.split("    except Exception", 1)[0]
        self.assertNotIn("sim_now()", tail)
        self.assertNotIn("read_graph_sim_time", tail)
        self.assertIn('timeline_flags["closing"] = True', tail)
        self.assertIn('sim_clock["last"] - sim_started', tail)

    def test_timeline_callback_skips_the_graph_while_closing(self):
        callback = self.source.split("        def on_timeline(name):", 1)[1].split("\n        timeline_events", 1)[0]
        self.assertLess(callback.index('if timeline_flags["closing"]:'), callback.index("read_graph_sim_time"))


class BeltSpeedCheckTest(unittest.TestCase):
    def test_sample_window_is_mid_belt(self):
        self.assertFalse(belt.speed_sample_due(0.15, 1.6))  # spawn area
        self.assertTrue(belt.speed_sample_due(0.8, 1.6))
        self.assertFalse(belt.speed_sample_due(1.45, 1.6))  # end zone

    def test_ratio_and_mismatch(self):
        # 9/17 master02: stop_belt speed 0.2400 in two runs and 0.1500 in another, both with --belt-speed 0.15.
        ratio, mismatch = belt.speed_mismatch(0.24, 0.15)
        self.assertAlmostEqual(1.6, ratio)
        self.assertTrue(mismatch)
        self.assertEqual((1.0, False), belt.speed_mismatch(0.15, 0.15))
        self.assertFalse(belt.speed_mismatch(0.0, 0.0)[1])

    def test_speed_along_projects_on_the_belt_direction(self):
        import math

        self.assertAlmostEqual(0.15, belt.speed_along((0.15, 0.0, 0.0), 0.0))
        self.assertAlmostEqual(0.15, belt.speed_along((0.0, 0.15, 0.01), math.pi / 2))

    def test_belt_body_argument(self):
        # 9/17 master02 window + ros: scaled-cube 5/5 ratio 1.6, xform 5/5 ratio 1.0.
        self.assertEqual("xform", STAGE.parse_args([]).belt_body)
        for preset in STAGE.PRESETS:
            self.assertEqual("xform", STAGE.parse_args(["--preset", preset]).belt_body)
        self.assertEqual("scaled-cube", STAGE.parse_args(["--belt-body", "scaled-cube"]).belt_body)

    def test_mismatch_error_and_at_end_detail(self):
        text = belt.speed_mismatch_error(0.24, 0.15, 1.6)
        self.assertTrue(text.startswith("ERROR 벨트 속도 이상: 실측 0.24 / 설정 0.15 (ratio 1.6)."))
        self.assertIn("재기동 권장", text)
        self.assertEqual("belt_ratio=1.600", belt.at_end_detail(1.6, True))
        self.assertEqual("", belt.at_end_detail(1.0, False))
        message = bridge.encode(bridge.EVENTS, stamp=bridge.stamp(12.0), name=belt.POUCH_AT_END, request_id="r001-0001",
                                order_id="ord-0001", robot_id=belt.ROBOT_ID, epoch=1,
                                detail=belt.at_end_detail(1.6, True))
        decoded, errors = bridge.decode(bridge.EVENTS, message)
        self.assertEqual([], errors)
        self.assertEqual("belt_ratio=1.600", decoded["detail"])


class DiagnosticsTest(unittest.TestCase):
    def test_kit_log_args(self):
        from p3sim import diag

        self.assertEqual([], diag.kit_log_args(""))
        args = diag.kit_log_args("/tmp/p3-kit.log")
        self.assertIn("--/log/file=/tmp/p3-kit.log", args)
        self.assertTrue(all(a.startswith("--/log/") for a in args))

    def test_public_fields_skips_private_and_callables_and_survives_raising_properties(self):
        from p3sim import diag

        class Response:
            mass = 50.0
            _hidden = 1

            @property
            def broken(self):
                raise RuntimeError("binding")

            def method(self):
                return 0

        fields = diag.public_fields(Response())
        self.assertIn("mass=50.0", fields)
        self.assertIn("broken=<RuntimeError>", fields)
        self.assertFalse(any(f.startswith(("_hidden", "method")) for f in fields))

    def test_new_arguments(self):
        args = STAGE.parse_args([])
        self.assertEqual(("", False), (args.kit_log_file, args.belt_presurface))
        args = STAGE.parse_args(["--kit-log-file", "/tmp/k.log", "--belt-presurface"])
        self.assertEqual(("/tmp/k.log", True), (args.kit_log_file, args.belt_presurface))

    def test_diag_module_has_no_isaac_imports_at_top(self):
        source = (Path(__file__).resolve().parents[1] / "standalone" / "p3sim" / "diag.py").read_text()
        top = [line for line in source.splitlines() if line.startswith(("import ", "from "))]
        self.assertEqual(["import traceback"], top)


class TimelineStopContextTest(unittest.TestCase):
    def test_tick_trace_keeps_the_last_ticks(self):
        trace = common.TickTrace(ticks=3, per_tick=2)
        for tick in range(5):
            trace.next_tick(f"t{tick}")
            trace.mark("a")
            trace.mark("b")
            trace.mark("c")
        dump = trace.dump()
        self.assertNotIn("[t0]", dump)  # three finished ticks (t1-t3) and the one in progress
        self.assertIn("[t1]: a, b, ...", dump)
        self.assertIn("[t3]: a, b, ...", dump)
        self.assertIn("[t4] (in progress): a, b, ...", dump)

    def test_kit_log_verbose(self):
        from p3sim import diag

        self.assertNotIn("--/log/fileLogLevel=verbose", diag.kit_log_args("/tmp/k.log"))
        self.assertIn("--/log/fileLogLevel=verbose", diag.kit_log_args("/tmp/k.log", verbose=True))
        self.assertEqual([], diag.kit_log_args("", verbose=True))
        self.assertTrue(STAGE.parse_args(["--kit-log-verbose"]).kit_log_verbose)

    def test_stop_logs_context_and_the_loop_labels_ticks(self):
        source = (Path(__file__).resolve().parents[1] / "standalone" / "pharmacy_stage.py").read_text()
        callback = source.split("        def on_timeline(name):", 1)[1].split("\n        timeline_events", 1)[0]
        self.assertIn("timeline_stop_context timeline=", callback)
        self.assertIn("trace.dump()", callback)
        loop = source.split("        while a1_poll() and not stop_event.is_set()", 1)[1]
        self.assertLess(loop.index("trace.next_tick("), loop.index("step_world()"))
        # 긴 틱은 그 틱의 호출과 함께 남긴다(최적화 9/23: joint_states 공백 추적).
        self.assertLess(loop.index("step_world()"), loop.index("loop stall wall_s="))
        self.assertIn("recent_calls={trace.dump()}", loop)


class RosRefillTest(unittest.TestCase):
    def test_demo_ros_refill_preset(self):
        args = STAGE.parse_args(["--preset", "demo-ros-refill"])
        self.assertEqual(("ros", False, 5.0), (args.mode, args.ros_refill_selfdemo, args.ros_pick_stand_in_s))
        self.assertEqual(STAGE.VERIFIED_RAIL_DRIVE, args.rail_drive)
        self.assertEqual("xform", args.belt_body)
        self.assertEqual(2.0, args.respawn_delay_s)
        self.assertEqual([], STAGE.validate(args))
        # the other presets keep their behaviour
        self.assertTrue(STAGE.parse_args(["--preset", "demo-ros"]).ros_refill_selfdemo)

    def test_inlet_containing(self):
        from p3sim import layout

        inlets = {"a": (0.94, 0.65, 0.91), "b": (1.06, 0.65, 0.91)}
        # 9/17 f796210 canister_in_inlet=True positions (centre after release)
        self.assertEqual("a", layout.inlet_containing((0.9413, 0.6506, 0.92), inlets, (0.1, 0.1, 0.12), 0.01))
        self.assertEqual("b", layout.inlet_containing((1.0610, 0.6511, 0.92), inlets, (0.1, 0.1, 0.12), 0.01))
        # 7ae2879 cycle 1: the canister ended on the floor
        self.assertIsNone(layout.inlet_containing((0.8711, 0.2693, 0.08), inlets, (0.1, 0.1, 0.12), 0.01))

    def test_ros_refill_is_wired(self):
        source = (Path(__file__).resolve().parents[1] / "standalone" / "pharmacy_stage.py").read_text()
        self.assertIn("arm_ros.publish_holding(ros_refill_holding())", source)
        after = source.split("elif arm_ros is not None and arm is not None:", 1)[1]
        ros_branch = after.split("            else:", 1)[0]
        self.assertIn("ros_refill_update(closed)", ros_branch)
        reset = source.split("def do_reset_steps(", 1)[1].split("\n        def ", 1)[0]
        self.assertIn("ros_refill_clear()", reset)


class Practice1Test(unittest.TestCase):
    """재범 실습1 (9/18): swing, speed 80%, visible 2-axis rail."""

    def test_speed_defaults_are_90_percent_arm_80_percent_rail(self):
        """재범 9/24 20:4x: M0609 은 사양의 90%(9/18 부터 80% 였다). 레일은 사양이 없어 80% 그대로."""
        from p3sim import motion

        args = STAGE.parse_args([])
        self.assertAlmostEqual(0.8, args.rail_speed)
        self.assertEqual(list(motion.JOINT_SPEED), args.joint_max_speed)
        self.assertEqual([2.356, 2.356, 2.827, 3.534, 3.534, 3.534], args.joint_max_speed)  # 노드 기본과 같은 값
        for limit, top in zip(args.joint_max_speed, motion.JOINT_MAX_SPEED, strict=True):
            self.assertAlmostEqual(0.9 * top, limit, places=2)
        # USD maxVelocity from the practice-1 log equals Doosan's spec in deg/s
        import math
        self.assertEqual([150, 150, 180, 225, 225, 225], [round(math.degrees(v)) for v in motion.JOINT_MAX_SPEED])

    def test_trapezoid_profile(self):
        from p3sim import motion

        d, v, a = 1.04, 0.8, 1.0  # shelf to inlet a on the rail
        total = motion.trapezoid_duration(d, v, a)
        self.assertAlmostEqual(d / v + v / a, total)
        self.assertEqual(0.0, motion.trapezoid_fraction(0.0, d, v, a))
        self.assertEqual(1.0, motion.trapezoid_fraction(total, d, v, a))
        self.assertAlmostEqual(0.5, motion.trapezoid_fraction(total / 2, d, v, a), places=6)
        samples = [motion.trapezoid_fraction(total * k / 100, d, v, a) for k in range(101)]
        self.assertEqual(samples, sorted(samples))
        steps = [b - a_ for a_, b in zip(samples[:-1], samples[1:], strict=True)]
        self.assertLessEqual(max(steps) * d / (total / 100), v + 1e-6)  # never faster than vmax
        # short move: triangle profile, never reaches vmax
        self.assertAlmostEqual(2 * (0.1 / a) ** 0.5, motion.trapezoid_duration(0.1, v, a))
        self.assertEqual(0.0, motion.trapezoid_duration(0.0, v, a))

    def test_clamp_step(self):
        from p3sim import motion

        self.assertEqual((0.1, -0.1, 0.05), motion.clamp_step((0, 0, 0), (1, -1, 0.05), (0.1, 0.1, 0.1)))

    def test_held_objects_move_after_the_physics_step(self):
        source = (Path(__file__).resolve().parents[1] / "standalone" / "pharmacy_stage.py").read_text()
        body = source.split("        def step_world():", 1)[1].split("\n        def ", 1)[0]
        self.assertLess(body.index("world.step(render=False, update_fabric=True)"), body.index("demo_follow()"))
        self.assertLess(body.index("ros_refill_follow()"), body.index("world.render()"))

    def test_contact_pair_log_throttles_per_pair(self):
        from p3sim import diag

        pairs = diag.ContactPairLog(every_s=2.0)
        self.assertTrue(pairs.add("/Arm/link_6", "/Room/InletA_WallN", 1.0))
        self.assertFalse(pairs.add("/Room/InletA_WallN", "/Arm/link_6", 1.5))  # same pair, either order
        self.assertTrue(pairs.add("/Arm/link_6", "/Room/Shelf", 1.5))  # another pair logs at once
        self.assertTrue(pairs.add("/Arm/link_6", "/Room/InletA_WallN", 3.1))
        self.assertEqual(3, pairs.count("/Arm/link_6", "/Room/InletA_WallN"))
        self.assertFalse(STAGE.parse_args([]).no_contact_log)

    def test_contact_log_interval_is_an_argument(self):
        """P30 (9/20): the 2 s throttle hid the gripper-canister touch. Diagnosis runs can tighten it."""
        from p3sim import diag

        self.assertEqual(2.0, STAGE.parse_args([]).contact_log_every_s)  # demo runs keep the old volume
        self.assertEqual(2.0, STAGE.parse_args(["--preset", "demo-ros-refill-v2"]).contact_log_every_s)
        self.assertEqual(0.05, STAGE.parse_args(["--contact-log-every-s", "0.05"]).contact_log_every_s)
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            STAGE.parse_args(["--contact-log-every-s", "-1"])
        dense = diag.ContactPairLog(every_s=0.05)
        self.assertTrue(dense.add("/Arm/finger", "/Shelf/canister", 1.000))
        self.assertFalse(dense.add("/Arm/finger", "/Shelf/canister", 1.030))
        self.assertTrue(dense.add("/Arm/finger", "/Shelf/canister", 1.117))  # the touch 2.0 s would have hidden
        every_event = diag.ContactPairLog(every_s=0.0)
        self.assertTrue(all(every_event.add("/Arm/finger", "/Shelf/canister", 1.0 + i / 60) for i in range(3)))
        source = (Path(__file__).resolve().parents[1] / "standalone" / "pharmacy_stage.py").read_text()
        self.assertIn("every_s=args.contact_log_every_s", source)  # the argument reaches the watcher

    def test_rail_reads_as_two_axes(self):
        from p3sim import layout

        # X tracks are raised and yellow; the Y beam and Y carriage have their own colours (visual, 재범 실습1 P4).
        tracks = layout.rail_boxes((0.0, 0.3, 0.0), 2.4, (-0.10, 0.33), 0.05, 0.6)
        self.assertEqual({layout.COLORS["rail_track"]}, {box.color for box in tracks})
        self.assertTrue(all(box.size[2] == layout.RAIL_TRACK_HEIGHT for box in tracks))
        self.assertEqual(3, len({layout.COLORS[k] for k in ("rail_track", "rail_beam", "carriage_y")}))


class RclpyInitTest(unittest.TestCase):
    """9/18 practice 1: Ctrl-C ended with exit 1 because rclpy's own SIGINT handler shut the context down first."""

    def _fake(self, accepts_options):
        import types

        calls = []
        rclpy = types.SimpleNamespace(ok=lambda: bool(calls))

        def init(**kwargs):
            if kwargs and not accepts_options:
                raise TypeError("unexpected keyword")
            calls.append(kwargs)

        rclpy.init = init
        return rclpy, calls

    def test_disables_rclpy_signal_handlers_when_possible(self):
        import sys
        import types

        signals = types.ModuleType("rclpy.signals")
        signals.SignalHandlerOptions = types.SimpleNamespace(NO="NO")
        sys.modules["rclpy.signals"] = signals
        try:
            rclpy, calls = self._fake(accepts_options=True)
            self.assertEqual("no_signal_handlers", STAGE.refill.init_rclpy(rclpy))
            self.assertEqual([{"signal_handler_options": "NO"}], calls)
            self.assertEqual("already", STAGE.refill.init_rclpy(rclpy))
            rclpy, calls = self._fake(accepts_options=False)
            self.assertEqual("default_signal_handlers", STAGE.refill.init_rclpy(rclpy))
        finally:
            del sys.modules["rclpy.signals"]


class Practice3Test(unittest.TestCase):
    """재범 실습3 (9/18): arm looks cut in the middle, contacts with impulse 0."""

    def test_contact_kind(self):
        from p3sim import diag

        self.assertEqual("near", diag.contact_kind(0.0, 0.08))  # inside the contact offset only
        self.assertEqual("touch", diag.contact_kind(0.0, -0.002))
        self.assertEqual("touch", diag.contact_kind(0.5, 0.05))
        self.assertEqual("near", diag.contact_kind(0.0, None))

    def test_quat_from_z_to(self):
        from p3sim import geometry

        for v in ((0, 0, 1), (1, 0, 0), (0, 1, 0), (0.3, -0.2, 0.9), (0, 0, -1), (0.0, 0.0, 0.0)):
            q = geometry.quat_from_z_to(v)
            n = sum(c * c for c in v) ** 0.5
            rotated = geometry.quat_rotate(q, (0.0, 0.0, 1.0))
            expected = (0.0, 0.0, 1.0) if n == 0 else tuple(c / n for c in v)
            for a, b in zip(rotated, expected, strict=True):
                self.assertAlmostEqual(a, b, places=9)

    def test_link_visual_check_runs_before_the_articulation_is_added(self):
        source = (Path(__file__).resolve().parents[1] / "standalone" / "pharmacy_stage.py").read_text()
        added = source.index("SingleArticulation(prim_path=arm_root")
        self.assertLess(source.index("scene.ensure_link_visuals("), added)
        mounted = source.index("scene.build_xy_rail_with_robot(")
        updates = source.index("simulation_app.update()", mounted)
        self.assertLess(source.index("scene.ensure_link_visuals("), updates)  # before Fabric fills the prims

    def test_inlets_stand_off_the_dispenser_face(self):
        from p3sim import layout

        room = layout.default_layout()
        boxes, inlets, _o = layout.dispenser_boxes(room["dispenser_origin"], room["dispenser_size"],
                                                   room["inlet_size"], room["inlet_height"], room["inlet_wall"],
                                                   room["belt_top"], room["outlet_size"], room["inlet_gap"])
        face_y = room["dispenser_origin"][1] - room["dispenser_size"][1] / 2
        for center in inlets.values():
            self.assertAlmostEqual(face_y - room["inlet_gap"], center[1] + room["inlet_size"][1] / 2)
        ledge = next(box for box in boxes if box.name == "DispenserLedge")
        self.assertAlmostEqual(face_y, ledge.center[1] + ledge.size[1] / 2)  # ledge still reaches the face
        # base-to-inlet distance shrank from 0.40 m (arm stretched, joint_3 0.115 rad at above_inlet on 9/18)
        self.assertLess(room["inlet_offset"][1], 0.40)

    def test_link_visuals_deinstance_meshes_with_subsets(self):
        try:
            from pxr import Sdf, Usd, UsdGeom
        except ImportError:
            self.skipTest("usd-core not installed")
        from p3sim import scene

        proto = Usd.Stage.CreateInMemory()
        UsdGeom.Mesh.Define(proto, "/visuals/link_2/MF0609_2_1/Scene/mesh")
        UsdGeom.Subset.Define(proto, "/visuals/link_2/MF0609_2_1/Scene/mesh/Material_008")
        stage = Usd.Stage.CreateInMemory()
        for name in ("link_1", "link_2", "link_3"):
            UsdGeom.Xform.Define(stage, f"/robot/{name}")
        visuals = stage.DefinePrim("/robot/link_2/visuals")
        visuals.GetReferences().AddReference(Sdf.Reference(proto.GetRootLayer().identifier, "/visuals/link_2"))
        visuals.SetInstanceable(True)
        knuckle = stage.DefinePrim("/robot/gripper/right_outer_knuckle/visuals")  # no GeomSubset (9/18 실습6)
        knuckle.GetReferences().AddReference(Sdf.Reference(proto.GetRootLayer().identifier, "/visuals/link_2"))
        knuckle.SetInstanceable(True)
        counts = scene.ensure_link_visuals(stage, "/robot", ("link_1", "link_2", "link_3"), lambda _t: None)
        self.assertFalse(visuals.IsInstanceable())
        self.assertFalse(knuckle.IsInstanceable())  # every robot visuals prim, not only GeomSubset meshes
        self.assertEqual(1, counts["link_2"])


class SceneV2Test(unittest.TestCase):
    """재범 9/18: 3-axis rail, four shelves, cylinder + module canisters, round bin, module hole (placeholders)."""

    def test_old_presets_stay_v1(self):
        for name in ("demo-ros", "demo-ros-refill", "selfdemo-refill"):
            self.assertEqual("v1", STAGE.parse_args(["--preset", name]).scene, name)
        self.assertEqual("v1", STAGE.parse_args([]).scene)

    def test_v2_preset(self):
        args = STAGE.parse_args(["--preset", "demo-ros-refill-v2"])
        self.assertEqual(("ros", False, "v2"), (args.mode, args.ros_refill_selfdemo, args.scene))
        self.assertEqual([0.0, 1.10], args.rail_z_limits)  # base 0.25..1.35 (재범: base near/below the canister)
        self.assertEqual(0.25, args.carriage_height)
        self.assertEqual(2.8, args.rail_x_stroke)  # 실습7-a: insert asked x 1.150 with limit 1.20
        self.assertEqual([1e7, 1e5, 1e8], args.rail_drive)  # 실습7-a: rail pushed 5-10 cm with 5e4
        self.assertEqual([], STAGE.validate(args))

    def test_v2_room(self):
        from p3sim import layout_v2

        layout = STAGE.room(STAGE.parse_args(["--scene", "v2"]))
        v2 = layout["v2"]
        self.assertEqual({}, layout["inlets"])
        self.assertEqual(16, len(v2["cells"]))
        kinds = {cell["type"] for cell in v2["cells"].values()}
        self.assertEqual({"cylinder", "module"}, kinds)
        tops = sorted(k for k, c in v2["cells"].items() if c["access"] == "top")
        self.assertEqual(["upper_left/r1c0", "upper_left/r1c1", "upper_right/r1c0", "upper_right/r1c1"], tops)
        names = {box.name for box in layout["boxes"]}
        self.assertIn("RoundBinFloor", names)
        self.assertIn("DispenserFrontAbove", names)
        self.assertNotIn("InletAFloor", names)
        # the upper shelves stand on the floor shelves
        for spec in layout_v2.default_v2()["shelves"]:
            if spec["name"].startswith("upper"):
                self.assertAlmostEqual(1.15, spec["z0"])  # a_plinth055
        self.assertTrue(all(len(o["size"]) == 3 for o in v2["obstacles"]))

    def test_judge_target(self):
        from p3sim import layout_v2

        layout = STAGE.room(STAGE.parse_args(["--scene", "v2"]))["v2"]["targets"]
        judge = layout_v2.judge_target
        self.assertEqual("round", judge((0.90, 0.56, 0.93), layout["round"], layout["module"]))
        self.assertEqual("none", judge((0.90, 0.56, 1.05), layout["round"], layout["module"]))  # above the rim
        self.assertEqual("module", judge((1.15, 0.76, 1.02), layout["round"], layout["module"]))  # more than half in
        self.assertEqual("none", judge((1.15, 0.66, 1.02), layout["round"], layout["module"]))  # still outside
        self.assertEqual("none", judge((1.25, 0.76, 1.02), layout["round"], layout["module"]))  # beside the hole

    def test_canisters_fit_their_targets(self):
        from p3sim import layout_v2

        p = layout_v2.default_v2()
        self.assertLess(p["cylinder"]["diameter"], p["round_bin"]["inner_diameter"])
        self.assertLess(p["module"]["x"], p["module_hole"]["opening"][0])
        self.assertLess(p["module"]["z"], p["module_hole"]["opening"][1])

    def test_inventory_and_layout_json(self):
        import importlib.util
        import json as _json

        path = Path(__file__).resolve().parents[1] / "standalone" / "pharmacy_layout_json.py"
        spec = importlib.util.spec_from_file_location("pharmacy_layout_json", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        data = _json.loads(_json.dumps(module.build(["--scene", "v2"])))
        self.assertEqual(("v2", 1), (data["scene"], data["v"]))
        self.assertEqual(["rail_x", "rail_y", "rail_z"], data["rail"]["names"])
        self.assertEqual([0.0, 0.30, 0.25], data["rail"]["origin"])  # v2 low pedestal
        self.assertEqual({"drug-amox": "cylinder", "drug-ibu": "module"}, data["items"])
        cell = data["cells"][0]
        for key in ("cell", "canister_id", "item", "type", "access", "present", "pose", "size"):
            self.assertIn(key, cell)
        self.assertTrue(all(c["present"] for c in data["cells"]))
        self.assertEqual({"round", "module"}, set(data["targets"]))
        self.assertGreater(len(data["obstacles"]), 20)

    def test_v2_shelves_have_their_own_colours(self):
        layout = STAGE.room(STAGE.parse_args(["--scene", "v2"]))
        colours = {}
        for box in layout["boxes"]:
            for prefix in ("FloorLeft", "FloorRight", "UpperLeft", "UpperRight"):
                if box.name.startswith(prefix) and "Frame" not in box.name:
                    colours.setdefault(prefix, set()).add(box.color)
        self.assertEqual(4, len(colours))
        self.assertTrue(all(len(c) == 1 for c in colours.values()))
        self.assertEqual(4, len({next(iter(c)) for c in colours.values()}))  # 재범 실습6: read as one rectangle

    def test_v2_shelf_frames_outline_each_shelf_without_moving_cells(self):
        from p3sim import layout_v2

        layout = STAGE.room(STAGE.parse_args(["--scene", "v2"]))
        frames = [box for box in layout["boxes"] if "Frame" in box.name]
        self.assertEqual(16, len(frames))  # 4 shelves x (2 posts + bottom + top)
        self.assertTrue(all(box.kind == "visual" for box in frames))
        self.assertFalse(any("Frame" in o["name"] for o in layout["v2"]["obstacles"]))  # not in the clearance model
        # the floor shelf's top bar and the upper shelf's bottom bar meet at z 1.15: a visible boundary line
        tops = {b.name: b for b in frames if b.name.endswith("FrameTop")}
        bottoms = {b.name: b for b in frames if b.name.endswith("FrameBottom")}
        self.assertAlmostEqual(1.15, tops["FloorLeftFrameTop"].center[2] + tops["FloorLeftFrameTop"].size[2] / 2)
        self.assertAlmostEqual(1.15, bottoms["UpperLeftFrameBottom"].center[2]
                               - bottoms["UpperLeftFrameBottom"].size[2] / 2)
        # cells of a_plinth055 (재범 9/18): the arm reads them from the layout JSON
        cells = layout["v2"]["cells"]
        def home(cell_id):
            return tuple(round(v, 4) for v in layout_v2.canister_home(cells[cell_id]))

        self.assertEqual((-1.15, 0.91, 0.61), home("floor_left/r0c0"))
        self.assertEqual((-0.15, 0.91, 1.54), home("upper_right/r1c1"))

    def test_v2_rail_stroke_default_only_in_v2(self):
        self.assertEqual(2.4, STAGE.parse_args([]).rail_x_stroke)
        self.assertEqual(2.4, STAGE.parse_args(["--preset", "demo-ros-refill"]).rail_x_stroke)
        self.assertEqual(STAGE.VERIFIED_RAIL_DRIVE, STAGE.parse_args(["--preset", "demo-ros-refill"]).rail_drive)
        self.assertEqual(2.8, STAGE.parse_args(["--scene", "v2"]).rail_x_stroke)
        self.assertEqual(2.6, STAGE.parse_args(["--scene", "v2", "--rail-x-stroke", "2.6"]).rail_x_stroke)
        self.assertEqual(2.6, STAGE.parse_args(["--scene", "v2", "--rail-x-stroke=2.6"]).rail_x_stroke)

    def test_v2_rail_parts_for_the_clearance_model(self):
        from p3sim import diag

        args = STAGE.parse_args(["--preset", "demo-ros-refill-v2"])
        info = STAGE.v2_rail_info(args)
        self.assertEqual([[-1.4, 1.4], [-0.1, 0.33], [0.0, 1.1]], info["limits"])
        self.assertEqual([0.0, 0.30, 0.25], info["origin"])
        parts = {p["name"]: p for p in info["parts"]}
        self.assertEqual([], parts["Track"]["moves"])
        self.assertEqual(["x"], parts["YBeam"]["moves"])
        self.assertEqual(["x", "y"], parts["Pedestal"]["moves"])  # the pedestal does not ride rail_z
        self.assertEqual(["x", "y", "z"], parts["LiftPlate"]["moves"])
        pedestal_top = parts["Pedestal"]["center"][2] + parts["Pedestal"]["size"][2] / 2
        plate_bottom = parts["LiftPlate"]["center"][2] - parts["LiftPlate"]["size"][2] / 2
        self.assertAlmostEqual(pedestal_top, plate_bottom)  # 실습6: no coplanar top faces
        self.assertEqual([0.5, 0.4, 0.43],
                         [round(v, 4) for v in diag.moved_part_center(parts["LiftPlate"], {"x": 0.5, "y": 0.1,
                                                                                            "z": 0.2})])
        obstacles = {o["name"] for o in STAGE.room(args)["v2"]["obstacles"]}
        self.assertTrue({"RailXLeft", "RailXRight"} <= obstacles)

    def test_v2_low_pedestal_reaches_every_canister_height(self):
        from p3sim import layout_v2

        args = STAGE.parse_args(["--preset", "demo-ros-refill-v2"])
        v1 = STAGE.parse_args(["--preset", "demo-ros-refill"])
        self.assertEqual(0.6, v1.carriage_height)  # v1 unchanged
        self.assertEqual(0.4, STAGE.parse_args(["--scene", "v2", "--carriage-height", "0.4"]).carriage_height)
        low, high = args.carriage_height + args.rail_z_limits[0], args.carriage_height + args.rail_z_limits[1]
        heights = [layout_v2.canister_home(c)[2] for c in STAGE.room(args)["v2"]["cells"].values()]
        self.assertLess(low, min(heights))  # the base can go below the lowest canister (z 0.61)
        # the arm's front approach needs rail_z up to 0.99 for the top cells (arm search, a_plinth055) and keeps
        # targets 0.05 m inside the limits
        self.assertGreaterEqual(args.rail_z_limits[1] - 0.05, 0.99)
        self.assertGreater(high, 0.99 + args.carriage_height - 1e-9)
        parts = {p["name"]: p for p in STAGE.v2_rail_info(args)["parts"]}
        for name, part in parts.items():
            if name == "LiftColumn":  # the mast slides down into the pedestal and under the floor at low rail_z
                continue
            self.assertGreaterEqual(part["center"][2] - part["size"][2] / 2, -1e-9, name)  # nothing below the floor

    def test_v2_lift_column_leaves_no_gap_under_the_plate(self):
        # 실습7-a2 (9/18, 재범 "M0609가 공중부양을 하잖아"): nothing held the plate up above the 0.16 m pedestal.
        from p3sim import diag

        args = STAGE.parse_args(["--preset", "demo-ros-refill-v2"])
        parts = {p["name"]: p for p in STAGE.v2_rail_info(args)["parts"]}
        self.assertNotIn("LiftGuide", parts)
        pedestal_top = parts["Pedestal"]["center"][2] + parts["Pedestal"]["size"][2] / 2
        column = parts["LiftColumn"]
        plate = parts["LiftPlate"]
        self.assertEqual(["x", "y", "z"], column["moves"])
        for z in (0.0, 0.55, 1.10):
            rail = {"x": 0.3, "y": 0.1, "z": z}
            col_center = diag.moved_part_center(column, rail)[2]
            plate_center = diag.moved_part_center(plate, rail)[2]
            col_bottom = col_center - column["size"][2] / 2
            col_top = col_center + column["size"][2] / 2
            plate_bottom = plate_center - plate["size"][2] / 2
            self.assertAlmostEqual(col_top, plate_bottom, msg=z)  # column holds the plate
            self.assertLessEqual(col_bottom, pedestal_top + 1e-9, msg=z)  # and reaches into the pedestal: gap 0
        self.assertLess(column["size"][0], parts["Pedestal"]["size"][0])  # mast slides inside the pedestal outline


class A1ProbeTest(unittest.TestCase):
    """9/18 external review A1: exit-cause probe; the loop condition itself does not change."""

    def test_verbose_sets_both_log_levels(self):
        from p3sim import diag

        args = diag.kit_log_args("/tmp/k.log", verbose=True)
        self.assertIn("--/log/fileLogLevel=verbose", args)
        self.assertIn("--/log/level=verbose", args)
        self.assertNotIn("--/log/level=verbose", diag.kit_log_args("/tmp/k.log"))

    def test_poll_runs_before_every_loop_condition_and_never_ends_the_loop(self):
        source = (Path(__file__).resolve().parents[1] / "standalone" / "pharmacy_stage.py").read_text()
        self.assertIn("        while a1_poll() and not stop_event.is_set() and common.keep_running(", source)
        poll = source.split("        def a1_poll():", 1)[1].split("\n        def ", 1)[0]
        self.assertIn("return True", poll)
        self.assertNotIn("return False", poll)

    def test_probe_emits_only_on_state_change(self):
        import sys
        import types

        from p3sim import diag

        kit = types.SimpleNamespace(state=True, is_running=lambda: kit.state, get_update_number=lambda: 7)
        fake_app = types.ModuleType("omni.kit.app")
        fake_app.get_app = lambda: kit
        saved = {name: sys.modules.get(name) for name in ("omni", "omni.kit", "omni.kit.app")}
        sys.modules["omni"] = types.ModuleType("omni")
        sys.modules["omni.kit"] = types.ModuleType("omni.kit")
        sys.modules["omni.kit.app"] = fake_app
        sys.modules["omni"].kit = sys.modules["omni.kit"]
        sys.modules["omni.kit"].app = fake_app
        try:
            events = []
            probe = diag.A1Probe(emit=lambda kind, **fields: events.append((kind, fields)))
            sim_app = types.SimpleNamespace(is_exiting=lambda: False,
                                            context=types.SimpleNamespace(get_stage=lambda: object()))
            probe.poll(sim_app)
            probe.poll(sim_app)
            kit.state = False
            probe.poll(sim_app)
            self.assertEqual(2, len(events))
            self.assertEqual(("state", False), (events[1][0], events[1][1]["kit_running"]))
            self.assertEqual(7, events[1][1]["update_number"])
        finally:
            for name, module in saved.items():
                if module is None:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = module

    def test_v2_shelves_stand_without_gaps(self):
        """재범 9/18 a_plinth055: the raised shelves must not float or leave gaps (no second "공중부양")."""
        from p3sim import layout_v2

        layout = STAGE.room(STAGE.parse_args(["--scene", "v2"]))
        boxes = {b.name: b for b in layout["boxes"]}

        def bottom(b):
            return b.center[2] - b.size[2] / 2

        def top(b):
            return b.center[2] + b.size[2] / 2

        heights = sorted({round(layout_v2.canister_home(c)[2], 3) for c in layout["v2"]["cells"].values()})
        self.assertEqual([0.61, 0.91, 1.24, 1.54], heights)
        for side in ("Left", "Right"):
            floor, upper = f"Floor{side}", f"Upper{side}"
            for panel in ("ShelfSideLeft", "ShelfSideRight", "ShelfBack"):
                self.assertAlmostEqual(0.0, bottom(boxes[floor + panel]), msg=floor + panel)  # stands on the floor
                self.assertAlmostEqual(top(boxes[floor + panel]), bottom(boxes[upper + panel]), msg=panel)  # no gap
            floor_top_board = max((b for n, b in boxes.items() if n.startswith(floor + "ShelfBoard")), key=top)
            upper_bottom_board = min((b for n, b in boxes.items() if n.startswith(upper + "ShelfBoard")), key=bottom)
            self.assertAlmostEqual(top(floor_top_board), bottom(upper_bottom_board))  # upper shelf rests on it
            for frame in ("FramePostLeft", "FramePostRight"):
                self.assertAlmostEqual(0.0, bottom(boxes[floor + frame]))
                self.assertAlmostEqual(top(boxes[floor + frame]), bottom(boxes[upper + frame]))
        for name, box in boxes.items():  # every canister cell's board is held by side panels reaching the floor
            if "ShelfBoard" in name:
                shelf = name.split("ShelfBoard")[0]
                self.assertLessEqual(bottom(boxes[shelf + "ShelfSideLeft"]), bottom(box), name)
                self.assertGreaterEqual(top(boxes[shelf + "ShelfSideLeft"]), top(box), name)


class ViewTests(unittest.TestCase):
    """실습7-a4 (9/18): named viewport cameras stand inside the room, clear of every box, and frame their subjects."""

    ARM_REACH = 0.9  # M0609 reach, m

    @staticmethod
    def corners(box):
        return [tuple(box.center[i] + s[i] * box.size[i] / 2 for i in range(3))
                for s in ((a, b, c) for a in (-1, 1) for b in (-1, 1) for c in (-1, 1))]

    @staticmethod
    def inside(point, box, margin=0.0):
        return all(abs(point[i] - box.center[i]) <= box.size[i] / 2 + margin for i in range(3))

    GRIP_ABOVE = 0.45  # gripper above a canister it reaches from the top (upper shelves' top row), m
    # Rail poses (x, y, z) the arm plans for v2 (#190 table, scene c40c3f3): picks per cell, round and module inserts.
    ARM_RAIL_POSES_V2 = ([(x, 0.11, z) for x in (-1.3, -1.0, -0.6, -0.3) for z in (0.1, 0.4)]
                         + [(x, y, z) for x in (-1.0, -0.7, -0.3, 0.0) for y, z in ((0.12, 0.69), (0.17, 0.94),
                                                                                  (0.12, 0.99))]
                         + [(0.617, -0.023, 0.41), (1.3, 0.03, 0.47)])
    ROBOT_HALF_WIDTH, ROBOT_HEIGHT = 0.30, 0.80  # robot envelope around its base in the frame, m (ours, conservative)

    def subjects(self, scene, layout, args):
        """Points each view must frame. overview = where the robot works (재범 7-a4: "로봇이 작업하는 것을 잘
        보이는 각도와 줌"): every canister with the gripper above the highest ones, the bins and the carriage's x
        travel on the pedestal. Floor-level track ends and plinths may fall outside to let the camera come closer."""
        from p3sim import layout_v2

        boxes = layout["boxes"]
        shelf = [p for b in boxes if "Shelf" in b.name for p in self.corners(b)]
        if scene == "v2":
            targets = layout["v2"]["targets"]
            bins = [tuple(targets["round"]["center"]), tuple(targets["module"]["entry_center"])]
            homes = [layout_v2.canister_home(c) for c in layout["v2"]["cells"].values()]
        else:
            bins = [tuple(v) for v in layout["inlets"].values()]
            homes = [(x, y, z + args.room_canister_size[2] / 2) for x, y, z in layout["cells"].values()]
        top = max(h[2] for h in homes)
        grip = [(x, y, z + self.GRIP_ABOVE) for x, y, z in homes if z == top]
        ox, oy, oz = args.rail_origin
        carriage = [(ox + s * args.rail_x_stroke / 2, oy, oz + args.carriage_height) for s in (-1, 1)]
        robot = []
        if scene == "v2":  # 실습7-a5: the robot at the module insert (rail x 1.30) left the overview frame
            for rx, ry, rz in self.ARM_RAIL_POSES_V2:
                base = (ox + rx, oy + ry, oz + args.carriage_height + rz)
                robot += [(base[0] + s * self.ROBOT_HALF_WIDTH, base[1], base[2] + h)
                          for s in (-1, 1) for h in (0.0, self.ROBOT_HEIGHT)]
        return {"overview": homes + grip + bins + carriage + robot, "shelves": shelf, "bins": bins}

    def test_views_are_in_the_room_clear_of_boxes_and_frame_their_subjects(self):
        from p3sim import views

        for scene, preset in (("v1", "demo-ros-refill"), ("v2", "demo-ros-refill-v2")):
            args = STAGE.parse_args(["--preset", preset])
            layout = STAGE.room(args)
            subjects = self.subjects(scene, layout, args)
            walls = [b for b in layout["boxes"] if b.name.startswith("Wall_")]
            reach_y = args.rail_origin[1] + args.rail_y_limits[0] - self.ARM_REACH
            for name in views.VIEW_NAMES:
                eye, target = views.view(scene, name)
                label = f"{scene}/{name}"
                # Inside the room: pharmacy side of the corridor wall, below its top, above the floor.
                self.assertLess(eye[0], args.wall_x - STAGE.ROOM["wall_thickness"] / 2 - 0.1, label)
                self.assertTrue(0.5 < eye[2] < STAGE.ROOM["wall_height"], label)
                for box in layout["boxes"]:
                    self.assertFalse(self.inside(eye, box, margin=0.2), f"{label} eye in {box.name}")
                self.assertLess(eye[1], reach_y, f"{label} eye within the arm's reach")
                for i in range(21):  # no wall between the eye and the target
                    point = tuple(e + (t - e) * i / 20 for e, t in zip(eye, target, strict=True))
                    for wall in walls:
                        self.assertFalse(self.inside(point, wall), f"{label} sight line through {wall.name}")
                for aspect in (views.ASPECT, views.HALF_SCREEN_ASPECT):  # full screen 16:9, 재범 half screen
                    for point in subjects[name]:
                        self.assertTrue(views.in_frame(eye, target, point, aspect=aspect),
                                        f"{label} aspect {aspect:.2f} misses {point}")

    def test_view_argument_defaults(self):
        self.assertEqual("none", STAGE.parse_args([]).view)
        self.assertEqual("none", STAGE.parse_args(["--preset", "demo-ros-refill"]).view)
        self.assertEqual("overview", STAGE.parse_args(["--preset", "demo-ros-refill-v2"]).view)
        self.assertEqual("bins", STAGE.parse_args(["--preset", "demo-ros-refill-v2", "--view", "bins"]).view)
        self.assertEqual("none", STAGE.parse_args(["--preset", "demo-ros-refill-v2", "--view", "none"]).view)
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            STAGE.parse_args(["--view", "top"])


class RoundBinTests(unittest.TestCase):
    """실습7-a5 (9/18): v2 round bin inner diameter 0.10 -> 0.12; the wider ring must still sit on its ledge."""

    def test_round_bin_sits_on_the_ledge_and_clears_the_cylinder(self):
        import math

        from p3sim import layout_v2

        args = STAGE.parse_args(["--scene", "v2"])
        layout = STAGE.room(args)
        boxes = {b.name: b for b in layout["boxes"]}
        spec = layout_v2.default_v2()["round_bin"]
        self.assertAlmostEqual(0.12, spec["inner_diameter"])
        self.assertAlmostEqual(0.12, layout["v2"]["targets"]["round"]["inner_diameter"])
        gap = (spec["inner_diameter"] - layout_v2.default_v2()["cylinder"]["diameter"]) / 2.0
        self.assertGreaterEqual(gap, 0.025 - 1e-9)  # cylinder to wall, a side
        ledge = boxes["DispenserLedge"]
        lx0, lx1 = ledge.center[0] - ledge.size[0] / 2, ledge.center[0] + ledge.size[0] / 2
        ly0, ly1 = ledge.center[1] - ledge.size[1] / 2, ledge.center[1] + ledge.size[1] / 2
        ledge_top = ledge.center[2] + ledge.size[2] / 2
        face_y = args.dispenser_origin[1] - args.dispenser_size[1] / 2.0
        self.assertAlmostEqual(face_y, ly1)  # the ledge runs out from the dispenser face
        ring = [b for n, b in boxes.items() if n.startswith("RoundBin")]
        self.assertEqual(17, len(ring))
        for box in ring:
            yaw = getattr(box, "yaw", 0.0) or 0.0
            hx, hy = box.size[0] / 2, box.size[1] / 2
            for sx in (-1, 1):
                for sy in (-1, 1):  # footprint corners after yaw
                    x = box.center[0] + sx * hx * math.cos(yaw) - sy * hy * math.sin(yaw)
                    y = box.center[1] + sx * hx * math.sin(yaw) + sy * hy * math.cos(yaw)
                    self.assertTrue(lx0 <= x <= lx1 and ly0 <= y <= ly1, f"{box.name} corner ({x:.3f}, {y:.3f})")
            self.assertGreaterEqual(box.center[2] - box.size[2] / 2, ledge_top - 1e-9, box.name)  # on, not in
        floor = boxes["RoundBinFloor"]
        self.assertAlmostEqual(ledge_top, floor.center[2] - floor.size[2] / 2)  # rests on the ledge
        for name, box in boxes.items():  # the dispenser front stays clear of the ring
            if name.startswith("DispenserFront"):
                self.assertGreaterEqual(box.center[1] - box.size[1] / 2, max(
                    b.center[1] + b.size[1] / 2 for b in ring) - 1e-9, name)


class BaseSceneTests(unittest.TestCase):
    """이식 준비 (9/18): the stage on 세준's hospital USD via --base-usd / --pharmacy-origin / --base-deactivate."""

    SCENE = STANDALONE.parent / "scenes" / "hospital_layout.usda"

    def test_defaults_leave_the_stage_as_it_was(self):
        args = STAGE.parse_args([])
        self.assertEqual((None, [0.0, 0.0, 0.0, 0.0], []),
                         (args.base_usd, args.pharmacy_origin, args.base_deactivate))
        self.assertEqual([], STAGE.validate(args))
        v2 = STAGE.parse_args(["--preset", "demo-ros-refill-v2"])
        self.assertIsNone(v2.base_usd)

    def test_frame_round_trip(self):
        from p3sim import base_scene

        origin = (0.25, 13.3, 0.1, 90.0)
        for point in ((0.0, 0.0, 0.0), (1.2, -0.4, 0.8), (-1.6, 1.3, 2.0)):
            there = base_scene.stage_to_base(point, origin)
            back = base_scene.base_to_stage(there, origin)
            for a, b in zip(point, back, strict=True):
                self.assertAlmostEqual(a, b)
        self.assertEqual((0.25, 13.3, 0.1), tuple(round(v, 9) for v in base_scene.stage_to_base((0, 0, 0), origin)))
        x_axis = base_scene.stage_to_base((1, 0, 0), origin)  # yaw 90: our +x is the base scene's +y
        self.assertAlmostEqual(0.25, x_axis[0])
        self.assertAlmostEqual(14.3, x_axis[1])

    def test_validate_base_usd(self):
        import tempfile

        missing = STAGE.parse_args(["--base-usd", "/nonexistent/p3-hospital.usda"])
        self.assertTrue(any("does not exist" in p for p in STAGE.validate(missing)))
        raw = STAGE.parse_args(["--base-usd", str(self.SCENE)])  # the committed scene still has placeholders
        self.assertTrue(any("prepare_hospital_scene.py" in p for p in STAGE.validate(raw)))
        no_base = STAGE.parse_args(["--pharmacy-origin", "1", "2", "0", "0"])
        self.assertTrue(any("need --base-usd" in p for p in STAGE.validate(no_base)))
        with tempfile.TemporaryDirectory() as tmp:
            ready = Path(tmp) / "scene.usda"
            ready.write_text("#usda 1.0\n")
            args = STAGE.parse_args(["--base-usd", str(ready), "--pharmacy-origin", "0.25", "13.3", "0", "0"])
            self.assertEqual([], STAGE.validate(args))

    def test_add_base_scene_composes_the_inverse_pose(self):
        try:
            from pxr import Gf, Usd, UsdGeom
        except ImportError:
            self.skipTest("usd-core not installed")
        import tempfile

        from p3sim import base_scene

        origin = (0.25, 10.52854210179955, 0.0, 30.0)
        marker_base = base_scene.stage_to_base((1.0, 0.5, 0.75), origin)  # where our (1, 0.5, 0.75) is in the base
        with tempfile.TemporaryDirectory() as tmp:
            base_path = Path(tmp) / "base.usda"
            base = Usd.Stage.CreateNew(str(base_path))
            world = UsdGeom.Xform.Define(base, "/World")
            world.AddTranslateOp().Set(Gf.Vec3d(0.0, 0.0, 0.0))  # like hospital_layout.usda
            base.SetDefaultPrim(world.GetPrim())
            marker = UsdGeom.Xform.Define(base, "/World/Marker")
            marker.AddTranslateOp().Set(Gf.Vec3d(*marker_base))
            for name in ("PillA", "PillB", "Keep"):
                UsdGeom.Xform.Define(base, f"/World/Shelf/{name}")
            graph_target = base.DefinePrim("/World/Graph/Node").CreateRelationship("inputs:conveyorPrim")
            graph_target.SetTargets(["/World/Marker"])
            base.GetRootLayer().Save()

            stage = Usd.Stage.CreateInMemory()
            UsdGeom.Xform.Define(stage, "/World")
            info = base_scene.add_base_scene(stage, str(base_path), origin, ["Shelf/Pill*", "Nope"])
            placed = UsdGeom.Xformable(stage.GetPrimAtPath("/World/P3Base/Scene/Marker"))
            at = placed.ComputeLocalToWorldTransform(Usd.TimeCode.Default()).ExtractTranslation()
            for a, b in zip(at, (1.0, 0.5, 0.75), strict=True):
                self.assertAlmostEqual(a, b, places=5)
            self.assertEqual(["Shelf/PillA", "Shelf/PillB"], sorted(info["deactivated"]))
            self.assertEqual(["Nope"], info["missing"])
            self.assertTrue(stage.GetPrimAtPath("/World/P3Base/Scene/Shelf/Keep").IsActive())
            node = stage.GetPrimAtPath("/World/P3Base/Scene/Graph/Node")  # absolute paths inside are remapped
            self.assertEqual(["/World/P3Base/Scene/Marker"],
                             [str(t) for t in node.GetRelationship("inputs:conveyorPrim").GetTargets()])

    def test_add_base_scene_reports_active_articulation_roots(self):
        try:
            from pxr import Usd, UsdGeom, UsdPhysics
        except ImportError:
            self.skipTest("usd-core not installed")
        import tempfile

        from p3sim import base_scene

        with tempfile.TemporaryDirectory() as tmp:
            base_path = Path(tmp) / "base.usda"
            base = Usd.Stage.CreateNew(str(base_path))
            world = UsdGeom.Xform.Define(base, "/World")
            base.SetDefaultPrim(world.GetPrim())
            for name in ("ridgeback", "old_arm", "shelf"):
                UsdGeom.Xform.Define(base, f"/World/{name}")
            for name in ("ridgeback", "old_arm"):
                UsdPhysics.ArticulationRootAPI.Apply(base.GetPrimAtPath(f"/World/{name}"))
            base.GetRootLayer().Save()
            stage = Usd.Stage.CreateInMemory()
            UsdGeom.Xform.Define(stage, "/World")
            info = base_scene.add_base_scene(stage, str(base_path), (0.0, 0.0, 0.0, 0.0), ["old_arm"])
        self.assertEqual(["ridgeback"], info["articulations"])  # the deactivated one is not reported

    def test_add_base_scene_root_prims_outside_the_default_prim(self):
        """9/23: 병원 주행 씬의 병상 여섯이 기본 프림 밖 루트에 있어 reference 로는 빠졌다."""
        try:
            from pxr import Gf, Usd, UsdGeom
        except ImportError:
            self.skipTest("usd-core not installed")
        import tempfile

        from p3sim import base_scene

        with tempfile.TemporaryDirectory() as tmp:
            base_path = Path(tmp) / "base.usda"
            base = Usd.Stage.CreateNew(str(base_path))
            world = UsdGeom.Xform.Define(base, "/World")
            base.SetDefaultPrim(world.GetPrim())
            bed = UsdGeom.Xform.Define(base, "/Bed_05")
            bed.AddTranslateOp().Set(Gf.Vec3d(23.7, 1.4, 0.0))
            base.DefinePrim("/Render")              # 렌더 설정 — 싣지 않는다
            base.OverridePrim("/SideTable_over")    # over — 정의가 아니라 싣지 않는다
            base.GetRootLayer().Save()
            self.assertEqual(["Bed_05"], base_scene.root_prims_outside_default(base_path))

            off = Usd.Stage.CreateInMemory()
            info = base_scene.add_base_scene(off, str(base_path), (0.0, 0.0, 0.0, 0.0))
            self.assertEqual(["Bed_05"], info["root_prims_skipped"])
            self.assertEqual([], info["root_prims_loaded"])
            self.assertFalse(off.GetPrimAtPath("/World/P3Base/SceneRoot/Bed_05"))

            on = Usd.Stage.CreateInMemory()
            info = base_scene.add_base_scene(on, str(base_path), (0.0, 0.0, 0.0, 0.0), root_prims=True)
            self.assertEqual(["Bed_05"], info["root_prims_loaded"])
            self.assertEqual([], info["root_prims_skipped"])
            placed = UsdGeom.Xformable(on.GetPrimAtPath("/World/P3Base/SceneRoot/Bed_05"))
            at = placed.ComputeLocalToWorldTransform(Usd.TimeCode.Default()).ExtractTranslation()
            for a, b in zip(at, (23.7, 1.4, 0.0), strict=True):
                self.assertAlmostEqual(a, b, places=5)

    def test_stage_warns_about_root_prims_it_did_not_load(self):
        source = (STANDALONE / "pharmacy_stage.py").read_text()
        self.assertIn("WARN base_scene root prims outside the default prim not loaded", source)

    def test_hospital_nav_preset_needs_the_scene_and_the_dock(self):
        args = STAGE.parse_args(["--preset", "hospital-nav"])
        self.assertTrue(args.no_room and args.amr and args.base_root_prims)
        self.assertEqual(["ridgeback_ur5", "Graph", "gripper", STAGE.HOSPITAL_CORRIDOR_CART], args.base_deactivate)
        self.assertEqual([0.0, 0.0, 0.0, 0.0], list(args.pharmacy_origin))
        problems = " ".join(STAGE.validate(args))
        self.assertIn("--preset hospital-nav needs --base-usd", problems)
        self.assertIn("--preset hospital-nav needs --amr-start", problems)

    def test_amr_is_built_without_the_room(self):
        """--no-room 이어도 --amr 이면 AMR 을 만든다. 예전에는 방 블록 안이라 조용히 빠졌다."""
        source = (STANDALONE / "pharmacy_stage.py").read_text()
        room = source.index("        if not args.no_room:\n")
        amr = source.index("        if args.amr:\n            # 방(--no-room)과 무관하게 만든다")
        self.assertGreater(amr, room)
        self.assertIn('with common.step(log, "build_amr"):', source[amr:amr + 400])

    def test_stage_warns_about_scene_articulations(self):
        source = (STANDALONE / "pharmacy_stage.py").read_text()
        self.assertIn('WARN base_scene articulations this stage does not drive: {info[\'articulations\']}', source)

    def test_hospital_scene_layer_report(self):
        try:
            import pxr  # noqa: F401
        except ImportError:
            self.skipTest("usd-core not installed")
        spec = importlib.util.spec_from_file_location("hospital_scene_check",
                                                      STANDALONE / "hospital_scene_check.py")
        check = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(check)
        report = check.layer_report(self.SCENE)
        self.assertEqual(("World", 1.0, "Z"), (report["default_prim"], report["meters_per_unit"], report["up_axis"]))
        self.assertEqual([], report["ros_or_clock_nodes"])  # no /clock author in the scene (#164)
        self.assertEqual([], report["physics_scenes"])
        self.assertEqual(19, len(report["graphs"]))
        robots = {r["prim"] for r in report["robot_references"]}
        self.assertEqual({"/World/ridgeback_ur5"}, robots)
        self.assertEqual([0.0, 0.0, 0.0], report["top_level"]["/World"]["translate"])
        self.assertEqual([0.5, 0.5, 0.5], report["top_level"]["/World/Conveyor"]["scale"])


class HospitalPresetTests(unittest.TestCase):
    """재범 결정 (9/18, #215 코멘트): --preset hospital-v2 = demo-ros-refill-v2 on 세준's hospital, site A."""

    # 세준 pharmacy room in the hospital scene's world frame (hospital_scene_check.py, 9/18): inner wall faces and
    # the ceiling underside (Geo_M2_Ceiling* at z 3.0).
    ROOM = ((-10.68, 5.51, 0.0), (3.03, 12.19, 3.0))

    def args(self, *extra):
        import tempfile

        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        scene = Path(self.tmp.name) / "p3-hospital.usda"
        scene.write_text("#usda 1.0\n")
        return STAGE.parse_args(["--preset", "hospital-v2", "--base-usd", str(scene), *extra])

    def test_preset_is_v2_on_site_a_with_the_decided_prims_off(self):
        from p3sim import base_scene

        args = self.args()
        self.assertEqual([], STAGE.validate(args))
        self.assertEqual(list(base_scene.HOSPITAL_ORIGIN_A), args.pharmacy_origin)
        self.assertEqual([0.25, 10.52854210179955, 0.0, 0.0], args.pharmacy_origin)
        self.assertNotIn("manipulator", args.base_deactivate)  # M0617 is no longer in the scene (b9ba0d6)
        self.assertEqual(47, len(args.base_deactivate))
        self.assertEqual(19, sum(1 for p in args.base_deactivate if p.startswith("Conveyor/")))  # scene belt graphs
        self.assertEqual(19, len(args.base_rigid_off))  # scene belt bodies
        v2 = vars(STAGE.parse_args(["--preset", "demo-ros-refill-v2"]))
        hospital = vars(args)
        differ = {k for k in v2 if v2[k] != hospital[k]}
        self.assertEqual({"preset", "base_usd", "pharmacy_origin", "base_deactivate", "base_rigid_off"}, differ)

    def test_preset_needs_the_scene(self):
        problems = STAGE.validate(STAGE.parse_args(["--preset", "hospital-v2"]))
        self.assertTrue(any("hospital-v2 needs --base-usd" in p for p in problems))

    def test_layout_and_inventory_do_not_change_with_the_hospital(self):
        import pharmacy_layout_json

        args = self.args()
        v2 = STAGE.parse_args(["--preset", "demo-ros-refill-v2"])
        with_base, without = STAGE.room(args), STAGE.room(v2)
        self.assertEqual(with_base["boxes"], without["boxes"])
        self.assertEqual(with_base["v2"], without["v2"])
        self.assertEqual(STAGE.v2_rail_info(args), STAGE.v2_rail_info(v2))
        scene = str(Path(self.tmp.name) / "p3-hospital.usda")
        self.assertEqual(pharmacy_layout_json.build(["--preset", "demo-ros-refill-v2"]),
                         pharmacy_layout_json.build(["--preset", "hospital-v2", "--base-usd", scene]))

    def test_cameras_stand_in_the_hospital_room(self):
        from p3sim import base_scene, views

        low, high = self.ROOM
        for name in views.VIEW_NAMES:
            eye = base_scene.stage_to_base(views.view("v2", name)[0], base_scene.HOSPITAL_ORIGIN_A)
            for i in range(3):
                self.assertTrue(low[i] + 0.3 < eye[i] < high[i] - 0.3, f"{name} eye {eye}")

    def test_lists_name_prims_of_the_committed_scene_layer(self):
        try:
            from pxr import Sdf
        except ImportError:
            self.skipTest("usd-core not installed")
        from p3sim import base_scene

        layer = Sdf.Layer.FindOrOpen(str(STANDALONE.parent / "scenes" / "hospital_layout.usda"))
        listed = base_scene.HOSPITAL_DEACTIVATE + base_scene.HOSPITAL_RIGID_OFF
        specs = {p: layer.GetPrimAtPath(f"/World/{p}") for p in listed}
        self.assertEqual([], [p for p, spec in specs.items() if not spec])  # every listed path has a spec in the layer
        self.assertFalse(layer.GetPrimAtPath("/World/manipulator"))  # M0617 left the scene in b9ba0d6 (#233)
        defined = [p for p, spec in specs.items() if spec.specifier == Sdf.SpecifierDef]
        self.assertEqual(16, sum(1 for p in defined if "/ConveyorBeltGraph" in p))
        self.assertEqual(18, len(defined))  # + the 2 east wall pieces
        # The other 48 are "over" specs on prims of the referenced hospital/conveyor assets: that the assets still hold
        # them needs the assets (prepared scene, hospital_scene_check.py), not this layer.
        self.assertEqual(48, len(listed) - len(defined))


class WindowHalfTests(unittest.TestCase):
    """재범 9/18 발표 화면: Isaac on the left half, 관제 웹 on the right."""

    def test_window_half_config(self):
        from p3sim import views

        left = views.window_half("left", (1920, 1080), environ={"P3_RENDER_MAX": ""})
        self.assertEqual((960, 1080, 960, 1080),
                         (left["window_width"], left["window_height"], left["width"], left["height"]))
        self.assertIn("--/app/window/x=0", left["extra_args"])
        self.assertIn("--/persistent/app/window/width=960", left["extra_args"])
        self.assertIn("--/app/window/x=960", views.window_half("right", (1920, 1080))["extra_args"])
        self.assertIn("--/app/window/x=1280", views.window_half("right", (2560, 1440))["extra_args"])

    def test_full_window_for_the_film_take(self):
        """재범 9/24 14:4x 촬영 테이크: 창이 화면 전체, 렌더 상한 1920x1080 이면 뷰포트가 화면 해상도다."""
        from p3sim import views

        full = views.window_half("full", (1920, 1080), environ={"P3_RENDER_MAX": "1920x1080"})
        self.assertEqual((1920, 1080, 1920, 1080),
                         (full["window_width"], full["window_height"], full["width"], full["height"]))
        self.assertIn("--/app/window/x=0", full["extra_args"])
        self.assertEqual("full", STAGE.parse_args(["--window-half", "full"]).window_half)

    def test_render_is_capped_by_default_and_the_window_is_not(self):
        """작전 결정 5(9/23): 창은 그대로 두고 렌더만 1280x720 상자 안으로(비율 유지)."""
        from p3sim import views

        # master02 내장 패널 --screen-size 2048 1152: 창 1024x1152, 렌더 1024x1152 → 640x720.
        half = views.window_half("left", (2048, 1152), environ={})
        self.assertEqual((1024, 1152, 640, 720),
                         (half["window_width"], half["window_height"], half["width"], half["height"]))
        self.assertIn("--/persistent/app/window/width=1024", half["extra_args"])
        wide = views.window_half("left", (4096, 1152), environ={})
        self.assertEqual((1280, 720), (wide["width"], wide["height"]))

    def test_render_max_env(self):
        from p3sim import views

        self.assertEqual((1280, 720), views.render_max({}))
        self.assertIsNone(views.render_max({"P3_RENDER_MAX": ""}))  # 최종 촬영: 상한 없음
        self.assertEqual((1920, 1080), views.render_max({"P3_RENDER_MAX": "1920X1080"}))
        for bad in ("1280", "wide", "0x720"):
            with self.assertRaises(ValueError):
                views.render_max({"P3_RENDER_MAX": bad})
        self.assertEqual((2048, 1152), views.fit_render(2048, 1152, None))
        self.assertEqual((800, 450), views.fit_render(800, 450, (1280, 720)))  # 이미 안이면 그대로

    def test_window_half_arguments(self):
        self.assertIsNone(STAGE.parse_args([]).window_half)
        self.assertIsNone(STAGE.parse_args(["--preset", "demo-ros-refill-v2"]).window_half)
        args = STAGE.parse_args(["--preset", "demo-ros-refill-v2", "--window-half", "left"])
        self.assertEqual(("left", [1920, 1080]), (args.window_half, args.screen_size))
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            STAGE.parse_args(["--window-half", "top"])

    def test_tall_aspect_keeps_the_width_and_sees_more_height(self):
        from p3sim import views

        eye, target = views.view("v2", "overview")
        point = (target[0], target[1], target[2] + 1.2)  # above the 16:9 frame, inside the taller one
        self.assertFalse(views.in_frame(eye, target, point))
        self.assertTrue(views.in_frame(eye, target, point, aspect=views.HALF_SCREEN_ASPECT))


class RenderEvery(unittest.TestCase):
    """`--render-every N`: 물리는 그대로 두고 그리기만 N 틱에 한 번(최적화 9/23, 작전 승인)."""

    def test_default_draws_every_tick(self):
        args = STAGE.parse_args([])
        self.assertEqual(args.render_every, 1)
        self.assertAlmostEqual(STAGE.render_hz(args), 1.0 / args.render_dt)

    def test_the_sensor_rate_follows_the_real_drawing_rate(self):
        """여기서 나누지 않으면 `--camera-max-hz` 가 거짓이 된다 — 그래프는 그려질 때만 돈다."""
        for every, expected in ((1, 60.0), (2, 30.0), (4, 15.0)):
            args = STAGE.parse_args(["--render-every", str(every)])
            self.assertAlmostEqual(STAGE.render_hz(args), expected, places=6)

    def test_zero_or_negative_is_refused(self):
        for bad in ("0", "-1"):
            with self.assertRaises(SystemExit):
                STAGE.parse_args(["--render-every", bad])


class HospitalRenderDefault(unittest.TestCase):
    """병원 preset 은 2 틱에 한 번 그린다(최적화 대조, 마클1 5a10c79 회차11 vs 12)."""

    def test_hospital_presets_draw_every_other_tick(self):
        for preset in ('hospital', 'hospital-full'):
            args = STAGE.parse_args(['--preset', preset])
            self.assertEqual(args.render_every, 2, preset)
            self.assertAlmostEqual(STAGE.render_hz(args), 30.0, places=6)

    def test_other_presets_are_unchanged(self):
        for preset in ('emptyworld-loop', 'demo-ros-refill-v2'):
            self.assertEqual(STAGE.parse_args(['--preset', preset]).render_every, 1, preset)

    def test_the_flag_still_wins_for_the_final_takes(self):
        """인자 없이 찍을 회차를 위해 되돌릴 수 있어야 한다(최적화 요청)."""
        self.assertEqual(STAGE.parse_args(['--preset', 'hospital', '--render-every', '1']).render_every, 1)
