"""Axis-aligned boxes and unit quaternions (w, x, y, z). No Isaac imports."""

import math


def aabb(center, size):
    low = tuple(c - s / 2.0 for c, s in zip(center, size, strict=True))
    high = tuple(c + s / 2.0 for c, s in zip(center, size, strict=True))
    return low, high


def aabbs_overlap(first, second, margin=0.0):
    (low_a, high_a), (low_b, high_b) = first, second
    return all(low_a[i] < high_b[i] - margin and low_b[i] < high_a[i] - margin for i in range(3))


def point_in_aabb(point, box):
    low, high = box
    return all(low[i] <= point[i] <= high[i] for i in range(3))


def quat_multiply(a, b):
    w1, x1, y1, z1 = a
    w2, x2, y2, z2 = b
    return (w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2, w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
            w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2, w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2)


def quat_conjugate(q):
    return (q[0], -q[1], -q[2], -q[3])


def quat_rotate(q, v):
    rotated = quat_multiply(quat_multiply(q, (0.0, *v)), quat_conjugate(q))
    return rotated[1:]


def quat_from_matrix(m):
    """(w, x, y, z) unit quaternion from a 3x3 rotation matrix given as rows."""
    trace = m[0][0] + m[1][1] + m[2][2]
    if trace > 0.0:
        s = 0.5 / math.sqrt(trace + 1.0)
        return (0.25 / s, (m[2][1] - m[1][2]) * s, (m[0][2] - m[2][0]) * s, (m[1][0] - m[0][1]) * s)
    i = max(range(3), key=lambda k: m[k][k])
    j, k = (i + 1) % 3, (i + 2) % 3
    s = math.sqrt(m[i][i] - m[j][j] - m[k][k] + 1.0) * 2.0
    q = [0.0, 0.0, 0.0, 0.0]
    q[i + 1] = 0.25 * s
    q[0] = (m[k][j] - m[j][k]) / s
    q[j + 1] = (m[j][i] + m[i][j]) / s
    q[k + 1] = (m[k][i] + m[i][k]) / s
    return tuple(q)


def quat_from_z_to(v):
    """(w, x, y, z) rotating +z onto the direction of v (identity for a zero vector)."""
    n = math.sqrt(sum(c * c for c in v))
    if n == 0.0:
        return (1.0, 0.0, 0.0, 0.0)
    x, y, z = (c / n for c in v)
    if z < -0.999999:  # opposite: 180 deg about x
        return (0.0, 1.0, 0.0, 0.0)
    w = math.sqrt((1.0 + z) / 2.0)
    return (w, -y / (2.0 * w), x / (2.0 * w), 0.0)


def yaw_quat(yaw):
    return (math.cos(yaw / 2.0), 0.0, 0.0, math.sin(yaw / 2.0))


def relative_pose(parent_xyz, parent_quat, child_xyz, child_quat):
    """Child pose in the parent frame."""
    inverse = quat_conjugate(parent_quat)
    delta = tuple(c - p for c, p in zip(child_xyz, parent_xyz, strict=True))
    return quat_rotate(inverse, delta), quat_multiply(inverse, child_quat)


def tcp_world(link_xyz, link_quat, tcp_offset):
    return tuple(p + r for p, r in zip(link_xyz, quat_rotate(link_quat, tcp_offset), strict=True))


def lerp(start, goal, alpha):
    alpha = min(1.0, max(0.0, alpha))
    return tuple(s + alpha * (g - s) for s, g in zip(start, goal, strict=True))
