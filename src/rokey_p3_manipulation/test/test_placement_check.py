"""L1: 칸 안착 확인의 순수 판정(계약 11.4 제안). 상자 치수는 시험용 값이다(실제 값 미측정)."""

import math

import pytest

from rokey_p3_manipulation import placement_check as placement
from rokey_p3_manipulation.placement_check import (
    Candidate,
    box_problem,
    dependency_problem,
    inside_box,
    placement_confirmed,
)

BOX = (0.14, 0.11, 0.04)
ORDER = 'ord-0001'


@pytest.mark.parametrize('box', [None, (0.14, 0.11), (0.14, 0.11, 0.0), (0.14, -0.1, 0.04),
                                 (0.14, math.nan, 0.04), ('a', 0.1, 0.1)])
def test_unset_or_invalid_box_cannot_confirm(box):
    assert box_problem(box)
    assert placement_confirmed([Candidate(ORDER, 5.0, (0.0, 0.0, 0.005))], ORDER, 1.0, box)[0] is False


def test_inside_is_strict_on_the_sides_and_closed_in_height():
    assert inside_box((0.0, 0.0, 0.0), BOX)
    assert inside_box((0.069, 0.054, 0.04), BOX)
    assert not inside_box((0.07, 0.0, 0.01), BOX)             # 벽 위(가장자리)는 안착이 아니다
    assert not inside_box((0.0, -0.055, 0.01), BOX)
    assert not inside_box((0.0, 0.0, -0.001), BOX)            # 바닥 아래
    assert not inside_box((0.0, 0.0, 0.041), BOX)             # 칸 위로 떠 있다
    assert not inside_box((math.nan, 0.0, 0.01), BOX)
    assert not inside_box(None, BOX)


def test_confirmed_needs_new_stamp_same_order_and_inside():
    good = Candidate(ORDER, 5.0, (0.01, -0.01, 0.005))
    assert placement_confirmed([good], ORDER, 4.0, BOX) == (True, '')
    for bad in (good._replace(stamp_s=3.9),                    # 해제 명령 전 이미지
                good._replace(stamp_s=None),
                good._replace(order_id='ord-0002'),            # 다른 봉투
                good._replace(point=None),                     # 거리를 모른 검출
                good._replace(point=(0.2, 0.0, 0.005))):       # 칸 밖
        confirmed, reason = placement_confirmed([bad], ORDER, 4.0, BOX)
        assert confirmed is False and reason


def test_any_one_good_candidate_is_enough():
    candidates = [Candidate('ord-0002', 5.0, (0.0, 0.0, 0.005)), Candidate(ORDER, 5.0, (0.0, 0.0, 0.005))]
    assert placement_confirmed(candidates, ORDER, 4.0, BOX)[0] is True


def test_reason_counts_what_was_seen():
    candidates = [Candidate(ORDER, 3.0, (0.0, 0.0, 0.0)), Candidate(ORDER, 5.0, (0.3, 0.0, 0.0))]
    confirmed, reason = placement_confirmed(candidates, ORDER, 4.0, BOX)
    assert not confirmed and 'old=1' in reason and 'outside=1' in reason
    assert placement_confirmed([], ORDER, 4.0, BOX) == (False, f'칸 안에서 {ORDER} 를 못 봤다(검출 없음)')
    assert placement_confirmed([Candidate(ORDER, 5.0, (0, 0, 0))], '', 4.0, BOX)[0] is False


def test_placement_check_requires_gripper_state():
    assert dependency_problem(True, 'bool')
    assert dependency_problem(True, 'state') == ''
    assert dependency_problem(False, 'bool') == ''


def test_stop_slots_spread_pouches_on_one_table_and_keep_a_retry_in_its_slot():
    """재범 9/25: 병실 묶음 3 봉투가 C 테이블 하나에 겹치지 않게 놓인다. 침상(정거장당 1)은 늘 가운데다."""
    slots = placement.StopSlots()
    assert slots.index_for('deck_slot_0', 'ord-0005', deck=True) == 0
    got = [slots.index_for('station_d/cabinet', order, deck=False) for order in ('ord-0005', 'ord-0006', 'ord-0007')]
    assert got == [0, 1, 2]
    assert slots.index_for('station_d/cabinet', 'ord-0006', deck=False) == 1        # 재시도는 같은 칸
    offsets = [placement.stop_slot_offset(i) for i in got]
    assert offsets == [0.0, placement.STOP_SLOT_SPACING, -placement.STOP_SLOT_SPACING]
    assert min(abs(a - b) for a in offsets for b in offsets if a != b) >= 0.15 - 1e-9   # 봉투 긴 변 0.10 + 틈 0.05
    assert slots.index_for('bed_a1/cabinet', 'ord-0001', deck=False) == 0         # 다른 정거장은 새로 센다
    slots.index_for('deck_slot_1', 'ord-0002', deck=True)
    assert slots.index_for('station_d/cabinet', 'ord-0013', deck=False) == 0       # 새 트립
