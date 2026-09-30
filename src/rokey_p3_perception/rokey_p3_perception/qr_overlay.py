"""QR 추적 영상(재범 9/29 "QR 찍는 걸 가시적으로 — QR 부분을 사각형으로 트랙킹"). ROS 를 import 하지 않는다.

손 카메라 한 장에 찾은 QR 마다 **네 꼭짓점 사각형**을 그린다(비스듬히 찍혀도 QR 에 맞는다). 색은 판정이다:
- 초록: 읽었다. 지금 집는 주문(`PICK_ATTEMPT`)의 봉투면 `OK` 를 붙인다.
- 빨강: 봉투 QR 인데 지금 집는 주문이 아니다(`NOT ORDER`) — 팔은 그 봉투를 집지 않는다(`qr_mismatch`).
- 노랑: 자리는 찾았지만 못 읽었다(`QR ?`).
글자는 ASCII 다(OpenCV Hershey 글꼴은 한글이 없다). 사람 말 요약은 웹 QR 판독 칸(api.md §1.12)이 한다.
판정(`mark_for`)과 크기(`scaled_size`)는 cv2 없이 시험한다. 그리기(`draw`)만 cv2 가 필요하다.
"""

GREEN = (40, 200, 40)      # BGR
RED = (40, 40, 230)
YELLOW = (0, 210, 255)
#: 내보내는 영상 폭 상한(px). 웹 스트림(live_sensors.MAX_WIDTH)과 같다 — 1280 원본을 그대로 보내지 않는다.
MAX_WIDTH = 640

_KIND_LABEL = {'pouch': 'POUCH', 'patient': 'PATIENT', 'station': 'STATION', 'container': 'CAN', 'module': 'MODULE'}


def mark_for(kind, tag_id, expected_order=''):
    """(글자, 색, 상태) — 상태는 'ok'·'read'·'mismatch'·'unread'. 못 읽었으면 kind·tag_id 가 None."""
    if not tag_id:
        return 'QR ?', YELLOW, 'unread'
    label = f'{_KIND_LABEL.get(kind, "QR")} {tag_id}'
    if kind == 'pouch' and expected_order:
        if tag_id == expected_order:
            return f'{label} OK', GREEN, 'ok'
        return f'{label} NOT ORDER', RED, 'mismatch'
    return label, GREEN, 'read'


def scaled_size(width, height, max_width=MAX_WIDTH):
    """(폭, 높이, 배율). 폭이 상한 이하면 그대로다."""
    if width <= max_width or width <= 0:
        return int(width), int(height), 1.0
    scale = max_width / float(width)
    return int(round(width * scale)), int(round(height * scale)), scale


def draw(image, marks, max_width=MAX_WIDTH):
    """`marks` = [(네 점, 글자, 색)] 을 그린 줄인 사본(bgr8). 원본은 건드리지 않는다."""
    import cv2
    import numpy as np

    height, width = image.shape[:2]
    out_w, out_h, scale = scaled_size(width, height, max_width)
    out = cv2.resize(image, (out_w, out_h), interpolation=cv2.INTER_AREA) if scale != 1.0 else image.copy()
    for quad, label, color in marks:
        points = (np.reshape(np.asarray(quad, dtype=np.float32), (4, 2)) * scale).astype(np.int32)
        cv2.polylines(out, [points], True, color, 3, cv2.LINE_AA)
        x, y = int(points[:, 0].min()), int(points[:, 1].min())
        (tw, th), base = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
        top = max(0, y - th - base - 6)
        cv2.rectangle(out, (x, top), (x + tw + 6, top + th + base + 4), color, -1)
        cv2.putText(out, label, (x + 3, top + th + 2), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1,
                    cv2.LINE_AA)
    return out
