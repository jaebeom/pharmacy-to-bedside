"""픽셀 광선과 지지 평면의 교차 → 평면 위의 점. ROS·OpenCV 를 import 하지 않는다. 노드에 아직 연결하지 않는다.

지시문 5절: "2D box 만으로 3D 파지점을 확정하지 않는다. QR 과 depth 또는 검증된 평면 투영을 결합한다."
#232 계획 4절 5·6번: 깊이가 없으면 보정된 벨트·상판·보관함 지지 평면과 광선 교차를 쓴다.
**일정 깊이를 모든 위치에 적용하지 않는다.** 이미 있는 `pouch_geometry` 의 폭·고정 거리 추정(현행 시연 경로)은
그대로 두고, 이 모듈은 별도 경로다.

규약
- 카메라는 REP 103 optical 프레임이다(z 앞, x 오른쪽, y 아래). 픽셀 (u, v) 는 **왜곡을 편 영상** 기준이다
  (`CameraInfo` 의 K 만 쓴다. D 는 호출자가 미리 편다).
- 평면은 "평면 프레임"의 z=0 면이다. +z 가 평면 위(물체가 놓이는 쪽)이고, 카메라는 +z 쪽에 있어야 한다.
  `optical_from_plane` 은 optical 프레임에서 본 평면 프레임의 자세다: 위치 (x, y, z) m 과
  quaternion **(x, y, z, w) — ROS geometry_msgs 의 순서**. USD 는 (w, x, y, z) 순서라 넘기기 전에 바꾼다.
- 허용 영역은 평면 프레임의 사각형 `(x_min, x_max, y_min, y_max)` m 이다(벨트 상판·상판 칸 바닥·보관함 바닥).
- 단위는 m·rad 이다.

모든 기하 입력(내부 파라미터·영상 크기, 평면 자세, 허용 영역, 최소 입사각)은 호출자가 넘긴다. **기본값이 없다.**
실제 카메라 보정값과 평면 자세는 L3 실측 대상이라 미측정이다. 하나라도 없거나 무효이면 거부(`status != OK`)다.
"""

import math
from collections import namedtuple

import numpy as np

OK = 'ok'
MISSING_INPUT = 'missing_input'          # 입력이 없다(미설정)
INVALID_INPUT = 'invalid_input'          # 입력이 NaN/Inf, 0 이하 초점거리, 빈 영역, 0 quaternion 등
OUTSIDE_IMAGE = 'outside_image'          # 픽셀이 영상 밖
CAMERA_BELOW_PLANE = 'camera_below_plane'  # 카메라가 평면 아래(또는 평면 위)에 있다
PARALLEL = 'parallel'                    # 광선이 평면과 평행
BEHIND = 'behind'                        # 교차점이 카메라 뒤
GRAZING = 'grazing'                      # 광선이 평면에 너무 얕게 닿는다(입사각 < 최소)
OUTSIDE_REGION = 'outside_region'        # 교차점이 허용 영역 밖

#: 광선·평면 평행 판정의 수치 한계(방향 코사인). 임계값이 아니다. 얕은 입사는 `min_grazing_rad` 로 거른다.
PARALLEL_EPSILON = 1e-9

Intrinsics = namedtuple('Intrinsics', ('fx', 'fy', 'cx', 'cy', 'width', 'height'))
Plane = namedtuple('Plane', ('position', 'quaternion_xyzw', 'region'))
Projection = namedtuple('Projection', ('status', 'reason', 'plane_point', 'optical_point', 'depth', 'grazing_rad'))


def project(u, v, intrinsics, plane, min_grazing_rad):
    """픽셀 (u, v) → Projection. status 가 OK 가 아니면 점은 None 이고 reason 에 이유가 있다.

    - `plane_point`: 평면 프레임의 교차점 (x, y, 0)
    - `optical_point`: optical 프레임의 교차점 (x, y, z)
    - `depth`: optical z(m). 광선 길이가 아니다
    - `grazing_rad`: 광선과 평면이 이루는 각. π/2 가 수직 입사다
    """
    problem = _input_problem(u, v, intrinsics, plane, min_grazing_rad)
    if problem:
        return _reject(*problem)
    fx, fy, cx, cy, width, height = (float(value) for value in intrinsics)
    if not (0.0 <= u <= width and 0.0 <= v <= height):
        return _reject(OUTSIDE_IMAGE, f'픽셀 ({u:.1f}, {v:.1f}) 가 영상 {width:.0f}x{height:.0f} 밖이다')

    rotation = rotation_from_quaternion(*plane.quaternion_xyzw)
    origin = np.asarray(plane.position, dtype=float)
    normal = rotation[:, 2]
    camera_in_plane = rotation.T @ (-origin)
    if camera_in_plane[2] <= 0.0:
        return _reject(CAMERA_BELOW_PLANE, f'카메라가 평면 위에 있지 않다(평면 z {camera_in_plane[2]:.4f} m)')

    ray = np.array([(u - cx) / fx, (v - cy) / fy, 1.0])
    unit = ray / np.linalg.norm(ray)
    facing = float(normal @ unit)
    if abs(facing) < PARALLEL_EPSILON:
        return _reject(PARALLEL, '광선이 평면과 평행하다')
    scale = float(normal @ origin) / float(normal @ ray)
    if scale <= 0.0:
        return _reject(BEHIND, '교차점이 카메라 뒤에 있다')
    grazing = math.asin(min(1.0, abs(facing)))
    if grazing < min_grazing_rad:
        return _reject(GRAZING, f'입사각 {grazing:.4f} rad < 최소 {min_grazing_rad:.4f} rad', grazing)

    optical_point = ray * scale
    plane_point = rotation.T @ (optical_point - origin)
    plane_point[2] = 0.0
    x_min, x_max, y_min, y_max = (float(value) for value in plane.region)
    if not (x_min <= plane_point[0] <= x_max and y_min <= plane_point[1] <= y_max):
        return _reject(OUTSIDE_REGION,
                       f'교차점 ({plane_point[0]:.4f}, {plane_point[1]:.4f}) 가 허용 영역 밖이다', grazing)
    return Projection(OK, '', tuple(plane_point), tuple(optical_point), float(optical_point[2]), grazing)


def rotation_from_quaternion(x, y, z, w):
    """ROS 순서 quaternion (x, y, z, w) → 3x3. 정규화한다. 크기 0 이면 ValueError."""
    norm = math.sqrt(x * x + y * y + z * z + w * w)
    if not math.isfinite(norm) or norm < 1e-12:
        raise ValueError('quaternion 크기가 0 이거나 유한하지 않다')
    x, y, z, w = x / norm, y / norm, z / norm, w / norm
    return np.array([
        [1.0 - 2.0 * (y * y + z * z), 2.0 * (x * y - z * w), 2.0 * (x * z + y * w)],
        [2.0 * (x * y + z * w), 1.0 - 2.0 * (x * x + z * z), 2.0 * (y * z - x * w)],
        [2.0 * (x * z - y * w), 2.0 * (y * z + x * w), 1.0 - 2.0 * (x * x + y * y)],
    ])


def _input_problem(u, v, intrinsics, plane, min_grazing_rad):
    if intrinsics is None or plane is None or min_grazing_rad is None or u is None or v is None:
        return MISSING_INPUT, '내부 파라미터·평면·최소 입사각·픽셀 중 없는 것이 있다'
    if plane.position is None or plane.quaternion_xyzw is None or plane.region is None:
        return MISSING_INPUT, '평면 자세 또는 허용 영역이 없다'
    try:
        values = [float(value) for value in (u, v, min_grazing_rad, *intrinsics, *plane.position,
                                             *plane.quaternion_xyzw, *plane.region)]
    except (TypeError, ValueError):
        return INVALID_INPUT, '숫자가 아닌 입력이 있다'
    if (len(intrinsics) != 6 or len(plane.position) != 3 or len(plane.quaternion_xyzw) != 4
            or len(plane.region) != 4):
        return INVALID_INPUT, '입력 길이가 틀렸다'
    if not all(math.isfinite(value) for value in values):
        return INVALID_INPUT, 'NaN 또는 Inf 가 있다'
    fx, fy, _cx, _cy, width, height = (float(value) for value in intrinsics)
    if fx <= 0.0 or fy <= 0.0 or width <= 0.0 or height <= 0.0:
        return INVALID_INPUT, '초점거리·영상 크기는 양수여야 한다'
    x_min, x_max, y_min, y_max = (float(value) for value in plane.region)
    if not (x_min < x_max and y_min < y_max):
        return INVALID_INPUT, '허용 영역이 비었다'
    if not 0.0 < float(min_grazing_rad) <= math.pi / 2.0:
        return INVALID_INPUT, '최소 입사각은 (0, π/2] 여야 한다'
    try:
        rotation_from_quaternion(*plane.quaternion_xyzw)
    except ValueError as error:
        return INVALID_INPUT, str(error)
    return None


def _reject(status, reason, grazing=None):
    return Projection(status, reason, None, None, None, grazing)
