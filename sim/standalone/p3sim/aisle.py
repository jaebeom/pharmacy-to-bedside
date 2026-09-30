"""Arm aisle box over the belt end (contract 11.6 arm_clear_of_belt: "상자 치수는 simulation 제공"). No Isaac.

The box is axis-aligned in the belt frame of p3sim/belt.py (origin = belt top surface at the start, x along the
belt, y lateral, z up), the lane frame rokey_p3_manipulation.belt_lane_clearance.LaneConfig takes as [lower, upper]:

    along   : [L - end_zone - m_along,  L + m_end]
    lateral : [-(W/2 + m_side),  +(W/2 + m_side)]
    up      : [0,  h_clear]

There are no default margins: the four margins are decision 20 (재범). Any margin left None gives no box, only the
names of the missing margins, so an unset aisle can never read as CLEAR. Not wired into the stage.
"""

import math
from collections import namedtuple

MARGINS = ("m_along", "m_end", "m_side", "h_clear")

AisleBox = namedtuple("AisleBox", ("frame", "lower", "upper", "problem"))


def _finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def belt_aisle_box(length, width, end_zone, m_along, m_end, m_side, h_clear):
    """AisleBox in frame "belt". lower/upper are (along, lateral, up) tuples, or None with `problem` set."""
    geometry = {"length": length, "width": width, "end_zone": end_zone}
    bad = [name for name, value in geometry.items() if not (_finite(value) and value > 0)]
    if bad or not end_zone <= length:
        return AisleBox("belt", None, None, f"belt geometry invalid: {bad or ['end_zone > length']}")
    margins = {"m_along": m_along, "m_end": m_end, "m_side": m_side, "h_clear": h_clear}
    unset = [name for name in MARGINS if margins[name] is None]
    if unset:
        return AisleBox("belt", None, None, f"margins unset (decision 20): {unset}")
    invalid = [name for name in MARGINS if not (_finite(margins[name]) and margins[name] >= 0)]
    if invalid or not h_clear > 0:
        return AisleBox("belt", None, None, f"margins must be finite, >= 0 and h_clear > 0: {invalid or ['h_clear']}")
    half = width / 2.0 + m_side
    lower = (length - end_zone - m_along, -half, 0.0)
    upper = (length + m_end, half, float(h_clear))
    return AisleBox("belt", lower, upper, "")


def world_from_belt(start_xyz, yaw):
    """4x4 (nested lists) of the belt frame in the world: the inverse of belt.belt_frame. A caller builds
    base_from_lane = inverse(world_from_arm_base) @ world_from_belt."""
    c, s = math.cos(yaw), math.sin(yaw)
    x, y, z = start_xyz
    return [[c, -s, 0.0, x], [s, c, 0.0, y], [0.0, 0.0, 1.0, z], [0.0, 0.0, 0.0, 1.0]]
