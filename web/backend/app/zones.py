"""구역 목록 — `zones.yaml` 을 읽어 배송 목적지 후보를 낸다. 순수(ROS import 없음).

원문(`src/rokey_p3_description/config/zones.yaml`, **다른 사람 레인 — 읽기만 한다**):

    frame: map
    zones:
      load:      {kind: load, ...}
      dock_1:    {kind: dock, ...}
      bed_a1:    {kind: bed, ...}
      station_a: {kind: station, ...}

구역 ID 규칙: `pharm`, `load`, `dock_N`, `ward_x`, `station_x`, `room_xN`, `bed_xN`.
**배송 목적지가 될 수 있는 것은 `kind` 가 bed·room·station 인 것뿐이다** — load·dock 은 아니다.

bed 에 `room`·`ward`·`label` 이 있으면 목적지 후보에 병실 묶음과 이름표로 싣는다. 병원 월드
(`zones.hospital.yaml`)는 생성기(`sim/standalone/p3sim/hospital_nav.py`)가 이 셋을 낸다 — 작전이 정한 값
(room C1·C2 = PDF P3_Map 의 병실, ward W1 = 1병동, label = PDF 병상 번호 D1–D10). 없으면 null 이다.
**웹은 값을 지어내지 않는다** — ID 글자(bed_a·bed_b)로 병실을 짐작하지 않는다.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

# 배송 목적지가 될 수 있는 kind
DESTINATION_KINDS = frozenset({"bed", "room", "station"})

# **orchestrator 는 zones.yaml 을 읽지 않는다.** destination_id 는 구역 ID 정규식만 통과하면
# 수락된다. 그래서 검증은 이 식으로 하고, zones.yaml 은 후보 목록 표시에만 쓴다.
#
# `rokey_p3_navigation/zones.py` 의 `_ZONE` 원문과 같다. dock 은 **1 부터**이고 앞자리 0 이 없다
# (`dock_0`·`dock_01` 은 구역 ID 가 아니다).
ZONE_ID_RE = re.compile(
    r"^(pharm|load|dock_[1-9][0-9]*|ward_[a-z]|station_[a-z]|room_[a-z][0-9]+|bed_[a-z][0-9]+)$")

# zones.yaml 을 못 찾았을 때만 쓰는 후보 목록. 검증용이 아니다 —
# 여기 없어도 정규식을 통과하면 수락된다.
MOCK_ZONES: dict[str, dict[str, str]] = {"bed_a1": {"kind": "bed"}, "station_a": {"kind": "station"}}

#: 구역에서 목적지 후보로 옮겨 싣는 자리 필드. 값은 문자열이고 없으면 싣지 않는다.
PLACE_KEYS = ("room", "ward", "label")

#: 평면도에 그리는 자세 필드(map 프레임, m·rad). 수가 아니면 싣지 않는다.
POSE_KEYS = ("x", "y", "yaw")

#: 기본은 저장소 원문. simulation 소유 파일이라 **읽기만 한다.**
_ZONES_RELATIVE = Path("src/rokey_p3_description/config/zones.yaml")


def default_zones_path() -> Path | None:
    for base in Path(__file__).resolve().parents:
        candidate = base / _ZONES_RELATIVE
        if candidate.is_file():
            return candidate
    return None


def is_zone_id(destination_id: str | None) -> bool:
    """orchestrator 가 수락할 모양인가. **zones.yaml 에 있는지는 보지 않는다.**

    zones.yaml 에 없는 구역은 수락된 뒤 실물 fleet 의 GoToZone 거부로 드러난다
    (HOLD_RETURN, reason `goto_rejected`). pharmacy_only 에서는 드러나지 않는다.
    """
    return bool(destination_id) and ZONE_ID_RE.match(destination_id) is not None


def parse_zones(doc: Any) -> dict[str, dict[str, Any]]:
    """`{frame: ..., zones: {id: {kind: ..., room: ...}}}` → `{구역 ID: {"kind", [room, ward, label, x, y, yaw]}}`.

    모르면 빈 맵. 자리 필드(PLACE_KEYS)·자세(POSE_KEYS)는 있는 것만 싣는다.
    """
    if not isinstance(doc, dict):
        return {}
    zones = doc.get("zones")
    if not isinstance(zones, dict):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for zone_id, value in zones.items():
        if not isinstance(zone_id, str) or not zone_id.strip():
            continue
        value = value if isinstance(value, dict) else {}
        kind = value.get("kind")
        entry = {"kind": str(kind).strip().lower() if kind else ""}
        for key in PLACE_KEYS:
            if value.get(key) not in (None, ""):
                entry[key] = str(value[key]).strip()
        for key in POSE_KEYS:
            if isinstance(value.get(key), (int, float)) and not isinstance(value.get(key), bool):
                entry[key] = float(value[key])
        out[zone_id.strip()] = entry
    return out


def load_zones(path: str | Path | None) -> dict[str, dict[str, Any]]:
    if not path:
        return {}
    p = Path(path)
    if not p.is_file():
        return {}
    try:
        import yaml
        return parse_zones(yaml.safe_load(p.read_text(encoding="utf-8")))
    except Exception:  # noqa: BLE001 - 남의 레인 파일이 깨졌다고 우리가 죽지 않는다
        return {}


def natural_key(zone_id: str) -> tuple[Any, ...]:
    """번호를 수로 비교한다 — `bed_a2` 가 `bed_a10` 보다 앞이다(문자열 정렬이면 뒤다)."""
    return tuple(int(part) if part.isdigit() else part for part in re.split(r"(\d+)", zone_id))


def room_label(room: str | None) -> str | None:
    """`C1` → `"C1 병실"`. 화면이 규칙을 복사하지 않게 서버가 이름을 정한다."""
    return f"{room} 병실" if room else None


def ward_label(ward: str | None) -> str | None:
    """`W1` → `"1병동"`. `W<번호>` 모양이 아니면 ID 를 그대로 쓴다."""
    if not ward:
        return None
    match = re.fullmatch(r"W([0-9]+)", ward)
    return f"{match.group(1)}병동" if match else ward


def destinations(zones: dict[str, dict[str, Any]]) -> list[dict[str, str | None]]:
    """배송 목적지로 고를 수 있는 구역만 번호 순으로 골라 낸다.

    `group` 은 병실(room)이다 — 화면은 이 키로 칸을 나눈다. 자리 필드가 없는 구역(station,
    빈월드 zones)은 `group`·`label` 등이 null 이다.
    """
    out: list[dict[str, str | None]] = []
    for zone_id in sorted(zones, key=natural_key):
        entry = zones[zone_id]
        if entry.get("kind") not in DESTINATION_KINDS:
            continue
        room, ward = entry.get("room"), entry.get("ward")
        out.append({"destination_id": zone_id, "kind": entry["kind"],
                    "group": room, "group_label": room_label(room),
                    "ward": ward, "ward_label": ward_label(ward),
                    "label": entry.get("label")})
    return out


def rooms_of_orders(orders: list[dict[str, Any]], zones: dict[str, dict[str, Any]]) -> dict[str, str]:
    """주문 풀 행(`order_id`·`bed`) → `{order_id: room}`. 병실을 모르는 주문은 빠진다."""
    out: dict[str, str] = {}
    for order in orders:
        room = zones.get(order.get("bed") or "", {}).get("room")
        if room and order.get("order_id"):
            out[order["order_id"]] = room
    return out


def zone_rows(zones: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """평면도용 — **모든** 구역(load·dock 포함)을 번호 순으로, 자세와 이름표를 붙여 낸다.

    자세가 없는 구역(mock 목록)은 x·y·yaw 가 null 이다. 화면은 그런 구역을 그리지 않는다.
    """
    out: list[dict[str, Any]] = []
    for zone_id in sorted(zones, key=natural_key):
        entry = zones[zone_id]
        room, ward = entry.get("room"), entry.get("ward")
        out.append({"zone_id": zone_id, "kind": entry.get("kind") or None,
                    **{key: entry.get(key) for key in POSE_KEYS},
                    "group": room, "group_label": room_label(room),
                    "ward": ward, "ward_label": ward_label(ward),
                    "label": entry.get("label")})
    return out
