"""오케스트레이터가 왜 goal 을 거부했는지 `/rosout` 에서 찾는다. 순수 함수.

goal REJECT 에는 **사유 자리가 없다**(계약 2.5절: 거부는 goal 거부로 끝나고 이벤트도 없다).
그래서 사람에게 보여 줄 말이 없다. 오케스트레이터는 거부할 때 로그를 한 줄 남기므로,
그 줄을 찾아 쓴다.

찾는 형식(팔 #201):

    Deliver goal 거부 <request_id>: <사유>

**`request_id` 가 있는 줄만 쓴다.** 시각만으로 맞추면 남의 거부 사유를 엉뚱한 요청에
붙일 수 있다. 지금 오케스트레이터는 `'Deliver goal 거부: {reason}'` 으로 request_id 없이
찍으므로(`orchestrator_node.py:323`), **#201 전까지는 매칭이 안 되고 사유는 빈 값이다.**
없는 사유를 지어내지 않는다.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import Any

#: 이 시간(wall) 안의 로그만 본다. 더 오래된 줄은 지난 요청의 것일 수 있다.
LOOKBACK_S = 10.0

_PREFIX = "Deliver goal 거부"


def _pattern(request_id: str) -> re.Pattern[str]:
    # request_id 는 사용자 입력이라 정규식 메타문자가 들어올 수 있다.
    return re.compile(rf"{_PREFIX}\s+{re.escape(request_id)}\s*:\s*(?P<reason>.+)")


def find_reject_reason(logs: Sequence[dict[str, Any]], request_id: str,
                       now: datetime, lookback_s: float = LOOKBACK_S) -> str | None:
    """가장 최근의 거부 사유. 못 찾으면 None.

    `logs` 는 `WorldState.logs`(도착 순서). 뒤에서부터 보되 창 밖으로 나가면 멈춘다.
    """
    if not request_id:
        return None
    pattern = _pattern(request_id)
    floor = now - timedelta(seconds=lookback_s)
    for entry in reversed(logs):
        wall = entry.get("wall")
        if isinstance(wall, str):
            try:
                seen = datetime.fromisoformat(wall.replace("Z", "+00:00"))
            except ValueError:
                seen = None
            if seen is not None and seen < floor:
                break
        found = pattern.search(str(entry.get("message") or ""))
        if found:
            return found.group("reason").strip() or None
    return None
