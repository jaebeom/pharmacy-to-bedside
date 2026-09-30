from pathlib import Path

import yaml

from rokey_p3_navigation.readiness import (
    COORDINATES_UNVERIFIED,
    DEFAULT_REQUIRED_ZONES,
    check_zones,
    is_ready,
)
from rokey_p3_navigation.zones import load_zones, parse_zones

SKELETON = Path(__file__).resolve().parents[2] / 'rokey_p3_description' / 'config' / 'zones.yaml'

READY = """
frame: map
zones:
  load:   {kind: load, x: 1.0, y: 2.0, yaw: 0.5, tol_xy: 0.05, tol_yaw: 0.05}
  dock_1: {kind: dock, x: 3.0, y: 4.0, yaw: 0.0, tol_xy: 0.10, tol_yaw: 0.10}
  bed_a1: {kind: bed, x: 5.0, y: 6.0, yaw: 0.0, tol_xy: 0.05, tol_yaw: 0.05,
           cabinet: {x: 5.1, y: 6.1, z: 0.8, yaw: 1.57},
           tag: {x: 5.2, y: 6.2, z: 1.0, yaw: 0.0}}
pharmacy:
  belt_end: {x: 7.0, y: 8.0, z: 0.7, yaw: 0.0}
"""


def parse(text):
    return parse_zones(yaml.safe_load(text))


def blocking(text, required=DEFAULT_REQUIRED_ZONES):
    return check_zones(parse(text), required).blocking


def test_a_filled_file_is_ready():
    assert blocking(READY) == []
    assert is_ready(parse(READY))


def test_default_required_zones_are_load_and_dock_1():
    assert DEFAULT_REQUIRED_ZONES == ('load', 'dock_1')


def test_zero_coordinates_are_not_a_reason():
    text = READY.replace('x: 1.0, y: 2.0, yaw: 0.5', 'x: 0.0, y: 0.0, yaw: 0.0')
    assert blocking(text) == []


def test_coordinates_being_set_is_always_reported_unverified():
    assert check_zones(parse(READY)).unverified == [COORDINATES_UNVERIFIED]


def test_zero_tolerance_blocks():
    reasons = blocking(READY.replace('tol_xy: 0.10', 'tol_xy: 0.0'))
    assert reasons == ['zones.dock_1.tol_xy 이 양의 유한값이 아니다: 0.0']


def test_negative_tolerance_blocks():
    reasons = blocking(READY.replace('tol_yaw: 0.10', 'tol_yaw: -0.1'))
    assert reasons == ['zones.dock_1.tol_yaw 이 양의 유한값이 아니다: -0.1']


def test_infinite_tolerance_blocks():
    assert blocking(READY.replace('tol_xy: 0.10', 'tol_xy: .inf'))


def test_nan_coordinate_blocks():
    reasons = blocking(READY.replace('x: 3.0', 'x: .nan'))
    assert len(reasons) == 1 and reasons[0].startswith('zones.dock_1.x ')


def test_nan_cabinet_and_pharmacy_poses_block():
    text = READY.replace('z: 0.8', 'z: .nan').replace('z: 0.7', 'z: -.inf')
    reasons = blocking(text)
    assert any(reason.startswith('zones.bed_a1.cabinet.z ') for reason in reasons)
    assert any(reason.startswith('pharmacy.belt_end.z ') for reason in reasons)


def test_missing_required_zone_blocks():
    assert blocking(READY, required=('load', 'dock_2')) == ['필수 zone dock_2 가 없다']


def test_required_zones_come_from_the_caller():
    text = READY.replace('  dock_1:', '  dock_2:')
    assert blocking(text) == ['필수 zone dock_1 가 없다']
    assert blocking(text, required=('load', 'dock_2')) == []
    assert blocking(text, required=()) == []


def test_frame_other_than_map_blocks():
    assert blocking(READY.replace('frame: map', 'frame: odom')) == ["frame 이 map 가 아니다: 'odom'"]


def test_every_reason_is_collected_not_just_the_first():
    text = READY.replace('tol_xy: 0.05', 'tol_xy: 0.0').replace('frame: map', 'frame: world')
    assert len(blocking(text, required=('load', 'dock_1', 'station_a'))) == 4


def test_the_current_skeleton_is_not_ready():
    """현 상태 관측: zones.yaml 의 공차가 전부 0 이라 막힌다. 값을 채우는 것은 이 시험의 일이 아니다."""
    reasons = check_zones(load_zones(SKELETON)).blocking
    assert reasons
    assert all('tol_' in reason for reason in reasons)
