"""저장소에 든 월드 설정 파일을 **주행의 로더로 직접** 읽는다. ROS 없이 돈다.

`zones.emptyworld.yaml`·`routes.emptyworld.yaml` 은 시뮬의 `layout.py` 에서 자동 생성된다.
`sim/tests/` 가 지키는 것은 "파일이 layout.py 와 같은가" 다. **파일을 우리 로더가 받아들이는가는
아무도 안 본다.** 두 벌로 갈라진 자리다(#435): 예컨대 `sim/tests/test_full_loop_layout.py` 는
zone ID 규칙을 `zones.py` 의 정규식과 "같은 뜻" 으로 다시 적어 두었다.

어긋나면 증상은 조용하다. fleet 은 뜰 때 zones 를 못 읽으면 `zones=없음` 으로 뜨고
**모든 GoToZone 을 거부**한다(한 바퀴가 ② 에서 끊긴다). routes 를 못 읽으면 경유점 없이
곧장 가서 고정물을 스친다. 둘 다 L3 에 가서야 보인다.

그래서 값이 아니라 **우리 쪽 계약**만 본다. 좌표가 맞는지는 시뮬 시험이 본다.

**건너뛰지 않는다.** 여기서 읽는 파일은 `sim/` 처럼 저장소 밖에 있을 수 있는 것이 아니라
같은 저장소의 `rokey_p3_description/config/` 에 늘 있는 것이다. 없으면 그 자체가 고장이다
(건너뛴 시험은 통과가 아니라 미실행이다).
"""

import pathlib

import pytest

from rokey_p3_navigation.routes import RoutesError, load_routes, waypoints
from rokey_p3_navigation.topology import is_terminal
from rokey_p3_navigation.zones import ZonesError, load_zones

CONFIG = pathlib.Path(__file__).resolve().parents[2] / 'rokey_p3_description' / 'config'

EMPTYWORLD_ZONES = 'zones.emptyworld.yaml'
EMPTYWORLD_ROUTES = 'routes.emptyworld.yaml'
#: 심월드 쪽 기본 파일. 값은 아직 자리표(좌표 미측정)라 읽히는지까지만 본다.
SIMWORLD_ZONES = 'zones.yaml'
#: 병원 씬(hospital_navigationv1)에서 생성한 파일. 값은 시뮬 시험(sim/tests/test_hospital_nav.py)이 본다.
HOSPITAL_ZONES = 'zones.hospital.yaml'
HOSPITAL_ROUTES = 'routes.hospital.yaml'


def _path(name):
    path = CONFIG / name
    assert path.is_file(), f'{path} 가 없다. 주행 노드가 기본값으로 이 파일을 읽는다'
    return path


def _zones(name):
    try:
        return load_zones(_path(name))
    except (OSError, ZonesError) as exc:
        pytest.fail(f'{name} 을 주행 로더가 못 읽는다 — fleet 이 모든 GoToZone 을 거부한다: {exc}')


def _emptyworld_routes():
    zones = _zones(EMPTYWORLD_ZONES)
    try:
        return load_routes(_path(EMPTYWORLD_ROUTES), zones)
    except (OSError, RoutesError) as exc:
        pytest.fail(f'{EMPTYWORLD_ROUTES} 를 주행 로더가 못 읽는다 — 경유점 없이 곧장 간다: {exc}')


@pytest.mark.parametrize('zones_name', (SIMWORLD_ZONES, EMPTYWORLD_ZONES, HOSPITAL_ZONES))
def test_the_shipped_zones_load(zones_name):
    assert _zones(zones_name).zones, f'{zones_name} 에 zone 이 하나도 없다'


def test_emptyworld_tolerances_are_positive():
    """공차 0 이면 fleet 이 arrived 를 영원히 내지 않는다. 로더는 WARN 만 내고 통과시킨다.

    **심월드 `zones.yaml` 은 여기서 뺀다.** 그 파일은 아직 전부 0 인 자리표이고(좌표 미측정),
    그 상태를 보는 것은 `readiness` 노드의 일이다. 한 바퀴를 실제로 도는 것은 빈월드 쪽이다.
    """
    for zone in _zones(EMPTYWORLD_ZONES).zones.values():
        assert zone.tol_xy > 0.0, f'{zone.zone_id} 의 tol_xy 가 0 이다'
        assert zone.tol_yaw > 0.0, f'{zone.zone_id} 의 tol_yaw 가 0 이다'


def test_emptyworld_has_the_dock_zone():
    # `dock_origin_tf` 가 이 zone 하나로 map -> odom 을 낸다. 없으면 TF 가 아예 안 나온다.
    assert 'dock_1' in _zones(EMPTYWORLD_ZONES).zones


def test_the_shipped_emptyworld_routes_load_against_the_same_zones():
    assert _emptyworld_routes().pairs, f'{EMPTYWORLD_ROUTES} 에 쌍이 하나도 없다'


def test_emptyworld_route_ends_are_terminal_zones():
    # fleet 은 경유 전용 zone(door_xN·cp_x)을 목표로 받지 않는다(#285). 경로의 양 끝은 종단이어야 한다.
    for source, target in _emptyworld_routes().pairs:
        assert is_terminal(source), f'{source} 는 경유 전용이라 목표가 될 수 없다'
        assert is_terminal(target), f'{target} 는 경유 전용이라 목표가 될 수 없다'


def test_emptyworld_has_a_route_out_of_the_dock():
    # 리셋 뒤 fleet 의 `_here` 는 도크다. 그 쌍이 없으면 첫 이동이 곧장 직선이 된다.
    routes = _emptyworld_routes()
    assert ('dock_1', 'load') in routes.pairs, 'dock_1 → load 쌍이 없다'
    # 빈 목록은 "곧장 가도 된다고 따져 봤다" 는 뜻이다. 그것까지 막지는 않는다.
    assert waypoints(routes, 'dock_1', 'load') is not None


def test_the_shipped_hospital_routes_load_and_end_at_terminal_zones():
    zones = _zones(HOSPITAL_ZONES)
    for zone in zones.zones.values():
        assert zone.tol_xy > 0.0 and zone.tol_yaw > 0.0, f'{zone.zone_id} 공차가 0 이다'
    try:
        routes = load_routes(_path(HOSPITAL_ROUTES), zones)
    except (OSError, RoutesError) as exc:
        pytest.fail(f'{HOSPITAL_ROUTES} 를 주행 로더가 못 읽는다: {exc}')
    assert ('dock_1', 'load') in routes.pairs
    for source, target in routes.pairs:
        assert is_terminal(source) and is_terminal(target), f'{source}→{target} 끝이 종단 zone 이 아니다'
