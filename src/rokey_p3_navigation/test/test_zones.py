import pytest
import yaml

from rokey_p3_navigation.zones import ZonesError, is_zone_id, parse_zones

MINIMAL = """
frame: map
zones:
  load:   {kind: load, x: 1.0, y: 2.0, yaw: 0.5, tol_xy: 0.05, tol_yaw: 0.05}
  bed_a1: {kind: bed, x: 3.0, y: 4.0, yaw: 0.0, tol_xy: 0.05, tol_yaw: 0.05,
           cabinet: {x: 3.1, y: 4.1, z: 0.8, yaw: 1.57},
           tag: {x: 3.2, y: 4.2, z: 1.0, yaw: 0.0}}
pharmacy:
  belt_end: {x: 5.0, y: 6.0, z: 0.7, yaw: 0.0}
"""


def parse(text):
    return parse_zones(yaml.safe_load(text))


def test_candidate_zone_ids():
    for ok in ('pharm', 'load', 'dock_1', 'dock_5', 'ward_a', 'station_a', 'room_a1', 'bed_a1'):
        assert is_zone_id(ok), ok


def test_rejects_unknown_ids():
    for bad in ('', 'dock_0', 'Bed_A1', 'ward_1', 'bed_a', 'elevator'):
        assert not is_zone_id(bad), bad


def test_parses_frame_zones_and_pharmacy():
    zones = parse(MINIMAL)
    assert zones.frame == 'map'
    assert sorted(zones.zones) == ['bed_a1', 'load']
    assert zones.pharmacy['belt_end'].z == 0.7


def test_zone_fields_become_floats():
    load = parse(MINIMAL).zones['load']
    assert (load.kind, load.x, load.y, load.yaw) == ('load', 1.0, 2.0, 0.5)
    assert (load.tol_xy, load.tol_yaw) == (0.05, 0.05)
    assert load.zone_id == 'load'


def test_cabinet_and_tag_are_optional():
    zones = parse(MINIMAL)
    assert zones.zones['load'].cabinet is None
    assert zones.zones['load'].tag is None
    assert zones.zones['bed_a1'].cabinet.yaw == 1.57
    assert zones.zones['bed_a1'].tag.z == 1.0


def test_integer_values_are_accepted_as_numbers():
    zones = parse(MINIMAL.replace('x: 1.0', 'x: 1'))
    assert zones.zones['load'].x == 1.0


def test_zone_id_outside_the_rule_is_rejected():
    with pytest.raises(ZonesError):
        parse(MINIMAL.replace('  load:', '  elevator:'))


def test_missing_tolerance_is_rejected():
    with pytest.raises(ZonesError):
        parse(MINIMAL.replace(', tol_yaw: 0.05}', '}', 1))


def test_missing_frame_is_rejected():
    with pytest.raises(ZonesError):
        parse(MINIMAL.replace('frame: map', 'frame:'))


def test_empty_zones_is_rejected():
    with pytest.raises(ZonesError):
        parse('frame: map\nzones: {}\n')


def test_text_where_a_number_belongs_is_rejected():
    with pytest.raises(ZonesError):
        parse(MINIMAL.replace('x: 1.0', 'x: "1.0"'))


def test_pharmacy_pose_needs_z():
    with pytest.raises(ZonesError):
        parse(MINIMAL.replace('belt_end: {x: 5.0, y: 6.0, z: 0.7, yaw: 0.0}',
                              'belt_end: {x: 5.0, y: 6.0, yaw: 0.0}'))


def test_pharmacy_is_optional():
    zones = parse('frame: map\nzones:\n  load: {kind: load, x: 0.0, y: 0.0, yaw: 0.0, '
                  'tol_xy: 0.0, tol_yaw: 0.0}\n')
    assert zones.pharmacy == {}
