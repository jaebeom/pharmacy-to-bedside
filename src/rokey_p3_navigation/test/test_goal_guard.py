import pytest

from rokey_p3_navigation.goal_guard import (
    CANCEL,
    CANCEL_WAIT_S,
    CANCELED,
    IGNORED,
    NOTHING,
    RESET,
    TIMEOUT,
    TRACK,
    WAIT,
    GoalGuard,
    Token,
)


def running(guard=None):
    """보내서 수락까지 된 goal 하나."""
    guard = guard or GoalGuard()
    token = guard.begin()
    assert guard.should_send(token)
    assert guard.on_accepted(token) == TRACK
    return guard, token


def test_cancel_wait_is_the_contract_value():
    # 계약 v1 7절 cancel 종결 대기 10 s(wall) 를 옮긴 값이다. 새 합격선이 아니다.
    assert CANCEL_WAIT_S == 10.0


@pytest.mark.parametrize('bad', [0.0, -1.0, float('nan'), float('inf')])
def test_cancel_wait_must_be_positive_and_finite(bad):
    with pytest.raises(ValueError):
        GoalGuard(cancel_wait_s=bad)


def test_one_goal_at_a_time_and_seq_grows():
    guard = GoalGuard()
    first = guard.begin()
    assert first == Token(None, 1)
    assert guard.begin() is None
    guard.finish(first)
    assert guard.begin() == Token(None, 2)


def test_normal_goal_finishes_without_reason():
    guard, token = running()
    assert guard.on_result(token)
    assert guard.finish(token) is None
    assert guard.token is None


# -- 보내기 전에 닫힘 (결함 후보 F1: 서버 대기 중 리셋·취소) --------------------

def test_reset_before_send_means_do_not_send():
    guard = GoalGuard()
    token = guard.begin()
    assert guard.on_reset_done(1, now=0.0) == NOTHING
    assert not guard.should_send(token)
    assert guard.finish(token) == RESET


def test_cancel_before_send_means_do_not_send():
    guard = GoalGuard()
    token = guard.begin()
    assert guard.close(CANCELED, now=0.0) == NOTHING
    assert not guard.should_send(token)
    assert guard.finish(token) == CANCELED


# -- 늦은 수락 -------------------------------------------------------------------

def test_goal_accepted_late_after_reset_is_canceled():
    guard = GoalGuard()
    token = guard.begin()
    assert guard.should_send(token)
    assert guard.on_reset_done(1, now=0.0) == WAIT
    assert guard.on_accepted(token) == CANCEL


def test_acceptance_of_a_finished_goal_is_canceled():
    guard = GoalGuard()
    old = guard.begin()
    guard.should_send(old)
    guard.close(TIMEOUT, now=0.0)
    guard.finish(old)
    new = guard.begin()
    guard.should_send(new)
    assert guard.on_accepted(old) == CANCEL
    assert guard.on_accepted(new) == TRACK


def test_acceptance_from_the_previous_epoch_is_canceled():
    guard = GoalGuard()
    old = guard.begin()
    guard.should_send(old)
    guard.on_reset_done(1, now=0.0)
    guard.finish(old)
    new = guard.begin()
    assert new.epoch == 1
    assert guard.on_accepted(old) == CANCEL


# -- 닫기와 종결 대기 (결함 후보 F2: cancel 무응답) ------------------------------

def test_closing_an_accepted_goal_sends_cancel():
    guard, _ = running()
    assert guard.close(TIMEOUT, now=0.0) == CANCEL


def test_no_answer_to_cancel_still_finishes_after_ten_seconds():
    guard, token = running()
    guard.close(CANCELED, now=100.0)
    assert not guard.expired(now=109.9)
    assert guard.expired(now=100.0 + CANCEL_WAIT_S)
    assert guard.finish(token) == CANCELED
    assert guard.begin() is not None


def test_closing_again_keeps_the_first_reason_and_deadline():
    guard, token = running()
    guard.close(TIMEOUT, now=0.0)
    assert guard.close(CANCELED, now=5.0) == NOTHING
    assert guard.on_reset_done(1, now=9.0) == NOTHING
    assert guard.expired(now=10.0)
    assert guard.finish(token) == TIMEOUT


def test_nothing_to_close_when_idle():
    guard = GoalGuard()
    assert guard.close(CANCELED, now=0.0) == NOTHING
    assert not guard.expired(now=1e9)


# -- 결과 -----------------------------------------------------------------------

def test_result_of_another_token_is_dropped():
    guard, token = running()
    assert not guard.on_result(Token(token.epoch, token.seq + 1))
    assert not guard.on_result(Token(0, token.seq))
    assert guard.on_result(token)


def test_result_before_send_is_dropped():
    guard = GoalGuard()
    token = guard.begin()
    assert not guard.on_result(token)


def test_finish_of_another_token_does_nothing():
    guard, token = running()
    assert guard.finish(Token(None, 99)) is None
    assert guard.token == token


# -- RESET_DONE epoch -------------------------------------------------------------

def test_older_and_duplicate_reset_done_are_ignored():
    guard = GoalGuard()
    assert guard.on_reset_done(3, now=0.0) == NOTHING
    assert guard.on_reset_done(3, now=1.0) == IGNORED
    assert guard.on_reset_done(2, now=2.0) == IGNORED
    assert guard.epoch == 3


def test_ignored_reset_done_does_not_close_the_goal():
    guard = GoalGuard()
    guard.on_reset_done(3, now=0.0)
    _, token = running(guard)
    assert guard.on_reset_done(2, now=1.0) == IGNORED
    assert guard.reason is None
    assert guard.on_result(token)


def test_reset_done_closes_the_running_goal():
    guard, token = running()
    assert guard.on_reset_done(1, now=0.0) == CANCEL
    assert guard.reason == RESET
    assert guard.finish(token) == RESET
