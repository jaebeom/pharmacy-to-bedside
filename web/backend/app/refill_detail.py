"""`REFILL_DONE.detail` 파서 — 순수 함수. ROS import 없음.

`detail` 은 계약 2.6절에서 **사람이 읽는 메모**이고 판정에 쓰지 않는다. 구조 파싱은
`REQUEST_ACCEPTED`(`request_detail.py`)와 이 파일 **둘만 예외**다.

조제실 장면 v2 에서 팔 노드는 compact JSON 한 줄을 낸다:

    {"item":"drug-amox","slot":"a","kind":"cylinder","cell":"floor_left/r0c1",
     "target":"round","seed":0,"draw":3,"clearance":0.011}

v1 은 `refill_sequence` 의 문자열이다: `"<item_id> slot <a|b>"` + lot 이 있으면 `" lot <lot_id>"`.
**v1 문자열은 일부러 파싱하지 않는다** — 두 형식을 다 읽으면 유지할 규칙이 둘이 되고,
v1 형식은 소비자를 위한 계약이 아니라 팔 노드 내부 문구다. 원문은 `event.detail` 에 그대로 있다.
"""

from __future__ import annotations

import json
from typing import Any

#: 약통 종류. 계약에 없는 값은 내려보내지 않는다.
KINDS = ("cylinder", "module")
#: 수납 종류.
TARGETS = ("round", "module")

#: `refill` 객체의 필드. 파싱이 안 되면 전부 None 이다.
FIELDS = ("item", "slot", "kind", "cell", "target", "seed", "draw", "clearance")


def _text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value or None


def _upper(value: str | None) -> str | None:
    return value.upper() if value else None


def _one_of(value: Any, allowed: tuple[str, ...]) -> str | None:
    """알려진 값만 통과시킨다. 모르는 것은 None — 화면이 그릴 수 없는 것을 내려보내지 않는다."""
    text = _text(value)
    return text if text in allowed else None


def _int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def parse_refill_detail(detail: str | None) -> dict[str, Any] | None:
    """v2 JSON 이면 파생 필드, 아니면 None.

    `detail` 은 신뢰할 수 없는 자유 문자열이다 — 어떤 입력에도 예외를 던지지 않는다.
    """
    if not isinstance(detail, str) or not detail.strip():
        return None
    try:
        raw = json.loads(detail)
    except (ValueError, TypeError):
        return None                      # v1 문자열이거나 깨진 JSON
    if not isinstance(raw, dict):
        return None

    parsed = {
        "item": _text(raw.get("item")),
        # 팔은 소문자로 내지만 **대문자로 맞춘다.** `dispenser.slots[].slot_name` 이
        # "A"/"B" 이므로, 소문자로 두면 화면이 "방금 보충된 칸" 을 찾을 때 "a" == "A" 가
        # 거짓이 되어 **조용히 아무것도 강조되지 않는다**(예외도 안 나고 화면도 안 깨진다).
        # 무엇이 실제로 왔는지는 `event.detail` 원문이 그대로 들고 있다.
        "slot": _upper(_text(raw.get("slot"))),
        "kind": _one_of(raw.get("kind"), KINDS),
        "cell": _text(raw.get("cell")),
        "target": _one_of(raw.get("target"), TARGETS),
        "seed": _int(raw.get("seed")),
        "draw": _int(raw.get("draw")),
        "clearance": _number(raw.get("clearance")),
    }
    if all(v is None for v in parsed.values()):
        return None                      # JSON 이긴 해도 우리 것이 아니다
    return parsed


def refill_summary(detail: str | None, stamp: float) -> dict[str, Any]:
    """`dispenser.last_refill` 한 장.

    `parsed` 는 **구조 파싱이 됐는가**일 뿐이고 **장면 버전이 아니다** — 서버는 장면 버전을
    모른다. `"v1"`/`"v2"` 같은 값을 쓰면 다음 사람이 이걸로 장면 버전을 판단한다.
    파싱이 안 됐으면 구조 필드는 전부 None 이고 원문은 `event.detail` 에 있다.
    """
    fields = parse_refill_detail(detail)
    if fields is None:
        return {"stamp": stamp, "parsed": False, **dict.fromkeys(FIELDS)}
    return {"stamp": stamp, "parsed": True, **fields}


#: 약통 종류 → 수납 종류. 팔의 장면 v2(`scene_v2.parse_inventory`)가 `targets.round` 를 cylinder 에,
#: `targets.module` 을 module 에 붙이는 것과 같은 짝이다.
TARGET_OF_KIND = {"cylinder": "round", "module": "module"}


def parse_shelf_kinds(text: str | None) -> dict[str, str] | None:
    """`/m0609/shelf/inventory`(장면 v2 JSON) → {item_id: 약통 종류}. v2 가 아니거나 깨졌으면 None.

    `items` 표가 먼저이고, 표에 없는 약은 칸(`cells[].item`·`type`)에서 채운다 — 팔과 같은 순서다.
    알려진 종류(`KINDS`)만 남긴다. 어떤 입력에도 예외를 던지지 않는다.
    """
    if not isinstance(text, str) or not text.strip():
        return None
    try:
        raw = json.loads(text)
    except (ValueError, TypeError):
        return None
    if not isinstance(raw, dict) or raw.get("scene") != "v2":
        return None
    kinds: dict[str, str] = {}
    items = raw.get("items")
    if isinstance(items, dict):
        for item, kind in items.items():
            if isinstance(item, str) and item and kind in KINDS:
                kinds[item] = kind
    cells = raw.get("cells")
    for cell in cells if isinstance(cells, list) else ():
        if not isinstance(cell, dict):
            continue
        item, kind = cell.get("item"), cell.get("type")
        if isinstance(item, str) and item and item not in kinds and kind in KINDS:
            kinds[item] = kind
    return kinds


def parse_shelf_stock(text: str | None) -> dict[str, dict[str, int]] | None:
    """`/m0609/shelf/inventory`(장면 v2 JSON) → {약통 종류: {"present", "total"}}.

    재범 9/29 N3 "현재 알약통 N개·모듈 N개".

    `present` 는 칸(`cells[].present`)이 참인 수 — 스테이지가 들고 있는 것·조제기에 넣어 치운 것(--workcell-consume)은
    거짓이다. 알려진 종류(`KINDS`)만 센다. v2 가 아니거나 깨졌으면 None. 어떤 입력에도 예외를 던지지 않는다.
    """
    if not isinstance(text, str) or not text.strip():
        return None
    try:
        raw = json.loads(text)
    except (ValueError, TypeError):
        return None
    if not isinstance(raw, dict) or raw.get("scene") != "v2" or not isinstance(raw.get("cells"), list):
        return None
    stock = {kind: {"present": 0, "total": 0} for kind in KINDS}
    for cell in raw["cells"]:
        if isinstance(cell, dict) and cell.get("type") in KINDS:
            stock[cell["type"]]["total"] += 1
            stock[cell["type"]]["present"] += 1 if cell.get("present") is True else 0
    return stock


def refill_target(item_id: str, slots: list[dict[str, Any]], kinds: dict[str, str]) -> dict[str, Any]:
    """보충 중인 약 하나의 대상. `slots` 는 `DispenserStatus.slots`(dict), `kinds` 는 `parse_shelf_kinds` 결과.

    슬롯은 그 약의 빈 슬롯 중 A 먼저다 — `refill_planner.target_slot` 과 같은 규칙이다(goal 은 밖에서 안 보인다).
    모르면 None 이다.
    """
    empty = sorted(int(s.get("slot", 0)) for s in slots
                   if s.get("item_id") == item_id and int(s.get("count", 0)) == 0)
    kind = kinds.get(item_id)
    return {
        "item_id": item_id,
        "slot_name": ("A" if empty[0] == 0 else "B") if empty else None,
        "kind": kind,
        "target": TARGET_OF_KIND.get(kind) if kind else None,
    }
