"""자리는 찾았는데 못 읽은 QR 을 펴서 다시 읽는다.

`cv2.QRCodeDetector.detectAndDecodeMulti` 는 코드 한 변이 100 px 아래로 내려가면 네 점은 내놓고 내용은 비우는 일이
잦다(병원 289a384 회차: "QR 을 못 읽었다. 한 변 83 px"). 그 네 점으로 코드를 모듈당 `MODULE_PX` 의 정사각형으로
펴고, 여백을 두르고, 이진화한 뒤 한 장짜리 `detectAndDecode` 로 다시 읽는다. 네 점 순서·회전은 디코더가 푼다.
거울상은 버전에 따라 못 풀어 좌우를 뒤집어 한 번 더 읽는다.
"""

import cv2
import numpy as np

#: 편 영상의 모듈 한 칸(px). 21 모듈(버전 1)이면 코드 한 변 168 px.
MODULE_PX = 8
#: QR 버전 1 의 모듈 수. `make_qr_textures.py` 가 만드는 ord-·cn-·md- ID 가 모두 버전 1 이다.
MODULES = 21
#: 편 영상에 두르는 여백(모듈). 디코더는 여백이 있어야 찾는다.
BORDER = 4


def rectify(image, quad):
    """네 점(영상 px) → 여백을 두른 흑백 정사각형(uint8, 0/255)."""
    gray = image if image.ndim == 2 else cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    side, pad = MODULES * MODULE_PX, BORDER * MODULE_PX
    target = np.float32([[pad, pad], [pad + side, pad], [pad + side, pad + side], [pad, pad + side]])
    transform = cv2.getPerspectiveTransform(np.float32(np.reshape(quad, (4, 2))), target)
    flat = cv2.warpPerspective(gray, transform, (side + 2 * pad, side + 2 * pad), flags=cv2.INTER_CUBIC,
                               borderValue=255)
    _, binary = cv2.threshold(flat, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return binary


def reread(image, quad, decoder=None):
    """펴서 다시 읽은 내용. 못 읽으면 빈 문자열."""
    decoder = decoder or cv2.QRCodeDetector()
    flat = rectify(image, quad)
    # 거울상은 OpenCV 버전에 따라 못 읽는다(master colcon 에서 실패 #553, 로컬 5.0 은 읽었다). 뒤집어 한 번 더 본다.
    for candidate in (flat, cv2.flip(flat, 1)):
        try:
            payload, _points, _straight = decoder.detectAndDecode(candidate)
        except cv2.error:
            continue
        if payload:
            return payload
    return ''


#: `read_enlarged` 가 영상을 키우는 배율.
ENLARGE = 2.0


def read_enlarged(image, decoder=None, scale=ENLARGE):
    """여러 개 읽기가 자리조차 못 찾았을 때: 영상을 키워 한 장짜리로 읽는다. (내용, 네 점) 또는 ('', None).

    `detectAndDecodeMulti` 는 코드 한 변 80 px 근처 아래에서 네 점도 못 찾는다(병원 모듈 약통, 35fb28a·94f19fb:
    거부 앞에 `QR 을 못 읽었다` 줄이 없었다). 2 배로 키운 영상의 `detectAndDecode` 는 오프라인에서 70 px 까지 읽었다.
    네 점만 찾고 못 읽으면 `reread` 로 편다. 네 점은 원래 영상 px 로 돌려준다.
    """
    decoder = decoder or cv2.QRCodeDetector()
    large = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    try:
        payload, points, _straight = decoder.detectAndDecode(large)
    except cv2.error:
        return '', None
    if points is None:
        return '', None
    quad = np.reshape(points, (4, 2)).astype(np.float32)
    if not payload:
        payload = reread(large, quad, decoder)
    if not payload:
        return '', None
    return payload, quad / float(scale)
