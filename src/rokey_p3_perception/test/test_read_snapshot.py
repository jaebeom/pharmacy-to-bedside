"""read_snapshot: 약통 QR 을 읽은 순간 한 장(발표 PiP). epoch 마다 ID 하나에 한 장."""

import numpy as np
import pytest

cv2 = pytest.importorskip('cv2')

from rokey_p3_perception import read_snapshot  # noqa: E402

QUAD = np.float32([[100, 100], [180, 100], [180, 180], [100, 180]])


def _image():
    return np.full((600, 960, 3), 200, np.uint8)


def test_file_name_sorts_by_sim_time():
    assert read_snapshot.file_name(71, 580_000_000, 'cn-0204') == '000000071.580-cn-0204.png'
    names = [read_snapshot.file_name(s, 0, 'cn-0001') for s in (9, 10, 100)]
    assert names == sorted(names)


def test_one_image_per_id_per_epoch(tmp_path):
    shots = read_snapshot.Snapshots(str(tmp_path / 'reads'))
    first = shots.save(_image(), QUAD, 'cn-0204', 71, 0, 1)
    assert first is not None and cv2.imread(first).shape == (600, 960, 3)
    assert shots.save(_image(), QUAD, 'cn-0204', 72, 0, 1) is None          # 같은 epoch·ID 는 한 장
    assert shots.save(_image(), QUAD, 'cn-0211', 73, 0, 1) is not None      # 다른 ID
    assert shots.save(_image(), QUAD, 'cn-0204', 90, 0, 2) is not None      # 리셋 뒤 다시
    assert len(list((tmp_path / 'reads').iterdir())) == 3


def test_off_when_directory_is_empty(tmp_path):
    assert read_snapshot.Snapshots('').save(_image(), QUAD, 'cn-0204', 1, 0, 0) is None


def test_annotation_leaves_the_input_untouched():
    image = _image()
    out = read_snapshot.annotate(image, QUAD, 'cn-0204')
    assert (image == 200).all()
    assert (out[100, 100:180] == (0, 255, 0)).all()                        # 네 점 선


def test_a_failed_write_is_not_retried_every_frame(tmp_path, monkeypatch):
    """#628 검토: 쓰기 실패(imwrite False)를 10 Hz 로 다시 시도하지 않는다. (epoch, ID) 마다 한 번."""
    calls = []
    monkeypatch.setattr(read_snapshot.cv2, 'imwrite', lambda path, image: calls.append(path) or False)
    shots = read_snapshot.Snapshots(str(tmp_path / 'reads'))
    assert shots.save(_image(), QUAD, 'cn-0204', 1, 0, 1) is None
    assert shots.save(_image(), QUAD, 'cn-0204', 2, 0, 1) is None
    assert len(calls) == 1


def test_directory_error_is_raised_to_the_caller(tmp_path):
    """디렉토리를 못 만들면 OSError — 노드는 판독을 이미 발행한 뒤 경고로만 남긴다."""
    blocker = tmp_path / 'file'
    blocker.write_text('x')
    shots = read_snapshot.Snapshots(str(blocker / 'reads'))
    with pytest.raises(OSError):
        shots.save(_image(), QUAD, 'cn-0204', 1, 0, 1)


def test_annotation_without_quad_writes_only_the_label():
    out = read_snapshot.annotate(_image(), None, 'deck-ord-0001-00s')
    assert out.shape == (600, 960, 3) and not (out == 200).all()


def test_frame_stats_reports_brightness_and_saturation():
    image = _image()
    image[:300] = 255
    brightness, saturated = read_snapshot.frame_stats(image)
    assert 220 < brightness < 235
    assert saturated == pytest.approx(0.5)


def test_deck_watch_opens_at_the_event_and_saves_one_per_second():
    """campaign1 a01: 상판 집기 뒤 창 안 프레임마다 한 줄, 초마다 한 장. 창 밖·꺼짐은 None."""
    watch = read_snapshot.DeckWatch(3.0)
    assert watch.frame(10.0) is None                      # 이벤트 전
    watch.arm('ord-0001', 10.0)
    assert watch.frame(9.9) is None                       # 이벤트보다 앞선 프레임
    assert watch.frame(10.2) == (pytest.approx(0.2), True)
    assert watch.frame(10.6) == (pytest.approx(0.6), False)
    assert watch.frame(11.1) == (pytest.approx(1.1), True)
    assert watch.frame(13.5) is None                      # 창이 닫혔다
    assert watch.frame(12.0) is None                      # 닫힌 뒤에는 다시 열리지 않는다
    assert watch.order_id == 'ord-0001'
    off = read_snapshot.DeckWatch(0.0)
    off.arm('ord-0002', 5.0)
    assert off.frame(5.1) is None
