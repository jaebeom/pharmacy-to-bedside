"""snapshot 조립 — api.md §1.

**얇게 유지한다.** 클론이 열리면 `rokey_p3_orchestrator.status_view` 의 `StatusModel` 과
`event_key` 를 **그대로 import 해서** 이 파일의 이벤트 버퍼·정렬·단계 추정을 대체한다
(복사하거나 고치지 않는다). 그때까지 쓰는 최소 구현이다.

ROS 를 import 하지 않는다 — 실물 모드에서도 ROS 메시지는 바깥에서 dict 로 바꿔 넣어 준다.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from app.alarms import (
    P3_ALERTS,
    parse_p3_alert,
    CLOCK_STALE_WALL_S,
    DISPENSER_STALE_WALL_S,
    RESET_SETTLE_WALL_S,
    RESET_TIMEOUT_WALL_S,
    REFILL_TIMEOUT_SIM_S,
    SIGNAL_KEYS,
    STALE_WALL_S,
    STATE_NAMES,
    evaluate_alarms,
    outcome_for,
    unavailable_items,
    unmatched_refill_requests,
)
from app.film import stage_for
from app.fleet_poses import parse_fleet_poses
from app.orchestrator_view import event_key, phase_for
from app.refill_detail import (
    KINDS as REFILL_KINDS,
    parse_refill_detail,
    parse_shelf_kinds,
    parse_shelf_stock,
    refill_summary,
    refill_target,
)
from app.qr_info import TAG_KINDS, QrResolver
from app.request_detail import parse_request_detail

#: 트립을 수행하는 로봇의 ID 모양. `Event.msg` 의 robot_id 주석은 `amr_1 .. amr_5, m0609, dispenser`.
#: **`m0609` 와 `dispenser` 는 트립의 로봇이 아니다** — 조제실 설비이고 트립과 무관하게 이벤트를 낸다.
AMR_ID_RE = re.compile(r"^amr_[0-9]+$")

# 트립을 닫는 이벤트. 이게 오면 trip 을 null 로 돌린다.
TRIP_CLOSING = {"DOCKED"}

#: AMR 이 도크에 있다고 보는 이벤트(그 AMR 의 이 epoch 마지막 이벤트일 때).
#: RESET_DONE 은 리셋이 AMR 을 도크 자세로 되돌린 뒤다(계약 6절 2·4). orchestrator 는 이것도
#: 트립 로봇의 robot_id 로 낸다(`orchestrator_node._emit`).
DOCKED_EVENTS = {"DOCKED", "RESET_DONE"}

#: 감속기 속도 제한은 1 Hz 로 다시 낸다(`speed_governor_node.py` publish_period_s). 3 주기를 놓치면 끊긴 것으로 본다.
SPEED_LIMIT_STALE_WALL_S = 3.0

#: `/p3/sim_running` 은 1 Hz 로 다시 온다. 3 s 넘게 안 오면 Isaac 이 없는 것으로 본다(시뮬통합 #759 정의).
SIM_RUNNING_STALE_WALL_S = 3.0

#: `TagRead` 의 약통 종류·판독 상태(메시지 상수).
TAG_KIND_CONTAINER = 3
TAG_STATUS_OK = 0
#: 스냅샷에 싣는 QR 판독 수(서로 다른 (로봇, ID) 기준, 최근 것부터).
QR_READS_MAX = 20


def iso_or_none(dt: datetime | None) -> str | None:
    """`iso` 인데 None 을 그대로 통과시킨다."""
    return iso(dt) if dt is not None else None


def iso(dt: datetime) -> str:
    """ISO 8601 UTC, 밀리초 3자리 (api.md §0.1)."""
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


class WorldState:
    """지금까지 본 것을 담고 snapshot 한 장을 만든다. 스레드 안전하지 않다 —
    호출자가 단일 이벤트 루프에서만 건드린다."""

    def __init__(self, *, refill_timeout_sim_s: float = REFILL_TIMEOUT_SIM_S,
                 reset_timeout_wall_s: float = RESET_TIMEOUT_WALL_S,
                 max_events: int = 12, event_buffer: int = 500, log_buffer: int = 500,
                 source_mode: str = "mock", commands_enabled: bool = False,
                 show_evaluator: bool = False) -> None:
        self.server_run_id = uuid.uuid4().hex[:8]
        self.source_mode = source_mode
        self.commands_enabled = commands_enabled
        # 켜진 고장 흉내 목록. 화면이 "고장 흉내 중" 배지를 띄워, 시연 때 실수로
        # 켠 채 띄우는 사고를 막는다. 평소에는 빈 목록이다.
        self.mock_faults: list[str] = []
        # 배치(api.md §1.10). main 이 채운다. 기본은 한 대.
        self.deployment: dict[str, Any] = {"multi_pc": False, "roles": None, "peer": None, "domain_id": None}
        # /evaluator/cabinet 은 **평가 전용** 토픽이다. 계약상 운영 노드는 구독하지 않는다.
        # 웹은 운영 노드가 아니고 표시만 하므로 구독은 허용되지만, 기본은 꺼 둔다.
        self.show_evaluator = show_evaluator
        self.refill_timeout_sim_s = refill_timeout_sim_s
        self.reset_timeout_wall_s = reset_timeout_wall_s
        self.max_events = max_events
        self.event_buffer = event_buffer
        self.log_buffer = log_buffer

        self.seq = 0
        self.epoch = 0
        self.events: list[dict[str, Any]] = []
        self.logs: list[dict[str, Any]] = []
        self.orders: dict[str, dict[str, Any]] = {}
        self.dispenser: dict[str, Any] | None = None
        self.belt: dict[str, Any] | None = None
        self.cabinet: dict[str, Any] | None = None
        self.signals: dict[str, dict[str, Any]] = {}
        # 로봇 자세(map 프레임). 실물은 TF map → <robot>/base_link, mock 은 dock 고정(`static`).
        self.robots: dict[str, dict[str, Any]] = {}
        self.clock_sim_s: float | None = None
        self.clock_wall: datetime | None = None
        # `/p3/alerts`(도킹·지도 알림). 받은 wall 을 붙여 둔다. 리셋(RESET_BEGIN)이 "포기" 를 지운다.
        self.p3_alerts: list[dict[str, Any]] = []
        # 감속기 속도 제한(`/<robot>/speed_limit`). 받은 적이 없으면 None — snapshot 에 키가 없다.
        self.speed_limit: dict[str, Any] | None = None
        # 여벌 AMR·더미 자리(`/isaac/fleet/poses`). {"stamp", "wall", "poses"}. 받은 적이 없으면 None.
        self.fleet: dict[str, Any] | None = None
        # Isaac 타임라인이 도는가(`/p3/sim_running`). {"value", "wall"}. 받은 적이 없으면 None.
        self.sim_running: dict[str, Any] | None = None
        # 선반의 약 → 약통 종류(`/m0609/shelf/inventory`). 받은 적이 없으면 빈 표다.
        self.shelf_kinds: dict[str, str] = {}
        # 선반 약통 수(`/m0609/shelf/inventory` 의 cells[].present, api.md §6.1 `stock`). 받은 적 없으면 None.
        self.shelf_stock: dict[str, dict[str, int]] | None = None
        # M0609 손 카메라의 마지막 약통(cn-) 판독. 세대가 바뀌면 비운다.
        self.container_read: dict[str, Any] | None = None
        # 손 카메라 QR 판독(재범 9/29, api.md §1.12). (로봇, ID) → 처음·마지막 받은 시각·횟수. 세대가 바뀌면 비운다.
        # 검출기는 보이는 동안 프레임마다 낸다 — 한 줄로 합친다. 요약은 `qr_resolver`(main 이 넣는다)가 푼다.
        self.qr_reads: dict[tuple[str, str], dict[str, Any]] = {}
        self.qr_resolver = QrResolver()
        #: 트립 AMR 의 ID(`--robot-id`). `/{robot}/hand_camera/tag_reads` 판독에 붙인다.
        self.robot_id = "amr_1"
        # 카메라·스캔 실시간 표시(api.md §1.8). `--live-sensors` 일 때만 main 이 넣는다. 없으면 scan 은 null.
        self.live: Any = None
        # request_id -> REQUEST_ACCEPTED.detail 파싱 결과 (없으면 None).
        # **세대가 바뀌면 비운다.** detail 은 그 epoch 의 트립에만 쓰인다. 리셋이 20 s 마다
        # 도는 실물에서 안 비우면 실행 내내 자란다.
        self.request_detail: dict[str, dict[str, Any] | None] = {}
        self.current_request_id: str | None = None
        self.trip_open = False
        # 이번 세대에서 쓰인 order_id 와 request_id.
        # **둘 다 리셋하면 비운다.** orchestrator_node `_reload_stores`(:398-404) 가
        # /sim/reset 이 ok 한 뒤 `_used_requests.clear()` 와 `_used_orders.clear()` 를
        # 둘 다 하기 때문이다(계약 6절 3). 그래서 비우는 시점은 RESET_DONE 이다.
        self.used_order_ids: set[str] = set()
        self.used_request_ids: set[str] = set()
        # 리셋 barrier 의 wall 시각. 판정이 sim 이 아니라 wall 인 유일한 곳이다 —
        # orchestrator 가 `time.monotonic()` 으로 재기 때문이다.
        self.reset_begin_wall: datetime | None = None
        self.reset_done_wall: datetime | None = None

    # ── 입력 ────────────────────────────────────────────────────────────

    def note_event(self, ev: dict[str, Any], wall: datetime) -> dict[str, Any]:
        self.seq += 1
        epoch = int(ev.get("epoch", self.epoch))
        record = {
            "seq": self.seq,
            "name": ev.get("name", ""),
            "request_id": ev.get("request_id") or "",
            "order_id": ev.get("order_id") or "",
            "robot_id": ev.get("robot_id") or "",
            "epoch": epoch,
            "detail": ev.get("detail") or "",
            "stamp": float(ev.get("stamp", 0.0)),
            "wall": iso(wall),
        }
        if record["name"] == "REFILL_DONE":
            # 장면 v2 의 JSON detail 만 파생한다. v1 문자열이면 None 이고 원문은 detail 에 있다.
            record["refill"] = parse_refill_detail(record["detail"])
        self.events.append(record)
        if len(self.events) > self.event_buffer:
            del self.events[: len(self.events) - self.event_buffer]

        self.epoch = max(self.epoch, epoch)

        name = record["name"]
        if name == "RESET_BEGIN":
            # 새 세대. 트립과 주문을 비운다 — 이벤트는 epoch 으로 걸러 낸다.
            # 아직 _reload_stores 전이라 사용 표는 그대로 둔다.
            self.orders.clear()
            self.request_detail.clear()
            self.current_request_id = None
            self.trip_open = False
            self.reset_begin_wall = wall
            self.reset_done_wall = None
            # 도킹·지도 "포기" 는 그 세대의 일이다. 재시도·개입은 시간으로 저절로 사라진다.
            self.p3_alerts = [a for a in self.p3_alerts if not a["kind"].endswith("_GIVEUP")]
            self.container_read = None
            self.qr_reads.clear()
        elif name == "RESET_DONE":
            self.reset_done_wall = wall
            # _reload_stores 가 도는 시점. 주문 풀과 request_id 표가 함께 되살아난다.
            self.used_order_ids.clear()
            self.used_request_ids.clear()
        elif name == "REQUEST_ACCEPTED" and record["request_id"]:
            rid = record["request_id"]
            self.current_request_id = rid
            self.trip_open = True
            # detail 은 신뢰할 수 없는 자유 문자열이다. 실패하면 조용히 None.
            self.request_detail[rid] = parse_request_detail(record["detail"])
            # 한 epoch 안에서 요청이 아주 많아도 자라지 않게 위에서부터 버린다.
            while len(self.request_detail) > self.event_buffer:
                self.request_detail.pop(next(iter(self.request_detail)))
            self.used_request_ids.add(rid)
            parsed = self.request_detail[rid]
            if parsed:
                self.used_order_ids.update(parsed["orders"])
            if record["order_id"]:
                self.used_order_ids.add(record["order_id"])
        elif name in TRIP_CLOSING:
            self.trip_open = False
        return record

    def note_log(self, log: dict[str, Any], wall: datetime) -> None:
        """`/rosout` 한 줄. WARN 이상만 넣는다 — 거르는 것은 호출자 몫이다."""
        self.logs.append({**log, "wall": iso(wall)})
        if len(self.logs) > self.log_buffer:
            del self.logs[: len(self.logs) - self.log_buffer]

    def note_order(self, st: dict[str, Any]) -> None:
        order_id = st.get("order_id") or ""
        if not order_id:
            return
        self.used_order_ids.add(order_id)
        self.orders[order_id] = {
            "request_id": st.get("request_id") or "",
            "state": int(st.get("state", 0)),
            "reason": st.get("reason") or "",
            "stamp": float(st.get("stamp", 0.0)),
        }

    def note_dispenser(self, st: dict[str, Any], wall: datetime) -> None:
        self.dispenser = {**st, "wall": wall}

    def note_belt(self, st: dict[str, Any], wall: datetime) -> None:
        self.belt = {**st, "wall": wall}
        # 벨트는 신호 5개 중 하나이기도 하다 (status_view 의 'belt' 키)
        self.note_signal("belt", bool(st.get("occupied")), wall)

    def note_cabinet(self, order_id: str, cabinet_id: str, present: bool,
                     wall: datetime) -> None:
        self.cabinet = {"order_id": order_id, "cabinet_id": cabinet_id,
                        "present": present, "wall": wall}

    def note_p3_alert(self, text: str, wall: datetime) -> None:
        """`/p3/alerts` 한 줄. 모르는 kind·깨진 JSON 은 버린다. 같은 (kind, robot) 은 새 것이 옛 것을 덮는다."""
        alert = parse_p3_alert(text)
        if alert is None:
            return
        self.p3_alerts = [a for a in self.p3_alerts
                          if (a["kind"], a["robot"]) != (alert["kind"], alert["robot"])][-49:]
        self.p3_alerts.append({**alert, "wall": wall})

    def active_p3_alerts(self, now: datetime) -> list[dict[str, Any]]:
        """지금 살아 있는 알림. 나이는 **받은 시각**으로 잰다 — 알림의 wall 은 보낸 PC 의 시계라 두 PC 에서 어긋난다."""
        return [a for a in self.p3_alerts if (self._age(a["wall"], now) or 0.0) <= P3_ALERTS[a["kind"]][2]]

    def note_speed_limit(self, limit: dict[str, Any], wall: datetime) -> None:
        # 정지가 시작된 wall 시각. 정지가 이어지는 동안(1 Hz 재발행) 그대로 두고, 풀리면 지운다.
        prev = self.speed_limit
        if not limit.get("stop_reason"):
            since = None
        elif prev is not None and prev.get("stop_reason") and prev.get("stop_since") is not None:
            since = prev["stop_since"]
        else:
            since = wall
        self.speed_limit = {**limit, "wall": wall, "stop_since": since}

    def obstacle_stop_age(self, now: datetime) -> float | None:
        """감속기 정지가 이어진 wall 초. 정지가 아니거나 신호가 끊겼으면(stale) None — 모르는 채로 알리지 않는다."""
        limit = self.speed_limit
        if limit is None or limit.get("stop_since") is None:
            return None
        if (self._age(limit["wall"], now) or 0.0) > SPEED_LIMIT_STALE_WALL_S:
            return None
        return self._age(limit["stop_since"], now)

    def speed_limit_view(self, now: datetime) -> dict[str, Any] | None:
        """snapshot.signals.speed_limit. 1 Hz 재발행이라 신선도 기준은 `SPEED_LIMIT_STALE_WALL_S` 다."""
        limit = self.speed_limit
        if limit is None:
            return None
        age = self._age(limit["wall"], now)
        return {"speed_limit_pct": limit["speed_limit_pct"], "stop_reason": limit["stop_reason"],
                "wall": iso(limit["wall"]), "age_wall_s": age,
                "stale": age is not None and age > SPEED_LIMIT_STALE_WALL_S}

    def note_sim_running(self, value: bool, wall: datetime) -> None:
        self.sim_running = {"value": bool(value), "wall": wall}

    def sim_running_view(self, now: datetime) -> dict[str, Any] | None:
        """snapshot.sim_running. 3 s 넘게 안 오면 stale — 시뮬통합 정의로 "Isaac 없음" 이다."""
        if self.sim_running is None:
            return None
        age = self._age(self.sim_running["wall"], now)
        return {"value": self.sim_running["value"], "wall": iso(self.sim_running["wall"]), "age_wall_s": age,
                "stale": age is not None and age > SIM_RUNNING_STALE_WALL_S}

    def note_shelf(self, text: str) -> None:
        """`/m0609/shelf/inventory` 한 장. 읽을 수 없는 것이면 지난 표를 그대로 둔다."""
        kinds = parse_shelf_kinds(text)
        if kinds is not None:
            self.shelf_kinds = kinds
        stock = parse_shelf_stock(text)
        if stock is not None:
            self.shelf_stock = stock

    def note_qr_read(self, robot: str, read: dict[str, Any], wall: datetime) -> None:
        """손 카메라 QR 판독 한 건(api.md §1.12). 못 읽은 것(status != OK)·모르는 종류는 버린다."""
        kind = TAG_KINDS.get(int(read.get("kind", -1)))
        tag_id = read.get("tag_id") or ""
        if kind is None or not tag_id or int(read.get("status", -1)) != TAG_STATUS_OK:
            return
        key = (robot, tag_id)
        row = self.qr_reads.get(key)
        if row is None:
            row = self.qr_reads[key] = {"robot": robot, "kind": kind, "tag_id": tag_id, "count": 0,
                                        "first_wall": wall, "first_stamp": float(read.get("stamp", 0.0))}
        row["count"] += 1
        row["last_wall"] = wall
        if len(self.qr_reads) > QR_READS_MAX * 2:     # 오래된 것부터 버린다
            for old in sorted(self.qr_reads, key=lambda k: self.qr_reads[k]["last_wall"])[:QR_READS_MAX]:
                del self.qr_reads[old]

    def qr_reads_view(self, now: datetime) -> list[dict[str, Any]]:
        """최근 받은 것부터 `QR_READS_MAX` 줄. `info` 는 QR 안 ID 를 주문 풀·카탈로그로 푼 요약이다."""
        rows = sorted(self.qr_reads.values(), key=lambda r: r["last_wall"], reverse=True)[:QR_READS_MAX]
        return [{"robot": r["robot"], "kind": r["kind"], "tag_id": r["tag_id"], "count": r["count"],
                 "first_wall": iso(r["first_wall"]), "last_wall": iso(r["last_wall"]),
                 "age_wall_s": self._age(r["last_wall"], now), "stamp": r["first_stamp"],
                 "info": self.qr_resolver.info(r["kind"], r["tag_id"])} for r in rows]

    def note_tag_read(self, read: dict[str, Any], wall: datetime) -> None:
        """M0609 손 카메라 판독 한 건. 약통(cn-) 판독만 담는다 — 허용·거부 판정은 토픽에 없다."""
        self.note_qr_read("m0609", read, wall)
        if int(read.get("kind", -1)) != TAG_KIND_CONTAINER:
            return
        self.container_read = {
            "tag_id": read.get("tag_id") or "",
            "status": "ok" if int(read.get("status", -1)) == TAG_STATUS_OK else "unreadable",
            "stamp": float(read.get("stamp", 0.0)),
            "wall": wall,
        }

    def note_signal(self, key: str, value: bool, wall: datetime) -> None:
        self.signals[key] = {"value": bool(value), "wall": wall}

    def note_robot_pose(self, robot_id: str, pose: dict[str, float], wall: datetime, *,
                        source: str = "tf", static: bool = False) -> None:
        """`pose` = {x, y, yaw, [stamp]}(map, m·rad). `static` 이면 신선도를 따지지 않는다(mock 의 고정 자리).

        **stamp 가 지난번과 같으면 새 정보가 아니다** — 받은 시각을 갱신하지 않는다. TF 버퍼는 마지막
        변환을 계속 내주므로, 이걸 안 보면 TF 가 끊겨도(base_driver 가 죽어도) 자세가 늘 신선하게 보인다.
        """
        prev = self.robots.get(robot_id)
        stamp = pose.get("stamp")
        if stamp is not None and prev is not None and prev.get("stamp") == stamp:
            return
        self.robots[robot_id] = {"x": float(pose["x"]), "y": float(pose["y"]), "yaw": float(pose["yaw"]),
                                 "stamp": stamp, "wall": wall, "source": source, "static": static}

    def _docked(self, robot_id: str, epoch_events: list[dict[str, Any]]) -> bool | None:
        """이 AMR 이 도크에 있는가. 이 epoch 에서 그 AMR 의 **마지막** 이벤트로 본다.

        `DOCKED`·`RESET_DONE` 이면 True, 다른 이벤트(다음 트립의 `REQUEST_ACCEPTED` 등)면 False,
        그 AMR 의 이벤트가 없으면 None(모름). `DOCKED` 없이 끝난 트립(복귀 실패)은 마지막이
        `RETURNED` 등이라 False 다 — orchestrator 가 다음 트립을 재도킹부터 하는 것과 같은 뜻이다.
        `/<robot>/base/docked` 는 fleet 의 opt-in(`publish_docking_state`)이 꺼져 있어 쓰지 않는다.
        """
        last = None
        for e in epoch_events:
            if e["robot_id"] == robot_id:
                last = e
        return None if last is None else last["name"] in DOCKED_EVENTS

    def note_fleet_poses(self, text: str, wall: datetime) -> None:
        """`/isaac/fleet/poses` 한 장. 읽을 수 없으면 버린다. stamp 가 같으면 새 정보가 아니다(TF 와 같은 규칙)."""
        parsed = parse_fleet_poses(text)
        if parsed is None:
            return
        if self.fleet is not None and self.fleet["stamp"] == parsed["stamp"]:
            return
        self.fleet = {**parsed, "wall": wall}

    def _fleet(self, now: datetime, kind: str) -> list[dict[str, Any]]:
        """fleet_poses 중 한 종류. 주 AMR(TF 로 받는 로봇)과 id 가 같으면 뺀다 — TF 가 기준이다."""
        if self.fleet is None:
            return []
        age = self._age(self.fleet["wall"], now)
        return [{"id": p["id"], "kind": p["kind"], "x": p["x"], "y": p["y"], "yaw": p["yaw"], "frame": "map",
                 "age_wall_s": age, "stale": age is not None and age > STALE_WALL_S, "source": "fleet_poses"}
                for p in sorted(self.fleet["poses"], key=lambda p: p["id"])
                if p["kind"] == kind and p["id"] not in self.robots]

    def _robots(self, now: datetime, epoch_events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out = []
        for robot_id in sorted(self.robots):
            r = self.robots[robot_id]
            age = 0.0 if r["static"] else self._age(r["wall"], now)
            out.append({"robot_id": robot_id, "x": r["x"], "y": r["y"], "yaw": r["yaw"], "frame": "map",
                        "age_wall_s": age, "stale": age is not None and age > STALE_WALL_S,
                        "source": r["source"],
                        # 지금 향하는 구역. GoToZone goal 은 밖에서 안 보이고 이벤트에도 안 실린다 — 늘 null.
                        # 목적지는 trip.destination_id 를 쓴다.
                        "goal_zone": None,
                        "docked": self._docked(robot_id, epoch_events),
                        "kind": "amr"})
        # 여벌 AMR — 주문·Nav2 가 없어 도킹·목표를 모른다.
        for spare in self._fleet(now, "spare_amr"):
            out.append({"robot_id": spare["id"], "x": spare["x"], "y": spare["y"], "yaw": spare["yaw"],
                        "frame": "map", "age_wall_s": spare["age_wall_s"], "stale": spare["stale"],
                        "source": "fleet_poses", "goal_zone": None, "docked": None, "kind": "spare_amr"})
        return out

    def note_clock(self, sim_s: float, wall: datetime) -> None:
        self.clock_sim_s = float(sim_s)
        self.clock_wall = wall

    # ── 조회 ────────────────────────────────────────────────────────────

    @staticmethod
    def ordered(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """`status_view.event_key` 순으로 줄 세운다 — 도착 순서가 아니다.

        `/events` 는 latched(transient_local)라 **늦게 붙으면 작성자별로 뭉쳐서 온다.**
        도착 순서로 그리면 늦게 붙은 화면의 타임라인이 통째로 뒤죽박죽이 된다.
        `seq` 는 커서일 뿐 표시 순서가 아니다.
        """
        return sorted(events, key=event_key)

    def events_for(self, epoch: int | None, since: int,
                   limit: int) -> tuple[list[dict[str, Any]], int, bool]:
        """`since` 뒤의 이벤트 한 페이지. (이벤트, 다음 커서, 더 있나).

        **페이지는 `seq`(커서 순)로 자르고, 자른 뒤에 `event_key` 로 줄 세운다.**
        순서로 자르면 커서가 되돌아가거나 건너뛰어 **영영 안 오는 이벤트가 생긴다** —
        `seq` 가 낮은데 `event_key` 가 늦은 이벤트(늦게 도착한 옛 이벤트)가 정확히 그렇다.
        """
        # self.events 는 도착 순서이므로 이 걸러내기는 seq 순을 지킨다.
        matched = [e for e in self.events
                   if e["seq"] > since and (epoch is None or e["epoch"] == epoch)]
        page = matched[:limit]
        has_more = len(matched) > limit
        next_since = max((e["seq"] for e in page), default=since)
        return self.ordered(page), next_since, has_more

    def _age(self, wall: datetime | None, now: datetime) -> float | None:
        return None if wall is None else max(0.0, (now - wall).total_seconds())

    def _signal_ages(self, now: datetime) -> dict[str, float]:
        return {k: self._age(v["wall"], now) for k, v in self.signals.items()
                if v.get("wall") is not None}

    def _trip(self) -> dict[str, Any] | None:
        rid = self.current_request_id
        if rid is None or not self.trip_open:
            return None
        mine = self.ordered(
            [e for e in self.events if e["epoch"] == self.epoch and e["request_id"] == rid])
        if not mine:
            return None
        last = mine[-1]
        # 조제기·M0609 이벤트는 단계를 바꾸지 않는다 — 원문 표에 있는 마지막 것을 찾는다.
        # 순서는 도착 순번이 아니라 event_key 다 (아래 _ordered 설명 참고).
        phase = phase_label = None
        for record in reversed(mine):
            phase, phase_label = phase_for(record["name"])
            if phase is not None:
                break
        detail = self.request_detail.get(rid)
        known = detail or {}
        detail_orders = known.get("orders") or {}

        orders = []
        for order_id, st in self.orders.items():
            if st["request_id"] and st["request_id"] != rid:
                continue
            extra = detail_orders.get(order_id) or {}
            orders.append({
                "order_id": order_id,
                # detail 이 없으면 null. 외부 관찰로는 얻을 길이 없다 (api.md §1.3).
                "patient_id": extra.get("patient_id"),
                "item_id": extra.get("item_id"),
                "state": st["state"],
                "state_name": STATE_NAMES.get(st["state"], str(st["state"])),
                # 결말 한 낱말. HOLD_RETURN 이 정상 완주와 이상으로 갈리므로,
                # 화면이 state_name·reason 을 다시 조합하지 않게 서버가 파생한다.
                "outcome": outcome_for(st["state"], st["reason"]),
                "reason": st["reason"],
                "stamp": st["stamp"],
            })
        orders.sort(key=lambda o: o["order_id"])

        return {
            "request_id": rid,
            "mode": known.get("mode"),
            "mode_name": known.get("mode_name"),
            "mode_source": known.get("mode_source"),
            "destination_id": known.get("destination_id"),
            "robot_id": self._trip_robot(mine),
            "phase": phase,
            "phase_label": phase_label,
            "phase_source": "status_view",
            "started_sim_s": mine[0]["stamp"],
            "last_event_sim_s": last["stamp"],
            "orders": orders,
        }

    def _stage(self, trip: dict[str, Any] | None, dispenser: dict[str, Any] | None) -> dict[str, Any]:
        """촬영 화면의 일곱 단계(api.md §1.7). 트립 약품은 REQUEST_ACCEPTED.detail 에서 — 상태보다 먼저 안다."""
        rid = (trip or {}).get("request_id")
        departed = bool(rid) and any(e["name"] == "DEPARTED" and e["request_id"] == rid and e["epoch"] == self.epoch
                                     for e in self.events)
        # 보충이 막을 수 있는 것은 **아직 조제 안 된** 주문의 약품뿐이다. 마지막 재고를 조제하는 순간
        # 그 약품이 PAUSED 가 되는데, 그때 이 트립의 봉투는 이미 나왔다 — "보충" 으로 보이면 틀린다.
        dispensed = {e["order_id"] for e in self.events
                     if e["name"] == "DISPENSED" and e["request_id"] == rid and e["epoch"] == self.epoch}
        detail_orders = ((self.request_detail.get(rid) or {}).get("orders") or {}) if rid else {}
        items = {o.get("item_id") for oid, o in detail_orders.items() if o.get("item_id") and oid not in dispensed}
        items |= {o["item_id"] for o in (trip or {}).get("orders", [])
                  if o.get("item_id") and o["order_id"] not in dispensed}
        blocked = unavailable_items(self.dispenser) | set((dispenser or {}).get("refilling_item_ids") or [])
        return stage_for((trip or {}).get("phase"), departed=departed, trip_items=items,
                         blocked_items=blocked, reset=self._reset_in_progress())

    def _refilling(self, epoch_events: list[dict[str, Any]],
                   paused_item_ids: list[str]) -> tuple[bool, list[str]]:
        """보충이 진행 중인가. **이벤트 이름만으로** 판정한다 — detail 은 읽지 않는다.

        열린 `REFILL_REQUESTED` 가 하나라도 있으면 진행 중이다. 각 `REFILL_DONE` 은
        가장 이른 열린 요청만 닫는다. 한 품목의 완료가 다른 품목의 진행 표시를 끄지 않는다.
        `epoch_events` 는 현재 epoch 것만 들어오므로, 리셋으로 세대가 바뀌면 자연히 풀린다.

        어떤 약품인지는 **그 시점의 `paused_item_ids`** 로 본다. 조제기가 직접 말해 주는 값이라
        detail 을 긁는 것보다 정확하다.
        """
        refilling = bool(unmatched_refill_requests(epoch_events))
        return refilling, (list(paused_item_ids) if refilling else [])

    def snapshot_reset_in_progress(self) -> bool:
        """리셋 barrier 가 도는 중인가 (RESET_BEGIN 뒤 RESET_DONE 전)."""
        return self._reset_in_progress()

    def accept_after_wall(self, now: datetime | None = None) -> datetime | None:
        """이 시각 전에는 요청이 거부된다. **기다릴 것이 없으면 None.**

        orchestrator 는 `RESET_DONE` 뒤에도 `self._accept_after` 까지 약 3 s 거부한다
        (계약 6절 5). 발행기가 `reset_settle_s` 3.5 s 를 기다리는 이유가 이것이다.
        """
        if self._reset_in_progress():
            return None  # 아직 RESET_DONE 도 안 왔다 — 언제 풀릴지 모른다
        if self.reset_done_wall is None:
            return None
        after = self.reset_done_wall + timedelta(seconds=RESET_SETTLE_WALL_S)
        # 이미 지났으면 None — 화면이 "기다릴 것 없음" 을 한 눈에 알게 한다.
        return None if (now is not None and now >= after) else after

    def accept_in_s(self, now: datetime) -> float | None:
        """요청을 다시 받기까지 남은 초. **서버가 계산한다.**

        `accept_after_wall` 은 절대 시각이라, 화면이 남은 시간을 쓰려면 제 시계와 빼야 한다.
        **브라우저 시계가 서버와 같다는 보장이 없다** — 30 s 틀어져 있으면 "33초 뒤" 라고 쓴다.
        신선도를 `age_wall_s` 로 주는 것과 같은 이유로 여기서도 숫자를 서버가 낸다.
        """
        # `now` 를 넘긴 쪽을 쓴다 — 창이 지나면 None 이 되어 `accept_after_wall` 과 짝이 맞는다.
        # 안 넘기면 다 기다린 뒤에도 `0.0` 이 남아, 화면이 "아직 기다리는 중" 으로 읽는다.
        after = self.accept_after_wall(now)
        if after is None:
            return None
        return max(0.0, (after - now).total_seconds())

    def accepting_requests(self, now: datetime) -> bool:
        """지금 요청을 넣을 수 있는가. barrier 와 settle 창만 본다 (트립 여부는 별개)."""
        if self._reset_in_progress():
            return False
        after = self.accept_after_wall()
        return after is None or now >= after

    # 주의: accepting_requests 는 now 를 넘기지 않은 accept_after_wall() 을 써야 한다.
    # now 를 넘기면 "지났으니 None" 이 되어 늘 True 가 되어 버린다.

    @staticmethod
    def _trip_robot(mine: list[dict[str, Any]]) -> str | None:
        """이 트립을 수행하는 로봇. **AMR 만 후보다.**

        `REQUEST_ACCEPTED` 의 robot_id 가 AMR 이면 그것, 아니면 `event_key` 순으로 처음
        나오는 AMR 이벤트의 robot_id 다. 한 번 정해지면 트립 동안 바뀌지 않는다.

        조제기·M0609 이벤트는 트립의 로봇을 바꾸지 않는다 — 단계표와 같은 원칙이다.
        "마지막 이벤트의 robot_id" 로 채우면 `DISPENSED` 직후에 로봇이 `dispenser` 로
        보인다(master02 스텁 원문에서 실제로 그렇게 찍혔다).
        """
        accepted = next((e for e in mine if e["name"] == "REQUEST_ACCEPTED"), None)
        if accepted and AMR_ID_RE.match(accepted["robot_id"] or ""):
            return accepted["robot_id"]
        return next((e["robot_id"] for e in mine
                     if AMR_ID_RE.match(e["robot_id"] or "")), None)

    @staticmethod
    def _last_refill(epoch_events: list[dict[str, Any]]) -> dict[str, Any] | None:
        """이 세대의 **마지막** REFILL_DONE 요약. 보충 이력이 없으면 None.

        순서는 도착이 아니라 `event_key` 다(호출자가 이미 그 순으로 넘긴다) — 늦게 뭉쳐
        오면 도착 순서로는 옛 보충이 마지막으로 보인다.
        """
        done = None
        for e in epoch_events:
            if e["name"] == "REFILL_DONE":
                done = e
        if done is None:
            return None
        return refill_summary(done["detail"], done["stamp"])

    def _stock(self, slots: list[dict[str, Any]], epoch_events: list[dict[str, Any]]) -> dict[str, Any]:
        """재고 한눈에(재범 9/29 N3 "현재 알약통 N개·모듈 N개·지금 조제기에 N개"). api.md §6.1 `stock`.

        선반은 스테이지 재고 JSON 의 칸 수, 조제기는 DispenserStatus 슬롯, 보충 횟수는 이 세대의 REFILL_DONE(종류별).
        """
        pouches: dict[str, int] = {}
        for s in slots:
            item = s.get("item_id") or ""
            if item:
                pouches[item] = pouches.get(item, 0) + max(0, int(s.get("count") or 0))
        refills = dict.fromkeys(REFILL_KINDS, 0)
        for e in epoch_events:
            if e["name"] == "REFILL_DONE":
                kind = (e.get("refill") or {}).get("kind")
                if kind in refills:
                    refills[kind] += 1
        return {
            "shelf": None if self.shelf_stock is None else {k: dict(v) for k, v in self.shelf_stock.items()},
            "canisters_loaded": sum(1 for s in slots if int(s.get("count") or 0) > 0),
            "pouches_by_item": pouches,
            "refills": refills,
        }

    def _reset_in_progress(self) -> bool:
        """마지막 리셋이 아직 안 끝났는가.

        **도착 순서가 아니라 `event_key` 순으로 본다.** 늦게 붙으면 지난 이벤트가 작성자별로
        뭉쳐서 오므로, 도착 순서로 보면 옛 `RESET_BEGIN` 이 새 `RESET_DONE` 뒤로 갈 수 있고
        그러면 첫 화면이 "리셋 중" 으로 잘못 잠긴다.
        """
        marks = [e for e in self.ordered(self.events)
                 if e["name"] in ("RESET_BEGIN", "RESET_DONE")]
        return bool(marks) and marks[-1]["name"] == "RESET_BEGIN"

    def _stamped(self, src: dict[str, Any] | None, now: datetime,
                 keys: tuple[str, ...],
                 stale_after_s: float = STALE_WALL_S) -> dict[str, Any] | None:
        if src is None:
            return None
        age = self._age(src.get("wall"), now)
        out = {k: src.get(k) for k in keys}
        out["stamp"] = src.get("stamp")
        out["wall"] = iso(src["wall"]) if src.get("wall") else None
        out["stale"] = age is not None and age > stale_after_s
        return out

    def snapshot(self, now: datetime) -> dict[str, Any]:
        clock_age = self._age(self.clock_wall, now)
        signal_ages = self._signal_ages(now)
        epoch_events = self.ordered([e for e in self.events if e["epoch"] == self.epoch])
        trip = self._trip()

        dispenser = None
        if self.dispenser is not None:
            paused = list(self.dispenser.get("paused_item_ids") or [])
            dispenser = self._stamped(
                self.dispenser, now, ("paused_item_ids", "queue_length", "belt_occupied"),
                stale_after_s=DISPENSER_STALE_WALL_S)
            dispenser["paused"] = bool(paused)
            refilling, refilling_items = self._refilling(epoch_events, paused)
            dispenser["refilling"] = refilling
            dispenser["refilling_item_ids"] = refilling_items
            slots = list(self.dispenser.get("slots") or [])
            dispenser["refill_targets"] = [refill_target(item, slots, self.shelf_kinds)
                                           for item in refilling_items]
            read = self.container_read
            dispenser["container_read"] = None if read is None else {
                **{k: read[k] for k in ("tag_id", "status", "stamp")},
                "wall": iso(read["wall"]),
                "age_wall_s": self._age(read["wall"], now),
            }
            dispenser["last_refill"] = self._last_refill(epoch_events)
            dispenser["stock"] = self._stock(slots, epoch_events)
            dispenser["slots"] = [
                {**s, "slot_name": "A" if int(s.get("slot", 0)) == 0 else "B"}
                for s in (self.dispenser.get("slots") or [])
            ]

        return {
            "server_run_id": self.server_run_id,
            "server_time": iso(now),
            "mode": self.source_mode,
            "deployment": dict(self.deployment),
            "commands_enabled": self.commands_enabled,
            "mock_faults": list(self.mock_faults),
            "seq": self.seq,
            "epoch": self.epoch,
            "reset_in_progress": self._reset_in_progress(),
            "accepting_requests": self.accepting_requests(now),
            "accept_after_wall": (iso(after) if (after := self.accept_after_wall(now)) else None),
            "accept_in_s": self.accept_in_s(now),
            "clock": {
                "sim_s": self.clock_sim_s,
                "alive": clock_age is not None and clock_age <= CLOCK_STALE_WALL_S,
                "age_wall_s": clock_age,
            },
            "trip": trip,
            "stage": self._stage(trip, dispenser),
            "dispenser": dispenser,
            "belt": self._stamped(self.belt, now, ("occupied", "at_end", "order_id")),
            "signals": {
                key: {
                    "value": self.signals[key]["value"],
                    "wall": iso(self.signals[key]["wall"]),
                    "age_wall_s": signal_ages.get(key),
                    "stale": (signal_ages.get(key) or 0.0) > STALE_WALL_S,
                }
                for key in SIGNAL_KEYS if key in self.signals
            } | ({"speed_limit": view} if (view := self.speed_limit_view(now)) is not None else {}),
            "sim_running": self.sim_running_view(now),
            "qr_reads": self.qr_reads_view(now),
            "robots": self._robots(now, epoch_events),
            "dummies": self._fleet(now, "dummy"),
            "scan": self.live.scan_view(now) if self.live is not None else None,
            "cabinet": (None if (self.cabinet is None or not self.show_evaluator) else {
                **{k: self.cabinet[k] for k in ("order_id", "cabinet_id", "present")},
                "wall": iso(self.cabinet["wall"]),
                # 판정에 쓰지 말 것 — 평가 노드의 관측이다.
                "source": "evaluator",
                "display_only": True,
            }),
            "recent_events": epoch_events[-self.max_events:],
            "alarms": evaluate_alarms(
                events=epoch_events,
                orders=self.orders,
                dispenser=self.dispenser,
                signal_ages=signal_ages,
                clock_age_wall_s=clock_age,
                epoch=self.epoch,
                now_sim_s=self.clock_sim_s or 0.0,
                destination_id=(trip or {}).get("destination_id"),
                trip_request_id=(trip or {}).get("request_id") if trip else "",
                refill_timeout_sim_s=self.refill_timeout_sim_s,
                reset_age_wall_s=(self._age(self.reset_begin_wall, now)
                                  if self._reset_in_progress() else None),
                reset_timeout_wall_s=self.reset_timeout_wall_s,
                obstacle_stop_age_wall_s=self.obstacle_stop_age(now),
                p3_alerts=self.active_p3_alerts(now),
            ),
        }
