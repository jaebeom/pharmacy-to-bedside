"""qr_rectify: 자리만 찾은 작은 QR 을 펴서 다시 읽는다(병원 289a384 회차, 한 변 83 px)."""

import numpy as np
import pytest

cv2 = pytest.importorskip('cv2')

from rokey_p3_perception import qr_rectify  # noqa: E402

ORDER = 'ord-0001'


def _code(text):
    """QR 코드(여백 없음) 모듈 행렬 → 모듈당 10 px 흑백. 오류 정정 M 은 make_qr_textures.py 와 같다."""
    params = cv2.QRCodeEncoder_Params()
    params.correction_level = cv2.QRCodeEncoder_CORRECT_LEVEL_M
    matrix = cv2.QRCodeEncoder_create(params).encode(text)
    rows = np.where((matrix == 0).any(axis=1))[0]
    matrix = matrix[rows[0]:rows[-1] + 1, rows[0]:rows[-1] + 1]      # 인코더가 두른 여백을 뗀다
    assert matrix.shape == (qr_rectify.MODULES, qr_rectify.MODULES)
    return cv2.resize(matrix, None, fx=10, fy=10, interpolation=cv2.INTER_NEAREST)


def _scene(code_px, degrees, mirror=False):
    """1280x800 회색 바탕에 코드 한 변 `code_px` 로 돌려 놓고 흐린 영상과 코드 네 점."""
    code = _code(ORDER)
    if mirror:
        code = cv2.flip(code, 1)
    canvas = np.full((800, 1280), 200, np.uint8)
    small = cv2.resize(code, (code_px, code_px), interpolation=cv2.INTER_AREA)
    x0, y0 = 500, 300
    canvas[y0:y0 + code_px, x0:x0 + code_px] = small
    centre = (x0 + code_px / 2.0, y0 + code_px / 2.0)
    rotation = cv2.getRotationMatrix2D(centre, degrees, 1.0)
    canvas = cv2.warpAffine(canvas, rotation, (1280, 800), borderValue=200)
    canvas = cv2.GaussianBlur(canvas, (3, 3), 0.8)
    corners = np.float32([[x0, y0], [x0 + code_px, y0], [x0 + code_px, y0 + code_px], [x0, y0 + code_px]])
    quad = cv2.transform(corners[None], rotation)[0]
    return cv2.cvtColor(canvas, cv2.COLOR_GRAY2BGR), quad


# 60 px(모듈당 약 2.9 px)는 돌리면 못 읽는다(오프라인 확인). 70 px 부터 본다.
@pytest.mark.parametrize('code_px', [70, 83, 120])
@pytest.mark.parametrize('degrees', [0, 17, 40])
def test_rectified_code_reads_from_its_four_points(code_px, degrees):
    image, quad = _scene(code_px, degrees)
    assert qr_rectify.reread(image, quad) == ORDER


def test_corner_order_does_not_matter():
    image, quad = _scene(83, 17)
    assert qr_rectify.reread(image, np.roll(quad, 2, axis=0)) == ORDER


def test_mirror_image_still_reads():
    image, quad = _scene(83, 0, mirror=True)
    assert qr_rectify.reread(image, quad) == ORDER


def test_mirror_reads_even_when_the_decoder_cannot_unmirror():
    """거울상을 못 푸는 디코더(master colcon, #553)에서도 뒤집어 읽는다. 첫 시도는 빈 값으로 흉내 낸다."""
    image, quad = _scene(83, 0, mirror=True)
    real = cv2.QRCodeDetector()
    seen = []

    class MirrorBlind:
        def detectAndDecode(self, flat):
            seen.append(flat)
            if len(seen) == 1:
                return '', None, None
            return real.detectAndDecode(flat)

    assert qr_rectify.reread(image, quad, MirrorBlind()) == ORDER
    assert len(seen) == 2


def test_blank_quad_reads_nothing():
    image = np.full((800, 1280, 3), 200, np.uint8)
    quad = np.float32([[500, 300], [583, 300], [583, 383], [500, 383]])
    assert qr_rectify.reread(image, quad) == ''


def test_rectified_image_is_code_plus_border():
    image, quad = _scene(83, 0)
    flat = qr_rectify.rectify(image, quad)
    side = (qr_rectify.MODULES + 2 * qr_rectify.BORDER) * qr_rectify.MODULE_PX
    assert flat.shape == (side, side)
    assert set(np.unique(flat)) <= {0, 255}


@pytest.mark.parametrize('code_px', [77, 83])
@pytest.mark.parametrize('degrees', [0, 10, 25, 40])
def test_enlarged_read_finds_codes_multi_misses(code_px, degrees):
    """병원 모듈 약통: 여러 개 읽기가 네 점도 못 찾은 크기를 키워서 읽는다. 네 점은 원래 영상 px 다."""
    image, quad = _scene(code_px, degrees)
    payload, found = qr_rectify.read_enlarged(image)
    assert payload == ORDER
    centre = np.mean(found, axis=0)
    np.testing.assert_allclose(centre, np.mean(quad, axis=0), atol=3.0)
    sides = [np.linalg.norm(found[i] - found[(i + 1) % 4]) for i in range(4)]
    assert min(sides) == pytest.approx(code_px, abs=6.0)


def test_enlarged_read_of_nothing_is_empty():
    image = np.full((600, 960, 3), 200, np.uint8)
    assert qr_rectify.read_enlarged(image) == ('', None)
