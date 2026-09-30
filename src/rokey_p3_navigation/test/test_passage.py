import math

import pytest

from rokey_p3_navigation.passage import (
    BLOCKED,
    PASSABLE,
    UNKNOWN,
    Circle,
    Rectangle,
    check_passage,
    swept_width,
)

# 아래 수치는 전부 식을 확인하려는 산술 예다. 로봇·문의 실측값이 아니다.
BOX = Rectangle(width=0.5, length=0.8)


def test_straight_through_uses_the_width():
    assert swept_width(BOX, 0.0) == pytest.approx(0.5)


def test_sideways_uses_the_length():
    assert swept_width(BOX, math.pi / 2) == pytest.approx(0.8)


def test_turned_box_follows_the_plan_formula():
    yaw = math.radians(30)
    expected = 0.5 * math.cos(yaw) + 0.8 * math.sin(yaw)
    assert swept_width(BOX, yaw) == pytest.approx(expected)
    assert swept_width(BOX, -yaw) == pytest.approx(expected)


def test_circle_does_not_depend_on_yaw():
    for yaw in (0.0, 0.7, math.pi / 2, -2.0):
        assert swept_width(Circle(0.3), yaw) == pytest.approx(0.6)


def test_passable_reports_required_width_and_no_shortfall():
    result = check_passage(BOX, 0.0, margin=0.1, error_budget=0.05, door_width=0.9)
    assert result.verdict == PASSABLE
    assert result.required == pytest.approx(0.75)
    assert result.shortfall == 0.0
    assert result.reason is None


def test_blocked_reports_the_shortfall():
    result = check_passage(BOX, math.pi / 2, margin=0.1, error_budget=0.05, door_width=0.9)
    assert result.verdict == BLOCKED
    assert result.required == pytest.approx(1.05)
    assert result.shortfall == pytest.approx(0.15)


def test_exact_fit_is_blocked():
    # fail-closed: 필요한 폭 == 문 폭이면 막는다. 이진수로 정확한 값만 써서 반올림이 끼지 않게 했다.
    result = check_passage(Rectangle(0.5, 0.5), 0.0, margin=0.125, error_budget=0.25, door_width=1.0)
    assert result.required == 1.0
    assert result.verdict == BLOCKED
    assert result.shortfall == 0.0


def test_plan_example_radius_0_6_does_not_fit_a_0_9_door():
    # 계획 문서(mock-hospital-world-integration-plan.md 8절)의 산술 예이며 실측값이 아니다.
    # 문 0.9 m, 양측 여유 0.15 m 면 불확실성 제외 폭은 0.6 m 이하다. 현 robot_radius 0.6 m(지름 1.2 m)로는 불가.
    # 오차 예산은 0 이하가 UNKNOWN 이라 가장 작은 양수 쪽을 넣었다. 어떤 양수여도 결과는 같다.
    result = check_passage(Circle(0.6), 0.0, margin=0.15, error_budget=1e-9, door_width=0.9)
    assert result.verdict == BLOCKED
    assert result.shortfall == pytest.approx(0.6)


@pytest.mark.parametrize('footprint', [
    None, (0.5, 0.8), Rectangle(0.0, 0.8), Rectangle(0.5, -0.1), Rectangle(float('nan'), 0.8),
    Rectangle(0.5, float('inf')), Rectangle(True, 0.8), Circle(0.0), Circle(None),
])
def test_bad_footprint_is_unknown(footprint):
    result = check_passage(footprint, 0.0, margin=0.1, error_budget=0.05, door_width=0.9)
    assert result.verdict == UNKNOWN
    assert result.required is None and result.shortfall is None
    assert 'footprint' in result.reason


@pytest.mark.parametrize('name', ['margin', 'error_budget', 'door_width'])
@pytest.mark.parametrize('bad', [None, 0.0, -0.1, float('nan'), float('inf'), '0.1'])
def test_missing_or_non_positive_dimension_is_unknown(name, bad):
    values = {'margin': 0.1, 'error_budget': 0.05, 'door_width': 0.9}
    values[name] = bad
    result = check_passage(BOX, 0.0, **values)
    assert result.verdict == UNKNOWN
    assert result.reason.startswith(name)


@pytest.mark.parametrize('yaw', [None, float('nan'), float('inf')])
def test_non_finite_yaw_is_unknown(yaw):
    result = check_passage(BOX, yaw, margin=0.1, error_budget=0.05, door_width=0.9)
    assert result.verdict == UNKNOWN
    assert result.reason.startswith('yaw')


def test_there_is_no_inflation_input():
    with pytest.raises(TypeError):
        check_passage(BOX, 0.0, margin=0.1, error_budget=0.05, door_width=0.9, inflation=0.3)
