"""L1: 이미지 좌표 → 카메라 프레임 자세."""

import math

from rokey_p3_perception.pouch_geometry import (
    box_center,
    box_of,
    box_size,
    depth_from_width,
    detection_pixel,
    skip_for_rate,
    point_in_box,
    position_from_pixel,
    quad_min_side,
    quad_yaw,
    quaternion_about_z,
    resolve_depth,
)

SQUARE = ((10.0, 20.0), (50.0, 20.0), (50.0, 60.0), (10.0, 60.0))


def test_box_helpers():
    box = box_of(SQUARE)
    assert box == (10.0, 20.0, 50.0, 60.0)
    assert box_center(box) == (30.0, 40.0)
    assert box_size(box) == (40.0, 40.0)
    assert quad_min_side(SQUARE) == 40.0


def test_point_in_box_matches_a_qr_to_a_detection():
    box = box_of(SQUARE)
    assert point_in_box((30.0, 40.0), box)
    assert not point_in_box((9.0, 40.0), box)


def test_quad_yaw_follows_the_first_edge():
    assert quad_yaw(SQUARE) == 0.0
    turned = ((10.0, 20.0), (10.0, 60.0), (-30.0, 60.0), (-30.0, 20.0))
    assert abs(quad_yaw(turned) - math.pi / 2.0) < 1e-12


def test_depth_from_apparent_width():
    # fx 600 px, 폭 0.10 m 인 봉투가 100 px 로 보이면 0.6 m.
    assert abs(depth_from_width(100.0, 0.10, 600.0) - 0.6) < 1e-12
    assert depth_from_width(0.0, 0.10, 600.0) is None
    assert depth_from_width(100.0, 0.0, 600.0) is None


def test_resolve_depth_order_and_unknown():
    assert abs(resolve_depth(100.0, 0.10, 600.0, 0.0) - 0.6) < 1e-12
    # 봉투 크기를 모르면 설정한 고정 거리를 쓴다.
    assert resolve_depth(100.0, 0.0, 600.0, 0.5) == 0.5
    # 둘 다 없으면 거리를 모른다. 지어내지 않는다.
    assert resolve_depth(100.0, 0.0, 600.0, 0.0) is None


def test_position_from_pixel_is_rep103_optical():
    intrinsics = (600.0, 600.0, 320.0, 240.0)
    assert position_from_pixel(320.0, 240.0, 0.5, intrinsics) == (0.0, 0.0, 0.5)
    # 오른쪽(+x), 아래(+y).
    x, y, z = position_from_pixel(380.0, 300.0, 0.5, intrinsics)
    assert x > 0.0 and y > 0.0 and z == 0.5
    assert position_from_pixel(320.0, 240.0, None, intrinsics) is None


def test_quaternion_about_z():
    assert quaternion_about_z(0.0) == (0.0, 0.0, 0.0, 1.0)
    x, y, z, w = quaternion_about_z(math.pi)
    assert abs(z - 1.0) < 1e-12 and abs(w) < 1e-12 and (x, y) == (0.0, 0.0)


def test_skip_for_rate_caps_inference_at_five_hertz():
    """재범 9/25: 추론 5 Hz 상한. 10 Hz 영상이면 한 장 건너 한 장."""
    assert not skip_for_rate(10.0, None, 5.0)          # 첫 장
    assert skip_for_rate(10.1, 10.0, 5.0)
    assert not skip_for_rate(10.2, 10.0, 5.0)
    assert not skip_for_rate(10.1, 10.0, 0.0)          # 0 = 상한 없음
    assert not skip_for_rate(3.0, 10.0, 5.0)           # 리셋으로 시계가 뒤로 가면 처리한다


def test_detection_pixel_is_the_qr_centre_when_the_qr_was_read():
    """병원 회차20: 색 사각형이 벨트 흰 부분과 합쳐져 넓어도, QR 을 읽었으면 QR 중심이 봉투 자리다."""
    wide_box = (100.0, 100.0, 500.0, 200.0)
    quad = [(120.0, 120.0), (180.0, 120.0), (180.0, 180.0), (120.0, 180.0)]
    assert detection_pixel(wide_box, quad) == (150.0, 150.0)
    assert detection_pixel(wide_box) == (300.0, 150.0)
