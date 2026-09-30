from rokey_p3_orchestrator import terminal_states as ts


def test_four_terminal_states_match_scenario():
    assert ts.TERMINAL_STATES == ('SUCCESS', 'HOLD_RETURN', 'ABORT', 'TIMEOUT')


def test_is_terminal():
    assert ts.is_terminal('SUCCESS')
    assert ts.is_terminal('HOLD_RETURN')
    assert not ts.is_terminal('ACCEPTED')
    assert not ts.is_terminal('')


def test_trip_succeeded_requires_every_order():
    assert ts.trip_succeeded(['SUCCESS', 'SUCCESS'])
    assert not ts.trip_succeeded(['SUCCESS', 'HOLD_RETURN'])
    assert not ts.trip_succeeded([])
