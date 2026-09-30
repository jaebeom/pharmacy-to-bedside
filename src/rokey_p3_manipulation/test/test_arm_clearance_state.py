"""L1: ArmClearance 발행 규칙(순수). epoch·seq·GripperState 신선도. 계약 v1 11.6절."""

from rokey_p3_manipulation.arm_clearance_state import GripperView, StampSeq, publish_epoch

HELD, RELEASED, UNKNOWN = 2, 1, 0


def test_epoch_is_unknown_before_any_event():
    assert publish_epoch(0, 0, False).epoch is None
    assert publish_epoch(None, 0, False).epoch is None


def test_epoch_is_one_before_any_reset_and_the_last_reset_done_after():
    assert publish_epoch(1, 0, False) == (1, False, '')
    assert publish_epoch(3, 3, False) == (3, False, '')


def test_reset_begin_does_not_raise_the_epoch():
    # RESET_BEGIN(4) 을 받아 본 epoch 는 4 지만 RESET_DONE 은 3 까지다. barrier 중이다.
    view = publish_epoch(4, 3, True)
    assert view.epoch == 3 and view.fenced and view.reason


def test_seq_moves_only_when_the_stamp_moves_forward():
    seq = StampSeq()
    assert seq.next(10.0, 1) == 1
    assert seq.next(10.0, 1) == 1                    # 같은 표본 반복
    assert seq.next(9.5, 1) == 1                     # 역행
    assert seq.next(None, 1) == 1                    # stamp 없음
    assert seq.next(float('nan'), 1) == 1
    assert seq.next(10.1, 1) == 2
    assert seq.next(0.5, 2) == 1                     # 새 epoch 는 다시 센다(리셋 뒤 sim time 이 작아도)


def gripper():
    return GripperView(1.0, HELD, RELEASED)


def test_gripper_holding_follows_a_fresh_state_of_the_same_epoch():
    view = gripper()
    view.update(epoch=2, seq=10, state=HELD, wall_now=100.0)
    assert view.holding(2, 100.5) == (True, '')
    view.update(epoch=2, seq=11, state=RELEASED, wall_now=100.6)
    assert view.holding(2, 100.7) == (False, '')


def test_gripper_unknown_cases():
    assert gripper().holding(1, 0.0)[0] is None                         # 받은 적 없음
    view = gripper()
    view.update(epoch=1, seq=5, state=HELD, wall_now=10.0)
    assert view.holding(2, 10.1)[0] is None                            # 다른 epoch
    assert view.holding(1, 11.5)[0] is None                            # 1.0 s 넘게 무수신
    view.update(epoch=1, seq=6, state=UNKNOWN, wall_now=12.0)
    assert view.holding(1, 12.1)[0] is None                            # state UNKNOWN


def test_gripper_repeating_the_same_seq_goes_stale():
    view = gripper()
    view.update(epoch=1, seq=5, state=HELD, wall_now=10.0)
    for step in range(1, 12):
        view.update(epoch=1, seq=5, state=HELD, wall_now=10.0 + 0.1 * step)   # 계속 오지만 seq 가 안 는다
    holding, reason = view.holding(1, 11.1)
    assert holding is None and 'seq' in reason


def test_gripper_clear_forgets_everything():
    view = gripper()
    view.update(epoch=1, seq=5, state=HELD, wall_now=10.0)
    view.clear()
    assert view.holding(1, 10.1)[0] is None


# GripperCommand seq 규칙(계약 11.6) ------------------------------------------------

def test_command_seq_starts_at_one_per_epoch_and_on_reset():
    from rokey_p3_manipulation.arm_clearance_state import CommandSeq
    seq = CommandSeq()
    assert [seq.next(1), seq.next(1), seq.next(1)] == [1, 2, 3]
    assert seq.next(2) == 1                          # 새 epoch
    seq.reset()                                      # RESET_DONE
    assert seq.next(2) == 1


def test_command_result_follows_last_applied_and_state():
    from rokey_p3_manipulation import arm_clearance_state as cs
    view = gripper()
    view.update(epoch=1, seq=1, state=HELD, wall_now=10.0, last_applied=0)
    assert view.command_result(1, 10.1, 2, True)[0] == cs.PENDING           # 명령 전의 HELD 는 파지가 아니다
    view.update(epoch=1, seq=2, state=HELD, wall_now=10.2, last_applied=2)
    assert view.command_result(1, 10.3, 2, True) == (cs.CONFIRMED, '')      # 흡착 확인
    view.update(epoch=1, seq=3, state=RELEASED, wall_now=10.4, last_applied=2)
    assert view.command_result(1, 10.5, 2, True) == (cs.CONTRADICTED, 'RELEASED')   # 적용 뒤 놓침
    view.update(epoch=1, seq=4, state=RELEASED, wall_now=10.6, last_applied=3)
    assert view.command_result(1, 10.7, 3, False) == (cs.CONFIRMED, '')     # 해제 확인
    view.update(epoch=1, seq=5, state=HELD, wall_now=10.8, last_applied=4)
    assert view.command_result(1, 10.9, 4, False) == (cs.CONTRADICTED, 'HELD')      # 열었는데 쥐고 있다


def test_command_result_unknown_cases():
    from rokey_p3_manipulation import arm_clearance_state as cs
    view = gripper()
    assert view.command_result(1, 0.0, 1, True)[0] == cs.UNKNOWN            # 받은 적 없음
    view.update(epoch=1, seq=1, state=HELD, wall_now=10.0, last_applied=1)
    assert view.command_result(1, 10.1, None, True)[0] == cs.UNKNOWN        # epoch 없이 명령을 못 냈다
    assert view.command_result(2, 10.1, 1, True)[0] == cs.UNKNOWN           # 다른 epoch
    assert view.command_result(1, 11.5, 1, True)[0] == cs.UNKNOWN           # 오래됨
    view.update(epoch=1, seq=2, state=UNKNOWN, wall_now=12.0, last_applied=1)
    assert view.command_result(1, 12.1, 1, True)[0] == cs.UNKNOWN           # state UNKNOWN
