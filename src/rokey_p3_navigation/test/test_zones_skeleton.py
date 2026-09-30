"""zones.yaml 뼈대를 zones.py 가 그대로 받는가. 계약 v1 3절.

파일은 rokey_p3_description/config/zones.yaml 하나다(simulation 소유).
값은 9/17-9/19 에 채우므로 여기서는 **키와 형식만** 본다.
"""

from pathlib import Path

from rokey_p3_navigation.zones import is_zone_id, load_zones

SKELETON = Path(__file__).resolve().parents[2] / 'rokey_p3_description' / 'config' / 'zones.yaml'
#: 계약 3절이 zones_tf 의 작성으로 정한 조제실 고정 프레임.
PHARMACY_FRAMES = ('belt_end', 'dispenser_slot_a', 'dispenser_slot_b', 'shelf')


def test_the_skeleton_is_where_the_contract_says():
    assert SKELETON.is_file(), f'{SKELETON} 가 없다'


def test_the_skeleton_parses():
    assert load_zones(SKELETON).frame == 'map'


def test_every_zone_id_matches_the_rule():
    for zone_id in load_zones(SKELETON).zones:
        assert is_zone_id(zone_id), zone_id


def test_every_zone_has_pose_and_tolerance():
    for zone_id, zone in load_zones(SKELETON).zones.items():
        assert zone.kind, zone_id
        for value in (zone.x, zone.y, zone.yaw, zone.tol_xy, zone.tol_yaw):
            assert isinstance(value, float), zone_id


def test_bed_and_station_carry_cabinet_and_tag():
    zones = load_zones(SKELETON).zones
    for zone in zones.values():
        if zone.kind in ('bed', 'station'):
            assert zone.cabinet is not None, zone.zone_id
            assert zone.tag is not None, zone.zone_id


def test_load_and_dock_are_there_for_the_pharmacy_leg():
    zones = load_zones(SKELETON).zones
    assert 'load' in zones
    assert any(zone.kind == 'dock' for zone in zones.values())


def test_pharmacy_frames_are_the_four_the_contract_names():
    assert tuple(sorted(load_zones(SKELETON).pharmacy)) == PHARMACY_FRAMES
