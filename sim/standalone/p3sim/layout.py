"""Pharmacy room layout as plain boxes. No Isaac imports; scene.py turns these into prims.

Follows docs/planning/scenario.md 1 (pharmacy room: storage shelf, dispenser, conveyor; loading spot outside the door
at the belt end) and the concept image docs/images/scenario-concept-v0.webp (tall multi-tier shelf with boxes along
the back wall, M0609 in front of it, a tall dispenser cabinet with a refill inlet at arm height, conveyor from the
dispenser to the wall and out to the corridor).
The 2-axis rail under the M0609 is 재범's decision on 9/17 (not in scenario.md, which still says "M0609 조제실 고정"):
the arm rides an X-Y carriage to cover the whole shelf and the dispenser.

Frame: metres, z up, rail centre on the floor at the origin, the back wall toward +y, the corridor toward +x.
Every box is (name, center, size, color, kind) with kind "fixed" (static collider) or "visual" (no collision).
"""

from collections import namedtuple

from . import geometry as G

# yaw (rad about z) defaults to 0; only the v2 round bin's ring walls use it.
Box = namedtuple("Box", ("name", "center", "size", "color", "kind", "yaw"), defaults=(0.0,))
HALF_PI = 1.5707963267948966  # 병상 접근 자리의 yaw(+y 를 바라본다)

COLORS = {
    "shelf": (0.85, 0.85, 0.88), "canister": (0.95, 0.55, 0.15), "canister_pick": (0.90, 0.15, 0.15),
    "dispenser": (0.92, 0.92, 0.95), "inlet_a": (0.20, 0.35, 0.85), "inlet_b": (0.20, 0.70, 0.35),
    "outlet": (0.15, 0.15, 0.18), "rail": (0.35, 0.35, 0.40), "carriage": (0.55, 0.55, 0.60),
    "wall": (0.80, 0.84, 0.88), "loading": (0.30, 0.60, 0.90), "belt_frame": (0.40, 0.40, 0.42),
    # 재범 실습1 P4: the 2-axis rail read as one axis. X tracks yellow, the Y beam (moves with X) orange, the Y carriage
    # (moves along the beam, carries the robot) blue.
    "rail_track": (0.95, 0.80, 0.10), "rail_beam": (0.95, 0.50, 0.10), "carriage_y": (0.20, 0.45, 0.85),
    "carriage_z": (0.25, 0.70, 0.35), "canister_module": (0.55, 0.30, 0.80), "round_bin": (0.20, 0.35, 0.85),
    # v2 shelves by position (재범 실습6: the four shelves read as one rectangle): floor left/right, upper left/right.
    "shelf_floor_left": (0.80, 0.80, 0.84), "shelf_floor_right": (0.66, 0.70, 0.76),
    "shelf_upper_left": (0.86, 0.74, 0.56), "shelf_upper_right": (0.74, 0.60, 0.42),
    "shelf_frame_floor": (0.25, 0.27, 0.30), "shelf_frame_upper": (0.35, 0.22, 0.12),
}
RAIL_TRACK_HEIGHT = 0.08  # visible X tracks (were base_height 0.05, same grey as the floor parts)


def shelf_boxes(origin, cols, rows, cell, depth, plinth=0.25, board=0.02, open_top=True):
    """Open-front rack against the wall. origin = (x_left, y_front, z_floor). Returns (boxes, cell_centers).

    cell = (width, height) of one cell; the lowest board sits at plinth. cell_centers[(row, col)] is the point on the
    board surface at the cell centre (row 0 is the lowest board). open_top leaves out the board above the top row so the
    arm can grasp top-row canisters from above (a board there would sit in the way of a top-down gripper)."""
    x0, y0, z0 = origin
    width, height = cols * cell[0], plinth + rows * cell[1]
    boxes = [
        Box("ShelfBack", (x0 + width / 2, y0 + depth + board / 2, z0 + height / 2), (width, board, height),
            COLORS["shelf"], "fixed"),
        Box("ShelfSideLeft", (x0 - board / 2, y0 + depth / 2, z0 + height / 2), (board, depth, height),
            COLORS["shelf"], "fixed"),
        Box("ShelfSideRight", (x0 + width + board / 2, y0 + depth / 2, z0 + height / 2), (board, depth, height),
            COLORS["shelf"], "fixed"),
    ]
    centers = {}
    for row in range(rows + 1):
        z = z0 + plinth + row * cell[1]
        if row == rows and open_top:
            break
        boxes.append(Box(f"ShelfBoard{row}", (x0 + width / 2, y0 + depth / 2, z - board / 2), (width, depth, board),
                         COLORS["shelf"], "fixed"))
        if row < rows:
            for col in range(cols):
                centers[(row, col)] = (x0 + (col + 0.5) * cell[0], y0 + depth / 2, z)
    return boxes, centers


def dispenser_boxes(origin, size, inlet_size, inlet_height, inlet_wall, outlet_height, outlet_size, inlet_gap=0.0):
    """Tall cabinet. origin = (x_center, y_center, z_floor), size = (x, y, z).

    Refill inlets A and B are open-top boxes on a ledge on the cabinet's -y face (toward the rail) at inlet_height,
    side by side along x (A at -x). The outlet is a dark chute on the +x face at outlet_height where the belt starts.
    inlet_gap is the space between the cabinet face and the inlets' back walls (the ledge covers it).
    Returns (boxes, inlet_centers {'a','b'} as outer-box centres, outlet_point on the +x face)."""
    cx, cy, z0 = origin
    sx, sy, sz = size
    boxes = [Box("DispenserBody", (cx, cy, z0 + sz / 2), size, COLORS["dispenser"], "fixed")]
    ledge_y = cy - sy / 2 - inlet_gap - inlet_size[1] / 2
    ledge = Box("DispenserLedge", (cx, ledge_y + inlet_gap / 2, inlet_height - 0.01),
                (2 * inlet_size[0] + 0.06, inlet_size[1] + inlet_gap, 0.02), COLORS["dispenser"], "fixed")
    boxes.append(ledge)
    inlets = {}
    for letter, dx in (("a", -(inlet_size[0] / 2 + 0.01)), ("b", inlet_size[0] / 2 + 0.01)):
        center = (cx + dx, ledge_y, inlet_height + inlet_size[2] / 2)
        inlets[letter] = center
        boxes.extend(open_box_boxes(f"Inlet{letter.upper()}", center, inlet_size, inlet_wall,
                                    COLORS[f"inlet_{letter}"]))
    outlet_point = (cx + sx / 2, cy, outlet_height)
    boxes.append(Box("DispenserOutlet", (cx + sx / 2 + outlet_size[0] / 2, cy, outlet_height + outlet_size[2] / 2),
                     outlet_size, COLORS["outlet"], "visual"))
    return boxes, inlets, outlet_point


def open_box_boxes(prefix, center, size, wall, color):
    x, y, z = center
    sx, sy, sz = size
    return [
        Box(f"{prefix}Floor", (x, y, z - sz / 2 + wall / 2), (sx, sy, wall), color, "fixed"),
        Box(f"{prefix}WallXMinus", (x - sx / 2 + wall / 2, y, z), (wall, sy, sz), color, "fixed"),
        Box(f"{prefix}WallXPlus", (x + sx / 2 - wall / 2, y, z), (wall, sy, sz), color, "fixed"),
        Box(f"{prefix}WallYMinus", (x, y - sy / 2 + wall / 2, z), (sx, wall, sz), color, "fixed"),
        Box(f"{prefix}WallYPlus", (x, y + sy / 2 - wall / 2, z), (sx, wall, sz), color, "fixed"),
    ]


def wall_boxes(wall_x, y_range, height, thickness, opening_y, opening_z, door_y, door_width):
    """Room wall at x = wall_x between the pharmacy (x < wall_x) and the corridor.

    opening_y/opening_z = (low, high) is the hole the belt passes through; the door is a gap of door_width centred at
    door_y (staff only; AMRs stay outside). Pieces are fixed boxes around both holes."""
    y_low, y_high = y_range
    boxes = []

    def piece(name, y0, y1, z0, z1):
        if y1 - y0 > 1e-6 and z1 - z0 > 1e-6:
            boxes.append(Box(name, (wall_x, (y0 + y1) / 2, (z0 + z1) / 2), (thickness, y1 - y0, z1 - z0),
                             COLORS["wall"], "fixed"))

    door_low, door_high = door_y - door_width / 2, door_y + door_width / 2
    holes = sorted([(opening_y[0], opening_y[1], "belt"), (door_low, door_high, "door")])
    cursor = y_low
    for low, high, kind in holes:
        piece(f"Wall_{kind}_before", cursor, low, 0.0, height)
        if kind == "belt":
            piece("Wall_belt_below", low, high, 0.0, opening_z[0])
            piece("Wall_belt_above", low, high, opening_z[1], height)
        else:
            piece("Wall_door_above", low, high, 2.1, height)
        cursor = high
    piece("Wall_after", cursor, y_high, 0.0, height)
    return boxes


RAIL_LINKS = ("Base", "CarriageX", "CarriageY", "CarriageZ")
RAIL_LINK_JOINTS = {"Base": (), "CarriageX": ("rail_x",), "CarriageY": ("rail_x", "rail_y"),
                    "CarriageZ": ("rail_x", "rail_y", "rail_z")}


LIFT_COLUMN_OVERLAP = 0.02  # the lift column always reaches this far into the pedestal


def rail_link_parts(x_stroke, y_limits, base_height, carriage_height, lift=False, collide_carriages=False,
                    lift_travel=0.0):
    """Boxes of the moving rail links, in each link's frame (link origin = rail origin + (0, 0, base_height / 2) at
    joint zero; CarriageX moves with rail_x, CarriageY with rail_x and rail_y, CarriageZ with all three).
    {link: [(name, center, size, color, collide)]}. Shared by scene.py (prims) and the v2 layout JSON (the arm's
    clearance model), so both use the same numbers. The base track always collides; carriage parts only when
    collide_carriages (v2, 실습7-a 9/18: the robot passed through its own rail)."""
    beam_z = RAIL_TRACK_HEIGHT + 0.05 - base_height / 2.0
    left_y, right_y = y_limits[0] - 0.05, y_limits[1] + 0.05
    beam = COLORS["rail_beam"]
    plate = 0.04 if lift else 0.0
    pedestal_h = carriage_height - base_height - plate
    top = carriage_height - base_height / 2.0
    c = bool(collide_carriages)
    parts = {
        "Base": [("Track", (0.0, 0.0, 0.0), (x_stroke + 0.4, 0.10, base_height), COLORS["rail"], True)],
        "CarriageX": [("YBeam", (0.0, (left_y + right_y) / 2.0, beam_z), (0.14, right_y - left_y + 0.12, 0.06), beam,
                       c),
                      ("TruckLeft", (0.0, left_y, beam_z - 0.04), (0.24, 0.12, 0.06), beam, c),
                      ("TruckRight", (0.0, right_y, beam_z - 0.04), (0.24, 0.12, 0.06), beam, c)],
        "CarriageY": [("Pedestal", (0.0, 0.0, base_height / 2.0 + pedestal_h / 2.0), (0.22, 0.22, pedestal_h),
                       COLORS["carriage"], c),
                      ("YCarriage", (0.0, 0.0, beam_z + 0.05), (0.30, 0.26, 0.05), COLORS["carriage_y"], c)],
    }
    if lift:
        # The robot's base_link sits on the plate; the plate stays visual so it never fights the base (our choice).
        parts["CarriageZ"] = [("LiftPlate", (0.0, 0.0, top - plate / 2.0), (0.28, 0.28, plate), COLORS["carriage_z"],
                               False),
                              # 실습7-a2 (9/18, 재범 "M0609가 공중부양을 하잖아"): with rail_z up to 1.10 the plate and
                              # robot floated above the 0.16 m pedestal. A mast rides with the plate and is lift_travel
                              # + overlap long, so from the pedestal top to the plate there is no gap at any rail_z;
                              # at low rail_z the rest of it sits inside the pedestal and under the floor.
                              ("LiftColumn", (0.0, 0.0, top - plate - (lift_travel + LIFT_COLUMN_OVERLAP) / 2.0),
                               (0.16, 0.16, lift_travel + LIFT_COLUMN_OVERLAP), COLORS["carriage_z"], False)]
    return parts


def rail_boxes(origin, x_stroke, y_limits, base_height, carriage_height):
    """Visual/static parts of the 2-axis rail: two X rails on the floor and a Y beam drawn at the centre.

    The moving carriages are articulation links built in scene.py; these are the fixed tracks. y_limits = rail_y
    joint (lower, upper); joint zero is the origin."""
    ox, oy, oz = origin
    boxes = []
    # Tracks just outside the carriage travel; wider offsets ran into the shelf once the rail moved toward it.
    for side, dy in (("Left", y_limits[0] - 0.05), ("Right", y_limits[1] + 0.05)):
        boxes.append(Box(f"RailX{side}", (ox, oy + dy, oz + RAIL_TRACK_HEIGHT / 2), (x_stroke + 0.4, 0.06,
                                                                                    RAIL_TRACK_HEIGHT),
                         COLORS["rail_track"], "fixed"))
    return boxes


def inlet_cavity(center, size, wall):
    """AABB of the space inside an open-top inlet box (outer centre and size, wall thickness, floor = one wall)."""
    return G.aabb((center[0], center[1], center[2] + wall / 2.0), (size[0] - 2 * wall, size[1] - 2 * wall,
                                                                   size[2] - wall))


def inlet_containing(point, inlets, size, wall):
    """Letter of the inlet whose cavity holds point, or None."""
    for letter in sorted(inlets):
        if G.point_in_aabb(point, inlet_cavity(inlets[letter], size, wall)):
            return letter
    return None


def rail_target(point_xy, reach_offset_xy, x_limits, y_limits, rail_origin_xy=(0.0, 0.0)):
    """Rail joint positions (rail_x, rail_y) that put point_xy at reach_offset_xy from the robot base, clamped to the
    strokes. Joint zero is the rail origin."""
    x = min(max(point_xy[0] - reach_offset_xy[0] - rail_origin_xy[0], x_limits[0]), x_limits[1])
    y = min(max(point_xy[1] - reach_offset_xy[1] - rail_origin_xy[1], y_limits[0]), y_limits[1])
    return x, y


def plan_rail_refill(canister_xyz, canister_height, inlet_center, inlet_size, inlet_wall, rail_origin, reach_offset,
                     x_limits, y_limits, clearance, grip_depth, rail_home=(0.0, 0.0), shelf_front_y=None,
                     pull_margin=0.12, limit_margin=0.02, retreat_back=0.10, inlet_offset=None, carry_z=None,
                     retreat_z=None):
    """One refill cycle on the rail: park at the shelf, pick the canister top-down, park at the inlet, insert, go home.

    Steps are (phase, kind, target, gripper): kind "rail" (target = rail joint positions), "tcp" (target = TCP xyz
    moved in a straight line), "hold" (stay, gripper settles).
    Heights (9/17 master02 d38a2c2: above_canister at z 1.10 stayed 5 cm short with rail_y at its limit):
    - shelf_z = canister top + clearance for everything at the shelf (the top row is open, nothing above it);
    - carry_z clears the inlet rim with the canister hanging below the TCP; the TCP rises to it only after the
      canister is out in front of the shelf (raise), because the inlets stand right in front of the dispenser;
    - retreat_z (after release) defaults to carry_z, as in d38a2c2 where the inlet side reached (insert 0.0033 m);
      carry_z and retreat_z can be given to test other heights without code changes.
    reach_offset is the base-to-target standoff at the shelf, inlet_offset at the inlets (default: reach_offset).
    With shelf_front_y, the TCP enters and leaves the shelf straight along y through a point pull_margin in front, so
    the rail never moves while the canister is inside the rack (9/17: a canister kept at shelf depth hit the
    dispenser body while the rail moved)."""
    cx, cy, cz = canister_xyz
    top = cz + canister_height / 2.0
    below_tcp = canister_height - grip_depth
    inlet_top = inlet_center[2] + inlet_size[2] / 2.0
    inlet_floor = inlet_center[2] - inlet_size[2] / 2.0 + inlet_wall
    shelf_z = top + clearance
    if carry_z is None:
        carry_z = max(inlet_top + clearance + below_tcp, shelf_z)
    if retreat_z is None:
        retreat_z = carry_z
    grasp = (cx, cy, top - grip_depth)
    above_canister = (cx, cy, shelf_z)
    above_inlet = (inlet_center[0], inlet_center[1], carry_z)
    insert = (inlet_center[0], inlet_center[1], inlet_floor + 0.005 + below_tcp)
    # A target exactly at the joint limit (rail_y 0.30) settled at 0.28 and timed out, so targets stay inside.
    x_in = (x_limits[0] + limit_margin, x_limits[1] - limit_margin)
    y_in = (y_limits[0] + limit_margin, y_limits[1] - limit_margin)
    shelf_rail = rail_target((cx, cy), reach_offset, x_in, y_in, rail_origin[:2])
    inlet_rail = rail_target(inlet_center[:2], reach_offset if inlet_offset is None else inlet_offset, x_in, y_in,
                             rail_origin[:2])
    back_off = (inlet_center[0], inlet_center[1] - retreat_back, retreat_z)
    front_y = None if shelf_front_y is None else shelf_front_y - pull_margin
    steps = [("rail_to_shelf", "rail", shelf_rail, "open")]
    if front_y is not None:
        steps.append(("shelf_front", "tcp", (cx, front_y, shelf_z), "open"))
    steps += [
        ("above_canister", "tcp", above_canister, "open"),
        ("descend", "tcp", grasp, "open"),
        ("grasp", "hold", grasp, "close"),
        ("lift", "tcp", above_canister, "close"),
    ]
    if front_y is not None:
        steps.append(("pull_out", "tcp", (cx, front_y, shelf_z), "close"))
        steps.append(("raise", "tcp", (cx, front_y, carry_z), "close"))
    else:
        steps.append(("raise", "tcp", (cx, cy, carry_z), "close"))
    return steps + [
        ("rail_to_inlet", "rail", inlet_rail, "close"),
        ("above_inlet", "tcp", above_inlet, "close"),
        ("insert", "tcp", insert, "close"),
        ("release", "hold", insert, "open"),
        ("retreat", "tcp", back_off, "open"),
        ("rail_home", "rail", tuple(rail_home), "open"),
    ]


def reach_distance(base_xyz, tcp_xyz, tool_length=0.19671, shoulder_height=0.135):
    """Straight-line distance from the arm shoulder to the flange for a tool pointing down.

    A plain distance check, not IK: tool_length is the class-example TCP offset on link_6, shoulder_height is our
    rough M0609 base-to-joint_2 height (not measured). Doosan lists the M0609 reach as 900 mm."""
    shoulder = (base_xyz[0], base_xyz[1], base_xyz[2] + shoulder_height)
    flange = (tcp_xyz[0], tcp_xyz[1], tcp_xyz[2] + tool_length)
    return sum((a - b) ** 2 for a, b in zip(shoulder, flange, strict=True)) ** 0.5


def plan_reach(plan, rail_origin, carriage_height, **kwargs):
    """(phase, shoulder-to-flange distance, horizontal distance from the base axis) for every tcp/hold step, with the
    base where the last rail step parked it."""
    rail = (0.0, 0.0)
    out = []
    for phase, kind, target, _gripper in plan:
        if kind == "rail":
            rail = target
            continue
        base = (rail_origin[0] + rail[0], rail_origin[1] + rail[1], rail_origin[2] + carriage_height)
        horizontal = ((target[0] - base[0]) ** 2 + (target[1] - base[1]) ** 2) ** 0.5
        out.append((phase, reach_distance(base, target, **kwargs), horizontal))
    return out


VIA_PHASES = ("rail_to_shelf", "shelf_front", "above_canister", "lift", "pull_out", "raise", "rail_to_inlet",
              "above_inlet", "retreat", "rail_home")  # pass-through poses: a looser tolerance is enough


def phase_tolerance(phase, kind, rail_tolerance, tcp_tolerance, via_tolerance):
    """Tolerance for ending a refill phase: the rail tolerance for rail moves, loose for pass-through poses,
    precise for descend, grasp, insert and release."""
    if kind == "rail":
        return rail_tolerance
    return via_tolerance if phase in VIA_PHASES else tcp_tolerance


DECK_FRAME_CHILD = "Top"  # ur5_cell: deck_slot_N is Deck/DeckSlot{N}Floor/Top


def deck_slot_frames(center, count, slot_size, wall):
    """World origins of deck_slot_1..count (결정 23: centre of the slot floor's top face, where a pouch rests).

    center = (x, y, z_top_of_plate) as for deck_boxes. The place target deck_boxes returns (outer-box centre) is
    slot_size[2] / 2 - wall above this origin."""
    x, y, z = center
    pitch = slot_size[0] + 0.02
    return [(x - (count - 1) * pitch / 2.0 + i * pitch, y, z + wall) for i in range(count)]


def deck_boxes(center, count, slot_size, wall, color=None):
    """Deck plate with `count` open-top slots in a row along x (contract 3: deck_slot_* frames on the AMR deck).

    center = (x, y, z_top_of_plate). Returns (boxes, slot_centers) with slot_centers[i] = outer-box centre of
    slot i (0-based here, deck_slot_{i+1} in names), used as the place target. The deck_slot_N frame itself is the
    floor's top-face centre (deck_slot_frames), slot_size[2] / 2 - wall below it."""
    color = color or COLORS["loading"]
    x, y, z = center
    pitch = slot_size[0] + 0.02
    width = count * pitch + 0.04
    boxes = [Box("DeckPlate", (x, y, z - 0.01), (width, slot_size[1] + 0.06, 0.02), COLORS["carriage"], "fixed")]
    centers = []
    for i in range(count):
        cx = x - (count - 1) * pitch / 2.0 + i * pitch
        slot_center = (cx, y, z + slot_size[2] / 2.0)
        centers.append(slot_center)
        boxes.extend(open_box_boxes(f"DeckSlot{i + 1}", slot_center, slot_size, wall, color))
    return boxes, centers


#: 트레이(상판 대신 얹는 통짜 상자 하나). 값은 `base_link` **로컬** 기준이다.
#: 9/21 재범 확정안: 칸막이 다섯을 없애고 큰 트레이 하나로 바꾼다. `deck_slot_N` 프레임은 **그 안의
#: 고정된 놓을 자리**로 남는다 — 계약·`target_slot`·결정 28/44·zones·팔 매개변수가 하나도 안 바뀐다.
TRAY = {
    "centre_x": 0.13,        # base_link 로컬. 바깥 x -0.18..0.44 (몸체 앞끝 0.466 안)
    # 안치수 (x, y). 바깥 y ±0.33 (몸체 반폭 0.397 안, 계획 footprint 반폭 0.45 안).
    #
    # y 는 0.56 → **0.64** 다(9/21). 봉투가 옆으로 밀릴 여지와 낙하 산포 여유를 산다.
    #
    # **처음에는 자리1 의 팔 여유(9 mm)를 사려고 넓혔는데, 그것은 안 샀다.** 비전이 다시 풀어
    # 보여 줬다: 제일 가까운 점이 밑동 기준 (−0.406, +0.324, −0.019)이고 턱 윗면이 z −0.051 —
    # **link2(위팔)가 턱 위를 32 mm 높이로 지나간다.** 턱을 옆으로 밀면 팔도 그만큼 바깥에서
    # 턱 위를 지날 뿐이라 높이 차가 그대로다. 제한하는 양이 가로거리가 아니라 **세로 높이**였다.
    # 넓힌 것을 되돌리지는 않는다 — 산 것이 다를 뿐 쓸모없지는 않다. 팔 여유는 `lip` 이 산다.
    "inner": (0.60, 0.64),
    "wall": 0.01,            # 옆 턱 두께. 비전이 이 두께의 얇은 벽 넷으로 모델링해 검증했다
    "floor": 0.028,          # 바닥판 두께. 몸체 윗면 0.301 에 얹으므로 바닥 윗면이 0.329 다
    # 바닥 윗면 위로 선 턱 높이. **자리1 팔 여유의 유일한 레버다** — 1 mm 낮추면 1 mm 늘어난다
    # (비전 9/21: 0.05→9 mm, 0.04→19 mm, 0.03→29 mm, 0.02→39 mm). 위 `inner` 주석을 보라.
    # 0.05 → **0.03**. 봉투 두께(0.01)의 세 배라 굴러 나가는 것은 여전히 막는다 — 봉투는
    # 던지는 것이 아니라 놓는 것이고, 낙하 산포 ±0.04 는 자리 간격과 `slot_accept` 가 본다.
    # **지금 막혀서 낮추는 것이 아니다** — lap8 은 9 mm 로도 touch 0 이었다. 여유를 사는 것이다.
    # 미끄러져 나가면 `in_slot` 참값이 false 로 잡고 `pouch placed … offset_xy=` 가 얼마나
    # 밀렸는지 찍는다. 그 두 줄이 이 값을 되돌릴 근거가 된다.
    "lip": 0.03,
    # 놓을 자리 (x, y), base_link 로컬. 간격 0.18 = 봉투 긴 변 0.10 + 낙하 산포 ±0.04.
    # **셋이다**(작전 권고, 비전이 IK·경로·충돌까지 닫았다 9/21). 상판 다섯 칸에서 줄었다.
    # **이 목록이 자리 수의 단일 출처다.** 다른 데 개수를 또 적지 않는다 — orchestrator 의
    # `TripConfig.deck_slots` 가 5 로 박혀 있어 넷째 주문이 없는 `deck_slot_4` 로 갈 뻔했다
    # (통합&정비 9/21, PR #455). **`tests/test_demo_v2.py` 가 이 개수와 빈월드 프로필의
    # `deck_slots:=N` 을 맞댄다** — 한쪽만 고치면 거기서 걸린다.
    # (내가 "저장소가 달라 못 묶는다" 고 적었던 것은 틀렸다. 같은 저장소다.)
    "slots": ((0.05, -0.18), (0.05, 0.00), (0.05, 0.18)),
    # `in_slot` 참값이 "그 자리에 놓였다" 로 볼 상자 (x, y, z). 자리 중심 기준 대칭이다.
    # **상판 칸(0.14 x 0.11)보다 넓다** — 트레이에는 칸을 가르는 벽이 없어서 봉투를 그 안에 가두는 것이
    # 없기 때문이다. 그래서 받는 상자는 벽이 아니라 **자리 간격**(0.18)이 정한다: 간격의 절반 안이면
    # 그 자리다. 낙하 산포 ±0.04 는 넉넉히 통과하고, 0.20 미끄러지면 떨어진다.
    # z 는 상판 칸과 같은 0.04 로 둔다 — 바뀐 것은 형상이지 높이가 아니다.
    "slot_accept": (0.18, 0.18, 0.04),
}


def tray_boxes(base_top_z, spec=None, color=None, plate_color=None):
    """상판 다섯 칸 대신 얹는 **통짜 트레이** 하나. 반환 (boxes, slot_frames).

    `base_top_z` 는 `base_link` 로컬에서 몸체 윗면 높이다. 트레이는 그 위에 바로 앉는다.
    `slot_frames[i]` 는 `deck_slot_{i+1}` 의 원점 = **바닥 윗면의 놓을 자리 중심**이다(결정 23 그대로).

    칸막이가 없어져 상판 자기 충돌 쌍이 사라진다 — lap3 에서 위팔이 3번 칸 벽에 sep 0.010 로 막혔던
    그 형상이다. 대신 봉투가 트레이 안에서 미끄러질 수 있고, 그것은 돌려 봐야 안다.
    """
    spec = spec or TRAY
    color = color or COLORS["loading"]
    plate_color = plate_color or COLORS["carriage"]
    cx, (ix, iy) = spec["centre_x"], spec["inner"]
    wall, floor, lip = spec["wall"], spec["floor"], spec["lip"]
    ox, oy = ix + 2 * wall, iy + 2 * wall
    floor_top = base_top_z + floor
    wall_cz = floor_top + lip / 2.0
    boxes = [Box("TrayFloor", (cx, 0.0, base_top_z + floor / 2.0), (ox, oy, floor), plate_color, "fixed")]
    for name, dx, dy, sx, sy in (("WallXMinus", -(ix + wall) / 2.0, 0.0, wall, oy),
                                 ("WallXPlus", (ix + wall) / 2.0, 0.0, wall, oy),
                                 ("WallYMinus", 0.0, -(iy + wall) / 2.0, ox, wall),
                                 ("WallYPlus", 0.0, (iy + wall) / 2.0, ox, wall)):
        boxes.append(Box(f"Tray{name}", (cx + dx, dy, wall_cz), (sx, sy, lip), color, "fixed"))
    frames = [(float(sx), float(sy), floor_top) for sx, sy in spec["slots"]]
    return boxes, frames


def tray_inner_bounds(base_top_z, spec=None):
    """트레이 **안쪽** 부피 ((x0, x1), (y0, y1), (z0, z1)), `base_link` 로컬.

    `truth_sensors.in_slot` 이 "트레이 안 + 제일 가까운 자리" 로 판정할 때의 그 안이다.
    위는 턱 높이까지만 본다 — 팔이 봉투를 들고 트레이 **위를** 지날 때를 담으면 안 된다.
    """
    spec = spec or TRAY
    cx, (ix, iy) = spec["centre_x"], spec["inner"]
    floor_top = base_top_z + spec["floor"]
    return ((cx - ix / 2.0, cx + ix / 2.0), (-iy / 2.0, iy / 2.0), (floor_top, floor_top + spec["lip"]))


def plan_suction_pick_place(pick_xyz, pouch_height, place_center, slot_size, slot_wall, clearance, ready_xyz,
                            rest_gap=0.005):
    """UR5 with a suction tool: take the pouch lying at pick_xyz (its centre) and drop it into a deck slot.

    Steps are (phase, kind, tcp_xyz, suction 'on'|'off'); the TCP is the suction face, so it touches the pouch top."""
    top = pick_xyz[2] + pouch_height / 2.0
    slot_top = place_center[2] + slot_size[2] / 2.0
    slot_floor = place_center[2] - slot_size[2] / 2.0 + slot_wall
    carry_z = max(top, slot_top + pouch_height) + clearance
    touch = (pick_xyz[0], pick_xyz[1], top)
    above_pick = (pick_xyz[0], pick_xyz[1], carry_z)
    above_slot = (place_center[0], place_center[1], carry_z)
    place = (place_center[0], place_center[1], slot_floor + rest_gap + pouch_height)
    return [
        ("above_pouch", "tcp", above_pick, "off"),
        ("touch", "tcp", touch, "off"),
        ("suck", "hold", touch, "on"),
        ("lift", "tcp", above_pick, "on"),
        ("above_slot", "tcp", above_slot, "on"),
        ("lower", "tcp", place, "on"),
        ("drop", "hold", place, "off"),
        ("retreat", "tcp", above_slot, "off"),
        ("ready", "tcp", tuple(ready_xyz), "off"),
    ]


def default_layout():
    """Numbers for the default pharmacy room. All are overridable through pharmacy_stage.py arguments."""
    return {
        # Reach (M0609 about 0.9 m, TCP 0.197 below link_6 from the class example): base on a 0.6 m pedestal, rail
        # origin 0.2 m toward the shelf, top row surface at 0.8 m. Not verified in Isaac.
        # 9/17 d38a2c2: with the origin at y 0.2 and ±0.3 the base stopped 0.43 m short of the shelf cell centre and
        # the arm could not reach above it. Origin y 0.30 and upper 0.33 let the base park 0.3 m from the cell.
        # 9/17 7ae2879: with lower -0.33 the carriage was pushed to y -0.25 and stuck there, so lower is -0.10 (the
        # inlet park point is -0.05).
        "rail_origin": (0.0, 0.30, 0.0), "rail_x_stroke": 2.4, "rail_y_limits": (-0.10, 0.33), "rail_base_height": 0.05,
        "carriage_height": 0.6,
        "shelf_origin": (-1.3, 0.75, 0.0), "shelf_cols": 5, "shelf_rows": 3, "shelf_cell": (0.30, 0.25),
        "shelf_depth": 0.32, "shelf_plinth": 0.30, "canister_size": (0.06, 0.06, 0.12), "pick_cell": (2, 4),
        # The base parks 0.15 m to the side and 0.30 m in front of each target so no TCP point sits right above the
        # base axis (the pull-out point in front of the shelf would otherwise be 0.02 m from it).
        # Shelf side: on 9/17 (4c07d8f, 7ae2879, 3b114c4) the first rail_to_shelf always stopped with the base at
        # world y 0.48 (rail_y 0.28 with origin 0.2, 0.18 with origin 0.3) and every shelf phase still reached within
        # 0.0007 m from there. Parking there on purpose: y standoff 0.43. The inlets keep the d38a2c2 standoff, base
        # 0.40 m straight in front (3b114c4: insert 0.0030 m, canister_in_inlet).
        # 재범 실습3 (9/18 7cd4b90): at above_inlet/insert link_4/link_5 hit the dispenser face (impulse up to 540 at
        # y 0.69-0.70) and above_inlet stopped 3 cm short with joint_3 at 0.115 rad (arm stretched). The inlets now
        # stand inlet_gap 0.07 m out from the face and the base parks 0.33 m in front of them (rail_y unchanged -0.05).
        "reach_offset": (0.15, 0.43), "inlet_offset": (0.0, 0.33), "inlet_gap": 0.07, "clearance": 0.06,
        "grip_depth": 0.05,
        "dispenser_origin": (1.0, 1.0, 0.0), "dispenser_size": (0.7, 0.6, 1.6), "inlet_size": (0.10, 0.10, 0.12),
        "inlet_height": 0.85, "inlet_wall": 0.01, "outlet_height": 0.75, "outlet_size": (0.08, 0.20, 0.12),
        "belt_length": 1.6, "belt_width": 0.25, "belt_top": 0.75,
        # Loading spot in the corridor (scenario 1: outside the door, at the belt end). Contract robot is Ridgeback_UR5;
        # here a UR5 on a fixed pedestal stands in for the docked AMR arm, with its deck slots next to it.
        "ur5_base": (3.25, 0.55, 0.45), "deck_center": (3.30, 0.05, 0.45), "deck_count": 5,
        "deck_slot_size": (0.14, 0.11, 0.04), "deck_wall": 0.008, "ur5_ready": (3.05, 0.55, 1.00),
        "wall_x": 2.7, "wall_y_range": (-1.5, 1.6), "wall_height": 2.4, "wall_thickness": 0.10,
        "door_y": -0.6, "door_width": 0.9,
        # 벨트가 벽을 지나는 창의 윗변 = 벨트 윗면 + 이 값. 0.20 → 0.40(9/23): 빈월드 동시 보충 회차 L3 에서
        # 가장 먼 스폰(along 0.145, rel_yaw 0.25)을 집을 때 UR5 wrist_2 가 윗벽 모서리(z 0.951)를
        # 스쳤다(#240 5788985212).
        "belt_opening_above": 0.40,
    }


# --- 전 구간 한 바퀴(빈월드) --------------------------------------------------
# K1 (작전 9/21, 재범 "구현부터"): 조제실 밖으로 복도·병상·보관함·도크를 상자로 얹는다. 치수는 전부 임시값이고
# 출처는 "임시"다 — 세준 USD 가 오면 값만 바꾼다. zone 이름은 계약 3절·zones.yaml 의 규칙 그대로 쓴다.
CORRIDOR = {
    # 조제실 벽은 x 2.7 이고 적재 구역(UR5·상판)이 x 3.0-3.7 이다. 복도는 그 동쪽으로 뻗는다.
    "origin_x": 4.10,      # 적재 구역 동쪽 끝에서 복도가 시작한다
    "length": 6.00,        # +x 로 곧게. 빈월드라 곡선을 넣지 않는다(작전: 직선이면 된다)
    # 벽 안쪽 치수. AMR 회전 외접 반경(계획 footprint 기준 0.711) + 추종 여유 + 안전 여유를 양쪽에 둔다.
    # 2.00 → 2.80. 2.00 은 내가 지어낸 "폭 0.60" 위에 서 있던 값이라 실측으로 바꾸니 모자랐다(9/21).
    "width": 2.80,
    "wall_thickness": 0.10,
    "wall_height": 2.40,
    "centre_y": 0.55,      # UR5 받침대와 같은 y 라 적재 구역에서 복도로 곧게 나간다
}

WARD = {
    # 복도 **끝 너머**의 병실(벽이 끝난 뒤라 접근을 막는 것이 없다). 침대·보관함·표식을 자리마다 둔다.
    "bed_size": (1.10, 0.90, 0.55),      # 침대 상판까지. 칸 간격 1.20 안에 들어가야 겹치지 않는다
    # 첫 자리. 복도 중심선(y 0.55)보다 북쪽이고 접근은 통로에서 한다. x 는 복도 끝(10.10)에서 충분히 떨어져야
    # 한다 — 복도를 빠져나와 통로로 내려서는 자리가 필요하다(11.60 이면 여유가 0.50 m 라 AMR 이 못 지난다).
    "bed_centre": (13.60, 1.05, 0.275),
    # **AMR 합본 기준으로 다시 잡았다**(9/21). 받침대 UR5 는 z 0.90 이었지만 합본 팔은 AMR 위 0.28 이라
    # 어깨가 0.399 다. 수평 예산은 `sqrt(reach² − dz²)` 라 **보관함을 낮추는 것이 베이스를 옮기는 것보다
    # 훨씬 크게 번다**(주행 9/21): z 0.80 이면 dz 0.401 로 예산 0.577 인데, 몸체 반폭 0.397 +
    # 보관함 반폭 + 틈 0.10 을 대면 **틈 0 으로도 모자랐다.**
    "cabinet_size": (0.36, 0.36, 0.70),
    "cabinet_offset": (-0.80, -0.75),    # 침대 중심에서 (dx, dy). 머리맡 남쪽
    "tag_size": (0.02, 0.20, 0.20),      # 병상 표식(QR 텍스처 자리). 얇은 판
    "tag_offset": (-0.80, -0.75, 0.95),  # 보관함 위
    # 보관함 중심에서 AMR 중심까지(−y). 최소는 몸체 반폭 0.397 + 보관함 반폭 0.18 + 틈 0.10 = 0.677.
    # **0.69 는 거리가 아니라 자세로 고른 값이다**(비전 9/21): 보관함을 낮출수록 거리는 편해지지만
    # 팔이 수평으로 뻗어 팔꿈치가 펴진다(실습3 에서 뻗은 채 3 cm 못 미친 그 영역).
    # 윗면 0.70 · 수평 0.68 에서 `sin|q3|` 0.931 로 제일 좋고, 0.50 · 0.70 은 0.382 로 통과선(0.35)에 붙는다.
    "approach_gap": 0.69,
    # 주문 풀의 destination 이 넷이라 zone 도 넷이어야 한다(통합&정비 K0-b: 없는 zone 은 fleet 에서만 거부된다).
    # v0 은 상자 모형을 하나만 두고 자리만 나눈다. 넷을 +x 로만 늘어놓으면 마지막 접근 자리가 AMR 이동 한계를
    # 넘으므로(amr_base.DEFAULT_LIMITS x 최대 14.0), **통로를 사이에 두고 양옆 두 줄**로 놓는다.
    #   (zone 이름, x 칸, 줄) — 줄 +1 은 통로 북쪽, −1 은 남쪽이고 접근 yaw 가 반대다.
    # (zone 이름, x 칸, 줄). **정차 yaw 는 전부 0 이다** — 회전하면 모서리가 중심에서 0.612 m 까지 나가는데
    # 보관함 면까지가 0.52 라 **닿는다**(주행 9/21). 회전을 허용하려면 간격이 0.892 는 되어야 하고 그러면
    # 도달이 110 % 로 밖이다. **기하가 yaw 0 을 강제한다** — 전방향 베이스라 옆으로 밀어 넣는다.
    # 그래서 yaw 로 두 줄을 가를 수 없고, 대신 **x 를 반 칸 어긋나게** 해 넷이 전부 다른 자리에 선다.
    # (zone 이름, x 칸, 줄). **정차 yaw 는 전부 0 이다** — 회전하면 모서리가 중심에서 0.612 m 까지 나가는데
    # 보관함 면까지가 0.52 라 **닿는다**(주행 9/21). 회전을 허용하려면 간격이 0.892 는 되어야 하고 그러면
    # 도달이 110 % 로 밖이다. **기하가 yaw 0 을 강제한다** — 전방향 베이스라 옆으로 밀어 넣는다.
    #
    # 그래서 yaw 로 두 줄을 가를 수 없고, **한 줄로 늘어놓는다.** 마주 보는 두 줄로 두면 통로 폭이
    # 1.40 뿐이라 **달리는 내내 보관함에서 0.12 m** 다 — 주행이 "0.10 로 2.4 m 를 나란히 달린다" 로
    # 경고한 자리다. 한 줄이면 이동 차선을 남쪽으로 따로 뺄 수 있다.
    "beds": (("bed_a1", 0), ("bed_a2", 1), ("bed_b1", 2), ("bed_b2", 3)),
    "bed_pitch": 1.20,                   # x 칸 간격. 정차 자리 넷이 들어가야 한다(AMR 길이 0.93)
    # 실제로 상자를 두는 자리 수. 작전 9/21 은 하나여도 된다고 했지만 **넷을 다 둔다** —
    # 여유 시험은 **있는 상자만** 본다. 모형이 없는 자리는 통로가 비어 있는 것처럼 계산되어 시험이 낙관적으로
    # 통과한다(조제실 상자를 빼고 계산하던 것과 같은 종류의 사각이다). 넷을 다 둬도 최소 여유는 그대로였다.
    "model_beds": 4,
    # 정차선에서 남쪽으로 이 만큼 떨어진 곳이 **이동 차선**이다. 침상을 오갈 때는 여기로 다닌다 —
    # 정차선으로 달리면 보관함에서 0.12 m 로 나란히 달리게 된다(주행 9/21 ②).
    # 보관함 면(y 0.12)에서 주행 여유(0.936) 밖이어야 한다.
    # 0.50 → 0.54 (9/21 오후). 주행이 추종 여유를 0.065 → 0.17 로 올려(80 % 속도 지시) 요구 여유가
    # 0.936 → 1.041 이 됐고, 0.50 이면 보관함 면까지 1.010 으로 **모자란다.**
    "travel_offset": 0.54,
}

DOCK = {"centre": (4.60, 0.55), "size": (0.90, 0.70, 0.01), "count": 1}

#: zone 도착 공차(m, rad). **0 이면 fleet 가 arrived 를 영원히 안 낸다**(주행 9/21). 빈월드 임시값이고 실측 아님.
ZONE_TOL = {"tol_xy": 0.15, "tol_yaw": 0.20}


def corridor_boxes(spec=None, colors=None):
    """복도 바닥 표식과 양쪽 벽. 바닥은 visual, 벽은 fixed. 반환 (boxes, centre_line)."""
    spec = spec or CORRIDOR
    colors = colors or COLORS
    x0, length, half = spec["origin_x"], spec["length"], spec["width"] / 2.0
    cy, t, h = spec["centre_y"], spec["wall_thickness"], spec["wall_height"]
    cx = x0 + length / 2.0
    boxes = [Box("CorridorFloor", (cx, cy, 0.005), (length, spec["width"], 0.01), colors["loading"], "visual")]
    for side, dy in (("North", half + t / 2.0), ("South", -half - t / 2.0)):
        boxes.append(Box(f"CorridorWall{side}", (cx, cy + dy, h / 2.0), (length, t, h), colors["wall"], "fixed"))
    return boxes, ((x0, cy), (x0 + length, cy))


def bed_zones(spec=None):
    """침상 zone 이름들. `WARD["beds"]` 의 **모양이 바뀌어도 부르는 쪽이 안 깨지게** 한 겹 둔다 —
    9/21 에 줄 배치를 바꾸면서 튜플 길이가 달라져 여섯 군데가 한꺼번에 깨졌다."""
    return [entry[0] for entry in (spec or WARD)["beds"]]


def ward_boxes(spec=None, colors=None):
    """병실: 자리마다 접근·보관함·표식 프레임을 두고 상자는 `model_beds` 개만 둔다.

    반환 (boxes, frames). frames 는 {zone 이름: {"bed"|"cabinet"|"tag": 자세}} 다. 주문 풀의 destination 이
    넷이라 zone 도 넷이어야 한다 — 없는 zone 은 웹·orchestrator 를 통과하고 fleet 에서만 거부된다(통합&정비).
    v0 은 상자를 하나만 두고 나머지 자리는 프레임만 둔다(작전 9/21: 상자 모형은 공유해도 좋다).
    """
    spec = spec or WARD
    colors = colors or COLORS
    bx, by, bz = spec["bed_centre"]
    bsx, bsy, bsz = spec["bed_size"]
    csx, csy, csz = spec["cabinet_size"]
    cdx, cdy = spec["cabinet_offset"]
    tdx, tdy, tz = spec["tag_offset"]
    # 통로 중심선: 첫 줄의 접근 자리가 놓이는 y. 반대쪽 줄은 이 선을 기준으로 거울이다.
    aisle_y = by + cdy - spec["approach_gap"]
    boxes, frames = [], {}
    for index, (zone, column) in enumerate(spec["beds"]):
        ox = bx + column * spec["bed_pitch"]
        oy = by
        cabinet_xy = (ox + cdx, by + cdy)
        tag = (ox + tdx, by + tdy, tz)
        if index < spec["model_beds"]:
            suffix = "" if index == 0 else f"_{zone}"
            boxes += [
                Box(f"BedFrame{suffix}", (ox, oy, bz), (bsx, bsy, bsz), colors["shelf"], "fixed"),
                Box(f"BedCabinet{suffix}", (cabinet_xy[0], cabinet_xy[1], csz / 2.0), (csx, csy, csz),
                    colors["dispenser"], "fixed"),
                Box(f"BedTag{suffix}", tag, spec["tag_size"], colors["inlet_a"], "visual"),
            ]
        # 접근 자리는 보관함 앞(통로 쪽). AMR 이 서는 곳이라 상자를 두지 않는다. yaw 는 침대를 바라본다.
        # 정차 x 는 보관함 x 에서 `ARM_MOUNT_SHIFT_X` 만큼 앞(+x)이다 — 팔이 몸체 뒤끝(−x)에 달려 있어서
        # 그만큼 밀어야 **팔 밑동이 보관함 바로 앞**에 온다. 안 밀면 밑동 기준 수평이 0.69 → 0.774 로
        # 늘어 보관함 윗면 도달이 예산 밖으로 나간다(비전 표의 0.68 은 밑동 기준 값이다).
        frames[zone] = {"bed": (cabinet_xy[0] + ARM_MOUNT_SHIFT_X, aisle_y, 0.0, 0.0),
                        "cabinet": (cabinet_xy[0], cabinet_xy[1], csz, 0.0),
                        "tag": tag + (0.0,)}
    return boxes, frames


def dock_boxes(spec=None, colors=None):
    """대기 도크 바닥 표식. 반환 (boxes, frames)."""
    spec = spec or DOCK
    colors = colors or COLORS
    dx, dy = spec["centre"]
    sx, sy, sz = spec["size"]
    boxes, frames = [], {}
    for i in range(spec["count"]):
        x = dx + i * (sx + 0.30)
        boxes.append(Box(f"Dock{i + 1}", (x, dy, sz / 2.0), (sx, sy, sz), colors["loading"], "visual"))
        frames[f"dock_{i + 1}"] = (x, dy, 0.0, 0.0)
    return boxes, frames


#: 빈월드 벨트 끝의 월드 xy. 스테이지의 `belt_end_xy()`(1.35 + belt_length, belt_start y)와 같은 자리다.
BELT_END_XY = (2.95, 1.00)


def pharmacy_frames(belt_end_xy=None):
    """계약 3절 `pharmacy/*` 고정 프레임 중 빈월드가 가진 것 {이름: (x, y, z, yaw)}. 값은 전부 임시다.

    지금은 `belt_end` 하나다: 벨트 윗면(봉투가 놓이는 면), 벨트 중심선의 끝점, x = 벨트 진행 방향(+x), z = 위.
    팔이 손 카메라로 벨트 끝을 내려다보는 관측 자세(`belt_view_frame`)가 이 프레임을 쓴다.
    """
    x, y = belt_end_xy or BELT_END_XY
    return {"belt_end": (x, y, default_layout()["belt_top"], 0.0)}


def full_loop_zones(corridor=None, ward=None, dock=None, belt_end_xy=None):
    """계약 3절 이름 규칙의 zone 자세 {이름: (x, y, z, yaw)}. 장면 매개변수가 단일 출처다.

    `load` 는 벨트 끝 적재 자리, `bed_a1` 은 병상 접근 자리, `dock_N` 은 대기 자리다. 값은 전부 임시다.
    공차는 zones_yaml 이 ZONE_TOL 에서 붙인다 — 0 이면 도착 판정이 성립하지 않는다(주행 9/21).
    """
    _wboxes, wframes = ward_boxes(ward)
    _dboxes, dframes = dock_boxes(dock)
    belt_end_xy = belt_end_xy or BELT_END_XY
    zones = {"load": (belt_end_xy[0] + LOAD_OFFSET[0], belt_end_xy[1] + LOAD_OFFSET[1], 0.0, 0.0)}
    zones.update(dframes)
    for zone, poses in wframes.items():
        zones[zone] = poses["bed"]
        zones[f"{zone}/cabinet"] = poses["cabinet"]
        zones[f"{zone}/tag"] = poses["tag"]
    return zones


def _round(value, places=4):
    """파일로 나갈 값은 자릿수를 자른다 — 부동소수 잡음이 diff 를 더럽힌다."""
    return round(float(value), places) + 0.0


def zones_yaml(zones=None, tol=None, frame="map", pharmacy=None):
    """zones.yaml 과 같은 모양의 사전. 월드별 파일(zones.emptyworld.yaml)로 쓴다.

    값의 단일 출처는 full_loop_zones 다. 기본 zones.yaml 은 건드리지 않는다(심월드 자리).
    """
    zones = zones or full_loop_zones()
    tol = tol or ZONE_TOL
    kinds = {"load": "load", "dock": "dock", "bed": "bed", "station": "station", "ward": "ward"}
    out = {}
    for name, pose in zones.items():
        if "/" in name:
            continue
        head = name.split("_", 1)[0]
        entry = {"kind": kinds.get(head, head), "x": _round(pose[0]), "y": _round(pose[1]), "yaw": _round(pose[3]),
                 "tol_xy": tol["tol_xy"], "tol_yaw": tol["tol_yaw"]}
        for extra in ("cabinet", "tag"):
            key = f"{name}/{extra}"
            if key in zones:
                x, y, z, yaw = zones[key]
                entry[extra] = {"x": _round(x), "y": _round(y), "z": _round(z), "yaw": _round(yaw)}
        out[name] = entry
    fixed = {name: {"x": _round(x), "y": _round(y), "z": _round(z), "yaw": _round(yaw)}
             for name, (x, y, z, yaw) in (pharmacy or pharmacy_frames()).items()}
    return {"frame": frame, "zones": out, "pharmacy": fixed}


#: zones.emptyworld.yaml 맨 위 주석. 본문과 같이 생성해야 손으로 붙인 헤더가 재생성에서 날아가지 않는다.
ZONES_HEADER = (
    "# 빈월드(K1, 전 구간 한 바퀴)의 구역과 고정 프레임. 계약 v1 3절의 형식이다.",
    "#",
    "# **이 파일은 자동 생성물이다. 손으로 고치지 않는다.**",
    "#   단일 출처는 sim/standalone/p3sim/layout.py 의 full_loop_zones·ZONE_TOL 이고,",
    "#   sim/tests/test_full_loop_layout.py 가 파일과 코드가 어긋나면 잡는다.",
    "#   다시 만들기: python3 sim/standalone/pharmacy_layout_json.py --zones emptyworld",
    "#",
    "# **값은 전부 임시다(출처 \"임시\"). 아무것도 재지 않았다.**",
    "#   빈월드는 구현을 먼저 돌리려고 만든 장면이다(재범 9/21 \"구현부터\").",
    "#   세준님 USD 가 오면 심월드는 config/zones.yaml 쪽에서 따로 채운다 — 이 파일과 섞지 않는다.",
    "#",
    "# 침상 넷은 주문 풀의 목적지와 같아야 한다(통합&정비: 없는 zone 은 fleet 에서만 거부된다).",
    "# 공차는 양수여야 한다. 0 이면 fleet 가 arrived 를 영원히 내지 않는다(주행 9/21).",
    "# 고르는 법: launch 인자나 P3_ZONES 로 이 파일의 절대 경로를 준다.",
    "#   기본값은 config/zones.yaml 이라 기본 동작은 그대로다.",
    "",
)


def zones_yaml_text(doc=None):
    """zones_yaml 을 YAML 본문으로. **PyYAML 을 쓰지 않는다.**

    L1 의 sim 잡에는 usd-core 만 깔려 있어 PyYAML 이 없다(#401 CI, 2026-09-21). 저장된 파일이 코드와 같은지
    보려면 시험이 본문을 다시 만들 수 있어야 하므로 여기서 직접 찍는다. 값은 수·문자열뿐이라 따옴표가 필요 없다.
    """
    doc = doc or zones_yaml()
    lines = [*ZONES_HEADER, f"frame: {doc['frame']}", "zones:"]
    for name, entry in doc["zones"].items():
        lines.append(f"  {name}:")
        for key, value in entry.items():
            if isinstance(value, dict):
                lines.append(f"    {key}:")
                lines += [f"      {k}: {v}" for k, v in value.items()]
            else:
                lines.append(f"    {key}: {value}")
    lines.append("pharmacy:")
    for name, pose in doc["pharmacy"].items():
        lines.append(f"  {name}:")
        lines += [f"    {k}: {v}" for k, v in pose.items()]
    return "\n".join(lines) + "\n"


#: 몸체 실측 치수 (길이 x, 폭 y, m). `ridgeback_ur5.usd` 의 `base_link` 외형 bbox
#: (박세준 PR #408 6.5절, 2026-09-21). **장면에 놓는 상자가 이 치수다.**
AMR_BBOX = (0.93251, 0.79320)
#: 여유 계산에 쓰는 **계획 footprint** (길이 x, 폭 y, m). 실측 bbox 보다 크다.
#: 태규님 test_amr 에서 실제로 주행이 돌던 Nav2 costmap footprint 이고 주행이 #383 에 반영했다.
#: bbox 와 다른 이유는 확인하지 못했다(가설: 센서·범퍼·여유 포함, 또는 base_link 밖으로 나온 링크).
#: **큰 쪽으로 잡는다**(주행 9/21) — 심월드에서 Nav2 로 갈아 끼우면 Nav2 가 이 footprint 로 장애물을
#: 피하므로, 작은 쪽에 장면을 맞추면 그때 통로가 모자란다.
#: K2b 로 UR5 를 얹으면 또 커진다 — 두 값 다 **팔이 없는 상태**다.
AMR_FOOTPRINT = (1.10, 0.90)
#: v0 추종기가 경로 선분에서 벗어나는 양(m). 주행 9/21: 모서리 자르기(waypoint_tolerance 0.05)
#: + 한 주기 이동량(max_linear 0.3 / 20 Hz) = 0.05 + 0.015. **v0 추종기 기준**이고 Isaac 미실행이다.
#: 심월드에서 Nav2 로 갈아 끼우면 다시 재야 한다(Nav2 는 costmap·inflation 으로 다른 여유를 쓴다).
#:
#: 9/21 오후 **0.065 → 0.17** (주행, PR #453 `400f706e`). 80 % 속도 지시로 가속 상한이 생겨 꺾일 때
#: 바깥으로 더 나간다: 공차 0.05 + `v^2/2a` 0.10 + 한 주기 0.02. 여유 요구가 0.936 → 1.041 로 오른다.
FOLLOWER_ALLOWANCE = 0.17
#: 팔이 몸체 **뒤끝**(−x)으로 옮겨 간 만큼(m), 모든 정차 자리를 +x 로 민다.
#:
#: 9/21 재범 확정안: 팔은 상판 한쪽 끝 + 낮은 받침, 반대쪽 끝은 통짜 트레이. **어느 끝인지는 기하가
#: 정한다** — 적재 자리에서 벨트는 AMR 로컬 −x 쪽(−0.60)이다. 팔을 +x 끝에 달면 봉투까지 0.95 로
#: 사거리(0.85) 밖이고, −x 끝에 달면 0.25 로 너무 가깝다. 그래서 **팔은 −x 끝이고, 정차 자리를
#: 그만큼 앞으로 민다.** 그러면 팔 밑동의 월드 자리가 옮기기 전과 **같아져** 도달·자세 계산이 전부
#: 그대로 유지된다(비전 검증 9/21: 벨트 sin|q3| 0.967→0.999, 보관함 0.912→0.988 로 오히려 좋아진다).
#:
#: `amr_base.ARM_MOUNT_LOCAL[0]` 의 **부호 반대 값**이어야 한다 — 시험이 둘을 묶는다.
ARM_MOUNT_SHIFT_X = 0.35

#: 적재 자리가 벨트 끝에서 떨어지는 (dx, dy). **AMR 합본 기준으로 다시 잡았다**(작전 승인 9/21).
#:
#: 받침대 UR5 는 조제실 옆 z 0.90 에 서 있었고, 합본 팔은 AMR 위 z 0.28 이다 — **팔이 62 cm 내려왔다.**
#: 그래서 옛 자리 (4.00, 0.55)에서는 벨트 끝 봉투까지 1.24 m 라 **도달 밖**이었다(회차 lap2).
#: 봉투 정착 자리 (2.806, 0.993, 0.755), 어깨 z 0.369 → dz 0.386, 2R 편 길이 0.817 에서 쓸 수 있는
#: 수평은 0.720 뿐이다. 자리 (3.40, 0.95)에서 3D 0.710 = **편 길이의 87 %** 다
#: (실습12m: 96.3 % 는 오차가 2–3배, 85.8 % 는 0.1 mm 대 — 87 % 는 그 좋은 구간에 가깝다).
#:
#: 9/21 재범 확정안에서 팔이 몸체 뒤끝으로 가면서 **`ARM_MOUNT_SHIFT_X` 가 붙었다.** 그 값은
#: 팔 밑동의 **월드 자리를 그대로 두려는** 보정이라, 위 87 % 계산은 손대지 않아도 그대로 성립한다.
LOAD_OFFSET = (0.45 + ARM_MOUNT_SHIFT_X, -0.05)
#: **접안 자리**의 몸체↔고정물 최소 틈(m). 주행 도착 오차 0.02 + 여유(작전 9/21).
#: 받침대 셀의 `SERVICE_CLEARANCE`(0.15)와 **다른 값이고 다른 이유**다 — 저쪽은 팔이 기둥에 걸리는 문제이고
#: 이쪽은 AMR 몸체가 고정물에 닿는 문제다. 한 값으로 묶으면 둘 중 하나의 근거가 사라진다.
DOCK_CLEARANCE = 0.10
#: 접안 규칙이 적용되는 구역과, 그 자리 둘레로 주행 여유 대신 접안 여유를 보는 반경(m).
#: 적재 자리는 벨트 끝에 **붙어야** 팔이 닿으므로 주행 여유(0.936)를 요구할 수 없다.
SERVICE_POSES = ("load",)
SERVICE_RADIUS = 1.0
#: 몸체 높이(m). 실측 bbox 의 z(박세준 #408). 이보다 **위에만** 있는 장애물은 xy 여유 규칙에서 빠진다 —
#: AMR 이 그 밑으로 지나간다. 대신 머리 위 여유(HEADROOM)로 본다.
AMR_BODY_HEIGHT = 0.32717
#: 장애물 아랫면과 몸체 윗면 사이에 남겨야 할 높이(m). 임시값이다.
HEADROOM = 0.05
#: **가까이 서야 하는 자리**의 최소 틈(m). 적재 자리가 그렇다 — UR5 가 봉투를 놓으려면 팔 길이 안에
#: 들어와야 하므로 주행 여유(0.936)를 요구할 수 없다. 받침대가 곧 UR5 의 자리라 둘은 동시에 만족되지 않는다.
#: 그래서 **그 자리에만** 적용하는 별도 규칙을 둔다. 예외를 두는 것이 아니라 다른 규칙을 적는 것이다.
SERVICE_CLEARANCE = 0.15
#: 그 위에 더 두는 안전 여유(m). 심월드 문 개구 1.2232 에 footprint 0.90 을 넣어 좌우 0.16 인 것을 따랐다
#: (박세준 #408). 빈월드가 심월드보다 빡빡할 이유가 없다.
SAFETY_MARGIN = 0.16


def amr_turn_radius(footprint=None):
    """제자리 회전까지 덮는 외접 반경(m). 침상 접근 자리는 같은 자리에서 yaw 만 ±pi/2 로 돈다.

    그래서 통로 여유는 **폭의 절반이 아니라 이 값**으로 봐야 한다 — 반폭으로 보면 회전에서 벽을 친다.
    """
    length, width = footprint or AMR_FOOTPRINT
    return (length * length + width * width) ** 0.5 / 2.0


def amr_required_clearance(footprint=None):
    """경로 선분이 고정 상자에서 떨어져 있어야 할 거리(m). 회전 외접 반경 + 추종 여유 + 안전 여유."""
    return amr_turn_radius(footprint) + FOLLOWER_ALLOWANCE + SAFETY_MARGIN


def corridor_exit_x(corridor=None, ward=None):
    """복도를 빠져나와 통로로 내려서는 자리의 x. 복도 끝과 병실 첫 상자의 **한가운데**다.

    `load ↔ bed_*` 가 복도 남쪽 벽을 피해 도는 유일한 길이고, 병실을 옮기면 같이 움직여야 한다.
    """
    corridor = corridor or CORRIDOR
    boxes, _frames = ward_boxes(ward)
    end_x = corridor["origin_x"] + corridor["length"]
    first_x = min(box.center[0] - box.size[0] / 2.0 for box in boxes)
    return (end_x + first_x) / 2.0


def amr_aabb(pose, footprint=None, height=None):
    """AMR 몸체가 차지하는 상자 ((x0, x1), (y0, y1), (z0, z1)). yaw 는 **무시한다** — 축 정렬 근사다.

    yaw 가 0 이나 ±pi/2 가 아니면 실제보다 작게 잡힌다. 지금 자리는 전부 그 둘 중 하나이고, 회전 중의
    형상은 `amr_turn_radius` 쪽에서 본다.
    """
    length, width = footprint or AMR_BBOX
    height = AMR_BODY_HEIGHT if height is None else height
    from . import amr_base as amrlib

    x, y = float(pose[0]), float(pose[1])
    bottom = amrlib.GROUND_CLEARANCE  # 몸체는 지면에서 떠 있다
    return ((x - length / 2.0, x + length / 2.0), (y - width / 2.0, y + width / 2.0), (bottom, bottom + height))


def box_gap(aabb, box):
    """상자와 AMR 상자 사이의 축별 틈 (dx, dy, dz). 겹치면 0 이다. 하나라도 양수면 안 닿는다."""
    gaps = []
    for axis, (low, high) in enumerate(aabb):
        b0 = box.center[axis] - box.size[axis] / 2.0
        b1 = box.center[axis] + box.size[axis] / 2.0
        gaps.append(max(b0 - high, low - b1, 0.0))
    return tuple(gaps)


def routes(zones=None, ward=None, exit_x=None):
    """(from, to) -> [(x, y)] 경유점. 주행 routes.py 스키마(#407)의 값이다.

    규칙(주행 9/21): 좌표는 map 기준 [x, y] 뿐이고 yaw 는 없다(목표 yaw 는 zones 에서 온다).
    **방향이 다르면 다른 쌍**이라 왕복은 두 줄이고 순서를 뒤집는다. 빈 목록이면 곧장 간다 —
    그 줄을 빼도 같지만 **빼지 않는다**. 빼면 "직선으로 가도 된다고 판정했다" 와 "안 따져 봤다" 가 구별되지 않는다.
    """
    zones = zones or full_loop_zones()
    ward = ward or WARD
    exit_x = corridor_exit_x(ward=ward) if exit_x is None else exit_x
    beds = [name for name, _column in ward["beds"]]
    aisle_y = zones[beds[0]][1]
    lane_y = aisle_y - ward["travel_offset"]   # 이동 차선. 정차선으로 달리면 보관함에 붙어 달린다
    # 복도는 **중심선으로 달린다.** 적재 자리의 y(0.95)로 달리면 북쪽 벽까지 딱 1.000 인데 요구 여유가
    # 1.041 이라 모자란다(주행이 추종 여유를 0.17 로 올린 뒤). 중심선이면 양쪽 1.400 이다.
    corridor_y = CORRIDOR["centre_y"]
    # **21 쌍이 아니라 30 쌍이다.** 빠진 쌍은 주행 로더에서 "빈 목록(따져 봤다)" 과 구별되지 않고
    # 그냥 직선이 된다(주행 9/21). 한 바퀴 정상 흐름에 안 쓰이는 쌍도 **리셋 직후 첫 목표**나
    # 연속 배송에서 쓰인다 — `dock_1 -> bed_*` 는 복도를 무시하고 병동까지 대각선이라 고정물을 지난다.
    pairs = {("dock_1", "load"): [], ("load", "dock_1"): []}   # 0.94 m 직선. 둘 다 접안 반경 안이다
    for bed in beds:
        bed_x = zones[bed][0]
        # 복도 → 차선 → 침상 앞. **마지막은 차선에서 정차점으로 곧장 들어가는 직선 하나**다
        # (주행 9/21: 꺾이는 자리를 틈 안에 두지 않는다).
        # 첫 경유점은 **복도에 들어가기 전에** 중심선으로 내려서는 자리다. 복도 안에서 비스듬히
        # 내려가면 입구 근처가 아직 북쪽에 치우쳐 있어 벽까지 1.019 밖에 안 남는다.
        pairs[("load", bed)] = [(zones["load"][0], corridor_y), (exit_x, corridor_y),
                                (exit_x, lane_y), (bed_x, lane_y)]
        # 돌아오는 길의 끝은 dock_1 이고 그것이 이미 중심선 위에 있어 따로 내려설 자리가 없다.
        pairs[(bed, "dock_1")] = [(bed_x, lane_y), (exit_x, lane_y), (exit_x, corridor_y)]
        # 도크에서 곧장 침상으로. 리셋 직후 첫 목표가 침상이면 이것이 쓰인다.
        pairs[("dock_1", bed)] = [(exit_x, corridor_y), (exit_x, lane_y), (bed_x, lane_y)]
        # 침상에서 곧장 적재로(연속 배송). 끝에 **적재 자리로 올라서는 자리**가 붙는다 — 나가는 길에
        # 내려섰던 그 자리의 거울이다.
        pairs[(bed, "load")] = [(bed_x, lane_y), (exit_x, lane_y), (exit_x, corridor_y),
                                (zones["load"][0], corridor_y)]
    # 침상끼리도 **차선으로 빠졌다가** 간다. 정차선으로 곧장 가면 보관함 줄과 나란히 달린다.
    for name in beds:
        for other in beds:
            if name != other:
                pairs[(name, other)] = [(zones[name][0], lane_y), (zones[other][0], lane_y)]
    return pairs


def route_clearance(pair_waypoints, start, goal, boxes, skip_near=()):
    """경로 선분과 고정 상자 사이의 최소 거리(m). AMR 반폭을 빼지 않은 값이다.

    정지 기하다 — 추종 오차도 위치 추정 오차도 들어 있지 않다(주행 9/21). 실제 이격은 L3 에서 잰다.

    `skip_near` 는 [(xy, 반경)] 이고, 그 안의 표본은 건너뛴다 — **접안 구간**이다. 적재 자리는 벨트 끝에
    붙어야 팔이 닿으므로 주행 여유를 요구할 수 없다. 뺀 구간은 `dock_clearance_at` 이 따로 본다.
    """
    points = [tuple(start), *[tuple(p) for p in pair_waypoints], tuple(goal)]
    worst = float("inf")
    for first, second in zip(points, points[1:], strict=False):
        for box in boxes:
            if box.kind != "fixed":
                continue
            worst = min(worst, _segment_box_distance(first, second, box, skip_near=skip_near))
    return worst


def _segment_box_distance(first, second, box, samples=200, skip_near=()):
    """선분 위를 표본으로 훑어 상자(AABB, xy)까지의 최단 거리. 표본이라 실제보다 크게 나올 수 있다."""
    x0, x1 = box.center[0] - box.size[0] / 2.0, box.center[0] + box.size[0] / 2.0
    y0, y1 = box.center[1] - box.size[1] / 2.0, box.center[1] + box.size[1] / 2.0
    worst = float("inf")
    for index in range(samples + 1):
        t = index / samples
        x = first[0] + (second[0] - first[0]) * t
        y = first[1] + (second[1] - first[1]) * t
        if any(((x - cx) ** 2 + (y - cy) ** 2) ** 0.5 <= radius for (cx, cy), radius in skip_near):
            continue
        dx = max(x0 - x, x - x1, 0.0)
        dy = max(y0 - y, y - y1, 0.0)
        worst = min(worst, (dx * dx + dy * dy) ** 0.5)
    return worst


ROUTES_HEADER = (
    "# 빈월드(K1)의 경로 경유점. 주행 routes.py 스키마(#407)다.",
    "#",
    "# **이 파일은 자동 생성물이다. 손으로 고치지 않는다.**",
    "#   단일 출처는 sim/standalone/p3sim/layout.py 의 routes 이고,",
    "#   sim/tests/test_full_loop_routes.py 가 파일과 코드가 어긋나면 잡는다.",
    "#   다시 만들기: python3 sim/standalone/pharmacy_layout_json.py --routes emptyworld",
    "#",
    "# `waypoints: []` 는 \"직선으로 가도 된다고 따져 봤다\" 는 뜻이다. 줄을 빼면 \"안 따져 봤다\" 와",
    "#   구별되지 않으므로 빈 쌍도 적는다(작전 9/21).",
    "# 여유는 정지 기하로만 계산했다 — 추종 오차도 위치 추정 오차도 빠져 있다. 실제 이격은 L3 에서 잰다.",
    "",
)


def routes_yaml_text(pairs=None, frame="map"):
    """routes.<world>.yaml 본문. PyYAML 을 쓰지 않는다(L1 의 sim 잡에 없다)."""
    pairs = routes() if pairs is None else pairs
    lines = [*ROUTES_HEADER, "schema_version: 1", f"frame: {frame}", "routes:"]
    for (source, target), waypoints in pairs.items():
        points = ", ".join(f"[{_round(x)}, {_round(y)}]" for x, y in waypoints)
        lines.append(f"  - {{from: {source}, to: {target}, waypoints: [{points}]}}")
    return "\n".join(lines) + "\n"
