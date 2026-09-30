from rokey_p3_manipulation.pick_permission import (
    OUTCOME_NOT_DETECTED,
    OUTCOME_OK,
    OUTCOME_QR_MISMATCH,
    OUTCOMES,
    arm_motion_allowed,
    belt_pick_allowed,
    deck_pick_allowed,
    pick_allowed,
    select_detection,
)


def test_all_three_conditions_required():
    assert pick_allowed(True, True, True)
    assert not pick_allowed(False, True, True)
    assert not pick_allowed(True, False, True)
    assert not pick_allowed(True, True, False)


def test_belt_guard_needs_stop_at_end_and_the_same_order():
    assert belt_pick_allowed(True, True, 'ord-0001', 'ord-0001')
    assert not belt_pick_allowed(True, False, 'ord-0001', 'ord-0001')
    assert not belt_pick_allowed(False, True, 'ord-0001', 'ord-0001')
    assert not belt_pick_allowed(True, True, 'ord-0002', 'ord-0001')
    assert not belt_pick_allowed(True, True, '', 'ord-0001')
    assert not belt_pick_allowed(True, True, 'ord-0001', '')


def test_unknown_is_not_permission():
    # 상태 토픽이 1.0 s 안 오면 노드가 None 을 넘긴다. None 은 허가가 아니다.
    assert not belt_pick_allowed(None, True, 'ord-0001', 'ord-0001')
    assert not belt_pick_allowed(True, None, 'ord-0001', 'ord-0001')
    assert not deck_pick_allowed(None)
    assert deck_pick_allowed(True)
    assert not deck_pick_allowed(False)
    # ScanTag 도 같은 공통 조건을 본다.
    assert not arm_motion_allowed(None)
    assert arm_motion_allowed(True)


def test_select_detection_picks_the_goal_order():
    assert select_detection(['ord-0002', 'ord-0001'], 'ord-0001') == (1, OUTCOME_OK)
    assert select_detection(['ord-0001', 'ord-0001'], 'ord-0001') == (0, OUTCOME_OK)


def test_select_detection_separates_mismatch_from_no_read():
    assert select_detection(['ord-0002'], 'ord-0001') == (None, OUTCOME_QR_MISMATCH)
    assert select_detection(['', ''], 'ord-0001') == (None, OUTCOME_NOT_DETECTED)
    assert select_detection([], 'ord-0001') == (None, OUTCOME_NOT_DETECTED)


def test_outcome_list_is_the_contract_list():
    assert OUTCOMES == ('ok', 'not_detected', 'qr_mismatch', 'grasp_failed',
                        'dropped', 'timeout', 'rejected_interlock')
