"""QR 을 읽은 순간의 영상 한 장을 남긴다(발표 손 카메라 PiP, 작전 9/23 재범 확정: D455 = 약통 QR 확인).

같은 ID 는 epoch 마다 한 장만 남긴다. 파일 이름은 영상 stamp(sim s)와 ID 다. 판독 네 점을 초록 선으로,
ID 를 그 위에 적는다. 판정에는 쓰지 않는다 — 기록용이다.
"""

import os

import cv2
import numpy as np


def file_name(stamp_sec, stamp_nanosec, tag_id):
    """`<sim s 9자리>.<ms 3자리>-<ID>.png`. 정렬하면 시간 순이다."""
    return f'{int(stamp_sec):09d}.{int(stamp_nanosec) // 1_000_000:03d}-{tag_id}.png'


def annotate(image, quad, text):
    """원본을 건드리지 않고, 네 점과 글자를 그린 사본. `quad` 가 None 이면 글자만 왼쪽 위에 적는다."""
    out = image.copy()
    if quad is None:
        cv2.putText(out, text, (8, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
        return out
    points = np.reshape(np.asarray(quad, dtype=np.float32), (4, 2)).astype(np.int32)
    cv2.polylines(out, [points], True, (0, 255, 0), 2)
    x, y = int(points[:, 0].min()), int(points[:, 1].min())
    cv2.putText(out, text, (x, max(18, y - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
    return out


class Snapshots:
    """(epoch, ID) 마다 한 장. `directory` 가 비면 아무것도 안 한다."""

    def __init__(self, directory):
        self.directory = directory
        self._saved = set()

    def save(self, image, quad, tag_id, stamp_sec, stamp_nanosec, epoch):
        """남겼으면 경로, 아니면 None(꺼짐·이미 시도함·쓰기 실패).

        (epoch, ID) 마다 **한 번만 시도**한다 — 쓰기에 실패해도 다음 프레임에 다시 쓰지 않는다(10 Hz 로 반복하지
        않게, #628 검토). 디렉토리를 못 만들면 OSError 를 그대로 올린다(부르는 쪽이 경고로 남긴다).
        """
        if not self.directory or (epoch, tag_id) in self._saved:
            return None
        self._saved.add((epoch, tag_id))
        os.makedirs(self.directory, exist_ok=True)
        path = os.path.join(self.directory, file_name(stamp_sec, stamp_nanosec, tag_id))
        if not cv2.imwrite(path, annotate(image, quad, tag_id)):
            return None
        return path


def frame_stats(image):
    """(밝기 V 평균 0–255, V ≥ 250 인 화소 비율). 조명·반사 단서다 — 판정에는 쓰지 않는다."""
    value = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)[:, :, 2]
    return float(value.mean()), float((value >= 250).mean())


class DeckWatch:
    """상판 집기(`PICK_ATTEMPT` detail=deck) 뒤 `seconds` 동안 손 카메라 프레임을 지켜본다.

    campaign1 a01(bed_a1): 상판 비전이 0/13 프레임인데 검출기 로그가 0줄이라 QR 이 화면 밖이었는지, 보였는데
    못 찾았는지(반사·조명) 가를 수 없었다. 창 안 프레임마다 한 줄, 그리고 초마다 한 장을 남긴다.
    """

    def __init__(self, seconds):
        self.seconds = max(0.0, float(seconds))
        self.order_id = ''
        self._start = None
        self._saved = set()

    def arm(self, order_id, stamp):
        """이벤트 stamp(sim s)부터 창을 연다. `seconds` 가 0 이면 꺼져 있다."""
        if self.seconds <= 0.0:
            return
        self.order_id, self._start, self._saved = order_id, float(stamp), set()

    def frame(self, stamp):
        """이 프레임이 창 안이면 (창 시작부터 초, 이 초의 첫 장인가). 아니면 None."""
        if self._start is None:
            return None
        offset = stamp - self._start
        if offset < 0.0 or offset > self.seconds:
            if offset > self.seconds:
                self._start = None
            return None
        second = int(offset)
        first = second not in self._saved
        self._saved.add(second)
        return offset, first
