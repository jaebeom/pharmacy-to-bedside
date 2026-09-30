"""M0609 명목 기구학. ROS 도 Isaac 도 import 하지 않는다.

`ROKEY_P2_B2` 의 `ros2/rokey_p2_task/rokey_p2_task/motion/smooth_trajectory.py`
(`56d8246`) 에서 기구학 부분만 옮겼다. P2 에서는 실행 경로가 아니었다 — 두산
컨트롤러가 `movel` 안에서 IK 를 풀었고 이 코드는 옆에서 검산만 했다. P3 에는
그 컨트롤러가 없고 `/m0609/arm/joint_command` 에 관절값을 직접 실어야 하므로
여기가 이 코드의 자리다.

**이 모듈은 아직 아무 노드도 쓰지 않는다.** `m0609_arm` 은 여전히 티칭한 관절
waypoint 를 재생한다([refill_sequence.py](refill_sequence.py)). 배선은 2축 레일을
계약에 넣을지 정한 뒤다. 레일이 들어오면 팔 베이스가 움직이고 목표 TCP·베이스·
레일 프레임을 먼저 정의해야 한다.

**기본값은 전부 명목값이고 마스터에서 확인해야 한다.**

- `_ORIGINS` (링크 원점·rpy) — doosan-robot2 `macro.m0609.blue.xacro`.
  Isaac 자산은 `m0609_isaac_sim.urdf` 다. 같은지 **미확인**.
- `URDF_LIMITS_RAD` — 같은 xacro. `m0609_arm` 의 `joint_limits_low/high` 와
  값은 같다(J3 +-2.618, 나머지 +-2pi).
- `ToolTransform` — **P2 는 GripperDA_v1 이었고 P3 는 onrobot RG2FT 다.**
  반드시 다시 재야 한다. 기본값을 두지 않는 이유다.

`UR5` 쪽 같은 역할은 [ur5_kinematics.py](ur5_kinematics.py) 다. 그쪽은 DH 표를
쓰고 여기는 링크 원점 체인을 쓴다 — 자산이 준 형식이 달라서다.
"""
from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

Vec3 = tuple[float, float, float]
Quat = tuple[float, float, float, float]  # ROS xyzw
Joints = tuple[float, ...]
MODEL_REF = "DoosanRobotics/doosan-robot2@816ecb5d1c2599303eaf9540216afa03552f80ad:m0609.blue"


class PlanError(ValueError):
    """Input, geometry or sampled kinematics is unsuitable; do not execute."""


def finite(values: Sequence[float], size: int) -> tuple[float, ...]:
    if len(values) != size:
        raise PlanError(f"expected {size} values")
    result = tuple(float(v) for v in values)
    if not all(math.isfinite(v) for v in result):
        raise PlanError("non-finite value")
    return result


def dot(a, b) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))


def add(a, b) -> tuple[float, ...]:
    return tuple(x + y for x, y in zip(a, b, strict=True))


def scale(a, k: float) -> tuple[float, ...]:
    return tuple(x * k for x in a)


def sub(a, b) -> tuple[float, ...]:
    return add(a, scale(b, -1))


def cross(a, b) -> Vec3:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def unit(values: Sequence[float], size: int) -> tuple[float, ...]:
    values = finite(values, size)
    length = math.hypot(*values)
    if not math.isfinite(length) or length < 1e-12:
        raise PlanError("zero or unnormalizable vector/quaternion")
    return scale(values, 1 / length)


def quat_mul(a: Quat, b: Quat) -> Quat:
    av, bv = a[:3], b[:3]
    return (
        *add(add(scale(bv, a[3]), scale(av, b[3])), cross(av, bv)),
        a[3] * b[3] - dot(av, bv),
    )


def conjugate(q: Quat) -> Quat:
    return (-q[0], -q[1], -q[2], q[3])


def rotate(q: Quat, v: Vec3) -> Vec3:
    q = unit(q, 4)
    return add(
        v,
        add(scale(cross(q[:3], v), 2 * q[3]), scale(cross(q[:3], cross(q[:3], v)), 2)),
    )


def axis_angle(axis: Vec3, angle: float) -> Quat:
    finite((angle,), 1)
    return (*scale(unit(axis, 3), math.sin(angle / 2)), math.cos(angle / 2))


def rotation_error(target: Quat, current: Quat) -> Vec3:
    q = unit(quat_mul(unit(target, 4), conjugate(unit(current, 4))), 4)
    if q[3] < -1e-12 or (abs(q[3]) <= 1e-12 and next((v for v in q[:3] if abs(v) > 1e-12), 1) < 0):
        q = scale(q, -1)
    sn = math.hypot(*q[:3])
    return scale(q[:3], 2 if sn < 1e-12 else 2 * math.atan2(sn, q[3]) / sn)


@dataclass(frozen=True)
class Pose:
    """BASE active-TCP pose. Tool +Z points INTO the grasp; +X closes the jaws.

    The position is already the final TCP reference, not a visible top surface,
    flange position or object centroid. Apply measured tool/pad geometry once,
    before constructing this pose. No implicit pad offset is applied here.
    """

    position_m: Vec3
    orientation_xyzw: Quat
    frame_id: str = "base_link"

    def __post_init__(self):
        object.__setattr__(self, "position_m", finite(self.position_m, 3))
        object.__setattr__(self, "orientation_xyzw", unit(self.orientation_xyzw, 4))
        if not self.frame_id:
            raise PlanError("pose needs the base frame it is expressed in")


_ORIGINS = (
    ((0.0, 0.0, 0.1345), (0.0, 0.0, 0.0)),
    ((0.0, 0.0062, 0.0), (0.0, -1.571, -1.571)),
    ((0.411, 0.0, 0.0), (0.0, 0.0, 1.571)),
    ((0.0, -0.368, 0.0), (1.571, 0.0, 0.0)),
    ((0.0, 0.0, 0.0), (-1.571, 0.0, 0.0)),
    ((0.0, -0.121, 0.0), (1.571, 0.0, 0.0)),
)
URDF_LIMITS_RAD = tuple(
    (-bound, bound) for bound in (6.2832, 6.2832, 2.618, 6.2832, 6.2832, 6.2832)
)
URDF_VELOCITY_RAD_S = (2.618, 2.618, 3.1416, 3.927, 3.927, 3.927)


def _rpy_quat(rpy) -> Quat:
    r, p, y = rpy
    return quat_mul(
        quat_mul(axis_angle((0, 0, 1), y), axis_angle((0, 1, 0), p)),
        axis_angle((1, 0, 0), r),
    )


_ORIGIN_QUATS = tuple(_rpy_quat(rpy) for _, rpy in _ORIGINS)


def solve_linear(matrix, vector) -> tuple[float, ...]:
    """Small pivoted dense solve; singular/NaN is a refusal, never zero motion."""
    n = len(vector)
    rows = [
        list(finite(row, n)) + [value] for row, value in zip(matrix, finite(vector, n), strict=True)
    ]
    for col in range(n):
        pivot = max(range(col, n), key=lambda i: abs(rows[i][col]))
        if abs(rows[pivot][col]) < 1e-12:
            raise PlanError("singular linear system")
        rows[col], rows[pivot] = rows[pivot], rows[col]
        rows[col] = [v / rows[col][col] for v in rows[col]]
        for i in range(n):
            if i != col:
                factor = rows[i][col]
                rows[i] = [a - factor * b for a, b in zip(rows[i], rows[col], strict=True)]
    return finite(tuple(row[-1] for row in rows), n)


@dataclass(frozen=True)
class ToolTransform:
    """Rigid link6/flange→active-TCP transform expressed in the FLANGE frame."""

    position_m: Vec3
    orientation_xyzw: Quat

    def __post_init__(self):
        object.__setattr__(self, "position_m", finite(self.position_m, 3))
        object.__setattr__(self, "orientation_xyzw", unit(self.orientation_xyzw, 4))


@dataclass(frozen=True)
class M0609:
    """Nominal blue-URDF kinematics with EXPLICIT flange→active-TCP transform.

    Additional bounds are intersected with the published URDF; they cannot
    silently broaden it. No controller calibration is inferred from this class.
    """

    flange_to_tcp: ToolTransform
    joint_limits_rad: tuple[tuple[float, float], ...] = URDF_LIMITS_RAD

    def __post_init__(self):
        if not isinstance(self.flange_to_tcp, ToolTransform):
            raise PlanError("explicit ToolTransform required")
        if len(self.joint_limits_rad) != 6:
            raise PlanError("six joint limits required")
        limits = []
        for supplied, published in zip(self.joint_limits_rad, URDF_LIMITS_RAD, strict=True):
            lo, hi = finite(supplied, 2)
            lo, hi = max(lo, published[0]), min(hi, published[1])
            if lo >= hi:
                raise PlanError("empty joint-limit intersection")
            limits.append((lo, hi))
        object.__setattr__(self, "joint_limits_rad", tuple(limits))

    def check_limits(self, joints: Joints, margin_rad: float = math.radians(1)) -> Joints:
        joints = finite(joints, 6)
        for i, (q, (lo, hi)) in enumerate(zip(joints, self.joint_limits_rad, strict=True), 1):
            if not lo + margin_rad <= q <= hi - margin_rad:
                raise PlanError(f"J{i} joint limit / margin")
        return joints

    def chain(self, joints: Joints):
        joints = finite(joints, 6)
        p, q = (0.0, 0.0, 0.0), (0.0, 0.0, 0.0, 1.0)
        origins, axes = [], []
        for theta, (translation, _), fixed in zip(joints, _ORIGINS, _ORIGIN_QUATS, strict=True):
            p = add(p, rotate(q, translation))
            q = unit(quat_mul(q, fixed), 4)
            origins.append(p)
            axes.append(rotate(q, (0.0, 0.0, 1.0)))
            q = unit(quat_mul(q, axis_angle((0.0, 0.0, 1.0), theta)), 4)
        p = add(p, rotate(q, self.flange_to_tcp.position_m))
        q = quat_mul(q, self.flange_to_tcp.orientation_xyzw)
        return Pose(p, q), origins, axes

    def fk(self, joints: Joints) -> Pose:
        return self.chain(joints)[0]

    def jacobian(self, joints: Joints) -> tuple[tuple[float, ...], ...]:
        tcp, origins, axes = self.chain(joints)
        columns = [
            (*cross(z, sub(tcp.position_m, o)), *z) for o, z in zip(origins, axes, strict=True)
        ]
        return tuple(zip(*columns, strict=True))

    def inverse(self, target: Pose, seed: Joints) -> Joints:
        """Bounded damped Newton solve; one local branch, no random retry/jump.

        Damping regularizes the solve only. A returned solution is **not**
        a permission to move. P2 가 그 검증을 `validate_plan()` 에서 했는데
        그 함수는 카테시안 궤적 쪽이라 아직 안 옮겼다. 그때까지는 호출부가
        `check_joint_segment()` 로 가지 점프와 J5 특이점 통과를,
        `jacobian_metrics()` 로 손목 여유를 직접 봐야 한다.
        """
        q = self.check_limits(seed)
        for _ in range(100):
            pose = self.fk(q)
            error = (
                *sub(target.position_m, pose.position_m),
                *rotation_error(target.orientation_xyzw, pose.orientation_xyzw),
            )
            if math.hypot(*error[:3]) <= 0.00002 and math.hypot(*error[3:]) <= 0.00005:
                return self.check_limits(q)
            j = self.jacobian(q)
            # Scale translation by a 0.5 m characteristic length.
            j = [scale(row, 2 if i < 3 else 1) for i, row in enumerate(j)]
            e = tuple(v * (2 if i < 3 else 1) for i, v in enumerate(error))
            columns = tuple(zip(*j, strict=True))
            normal = [
                [dot(a, b) + (1e-6 if i == k else 0) for k, b in enumerate(columns)]
                for i, a in enumerate(columns)
            ]
            dq = solve_linear(normal, tuple(dot(col, e) for col in columns))
            step = min(1.0, math.radians(5) / max(1e-12, max(abs(v) for v in dq)))
            accepted = False
            for _ in range(12):
                candidate = add(q, scale(dq, step))
                try:
                    self.check_limits(candidate)
                except PlanError:
                    step *= 0.5
                    continue
                p = self.fk(candidate)
                new_error = (
                    *scale(sub(target.position_m, p.position_m), 2),
                    *rotation_error(target.orientation_xyzw, p.orientation_xyzw),
                )
                if math.hypot(*new_error) < math.hypot(*e):
                    q, accepted = candidate, True
                    break
                step *= 0.5
            if not accepted:
                break
        raise PlanError("IK did not converge on the seeded joint branch")


def wrist_clearance_rad(j5: float) -> float:
    return abs(math.remainder(j5, math.pi))


def check_joint_segment(start: Joints, end: Joints) -> None:
    start, end = finite(start, 6), finite(end, 6)
    if max(abs(v) for v in sub(end, start)) > math.radians(10):
        raise PlanError("IK branch jump / insufficient joint sampling")
    lo, hi = sorted((start[4], end[4]))
    # No crossing ANY k*pi, including +/-180 and +/-360. This is a branch
    # screen, not a claim about an unobserved controller interpolation curve.
    if math.ceil(lo / math.pi) <= math.floor(hi / math.pi):
        raise PlanError("J5 singular crossing between valid endpoints")


def jacobian_metrics(model: M0609, joints: Joints) -> tuple[float, float]:
    _, _, axes = model.chain(joints)
    det_w = dot(axes[3], cross(axes[4], axes[5]))
    j = model.jacobian(joints)
    normalized = [scale(row, 2 if i < 3 else 1) for i, row in enumerate(j)]
    try:
        inverse_columns = [
            solve_linear(normalized, tuple(float(k == i) for k in range(6))) for i in range(6)
        ]
    except PlanError:
        return det_w, 0.0
    # 1/||J_n^-1||_F <= sigma_min(J_n), hence a conservative lower bound.
    return det_w, 1 / math.hypot(*(v for col in inverse_columns for v in col))
