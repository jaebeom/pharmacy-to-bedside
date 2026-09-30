"""layout_v2.translated·translated_room: 조제실 모듈 평행이동(#527 H1). Isaac 없음.

    python3 -m unittest sim.tests.test_layout_v2_translate
"""

import copy
import sys
import unittest
from pathlib import Path

STANDALONE = Path(__file__).resolve().parents[1] / "standalone"
sys.path.insert(0, str(STANDALONE))

from p3sim import layout, layout_v2  # noqa: E402

#: 시험용 병원 평행이동(작전 제안값). 기본값에 넣지 않는다.
T = (-7.85, 9.50)
TOL = 1e-9


def v2_scene(params, room):
    """pharmacy_stage.room 의 v2 가지와 같은 조립(순수 부분만): 상자·칸·목표·장애물·레일 블록·벨트 시작."""
    shelf, cells = layout_v2.shelves(params)
    cabinet, module_target = layout_v2.dispenser_with_hole(room["dispenser_origin"], room["dispenser_size"],
                                                           params["module_hole"])
    bin_boxes, round_target = layout_v2.round_bin_boxes(params["round_bin"])
    face_y = room["dispenser_origin"][1] - room["dispenser_size"][1] / 2.0
    _unused, _inlets, outlet = layout.dispenser_boxes(
        room["dispenser_origin"], room["dispenser_size"], room["inlet_size"], room["inlet_height"],
        room["inlet_wall"], room["belt_top"], room["outlet_size"])
    dispenser = cabinet + [layout_v2.ledge_box(params["ledge"], face_y, params["round_bin"])] + bin_boxes
    rails = layout.rail_boxes(room["rail_origin"], params["rail_x_stroke"], room["rail_y_limits"],
                              room["rail_base_height"], params["carriage_height"])
    lift = params["rail_z_limits"][1]
    rail = {"names": ["rail_x", "rail_y", "rail_z"],
            "limits": [[-params["rail_x_stroke"] / 2, params["rail_x_stroke"] / 2], list(room["rail_y_limits"]),
                       list(params["rail_z_limits"])],
            "origin": [room["rail_origin"][0], room["rail_origin"][1],
                       room["rail_origin"][2] + params["carriage_height"]],
            "parts": layout_v2.rail_parts(room["rail_origin"], params["rail_x_stroke"], room["rail_y_limits"],
                                          room["rail_base_height"], params["carriage_height"], lift_travel=lift)}
    targets = {"round": round_target, "module": module_target}
    obstacles = [layout_v2.aabb_of(box) for box in shelf + dispenser + rails if box.kind == "fixed"]
    inventory = layout_v2.inventory(cells, {}, targets, obstacles, rail=rail)
    return {"boxes": shelf + dispenser + rails, "cells": cells, "targets": targets, "inventory": inventory,
            "belt_start": (outlet[0], outlet[1], room["belt_top"])}


class TranslatedTests(unittest.TestCase):
    def setUp(self):
        self.params, self.room = layout_v2.default_v2(), layout.default_layout()
        self.base = v2_scene(self.params, self.room)
        self.moved = v2_scene(layout_v2.translated(self.params, *T),
                              layout_v2.translated_room(self.room, *T))

    def assertShifted(self, before, after, what):
        self.assertAlmostEqual(after[0] - before[0], T[0], delta=TOL, msg=what)
        self.assertAlmostEqual(after[1] - before[1], T[1], delta=TOL, msg=what)
        for a, b in zip(before[2:], after[2:], strict=True):
            self.assertAlmostEqual(a, b, delta=TOL, msg=f"{what}: z 는 그대로여야 한다")

    def assertSame(self, before, after, what):
        for a, b in zip(before, after, strict=True):
            self.assertAlmostEqual(a, b, delta=TOL, msg=what)

    def test_every_key_is_classified(self):
        # 새 키가 어느 쪽인지 안 적히면 조용히 안 옮겨진다. 여기서 막는다.
        self.assertEqual(set(self.params), set(layout_v2.V2_WORLD_KEYS) | set(layout_v2.V2_RELATIVE_KEYS))
        world = (layout_v2.ROOM_WORLD_POINTS + layout_v2.ROOM_WORLD_X + layout_v2.ROOM_WORLD_Y
                 + layout_v2.ROOM_WORLD_Y_RANGES)
        self.assertEqual(set(self.room), set(world) | set(layout_v2.ROOM_RELATIVE_KEYS))
        self.assertFalse(set(world) & set(layout_v2.ROOM_RELATIVE_KEYS))

    def test_inputs_are_not_mutated(self):
        params, room = copy.deepcopy(self.params), copy.deepcopy(self.room)
        layout_v2.translated(self.params, *T)
        layout_v2.translated_room(self.room, *T)
        self.assertEqual(params, self.params)
        self.assertEqual(room, self.room)

    def test_boxes_shift_by_exactly_t(self):
        before = {box.name: box for box in self.base["boxes"]}
        after = {box.name: box for box in self.moved["boxes"]}
        self.assertEqual(set(before), set(after))
        for name, box in before.items():
            self.assertShifted(box.center, after[name].center, name)
            self.assertSame(box.size, after[name].size, f"{name}: 치수")
            self.assertEqual(box.yaw, after[name].yaw, f"{name}: yaw")

    def test_inventory_world_points_shift_and_relative_values_stay(self):
        before, after = self.base["inventory"], self.moved["inventory"]
        for a, b in zip(before["cells"], after["cells"], strict=True):
            self.assertEqual(a["cell"], b["cell"])
            self.assertShifted(a["pose"]["xyz"], b["pose"]["xyz"], a["cell"])
            self.assertEqual(a["pose"]["yaw"], b["pose"]["yaw"])
            self.assertEqual((a["size"], a["type"], a["access"]), (b["size"], b["type"], b["access"]))
        self.assertShifted(before["targets"]["round"]["center"], after["targets"]["round"]["center"], "round")
        self.assertShifted(before["targets"]["module"]["entry_center"], after["targets"]["module"]["entry_center"],
                           "module")
        for key in ("inner_diameter", "depth", "axis"):
            self.assertEqual(before["targets"]["round"][key], after["targets"]["round"][key])
        self.assertAlmostEqual(before["targets"]["round"]["floor_z"], after["targets"]["round"]["floor_z"],
                               delta=TOL)
        for key in ("opening", "depth", "axis"):
            self.assertEqual(before["targets"]["module"][key], after["targets"]["module"][key])
        for a, b in zip(before["obstacles"], after["obstacles"], strict=True):
            self.assertEqual(a["name"], b["name"])
            self.assertShifted(a["center"], b["center"], a["name"])
            self.assertSame(a["size"], b["size"], a["name"])
        self.assertShifted(before["rail"]["origin"], after["rail"]["origin"], "rail.origin")
        self.assertEqual(before["rail"]["limits"], after["rail"]["limits"])
        for a, b in zip(before["rail"]["parts"], after["rail"]["parts"], strict=True):
            self.assertEqual((a["name"], a["link"], a["moves"]), (b["name"], b["link"], b["moves"]))
            self.assertShifted(a["center"], b["center"], a["name"])
        self.assertShifted(self.base["belt_start"], self.moved["belt_start"], "belt_start")

    def test_rail_joint_targets_are_unchanged(self):
        # 관절값(레일 원점 기준)은 평행이동에 안 바뀐다 — 가르친 값·팔 탐색 결과를 그대로 쓸 수 있다.
        room, moved_room = self.room, layout_v2.translated_room(self.room, *T)
        limits = (-self.params["rail_x_stroke"] / 2, self.params["rail_x_stroke"] / 2)
        for cell_id, cell in self.base["cells"].items():
            moved_cell = self.moved["cells"][cell_id]
            joint = layout.rail_target(cell["surface"][:2], room["reach_offset"], limits, room["rail_y_limits"],
                                       room["rail_origin"][:2])
            moved = layout.rail_target(moved_cell["surface"][:2], moved_room["reach_offset"], limits,
                                       moved_room["rail_y_limits"], moved_room["rail_origin"][:2])
            self.assertSame(joint, moved, cell_id)
        for name in ("round", "module"):
            point = self.base["targets"][name].get("center") or self.base["targets"][name]["entry_center"]
            moved = self.moved["targets"][name].get("center") or self.moved["targets"][name]["entry_center"]
            self.assertSame(layout.rail_target(point[:2], room["inlet_offset"], limits, room["rail_y_limits"],
                                               room["rail_origin"][:2]),
                            layout.rail_target(moved[:2], moved_room["inlet_offset"], limits,
                                               moved_room["rail_y_limits"], moved_room["rail_origin"][:2]), name)

    def test_judge_target_answers_the_same(self):
        judge = layout_v2.judge_target
        round_center = self.base["targets"]["round"]["center"]
        inside = (round_center[0], round_center[1], round_center[2] - 0.05)
        moved_inside = (inside[0] + T[0], inside[1] + T[1], inside[2])
        self.assertEqual("round", judge(inside, self.base["targets"]["round"], self.base["targets"]["module"]))
        self.assertEqual("round", judge(moved_inside, self.moved["targets"]["round"],
                                        self.moved["targets"]["module"]))
        self.assertEqual("none", judge(inside, self.moved["targets"]["round"], self.moved["targets"]["module"]))

    def test_half_translation_is_refused(self):
        # 모듈 구멍만 옮기고 조제기를 안 옮기면 앞면이 어긋난다 — 조용히 넘어가지 않고 멈춘다.
        with self.assertRaises(ValueError):
            v2_scene(layout_v2.translated(self.params, *T), self.room)

    def test_zero_translation_is_identity(self):
        self.assertEqual(self.params, layout_v2.translated(self.params, 0.0, 0.0))
        self.assertEqual(self.room, layout_v2.translated_room(self.room, 0.0, 0.0))


if __name__ == "__main__":
    unittest.main()
