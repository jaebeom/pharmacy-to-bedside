"""ROS 메시지 → dict 변환. **순수 함수이고 ROS 를 import 하지 않는다.**

실물 브리지의 뼈대다. 구독 콜백이 받은 msg 객체를 여기서 평범한 dict 로 바꿔
`WorldState.note_*` 에 넣는다. 그래서 상태 조립·알람·snapshot 전체가 ROS 없이 테스트된다.

읽는 방식은 **duck typing** 이다 — `getattr` 만 쓰므로 진짜 msg 객체든 가짜든 똑같이 돈다.
테스트는 `SimpleNamespace` 가짜를 넣어 돌린다.

필드 이름은 작전이 준 msg 발췌 그대로다:

    Event             header, name, request_id, order_id, robot_id, epoch, detail
    OrderStatus       header, request_id, order_id, state, reason
    DispenserStatus   header, slots, paused_item_ids, queue_length, belt_occupied
    DispenserSlot     item_id, slot, lot_id, expiry, count, active
    BeltState         header, occupied, at_end, order_id
    TagRead           header, kind, tag_id, status
    DeliveryRequest   header, request_id, mode, destination_id, orders
    Order             order_id, patient_id, item_id

**나가는 dict 의 키는 클론 뒤 PR #105 의 status_view 공개 API 표로 맞춘다.**
그때 고칠 곳은 이 파일 하나이고, 위쪽(state·alarms·API)은 손대지 않아도 되게 짰다.
"""

from __future__ import annotations

from typing import Any

# rcl_interfaces/msg/Log 의 레벨 상수
LOG_DEBUG, LOG_INFO, LOG_WARN, LOG_ERROR, LOG_FATAL = 10, 20, 30, 40, 50
LOG_LEVEL_NAMES = {
    LOG_DEBUG: "debug", LOG_INFO: "info", LOG_WARN: "warn",
    LOG_ERROR: "error", LOG_FATAL: "fatal",
}


def _get(msg: Any, name: str, default: Any = None) -> Any:
    return getattr(msg, name, default)


def _text(msg: Any, name: str) -> str:
    """ROS 문자열 필드는 비어 있을 수 있다. 항상 str 을 돌려준다."""
    value = _get(msg, name, "")
    return value if isinstance(value, str) else ("" if value is None else str(value))


def _int(msg: Any, name: str, default: int = 0) -> int:
    value = _get(msg, name, default)
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def time_to_seconds(time_msg: Any) -> float:
    """`builtin_interfaces/Time`(sec, nanosec) → 초(float). 없으면 0.0."""
    if time_msg is None:
        return 0.0
    sec = _int(time_msg, "sec")
    nanosec = _int(time_msg, "nanosec")
    return sec + nanosec / 1e9


def header_stamp(msg: Any) -> float:
    """`msg.header.stamp` → 초. Event 의 stamp 는 **sim time** 이다."""
    return time_to_seconds(_get(_get(msg, "header"), "stamp"))


def clock_to_seconds(clock_msg: Any) -> float:
    """`rosgraph_msgs/Clock` → sim 초."""
    return time_to_seconds(_get(clock_msg, "clock"))


def bool_value(msg: Any) -> bool:
    """`std_msgs/Bool` → bool."""
    return bool(_get(msg, "data", False))


def event_to_dict(msg: Any) -> dict[str, Any]:
    return {
        "name": _text(msg, "name"),
        "request_id": _text(msg, "request_id"),
        "order_id": _text(msg, "order_id"),
        "robot_id": _text(msg, "robot_id"),
        "epoch": _int(msg, "epoch"),
        # detail 은 자유 문자열이고 판정에 쓰지 않는다. 구조 파싱은
        # REQUEST_ACCEPTED 의 #104 JSON 하나만 예외다 (app/request_detail.py).
        "detail": _text(msg, "detail"),
        "stamp": header_stamp(msg),
    }


def order_status_to_dict(msg: Any) -> dict[str, Any]:
    return {
        "request_id": _text(msg, "request_id"),
        "order_id": _text(msg, "order_id"),
        "state": _int(msg, "state"),
        "reason": _text(msg, "reason"),
        "stamp": header_stamp(msg),
    }


def dispenser_slot_to_dict(slot: Any) -> dict[str, Any]:
    return {
        "item_id": _text(slot, "item_id"),
        "slot": _int(slot, "slot"),
        "lot_id": _text(slot, "lot_id"),
        "expiry": _text(slot, "expiry"),
        "count": _int(slot, "count"),
        "active": bool(_get(slot, "active", False)),
        # capacity 는 msg 에 없다 — 만들지 않는다 (api.md §6.1).
    }


def dispenser_status_to_dict(msg: Any) -> dict[str, Any]:
    return {
        "slots": [dispenser_slot_to_dict(s) for s in (_get(msg, "slots") or [])],
        "paused_item_ids": [str(i) for i in (_get(msg, "paused_item_ids") or [])],
        "queue_length": _int(msg, "queue_length"),
        "belt_occupied": bool(_get(msg, "belt_occupied", False)),
        "stamp": header_stamp(msg),
    }


def belt_state_to_dict(msg: Any) -> dict[str, Any]:
    return {
        "occupied": bool(_get(msg, "occupied", False)),
        "at_end": bool(_get(msg, "at_end", False)),
        "order_id": _text(msg, "order_id"),
        "stamp": header_stamp(msg),
    }


def tag_read_to_dict(msg: Any) -> dict[str, Any]:
    """`TagRead` — 손 카메라 QR 판독 한 건. 종류(`kind`)는 거르지 않는다 — 상태가 고른다."""
    return {
        "kind": _int(msg, "kind"),
        "tag_id": _text(msg, "tag_id"),
        "status": _int(msg, "status"),
        "stamp": header_stamp(msg),
    }


def image_to_dict(msg: Any) -> dict[str, Any]:
    """`sensor_msgs/Image` → 프레임 dict. `data` 는 복사한 bytes 다(메시지 버퍼를 붙잡지 않게)."""
    return {
        "data": bytes(_get(msg, "data") or b""),
        "width": _int(msg, "width"),
        "height": _int(msg, "height"),
        "encoding": _text(msg, "encoding"),
        "step": _int(msg, "step"),
        "stamp": header_stamp(msg),
    }


def pouch_array_to_list(msg: Any) -> list[dict[str, Any]]:
    """`PouchDetectionArray` → 글자 오버레이용 목록. 자세는 싣지 않는다(픽셀 박스가 아니다)."""
    return [{"order_id": _text(d, "order_id"),
             "confidence": float(_get(d, "confidence", 0.0) or 0.0),
             "slot_index": _int(d, "slot_index", -1)}
            for d in (_get(msg, "detections") or [])]


#: 감속기의 정지 값(%). `rokey_p3_navigation/speed_governor.py` 의 `STOP_PERCENT` 와 같다.
#: 0 은 Nav2 에서 "제한 없음" 이라 감속기는 멈출 때 1 % 를 낸다.
SPEED_STOP_PERCENT = 1.0


def speed_limit_to_dict(msg: Any) -> dict[str, Any]:
    """`nav2_msgs/SpeedLimit`(header, percentage, speed_limit) → {speed_limit_pct, stop_reason, stamp}.

    감속기는 늘 `percentage=true` 로 낸다. Nav2 에서 0 은 "제한 없음" 이라 100 으로 바꾼다.
    m/s 로 온 값(`percentage=false`)은 비율을 모르므로 `speed_limit_pct` 를 None 으로 둔다.
    msg 에 사유 필드가 없다 — 정지 값(≤ 1 %)이면 감속기 정지 규칙(진행 방향 앞, 지도에 없는 장애물)이다.
    """
    value = float(_get(msg, "speed_limit", 0.0) or 0.0)
    pct = None
    if bool(_get(msg, "percentage", False)):
        pct = 100.0 if value <= 0.0 else min(value, 100.0)
    stopped = pct is not None and pct <= SPEED_STOP_PERCENT
    return {"speed_limit_pct": pct, "stop_reason": "obstacle_ahead" if stopped else None,
            "stamp": header_stamp(msg)}


def string_data(msg: Any) -> str:
    """`std_msgs/String` → str."""
    return _text(msg, "data")


def cabinet_observation_to_dict(msg: Any) -> dict[str, Any]:
    """`/evaluator/cabinet` (선택 토픽).

    **필드 이름 미확정** — `status_view.note_cabinet(order_id, cabinet_id, present)` 의
    인자에서 역으로 잡았다. 클론 뒤 msg 원문으로 확인한다.
    """
    return {
        "order_id": _text(msg, "order_id"),
        "cabinet_id": _text(msg, "cabinet_id"),
        "present": bool(_get(msg, "present", False)),
        "stamp": header_stamp(msg),
    }


def order_to_dict(order: Any) -> dict[str, Any]:
    """`Order` — /deliver 액션 goal 안에 있다. 웹이 직접 넣은 요청에서만 쓴다."""
    return {
        "order_id": _text(order, "order_id"),
        "patient_id": _text(order, "patient_id") or None,
        "item_id": _text(order, "item_id") or None,
    }


def delivery_request_to_dict(msg: Any) -> dict[str, Any]:
    """`DeliveryRequest` — 토픽으로는 **안 나온다**(액션 goal). 웹이 보낼 때 쓴다."""
    return {
        "request_id": _text(msg, "request_id"),
        "mode": _int(msg, "mode"),
        "destination_id": _text(msg, "destination_id"),
        "orders": [order_to_dict(o) for o in (_get(msg, "orders") or [])],
    }


def log_to_dict(msg: Any) -> dict[str, Any]:
    """`rcl_interfaces/msg/Log` → api.md §5 의 로그 객체.

    `name` 이 노드 이름, `msg` 가 본문이다. stamp 는 header 가 아니라 최상위에 있다.
    """
    level = _int(msg, "level")
    return {
        "level": LOG_LEVEL_NAMES.get(level, str(level)),
        "level_value": level,
        "node": _text(msg, "name"),
        "message": _text(msg, "msg"),
        "stamp": time_to_seconds(_get(msg, "stamp")),
    }


def transform_to_pose(transform_stamped: Any) -> dict[str, float]:
    """`geometry_msgs/TransformStamped`(map → <robot>/base_link) → {x, y, yaw, stamp}.

    yaw 는 쿼터니언의 z 축 회전. `stamp` 는 변환의 시각(sim s)이다 — 같은 값이 다시 오면 새 정보가 아니다.
    """
    import math

    t = _get(transform_stamped, "transform")
    tr, q = _get(t, "translation"), _get(t, "rotation")
    qx, qy, qz, qw = (float(_get(q, k, 0.0) or 0.0) for k in ("x", "y", "z", "w"))
    yaw = math.atan2(2.0 * (qw * qz + qx * qy), 1.0 - 2.0 * (qy * qy + qz * qz))
    return {"x": float(_get(tr, "x", 0.0) or 0.0), "y": float(_get(tr, "y", 0.0) or 0.0), "yaw": yaw,
            "stamp": header_stamp(transform_stamped)}
