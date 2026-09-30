"""REQUEST_ACCEPTED.detail 파서 — 순수 함수. ROS import 없음.

`/deliver` 는 액션이라 goal(DeliveryRequest)이 토픽으로 안 나온다. 그래서 외부 관찰만으로는
mode·destination_id·주문의 patient_id·item_id 를 알 수 없다.

팔 세션이 REQUEST_ACCEPTED 의 detail 에 compact JSON 한 줄을 싣기로 했다(계약·msg 는 안 바꾼다):

    {"mode":1,"destination_id":"bed_a1","orders":[{"order_id":"o1","patient_id":"p1","item_id":"i1"}]}

**아직 머지 전이다.** detail 은 자유 문자열이고 판정에 쓰지 않는 메모라, 여기서 파싱에 실패하면
조용히 None 을 돌려주고 호출자는 mode_source=null 로 둔다. 화면 표시에만 쓴다.
"""

from __future__ import annotations

import json
from typing import Any

MODE_SINGLE = 0
MODE_URGENT = 1
MODE_BATCH_ROOM = 2
MODE_BATCH_WARD = 3

MODE_NAMES = {
    MODE_SINGLE: "MODE_SINGLE",
    MODE_URGENT: "MODE_URGENT",
    MODE_BATCH_ROOM: "MODE_BATCH_ROOM",
    MODE_BATCH_WARD: "MODE_BATCH_WARD",
}


def mode_name(mode: int | None) -> str | None:
    return MODE_NAMES.get(mode) if mode is not None else None


def _clean_str(value: Any) -> str | None:
    """문자열만 받는다. 빈 문자열은 없는 것으로 본다."""
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value or None


def _clean_mode(value: Any) -> int | None:
    """알려진 4개 모드만 받는다. bool 은 int 의 하위형이라 명시적으로 막는다."""
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if value in MODE_NAMES else None


def parse_request_detail(detail: str | None) -> dict[str, Any] | None:
    """detail 을 파싱한다. 쓸 만한 게 하나도 없으면 None.

    detail 은 신뢰할 수 없는 자유 문자열이다 — 어떤 입력에도 예외를 던지지 않는다.
    """
    if not isinstance(detail, str) or not detail.strip():
        return None
    try:
        raw = json.loads(detail)
    except (ValueError, TypeError):
        return None
    if not isinstance(raw, dict):
        return None

    mode = _clean_mode(raw.get("mode"))
    destination_id = _clean_str(raw.get("destination_id"))

    orders: dict[str, dict[str, str | None]] = {}
    for item in raw.get("orders") or []:
        if not isinstance(item, dict):
            continue
        order_id = _clean_str(item.get("order_id"))
        if order_id is None:
            continue
        orders[order_id] = {
            "patient_id": _clean_str(item.get("patient_id")),
            "item_id": _clean_str(item.get("item_id")),
        }

    if mode is None and destination_id is None and not orders:
        return None

    return {
        "mode": mode,
        "mode_name": mode_name(mode),
        "destination_id": destination_id,
        "orders": orders,
        "mode_source": "event_detail",
    }
