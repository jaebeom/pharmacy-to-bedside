"""주문 풀 — `GET /api/order_pool` (api.md §7.3). 순수하게 유지한다(ROS import 없음).

왜 필요한가: orchestrator 는 `order_id` 가 **주문 풀에 있고 미사용**일 때만 요청을 수락한다.
웹에서 자유 입력을 받으면 거의 항상 goal 거부로 끝나므로, 고를 수 있는 목록을 서버가 준다.

**스키마는 하나로 고정됐다** (작전이 origin/main 원문 확인):

    version: 1
    orders:
      - {order_id: ord-0001, patient_id: "1001", item_id: drug-amox, bed: bed_a1}
      - {order_id: ord-0002, patient_id: "1002", item_id: drug-ibu, bed: bed_a2, mode: urgent}

`mode` 는 `single` | `urgent` 이고 기본은 `single`.
**숫자로 보이는 ID 는 YAML 에서 따옴표가 필수다** — 정수로 읽히면 orchestrator 가 거부한다.
그래서 여기서도 정수로 읽힌 것은 쓰지 않고 `problems` 에 담아 돌려준다(조용히 고치면
웹에서는 되는데 실물에서 거부되는, 제일 나쁜 종류의 버그가 된다).

묶음은 풀에 표현이 없다. 웹이 주문 여러 개를 골라 `mode` 2·3 과 `destination_id` 를 직접 정한다.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

POOL_MODES = {"single": 0, "urgent": 1}
DEFAULT_POOL_MODE = "single"


class PoolResult:
    """풀 파싱 결과. 주문과 함께 **왜 버렸는지**를 들고 다닌다."""

    def __init__(self, orders: list[dict[str, Any]], problems: list[str]) -> None:
        self.orders = orders
        self.problems = problems


def _quoted_str(raw: Any) -> tuple[str | None, str | None]:
    """YAML 에서 문자열로 읽혔는가. (값, 문제) 를 돌려준다.

    정수로 읽혔다면 따옴표가 빠진 것이다 — 값을 str() 로 고쳐 주지 않는다.
    """
    if isinstance(raw, (bool, int)):
        return None, f"따옴표가 빠져 정수로 읽혔다: {raw}"
    if not isinstance(raw, str):
        return None, None if raw is None else f"문자열이 아니다: {raw!r}"
    raw = raw.strip()
    return (raw or None), None


def parse_pool(doc: Any) -> PoolResult:
    """`{version: 1, orders: [...]}` 한 모양만 받는다."""
    problems: list[str] = []
    if not isinstance(doc, dict):
        return PoolResult([], ["최상위가 맵이 아니다 (version·orders 가 있어야 한다)"])

    version = doc.get("version")
    if version is not None and version != 1:
        problems.append(f"모르는 version: {version!r} (1 을 기대)")

    raw_orders = doc.get("orders")
    if not isinstance(raw_orders, list):
        return PoolResult([], [*problems, "orders 가 리스트가 아니다"])

    orders: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(raw_orders):
        where = f"orders[{index}]"
        if not isinstance(item, dict):
            problems.append(f"{where}: 맵이 아니다")
            continue

        order_id, problem = _quoted_str(item.get("order_id"))
        if problem:
            problems.append(f"{where}.order_id: {problem}")
            continue
        if order_id is None:
            problems.append(f"{where}: order_id 가 없다")
            continue
        if order_id in seen:
            problems.append(f"{where}: order_id 가 중복이다: {order_id}")
            continue

        patient_id, problem = _quoted_str(item.get("patient_id"))
        if problem:
            # 여기서 str() 로 고쳐 주면 웹에서는 되고 실물에서 거부된다. 버린다.
            problems.append(f"{where}.patient_id: {problem}")
            continue

        item_id, _ = _quoted_str(item.get("item_id"))
        bed, _ = _quoted_str(item.get("bed"))

        mode_raw = item.get("mode")
        mode = DEFAULT_POOL_MODE if mode_raw is None else str(mode_raw).strip().lower()
        if mode not in POOL_MODES:
            problems.append(f"{where}.mode: 모르는 값 {mode_raw!r} (single|urgent)")
            mode = DEFAULT_POOL_MODE

        seen.add(order_id)
        orders.append({
            "order_id": order_id,
            "patient_id": patient_id,
            "item_id": item_id,
            "bed": bed,
            "mode": mode,
            "mode_value": POOL_MODES[mode],
        })
    return PoolResult(orders, problems)


def load_pool(path: str | Path | None) -> PoolResult:
    """`--order-pool` 로 받은 파일을 읽는다."""
    if not path:
        return PoolResult([], [])
    p = Path(path)
    if not p.is_file():
        return PoolResult([], [f"파일이 없다: {p}"])
    try:
        import yaml
        return parse_pool(yaml.safe_load(p.read_text(encoding="utf-8")))
    except Exception as exc:  # noqa: BLE001 - 풀이 깨졌다고 서버가 죽으면 안 된다
        return PoolResult([], [f"읽지 못했다: {exc}"])


def pool_from_fixture(fixture: dict[str, Any]) -> PoolResult:
    """`--order-pool` 없이 mock 으로 띄웠을 때, fixture 의 주문으로 풀을 만든다.

    프론트가 풀 파일 없이도 고르기 UI 를 만들 수 있게 하려는 것뿐이다.
    """
    from app.request_detail import parse_request_detail

    orders: list[dict[str, Any]] = []
    seen: set[str] = set()
    for frame in fixture.get("frames") or []:
        if frame.get("kind") != "event":
            continue
        data = frame["data"]
        if data.get("name") != "REQUEST_ACCEPTED":
            continue
        parsed = parse_request_detail(data.get("detail"))
        destination = (parsed or {}).get("destination_id")
        for order_id, extra in (parsed or {}).get("orders", {}).items():
            if order_id in seen:
                continue
            seen.add(order_id)
            orders.append({**extra, "order_id": order_id, "bed": destination,
                           "mode": DEFAULT_POOL_MODE,
                           "mode_value": POOL_MODES[DEFAULT_POOL_MODE]})
    return PoolResult(orders, [])


def with_used(orders: list[dict[str, Any]], used: set[str]) -> list[dict[str, Any]]:
    """풀 목록에 사용 여부를 붙인다. 프론트는 `used=false` 만 고를 수 있어야 한다."""
    return [{**order, "used": order["order_id"] in used} for order in orders]
