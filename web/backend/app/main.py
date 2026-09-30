"""관제 웹 서비스 백엔드 — FastAPI 앱. 계약은 api.md 가 기준이다.

    python -m app.main --mock          # ROS 없이 fixture 재생 (프론트 개발용)
    python -m app.main                 # 실물 (ROS 2 Jazzy 환경 필요)

환자 식별자(patient_id)는 **서버 로그에 남기지 않는다.** 합성 주문 풀 전제라 해도
로그로 새는 경로를 처음부터 만들지 않는다.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import os
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, NamedTuple

from fastapi import FastAPI, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from app.alarms import (
    REFILL_TIMEOUT_SIM_S,
    RESET_TIMEOUT_WALL_S,
    available_stock,
    outcome_for,
    unavailable_items,
)
from app.faults import HELP as FAULT_HELP
from app.faults import Faults, FaultSpecError, parse_faults
from app.film import queue_rows
from app import live_sensors
from app.floorplan import MapError, load_map, map_meta
from app.mock import DEFAULT_ORDER_POOL, MockPlayer, load_fixture
from app.qr_info import QrResolver
from app.order_pool import PoolResult, load_pool, pool_from_fixture, with_used
from app.reject_reason import find_reject_reason
from app.request_detail import MODE_BATCH_ROOM
from app.zones import (MOCK_ZONES, default_zones_path, destinations, is_zone_id, load_zones,
                       rooms_of_orders, zone_rows)
from app.state import WorldState, iso_or_none

# mock 의 리셋이 RESET_BEGIN 에서 RESET_DONE 까지 걸리는 시간 (wall).
# 실물은 서버 탐색을 포함해 30 s 까지 걸리지만, 개발에서 그만큼 기다릴 이유는 없다.
MOCK_RESET_SECONDS = 1.0

# WS push 를 합치는 주기 (api.md §3: 최대 5 Hz)
WS_MIN_INTERVAL_S = 0.2

# 변화가 없어도 이 주기로는 한 번 보낸다.
# **조용한 것과 죽은 것을 클라이언트가 구분할 수 있게 하려는 것이다.** 변화 때만 보내면
# 보충 대기처럼 조용한 구간이 10 s 넘게 이어져, 화면이 "갱신이 멎었다" 와 구별할 수 없다.
WS_IDLE_PUSH_S = 1.0

LOG_LEVELS = {"warn": 30, "error": 40, "fatal": 50}
LOG_LEVEL_NAMES = {10: "debug", 20: "info", 30: "warn", 40: "error", 50: "fatal"}

# mock 이 zones.yaml 대신 쓰는 목적지는 app/zones.py 의 MOCK_ZONES 다 — origin/main 에 실제로
# 있는 bed_a1·station_a 둘뿐이다. 실물 판정은 orchestrator 가 zones.yaml 로 하므로
# mock 통과가 실물 통과를 뜻하지 않는다.


class Refusal(NamedTuple):
    """거부 한 건. `detail` 은 **무엇 때문에 막혔는지를 구조로** 담는다.

    `message` 는 사람이 읽는 문구라 다듬을 수 있고, 화면이 거기서 값을 뽑으면 문구를 고칠 때
    조용히 깨진다(계약이 "`message` 로 분기하지 마라" 라고 하면서 값을 문장 안에만 두면
    파싱을 강요하는 셈이다). 막힌 대상은 `detail` 에 따로 싣는다.
    """

    status: int
    code: str
    message: str
    detail: dict[str, Any] = {}


def error(status: int, code: str, message: str,
          detail: dict[str, Any] | None = None) -> JSONResponse:
    body: dict[str, Any] = {"code": code, "message": message}
    if detail:
        body["detail"] = detail
    return JSONResponse({"error": body}, status_code=status)


# 요청 거부 사유 코드. **화면 분기는 message 가 아니라 이 코드로 한다** — 문구는 다듬을 수 있다.
REJECT_CODES = (
    "bad_mode_for_orders",    # 1인·긴급인데 주문이 둘 이상이다 (400)
    "mixed_rooms",            # 병실 묶음(mode 2)인데 주문의 병상이 두 병실 이상이다 (400)
    "duplicate_request_id",   # request_id 가 이미 쓰였다
    "empty_orders",           # orders 가 비었다
    "bad_destination",        # destination_id 가 구역 ID 모양이 아니다
    "unknown_or_used_order",  # 주문 풀에 없거나 이미 쓰인 order_id
    "refill_in_progress",     # 그 약품이 재고 0·PAUSED 다
    "insufficient_stock",     # 요청한 개수가 가용 재고보다 많다
    "trip_in_progress",       # 진행 중 트립이 있다
    "barrier_running",        # 리셋 중이다
    "rejected",               # 그 밖 — 실물에서 사유 없이 거부된 경우가 여기로 온다
)

#: mock 에서 평면도가 있을 때 AMR 을 세워 두는 구역.
MOCK_ROBOT_ZONE = "dock_1"

#: 주문을 하나만 받는 모드. `trip_fsm._build_stops` 가 정거장을 못 만들어 사유 없이 거부한다.
SINGLE_ORDER_MODES = {0: "1인(mode 0)", 1: "긴급(mode 1)"}


def check_request(body: dict[str, Any], state: WorldState, now: datetime,
                  pool_ids: set[str], used: set[str],
                  order_rooms: dict[str, str] | None = None) -> Refusal | None:
    """orchestrator 의 수락 조건을 미리 검사한다. 통과하면 None, 아니면 (HTTP, code, 사유).

    **검사 순서는 `orchestrator_node._on_deliver_goal`(:303-325) 원문과 같게 맞췄다.**
    여러 조건이 한꺼번에 걸릴 때 실물과 같은 코드가 나오게 하려는 것이다.

    **실물에서도 이 검사를 보낸다** — goal 거부에는 사유가 안 실려 오고 Event 도 안 남기
    때문이다. 여기서 못 잡고 거부된 것은 `rejected` 로 떨어진다.
    """
    # 0. 본문 형식 — 이건 orchestrator 의 조건이 아니라 우리 입력 검사다. 그래서 400 이고,
    #    id 가 없으면 아래 검사를 할 수조차 없으므로 맨 앞이다.
    request_id = body.get("request_id")
    if not request_id:
        return Refusal(400, "bad_request", "request_id 가 필요하다")
    orders = body.get("orders") or []
    for order in orders:
        if not (order or {}).get("order_id"):
            return Refusal(400, "bad_request", "order 에 order_id 가 없다")

    # 0.5 모드와 주문 수 — **입력이 스스로 모순**이다. 서버 상태를 보기 전에 답할 수 있고,
    #     그래야 사람이 "기다리면 되나?" 로 헷갈리지 않는다. 기다려도 안 풀린다.
    #     실습8 의 묶음 거부 2회가 이것이었다(mode 0 에 주문 3개 → 사유 없는 goal 거부).
    mode_label = SINGLE_ORDER_MODES.get(body.get("mode"))
    if mode_label and len(orders) > 1:
        return Refusal(400, "bad_mode_for_orders",
                       f"{mode_label}은 주문 1건만 — {len(orders)}건을 보냈다",
                       {"mode": body.get("mode"), "order_count": len(orders)})

    # 0.6 병실 묶음(mode 2)인데 주문의 병상이 두 병실 이상 — 이것도 입력이 스스로 모순이다.
    #     계약은 "한 병실의 병상을 차례로" 인데 orchestrator(`trip_fsm._build_stops`)는 병실을
    #     모른다. 병상마다 정거장을 만들어 그대로 돈다 — 두 병실을 한 트립으로 도는 것이 조용히
    #     통과한다. 병실은 zones 의 `room` 이고(`order_rooms`), 모르는 주문은 판단에서 뺀다.
    if body.get("mode") == MODE_BATCH_ROOM and order_rooms:
        by_room: dict[str, list[str]] = {}
        for order in orders:
            room = order_rooms.get(order["order_id"])
            if room:
                by_room.setdefault(room, []).append(order["order_id"])
        if len(by_room) > 1:
            rooms = [{"room": room, "order_ids": ids} for room, ids in sorted(by_room.items())]
            return Refusal(400, "mixed_rooms",
                           "병실 묶음은 한 병실만 — "
                           + ", ".join(f"{r['room']} {len(r['order_ids'])}건" for r in rooms),
                           {"mode": MODE_BATCH_ROOM, "rooms": rooms})

    # 1. fsm.resetting — 리셋 barrier 가 도는 중. 큐에 넣지 않고 바로 거부한다.
    if state.snapshot_reset_in_progress():
        return Refusal(409, "barrier_running", "리셋 barrier 중이다")

    # 2. accept_after — RESET_DONE 뒤에도 약 3 s wall 은 더 거부한다 (계약 6절 5).
    if not state.accepting_requests(now):
        return Refusal(409, "barrier_running", "리셋 barrier 가 아직 안 끝났다",
                       {"accept_after_wall": iso_or_none(state.accept_after_wall()),
                        "accept_in_s": state.accept_in_s(now)})

    # 3. 빈 orders
    if not orders:
        return Refusal(409, "empty_orders", "orders 가 비었다")

    # 4. 중복 request_id
    if request_id in state.used_request_ids:
        return Refusal(409, "duplicate_request_id", f"request_id 가 이미 쓰였다: {request_id}",
                       {"request_id": request_id})

    # 5. 구역 ID 정규식 (zones.yaml 을 보지 않는다)
    destination_id = body.get("destination_id") or ""
    if not is_zone_id(destination_id):
        return Refusal(409, "bad_destination",
                       f"destination_id 가 구역 ID 모양이 아니다: {destination_id or '(비었음)'}",
                       {"destination_id": destination_id})

    # 6·7. 주문 풀에 없음 → 이미 쓴 주문
    for order in orders:
        order_id = order["order_id"]
        if pool_ids and order_id not in pool_ids:
            return Refusal(409, "unknown_or_used_order", f"주문 풀에 없는 order_id: {order_id}",
                               {"order_id": order_id})
    for order in orders:
        if order["order_id"] in used:
            return Refusal(409, "unknown_or_used_order",
                           f"이미 쓰인 order_id: {order['order_id']}",
                           {"order_id": order["order_id"]})

    # 7.5 보충 중 — 재고 0 이거나 PAUSED 인 약품은 지금 낼 수 없다. orchestrator 는 수락한 뒤
    #     적재에서 ABORT(out_of_stock) 으로 끝내므로(실습8: 1.2 s 만에 죽었다), 여기서 막아야
    #     사람이 그 자리에서 이유를 안다.
    blocked = unavailable_items(state.dispenser)
    if blocked:
        for order in orders:
            item = (order or {}).get("item_id")
            if item and item in blocked:
                return Refusal(409, "refill_in_progress", f"보충 중 — 재개 뒤 다시 ({item})",
                               {"item_id": item, "order_id": order.get("order_id")})

    # 7.6 재고가 요청 수를 못 받친다. refill_in_progress 는 **요청 시점에 이미 0** 인 것만
    #     막는다 — 묶음 안에서 서로 잡아먹는 것은 못 막는다. 실습9: amox 재고 1 에 묶음으로
    #     amox 주문 2개가 들어가 앞의 것이 마지막 1개를 쓰고 뒤의 것이 ABORT(out_of_stock)로
    #     끝났다. 시연 화면에 error 알람이 남는다.
    stock = available_stock(state.dispenser)
    wanted: dict[str, int] = {}
    for order in orders:
        item = (order or {}).get("item_id")
        if item:
            wanted[item] = wanted.get(item, 0) + 1
    # 슬롯에 없는 품목은 키가 없다 — 모르는 것으로 거부하지 않는다.
    # **모자란 것을 전부 모은다.** 한 건만 말하면, 두 품목이 모자랄 때 운영자가 하나를 빼고
    # 다시 보내 두 번째 거부를 받는다. 한 번에 다 말해야 한 번에 고친다.
    shortages = [{"item_id": item, "requested": need, "available": stock[item]}
                 for item, need in sorted(wanted.items())
                 if item in stock and need > stock[item]]
    if shortages:
        first = shortages[0]
        if len(shortages) == 1:
            message = (f"재고 부족 — {first['item_id']} {first['requested']}개 필요, "
                       f"{first['available']}개 가능")
        else:
            other = ", ".join(f"{s['item_id']} {s['requested']}/{s['available']}"
                              for s in shortages[1:])
            message = (f"재고 부족 — {first['item_id']} {first['requested']}개 필요, "
                       f"{first['available']}개 가능 (그 밖에 {other})")
        return Refusal(409, "insufficient_stock", message, {**first, "shortages": shortages})

    # 8. fsm.accepts — '진행 중 트립이 있거나 정거장을 만들 수 없다'.
    #    둘을 밖에서 구분할 수 없으므로, 트립이 실제로 열려 있을 때만 trip_in_progress 다.
    if state.trip_open:
        return Refusal(409, "trip_in_progress", "진행 중 트립이 있다",
                       {"request_id": state.current_request_id})
    return None


class Hub:
    """붙어 있는 WS 들에게 snapshot 변화를 밀어 준다. 5 Hz 로 합친다."""

    def __init__(self, state: WorldState) -> None:
        self.state = state
        self.clients: set[WebSocket] = set()
        self._dirty = asyncio.Event()
        self._task: asyncio.Task | None = None
        self._last_alarm_ids: tuple[str, ...] = ()
        self._last_speed: tuple[Any, Any] | None = None

    def mark_dirty(self) -> None:
        self._dirty.set()

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._pump())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    async def _pump(self) -> None:
        while True:
            # 시간이 지나면 조용해도 한 번 보낸다 — 살아 있다는 신호가 된다.
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(self._dirty.wait(), timeout=WS_IDLE_PUSH_S)
            self._dirty.clear()
            if self.clients:
                snap = self.state.snapshot(datetime.now(timezone.utc))
                await self.broadcast("snapshot", snap)
                # 알람은 변화분이 아니라 **매번 전체 목록**을 보낸다. 몇 개 안 되고,
                # 제거 표식 없는 델타는 클라이언트가 사라짐을 알 수 없다.
                ids = tuple(a["id"] for a in snap["alarms"])
                if ids != self._last_alarm_ids:
                    self._last_alarm_ids = ids
                    await self.broadcast("alarms", snap["alarms"])
                # 속도 제한은 값(비율·정지 사유)이 바뀔 때만 따로 보낸다. 나이만 바뀐 것은 snapshot 으로 충분하다.
                speed = snap["signals"].get("speed_limit")
                key = None if speed is None else (speed["speed_limit_pct"], speed["stop_reason"])
                if speed is not None and key != self._last_speed:
                    self._last_speed = key
                    await self.broadcast("speed_limit", speed)
            await asyncio.sleep(WS_MIN_INTERVAL_S)

    async def broadcast(self, kind: str, data: Any) -> None:
        if not self.clients:
            return
        envelope = {
            "type": kind,
            "seq": self.state.seq,
            "server_time": self.state.snapshot(datetime.now(timezone.utc))["server_time"],
            "data": data,
        }
        dead = []
        for ws in list(self.clients):
            try:
                await ws.send_json(envelope)
            except Exception:  # noqa: BLE001 - 끊긴 소켓은 조용히 걷어낸다
                dead.append(ws)
        for ws in dead:
            self.clients.discard(ws)


def deployment_info(roles: list[str] | None, peer: str | None, domain: str | None) -> dict[str, Any]:
    """snapshot.deployment. 역할이 비었으면 한 대 기본(null). 도메인은 숫자일 때만."""
    peer = (peer or "").strip() or None
    return {"multi_pc": peer is not None, "roles": list(roles) if roles else None, "peer": peer,
            "domain_id": int(domain) if domain and domain.strip().isdigit() else None}


def create_app(*, mock: bool = True, fixture_path: str | None = None,
               speed: float = 1.0, loop: bool = False, allow_commands: bool = False,
               refill_timeout: float = REFILL_TIMEOUT_SIM_S,
               reset_timeout: float = RESET_TIMEOUT_WALL_S,
               order_pool: str | None = None, static_dir: str | None = None,
               zones_file: str | None = None, show_evaluator: bool = False,
               faults: Faults | None = None, robot_id: str = "amr_1",
               map_file: str | None = None, autostart: bool = True,
               live: bool = False, roles: list[str] | None = None, peer: str | None = None,
               catalog: str | None = None, dispenser_file: str | None = None) -> FastAPI:
    state = WorldState(
        refill_timeout_sim_s=refill_timeout,
        reset_timeout_wall_s=reset_timeout,
        source_mode="mock" if mock else "ros",
        commands_enabled=allow_commands,
        show_evaluator=show_evaluator,
    )
    faults = faults or Faults()
    state.mock_faults = faults.active
    # 손 카메라 QR 판독의 요약(api.md §1.12). QR 안 ID 를 주문 풀·약 카탈로그·조제기 파일로 푼다. 없으면 ID 만.
    state.robot_id = robot_id
    state.qr_resolver = QrResolver(load_pool(order_pool).orders if order_pool else [], catalog, dispenser_file)
    # 배치(api.md §1.10). 두 PC 모드는 demo_v2.sh 가 --roles·--peer 로 알려 준다. 도메인은 이 프로세스의 것이다.
    state.deployment = deployment_info(roles, peer, None if mock else os.environ.get("ROS_DOMAIN_ID"))
    # 카메라·스캔 실시간(api.md §1.8). 기본 꺼짐 — 끄면 이 객체가 없고 구독도 0 이다.
    state.live = None
    if live:
        ok, why = live_sensors.available()
        if ok:
            state.live = live_sensors.LiveSensors(robot_id)
        else:
            print(f"** --live-sensors 를 끈다: {why} **")
    hub = Hub(state)

    # 평면도 — `--map-file` 을 준 실행(병원 월드)에서만 켠다. 안 주면 /api/map 은 404 이고
    # snapshot.robots 는 빈 배열이다(지금 동작 그대로). 못 읽으면 이유를 들고 404 다.
    floor_map: dict[str, Any] | None = None
    map_problem = "지도를 주지 않았다(--map-file)"
    if map_file:
        try:
            floor_map = load_map(map_file)
        except MapError as exc:
            map_problem = str(exc)

    bridge = None
    if not mock:
        # rclpy 는 여기서만 들어온다. --mock 경로는 ROS 없이 돌아야 하므로 지연 import 다.
        from app.ros_bridge import RosBridge
        bridge = RosBridge(state, robot_id=robot_id, show_evaluator=show_evaluator,
                           allow_commands=allow_commands, on_change=hub.mark_dirty,
                           track_pose=floor_map is not None, live=state.live)
    player: MockPlayer | None = None
    if mock:
        player = MockPlayer(state, load_fixture(fixture_path), speed=speed, loop=loop,
                            faults=faults, on_change=hub.mark_dirty)

    @contextlib.asynccontextmanager
    async def lifespan(_: FastAPI):
        # Hub 는 WS 서빙의 일부라 언제나 띄운다. `autostart` 가 끄는 것은 **재생기**뿐이다
        # (테스트가 상태를 직접 넣어 결정적으로 시험할 수 있게).
        hub.start()
        if autostart and player is not None:
            player.start()
        if autostart and bridge is not None:
            bridge.start()
        mock_live = None
        if autostart and mock and state.live is not None:
            mock_live = asyncio.create_task(_mock_live(state, robot_id, hub.mark_dirty))
        yield
        if mock_live is not None:
            mock_live.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await mock_live
        if player is not None:
            await player.stop()
        if bridge is not None:
            bridge.stop()
        await hub.stop()

    app = FastAPI(title="ROKEY P3 관제 백엔드", version="0.1.0", lifespan=lifespan)
    app.state.world = state
    app.state.hub = hub
    app.state.player = player
    app.state.bridge = bridge
    app.state.allow_commands = allow_commands
    app.state.order_pool = order_pool

    # 개발 편의: **mock 일 때만** 교차 출처를 연다. 프론트가 별도 포트에서 정적 파일을 띄우기 때문.
    # 실물 모드에서는 켜지 않는다 — 그때는 --static 으로 같은 출처가 되거나 리버스 프록시를 둔다.
    if mock:
        app.add_middleware(
            CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

    def now() -> datetime:
        return datetime.now(timezone.utc)

    @app.get("/api/snapshot")
    def get_snapshot() -> dict[str, Any]:
        return state.snapshot(now())

    @app.get("/api/events")
    def get_events(
        epoch: str | None = Query(default=None),
        since: int = Query(default=0, ge=0),
        limit: int = Query(default=200, ge=1, le=500),
    ):
        if epoch is None:
            want: int | None = state.epoch
        elif epoch == "all":
            want = None
        elif epoch.lstrip("-").isdigit():
            want = int(epoch)
        else:
            return error(400, "bad_request", "epoch 은 정수이거나 'all' 이어야 한다")
        events, next_since, has_more = state.events_for(want, since, limit)
        return {
            "epoch": want,
            "next_since": next_since,
            "has_more": has_more,
            "events": events,
        }

    @app.get("/api/alarms")
    def get_alarms() -> dict[str, Any]:
        return {"alarms": state.snapshot(now())["alarms"]}

    @app.get("/api/logs")
    def get_logs(
        level: str = Query(default="warn"),
        limit: int = Query(default=100, ge=1, le=500),
    ):
        if level not in LOG_LEVELS:
            return error(400, "bad_request", "level 은 warn·error·fatal 중 하나여야 한다")
        floor = LOG_LEVELS[level]
        logs = [log for log in state.logs if log["level_value"] >= floor]
        return {"logs": logs[-limit:]}

    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket) -> None:
        await ws.accept()
        hub.clients.add(ws)
        try:
            await ws.send_json({
                "type": "hello",
                "seq": state.seq,
                "server_time": state.snapshot(now())["server_time"],
                "data": state.snapshot(now()),
            })
            while True:
                # v0.1 에 클라이언트→서버 메시지는 없다. 끊길 때까지 잡고만 있는다.
                await ws.receive_text()
        except WebSocketDisconnect:
            pass
        finally:
            hub.clients.discard(ws)

    # ── 카메라·스캔 실시간 (§1.8) ───────────────────────────────────────

    def live_problem(name: str | None = None) -> JSONResponse | None:
        if state.live is None:
            return error(404, "live_sensors_off", "실시간 카메라·스캔이 꺼져 있다(--live-sensors)")
        if name is not None and name not in live_sensors.CAMERAS:
            return error(404, "unknown_camera", f"{name} 은 카메라 이름이 아니다",
                         {"cameras": list(live_sensors.CAMERAS)})
        return None

    @app.get("/api/cameras")
    async def get_cameras():
        if state.live is None:
            return {"enabled": False, "limits": live_sensors.limits(), "cameras": []}
        return {"enabled": True, "limits": live_sensors.limits(),
                "cameras": state.live.cameras(now(), container_read=state.container_read)}

    @app.get("/api/cameras/{name}/frame.jpg")
    async def get_camera_frame(name: str):
        if (problem := live_problem(name)) is not None:
            return problem
        # 한 장만 볼 때도 구독이 걸려야 프레임이 온다 — 잠깐 시청자로 들어가 한 장을 기다린다.
        if not state.live.acquire(name):
            return error(429, "too_many_viewers", f"{name} 은 이미 {live_sensors.MAX_VIEWERS}명이 보고 있다")
        try:
            for _ in range(int(live_sensors.CAMERA_STALE_WALL_S * 10) + 10):
                got = await asyncio.to_thread(state.live.jpeg, name)
                if got is not None:
                    return Response(got[1], media_type="image/jpeg", headers={"Cache-Control": "no-store"})
                await asyncio.sleep(0.1)
        finally:
            state.live.release(name)
        return error(404, "no_frame", f"{name} 프레임이 아직 없다(토픽이 안 온다)")

    @app.get("/api/cameras/{name}/stream")
    async def get_camera_stream(name: str, request: Request):
        if (problem := live_problem(name)) is not None:
            return problem
        if not state.live.acquire(name):
            return error(429, "too_many_viewers", f"{name} 은 이미 {live_sensors.MAX_VIEWERS}명이 보고 있다")

        async def parts():
            last = 0
            try:
                while not await request.is_disconnected():
                    got = await asyncio.to_thread(state.live.jpeg, name)
                    if got is not None and got[0] != last:
                        last = got[0]
                        yield (b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "
                               + str(len(got[1])).encode() + b"\r\n\r\n" + got[1] + b"\r\n")
                    await asyncio.sleep(1.0 / live_sensors.STREAM_FPS)
            finally:
                state.live.release(name)

        return StreamingResponse(parts(), media_type="multipart/x-mixed-replace; boundary=frame",
                                 headers={"Cache-Control": "no-store"})

    # ── 주문 풀 (§7.3) ──────────────────────────────────────────────────

    def current_pool() -> PoolResult:
        """`--order-pool` 이 있으면 그 파일, 없고 mock 이면 fixture 에서 만든다."""
        if order_pool:
            return load_pool(order_pool)
        # 기본은 저장소 원문 — **실물에서도 같다.** orchestrator 가 읽는 그 파일이다.
        # 풀이 비면 `check_request` 의 주문 검사가 통째로 건너뛰어져, 웹이 없는 주문도
        # 수락해 버리고 거부는 실물에서야 드러난다.
        if DEFAULT_ORDER_POOL is not None:
            return load_pool(DEFAULT_ORDER_POOL)
        if player is not None:
            return pool_from_fixture(player.fixture)
        return PoolResult([], [])

    def current_zones() -> tuple[dict[str, dict[str, Any]], str]:
        """`--zones-file` → 저장소 원문 → 고정 목록 순으로 찾는다. (구역, 출처)."""
        if zones_file:
            return load_zones(zones_file), "file"
        found = default_zones_path()
        if found is not None:
            return load_zones(found), "repo_default"
        return dict(MOCK_ZONES), "mock"

    # mock 은 로봇이 움직이지 않는다 — 평면도가 있으면 AMR 을 dock_1 자리에 세워 둔다(source "mock").
    # 재생 fixture 에 자세가 없어서, 단계로 자리를 지어내지 않는다.
    if mock and floor_map is not None:
        dock = current_zones()[0].get(MOCK_ROBOT_ZONE, {})
        if all(k in dock for k in ("x", "y", "yaw")):
            state.note_robot_pose(robot_id, dock, datetime.now(timezone.utc), source="mock", static=True)

    @app.get("/api/order_pool")
    def get_order_pool() -> dict[str, Any]:
        pool = current_pool()
        return {
            "source": ("file" if order_pool
                       else ("repo_default" if DEFAULT_ORDER_POOL is not None
                             else ("fixture" if player is not None else "none"))),
            "orders": with_used(pool.orders, state.used_order_ids),
            # 버려진 항목이 있으면 왜 버렸는지 말해 준다. 조용히 고치지 않는다.
            "problems": pool.problems,
        }

    @app.get("/api/queue")
    def get_queue() -> dict[str, Any]:
        """촬영 화면의 주문 큐 — 주문 풀 순서로 대기·진행·완료(api.md §7.7). 현재 epoch 기준."""
        zones = current_zones()[0]
        pool_orders = [{**o, "group": zones.get(o.get("bed") or "", {}).get("room"),
                        "label": zones.get(o.get("bed") or "", {}).get("label")}
                       for o in current_pool().orders]
        rows = queue_rows(pool_orders, state.orders, state.used_order_ids, outcome_for)
        return {"epoch": state.epoch, **rows, "counts": {k: len(v) for k, v in rows.items()}}

    @app.get("/api/zones")
    def get_zones() -> dict[str, Any]:
        """평면도용 전 구역(load·dock 포함)과 자세. 목적지 후보는 /api/destinations 다."""
        zones, source = current_zones()
        return {"source": source, "frame": "map", "zones": zone_rows(zones)}

    @app.get("/api/map")
    def get_map() -> Any:
        if floor_map is None:
            return error(404, "map_unavailable", map_problem)
        return map_meta(floor_map, "file")

    @app.get("/api/map/image")
    def get_map_image() -> Any:
        """PGM(P5) 원본 바이트. 화면이 캔버스로 직접 푼다 — 서버는 바꾸지 않는다."""
        if floor_map is None:
            return error(404, "map_unavailable", map_problem)
        return FileResponse(floor_map["image_path"], media_type="application/octet-stream")

    @app.get("/api/destinations")
    def get_destinations() -> dict[str, Any]:
        zones, source = current_zones()
        return {"source": source, "destinations": destinations(zones)}

    # ── 명령 API (기본 403) ─────────────────────────────────────────────

    @app.post("/api/reset")
    async def post_reset():
        if not allow_commands:
            return error(403, "commands_disabled", "서버가 --allow-commands 없이 떴다")
        if bridge is not None:
            ok, message = await asyncio.to_thread(bridge.call_reset)
            if not ok:
                return error(503, "no_ros", message)
            # 새 epoch 은 뒤따르는 RESET_BEGIN 이 말한다 — message 를 파싱하지 않는다.
            return JSONResponse({"ok": True, "accepted": True}, status_code=202)
        # mock 에서는 리셋을 흉내 낸다 — 프론트가 epoch 전환 화면을 시험할 수 있게.
        # **RESET_DONE 까지 반드시 낸다.** BEGIN 만 내면 barrier 가 영영 안 풀려
        # 이후 요청이 전부 barrier_running 으로 거부되고 RESET_STUCK 까지 뜬다.
        epoch = state.epoch + 1
        state.note_event({"name": "RESET_BEGIN", "epoch": epoch,
                          "stamp": state.clock_sim_s or 0.0}, now())
        hub.mark_dirty()

        if faults.stuck_reset:
            # **개발 전용 고장 흉내.** RESET_DONE 을 내지 않아 barrier 가 안 풀린다.
            # --reset-timeout 을 줄여 띄우면 RESET_STUCK 알람을 화면에서 볼 수 있다.
            return JSONResponse({"ok": True, "accepted": True}, status_code=202)

        async def finish_reset() -> None:
            await asyncio.sleep(MOCK_RESET_SECONDS)
            state.note_event({"name": "RESET_DONE", "epoch": epoch,
                              "stamp": state.clock_sim_s or 0.0}, now())
            hub.mark_dirty()

        app.state.reset_task = asyncio.create_task(finish_reset())
        return JSONResponse({"ok": True, "accepted": True}, status_code=202)

    @app.post("/api/requests")
    async def post_request(req: Request):
        if not allow_commands:
            return error(403, "commands_disabled", "서버가 --allow-commands 없이 떴다")
        try:
            body = await req.json()
        except Exception:  # noqa: BLE001 - 깨진 본문은 400 이지 500 이 아니다
            return error(400, "bad_request", "본문이 JSON 이 아니다")
        if not isinstance(body, dict):
            return error(400, "bad_request", "본문은 객체여야 한다")

        pool = current_pool()
        by_id = {o["order_id"]: o for o in pool.orders}

        # 1인·긴급의 실제 목적 침상은 요청의 destination_id 가 아니라
        # **주문 풀의 환자→bed 매핑이 우선한다.** 여기서 자동으로 채운다.
        # 웹이 order_id 만 보냈으면 환자·약품을 풀에서 채운다. 안 채우면 orchestrator 가
        # detail 에 빈 값을 싣고, 화면에 환자·약품이 영영 안 뜬다.
        filled = []
        for order in (body.get("orders") or []):
            if not isinstance(order, dict):
                filled.append(order)
                continue
            known = by_id.get(order.get("order_id", "")) or {}
            filled.append({
                "order_id": order.get("order_id", ""),
                "patient_id": order.get("patient_id") or known.get("patient_id"),
                "item_id": order.get("item_id") or known.get("item_id"),
            })
        body = {**body, "orders": filled}

        destination_source = "request"
        if body.get("mode") in (0, 1):
            beds = [by_id[o["order_id"]]["bed"]
                    for o in (body.get("orders") or [])
                    if isinstance(o, dict) and by_id.get(o.get("order_id", ""), {}).get("bed")]
            if beds:
                body = {**body, "destination_id": beds[0]}
                destination_source = "order_pool"

        verdict = check_request(body, state, now(), set(by_id), state.used_order_ids,
                                order_rooms=rooms_of_orders(pool.orders, current_zones()[0]))
        if verdict is not None:
            return error(verdict.status, verdict.code, verdict.message, verdict.detail)

        if bridge is not None:
            # 실물에서는 orchestrator 가 판정한다. 위 검사는 사유를 붙이기 위한 선검사다.
            ok, message = await asyncio.to_thread(bridge.send_delivery, body)
            if not ok:
                # goal REJECT 에는 사유 자리가 없다. /rosout 에서 이 request_id 의 줄을
                # 찾아 본다 — 못 찾으면 비운 채로 둔다. 추측 문구는 만들지 않는다.
                found = find_reject_reason(state.logs, body["request_id"], now())
                return error(409, "rejected", f"{message} — {found}" if found else message)
            return {"ok": True, "request_id": body["request_id"],
                    "mode_source": "web_request",
                    "destination_id": body.get("destination_id"),
                    "destination_source": destination_source,
                    "order_ids": [o["order_id"] for o in body["orders"]]}

        orders = body["orders"]
        detail = json.dumps(
            {"mode": body.get("mode"), "destination_id": body.get("destination_id"),
             "orders": orders},
            separators=(",", ":"), ensure_ascii=False)
        request_id = body["request_id"]
        state.note_event({"name": "REQUEST_ACCEPTED", "epoch": state.epoch,
                          "request_id": request_id, "detail": detail,
                          "stamp": state.clock_sim_s or 0.0}, now())
        for order in orders:
            state.note_order({"request_id": request_id, "order_id": order["order_id"],
                              "state": 0, "stamp": state.clock_sim_s or 0.0})
        # 웹이 직접 넣었으니 출처는 web_request 다 (api.md §1.3)
        parsed = state.request_detail.get(request_id)
        if parsed is not None:
            parsed["mode_source"] = "web_request"
        hub.mark_dirty()
        return {"ok": True, "request_id": request_id, "mode_source": "web_request",
                "destination_id": body.get("destination_id"),
                "destination_source": destination_source,
                "order_ids": [o["order_id"] for o in orders]}

    # 정적 서빙은 **맨 마지막에** mount 한다 — 먼저 걸면 "/" 가 API 라우트를 덮는다.
    if static_dir and Path(static_dir).is_dir():
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="frontend")

    return app


LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}


def host_warnings(host: str, allow_commands: bool) -> list[str]:
    """127.0.0.1 밖으로 여는 경우의 경고. 기동 로그에 찍는다.

    이 서버에는 **인증이 없다.** 교육장 유선망 안에서 쓰는 전제이고,
    그 밖에서는 리버스 프록시나 방화벽이 앞에 있어야 한다.
    """
    if host in LOCAL_HOSTS:
        return []
    lines = [f"** {host} 로 연다 — 이 서버에는 인증이 없다. 망 안의 누구나 화면을 본다. **"]
    if allow_commands:
        lines.append(
            "** --allow-commands 까지 켜져 있다 — 망 안의 누구나 리셋·배송 요청을 넣을 수 있다. **")
    return lines


async def _mock_live(state: WorldState, robot_id: str, on_change) -> None:
    """mock + --live-sensors: 합성 프레임(보는 사람이 있을 때만)과 원형 스캔을 낸다. 화면 개발용이다."""
    import time

    width, height = 640, 360
    tick = 0
    while True:
        wall = datetime.now(timezone.utc)
        for name in state.live.wanted_images():
            # 가로로 초록이 짙어지고 틱마다 빨강이 바뀐다(bgr8). 움직이는 것이 보이면 된다.
            red = (tick * 8) % 256
            row = b"".join(bytes((0, 40 + 160 * x // (width - 1), red)) for x in range(width))
            state.live.note_frame(name, {"data": row * height, "width": width, "height": height,
                                         "encoding": "bgr8", "step": width * 3, "stamp": tick * 0.2},
                                  wall, time.monotonic())
        if tick % round(live_sensors.SCAN_PERIOD_S * live_sensors.STREAM_FPS) == 0:
            robot = state.robots.get(robot_id)
            pose = (robot["x"], robot["y"], robot["yaw"]) if robot else None
            n = 360
            state.live.note_scan({
                "robot_id": robot_id, "frame": "map" if pose else f"{robot_id}/lidar_link",
                "stamp": tick * 0.2, "range_max": 10.0,
                "points": live_sensors.scan_points([2.0] * n, -math.pi, 2 * math.pi / n, 0.1, 10.0, pose=pose),
            }, wall)
            on_change()
        tick += 1
        await asyncio.sleep(1.0 / live_sensors.STREAM_FPS)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="app.main", description="ROKEY P3 관제 백엔드")
    p.add_argument("--mock", action="store_true", help="ROS 대신 fixture 를 재생한다")
    p.add_argument("--fixture", default=None, help="fixture JSON 경로")
    p.add_argument("--host", default="127.0.0.1", help="bind 주소 (기본 127.0.0.1)")
    p.add_argument("--port", type=int, default=8000, help="bind 포트 (기본 8000)")
    p.add_argument("--speed", type=float, default=1.0, help="mock 재생 배속")
    p.add_argument("--loop", action="store_true", help="mock fixture 를 반복 재생")
    p.add_argument("--allow-commands", action="store_true",
                   help="POST /api/reset·/api/requests 를 연다 (기본 403)")
    p.add_argument("--refill-timeout", type=float, default=REFILL_TIMEOUT_SIM_S,
                   help=f"REFILL_FAILED 임계 sim s (기본 {REFILL_TIMEOUT_SIM_S:.0f})")
    p.add_argument("--mock-fault", default=None, metavar="이름[,이름…]",
                   help="**개발 전용, 시연 절차에 없음.** mock 재생 데이터에 고장을 넣어 "
                        f"알람 화면을 확인한다. {FAULT_HELP}")
    p.add_argument("--reset-timeout", type=float, default=RESET_TIMEOUT_WALL_S,
                   help=f"RESET_STUCK 임계 wall s (기본 {RESET_TIMEOUT_WALL_S:.0f}). "
                        "화면에서 확인하려면 3 정도로 줄여서 띄운다")
    p.add_argument("--robot-id", default="amr_1", help="구독할 AMR 이름 (기본 amr_1)")
    p.add_argument("--order-pool", default=None, help="order_pool.yaml 경로")
    p.add_argument("--zones-file", default=None,
                   help="zones.yaml 경로. 목적지 후보를 kind 가 bed·room·station 인 구역으로 낸다")
    p.add_argument("--map-file", default=None,
                   help="Nav2 지도 yaml(maps/<월드>.yaml). 주면 평면도 API(/api/map)와 snapshot.robots 가 켜진다")
    p.add_argument("--show-evaluator", action="store_true",
                   help="/evaluator/cabinet 관측을 snapshot 에 싣는다 (표시 전용, 기본 꺼짐)")
    p.add_argument("--live-sensors", action="store_true",
                   help="카메라 MJPEG 스트림·라이다 스캔을 켠다(기본 꺼짐, 촬영용). "
                        "카메라는 보는 사람이 있을 때만 구독한다")
    p.add_argument("--roles", default=None,
                   help="이 PC 가 맡은 역할(P3_ROLES, 공백 구분). 두 PC 모드에서 demo_v2.sh 가 넘긴다(§1.10)")
    p.add_argument("--peer", default=None, help="상대 PC 주소(P3_PEER). 주면 snapshot.deployment.multi_pc 가 true")
    p.add_argument("--catalog", default=None,
                   help="약 카탈로그 YAML(P3_CATALOG). QR 판독 요약의 약 이름·약통 로트(api.md §1.12)")
    p.add_argument("--dispenser-file", default=None,
                   help="조제기 YAML(P3_DISPENSER_FILE). 약통 로트 → 약품·유통기한(api.md §1.12)")
    p.add_argument("--static", default=None,
                   help="이 디렉터리를 / 에서 서빙한다 (index.html). 같은 출처가 되어 CORS 가 필요 없다")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        faults = parse_faults(args.mock_fault)
    except FaultSpecError as exc:
        print(f"--mock-fault: {exc}")
        return 2
    if faults and not args.mock:
        # 실물에 고장을 주입할 길을 아예 두지 않는다.
        print("--mock-fault 는 --mock 과 함께만 쓸 수 있다.")
        return 2
    if faults:
        print(f"** 고장 흉내 중 (개발 전용): {', '.join(faults.active)} **")
    for line in host_warnings(args.host, args.allow_commands):
        print(line)
    import uvicorn
    app = create_app(mock=args.mock, fixture_path=args.fixture, speed=args.speed, loop=args.loop,
                     allow_commands=args.allow_commands,
                     refill_timeout=args.refill_timeout, reset_timeout=args.reset_timeout,
                     order_pool=args.order_pool, static_dir=args.static,
                     zones_file=args.zones_file, show_evaluator=args.show_evaluator,
                     faults=faults, robot_id=args.robot_id, map_file=args.map_file,
                     live=args.live_sensors, roles=(args.roles or "").split() or None, peer=args.peer,
                     catalog=args.catalog, dispenser_file=args.dispenser_file)
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
