"""이미지 좌표 → 카메라 optical 프레임 자세. ROS 와 OpenCV 를 import 하지 않는다.

optical 프레임은 REP 103 이다(z 앞, x 오른쪽, y 아래). 계약 3절.
깊이는 두 가지로만 정한다. 둘 다 없으면 **거리를 모른다고 본다**(None).
지어낸 거리를 내보내면 팔이 엉뚱한 곳으로 간다.
"""

import math


def box_of(points):
    """점 목록을 감싸는 사각형 (x0, y0, x1, y1)."""
    xs = [float(point[0]) for point in points]
    ys = [float(point[1]) for point in points]
    return min(xs), min(ys), max(xs), max(ys)


def box_center(box):
    """사각형의 중심 (u, v)."""
    x0, y0, x1, y1 = box
    return (x0 + x1) / 2.0, (y0 + y1) / 2.0


def detection_pixel(box, quad=None):
    """봉투 자리로 쓸 영상 점 (u, v). QR 을 읽었으면 QR 네 점의 중심, 아니면 검출 사각형의 중심.

    QR 면은 봉투 윗면 한가운데에 붙는다(계약 3절). 색 검출 사각형은 봉투 옆 흰 벨트·롤러와 합쳐져 커질 수 있다
    (병원 회차20: 검출 16건, 흡착점이 봉투에서 0.10 m 옆). 그래서 QR 이 있으면 QR 이 봉투 자리다.
    """
    if quad is not None:
        return box_center(box_of(quad))
    return box_center(box)


def skip_for_rate(stamp, last, rate_hz):
    """추론 주기 상한(`max_rate_hz`). 마지막으로 처리한 프레임과 `1/rate_hz` 보다 가까우면 True(건너뛴다).

    `rate_hz` 가 0 이하면 상한 없음. 시계가 뒤로 가면(리셋) 건너뛰지 않는다. 1 ms 여유를 둔다 — 10 Hz 영상의
    stamp 차가 부동소수점으로 0.19999… 가 되어 한 장을 더 건너뛰면 5 Hz 가 3.3 Hz 가 된다.
    """
    return rate_hz > 0.0 and last is not None and 0.0 <= stamp - last < 1.0 / rate_hz - 1e-3


def box_size(box):
    """사각형의 (너비, 높이) px."""
    x0, y0, x1, y1 = box
    return x1 - x0, y1 - y0


def point_in_box(point, box):
    """점이 사각형 안인가. 검출된 봉투와 읽은 QR 을 짝지을 때 쓴다."""
    x0, y0, x1, y1 = box
    return x0 <= float(point[0]) <= x1 and y0 <= float(point[1]) <= y1


def quad_yaw(points):
    """QR 네 점의 첫 변 방향(rad). 이미지 기준이라 optical z 축 회전이다.

    OpenCV QRCodeDetector 는 네 꼭짓점을 순서대로 준다. 첫 변이 QR 의 가로다.
    """
    (x0, y0), (x1, y1) = (float(points[0][0]), float(points[0][1])), (float(points[1][0]), float(points[1][1]))
    return math.atan2(y1 - y0, x1 - x0)


def quad_min_side(points):
    """네 점이 이루는 사각형의 가장 짧은 변(px). `qr_min_size_px` 판정에 쓴다."""
    sides = []
    for index in range(len(points)):
        x0, y0 = float(points[index][0]), float(points[index][1])
        x1, y1 = float(points[(index + 1) % len(points)][0]), float(points[(index + 1) % len(points)][1])
        sides.append(math.hypot(x1 - x0, y1 - y0))
    return min(sides) if sides else 0.0


def depth_from_width(width_px, width_m, fx):
    """실제 크기를 아는 물체의 화면 너비로 거리를 잰다. 핀홀 모델. 모르면 None."""
    if width_px <= 0.0 or width_m <= 0.0 or fx <= 0.0:
        return None
    return fx * width_m / width_px


def resolve_depth(width_px, width_m, fx, fallback_distance_m):
    """깊이 결정 순서: 봉투 크기로 계산 → 설정한 고정 거리 → 모름(None)."""
    depth = depth_from_width(width_px, width_m, fx)
    if depth is not None:
        return depth
    return fallback_distance_m if fallback_distance_m > 0.0 else None


def position_from_pixel(u, v, depth, intrinsics):
    """픽셀과 깊이 → optical 프레임 위치 (x, y, z) m. `intrinsics` 는 (fx, fy, cx, cy)."""
    fx, fy, cx, cy = intrinsics
    if depth is None or fx <= 0.0 or fy <= 0.0:
        return None
    return ((u - cx) * depth / fx, (v - cy) * depth / fy, depth)


def quaternion_about_z(yaw):
    """optical z 축 회전 쿼터니언 (x, y, z, w)."""
    return (0.0, 0.0, math.sin(yaw / 2.0), math.cos(yaw / 2.0))
