"""fixture 재생 — ROS 없이 실물과 똑같은 API 를 내기 위한 것.

fixture 는 `fixtures/*.json`. 손으로 고치지 말고 `fixtures/make_pharmacy_loop.py` 를 고쳐라.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.faults import (
    LATE_JOIN_BACKLOG_SIM_S,
    Faults,
    apply_to_frame,
    clock_frozen_at,
    split_late_join,
)
from app.state import WorldState

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures"
DEFAULT_FIXTURE = FIXTURE_DIR / "pharmacy_loop.json"

#: `--order-pool` 을 안 주면 **저장소 원문**을 읽는다. 사본을 두지 않는다 —
#: 사본은 원문이 바뀌어도 안 따라가서, mock 에서만 되는 요청을 만들어 낸다.
_ORDER_POOL_RELATIVE = Path("src/rokey_p3_orchestrator/config/order_pool.yaml")


def _find_order_pool() -> Path | None:
    for base in Path(__file__).resolve().parents:
        candidate = base / _ORDER_POOL_RELATIVE
        if candidate.is_file():
            return candidate
    return None


DEFAULT_ORDER_POOL = _find_order_pool()

# 재생 틱은 **wall 기준**이다. 재생 배속과 무관하게 하트비트를 실물과 같은 주기로 내야
# 한다 — sim 기준으로 내면 --speed 0.01 같은 느린 재생에서 가짜 stale 이 뜬다.
HEARTBEAT_TICK_WALL_S = 0.1          # 10 Hz. gripper_holding 이 10 Hz 라 이게 최소 단위다.
SIGNAL_5HZ_EVERY_TICKS = 2           # 0.2 s = 5 Hz — 계약의 H 주기
FAST_SIGNAL_KEYS = ("gripper_holding",)  # 계약상 10 Hz
DISPENSER_EVERY_TICKS = 10           # 1.0 s = 1 Hz — DispenserStatus 는 L(변화 시 + 1 Hz)


def load_fixture(path: Path | str | None = None) -> dict[str, Any]:
    p = Path(path) if path else DEFAULT_FIXTURE
    return json.loads(p.read_text(encoding="utf-8"))


def apply_frame(state: WorldState, frame: dict[str, Any], wall: datetime) -> None:
    """fixture 프레임 한 장을 상태에 넣는다. 실물 모드의 ROS 콜백과 같은 자리다."""
    kind, data = frame["kind"], frame["data"]
    if kind == "event":
        state.note_event(data, wall)
    elif kind == "order":
        state.note_order(data)
    elif kind == "dispenser":
        state.note_dispenser(data, wall)
    elif kind == "belt":
        state.note_belt(data, wall)
    elif kind == "signal":
        state.note_signal(data["key"], data["value"], wall)
    elif kind == "cabinet":
        state.note_cabinet(data["order_id"], data["cabinet_id"], data["present"], wall)
    elif kind == "log":
        state.note_log(data, wall)
    # 모르는 kind 는 조용히 무시한다 — fixture 가 앞서 나가도 서버가 죽지 않게.


class MockPlayer:
    """fixture 를 sim 시각 순서대로 재생한다.

    `speed` 는 배속(5.0 이면 5배 빠르게). `loop` 면 끝에서 처음으로 돌아간다.
    """

    def __init__(self, state: WorldState, fixture: dict[str, Any], *,
                 speed: float = 1.0, loop: bool = False,
                 faults: Faults | None = None,
                 on_change: Callable[[], None] | None = None) -> None:
        self.state = state
        self.fixture = fixture
        self.faults = faults or Faults()
        # 마지막으로 본 하트비트 값. 실물에서 이 토픽들은 변화가 없어도 계속 발행된다
        # (Bool 하트비트, BeltState 5 Hz, DispenserStatus 1 Hz). fixture 는 변화 때만
        # 담고 있으므로, 재생 중에 여기서 계속 다시 실어 준다. 안 그러면 mock 이
        # 실물에는 없는 STATUS_STALE 을 만들어 낸다.
        self._last_signals: dict[str, bool] = {}
        self._last_belt: dict[str, Any] | None = None
        self._last_dispenser: dict[str, Any] | None = None
        self.speed = max(0.01, float(speed))
        self.loop = loop
        self.on_change = on_change or (lambda: None)
        self._task: asyncio.Task | None = None
        self._ticks = 0

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    async def _run(self) -> None:
        while True:
            await self._play_once()
            if not self.loop:
                return
            # 바퀴와 바퀴 사이에 리셋을 한 번 넣는다. sim_s 는 되감기지 않고 epoch 만 오른다.
            #
            # **RESET_BEGIN 과 RESET_DONE 을 반드시 짝으로 낸다.** BEGIN 만 내면
            # reset_in_progress 가 다음 바퀴가 제 RESET_DONE 에 닿을 때까지(한 바퀴의 3/4)
            # 계속 true 로 남아, 그동안 요청이 barrier_running 으로 거부된다.
            self._reset_now()

    def _reset_now(self) -> None:
        wall = datetime.now(timezone.utc)
        stamp = self.state.clock_sim_s or 0.0
        epoch = self.state.epoch + 1
        for name in ("RESET_BEGIN", "RESET_DONE"):
            self.state.note_event({"name": name, "epoch": epoch, "stamp": stamp}, wall)
        self.on_change()

    async def _play_once(self) -> None:
        frames: list[dict[str, Any]] = self.fixture["frames"]
        base_sim = self.state.clock_sim_s or 0.0
        if self.faults.late_join:
            # 늦게 붙은 구독자가 받는 backlog 를 먼저 한꺼번에 쏟는다.
            burst, frames = split_late_join(frames)
            wall = datetime.now(timezone.utc)
            for frame in burst:
                shifted = self._shift(frame, base_sim, wall)
                if shifted is not None:
                    apply_frame(self.state, shifted, wall)
            self._maybe_note_clock(base_sim + LATE_JOIN_BACKLOG_SIM_S, wall)
            self.on_change()
            # 쏟아 낸 구간은 이미 지난 것으로 친다. 안 그러면 첫 _tick 이 0 부터
            # 기다려 backlog 만큼을 통째로 다시 재운다.
            prev_t_start = LATE_JOIN_BACKLOG_SIM_S
        else:
            prev_t_start = 0.0
        epoch_shift = self.state.epoch - int(self.fixture.get("start_epoch", 0)) \
            if self.state.epoch else 0
        prev_t = prev_t_start
        for frame in frames:
            await self._tick(base_sim + prev_t, base_sim + frame["t"])
            prev_t = frame["t"]
            wall = datetime.now(timezone.utc)
            shifted = self._shift(frame, base_sim, wall, epoch_shift)
            if shifted is None:
                continue
            self._remember(shifted)
            apply_frame(self.state, shifted, wall)
            self._maybe_note_clock(base_sim + frame["t"], wall)
            self.on_change()

    def _shift(self, frame: dict[str, Any], base_sim: float, wall: datetime,
               epoch_shift: int = 0) -> dict[str, Any] | None:
        """프레임의 시각·epoch 을 이번 바퀴에 맞추고 고장 흉내를 적용한다.

        고장 흉내는 **여기서 데이터만** 비튼다. 상태·알람 경로는 실물과 같다.
        """
        shifted = dict(frame)
        data = dict(frame["data"])
        if "stamp" in data:
            data["stamp"] = base_sim + float(data["stamp"])
        if "epoch" in data and epoch_shift:
            data["epoch"] = int(data["epoch"]) + epoch_shift
        shifted["data"] = data
        return apply_to_frame(shifted, self.faults)

    def _remember(self, frame: dict[str, Any]) -> None:
        kind, data = frame["kind"], frame["data"]
        if kind == "signal":
            self._last_signals[data["key"]] = bool(data["value"])
        elif kind == "belt":
            self._last_belt = data
        elif kind == "dispenser":
            self._last_dispenser = data

    def _heartbeat(self, wall: datetime, tick: int) -> None:
        """하트비트 토픽을 계약과 같은 주기로 다시 실어 준다.

        실물에서 이 토픽들은 값이 안 변해도 계속 발행된다(H = 5 Hz, gripper_holding 10 Hz,
        DispenserStatus 는 L = 변화 시 + 1 Hz). fixture 는 변화 때만 담고 있으므로
        여기서 채워 주지 않으면 mock 이 실물에는 없는 STATUS_STALE 을 만들어 낸다.

        `stale:<key>` 고장이 켜진 신호만 빼놓는다. 그래야 그 신호만 낡는다.
        """
        slow_turn = tick % SIGNAL_5HZ_EVERY_TICKS == 0
        for key, value in self._last_signals.items():
            if key in self.faults.stale_keys:
                continue
            if key in FAST_SIGNAL_KEYS or slow_turn:
                self.state.note_signal(key, value, wall)
        if slow_turn and self._last_belt is not None and "belt" not in self.faults.stale_keys:
            self.state.note_belt(self._last_belt, wall)
        if tick % DISPENSER_EVERY_TICKS == 0 and self._last_dispenser is not None:
            self.state.note_dispenser(self._last_dispenser, wall)

    def _maybe_note_clock(self, sim_s: float, wall: datetime) -> None:
        """clock_stop 이 켜져 있고 얼릴 시각을 지났으면 /clock 을 흘리지 않는다."""
        if not clock_frozen_at(self.faults, sim_s):
            self.state.note_clock(sim_s, wall)

    async def _tick(self, from_sim: float, to_sim: float) -> None:
        """두 프레임 사이를 /clock 과 하트비트를 흘리면서 기다린다.

        그냥 sleep 하면 그동안 /clock 이 멈추고 신호가 낡은 것으로 보여,
        CLOCK_STOPPED·STATUS_STALE 이 가짜로 뜬다.
        """
        now_sim = from_sim
        while to_sim - now_sim > 1e-9:
            wall_step = min(HEARTBEAT_TICK_WALL_S, (to_sim - now_sim) / self.speed)
            await asyncio.sleep(wall_step)
            now_sim = min(to_sim, now_sim + wall_step * self.speed)
            self._ticks += 1
            wall = datetime.now(timezone.utc)
            self._maybe_note_clock(now_sim, wall)
            self._heartbeat(wall, self._ticks)
