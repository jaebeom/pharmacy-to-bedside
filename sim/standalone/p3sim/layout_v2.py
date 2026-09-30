"""Pharmacy scene v2 (재범 9/18): 3-axis rail, four shelves, two canister kinds, a round bin and a module hole.

No Isaac imports. Every number here is a placeholder ("임시") until the scene moves to 세준's real USD; the stage
takes them from default_v2() and the arguments. Frame and units as layout.py (metres, z up, rail origin (0, 0.30, 0)).

- Shelves: two fixed floor shelves and two fixed shelves standing on them, against the back wall (front y 0.75).
  Only the top row of the upper shelves is open above ("top" access); every other cell has a board above it and is
  reached from the front ("front" access).
- Canisters: "cylinder" on the floor shelves, "module" (upright box) on the upper shelves (placeholder assignment).
- Round bin: an open cylinder (ring of boxes) on a ledge in front of the dispenser; cylinders go in from above.
- Module hole: a rectangular pocket in the dispenser's front face; modules are pushed in along +y.
"""

import math

from . import geometry as G
from .layout import COLORS, Box, shelf_boxes

SOURCE = "임시(9/18 재범 지시, 세준 실제 USD 로 옮길 때 바뀜)"


def default_v2():
    return {
        # Limits keep rail targets away from the joint limits (9/17: a target at the limit stopped short and timed
        # out). 실습7-a (9/18): the module insert asked for x 1.150 (limit 1.20) and z 0.576 (limit 0.60) and the rail
        # bounced to the x limit, so the x stroke is ±1.40 and rail_z 0..0.80 (placeholders).
        "rail_x_stroke": 2.8,
        # 재범 (실습7-a, 9/18): when picking, the robot base should sit near/below the canister, lower than its home
        # pose, for the shortest reach. The 0.60 pedestal kept the base above the floor-shelf canisters (z 0.36), so
        # v2 uses a 0.25 pedestal and rail_z 0..1.10: base z 0.25..1.35 (placeholders, 작전 approved 9/18).
        "carriage_height": 0.25,
        "rail_z_limits": (0.0, 1.10),
        "shelf_front_y": 0.75, "shelf_depth": 0.32, "board": 0.02, "cell": (0.30, 0.30),
        # 재범 9/18 (a_plinth055): the arm had no front pose for the floor shelves' bottom row at z 0.36 (link_2 hit the
        # boards or the lift plate); with the first board at 0.55 all 16 cells pass with the rail >= 0.10 m inside
        # its limits (arm session search, 1 cm clearance). The upper shelves stand on the floor shelves (z0 = 1.15).
        "shelves": (
            {"name": "floor_left", "x0": -1.30, "z0": 0.0, "plinth": 0.55, "rows": 2, "cols": 2, "open_top": False,
             "type": "cylinder"},
            {"name": "floor_right", "x0": -0.60, "z0": 0.0, "plinth": 0.55, "rows": 2, "cols": 2, "open_top": False,
             "type": "cylinder"},
            {"name": "upper_left", "x0": -1.30, "z0": 1.15, "plinth": 0.02, "rows": 2, "cols": 2, "open_top": True,
             "type": "module"},
            {"name": "upper_right", "x0": -0.60, "z0": 1.15, "plinth": 0.02, "rows": 2, "cols": 2, "open_top": True,
             "type": "module"},
        ),
        # Item per canister kind (placeholder; items from src/rokey_p3_orchestrator/config/dispenser.yaml).
        "items": {"cylinder": "drug-amox", "module": "drug-ibu"},
        "cylinder": {"diameter": 0.07, "height": 0.12},
        "module": {"x": 0.06, "y": 0.10, "z": 0.14},
        # Inner diameter 0.10 -> 0.12 (실습7-a5 9/18: the 0.07 cylinder touched the wall 1.3 s before release; the
        # arm agreed - 2.5 cm a side, rail poses and 16/16 unchanged). Outer ring 0.14 stays on the ledge (test).
        "round_bin": {"center_xy": (0.90, 0.56), "inner_diameter": 0.12, "wall": 0.01, "floor_z": 0.85,
                      "height": 0.12, "segments": 16},
        "ledge": {"x_range": (0.80, 1.00), "top_z": 0.85, "thickness": 0.02},
        "module_hole": {"center": (1.15, 0.70, 1.02), "opening": (0.08, 0.16), "depth": 0.15},
    }


def _pascal(name):
    return "".join(part.capitalize() for part in name.split("_"))


def shelves(params):
    """(boxes, cells). cells[id] = {shelf, row, col, type, access, surface (x, y, z), size, height}."""
    boxes, cells = [], {}
    for spec in params["shelves"]:
        origin = (spec["x0"], params["shelf_front_y"], spec["z0"])
        parts, centers = shelf_boxes(origin, spec["cols"], spec["rows"], params["cell"], params["shelf_depth"],
                                     plinth=spec["plinth"], board=params["board"], open_top=spec["open_top"])
        prefix = _pascal(spec["name"])
        color = COLORS.get(f"shelf_{spec['name']}", COLORS["shelf"])
        boxes += [box._replace(name=prefix + box.name, color=color) for box in parts]
        boxes += shelf_frame(prefix, origin, spec, params)
        kind = spec["type"]
        size = dict(params[kind])
        height = size["height"] if kind == "cylinder" else size["z"]
        for (row, col), surface in sorted(centers.items()):
            top_row = row == spec["rows"] - 1
            cells[f"{spec['name']}/r{row}c{col}"] = {
                "shelf": spec["name"], "row": row, "col": col, "type": kind,
                "access": "top" if top_row and spec["open_top"] else "front",
                "surface": surface, "size": size, "height": height,
            }
    return boxes, cells


def shelf_frame(prefix, origin, spec, params, bar=0.03, thick=0.01):
    """Dark front frame of one shelf (visual only, no collision, not an obstacle): corner posts over the side panels'
    front edges and bars along the bottom and top front edges. 재범 실습6 (9/18): the four shelves read as one
    rectangle; the frames outline each shelf without moving any cell (inventory, layout JSON and arm teach keep
    their coordinates). The frame sits `thick` in front of the shelf face."""
    x0, y_front, z0 = origin
    board = params["board"]
    width = spec["cols"] * params["cell"][0]
    height = spec["plinth"] + spec["rows"] * params["cell"][1]
    y = y_front - thick / 2.0
    color = COLORS["shelf_frame_upper" if spec["name"].startswith("upper") else "shelf_frame_floor"]
    left, right = x0 - board, x0 + width + board
    return [
        Box(f"{prefix}FramePostLeft", (left + bar / 2.0, y, z0 + height / 2.0), (bar, thick, height), color, "visual"),
        Box(f"{prefix}FramePostRight", (right - bar / 2.0, y, z0 + height / 2.0), (bar, thick, height), color,
            "visual"),
        Box(f"{prefix}FrameBottom", ((left + right) / 2.0, y, z0 + bar / 2.0), (right - left, thick, bar), color,
            "visual"),
        Box(f"{prefix}FrameTop", ((left + right) / 2.0, y, z0 + height - bar / 2.0), (right - left, thick, bar), color,
            "visual"),
    ]


def canister_home(cell):
    """Centre of the canister standing on its cell."""
    x, y, z = cell["surface"]
    return (x, y, z + cell["height"] / 2.0)


def round_bin_boxes(spec):
    """Ring of wall boxes (yaw set per box) and a floor plate. Returns (boxes, target)."""
    cx, cy = spec["center_xy"]
    inner = spec["inner_diameter"] / 2.0
    wall, height, floor_z, n = spec["wall"], spec["height"], spec["floor_z"], spec["segments"]
    radius = inner + wall / 2.0
    length = 2.0 * math.pi * radius / n * 1.08  # small overlap so the ring has no gaps
    boxes = [Box("RoundBinFloor", (cx, cy, floor_z + wall / 2.0), (2 * (inner + wall), 2 * (inner + wall), wall),
                 COLORS["round_bin"], "fixed")]
    for i in range(n):
        angle = 2.0 * math.pi * i / n
        center = (cx + radius * math.cos(angle), cy + radius * math.sin(angle), floor_z + wall + height / 2.0)
        boxes.append(Box(f"RoundBinWall{i:02d}", center, (wall, length, height), COLORS["round_bin"], "fixed",
                         angle))
    target = {"center": [cx, cy, floor_z + wall + height], "inner_diameter": spec["inner_diameter"],
              "floor_z": floor_z + wall, "depth": height, "axis": [0.0, 0.0, -1.0]}
    return boxes, target


def dispenser_with_hole(origin, size, hole):
    """Dispenser cabinet split around a pocket in its -y face. Returns (boxes, target)."""
    cx, cy, z0 = origin
    sx, sy, sz = size
    hx, face_y, hz = hole["center"]
    ox, oz = hole["opening"]
    depth = hole["depth"]
    x_lo, x_hi = cx - sx / 2.0, cx + sx / 2.0
    y_front, y_back = cy - sy / 2.0, cy + sy / 2.0
    if abs(face_y - y_front) > 1e-9:
        raise ValueError(f"module hole centre y {face_y} must lie on the dispenser face y {y_front}")
    hx_lo, hx_hi, hz_lo, hz_hi = hx - ox / 2.0, hx + ox / 2.0, hz - oz / 2.0, hz + oz / 2.0
    y_mid = y_front + depth
    color = COLORS["dispenser"]

    def box(name, lo, hi):
        return Box(name, tuple((a + b) / 2.0 for a, b in zip(lo, hi, strict=True)),
                   tuple(b - a for a, b in zip(lo, hi, strict=True)), color, "fixed")

    boxes = [
        box("DispenserBody", (x_lo, y_mid, z0), (x_hi, y_back, z0 + sz)),  # behind the pocket
        box("DispenserFrontLeft", (x_lo, y_front, z0), (hx_lo, y_mid, z0 + sz)),
        box("DispenserFrontRight", (hx_hi, y_front, z0), (x_hi, y_mid, z0 + sz)),
        box("DispenserFrontBelow", (hx_lo, y_front, z0), (hx_hi, y_mid, hz_lo)),
        box("DispenserFrontAbove", (hx_lo, y_front, hz_hi), (hx_hi, y_mid, z0 + sz)),
    ]
    target = {"entry_center": [hx, face_y, hz], "opening": {"x": ox, "z": oz}, "depth": depth, "axis": [0.0, 1.0, 0.0]}
    return boxes, target


def ledge_box(spec, face_y, bin_spec):
    """Plate from the dispenser face out under the round bin."""
    y_lo = bin_spec["center_xy"][1] - bin_spec["inner_diameter"] / 2.0 - bin_spec["wall"] - 0.01
    x_lo, x_hi = spec["x_range"]
    top, thick = spec["top_z"], spec["thickness"]
    return Box("DispenserLedge", ((x_lo + x_hi) / 2.0, (y_lo + face_y) / 2.0, top - thick / 2.0),
               (x_hi - x_lo, face_y - y_lo, thick), COLORS["dispenser"], "fixed")


def judge_target(point, round_target, module_target):
    """'round' when point (canister centre) is inside the bin's inner cylinder, 'module' when it is past the dispenser
    face (more than half in) inside the hole's cross-section, else 'none'."""
    x, y, z = point
    cx, cy, rim = round_target["center"]
    if (math.hypot(x - cx, y - cy) <= round_target["inner_diameter"] / 2.0
            and round_target["floor_z"] <= z <= rim):
        return "round"
    hx, face_y, hz = module_target["entry_center"]
    if (face_y < y <= face_y + module_target["depth"] and abs(x - hx) <= module_target["opening"]["x"] / 2.0
            and abs(z - hz) <= module_target["opening"]["z"] / 2.0):
        return "module"
    return "none"


def aabb_of(box):
    """Axis-aligned bounds of a box, rotated about z by its yaw (conservative for the clearance model)."""
    yaw = getattr(box, "yaw", 0.0) or 0.0
    hx, hy, hz = (s / 2.0 for s in box.size)
    ex = abs(math.cos(yaw)) * hx + abs(math.sin(yaw)) * hy
    ey = abs(math.sin(yaw)) * hx + abs(math.cos(yaw)) * hy
    return {"name": box.name, "center": list(box.center), "size": [2 * ex, 2 * ey, 2 * hz]}


def rail_parts(origin, x_stroke, y_limits, base_height, carriage_height, lift=True, lift_travel=0.0):
    """The rail's own boxes for the arm's clearance model: world axis-aligned box at rail (0, 0, 0) and the rail axes
    that move it (Track [], CarriageX ["x"], CarriageY ["x", "y"], CarriageZ ["x", "y", "z"]). The pedestal stays on
    CarriageY; only the lift plate rides rail_z. From layout.rail_link_parts, the same numbers scene.py builds."""
    from .layout import RAIL_LINK_JOINTS, rail_link_parts

    link_origin = (origin[0], origin[1], origin[2] + base_height / 2.0)
    out = []
    for link, parts in rail_link_parts(x_stroke, y_limits, base_height, carriage_height, lift=lift,
                                       lift_travel=lift_travel).items():
        moves = [joint.split("_")[1] for joint in RAIL_LINK_JOINTS[link]]
        for name, center, size, _color, collide in parts:
            out.append({"name": name, "link": link, "moves": moves, "collision": bool(collide),
                        "center": [round(o + c, 4) for o, c in zip(link_origin, center, strict=True)],
                        "size": [round(v, 4) for v in size]})
    return out


def canister_id(cell_id):
    return "can-" + cell_id.replace("/", "-")


def inventory(cells, present, targets, obstacles, last_release=None, stamp=None, rail=None, items=None):
    """The /m0609/shelf/inventory JSON object (dict).

    Per cell: canister_id, item (item_id), type, access, present, pose (canister centre, yaw 0 = the upright
    orientation of default_v2 sizes), size. `items` maps item_id -> type (the Refill goal only names the item_id).
    `rail` carries joint names, limits and the base origin so the arm node does not hard-code them."""
    items = items or default_v2()["items"]
    out_cells = []
    for cell_id, cell in sorted(cells.items()):
        out_cells.append({"cell": cell_id, "canister_id": canister_id(cell_id), "item": items.get(cell["type"]),
                          "shelf": cell["shelf"], "row": cell["row"], "col": cell["col"],
                          "type": cell["type"], "access": cell["access"], "present": bool(present.get(cell_id, True)),
                          "pose": {"xyz": [round(v, 4) for v in canister_home(cell)], "yaw": 0.0},
                          "size": cell["size"]})
    return {"v": 1, "stamp": stamp or {"sec": 0, "nanosec": 0}, "scene": "v2", "source": SOURCE,
            "items": {item: kind for kind, item in items.items()}, "rail": rail,
            "cells": out_cells, "targets": targets, "obstacles": obstacles, "last_release": last_release}


def quat_yaw(yaw):
    return G.yaw_quat(yaw)


# --- 평행이동(병원 전체 preset, #527 H1) ------------------------------------------
# 조제실 모듈을 다른 월드(병원 씬)에 통째로 옮길 때 쓴다. 회전은 없다 — yaw·z·치수·레일 관절값은 그대로다.
# 어느 키가 월드 자리인지 여기에 적어 둔다. 새 키를 넣으면 시험이 어느 쪽인지 적으라고 깨진다.

#: default_v2 에서 월드 xy 를 가진 키. 나머지(V2_RELATIVE_KEYS)는 치수·관절 한계·항목이다.
V2_WORLD_KEYS = ("shelves", "shelf_front_y", "round_bin", "ledge", "module_hole")
V2_RELATIVE_KEYS = ("rail_x_stroke", "carriage_height", "rail_z_limits", "shelf_depth", "board", "cell", "items",
                    "cylinder", "module")

#: layout.default_layout() 에서 월드 자리를 가진 키. 점(x, y, z)·x 하나·y 하나·y 구간으로 나눈다.
ROOM_WORLD_POINTS = ("rail_origin", "shelf_origin", "dispenser_origin", "ur5_base", "deck_center", "ur5_ready")
ROOM_WORLD_X = ("wall_x",)
ROOM_WORLD_Y = ("door_y",)
ROOM_WORLD_Y_RANGES = ("wall_y_range",)
#: 레일 원점 기준 값(rail_y_limits·reach_offset·inlet_offset)과 치수. 평행이동에 안 바뀐다.
ROOM_RELATIVE_KEYS = ("rail_x_stroke", "rail_y_limits", "rail_base_height", "carriage_height", "shelf_cols",
                      "shelf_rows", "shelf_cell", "shelf_depth", "shelf_plinth", "canister_size", "pick_cell",
                      "reach_offset", "inlet_offset", "inlet_gap", "clearance", "grip_depth", "dispenser_size",
                      "inlet_size", "inlet_height", "inlet_wall", "outlet_height", "outlet_size", "belt_length",
                      "belt_width", "belt_top", "deck_count", "deck_slot_size", "deck_wall", "wall_height",
                      "wall_thickness", "door_width", "belt_opening_above")


def _shift(point, dx, dy):
    return (point[0] + dx, point[1] + dy, *point[2:])


def translated(params, dx, dy):
    """default_v2 모양의 매개변수를 (dx, dy) 만큼 평행이동한 사본. 원본은 안 바뀐다.

    옮기는 것은 V2_WORLD_KEYS 뿐이다: 선반 x0·앞면 y, 둥근 통 중심, 선반턱 x 구간, 모듈 구멍 중심.
    레일 원점·조제기 원점은 이 사전에 없다(스테이지 인자) — translated_room 으로 같이 옮겨야 한다.
    조제기만 옮기고 모듈 구멍을 안 옮기면 dispenser_with_hole 이 ValueError 로 멈춘다(앞면 y 불일치).
    """
    out = dict(params)
    out["shelves"] = tuple(dict(spec, x0=spec["x0"] + dx) for spec in params["shelves"])
    out["shelf_front_y"] = params["shelf_front_y"] + dy
    out["round_bin"] = dict(params["round_bin"], center_xy=_shift(params["round_bin"]["center_xy"], dx, dy))
    x_lo, x_hi = params["ledge"]["x_range"]
    out["ledge"] = dict(params["ledge"], x_range=(x_lo + dx, x_hi + dx))
    out["module_hole"] = dict(params["module_hole"], center=_shift(params["module_hole"]["center"], dx, dy))
    for key in V2_RELATIVE_KEYS:
        if key in params and isinstance(params[key], dict):
            out[key] = dict(params[key])
    return out


def translated_room(room, dx, dy):
    """layout.default_layout() 모양의 사전을 (dx, dy) 만큼 평행이동한 사본. 옮기는 키는 ROOM_WORLD_* 다.

    레일 원점이 옮겨 가므로 레일 관절 목표(원점 기준)는 그대로 나온다. 벨트 시작점은 조제기 배출구에서 나온다.
    """
    out = dict(room)
    for key in ROOM_WORLD_POINTS:
        out[key] = _shift(room[key], dx, dy)
    for key in ROOM_WORLD_X:
        out[key] = room[key] + dx
    for key in ROOM_WORLD_Y:
        out[key] = room[key] + dy
    for key in ROOM_WORLD_Y_RANGES:
        out[key] = (room[key][0] + dy, room[key][1] + dy)
    return out
