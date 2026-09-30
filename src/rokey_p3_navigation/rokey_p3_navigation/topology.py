"""병동 계층 경로. `hospital_topology.yaml` 을 검사하고 두 정거장 사이 경로를 낸다. ROS 를 import 하지 않는다.

계약 v1 3절 "경유 zone 과 경로 토폴로지(F3, 제안)"를 따른다.

- 토폴로지 파일은 좌표가 없다. zone id 만 참조하고, 절대 좌표는 `zones.yaml` 한 곳에 있다.
- 종단은 `load`, `dock_N`, `bed_xN`, `station_x` 다. `door_*`·`cp_*`·`room_*` 은 경유 전용이다.
  경로의 중간에 종단 zone 이 오지 않는다. 종단 zone 은 경로의 시작이나 끝에만 온다.
- 계층의 짝은 id 로 정한다: `room_a1` ↔ `door_a1`, `ward_a` ↔ `cp_a`·`station_a`.
  파일에 다시 적지 않는다. `<zone>/cabinet`·`<zone>/tag` 도 zone id 에서 만든다.
- 미측정 값(`clear_width_m`)은 `null` 이다. 0 으로 채우지 않는다. 그 edge 를 쓰는 경로는 `ready=false` 다.
- 판본은 파일마다 두지 않는다. manifest 의 해시로 본다. manifest 가 없으면 `ready=false`, 해시가 다르면 거부다.
- 방문 순서는 트립 FSM 이 정한다. 이 모듈은 연속한 두 정거장 사이만 계산한다.

`plan` 은 거리·예상 시간 등 edge `cost` 합이 가장 작은 경로를 낸다(Dijkstra). 비용이 같으면 zone id 순으로 앞선 경로다.
지정 그래프 안의 최단일 뿐, 연속 공간의 최적을 뜻하지 않는다. fleet 에는 아직 연결하지 않았다.
"""

import hashlib
import heapq
import math
import re
from collections import namedtuple

import yaml

from rokey_p3_navigation.passage import PASSABLE, UNKNOWN, check_passage

SCHEMA_VERSION = 1
#: 경로의 끝이 될 수 있는 zone.
_TERMINAL = re.compile(r'^(load|dock_[1-9][0-9]*|bed_[a-z][0-9]+|station_[a-z])$')
#: 문 폭 판정의 yaw. 첫 버전은 문 법선에 맞춰 곧게 지난다고 본다(비스듬한 통과는 다루지 않는다).
PASSAGE_YAW = 0.0

THROUGH = 'through'
STOP = 'stop'
TERMINAL = 'terminal'

Edge = namedtuple('Edge', ('src', 'dst', 'cost', 'clear_width_m', 'blocked'))
#: `edges` 는 방향 edge 목록(양방향은 두 개로 펼친다). `ready`·`reasons` 는 manifest 기준 준비 상태.
Topology = namedtuple('Topology', ('wards', 'rooms', 'beds', 'stops', 'edges', 'ready', 'reasons'))
#: `stops` 는 (zone id, THROUGH|STOP|TERMINAL) 목록. 시작 zone 은 넣지 않는다.
Route = namedtuple('Route', ('stops', 'cost', 'ready', 'reasons'))


class TopologyError(ValueError):
    """토폴로지를 받아들일 수 없다(계약 3절의 거부 사유)."""


class NoRoute(ValueError):
    """두 zone 사이에 쓸 수 있는 경로가 없다."""


def is_terminal(zone_id):
    return bool(_TERMINAL.match(zone_id or ''))


def _letter(zone_id):
    """`bed_a1` → `a`. 병동 글자."""
    return zone_id.split('_', 1)[1][0]


class _UniqueKeyLoader(yaml.SafeLoader):
    """같은 키가 두 번 나오면 거부한다. 기본 로더는 뒤의 값으로 조용히 덮는다."""


def _mapping(loader, node, deep=False):
    keys = set()
    for key_node, _ in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in keys:
            raise TopologyError(f'중복 id: {key}')
        keys.add(key)
    return loader.construct_mapping(node, deep=deep)


_UniqueKeyLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _mapping)


def _table(document, key):
    value = document.get(key) or {}
    if not isinstance(value, dict):
        raise TopologyError(f'{key} 는 맵이어야 한다')
    return value


def _ids(value, where):
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise TopologyError(f'{where} 는 id 목록이어야 한다')
    if len(set(value)) != len(value):
        raise TopologyError(f'{where} 에 중복 id')
    return list(value)


def _number(value, where, allow_null):
    if value is None and allow_null:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise TopologyError(f'{where} 가 유한한 숫자가 아니다: {value!r}')
    return float(value)


def _edges(document, known):
    edges, seen = [], set()
    for index, body in enumerate(document.get('edges') or []):
        where = f'edges[{index}]'
        if not isinstance(body, dict):
            raise TopologyError(f'{where} 는 맵이어야 한다')
        src, dst = body.get('from'), body.get('to')
        for zone_id in (src, dst):
            if zone_id not in known:
                raise TopologyError(f'{where}: 없는 zone 참조 {zone_id!r}')
        if src == dst:
            raise TopologyError(f'{where}: 자기 자신으로 가는 edge')
        cost = _number(body.get('cost'), f'{where}.cost', allow_null=False)
        if cost < 0.0:
            raise TopologyError(f'{where}.cost 가 음수다: {cost}')
        width = _number(body.get('clear_width_m'), f'{where}.clear_width_m', allow_null=True)
        if width is not None and width <= 0.0:
            raise TopologyError(f'{where}.clear_width_m 이 0 이하다: {width}')
        blocked = body.get('blocked', False)
        bidirectional = body.get('bidirectional', False)
        if not isinstance(blocked, bool) or not isinstance(bidirectional, bool):
            raise TopologyError(f'{where}: blocked·bidirectional 은 true/false 다')
        pairs = [(src, dst), (dst, src)] if bidirectional else [(src, dst)]
        for a, b in pairs:
            if (a, b) in seen:
                raise TopologyError(f'{where}: 중복 edge {a} → {b}')
            seen.add((a, b))
            edges.append(Edge(a, b, cost, width, blocked))
    return edges


def _hierarchy(document, known):
    wards, rooms, beds = _table(document, 'wards'), _table(document, 'rooms'), _table(document, 'beds')
    # 계층은 id 모양으로 층이 정해진다(ward → room → bed).
    # 다른 층의 id 를 가리키면 역참조 검사에서 걸리므로 순환이 생길 수 없다.
    for table, pattern in ((wards, r'^ward_[a-z]$'), (rooms, r'^room_[a-z][0-9]+$'), (beds, r'^bed_[a-z][0-9]+$')):
        for key, body in table.items():
            if not re.match(pattern, str(key)) or not isinstance(body, dict):
                raise TopologyError(f'{key}: id 모양({pattern})이 아니거나 맵이 아니다')
    for ward_id, body in wards.items():
        letter = _letter(ward_id)
        for derived in (f'cp_{letter}', body.get('station')):
            if derived not in known:
                raise TopologyError(f'wards.{ward_id}: 없는 zone 참조 {derived!r}')
        if body['station'] != f'station_{letter}':
            raise TopologyError(f'wards.{ward_id}: station 은 station_{letter} 이어야 한다')
        for room_id in _ids(body.get('rooms'), f'wards.{ward_id}.rooms'):
            if room_id not in rooms:
                raise TopologyError(f'wards.{ward_id}: 없는 병실 {room_id}')
            if rooms[room_id].get('ward') != ward_id:
                raise TopologyError(
                    f'역참조 불일치: {ward_id}.rooms 의 {room_id} 가 ward 로 {ward_id} 를 가리키지 않는다')
    for room_id, body in rooms.items():
        ward_id = body.get('ward')
        if ward_id not in wards or room_id not in (wards[ward_id].get('rooms') or []):
            raise TopologyError(f'역참조 불일치: {room_id}.ward = {ward_id!r} 가 그 병실을 목록에 두지 않는다')
        if _letter(room_id) != _letter(ward_id):
            raise TopologyError(f'rooms.{room_id}: 다른 병동({ward_id}) 소속이다')
        for zone_id in (room_id, 'door_' + room_id.split('_', 1)[1]):
            if zone_id not in known:
                raise TopologyError(f'rooms.{room_id}: 없는 zone 참조 {zone_id}')
        for bed_id in _ids(body.get('beds'), f'rooms.{room_id}.beds'):
            if bed_id not in beds:
                raise TopologyError(f'rooms.{room_id}: 없는 침상 {bed_id}')
            if beds[bed_id].get('room') != room_id:
                raise TopologyError(f'다른 병실의 침상: {bed_id} 가 {room_id} 목록에 있지만 room 이 다르다')
    for bed_id, body in beds.items():
        room_id = body.get('room')
        if room_id not in rooms or bed_id not in (rooms[room_id].get('beds') or []):
            raise TopologyError(f'역참조 불일치: {bed_id}.room = {room_id!r} 가 그 침상을 목록에 두지 않는다')
        if _letter(bed_id) != _letter(room_id):
            raise TopologyError(f'beds.{bed_id}: 다른 병동의 병실({room_id}) 소속이다')
        if bed_id not in known:
            raise TopologyError(f'beds.{bed_id}: 없는 zone 참조')
    return wards, rooms, beds


def _manifest_reasons(manifest, hashes):
    if manifest is None:
        return ['manifest 없음 — map·zones·topology 가 같은 묶음인지 모른다']
    for name in ('zones', 'topology'):
        expected = manifest.get(f'{name}_sha256')
        if expected is None:
            return [f'manifest 에 {name}_sha256 가 없다']
        if hashes is None or hashes.get(name) != expected:
            raise TopologyError(f'manifest 해시 불일치: {name}')
    return []


def parse_topology(document, zones, manifest=None, hashes=None):
    """토폴로지 매핑을 검사한다. 거부 사유면 `TopologyError`, 아니면 `Topology`.

    `zones` 는 `zones.parse_zones` 결과다. `hashes` 는 {'zones': sha256, 'topology': sha256}.
    """
    if not isinstance(document, dict):
        raise TopologyError('토폴로지가 맵이 아니다')
    if document.get('schema_version') != SCHEMA_VERSION:
        raise TopologyError(f'schema_version 이 {SCHEMA_VERSION} 가 아니다: {document.get("schema_version")!r}')
    known = set(zones.zones)
    wards, rooms, beds = _hierarchy(document, known)
    edges = _edges(document, known)
    stops = set(_ids(document.get('stops') or [], 'stops'))
    for zone_id in stops:
        if zone_id not in known or is_terminal(zone_id):
            raise TopologyError(f'stops: 경유 zone 이 아니다 {zone_id!r}')
    for zone_id in [*beds, *(body['station'] for body in wards.values())]:
        zone = zones.zones[zone_id]
        if zone.cabinet is None or zone.tag is None:
            raise TopologyError(f'{zone_id}: zones.yaml 에 cabinet·tag 가 없다')
    topology = Topology(wards, rooms, beds, frozenset(stops), edges, False, [])
    for origin in (zone_id for zone_id in ('load',) if zone_id in known):
        for goal in sorted([*beds, *(body['station'] for body in wards.values())]):
            try:
                _search(topology, origin, goal, frozenset(), lambda edge: True)
            except NoRoute as exc:
                raise TopologyError(f'목적지에 닿지 않는다: {exc}') from None
    reasons = _manifest_reasons(manifest, hashes)
    return topology._replace(ready=not reasons, reasons=reasons)


def load_topology(path, zones, zones_path, manifest=None):
    """파일을 읽어 해시를 재고 `parse_topology` 한다."""
    with open(path, 'rb') as handle:
        raw = handle.read()
    with open(zones_path, 'rb') as handle:
        zones_raw = handle.read()
    hashes = {'topology': hashlib.sha256(raw).hexdigest(), 'zones': hashlib.sha256(zones_raw).hexdigest()}
    return parse_topology(yaml.load(raw, Loader=_UniqueKeyLoader), zones, manifest, hashes)


def _search(topology, start, goal, blocked, usable):
    """Dijkstra. 중간에 종단 zone 을 거치지 않는다. 같은 비용이면 zone id 목록이 앞선 경로."""
    queue = [(0.0, (start,))]
    settled = set()
    while queue:
        cost, path = heapq.heappop(queue)
        here = path[-1]
        if here == goal:
            return cost, path
        if here in settled:
            continue
        settled.add(here)
        if here != start and is_terminal(here):
            continue
        for edge in topology.edges:
            if edge.src != here or edge.blocked or (edge.src, edge.dst) in blocked:
                continue
            if edge.dst in settled or not usable(edge):
                continue
            heapq.heappush(queue, (cost + edge.cost, path + (edge.dst,)))
    raise NoRoute(f'{start} → {goal}')


def plan(topology, start, goal, blocked_edges=frozenset(), footprint=None, margin=None, error_budget=None):
    """`start` 에서 종단 `goal` 까지의 `Route`. 쓸 수 있는 경로가 없으면 `NoRoute`.

    `blocked_edges` 는 막힌 (from, to) 쌍 집합이다(기본 빈 집합). 문 폭은 `passage.check_passage` 로 본다.
    폭이 `BLOCKED` 인 edge 는 쓰지 않는다. 폭이 `null` 이거나 footprint 등이 없어 `UNKNOWN` 이면 쓰되 `ready=false` 다.
    """
    if not is_terminal(goal):
        raise NoRoute(f'{goal} 은 종단 zone 이 아니다(경유 전용 zone 은 목적지가 될 수 없다)')

    def verdict(edge):
        if edge.clear_width_m is None:
            return UNKNOWN
        return check_passage(footprint, PASSAGE_YAW, margin, error_budget, edge.clear_width_m).verdict

    cost, path = _search(topology, start, goal, frozenset(blocked_edges),
                         lambda edge: verdict(edge) in (PASSABLE, UNKNOWN))
    reasons = list(topology.reasons)
    for src, dst in zip(path[:-1], path[1:], strict=True):
        edge = next(e for e in topology.edges if (e.src, e.dst) == (src, dst))
        if verdict(edge) == UNKNOWN:
            reasons.append(f'{src} → {dst}: 통과 폭 판정 불가(폭 미측정 또는 footprint·여유 미입력)')
    kinds = [(zone_id, STOP if zone_id in topology.stops else THROUGH) for zone_id in path[1:-1]]
    return Route(tuple(kinds) + ((goal, TERMINAL),), cost, not reasons, reasons)
