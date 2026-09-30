"""topology.py L1. 계약 v1 3절 "경유 zone 과 경로 토폴로지"의 규칙을 시험 사례로 옮겼다.

픽스처의 좌표·비용·폭은 규칙을 확인하려는 값이다. 병원 씬의 실측값이 아니다.
"""

import hashlib
import math

import pytest
import yaml

from rokey_p3_navigation.passage import Circle, Rectangle
from rokey_p3_navigation.topology import (
    STOP,
    TERMINAL,
    THROUGH,
    NoRoute,
    TopologyError,
    is_terminal,
    load_topology,
    parse_topology,
    plan,
)
from rokey_p3_navigation.zones import is_zone_id, parse_zones

ZONES = """
frame: map
zones:
  load:      {kind: load, x: 0.0, y: 0.0, yaw: 0.0, tol_xy: 0.05, tol_yaw: 0.05}
  dock_1:    {kind: dock, x: -1.0, y: 0.0, yaw: 0.0, tol_xy: 0.1, tol_yaw: 0.1}
  cp_a:      {kind: checkpoint, x: 5.0, y: 0.0, yaw: 0.0, tol_xy: 0.2, tol_yaw: 0.2}
  station_a: {kind: station, x: 6.0, y: 1.0, yaw: 0.0, tol_xy: 0.05, tol_yaw: 0.05,
              cabinet: {x: 6.0, y: 1.5, z: 0.8, yaw: 0.0}, tag: {x: 6.0, y: 1.5, z: 1.0, yaw: 0.0}}
  door_a1:   {kind: door, x: 7.0, y: 0.0, yaw: 0.0, tol_xy: 0.1, tol_yaw: 0.1}
  room_a1:   {kind: room, x: 8.0, y: 0.0, yaw: 0.0, tol_xy: 0.2, tol_yaw: 0.2}
  bed_a1:    {kind: bed, x: 9.0, y: 0.5, yaw: 0.0, tol_xy: 0.05, tol_yaw: 0.05,
              cabinet: {x: 9.0, y: 1.0, z: 0.8, yaw: 0.0}, tag: {x: 9.0, y: 1.0, z: 1.0, yaw: 0.0}}
  bed_a2:    {kind: bed, x: 9.0, y: -0.5, yaw: 0.0, tol_xy: 0.05, tol_yaw: 0.05,
              cabinet: {x: 9.0, y: -1.0, z: 0.8, yaw: 0.0}, tag: {x: 9.0, y: -1.0, z: 1.0, yaw: 0.0}}
  door_a2:   {kind: door, x: 5.0, y: 3.0, yaw: 0.0, tol_xy: 0.1, tol_yaw: 0.1}
  room_a2:   {kind: room, x: 5.0, y: 4.0, yaw: 0.0, tol_xy: 0.2, tol_yaw: 0.2}
  bed_a3:    {kind: bed, x: 5.0, y: 5.0, yaw: 0.0, tol_xy: 0.05, tol_yaw: 0.05,
              cabinet: {x: 5.5, y: 5.0, z: 0.8, yaw: 0.0}, tag: {x: 5.5, y: 5.0, z: 1.0, yaw: 0.0}}
"""

TOPOLOGY = """
schema_version: 1
wards:
  ward_a: {station: station_a, rooms: [room_a1, room_a2]}
rooms:
  room_a1: {ward: ward_a, beds: [bed_a1, bed_a2]}
  room_a2: {ward: ward_a, beds: [bed_a3]}
beds:
  bed_a1: {room: room_a1}
  bed_a2: {room: room_a1}
  bed_a3: {room: room_a2}
stops: [door_a1, door_a2]
edges:
  - {from: dock_1, to: load, cost: 1.0, bidirectional: true, clear_width_m: 2.0}
  - {from: dock_1, to: cp_a, cost: 12.0, bidirectional: true, clear_width_m: 2.0}
  - {from: load, to: cp_a, cost: 10.0, bidirectional: true, clear_width_m: null}
  - {from: cp_a, to: station_a, cost: 2.0, bidirectional: true, clear_width_m: 2.0}
  - {from: cp_a, to: door_a1, cost: 3.0, bidirectional: true, clear_width_m: 2.0}
  - {from: door_a1, to: room_a1, cost: 1.0, bidirectional: true, clear_width_m: 0.9}
  - {from: room_a1, to: bed_a1, cost: 1.0, bidirectional: true, clear_width_m: 2.0}
  - {from: room_a1, to: bed_a2, cost: 1.5, bidirectional: true, clear_width_m: 2.0}
  - {from: cp_a, to: door_a2, cost: 4.0, bidirectional: true, clear_width_m: 2.0}
  - {from: door_a2, to: room_a2, cost: 1.0, bidirectional: true, clear_width_m: 0.9}
  - {from: room_a2, to: bed_a3, cost: 1.0, bidirectional: true, clear_width_m: 2.0}
"""

ZONES_DOC = parse_zones(yaml.safe_load(ZONES))
SMALL = {'footprint': Rectangle(0.5, 0.7), 'margin': 0.1, 'error_budget': 0.05}


def topo(text=TOPOLOGY, **kwargs):
    return parse_topology(yaml.safe_load(text), ZONES_DOC, **kwargs)


def measured(text=TOPOLOGY):
    """폭이 전부 잰 값인 판."""
    return text.replace('clear_width_m: null', 'clear_width_m: 2.0')


def zone_ids(route):
    return [zone_id for zone_id, _ in route.stops]


def rejects(text, fragment):
    with pytest.raises(TopologyError) as error:
        topo(text)
    assert fragment in str(error.value)


# -- zone id 규칙 -----------------------------------------------------------------

def test_door_and_checkpoint_ids_are_zone_ids():
    for ok in ('door_a1', 'door_b12', 'cp_a'):
        assert is_zone_id(ok), ok
    for bad in ('door_a', 'door_1', 'cp_1', 'cp_ab', 'Door_a1'):
        assert not is_zone_id(bad), bad


def test_only_load_dock_bed_station_are_terminal():
    assert all(is_terminal(z) for z in ('load', 'dock_1', 'bed_a1', 'station_a'))
    assert not any(is_terminal(z) for z in ('door_a1', 'cp_a', 'room_a1', 'ward_a', 'pharm'))


# -- 로드 ---------------------------------------------------------------------------

def test_fixture_loads_but_is_not_ready_without_manifest():
    topology = topo()
    assert not topology.ready
    assert topology.reasons == ['manifest 없음 — map·zones·topology 가 같은 묶음인지 모른다']


def test_manifest_with_matching_hashes_makes_it_ready(tmp_path):
    zones_file, topology_file = tmp_path / 'zones.yaml', tmp_path / 'hospital_topology.yaml'
    zones_file.write_text(ZONES, encoding='utf-8')
    topology_file.write_text(TOPOLOGY, encoding='utf-8')
    manifest = {'zones_sha256': hashlib.sha256(ZONES.encode()).hexdigest(),
                'topology_sha256': hashlib.sha256(TOPOLOGY.encode()).hexdigest()}
    assert load_topology(topology_file, ZONES_DOC, zones_file, manifest).ready


def test_manifest_hash_mismatch_is_rejected(tmp_path):
    zones_file, topology_file = tmp_path / 'zones.yaml', tmp_path / 'hospital_topology.yaml'
    zones_file.write_text(ZONES, encoding='utf-8')
    topology_file.write_text(TOPOLOGY, encoding='utf-8')
    manifest = {'zones_sha256': hashlib.sha256(ZONES.encode()).hexdigest(), 'topology_sha256': '0' * 64}
    with pytest.raises(TopologyError, match='manifest 해시 불일치: topology'):
        load_topology(topology_file, ZONES_DOC, zones_file, manifest)


def test_manifest_without_a_hash_is_not_ready():
    topology = topo(manifest={'zones_sha256': 'x'}, hashes={'zones': 'x', 'topology': 'y'})
    assert not topology.ready
    assert topology.reasons == ['manifest 에 topology_sha256 가 없다']


def test_zero_coordinates_are_valid():
    # load 는 (0, 0, 0) 이다. 좌표 0 은 미설정이 아니다.
    assert ZONES_DOC.zones['load'].x == 0.0
    assert topo().edges


def test_null_width_is_kept_as_unmeasured_not_zero():
    edge = next(e for e in topo().edges if (e.src, e.dst) == ('load', 'cp_a'))
    assert edge.clear_width_m is None


def test_bidirectional_edges_are_expanded():
    pairs = {(e.src, e.dst) for e in topo().edges}
    assert ('cp_a', 'load') in pairs and ('load', 'cp_a') in pairs


# -- 로드에서 거부할 것(계약 3절) ----------------------------------------------------

def test_reject_missing_zone_reference():
    rejects(TOPOLOGY.replace('to: station_a, cost: 2.0', 'to: station_b, cost: 2.0'), '없는 zone 참조')


def test_reject_duplicate_id(tmp_path):
    text = TOPOLOGY.replace('  bed_a3: {room: room_a2}', '  bed_a3: {room: room_a2}\n  bed_a3: {room: room_a2}')
    zones_file, topology_file = tmp_path / 'zones.yaml', tmp_path / 'hospital_topology.yaml'
    zones_file.write_text(ZONES, encoding='utf-8')
    topology_file.write_text(text, encoding='utf-8')
    with pytest.raises(TopologyError, match='중복 id: bed_a3'):
        load_topology(topology_file, ZONES_DOC, zones_file)


def test_reject_duplicate_id_in_a_list():
    rejects(TOPOLOGY.replace('beds: [bed_a3]', 'beds: [bed_a3, bed_a3]'), '중복 id')


def test_reject_duplicate_edge():
    extra = '  - {from: cp_a, to: load, cost: 5.0}\n'
    rejects(TOPOLOGY + extra, '중복 edge cp_a → load')


def test_reject_back_reference_mismatch():
    rejects(TOPOLOGY.replace('room_a2: {ward: ward_a', 'room_a2: {ward: ward_b'), '역참조 불일치')


def test_reject_hierarchy_pointing_at_the_wrong_level():
    # room 이 ward 대신 room 을 가리키면(계층 순환의 시작) 역참조 검사에서 걸린다.
    rejects(TOPOLOGY.replace('room_a2: {ward: ward_a', 'room_a2: {ward: room_a1'), '역참조 불일치')


def test_reject_bed_of_another_room():
    rejects(TOPOLOGY.replace('bed_a2: {room: room_a1}', 'bed_a2: {room: room_a2}'), '다른 병실의 침상')


def test_reject_bed_listed_in_two_rooms():
    rejects(TOPOLOGY.replace('beds: [bed_a3]', 'beds: [bed_a3, bed_a1]'), '다른 병실의 침상')


@pytest.mark.parametrize('cost', ['-1.0', '.nan', '.inf', 'null', 'true'])
def test_reject_bad_cost(cost):
    with pytest.raises(TopologyError, match='cost'):
        topo(TOPOLOGY.replace('cost: 2.0', f'cost: {cost}'))


@pytest.mark.parametrize('width', ['-0.5', '0.0', '.nan', '.inf'])
def test_reject_bad_width(width):
    with pytest.raises(TopologyError, match='clear_width_m'):
        topo(TOPOLOGY.replace('clear_width_m: 0.9}', f'clear_width_m: {width}}}', 1))


def test_reject_graph_that_does_not_reach_a_destination():
    text = TOPOLOGY.replace('  - {from: room_a2, to: bed_a3, cost: 1.0, bidirectional: true, clear_width_m: 2.0}\n', '')
    rejects(text, '목적지에 닿지 않는다: load → bed_a3')


def test_reject_statically_blocked_only_way():
    text = TOPOLOGY.replace('to: bed_a3, cost: 1.0, bidirectional: true',
                            'to: bed_a3, cost: 1.0, bidirectional: true, blocked: true')
    rejects(text, '목적지에 닿지 않는다')


def test_reject_terminal_listed_as_a_stop():
    rejects(TOPOLOGY.replace('stops: [door_a1, door_a2]', 'stops: [door_a1, bed_a1]'), '경유 zone 이 아니다')


def test_reject_wrong_schema_version():
    rejects(TOPOLOGY.replace('schema_version: 1', 'schema_version: 2'), 'schema_version')


def test_reject_station_that_is_not_the_wards_own():
    rejects(TOPOLOGY.replace('station: station_a', 'station: bed_a1'), 'station 은 station_a')


def test_reject_bed_without_cabinet_and_tag_in_zones():
    bare = ZONES.replace('tol_yaw: 0.05,\n              cabinet: {x: 5.5, y: 5.0, z: 0.8, yaw: 0.0}, '
                         'tag: {x: 5.5, y: 5.0, z: 1.0, yaw: 0.0}}', 'tol_yaw: 0.05}')
    assert bare != ZONES
    zones = parse_zones(yaml.safe_load(bare))
    with pytest.raises(TopologyError, match='bed_a3: zones.yaml 에 cabinet·tag 가 없다'):
        parse_topology(yaml.safe_load(TOPOLOGY), zones)


# -- 경로 ---------------------------------------------------------------------------

def test_route_through_the_hierarchy():
    route = plan(topo(measured()), 'load', 'bed_a1', **SMALL)
    assert route.stops == (('cp_a', THROUGH), ('door_a1', STOP), ('room_a1', THROUGH), ('bed_a1', TERMINAL))
    assert route.cost == pytest.approx(15.0)


def test_route_is_not_ready_without_manifest_even_when_widths_pass():
    route = plan(topo(measured()), 'load', 'bed_a1', **SMALL)
    assert not route.ready
    assert route.reasons == ['manifest 없음 — map·zones·topology 가 같은 묶음인지 모른다']


def test_unmeasured_width_makes_the_route_not_ready():
    route = plan(topo(), 'load', 'bed_a1', **SMALL)
    assert 'load → cp_a: 통과 폭 판정 불가(폭 미측정 또는 footprint·여유 미입력)' in route.reasons


def test_missing_footprint_makes_every_measured_door_unknown():
    route = plan(topo(measured()), 'load', 'bed_a1')
    assert zone_ids(route)[-1] == 'bed_a1'
    assert len(route.reasons) == 1 + 4


def test_consecutive_beds_only_route_between_the_two():
    route = plan(topo(measured()), 'bed_a1', 'bed_a2', **SMALL)
    assert zone_ids(route) == ['room_a1', 'bed_a2']


def test_goal_must_be_terminal():
    for goal in ('door_a1', 'cp_a', 'room_a1'):
        with pytest.raises(NoRoute, match='종단 zone 이 아니다'):
            plan(topo(measured()), 'load', goal, **SMALL)


def test_terminal_is_never_an_intermediate():
    # bed_a1 을 거치는 지름길이 있어도 쓰지 않는다.
    shortcut = '  - {from: bed_a1, to: bed_a3, cost: 0.1, clear_width_m: 2.0}\n'
    route = plan(topo(measured(TOPOLOGY + shortcut)), 'load', 'bed_a3', **SMALL)
    assert 'bed_a1' not in zone_ids(route)
    assert zone_ids(route) == ['cp_a', 'door_a2', 'room_a2', 'bed_a3']


def test_blocked_edges_default_to_none_and_reroute():
    shortcut = '  - {from: cp_a, to: room_a1, cost: 10.0, bidirectional: true, clear_width_m: 2.0}\n'
    topology = topo(measured(TOPOLOGY + shortcut))
    assert zone_ids(plan(topology, 'load', 'bed_a1', **SMALL))[:2] == ['cp_a', 'door_a1']
    rerouted = plan(topology, 'load', 'bed_a1', blocked_edges={('door_a1', 'room_a1')}, **SMALL)
    assert zone_ids(rerouted) == ['cp_a', 'room_a1', 'bed_a1']


def test_blocking_the_only_way_is_no_route():
    with pytest.raises(NoRoute):
        plan(topo(measured()), 'load', 'bed_a3', blocked_edges={('cp_a', 'door_a2')}, **SMALL)


def test_door_too_narrow_for_the_footprint_is_no_route():
    # 계획 문서의 산술 예(반지름 0.6 m, 양측 여유 0.15 m)를 0.9 m 문에 넣은 것이다. 실측값이 아니다.
    with pytest.raises(NoRoute):
        plan(topo(measured()), 'load', 'bed_a1', footprint=Circle(0.6), margin=0.15, error_budget=0.01)


def test_equal_cost_ties_break_by_zone_id():
    text = measured(TOPOLOGY.replace('to: door_a2, cost: 4.0', 'to: door_a2, cost: 3.0'))
    extra = '  - {from: door_a2, to: bed_a2, cost: 2.5, clear_width_m: 2.0}\n'
    route = plan(topo(text + extra), 'load', 'bed_a2', **SMALL)
    # cp_a→door_a1→room_a1→bed_a2 = 10+3+1+1.5 = 15.5, cp_a→door_a2→bed_a2 = 10+3+2.5 = 15.5
    assert route.cost == pytest.approx(15.5)
    assert zone_ids(route) == ['cp_a', 'door_a1', 'room_a1', 'bed_a2']


def test_same_inputs_give_the_same_route():
    topology = topo(measured())
    assert plan(topology, 'dock_1', 'station_a', **SMALL) == plan(topology, 'dock_1', 'station_a', **SMALL)


def test_dock_does_not_pass_through_load():
    # dock_1 → load → cp_a(1 + 10 = 11)가 dock_1 → cp_a(12)보다 싸도 load 는 종단이라 경유하지 않는다.
    route = plan(topo(measured()), 'dock_1', 'bed_a3', **SMALL)
    assert zone_ids(route) == ['cp_a', 'door_a2', 'room_a2', 'bed_a3']
    assert route.cost == pytest.approx(12.0 + 4.0 + 1.0 + 1.0)
    assert math.isfinite(route.cost)
