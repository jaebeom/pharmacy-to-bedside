"""UR5 정기구학과 수치 역기구학. ROS 를 import 하지 않는다.

- DH 는 Universal Robots 가 공개한 UR5 표준 DH 표(classic DH)다.
  시뮬 자산(USD)의 링크 길이·조인트 이름·관절 한계가 이 표와 다를 수 있다.
  **마스터에서 확인**한다. 함수는 ``dh`` 와 ``limits`` 인자를 받지만 현재 ``arm_node`` 는
  ``limits`` 만 전달한다. DH 가 다르면 노드 연결도 바꿔야 한다.
- 홈 자세는 이 모듈이 정하지 않는다. 노드 파라미터로 받아 인자로 넘긴다.
- 해석해를 쓰지 않는 이유: 자산의 DH 가 표준과 다를 수 있어서, DH 표만 바꾸면
  그대로 도는 수치해(감쇠 최소자승)를 쓴다. numpy 말고 새 의존성은 없다.
"""

import math
from collections import namedtuple

import numpy as np

# (d, a, alpha). theta 는 관절 변수다.
UR5_DH = (
    (0.089159, 0.0, math.pi / 2.0),
    (0.0, -0.425, 0.0),
    (0.0, -0.39225, 0.0),
    (0.10915, 0.0, math.pi / 2.0),
    (0.09465, 0.0, -math.pi / 2.0),
    (0.0823, 0.0, 0.0),
)

# UR5 제원의 관절 범위. 자산이 다르면 노드 파라미터로 덮는다.
UR5_JOINT_LIMITS = tuple((-2.0 * math.pi, 2.0 * math.pi) for _ in range(6))

# Isaac 자산(`Isaac/Robots/UniversalRobots/ur5/ur5.usd`, 그 `ur5.urdf`)의 관절 한계.
# **elbow 만 ±π 다.** 9/20 L3(실습12·12d) 의 `dof` 줄과 `ur5.urdf` 대조로 확인했다.
# 제원(위 표)보다 좁으므로, 제원만 믿고 푼 해는 자산에서 잘린다. 자르는 쪽은 PhysX 라 조용히 일어난다.
# 같은 일을 M0609 는 `m0609_kinematics.URDF_LIMITS_RAD` 로 이미 한다(그쪽은 J3 이 ±2.618).
# 다른 자산을 쓰면 노드 파라미터로 덮는다. 넓히는 방향으로는 덮이지 않는다(`intersect_limits`).
UR5_ASSET_LIMITS = tuple((-bound, bound) for bound in
                         (2.0 * math.pi, 2.0 * math.pi, math.pi,
                          2.0 * math.pi, 2.0 * math.pi, 2.0 * math.pi))

# 관절 이름 기본값. `/amr_1/joint_states` 는 USD 조인트 이름 그대로라서
# 실제 이름은 **마스터에서 확인**하고 노드 파라미터로 덮는다(계약 2.1절).
UR5_JOINT_NAMES = (
    'shoulder_pan_joint',
    'shoulder_lift_joint',
    'elbow_joint',
    'wrist_1_joint',
    'wrist_2_joint',
    'wrist_3_joint',
)

# 해 선택용 결정적 시드 오프셋. 난수를 쓰지 않아 같은 입력이면 같은 해가 나온다.
SEED_OFFSETS = (
    (0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
    (0.0, -0.6, 1.2, -0.6, 0.0, 0.0),
    (0.0, 0.6, -1.2, 0.6, 0.0, 0.0),
    (math.pi, -0.6, 1.2, -0.6, 0.0, 0.0),
    (math.pi / 2.0, -0.9, 1.5, -0.6, math.pi / 2.0, 0.0),
    (-math.pi / 2.0, 0.9, -1.5, 0.6, -math.pi / 2.0, 0.0),
    (math.pi, 0.9, -1.5, 0.6, math.pi, 0.0),
)

# 해 선택 가중치. 어깨 쪽이 크게 도는 해보다 손목 쪽이 도는 해를 고른다.
SELECTION_WEIGHTS = (1.0, 1.0, 1.0, 0.6, 0.4, 0.2)

TAU = 2.0 * math.pi

IkResult = namedtuple('IkResult', 'joints ok position_error rotation_error iterations')


def dh_transform(theta, d, a, alpha):
    """classic DH 한 줄의 4x4 변환."""
    ct, st = math.cos(theta), math.sin(theta)
    ca, sa = math.cos(alpha), math.sin(alpha)
    return np.array([
        [ct, -st * ca, st * sa, a * ct],
        [st, ct * ca, -ct * sa, a * st],
        [0.0, sa, ca, d],
        [0.0, 0.0, 0.0, 1.0],
    ])


def link_frames(joints, dh=UR5_DH):
    """베이스부터 각 링크까지의 누적 변환. [0] 은 단위행렬, [-1] 이 손끝이다."""
    frames = [np.eye(4)]
    for theta, (d, a, alpha) in zip(joints, dh, strict=True):
        frames.append(frames[-1] @ dh_transform(float(theta), d, a, alpha))
    return frames


def forward_kinematics(joints, dh=UR5_DH):
    """관절값 6개 → 손끝 4x4 자세(팔 베이스 프레임 기준)."""
    return link_frames(joints, dh)[-1]


def jacobian(joints, dh=UR5_DH):
    """기하 야코비안 6x6. 위 3줄이 선속도, 아래 3줄이 각속도."""
    frames = link_frames(joints, dh)
    end = frames[-1][:3, 3]
    columns = []
    for frame in frames[:-1]:
        axis = frame[:3, 2]
        columns.append(np.concatenate([np.cross(axis, end - frame[:3, 3]), axis]))
    return np.column_stack(columns)


def rotation_log(matrix):
    """회전행렬 → 축각 벡터(크기 = 각도, rad)."""
    cosine = (np.trace(matrix[:3, :3]) - 1.0) / 2.0
    angle = math.acos(min(1.0, max(-1.0, cosine)))
    if angle < 1e-9:
        return np.zeros(3)
    if angle > math.pi - 1e-6:
        # 180도 근처는 sin 이 0 이라 대각 성분으로 축을 뽑는다.
        axis = np.sqrt(np.maximum((np.diag(matrix[:3, :3]) + 1.0) / 2.0, 0.0))
        largest = int(np.argmax(axis))
        if axis[largest] < 1e-9:
            return np.zeros(3)
        signs = np.ones(3)
        off = matrix[:3, :3]
        for index in range(3):
            if index != largest:
                signs[index] = math.copysign(1.0, off[largest, index] + off[index, largest])
        return angle * axis * signs / np.linalg.norm(axis)
    axis = np.array([
        matrix[2, 1] - matrix[1, 2],
        matrix[0, 2] - matrix[2, 0],
        matrix[1, 0] - matrix[0, 1],
    ]) / (2.0 * math.sin(angle))
    return angle * axis


def pose_error(current, target):
    """현재 자세에서 목표 자세까지의 6벡터 오차 [위치 3, 회전 3]."""
    position = target[:3, 3] - current[:3, 3]
    rotation = rotation_log(target[:3, :3] @ current[:3, :3].T)
    return np.concatenate([position, rotation])


def intersect_limits(requested, asset=UR5_ASSET_LIMITS):
    """요청한 한계와 자산 한계의 교집합. **넓히지 않는다**(M0609 `joint_limits_rad` 와 같은 규칙).

    요청이 자산보다 넓으면 자산 쪽으로 좁힌다. 좁으면 그대로 둔다(운영상 더 좁게 쓰는 것은 막지 않는다).
    자산 한계를 모르는 관절은 요청을 그대로 쓴다(`asset` 에 None 을 넣는다).
    """
    limits = []
    for (low, high), bounds in zip(requested, asset, strict=True):
        if bounds is None:
            limits.append((float(low), float(high)))
            continue
        asset_low, asset_high = bounds
        limits.append((max(float(low), float(asset_low)), min(float(high), float(asset_high))))
    return tuple(limits)


def clamp_to_limits(joints, limits=UR5_JOINT_LIMITS):
    """관절 한계 안으로 자른다."""
    values = np.asarray(joints, dtype=float).copy()
    for index, (low, high) in enumerate(limits):
        values[index] = min(high, max(low, values[index]))
    return values


def within_limits(joints, limits=UR5_JOINT_LIMITS, tolerance=1e-6):
    """관절 한계 안인가."""
    return all(low - tolerance <= value <= high + tolerance
               for value, (low, high) in zip(joints, limits, strict=True))


def nearest_wrapped(joints, reference, limits=UR5_JOINT_LIMITS):
    """같은 자세를 뜻하는 2pi 배수 중 기준 자세에 가장 가까운 것."""
    values = np.asarray(joints, dtype=float).copy()
    for index, (low, high) in enumerate(limits):
        best = values[index]
        for turns in (-2, -1, 0, 1, 2):
            candidate = values[index] + turns * TAU
            if low <= candidate <= high and abs(candidate - reference[index]) < abs(best - reference[index]):
                best = candidate
        values[index] = best
    return values


def joint_distance(joints, reference, weights=SELECTION_WEIGHTS):
    """해 선택용 가중 관절 거리."""
    diff = np.asarray(joints, dtype=float) - np.asarray(reference, dtype=float)
    return float(np.sum(np.asarray(weights) * np.abs(diff)))


def solve_ik_from_seed(target, seed, dh=UR5_DH, limits=UR5_JOINT_LIMITS,
                       position_tolerance=1e-5, rotation_tolerance=1e-5,
                       max_iterations=200, damping=0.05, max_step=0.2):
    """시드 하나에서 감쇠 최소자승으로 푼다. 한 해만 본다."""
    joints = clamp_to_limits(seed, limits)
    identity = np.eye(6)
    error = pose_error(forward_kinematics(joints, dh), target)
    for iteration in range(1, max_iterations + 1):
        position_error = float(np.linalg.norm(error[:3]))
        rotation_error = float(np.linalg.norm(error[3:]))
        if position_error <= position_tolerance and rotation_error <= rotation_tolerance:
            return IkResult(joints, True, position_error, rotation_error, iteration - 1)
        matrix = jacobian(joints, dh)
        step = matrix.T @ np.linalg.solve(matrix @ matrix.T + (damping ** 2) * identity, error)
        largest = float(np.max(np.abs(step)))
        if largest > max_step:
            step *= max_step / largest
        joints = clamp_to_limits(joints + step, limits)
        error = pose_error(forward_kinematics(joints, dh), target)
    position_error = float(np.linalg.norm(error[:3]))
    rotation_error = float(np.linalg.norm(error[3:]))
    ok = position_error <= position_tolerance and rotation_error <= rotation_tolerance
    return IkResult(joints, ok, position_error, rotation_error, max_iterations)


def solve_ik(target, seed, home=None, dh=UR5_DH, limits=UR5_JOINT_LIMITS,
             position_tolerance=1e-5, rotation_tolerance=1e-5,
             max_iterations=200, damping=0.05, max_step=0.2,
             weights=SELECTION_WEIGHTS):
    """여러 시드로 풀고 하나를 고른다.

    해 선택 규칙 (순서대로):
    1. 관절 한계 안에 있는 해만 본다.
    2. 수렴한 해만 본다. 하나도 없으면 오차가 가장 작은 해를 ``ok=False`` 로 돌려준다.
    3. 2pi 를 더하고 빼서 현재 자세(``seed``)에 가장 가까운 형태로 바꾼다.
    4. ``seed`` 에서의 가중 관절 거리가 가장 작은 해. 같으면 시드 순서가 앞선 것.
    """
    reference = clamp_to_limits(seed, limits)
    seeds = [reference]
    for offset in SEED_OFFSETS:
        seeds.append(clamp_to_limits(reference + np.asarray(offset, dtype=float), limits))
    if home is not None:
        seeds.append(clamp_to_limits(home, limits))

    best_converged = None
    best_distance = None
    fallback = None
    for candidate in seeds:
        result = solve_ik_from_seed(target, candidate, dh, limits, position_tolerance,
                                    rotation_tolerance, max_iterations, damping, max_step)
        if fallback is None or result.position_error < fallback.position_error:
            fallback = result
        if not result.ok or not within_limits(result.joints, limits):
            continue
        joints = nearest_wrapped(result.joints, reference, limits)
        distance = joint_distance(joints, reference, weights)
        if best_distance is None or distance < best_distance - 1e-9:
            best_distance = distance
            best_converged = result._replace(joints=joints)
    if best_converged is not None:
        return best_converged
    return fallback._replace(ok=False)


def solve_suction_ik(target, seed, wrist, limits=UR5_JOINT_LIMITS):
    """TCP +Z 방향과 위치만 맞춘다. 마지막 관절은 고정하고 축 주위 각은 자유다.

    target 은 tool0 자세다. 흡착 TCP 오프셋이 tool +Z 축 위일 때만 사용할 수 있다.
    현재 해에서만 연속적으로 푼다. 실패하면 다른 팔 자세로 뛰지 않는다.
    """
    joints = clamp_to_limits(seed, limits)
    if not limits[-1][0] <= wrist <= limits[-1][1]:
        return IkResult(joints, False, math.inf, math.inf, 0)
    joints[-1] = wrist
    axis = target[:3, 2]
    projection = np.eye(3) - np.outer(axis, axis)
    for iteration in range(401):
        current = forward_kinematics(joints)
        position = target[:3, 3] - current[:3, 3]
        cross = np.cross(current[:3, 2], axis)
        angle = math.atan2(float(np.linalg.norm(cross)),
                           float(np.dot(current[:3, 2], axis)))
        pos_error = float(np.linalg.norm(position))
        if pos_error < 1e-5 and angle < 1e-5:
            return IkResult(joints, True, pos_error, angle, iteration)
        # 반대 축에서 영벡터를 수렴으로 오인하지 않는다.
        if np.linalg.norm(cross) < 1e-10 and angle > 1e-3:
            break
        rotation = cross * angle / max(float(np.linalg.norm(cross)), 1e-12)
        matrix = jacobian(joints)[:, :5].copy()
        matrix[3:] = projection @ matrix[3:]
        error = np.concatenate((position, rotation))
        step = matrix.T @ np.linalg.solve(matrix @ matrix.T + 0.0004 * np.eye(6), error)
        step *= min(1.0, 0.1 / max(float(np.max(np.abs(step))), 1e-12))
        joints[:5] += step
        joints = clamp_to_limits(joints, limits)
        joints[-1] = wrist
    return IkResult(joints, False, pos_error, angle, iteration)


def interpolate_joint_path(start, goal, max_step=0.05):
    """관절 공간 직선 경로. 한 점 사이의 최대 관절 변화가 ``max_step`` 이하가 되게 나눈다."""
    begin = np.asarray(start, dtype=float)
    end = np.asarray(goal, dtype=float)
    largest = float(np.max(np.abs(end - begin))) if begin.size else 0.0
    steps = max(1, int(math.ceil(largest / max_step))) if max_step > 0.0 else 1
    return [begin + (end - begin) * (index / steps) for index in range(1, steps + 1)]


def at_pose(joints, reference, tolerance):
    """모든 관절이 기준 자세에서 ``tolerance`` rad 이내인가. `arm/at_home` 판정."""
    if joints is None or reference is None or len(joints) != len(reference):
        return False
    return all(abs(float(value) - float(target)) <= tolerance
               for value, target in zip(joints, reference, strict=True))


# z 를 뒤집는 회전(x 축 180도). 위에서 내려다보기와 태그 마주보기에 같이 쓴다.
FLIP_Z = np.array([[1.0, 0.0, 0.0], [0.0, -1.0, 0.0], [0.0, 0.0, -1.0]])


def rotation_z(yaw):
    """z 축 회전 3x3."""
    cos, sin = math.cos(yaw), math.sin(yaw)
    return np.array([[cos, -sin, 0.0], [sin, cos, 0.0], [0.0, 0.0, 1.0]])


def top_down_pose(position, yaw):
    """위에서 내려다보는 손끝 자세. 공구 z 가 아래(-z)를 본다.

    상판 칸과 보관함은 위가 열려 있어 접근이 -z 방향이다(계약 3절).
    공구 프레임과 흡착면의 관계는 **마스터에서 확인**한다.
    """
    matrix = np.eye(4)
    matrix[:3, :3] = rotation_z(yaw) @ FLIP_Z
    matrix[:3, 3] = np.asarray(position, dtype=float)
    return matrix


def facing_pose(frame, standoff):
    """프레임의 +z 쪽 `standoff` m 떨어진 곳에서 그 프레임을 마주보는 자세.

    태그의 바깥 방향을 태그 프레임의 +z 로 본다. 실제 축은 zones.yaml 의 태그 배치와
    함께 **마스터에서 확인**한다. 손 카메라를 인식표에 대는 자세를 이걸로 만든다.
    """
    pose = np.eye(4)
    pose[:3, :3] = frame[:3, :3] @ FLIP_Z
    pose[:3, 3] = np.asarray(frame[:3, 3], dtype=float) + np.asarray(frame[:3, 2], dtype=float) * standoff
    return pose


def invert(matrix):
    """강체 변환 4x4 의 역변환."""
    rotation = matrix[:3, :3]
    inverse = np.eye(4)
    inverse[:3, :3] = rotation.T
    inverse[:3, 3] = -rotation.T @ matrix[:3, 3]
    return inverse


def translate(matrix, offset):
    """자세는 그대로 두고 부모 프레임 기준으로 평행이동한 사본."""
    moved = np.array(matrix, dtype=float, copy=True)
    moved[:3, 3] = moved[:3, 3] + np.asarray(offset, dtype=float)
    return moved


def matrix_from_quaternion(x, y, z, w, translation=(0.0, 0.0, 0.0)):
    """쿼터니언 + 위치 → 4x4. TF 와 geometry_msgs/Pose 를 행렬로 바꿀 때 쓴다."""
    norm = math.sqrt(x * x + y * y + z * z + w * w)
    if norm < 1e-12:
        raise ValueError('quaternion norm is zero')
    x, y, z, w = x / norm, y / norm, z / norm, w / norm
    matrix = np.eye(4)
    matrix[:3, :3] = np.array([
        [1.0 - 2.0 * (y * y + z * z), 2.0 * (x * y - z * w), 2.0 * (x * z + y * w)],
        [2.0 * (x * y + z * w), 1.0 - 2.0 * (x * x + z * z), 2.0 * (y * z - x * w)],
        [2.0 * (x * z - y * w), 2.0 * (y * z + x * w), 1.0 - 2.0 * (x * x + y * y)],
    ])
    matrix[:3, 3] = np.asarray(translation, dtype=float)
    return matrix


def yaw_of(matrix):
    """4x4 자세의 z 축 회전각(rad). 위에서 내려다보는 파지의 손목 각으로 쓴다."""
    return math.atan2(matrix[1, 0], matrix[0, 0])
