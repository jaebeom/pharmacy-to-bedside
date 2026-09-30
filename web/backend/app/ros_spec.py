"""구독 명세와 상태 반영 — **순수. rclpy 를 import 하지 않는다.**

브리지의 "무엇을 어떤 QoS 로 구독하고, 받은 것을 어디에 넣는가" 를 여기에 표로 둔다.
`ros_bridge.py` 는 이 표를 읽어 배선만 한다. 그래서 **배선 자체를 ROS 없이 시험**할 수 있다 —
토픽 이름 오타나 QoS 선택 실수는 실물에서만 드러나는 종류라, 표로 빼 두는 값이 크다.

QoS 이름은 `rokey_p3_orchestrator.ros_qos` 의 함수 이름이다(계약 2절 약어).
`status_monitor_node.py` 가 쓰는 것과 같아야 한다 — 같은 토픽을 다른 QoS 로 구독하면
한쪽만 메시지를 못 받는다.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, NamedTuple

M0609_ID = "m0609"
ROSOUT_DEPTH = 200


class Sub(NamedTuple):
    """구독 한 줄. `topic` 의 `{robot}` 은 `--robot-id` 로 채운다."""

    kind: str          # 상태에 넣을 때 쓰는 이름 (apply_update 의 분기)
    topic: str
    msg: str           # 메시지 타입 이름 (표에서는 문자열, 배선에서 실제 타입으로)
    qos: str           # ros_qos 의 함수 이름
    depth: int | None = None
    signal_key: str | None = None   # Bool 신호일 때 어느 키인지
    evaluator_only: bool = False


#: 구독 표. `status_monitor_node.py` 의 QoS 와 같다.
SUBSCRIPTIONS: tuple[Sub, ...] = (
    Sub("clock", "/clock", "Clock", "sensor_qos", 1),
    Sub("event", "/events", "Event", "latched_qos", 500),
    Sub("order", "/orders/status", "OrderStatus", "latched_qos", 50),
    Sub("dispenser", "/pharmacy/dispenser/status", "DispenserStatus", "latched_qos", 1),
    Sub("belt", "/pharmacy/belt", "BeltState", "heartbeat_qos"),
    Sub("signal", "/{robot}/arm/at_home", "Bool", "heartbeat_qos", signal_key="arm_at_home"),
    Sub("signal", "/{robot}/base/stopped", "Bool", "heartbeat_qos", signal_key="base_stopped"),
    Sub("signal", "/{robot}/gripper/holding", "Bool", "heartbeat_qos",
        signal_key="gripper_holding"),
    Sub("signal", f"/{M0609_ID}/arm/at_home", "Bool", "heartbeat_qos",
        signal_key="m0609_at_home"),
    # 감속기(speed_governor)의 Nav2 속도 제한. 1 Hz 재발행, reliable + transient local depth 1 이다.
    # nav2_msgs 가 없는 PC 에서는 브리지가 이 줄만 빼고 경고를 남긴다.
    Sub("speed_limit", "/{robot}/speed_limit", "SpeedLimit", "latched_qos", 1),
    # 여벌 AMR·더미 자리(시뮬통합 #754). TF 가 없는 몸체라 스테이지가 JSON 으로 낸다. 없는 회차엔 안 온다.
    Sub("fleet_poses", "/isaac/fleet/poses", "String", "reliable_qos", 1),
    # 도킹 재시도·포기, 지도 개입·포기(시뮬통합 #757, 계약 밖). transient local depth 20 — 늦게 붙어도 지난 것이 온다.
    Sub("p3_alert", "/p3/alerts", "String", "latched_qos", 20),
    # Isaac 타임라인 Play/Stop(시뮬통합 #759). 바뀔 때 + 1 Hz, volatile — 3 s 안 오면 Isaac 없음.
    Sub("sim_running", "/p3/sim_running", "Bool", "reliable_qos", 1),
    # 조제실 선반(장면 v2 JSON, latched). 보충 중 약의 약통 종류(→ 수납 종류)를 여기서 안다.
    Sub("shelf", "/m0609/shelf/inventory", "String", "latched_qos", 1),
    # M0609 손 카메라 QR 판독. 약통(cn-) 판독만 쓴다. `P3_CONTAINER_QR=1` 기동에서만 나온다.
    Sub("tag_read", f"/{M0609_ID}/hand_camera/tag_reads", "TagRead", "reliable_qos", 10),
    # AMR 손 카메라 QR 판독(봉투 ord-·환자 pt-·스테이션 st-). 재범 9/29 "QR 정보를 웹에"(api.md §1.12).
    Sub("qr_read", "/{robot}/hand_camera/tag_reads", "TagRead", "reliable_qos", 10),
    # /rosout 은 reliable + transient_local 로 발행된다. 같은 내구성으로 받아야 지난 줄도 온다.
    Sub("log", "/rosout", "Log", "latched_qos", ROSOUT_DEPTH),
    # 평가 전용 경로. 기본으로 구독하지 않는다 (계약 2.1절).
    Sub("cabinet", "/evaluator/cabinet", "CabinetObservation", "latched_qos", 50,
        evaluator_only=True),
)


#: 로봇 자세는 구독이 아니라 TF 조회다(`ros_bridge` 의 타이머). map → <robot>/base_link, 이 주기로.
#: 신선도 1.0 s(signals 와 같다) 안에 여러 번 오도록 5 Hz.
ROBOT_POSE_PERIOD_S = 0.2
MAP_FRAME = "map"


def robot_base_frame(robot_id: str) -> str:
    """계약 3절: `<robot>/base_link`(부모 `<robot>/odom`). fleet_node 와 같은 이름이다."""
    return f"{robot_id}/base_link"


def subscriptions(robot_id: str, *, show_evaluator: bool = False) -> list[Sub]:
    """이 실행에서 실제로 걸 구독 목록. `{robot}` 을 채우고 평가 토픽을 걸러 낸다."""
    return [sub._replace(topic=sub.topic.format(robot=robot_id))
            for sub in SUBSCRIPTIONS
            if show_evaluator or not sub.evaluator_only]


def apply_update(state: Any, kind: str, payload: Any, wall: datetime) -> None:
    """받은 것을 `WorldState` 에 넣는다. **호출자가 단일 이벤트 루프에서만 부른다.**

    모르는 `kind` 는 조용히 무시한다 — 표가 앞서 나가도 서버가 죽지 않게.
    """
    if kind == "clock":
        state.note_clock(payload, wall)
    elif kind == "event":
        state.note_event(payload, wall)
    elif kind == "order":
        state.note_order(payload)
    elif kind == "dispenser":
        state.note_dispenser(payload, wall)
    elif kind == "belt":
        state.note_belt(payload, wall)
    elif kind == "signal":
        state.note_signal(payload["key"], payload["value"], wall)
    elif kind == "robot_pose":
        state.note_robot_pose(payload["robot_id"], payload["pose"], wall)
    elif kind == "cabinet":
        state.note_cabinet(payload["order_id"], payload["cabinet_id"],
                           payload["present"], wall)
    elif kind == "log":
        state.note_log(payload, wall)
    elif kind == "speed_limit":
        state.note_speed_limit(payload, wall)
    elif kind == "fleet_poses":
        state.note_fleet_poses(payload, wall)
    elif kind == "p3_alert":
        state.note_p3_alert(payload, wall)
    elif kind == "sim_running":
        state.note_sim_running(payload, wall)
    elif kind == "shelf":
        state.note_shelf(payload)
    elif kind == "tag_read":
        state.note_tag_read(payload, wall)
    elif kind == "qr_read":
        state.note_qr_read(state.robot_id, payload, wall)
    elif kind == "scan" and state.live is not None:
        state.live.note_scan(payload, wall)
