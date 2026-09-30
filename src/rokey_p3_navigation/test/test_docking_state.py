"""docking_state.py L1. 계약 v1 11.6 `DockingState` 규칙. 수치는 판정을 확인하려는 값이며 실측이 아니다."""

import math

import pytest

from rokey_p3_navigation.docking_state import DOCKED, NOT_DOCKED, UNKNOWN, SeqCounter, judge
from rokey_p3_navigation.zones import Zone

LOAD = Zone('load', 'load', 1.0, 2.0, 0.0, 0.05, 0.05, None, None)
GOOD = {'epoch_known': True, 'goal_active': False, 'zone': LOAD, 'pose': (1.01, 2.0, 0.01),
        'odom_age_s': 0.1, 'odom_timeout_s': 1.0, 'amcl_age_s': 0.2, 'amcl_max_age_s': 0.5}


def with_(**changes):
    return judge(**{**GOOD, **changes})


def test_inside_tolerance_is_docked_with_errors():
    result = with_()
    assert result.docking == DOCKED
    assert result.error_xy == pytest.approx(0.01)
    assert result.error_yaw == pytest.approx(0.01)
    assert result.reason is None


def test_outside_tolerance_is_not_docked():
    assert with_(pose=(1.2, 2.0, 0.0)).docking == NOT_DOCKED
    assert with_(pose=(1.0, 2.0, 0.2)).docking == NOT_DOCKED


def test_before_first_reset_done_is_unknown_even_inside():
    assert with_(epoch_known=False).docking == UNKNOWN


def test_active_goal_is_not_docked_even_inside():
    assert with_(goal_active=True).docking == NOT_DOCKED


def test_no_target_zone_is_unknown():
    result = with_(zone=None)
    assert result.docking == UNKNOWN and math.isnan(result.error_xy)


@pytest.mark.parametrize('tol', [0.0, -0.1, float('nan'), float('inf')])
def test_zone_not_ready_is_unknown_not_not_docked(tol):
    # docking.docked 는 NaN 공차에 거짓(NOT_DOCKED)을 낸다. 여기서는 readiness 기준으로 UNKNOWN 이다.
    assert with_(zone=LOAD._replace(tol_xy=tol)).docking == UNKNOWN


def test_zero_coordinates_are_a_valid_zone():
    origin = LOAD._replace(x=0.0, y=0.0, yaw=0.0)
    assert with_(zone=origin, pose=(0.0, 0.0, 0.0)).docking == DOCKED


def test_missing_tf_is_unknown():
    assert with_(pose=None).docking == UNKNOWN


@pytest.mark.parametrize('age', [None, 1.01, float('nan')])
def test_stale_odom_is_unknown(age):
    assert with_(odom_age_s=age).docking == UNKNOWN


@pytest.mark.parametrize('threshold', [None, 0.0, -1.0, float('nan'), float('inf')])
def test_undecided_amcl_threshold_is_unknown(threshold):
    result = with_(amcl_max_age_s=threshold)
    assert result.docking == UNKNOWN
    assert result.reason == 'AMCL 신선도 문턱 미정(L3 측정 뒤)'


@pytest.mark.parametrize('age', [None, 0.51, float('nan')])
def test_stale_amcl_is_unknown(age):
    assert with_(amcl_age_s=age).docking == UNKNOWN


def test_boundary_is_inside():
    # 공차와 같은 오차는 안이다(docking.docked 와 같은 <=). 이진수로 정확한 값만 써서 반올림이 끼지 않게 했다.
    assert with_(zone=LOAD._replace(tol_xy=0.0625), pose=(1.0625, 2.0, 0.0)).docking == DOCKED


def test_seq_moves_only_when_odom_stamp_moves_forward():
    seq = SeqCounter()
    assert seq.advance(1, 10.0) == 1
    assert seq.advance(1, 10.0) == 1
    assert seq.advance(1, 9.9) == 1
    assert seq.advance(1, None) == 1
    assert seq.advance(1, 10.1) == 2


def test_seq_restarts_on_a_new_epoch():
    seq = SeqCounter()
    seq.advance(1, 10.0)
    seq.advance(1, 11.0)
    assert seq.advance(2, 1.0) == 1
