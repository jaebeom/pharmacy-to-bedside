"""알람 규칙 — 순수 함수.

이 모듈은 ROS 를 import 하지 않는다. 입력은 평범한 dict/float 뿐이고,
출력은 api.md §4 의 알람 객체(dict) 목록이다. 그래서 ROS 없이 테스트된다.

판정·정렬은 sim 시각(stamp)과 epoch 으로, 신선도(stale)는 wall 나이로 한다.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from app.orchestrator_view import CLOCK_FRESH_S, SIGNAL_FRESH_S
from app.orchestrator_view import SIGNAL_KEYS as _SIGNAL_KEYS
from app.request_detail import parse_request_detail

# ── 임계값 ──────────────────────────────────────────────────────────────
# 상태 heartbeat(H) 토픽의 신선도 임계. **계약 v1 4절 값 그대로다.**
# H 는 5 Hz 주기 발행(gripper_holding 은 10 Hz)이라 1.0 s 는 5주기 누락에 해당한다 — 빡빡하지 않다.
STALE_WALL_S = SIGNAL_FRESH_S

# DispenserStatus 는 H 가 아니라 L(latched, 변화 시 + 1 Hz)이다. 1 Hz 발행에 1.0 s 임계를
# 적용하면 실물에서 가짜 stale 이 깜빡인다. **계약에 이 임계는 없다 — 웹 표시용이다.**
# status_view 가 dispenser 신선도를 어떻게 다루는지는 클론 뒤 원문으로 맞춘다 (미확정).
DISPENSER_STALE_WALL_S = 3.0
CLOCK_STALE_WALL_S = CLOCK_FRESH_S
# 보충 실패 임계. orchestrator 의 refill 액션 시한(90 s) + 재시도(5 s 간격 최대 3회)를
# 클론 뒤 코드로 확인해 맞춘다. 그 전 기본값이며 실행 인자로 덮어쓸 수 있다.
# 팔 #99 가 들어가면 정상 보충이 28 → 33-34 sim s(홈 복귀 포함)로 늘어난다.
REFILL_TIMEOUT_SIM_S = 120.0

# RESET_BEGIN 뒤 이만큼(wall)이 지나도 RESET_DONE 이 없으면 리셋이 멈춘 것으로 본다.
# orchestrator 의 리셋 시한이 30 s wall 이라 여유를 얹었다. 밖에서 barrier_failed 를
# 알 방법이 지금은 "RESET_DONE 이 끝내 안 온다" 뿐이다.
RESET_TIMEOUT_WALL_S = 35.0

# RESET_DONE 뒤에도 orchestrator 는 약 3 s wall 동안 요청을 거부한다(계약 6절 5).
# 발행기가 기다리는 reset_settle_s 와 같은 값을 쓴다.
RESET_SETTLE_WALL_S = 3.5

# ── OrderStatus.state ───────────────────────────────────────────────────
STATE_ACCEPTED = 0
STATE_IN_PROGRESS = 1
STATE_DELIVERED = 2
STATE_SUCCESS = 10  # orchestrator 는 안 냄. event_logger 가 기록에만 쓴다.
STATE_HOLD_RETURN = 11
STATE_ABORT = 12
STATE_TIMEOUT = 13

STATE_NAMES = {
    STATE_ACCEPTED: "ACCEPTED",
    STATE_IN_PROGRESS: "IN_PROGRESS",
    STATE_DELIVERED: "DELIVERED",
    STATE_SUCCESS: "SUCCESS",
    STATE_HOLD_RETURN: "HOLD_RETURN",
    STATE_ABORT: "ABORT",
    STATE_TIMEOUT: "TIMEOUT",
}

# 종료 상태 → (kind, level)
TERMINAL_STATES = {
    STATE_HOLD_RETURN: ("HOLD_RETURN", "warn"),
    STATE_ABORT: ("ABORT", "error"),
    STATE_TIMEOUT: ("TIMEOUT", "error"),
}

#: `pharmacy_only` 모드의 **정상 완주** 사유(`trip_fsm.REASON_PHARMACY_ONLY`).
#: 이 모드는 적재 뒤 정거장으로 가지 않고 도크로 복귀하며, 실은 주문을
#: `HOLD_RETURN(pharmacy_only)` 로 닫는다(`trip_fsm.py:733`). 봉투가 상판에 남은 채
#: 복귀한 것이 사실이므로 상태는 `HOLD_RETURN` 이 맞다 — **다만 이상이 아니다.**
#: 1차 시연이 이 모드라, 경고로 올리면 매 바퀴 성공이 청중에게 노란 줄로 보인다.
REASON_PHARMACY_ONLY = "pharmacy_only"

#: 주문의 결말. `state`·`reason` 을 화면이 한 번에 분기할 수 있게 서버가 파생한다.
#: `HOLD_RETURN` 이 둘로 갈리는 것이 이 필드가 있는 이유다.
#: 값은 화면이 다르게 그리는 경우와 **1:1** 이다. 합쳐 두면 화면이 `state_name` 으로
#: 다시 갈라야 하고, "화면은 outcome 하나로 분기한다" 가 깨진다.
OUTCOME_ACCEPTED = "accepted"
OUTCOME_IN_PROGRESS = "in_progress"
OUTCOME_DELIVERED = "delivered"
OUTCOME_PHARMACY_DONE = "pharmacy_done"
OUTCOME_HELD = "held"
OUTCOME_ABORTED = "aborted"
OUTCOME_TIMEOUT = "timeout"

_OUTCOME_BY_STATE = {
    STATE_ACCEPTED: OUTCOME_ACCEPTED,
    STATE_IN_PROGRESS: OUTCOME_IN_PROGRESS,
    STATE_DELIVERED: OUTCOME_DELIVERED,
    STATE_SUCCESS: OUTCOME_DELIVERED,
    STATE_ABORT: OUTCOME_ABORTED,
    STATE_TIMEOUT: OUTCOME_TIMEOUT,
}


def is_pharmacy_only_close(state: int, reason: str | None) -> bool:
    """`pharmacy_only` 모드의 정상 완주인가. **알람 판정과 outcome 이 같은 함수를 쓴다.**

    두 곳에서 따로 판정하면 한쪽만 고쳐져 "알람은 안 뜨는데 화면은 회수로 보이는" 식이 된다.
    """
    return int(state) == STATE_HOLD_RETURN and (reason or "") == REASON_PHARMACY_ONLY


def unavailable_items(dispenser: Mapping[str, Any] | None) -> set[str]:
    """지금 낼 수 없는 약품. **순수 함수** — snapshot 의 `dispenser` 만 본다.

    실습8 에서 재고 0 인 약품의 요청이 수락됐다가 적재에서 `ABORT out_of_stock` 으로
    1.2 s 만에 끝났다. 사람이 보기엔 "넣었는데 갑자기 죽었다" 다. 미리 막으면 그 자리에서
    이유를 말할 수 있다.

    낼 수 없다고 보는 경우:
      - `paused_item_ids` 에 있다(보충 요청 중·PAUSED)
      - 그 약품을 담은 슬롯이 **전부** `count == 0` 이거나 `active == false`

    **슬롯에 아예 없는 약품은 넣지 않는다** — 모르는 것으로 거부하지 않는다.
    """
    if not dispenser:
        return set()
    out = {str(i) for i in (dispenser.get("paused_item_ids") or []) if i}

    usable: dict[str, bool] = {}
    for slot in dispenser.get("slots") or []:
        item = str(slot.get("item_id") or "")
        if not item:
            continue
        ok = bool(slot.get("active")) and int(slot.get("count") or 0) > 0
        usable[item] = usable.get(item, False) or ok
    out |= {item for item, ok in usable.items() if not ok}
    return out


def available_stock(dispenser: Mapping[str, Any] | None) -> dict[str, int]:
    """품목별로 지금 낼 수 있는 개수. **순수 함수** — snapshot 의 `dispenser` 만 본다.

    활성 슬롯(`active`)의 `count` 를 합한다. 한 품목이 여러 슬롯에 있으면 다 더한다.
    **슬롯에 없는 품목은 키가 없다** — 0 이 아니라 "모른다" 다. 모르는 것으로 거부하지 않는
    기존 원칙과 같다(`unavailable_items` 참고).
    """
    if not dispenser:
        return {}
    stock: dict[str, int] = {}
    for slot in dispenser.get("slots") or []:
        item = str(slot.get("item_id") or "")
        if not item:
            continue
        count = int(slot.get("count") or 0) if slot.get("active") else 0
        stock[item] = stock.get(item, 0) + count
    return stock


def outcome_for(state: int, reason: str | None) -> str:
    """주문의 결말 한 낱말. 화면은 이것으로 분기한다."""
    if is_pharmacy_only_close(state, reason):
        return OUTCOME_PHARMACY_DONE
    if int(state) == STATE_HOLD_RETURN:
        return OUTCOME_HELD
    # 모르는 상태는 접수로 떨어뜨린다 — 없는 결말을 지어내지 않는다.
    return _OUTCOME_BY_STATE.get(int(state), OUTCOME_ACCEPTED)

LEVEL_ORDER = {"error": 0, "warn": 1, "info": 2}

#: 신호 키 5개. **원문(status_view.SIGNALS)에서 온다** — 여기서 새로 적지 않는다.
SIGNAL_KEYS = _SIGNAL_KEYS


def alarm_id(kind: str, request_id: str | None, order_id: str | None, epoch: int) -> str:
    """같은 알람이 중복으로 쌓이지 않도록 하는 안정적인 짧은 id."""
    raw = f"{kind}|{request_id or ''}|{order_id or ''}|{epoch}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:6]


def make_alarm(
    kind: str,
    level: str,
    message: str,
    *,
    epoch: int,
    stamp: float,
    request_id: str | None = None,
    order_id: str | None = None,
) -> dict[str, Any]:
    """api.md §4 의 알람 객체. 필드는 정확히 8개."""
    return {
        "id": alarm_id(kind, request_id, order_id, epoch),
        "level": level,
        "kind": kind,
        "message": message,
        "request_id": request_id,
        "order_id": order_id,
        "stamp": stamp,
        "epoch": epoch,
    }


#: 집기 실패 사유(팔 `pick_permission` outcome) → 사람 말. 병원은 QR 을 반드시 찍는다(재범 9/29, #784):
#: 봉투 QR 이 주문과 다르면 `qr_mismatch`, 못 읽으면 `not_detected` 로 주문이 닫힌다. 원문 코드도 같이 싣는다.
REASON_TEXT = {
    "qr_mismatch": "약 QR 이 주문과 다름",
    "not_detected": "약 QR 을 못 읽음",
}


def _with_reason(base: str, reason: str | None) -> str:
    """HOLD_RETURN·ABORT·TIMEOUT 은 reason 을 반드시 싣는다. 아는 사유는 사람 말을 앞에 둔다."""
    reason = (reason or "").strip()
    if not reason:
        return base
    text = REASON_TEXT.get(reason)
    return f"{base} (사유: {text} — {reason})" if text else f"{base} (사유: {reason})"


def _last_event(events: Sequence[Mapping[str, Any]], *names: str) -> Mapping[str, Any] | None:
    for ev in reversed(events):
        if ev.get("name") in names:
            return ev
    return None


def unmatched_refill_requests(events: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    """아직 닫히지 않은 `REFILL_REQUESTED`. **이벤트 이름만** 본다.

    `REFILL_REQUESTED.detail` 은 사람 메모라 품목 키가 아니다. 그래서 완료를 품목에
    붙이지 않고, 각 `REFILL_DONE` 이 **아직 열린 요청 중 가장 이른 것**을 닫는다.
    요청 순서대로 끝나는 한 바퀴에서는 품목과 같고, 한 품목의 완료가 다른 품목의
    진행·실패 알람을 지우는 일은 없다.

    호출자는 현재 epoch 이벤트를 `event_key` 순으로 넘긴다. 도착 순서가 아니다.
    """
    pending: list[Mapping[str, Any]] = []
    for ev in events:
        name = ev.get("name")
        if name == "REFILL_REQUESTED":
            pending.append(ev)
        elif name == "REFILL_DONE" and pending:
            pending.pop(0)
    return pending


# ── 개별 규칙 ───────────────────────────────────────────────────────────
# 각 규칙은 (입력) -> Iterable[alarm] 이다. 부작용 없음.

#: 긴급 모드(DeliveryRequest.MODE_URGENT).
MODE_URGENT = 1


def accepted_requests(events) -> dict[str, dict[str, Any]]:
    """`REQUEST_ACCEPTED.detail` 에서 요청마다 {mode, destination_id}. detail 이 비면(옛 빌드) 없다."""
    out: dict[str, dict[str, Any]] = {}
    for ev in events:
        if ev.get("name") == "REQUEST_ACCEPTED" and ev.get("request_id"):
            parsed = parse_request_detail(ev.get("detail"))
            if parsed is not None:
                out[ev["request_id"]] = parsed
    return out


def _where(ev, requests, destination_id, trip_request_id) -> str:
    """이 이벤트의 목적지. **그 이벤트가 속한 요청**의 것이다 — 지금 트립의 것이 아니다.

    9/23 스텁 한 바퀴: 긴급(bed_a2) 뒤 병동 묶음(station_a) 트립이 열리자 앞 트립의 긴급 알람이
    "— station_a" 로 바뀌었다. 요청의 detail 이 없으면(옛 빌드) 지금 트립의 이벤트일 때만
    `destination_id` 를 쓴다(`trip_request_id` 를 모르는 호출은 예전처럼 쓴다).
    """
    request_id = ev.get("request_id") or None
    known = (requests.get(request_id) or {}).get("destination_id") if request_id else None
    if known:
        return known
    if destination_id and (trip_request_id is None or request_id == trip_request_id):
        return destination_id
    return "목적지"


def rule_urgent_arriving(events, epoch, destination_id, trip_request_id=None) -> Iterable[dict]:
    """ARRIVING 은 긴급 모드에서만 나온다. 나오면 곧 도착한다는 뜻.

    **긴급이 아닌 요청의 ARRIVING 은 알람이 아니다** — orchestrator 는 긴급에만 내지만, 모드를 아는
    요청이 긴급이 아니면 웹도 거른다(api.md 4.1 "긴급 모드만"). 모드를 모르면 orchestrator 를 믿는다.
    """
    requests = accepted_requests(events)
    for ev in events:
        if ev.get("name") != "ARRIVING":
            continue
        mode = (requests.get(ev.get("request_id") or "") or {}).get("mode")
        if mode is not None and mode != MODE_URGENT:
            continue
        where = _where(ev, requests, destination_id, trip_request_id)
        yield make_alarm(
            "URGENT_ARRIVING", "warn", f"긴급 배송 접근 중 — {where}",
            epoch=epoch, stamp=float(ev.get("stamp", 0.0)),
            request_id=ev.get("request_id") or None,
            order_id=ev.get("order_id") or None,
        )


def rule_auth_fail(events, epoch, destination_id, trip_request_id=None) -> Iterable[dict]:
    requests = accepted_requests(events)
    for ev in events:
        if ev.get("name") != "AUTH_FAIL":
            continue
        where = _where(ev, requests, destination_id, trip_request_id)
        # 묶음의 정거장 인증 실패에는 order_id 가 없다 — "?" 대신 요청을 적는다.
        order = ev.get("order_id") or ev.get("request_id") or "?"
        yield make_alarm(
            "AUTH_FAIL", "error", f"{where} 인증 실패 — {order}",
            epoch=epoch, stamp=float(ev.get("stamp", 0.0)),
            request_id=ev.get("request_id") or None,
            order_id=ev.get("order_id") or None,
        )


def rule_order_terminal(orders, epoch) -> Iterable[dict]:
    """HOLD_RETURN / ABORT / TIMEOUT. reason 을 반드시 싣는다."""
    for order_id, st in orders.items():
        state = int(st.get("state", -1))
        if is_pharmacy_only_close(state, st.get("reason")):
            # 정상 완주다. 알람으로 올리지 않는다 — 화면은 outcome 으로 안다.
            continue
        spec = TERMINAL_STATES.get(state)
        if spec is None:
            continue
        kind, level = spec
        base = {
            "HOLD_RETURN": f"주문 회수 — {order_id}",
            "ABORT": f"주문 중단 — {order_id}",
            "TIMEOUT": f"주문 시간초과 — {order_id}",
        }[kind]
        yield make_alarm(
            kind, level, _with_reason(base, st.get("reason")),
            epoch=epoch, stamp=float(st.get("stamp", 0.0)),
            request_id=st.get("request_id") or None,
            order_id=order_id,
        )


def rule_dispenser_paused(dispenser, epoch, now_sim_s) -> Iterable[dict]:
    if not dispenser:
        return
    paused = [i for i in (dispenser.get("paused_item_ids") or []) if i]
    if not paused:
        return
    yield make_alarm(
        "DISPENSER_PAUSED", "warn", f"조제기 정지 — {', '.join(paused)}",
        epoch=epoch, stamp=float(dispenser.get("stamp", now_sim_s)),
    )


def rule_refill_failed(events, epoch, now_sim_s, timeout_sim_s) -> Iterable[dict]:
    """열린 `REFILL_REQUESTED` 가 timeout_sim_s 안에 닫히지 않으면 실패.

    마지막 요청·마지막 완료만 보면, A 요청 → B 요청 → A 완료일 때 B 가 남아 있는데도
    알람이 사라진다. 닫히지 않은 요청마다 시한을 잰다.
    """
    for requested in unmatched_refill_requests(events):
        req_stamp = float(requested.get("stamp", 0.0))
        if now_sim_s - req_stamp <= timeout_sim_s:
            continue
        yield make_alarm(
            "REFILL_FAILED", "error",
            f"보충 실패 — {timeout_sim_s:.0f} s 내 REFILL_DONE 없음",
            epoch=epoch, stamp=req_stamp,
            request_id=requested.get("request_id") or None,
            order_id=requested.get("order_id") or None,
        )


def rule_status_stale(signal_ages, epoch, now_sim_s) -> Iterable[dict]:
    for key in SIGNAL_KEYS:
        age = signal_ages.get(key)
        if age is None or age <= STALE_WALL_S:
            continue
        yield make_alarm(
            "STATUS_STALE", "warn", f"상태 끊김 — {key} ({age:.1f} s)",
            epoch=epoch, stamp=now_sim_s, order_id=key,
        )


def rule_clock_stopped(clock_age_wall_s, epoch, now_sim_s) -> Iterable[dict]:
    if clock_age_wall_s is None or clock_age_wall_s <= CLOCK_STALE_WALL_S:
        return
    yield make_alarm(
        "CLOCK_STOPPED", "error", f"/clock 멈춤 ({clock_age_wall_s:.1f} s)",
        epoch=epoch, stamp=now_sim_s,
    )


def rule_reset_stuck(events, epoch, now_sim_s, reset_age_wall_s, timeout_wall_s
                     ) -> Iterable[dict]:
    """리셋이 시한 안에 안 끝났다. 밖에서 barrier_failed 를 알 수 있는 유일한 신호다."""
    if reset_age_wall_s is None or reset_age_wall_s <= timeout_wall_s:
        return
    begin = _last_event(events, "RESET_BEGIN")
    yield make_alarm(
        "RESET_STUCK", "error",
        f"리셋이 {reset_age_wall_s:.0f} s 째 안 끝났다 (epoch {epoch})",
        epoch=epoch,
        stamp=float(begin.get("stamp", now_sim_s)) if begin else now_sim_s,
    )


#: 감속기 정지(`signals.speed_limit.stop_reason`)가 이만큼(wall s) 이어지면 알린다. 작전 카드 ③ 값이다.
#: 정지 규칙은 멀어진 뒤 1 s(sim) 만에 풀리므로(`speed_governor.RESUME_DELAY_S`) 5 s 는 "비키지 않는 것이 있다" 다.
OBSTACLE_STOP_WALL_S = 5.0


def rule_obstacle_stop(stop_age_wall_s, epoch, now_sim_s, threshold_wall_s=OBSTACLE_STOP_WALL_S) -> Iterable[dict]:
    if stop_age_wall_s is None or stop_age_wall_s < threshold_wall_s:
        return
    yield make_alarm(
        "OBSTACLE_STOP", "warn", f"AMR 정지 — 앞 장애물 ({stop_age_wall_s:.1f} s)",
        epoch=epoch, stamp=now_sim_s,
    )


#: `/p3/alerts`(시뮬통합 #757, `rokey_p3_navigation/alerts.py`)의 kind → (알람 level, 문구 머리, 살아 있는 시간).
#: 재시도·개입은 지나가는 일이라 받은 뒤 `ALERT_RECENT_WALL_S` 동안만, 포기는 다음 리셋까지(최대 `ALERT_GIVEUP_WALL_S`).
ALERT_RECENT_WALL_S = 60.0
ALERT_GIVEUP_WALL_S = 600.0
P3_ALERTS = {
    "DOCK_RETRY": ("warn", "도킹 재시도", ALERT_RECENT_WALL_S),
    "DOCK_GIVEUP": ("error", "도킹 포기", ALERT_GIVEUP_WALL_S),
    "MAP_GUARD_INTERVENE": ("warn", "지도 개입", ALERT_RECENT_WALL_S),
    "MAP_GUARD_GIVEUP": ("error", "지도 미수신", ALERT_GIVEUP_WALL_S),
}


def parse_p3_alert(text: str | None) -> dict[str, Any] | None:
    """`/p3/alerts` 한 줄(JSON {kind, robot, detail, sim, wall}) → dict. 모르는 kind·깨진 JSON 은 None."""
    try:
        raw = json.loads(text) if isinstance(text, str) else None
    except ValueError:
        return None
    if not isinstance(raw, dict) or raw.get("kind") not in P3_ALERTS:
        return None
    sim = raw.get("sim")
    return {"kind": raw["kind"], "robot": str(raw.get("robot") or ""), "detail": str(raw.get("detail") or ""),
            "sim": float(sim) if isinstance(sim, (int, float)) and not isinstance(sim, bool) else 0.0}


def rule_p3_alerts(alerts, epoch) -> Iterable[dict]:
    """`alerts` = 살아 있는 알림 [{kind, robot, detail, sim}] (나이·리셋은 호출자가 이미 걸렀다)."""
    for alert in alerts:
        level, head, _ = P3_ALERTS[alert["kind"]]
        where = f" — {alert['robot']}" if alert["robot"] else ""
        detail = f": {alert['detail']}" if alert["detail"] else ""
        yield make_alarm(alert["kind"], level, f"{head}{where}{detail}",
                         epoch=epoch, stamp=alert["sim"], order_id=alert["robot"] or None)


def rule_reset_in_progress(events, epoch, now_sim_s) -> Iterable[dict]:
    """RESET_BEGIN 뒤 RESET_DONE 전이면 리셋 중."""
    begin = _last_event(events, "RESET_BEGIN")
    if begin is None:
        return
    done = _last_event(events, "RESET_DONE")
    if done is not None and float(done.get("stamp", 0.0)) >= float(begin.get("stamp", 0.0)):
        return
    yield make_alarm(
        "RESET_IN_PROGRESS", "info", f"리셋 중 (epoch {epoch})",
        epoch=epoch, stamp=float(begin.get("stamp", now_sim_s)),
    )


# ── 진입점 ──────────────────────────────────────────────────────────────


def evaluate_alarms(
    *,
    events: Sequence[Mapping[str, Any]] = (),
    orders: Mapping[str, Mapping[str, Any]] | None = None,
    dispenser: Mapping[str, Any] | None = None,
    signal_ages: Mapping[str, float] | None = None,
    clock_age_wall_s: float | None = None,
    epoch: int = 0,
    now_sim_s: float = 0.0,
    destination_id: str | None = None,
    trip_request_id: str | None = None,
    refill_timeout_sim_s: float = REFILL_TIMEOUT_SIM_S,
    reset_age_wall_s: float | None = None,
    reset_timeout_wall_s: float = RESET_TIMEOUT_WALL_S,
    obstacle_stop_age_wall_s: float | None = None,
    p3_alerts: Sequence[Mapping[str, Any]] = (),
) -> list[dict[str, Any]]:
    """현재 상태에서 살아있는 알람 목록을 만든다. 순수 함수.

    events 는 **현재 epoch 의** 이벤트만 seq 순으로 넘긴다.
    같은 (kind, request_id, order_id, epoch) 는 하나로 접힌다 — 나중 것이 이긴다.
    반환은 level(error→warn→info) 그다음 stamp 내림차순.
    """
    orders = orders or {}
    signal_ages = signal_ages or {}

    produced: list[dict[str, Any]] = []
    produced += list(rule_clock_stopped(clock_age_wall_s, epoch, now_sim_s))
    produced += list(rule_auth_fail(events, epoch, destination_id, trip_request_id))
    produced += list(rule_order_terminal(orders, epoch))
    produced += list(rule_refill_failed(events, epoch, now_sim_s, refill_timeout_sim_s))
    produced += list(rule_urgent_arriving(events, epoch, destination_id, trip_request_id))
    produced += list(rule_dispenser_paused(dispenser, epoch, now_sim_s))
    produced += list(rule_status_stale(signal_ages, epoch, now_sim_s))
    produced += list(rule_reset_in_progress(events, epoch, now_sim_s))
    produced += list(rule_reset_stuck(events, epoch, now_sim_s,
                                      reset_age_wall_s, reset_timeout_wall_s))
    produced += list(rule_obstacle_stop(obstacle_stop_age_wall_s, epoch, now_sim_s))
    produced += list(rule_p3_alerts(p3_alerts, epoch))

    deduped: dict[str, dict[str, Any]] = {}
    for alarm in produced:
        deduped[alarm["id"]] = alarm  # 나중 것이 이긴다

    return sorted(
        deduped.values(),
        key=lambda a: (LEVEL_ORDER.get(a["level"], 9), -a["stamp"]),
    )
