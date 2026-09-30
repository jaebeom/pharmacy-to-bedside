"""routes L1. 월드별 고정 경로 파일의 형식 검사. 값은 형식을 확인하려는 예다."""

import pytest
import yaml

from rokey_p3_navigation.routes import RoutesError, departure_point, has_pair, parse_routes, waypoints
from rokey_p3_navigation.zones import parse_zones

ZONES = parse_zones(yaml.safe_load("""
frame: map
zones:
  load:   {kind: load, x: 0.0, y: 0.0, yaw: 0.0, tol_xy: 0.05, tol_yaw: 0.05}
  dock_1: {kind: dock, x: -1.0, y: 0.0, yaw: 0.0, tol_xy: 0.1, tol_yaw: 0.1}
  bed_a1: {kind: bed, x: 5.0, y: 2.0, yaw: 1.57, tol_xy: 0.05, tol_yaw: 0.05,
           cabinet: {x: 5.0, y: 2.5, z: 0.8, yaw: 0.0},
           tag: {x: 5.0, y: 2.5, z: 1.0, yaw: 0.0}}
"""))

ROUTES = """
schema_version: 1
frame: map
routes:
  - {from: dock_1, to: load, waypoints: [[-0.5, 0.0], [0.0, 0.0]]}
  - {from: load, to: bed_a1, waypoints: [[2.0, 0.0], [4.0, 1.0]]}
  - {from: bed_a1, to: dock_1, waypoints: []}
"""


def parse(text=ROUTES):
    return parse_routes(yaml.safe_load(text), ZONES)


def rejects(text, fragment):
    with pytest.raises(RoutesError) as error:
        parse(text)
    assert fragment in str(error.value)


def test_parses_pairs_and_points():
    routes = parse()
    assert routes.frame == 'map'
    assert waypoints(routes, 'load', 'bed_a1') == ((2.0, 0.0), (4.0, 1.0))


def test_empty_waypoints_means_straight_there():
    assert waypoints(parse(), 'bed_a1', 'dock_1') == ()


def test_unknown_pair_is_empty_not_an_error():
    assert waypoints(parse(), 'load', 'dock_1') == ()


def test_no_routes_file_is_empty():
    assert waypoints(None, 'load', 'bed_a1') == ()


def test_integers_become_floats():
    routes = parse(ROUTES.replace('[[2.0, 0.0]', '[[2, 0]'))
    assert waypoints(routes, 'load', 'bed_a1')[0] == (2.0, 0.0)


def test_direction_matters():
    routes = parse()
    assert waypoints(routes, 'dock_1', 'load') and not waypoints(routes, 'load', 'dock_1')


def test_reject_unknown_zone():
    rejects(ROUTES.replace('to: bed_a1', 'to: bed_a9'), '없는 zone')


def test_reject_same_from_and_to():
    rejects(ROUTES.replace('from: load, to: bed_a1', 'from: load, to: load'), 'from 과 to 가 같다')


def test_reject_duplicate_pair():
    rejects(ROUTES + '  - {from: load, to: bed_a1, waypoints: []}\n', '같은 쌍이 두 번')


@pytest.mark.parametrize('point', ['[2.0]', '[2.0, 0.0, 1.0]', '[2.0, .nan]', '[2.0, "x"]',
                                   '[.inf, 0.0]'])
def test_reject_bad_point(point):
    with pytest.raises(RoutesError):
        parse(ROUTES.replace('[2.0, 0.0]', point))


def test_reject_wrong_schema_version():
    rejects(ROUTES.replace('schema_version: 1', 'schema_version: 2'), 'schema_version')


def test_reject_wrong_frame():
    rejects(ROUTES.replace('frame: map', 'frame: odom'), 'frame')


def test_reject_waypoints_that_are_not_a_list():
    rejects(ROUTES.replace('waypoints: []', 'waypoints: 3'), 'waypoints 는 목록')


# -- 빈 목록과 쌍 없음은 다르다 -----------------------------------------------------
# 가는 방법은 둘 다 "곧장" 이라 조용히 섞인다. 뜻은 반대다 — 따져 봤다 / 아무도 안 따져 봤다.
# 시뮬 9/21: 쌍 9개가 빠져 병동까지 대각선이 될 뻔했다. fleet 이 이 차이로 WARN 을 낸다.

def test_an_empty_list_is_recorded_as_a_pair():
    routes = parse()
    assert has_pair(routes, 'bed_a1', 'dock_1')          # 표에 `waypoints: []` 로 적혀 있다
    assert waypoints(routes, 'bed_a1', 'dock_1') == ()


def test_a_missing_pair_is_not_the_same_as_an_empty_list():
    routes = parse()
    assert not has_pair(routes, 'dock_1', 'bed_a1')      # 표에 없다
    assert waypoints(routes, 'dock_1', 'bed_a1') == ()   # 가는 방법은 같다


def test_without_a_routes_file_no_pair_is_recorded():
    assert not has_pair(None, 'dock_1', 'load')


def test_staging_point_is_the_last_waypoint_of_the_pair():
    """nav2_final_approach: Nav2 는 경로의 마지막 waypoint(접근점)까지 간다. 없으면 None(끝까지 Nav2)."""
    from rokey_p3_navigation.routes import Routes, staging_point
    routes = Routes('map', {('dock_1', 'bed_a1'): ((1.0, 0.0), (2.0, 0.5)), ('dock_1', 'load'): ()})
    assert staging_point(routes, 'dock_1', 'bed_a1') == (2.0, 0.5)
    assert staging_point(routes, 'dock_1', 'load') is None
    assert staging_point(routes, 'load', 'bed_a1') is None
    assert staging_point(None, 'dock_1', 'bed_a1') is None


# -- 떠날 때 접근점으로 물러나기(departure_point) ------------------------------------
# 9/24 10건: bed_b1 에서 bed_b2 로 떠나는 첫 움직임에 몸체가 D5 협탁 모서리에 닿았다.

DEPART_ROUTES = ROUTES + """  - {from: dock_1, to: bed_a1, waypoints: [[2.0, 0.0], [5.0, 1.7]]}
"""
BED = ZONES.zones['bed_a1']


def test_leaving_a_bed_backs_out_to_the_approach_point_of_the_way_in():
    routes = parse(DEPART_ROUTES)
    assert departure_point(routes, BED, 'dock_1', (5.0, 2.0, 1.57), 0.05) == (5.0, 1.7)


def test_no_back_out_when_not_standing_at_the_bed():
    routes = parse(DEPART_ROUTES)
    assert departure_point(routes, BED, 'dock_1', (4.0, 2.0, 1.57), 0.05) is None   # 실패·리셋 뒤 다른 자리
    assert departure_point(routes, BED, 'dock_1', None, 0.05) is None               # 자세 모름


def test_only_bed_and_dock_stops_back_out():
    routes = parse(DEPART_ROUTES)
    load = ZONES.zones['load']
    assert departure_point(routes, load, 'bed_a1', (0.0, 0.0, 0.0), 0.05) is None


def test_leaving_a_wall_dock_backs_out_before_turning_but_never_far():
    """회차77(6812ee5): 벽 앞 dock_1 에서 제자리로 돌다 ArmRiser 가 모듈에 닿았다. 도크도 접근점까지 물러난다."""
    dock = ZONES.zones['dock_1']
    base = ROUTES.replace("  - {from: bed_a1, to: dock_1, waypoints: []}\n", "")
    near = parse(base + f"  - {{from: bed_a1, to: dock_1, waypoints: [[3.0, 0.0], [{dock.x}, {dock.y - 0.4}]]}}\n")
    assert departure_point(near, dock, 'bed_a1', (dock.x, dock.y, dock.yaw), 0.05) == (dock.x, dock.y - 0.4)
    far = parse(base + f"  - {{from: bed_a1, to: dock_1, waypoints: [[{dock.x + 3.0}, {dock.y}]]}}\n")
    assert departure_point(far, dock, 'bed_a1', (dock.x, dock.y, dock.yaw), 0.05) is None   # 빈월드처럼 먼 마지막 점


def test_no_back_out_without_a_way_in_or_to_itself():
    assert departure_point(parse(), BED, 'dock_1', (5.0, 2.0, 1.57), 0.05) is None   # dock_1 → bed_a1 쌍 없음
    assert departure_point(parse(DEPART_ROUTES), BED, 'bed_a1', (5.0, 2.0, 1.57), 0.05) is None
    assert departure_point(None, BED, 'dock_1', (5.0, 2.0, 1.57), 0.05) is None
