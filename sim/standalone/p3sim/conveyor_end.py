"""Measured terminal-surface checks for the opt-in belt probe, not production events."""
import math


def item_bounds(position, orientation, size):
    """World AABB of an oriented cuboid; quaternion is Isaac's w, x, y, z."""
    norm = math.sqrt(sum(q*q for q in orientation))
    if norm < 1e-12:
        raise ValueError('invalid pouch orientation')
    w, x, y, z = (q/norm for q in orientation)
    rotation = ((1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w)),
                (2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w)),
                (2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y)))
    half = [sum(abs(rotation[i][j])*size[j]/2 for j in range(3)) for i in range(3)]
    return ([float(p-h) for p, h in zip(position, half, strict=True)],
            [float(p+h) for p, h in zip(position, half, strict=True)])


def terminal_status(position, orientation, size, surface, direction, edge_margin, height_tolerance):
    """Require the entire item over the last roller, with its leading edge near the exit.

    Axis-aligned horizontal surfaces only. A radial target cannot substitute for
    longitudinal progress. Tolerances are explicit trial inputs, not contract gates.
    """
    if direction not in ('+x', '-x', '+y', '-y'):
        raise ValueError('terminal direction must be an axis-aligned horizontal direction')
    if not all(math.isfinite(v) and v > 0 for v in (edge_margin, height_tolerance)):
        raise ValueError('terminal tolerances must be positive and finite')
    lo, hi = item_bounds(position, orientation, size)
    axis = 0 if direction[1] == 'x' else 1
    gap = surface['max'][axis]-hi[axis] if direction[0] == '+' else lo[axis]-surface['min'][axis]
    supported_xy = all(surface['min'][i] <= lo[i] and hi[i] <= surface['max'][i] for i in (0, 1))
    bottom_gap = lo[2]-surface['max'][2]
    reached = supported_xy and 0 <= gap <= edge_margin and abs(bottom_gap) <= height_tolerance
    return {'reached': reached, 'supported_xy': supported_xy, 'edge_gap_m': gap,
            'bottom_gap_m': bottom_gap, 'item_min': lo, 'item_max': hi}


def receiver_status(position, orientation, size, surface, height_tolerance):
    """The whole pouch must reach and lie flat on the receiving table, beyond the chute."""
    lo, hi = item_bounds(position, orientation, size)
    supported = all(surface['min'][i] <= lo[i] and hi[i] <= surface['max'][i] for i in (0, 1))
    bottom_gap = lo[2]-surface['max'][2]
    flat = hi[2]-lo[2] <= size[2]+height_tolerance
    return {'reached': supported and flat and abs(bottom_gap) <= height_tolerance,
            'supported_xy': supported, 'flat': flat, 'bottom_gap_m': bottom_gap,
            'item_min': lo, 'item_max': hi}
