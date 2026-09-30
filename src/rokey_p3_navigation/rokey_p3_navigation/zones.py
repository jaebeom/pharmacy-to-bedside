"""구역 ID 규칙과 zones.yaml 읽기. ROS 를 import 하지 않는다.

`zones.yaml` 은 `rokey_p3_description/config/zones.yaml` 하나다(계약 v1 3절, simulation 소유).
navigation 은 9/17 맵 추출 뒤 값을 채우는 PR 을 내고 simulation 이 리뷰한다.
"""

import re
from collections import namedtuple

import yaml

_ZONE = re.compile(r'^(pharm|load|dock_[1-9][0-9]*|ward_[a-z]|station_[a-z]|room_[a-z][0-9]+|bed_[a-z][0-9]+'
                   r'|door_[a-z][0-9]+|cp_[a-z])$')

#: `map` 아래의 자세. 구역 자체는 z 가 없고 보관함·인식표는 z 가 있다.
Pose = namedtuple('Pose', ('x', 'y', 'z', 'yaw'))
#: 한 구역. `cabinet` 과 `tag` 는 없으면 None 이다(적재 위치·도크).
Zone = namedtuple('Zone', ('zone_id', 'kind', 'x', 'y', 'yaw', 'tol_xy', 'tol_yaw', 'cabinet', 'tag'))
#: 파일 하나. `pharmacy` 는 조제실 고정 프레임들(`pharmacy/belt_end` 등)이다.
Zones = namedtuple('Zones', ('frame', 'zones', 'pharmacy'))


class ZonesError(ValueError):
    """zones.yaml 이 계약 3절 형식이 아니다."""


def is_zone_id(zone_id):
    """계약 3절 규칙에 맞는 구역 ID 인가."""
    return bool(_ZONE.match(zone_id or ''))


def _number(document, key, where):
    value = document.get(key)
    if value is None:
        raise ZonesError(f'{where}: {key} 가 없다')
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ZonesError(f'{where}: {key} 가 숫자가 아니다: {value!r}')
    return float(value)


def _pose(document, where):
    if not isinstance(document, dict):
        raise ZonesError(f'{where}: x, y, z, yaw 를 담은 맵이어야 한다')
    return Pose(_number(document, 'x', where), _number(document, 'y', where),
                _number(document, 'z', where), _number(document, 'yaw', where))


def _zone(zone_id, document):
    where = f'zones.{zone_id}'
    if not is_zone_id(zone_id):
        raise ZonesError(f'{where}: 구역 ID 규칙에 맞지 않는다')
    if not isinstance(document, dict):
        raise ZonesError(f'{where}: 맵이어야 한다')
    kind = document.get('kind')
    if not isinstance(kind, str) or not kind:
        raise ZonesError(f'{where}: kind 가 없다')
    return Zone(
        zone_id=zone_id,
        kind=kind,
        x=_number(document, 'x', where),
        y=_number(document, 'y', where),
        yaw=_number(document, 'yaw', where),
        tol_xy=_number(document, 'tol_xy', where),
        tol_yaw=_number(document, 'tol_yaw', where),
        cabinet=_pose(document['cabinet'], f'{where}.cabinet') if 'cabinet' in document else None,
        tag=_pose(document['tag'], f'{where}.tag') if 'tag' in document else None,
    )


def parse_zones(document):
    """읽어 들인 매핑을 검사해 `Zones` 로 만든다. 형식이 틀리면 `ZonesError`."""
    if not isinstance(document, dict):
        raise ZonesError('zones.yaml 이 맵이 아니다')
    frame = document.get('frame')
    if not isinstance(frame, str) or not frame:
        raise ZonesError('frame 이 없다. 계약 3절에서 map 이다')
    zones = document.get('zones')
    if not isinstance(zones, dict) or not zones:
        raise ZonesError('zones 가 비었다')
    pharmacy = document.get('pharmacy') or {}
    if not isinstance(pharmacy, dict):
        raise ZonesError('pharmacy 는 맵이어야 한다')
    return Zones(
        frame=frame,
        zones={zone_id: _zone(zone_id, body) for zone_id, body in zones.items()},
        pharmacy={name: _pose(body, f'pharmacy.{name}') for name, body in pharmacy.items()},
    )


def load_zones(path):
    """zones.yaml 을 읽어 `Zones` 로 만든다."""
    with open(path, encoding='utf-8') as handle:
        return parse_zones(yaml.safe_load(handle))
