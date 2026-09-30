"""고장 흉내 — **개발 전용. 시연 절차에 없다.**

알람은 대부분 실물이 고장 났을 때만 뜬다. 그래서 화면이 그 알람을 제대로 그리는지
시연 전에 확인할 방법이 없다. 이 모듈은 **mock 재생 데이터만** 비틀어서 고장을 만든다.

**알람 규칙과 `WorldState` 코드 경로는 손대지 않는다.** 실물이 타는 그 길을 그대로 타야
확인에 의미가 있다 — 화면에 알람을 억지로 꽂아 넣는 것이 아니다.

    --mock-fault clock_stop
    --mock-fault stale:m0609_at_home,refill_fail

`--mock` 없이 주면 기동을 거부한다.
"""

from __future__ import annotations

from typing import Any

# clock_stop 이 시계를 얼려 버리는 sim 시각. 앞부분은 정상으로 보이다가 멈춘다.
CLOCK_FREEZE_AT_SIM_S = 10.0

STALE_PREFIX = "stale:"
SIMPLE_FAULTS = ("stuck_reset", "clock_stop", "refill_fail", "order_timeout", "late_join")

# late_join 이 처음에 한꺼번에 쏟아 낼 구간(sim 초). 이 안의 이벤트를 작성자별로 묶어 낸다.
LATE_JOIN_BACKLOG_SIM_S = 25.0

# stale:<key> 에 쓸 수 있는 신호 키 (status_view 와 같다)
STALE_KEYS = ("arm_at_home", "base_stopped", "gripper_holding", "belt", "m0609_at_home")

HELP = (
    "이름: " + " | ".join(SIMPLE_FAULTS) + " | stale:<신호키>"
    + "   (신호키: " + ", ".join(STALE_KEYS) + ")"
)


class FaultSpecError(ValueError):
    """모르는 고장 이름. 오타를 조용히 무시하면 '왜 안 뜨지' 로 시간을 버린다."""


class Faults:
    """어떤 고장을 켰나. 아무것도 안 켜면 모든 검사가 False 다."""

    def __init__(self, names: list[str] | None = None) -> None:
        self.names = list(names or [])
        self.stuck_reset = "stuck_reset" in self.names
        self.clock_stop = "clock_stop" in self.names
        self.refill_fail = "refill_fail" in self.names
        self.order_timeout = "order_timeout" in self.names
        self.late_join = "late_join" in self.names
        self.stale_keys = {n[len(STALE_PREFIX):] for n in self.names
                           if n.startswith(STALE_PREFIX)}

    def __bool__(self) -> bool:
        return bool(self.names)

    @property
    def active(self) -> list[str]:
        """snapshot 과 기동 로그에 싣는 목록. 화면이 '고장 흉내 중' 배지를 띄운다."""
        return list(self.names)


def parse_faults(spec: str | None) -> Faults:
    """`"clock_stop,stale:belt"` → Faults. 모르는 이름이면 FaultSpecError."""
    if not spec:
        return Faults()
    names: list[str] = []
    for raw in spec.split(","):
        name = raw.strip()
        if not name:
            continue
        if name in SIMPLE_FAULTS:
            names.append(name)
        elif name.startswith(STALE_PREFIX):
            key = name[len(STALE_PREFIX):]
            if key not in STALE_KEYS:
                raise FaultSpecError(
                    f"모르는 신호 키: {key!r} (쓸 수 있는 것: {', '.join(STALE_KEYS)})")
            names.append(name)
        else:
            raise FaultSpecError(f"모르는 고장 이름: {name!r}\n{HELP}")
    return Faults(names)


def apply_to_frame(frame: dict[str, Any], faults: Faults) -> dict[str, Any] | None:
    """fixture 프레임 한 장을 고장에 맞게 비튼다. None 이면 그 프레임을 버린다.

    **여기서만 데이터를 바꾼다.** 상태 조립과 알람 판정은 손대지 않는다.
    """
    if not faults:
        return frame
    kind, data = frame["kind"], frame["data"]

    if kind == "event":
        name = data.get("name")
        # 보충이 끝나지 않는다 → REFILL_FAILED
        if faults.refill_fail and name in ("REFILL_DONE", "DISPENSER_RESUMED"):
            return None

    elif kind == "signal":
        # 그 신호가 t=0 이후로 갱신되지 않는다 → STATUS_STALE
        if data.get("key") in faults.stale_keys and frame["t"] > 0.0:
            return None

    elif kind == "dispenser":
        # 보충이 안 끝났으니 조제기도 계속 멈춰 있어야 앞뒤가 맞는다
        if faults.refill_fail and frame["t"] > 26.0 and not data.get("paused_item_ids"):
            return None

    elif kind == "order":
        # 주문이 시간초과로 닫힌다 → TIMEOUT
        if faults.order_timeout and int(data.get("state", 0)) == 11:
            return {**frame, "data": {**data, "state": 13, "reason": "delivery_timeout"}}

    return frame


def clock_frozen_at(faults: Faults, sim_s: float) -> bool:
    """clock_stop 이 켜졌고 얼릴 시각을 지났는가."""
    return faults.clock_stop and sim_s >= CLOCK_FREEZE_AT_SIM_S


def split_late_join(frames: list[dict[str, Any]]) -> tuple[list[dict[str, Any]],
                                                           list[dict[str, Any]]]:
    """`late_join` 의 (먼저 쏟아 낼 것, 그 뒤 평소대로 재생할 것).

    `/events` 는 `transient_local` 이라 **늦게 붙으면 지난 이벤트가 작성자별로 뭉쳐서
    한꺼번에 온다.** mock 은 한 줄로 재생하니 도착 순서 = 시각 순서라 그 상황이 안 생기고,
    그래서 "seq 가 낮은데 event_key 가 늦은 이벤트" 를 다루는 코드가 검증되지 않는다.
    오늘 그 경로에서 버그가 둘 났다(화면의 중복 판정, 서버의 페이지 커서).

    쏟아 내는 묶음 안에서는 **작성자(robot_id)별로 모아** 내보낸다. 실물에서 뭉쳐 오는
    모양이 그렇다. 시각이 아니라 도착 순서만 바꾸는 것이고, 프레임 내용은 안 건드린다.
    """
    backlog = [f for f in frames if f["t"] <= LATE_JOIN_BACKLOG_SIM_S]
    rest = [f for f in frames if f["t"] > LATE_JOIN_BACKLOG_SIM_S]

    # 이벤트가 아닌 것(신호·조제기·벨트·로그)은 최신값만 의미가 있으므로 순서 그대로 먼저.
    others = [f for f in backlog if f["kind"] != "event"]
    events = [f for f in backlog if f["kind"] == "event"]

    by_author: dict[str, list[dict[str, Any]]] = {}
    for frame in events:
        by_author.setdefault(frame["data"].get("robot_id") or "", []).append(frame)
    grouped = [f for author in sorted(by_author) for f in by_author[author]]
    return others + grouped, rest
