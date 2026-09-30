"""Speed limits and trapezoidal motion profiles for the rail and the M0609. No Isaac imports.

재범 실습1 (9/18): "too slow → 80% of the possible top speed". Top joint speeds are the M0609 USD maxVelocity values
(practice-1 log demo18_stage.log lines 485-490), which equal Doosan's M0609 spec (150/150/180/225/225/225 deg/s).
The rail has no real counterpart (USD maxVelocity unlimited); 1.0 m/s is our proposal for a 2.4 m gantry stroke.
Accelerations have no spec source: they are our choice, kept low so the held canister does not swing.
"""

import math

JOINT_MAX_SPEED = (2.618, 2.618, 3.142, 3.927, 3.927, 3.927)  # rad/s, joint_1..joint_6 (USD = Doosan spec)
TCP_MAX_SPEED = 1.0  # m/s, Doosan M0609 TCP spec
RAIL_MAX_SPEED = 1.0  # m/s, our proposal (no real rail)
SPEED_SHARE = 0.9  # 재범 9/24 20:4x: the M0609 at 90% of its spec top speed (was 80% since 9/18)
RAIL_SPEED_SHARE = 0.8  # the rail stays at 80%: it has no spec (재범 9/24 kept it)
# From the Doosan spec in degrees, so 180 deg/s gives 2.827 (not 3.142 * 0.9 = 2.828), the same value as the arm node.
JOINT_SPEC_DEG_S = (150.0, 150.0, 180.0, 225.0, 225.0, 225.0)
JOINT_SPEED = tuple(round(math.radians(d) * SPEED_SHARE, 3) for d in JOINT_SPEC_DEG_S)
TCP_SPEED = round(TCP_MAX_SPEED * SPEED_SHARE, 3)
RAIL_SPEED = RAIL_MAX_SPEED * RAIL_SPEED_SHARE
TCP_ACCEL = 1.0  # m/s^2, our choice
RAIL_ACCEL = 1.0  # m/s^2, our choice
JOINT_ACCEL = (4.0, 4.0, 4.0, 6.0, 6.0, 6.0)  # rad/s^2, our choice (sent to the arm session on 9/18)


def trapezoid_duration(distance, vmax, amax):
    """Seconds to cover distance from rest to rest with speed vmax and acceleration amax (triangle if short)."""
    if distance <= 0:
        return 0.0
    ramp = vmax / amax
    if distance < vmax * ramp:  # never reaches vmax
        return 2.0 * math.sqrt(distance / amax)
    return distance / vmax + ramp


def trapezoid_fraction(t, distance, vmax, amax):
    """Fraction (0..1) of the distance covered at time t on the rest-to-rest profile."""
    if distance <= 0:
        return 1.0
    total = trapezoid_duration(distance, vmax, amax)
    if t >= total:
        return 1.0
    if t <= 0:
        return 0.0
    peak = min(vmax, math.sqrt(distance * amax))  # triangle profile peaks below vmax
    ramp = peak / amax
    if t < ramp:
        covered = 0.5 * amax * t * t
    elif t <= total - ramp:
        covered = 0.5 * amax * ramp * ramp + peak * (t - ramp)
    else:
        left = total - t
        covered = distance - 0.5 * amax * left * left
    return min(1.0, max(0.0, covered / distance))


def clamp_step(previous, target, max_delta):
    """Move each joint from previous toward target by at most max_delta (per-joint speed limit per update)."""
    return tuple(p + max(-d, min(d, t - p)) for p, t, d in zip(previous, target, max_delta, strict=True))
