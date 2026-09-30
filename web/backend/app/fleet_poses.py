"""`/isaac/fleet/poses` 파서 — 순수 함수. ROS import 없음(api.md §1.6).

여벌 AMR(`--amr-count` > 1)과 가짜 AMR(더미, `--traffic-dummies`)은 주문·Nav2·base_driver 가 없어
TF `map → <robot>/base_link` 가 없다. 스테이지가 대신 JSON 으로 낸다(시뮬통합 #754, `sim/standalone/p3sim/bridge.py`
`FLEET_POSES`). 형식:

    {"v":1, "stamp":{"sec","nanosec"}, "frame_id":"map",
     "poses":[{"id":"amr_2", "kind":"spare_amr"|"dummy", "x", "y", "yaw"}]}

신뢰할 수 없는 입력으로 다룬다 — 어떤 입력에도 예외를 던지지 않는다. 모양이 틀린 원소는 그 원소만 버린다.
"""

from __future__ import annotations

import json
import math
from typing import Any

KINDS = ("spare_amr", "dummy")
FRAME = "map"


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    return value if math.isfinite(value) else None


def parse_fleet_poses(text: str | None) -> dict[str, Any] | None:
    """JSON 문자열 → {"stamp": sim s, "poses": [{id, kind, x, y, yaw}]}. 우리 형식이 아니면 None."""
    if not isinstance(text, str) or not text.strip():
        return None
    try:
        raw = json.loads(text)
    except (ValueError, TypeError):
        return None
    if not isinstance(raw, dict) or raw.get("v") != 1 or raw.get("frame_id") != FRAME:
        return None
    stamp = raw.get("stamp")
    if not isinstance(stamp, dict):
        return None
    sec, nanosec = _number(stamp.get("sec")), _number(stamp.get("nanosec"))
    if sec is None or nanosec is None:
        return None
    poses = []
    seen = set()
    for item in raw.get("poses") if isinstance(raw.get("poses"), list) else ():
        if not isinstance(item, dict):
            continue
        who, kind = item.get("id"), item.get("kind")
        x, y, yaw = _number(item.get("x")), _number(item.get("y")), _number(item.get("yaw"))
        if not isinstance(who, str) or not who or who in seen or kind not in KINDS or None in (x, y, yaw):
            continue
        seen.add(who)
        poses.append({"id": who, "kind": kind, "x": x, "y": y, "yaw": yaw})
    return {"stamp": sec + nanosec / 1e9, "poses": poses}
