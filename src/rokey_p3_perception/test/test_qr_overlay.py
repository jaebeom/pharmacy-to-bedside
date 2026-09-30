"""QR 추적 영상(재범 9/29 "QR 부분을 사각형으로 트랙킹")의 판정 색·글자·크기. 그리기는 cv2 가 있을 때만 본다."""

import importlib.util

import pytest

from rokey_p3_perception import qr_overlay as Q


def test_the_pouch_being_picked_is_green_ok_and_another_order_is_red():
    assert Q.mark_for('pouch', 'ord-0001', 'ord-0001') == ('POUCH ord-0001 OK', Q.GREEN, 'ok')
    assert Q.mark_for('pouch', 'ord-0002', 'ord-0001') == ('POUCH ord-0002 NOT ORDER', Q.RED, 'mismatch')


def test_other_reads_are_green_and_a_located_but_unread_qr_is_yellow():
    assert Q.mark_for('patient', '2001') == ('PATIENT 2001', Q.GREEN, 'read')
    assert Q.mark_for('container', 'cn-0003', 'ord-0001') == ('CAN cn-0003', Q.GREEN, 'read')
    assert Q.mark_for('pouch', 'ord-0001', '') == ('POUCH ord-0001', Q.GREEN, 'read')   # 집는 중이 아니다
    assert Q.mark_for(None, None, 'ord-0001') == ('QR ?', Q.YELLOW, 'unread')


def test_labels_are_ascii_because_the_hershey_font_has_no_hangul():
    for args in (('pouch', 'ord-0001', 'ord-0002'), ('station', 'station_b'), (None, None)):
        assert Q.mark_for(*args)[0].isascii()


def test_the_view_is_scaled_to_the_web_stream_width():
    assert Q.scaled_size(1280, 800) == (640, 400, 0.5)
    assert Q.scaled_size(640, 400) == (640, 400, 1.0)


@pytest.mark.skipif(importlib.util.find_spec('cv2') is None, reason='cv2 없음(마스터에서 돈다)')
def test_draw_returns_a_scaled_copy_and_leaves_the_frame_alone():
    import numpy as np

    frame = np.zeros((800, 1280, 3), dtype=np.uint8)
    quad = [[100, 100], [300, 100], [300, 300], [100, 300]]
    out = Q.draw(frame, [(quad, 'POUCH ord-0001 OK', Q.GREEN)])
    assert out.shape == (400, 640, 3)
    assert frame.sum() == 0
    assert out.sum() > 0
