"""L1: 픽셀 광선과 지지 평면의 교차(순수). 기하는 시험용 값이다. 실제 보정값·평면 자세는 미측정(L3)이다."""

import math

import pytest

from rokey_p3_perception import plane_projection as pp

K = pp.Intrinsics(fx=550.0, fy=550.0, cx=320.0, cy=240.0, width=640.0, height=480.0)
H = 0.40                                    # 시험용 카메라 높이
DOWN = (1.0, 0.0, 0.0, 0.0)                 # xyzw: x 축 180°. 평면 +z 가 카메라 쪽(optical -z)
REGION = (-1.0, 1.0, -1.0, 1.0)
MIN_GRAZING = math.radians(10.0)


def about_x(angle):
    """x 축 회전 quaternion (x, y, z, w)."""
    return (math.sin(angle / 2.0), 0.0, 0.0, math.cos(angle / 2.0))


def plane(position=(0.0, 0.0, H), quaternion=DOWN, region=REGION):
    return pp.Plane(position, quaternion, region)


def pixel_of(plane_point, plane_):
    """평면 위 점 → 픽셀(핀홀). 역투영 대조용."""
    rotation = pp.rotation_from_quaternion(*plane_.quaternion_xyzw)
    x, y, z = rotation @ plane_point + plane_.position
    return K.fx * x / z + K.cx, K.fy * y / z + K.cy, z


# 정상 -------------------------------------------------------------------------

def test_straight_down_center_pixel_hits_below_the_camera():
    result = pp.project(K.cx, K.cy, K, plane(), MIN_GRAZING)
    assert result.status == pp.OK and result.reason == ''
    assert result.plane_point == pytest.approx((0.0, 0.0, 0.0), abs=1e-12)
    assert result.depth == pytest.approx(H)
    assert result.grazing_rad == pytest.approx(math.pi / 2.0)


@pytest.mark.parametrize('tilt', [0.0, 0.35, -0.5])
@pytest.mark.parametrize('point', [(0.0, 0.0), (0.12, -0.05), (-0.12, 0.10)])
def test_back_projection_recovers_the_plane_point(tilt, point):
    tilted = plane(position=(0.02, -0.03, H), quaternion=_compose(about_x(tilt), DOWN))
    target = (point[0], point[1], 0.0)
    u, v, z = pixel_of(target, tilted)
    assert 0.0 <= u <= K.width and 0.0 <= v <= K.height          # 시험 배치가 시야 안인지 먼저 확인
    result = pp.project(u, v, K, tilted, MIN_GRAZING)
    assert result.status == pp.OK
    assert result.plane_point == pytest.approx(target, abs=1e-9)
    assert result.depth == pytest.approx(z)


def test_constant_depth_is_wrong_on_a_tilted_plane():
    # 계획 4절 5번: 일정 깊이를 모든 위치에 적용하지 않는다.
    # 중심에서 같은 픽셀 거리(위·아래 150 px)라도 기울어진 평면에서는 깊이가 다르다.
    tilted = plane(quaternion=_compose(about_x(0.4), DOWN))
    center = pp.project(K.cx, K.cy, K, tilted, MIN_GRAZING)
    above = pp.project(K.cx, K.cy - 150.0, K, tilted, MIN_GRAZING)
    below = pp.project(K.cx, K.cy + 150.0, K, tilted, MIN_GRAZING)
    assert {center.status, above.status, below.status} == {pp.OK}
    assert abs(above.depth - below.depth) > 0.05
    # 중심 깊이를 그대로 쓰면 optical 위치가 실제 교차점에서 수 cm 벗어난다.
    for hit in (above, below):
        u_offset = 0.0
        v_offset = hit.optical_point[1] / hit.depth                  # (v - cy) / fy
        assumed = (u_offset * center.depth, v_offset * center.depth, center.depth)
        error = math.dist(assumed, hit.optical_point)
        assert error > 0.02


def test_quaternion_is_ros_xyzw_order():
    # (1, 0, 0, 0) 은 xyzw 로 x 축 180°다. 같은 네 수를 wxyz 로 읽으면 항등 회전이라 평면이 카메라 반대쪽을 본다.
    assert pp.project(K.cx, K.cy, K, plane(quaternion=(1.0, 0.0, 0.0, 0.0)), MIN_GRAZING).status == pp.OK
    identity_xyzw = (0.0, 0.0, 0.0, 1.0)
    assert pp.project(K.cx, K.cy, K, plane(quaternion=identity_xyzw), MIN_GRAZING).status == pp.CAMERA_BELOW_PLANE


def test_unnormalized_quaternion_is_normalized():
    result = pp.project(K.cx, K.cy, K, plane(quaternion=(2.0, 0.0, 0.0, 0.0)), MIN_GRAZING)
    assert result.status == pp.OK and result.depth == pytest.approx(H)


# 거부 -------------------------------------------------------------------------

@pytest.mark.parametrize('args', [
    (None, K.cy, K, plane(), MIN_GRAZING),
    (K.cx, K.cy, None, plane(), MIN_GRAZING),
    (K.cx, K.cy, K, None, MIN_GRAZING),
    (K.cx, K.cy, K, plane(), None),
    (K.cx, K.cy, K, plane(position=None), MIN_GRAZING),
    (K.cx, K.cy, K, plane(quaternion=None), MIN_GRAZING),
    (K.cx, K.cy, K, plane(region=None), MIN_GRAZING),
])
def test_missing_inputs_are_rejected(args):
    result = pp.project(*args)
    assert result.status == pp.MISSING_INPUT and result.plane_point is None


@pytest.mark.parametrize('args', [
    (math.nan, K.cy, K, plane(), MIN_GRAZING),
    (K.cx, math.inf, K, plane(), MIN_GRAZING),
    (K.cx, K.cy, K._replace(fx=0.0), plane(), MIN_GRAZING),
    (K.cx, K.cy, K._replace(width=math.nan), plane(), MIN_GRAZING),
    (K.cx, K.cy, K, plane(position=(0.0, 0.0, math.nan)), MIN_GRAZING),
    (K.cx, K.cy, K, plane(quaternion=(0.0, 0.0, 0.0, 0.0)), MIN_GRAZING),
    (K.cx, K.cy, K, plane(region=(0.5, 0.5, -1.0, 1.0)), MIN_GRAZING),     # 빈 영역
    (K.cx, K.cy, K, plane(region=(-1.0, 1.0)), MIN_GRAZING),               # 길이
    (K.cx, K.cy, K, plane(), 0.0),                                        # 최소 입사각 0 은 무효
    (K.cx, K.cy, K, plane(), 2.0),                                        # π/2 초과
    (K.cx, K.cy, K, plane(position=('a', 0.0, H)), MIN_GRAZING),
])
def test_invalid_inputs_are_rejected(args):
    assert pp.project(*args).status == pp.INVALID_INPUT


@pytest.mark.parametrize('u, v', [(-1.0, K.cy), (K.width + 1.0, K.cy), (K.cx, -0.5), (K.cx, K.height + 2.0)])
def test_pixels_outside_the_image_are_rejected(u, v):
    assert pp.project(u, v, K, plane(), MIN_GRAZING).status == pp.OUTSIDE_IMAGE


def test_camera_below_the_plane_is_rejected():
    assert pp.project(K.cx, K.cy, K, plane(position=(0.0, 0.0, -H)), MIN_GRAZING).status == pp.CAMERA_BELOW_PLANE


# 벽처럼 선 평면: 원점 (1, 0, 0), 법선 optical -x(카메라 쪽). 카메라는 평면 위(+z 쪽)에 있다.
WALL = plane(position=(1.0, 0.0, 0.0), quaternion=(0.0, -math.sin(math.pi / 4.0), 0.0, math.cos(math.pi / 4.0)))


def test_ray_parallel_to_the_plane_is_rejected():
    assert pp.project(K.cx, K.cy, K, WALL, MIN_GRAZING).status == pp.PARALLEL


def test_intersection_behind_the_camera_is_rejected():
    assert pp.project(K.cx - 100.0, K.cy, K, WALL, MIN_GRAZING).status == pp.BEHIND


def test_grazing_rays_are_rejected_by_the_given_threshold():
    shallow = pp.project(K.cx + 20.0, K.cy, K, WALL._replace(region=(-100.0, 100.0, -100.0, 100.0)), MIN_GRAZING)
    assert shallow.status == pp.GRAZING and shallow.grazing_rad < MIN_GRAZING
    allowed = pp.project(K.cx + 20.0, K.cy, K, WALL._replace(region=(-100.0, 100.0, -100.0, 100.0)),
                         shallow.grazing_rad / 2.0)
    assert allowed.status == pp.OK


def test_intersection_outside_the_allowed_region_is_rejected():
    small = plane(region=(-0.05, 0.05, -0.05, 0.05))
    assert pp.project(K.cx, K.cy, K, small, MIN_GRAZING).status == pp.OK
    result = pp.project(K.cx + 200.0, K.cy, K, small, MIN_GRAZING)
    assert result.status == pp.OUTSIDE_REGION and result.plane_point is None


def test_region_edges_are_inside():
    # 가장자리는 영역 안으로 본다(평면 위의 점이 영역 경계에 정확히 놓인 경우).
    edge = plane(region=(0.0, 0.1, -0.1, 0.1))
    assert pp.project(K.cx, K.cy, K, edge, MIN_GRAZING).status == pp.OK


def _compose(first, second):
    """quaternion 곱 first ⊗ second (xyzw). second 를 먼저 적용한 뒤 first."""
    x1, y1, z1, w1 = first
    x2, y2, z2, w2 = second
    return (w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
            w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
            w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2,
            w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2)
