"""실물 ROS 2 브리지 — 구독해서 `WorldState` 에 넣는다. **이 파일만 rclpy 를 import 한다.**

나머지(`state`·`alarms`·`ros_convert`·`order_pool`·`zones`)는 ROS 없이 돈다. 그래서 상태
조립과 알람 판정 전체가 `--mock` 으로 검증된다. 여기서 하는 일은 **배선뿐**이다.

스레드: rclpy 는 제 스레드에서 돌고, `WorldState` 는 asyncio 루프에서만 만진다.
콜백은 변환만 하고 `loop.call_soon_threadsafe` 로 넘긴다 — 상태를 두 스레드가 만지지 않는다.

QoS 는 `status_monitor_node.py` 의 것을 그대로 쓴다(`ros_qos.py` 를 import). 같은 토픽을
다른 QoS 로 구독하면 한쪽만 메시지를 못 받는 일이 생긴다.
"""

from __future__ import annotations

import asyncio
import contextlib
import threading
import time
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

import rclpy
from rclpy.clock import Clock, ClockType
from rclpy.executors import ExternalShutdownException, SingleThreadedExecutor
from rclpy.node import Node
from rcl_interfaces.msg import Log
from rosgraph_msgs.msg import Clock as ClockMsg
from std_msgs.msg import Bool, String

from rokey_p3_interfaces.action import Deliver
from rokey_p3_interfaces.msg import (
    BeltState,
    CabinetObservation,
    DeliveryRequest,
    DispenserStatus,
    Event,
    Order,
    OrderStatus,
    PouchDetectionArray,
    TagRead,
)
from rokey_p3_interfaces.srv import Reset
from rokey_p3_orchestrator.ros_qos import heartbeat_qos, latched_qos, reliable_qos, sensor_qos

from app.ros_convert import (
    header_stamp,
    transform_to_pose,
    LOG_WARN,
    belt_state_to_dict,
    bool_value,
    cabinet_observation_to_dict,
    clock_to_seconds,
    dispenser_status_to_dict,
    event_to_dict,
    log_to_dict,
    image_to_dict,
    order_status_to_dict,
    pouch_array_to_list,
    speed_limit_to_dict,
    string_data,
    tag_read_to_dict,
)
from app import live_sensors
from app.ros_spec import MAP_FRAME, ROBOT_POSE_PERIOD_S, apply_update, robot_base_frame, subscriptions
from app.state import WorldState

SERVICE_WAIT_S = 5.0

#: 표의 이름 → 실제 메시지 타입
MSG_TYPES = {
    "Clock": ClockMsg, "Event": Event, "OrderStatus": OrderStatus,
    "DispenserStatus": DispenserStatus, "BeltState": BeltState, "Bool": Bool,
    "Log": Log, "CabinetObservation": CabinetObservation, "String": String, "TagRead": TagRead,
}

#: 표의 이름 → QoS 함수 (ros_qos.py 원문)
QOS_FACTORIES = {
    "sensor_qos": sensor_qos, "heartbeat_qos": heartbeat_qos, "latched_qos": latched_qos,
    "reliable_qos": reliable_qos,
}

#: 표의 kind → 변환기
CONVERTERS = {
    "clock": clock_to_seconds, "event": event_to_dict, "order": order_status_to_dict,
    "dispenser": dispenser_status_to_dict, "belt": belt_state_to_dict,
    "cabinet": cabinet_observation_to_dict, "log": log_to_dict,
    "shelf": string_data, "tag_read": tag_read_to_dict, "speed_limit": speed_limit_to_dict,
    "fleet_poses": string_data,
    "p3_alert": string_data,
    "sim_running": bool_value,
    "qr_read": tag_read_to_dict,
}


def _optional_types() -> dict[str, Any]:
    """없을 수 있는 메시지 타입. Nav2 가 없는 PC(개발 PC)에서도 브리지는 떠야 한다."""
    out = {}
    try:
        from nav2_msgs.msg import SpeedLimit
        out["SpeedLimit"] = SpeedLimit
    except ImportError:
        pass
    return out


class BridgeNode(Node):
    """구독 전용 노드 + (명령이 열렸을 때만) 리셋 서비스·배송 액션 클라이언트.

    운영 노드가 아니다. `--allow-commands` 없이 띄우면 **발행도 서비스 호출도 하지 않는다.**
    """

    def __init__(self, submit: Callable[[str, Any], None], *,
                 robot_id: str = "amr_1", show_evaluator: bool = False,
                 allow_commands: bool = False, track_pose: bool = False, context=None,
                 live: live_sensors.LiveSensors | None = None) -> None:
        # **context 를 반드시 넘긴다.** 안 넘기면 전역 기본 컨텍스트를 쓰는데, 우리는
        # 전용 컨텍스트를 init 했으므로 "rclpy.init() has not been called" 로 죽는다.
        super().__init__("web_gateway", context=context)
        self._submit = submit

        types = {**MSG_TYPES, **_optional_types()}
        for sub in subscriptions(robot_id, show_evaluator=show_evaluator):
            if sub.msg not in types:
                self.get_logger().warning(f"{sub.topic} 는 구독하지 않는다: {sub.msg} 타입이 없다(패키지 미설치)")
                continue
            qos = QOS_FACTORIES[sub.qos]
            profile = qos(sub.depth) if sub.depth is not None else qos()
            self.create_subscription(types[sub.msg], sub.topic,
                                     self._callback(sub), profile)

        self._tf_buffer = None
        if track_pose:
            self._track_pose(robot_id)
        if live is not None:
            self._wire_live(robot_id, live)

        # 명령을 안 열었으면 클라이언트를 **만들지도 않는다.**
        self.reset_client = self.create_client(Reset, "/orchestrator/reset") \
            if allow_commands else None
        self.deliver_client = None
        if allow_commands:
            from rclpy.action import ActionClient
            self.deliver_client = ActionClient(self, Deliver, "/deliver")

    def _track_pose(self, robot_id: str) -> None:
        """로봇 자세 — TF map → <robot>/base_link 를 주기적으로 조회한다(fleet_node 와 같은 방식).

        `--map-file` 을 준 실행에서만 건다. 아직 TF 가 없으면(기동 직후) 조용히 건너뛴다 —
        snapshot.robots 가 비거나 stale 이 된다.
        """
        from rclpy.time import Time
        from tf2_ros import Buffer, TransformException, TransformListener
        self._tf_buffer = Buffer()
        self._tf_listener = TransformListener(self._tf_buffer, self)

        def on_pose_timer():
            try:
                t = self._tf_buffer.lookup_transform(MAP_FRAME, robot_base_frame(robot_id), Time())
            except TransformException:
                return
            self._submit("robot_pose", {"robot_id": robot_id, "pose": transform_to_pose(t)})
        self.create_timer(ROBOT_POSE_PERIOD_S, on_pose_timer)

    # ── 실시간 카메라·스캔 (--live-sensors, api.md §1.8) ───────────────────

    def _wire_live(self, robot_id: str, live: live_sensors.LiveSensors) -> None:
        """스캔·오버레이는 켜자마자, 카메라는 보는 사람이 있을 때만 구독한다.

        모두 best effort 로 받는다 — reliable 발행자와도 맞고, 웹이 늦어도 발행자를 붙잡지 않는다.
        카메라 구독을 걸고 푸는 것은 이 노드의 타이머(실행기 스레드)에서만 한다.
        """
        from sensor_msgs.msg import Image, LaserScan
        self._live = live
        self._image_subs: dict[str, Any] = {}
        self._scan_last = -float("inf")
        self.create_subscription(LaserScan, f"/{robot_id}/scan", self._on_scan, sensor_qos(1))
        for name, spec in live_sensors.CAMERAS.items():
            if spec.tag:
                self.create_subscription(
                    TagRead, live_sensors.topic_for(spec.tag, robot_id),
                    lambda msg, n=name: live.note_tag(n, tag_read_to_dict(msg)), sensor_qos(5))
            if spec.pouches:
                self.create_subscription(
                    PouchDetectionArray, live_sensors.topic_for(spec.pouches, robot_id),
                    lambda msg, n=name: live.note_pouches(n, pouch_array_to_list(msg)), sensor_qos(1))
        self._image_type = Image
        self.create_timer(0.5, self._sync_image_subs)

    def _sync_image_subs(self) -> None:
        wanted = self._live.wanted_images()
        for name in wanted - self._image_subs.keys():
            topic = live_sensors.topic_for(live_sensors.CAMERAS[name].image, self._live.robot_id)
            self._image_subs[name] = self.create_subscription(
                self._image_type, topic, lambda msg, n=name: self._on_image(n, msg), sensor_qos(1))
        for name in self._image_subs.keys() - wanted:
            self.destroy_subscription(self._image_subs.pop(name))

    def _on_image(self, name: str, msg) -> None:
        # 복사(image_to_dict) 전에 주기를 먼저 본다 — 5 fps 를 넘는 프레임은 복사도 하지 않는다.
        mono = time.monotonic()
        if self._live.due(name, mono):
            self._live.note_frame(name, image_to_dict(msg), datetime.now(timezone.utc), mono)

    def _on_scan(self, msg) -> None:
        mono = time.monotonic()
        if mono - self._scan_last < live_sensors.SCAN_PERIOD_S:
            return
        self._scan_last = mono
        frame, pose = msg.header.frame_id, None
        if self._tf_buffer is not None and frame:
            from rclpy.time import Time
            from tf2_ros import TransformException
            try:
                p = transform_to_pose(self._tf_buffer.lookup_transform(MAP_FRAME, frame, Time()))
                pose, frame = (p["x"], p["y"], p["yaw"]), MAP_FRAME
            except TransformException:
                pass
        self._submit("scan", {
            "robot_id": self._live.robot_id, "frame": frame, "stamp": header_stamp(msg),
            "range_max": float(msg.range_max),
            "points": live_sensors.scan_points(list(msg.ranges), msg.angle_min, msg.angle_increment,
                                               msg.range_min, msg.range_max, pose=pose),
        })

    def _callback(self, sub):
        """표 한 줄에 대한 콜백. 변환만 하고 넘긴다."""
        if sub.signal_key is not None:
            def on_signal(msg):
                self._submit("signal", {"key": sub.signal_key, "value": bool_value(msg)})
            return on_signal

        convert = CONVERTERS[sub.kind]
        if sub.kind == "log":
            def on_log(msg):
                record = convert(msg)
                if record["level_value"] >= LOG_WARN:   # WARN 미만은 담지 않는다 (api.md §5)
                    self._submit("log", record)
            return on_log

        def on_message(msg):
            self._submit(sub.kind, convert(msg))
        return on_message


class RosBridge:
    """rclpy 를 제 스레드에서 돌리고, 받은 것을 asyncio 루프로 넘긴다."""

    def __init__(self, state: WorldState, *, robot_id: str = "amr_1",
                 show_evaluator: bool = False, allow_commands: bool = False,
                 on_change: Callable[[], None] | None = None, track_pose: bool = False,
                 live: live_sensors.LiveSensors | None = None) -> None:
        self.state = state
        self.robot_id = robot_id
        self.show_evaluator = show_evaluator
        self.allow_commands = allow_commands
        self.track_pose = track_pose
        self.live = live
        self.on_change = on_change or (lambda: None)
        self.node: BridgeNode | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._executor: SingleThreadedExecutor | None = None
        self._thread: threading.Thread | None = None
        self._context = None

    # ── 수명 ────────────────────────────────────────────────────────────

    def start(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._context = rclpy.Context()
        self._context.init()
        self.node = BridgeNode(self._submit, robot_id=self.robot_id,
                               show_evaluator=self.show_evaluator,
                               allow_commands=self.allow_commands,
                               track_pose=self.track_pose, context=self._context,
                               live=self.live)
        self._executor = SingleThreadedExecutor(context=self._context)
        self._executor.add_node(self.node)
        self._thread = threading.Thread(target=self._spin, name="ros-bridge", daemon=True)
        self._thread.start()

    def _spin(self) -> None:
        with contextlib.suppress(ExternalShutdownException, KeyboardInterrupt):
            self._executor.spin()

    def stop(self) -> None:
        if self._executor is not None:
            self._executor.shutdown()
        if self.node is not None:
            self.node.destroy_node()
        if self._thread is not None:
            self._thread.join(timeout=5.0)
        if self._context is not None and self._context.ok():
            self._context.try_shutdown()

    # ── 스레드 경계 ─────────────────────────────────────────────────────

    def _submit(self, kind: str, payload: Any) -> None:
        """ROS 스레드에서 불린다. 상태는 만지지 않고 루프로 넘기기만 한다."""
        loop = self._loop
        if loop is None or loop.is_closed():
            return
        loop.call_soon_threadsafe(self._apply, kind, payload, datetime.now(timezone.utc))

    def _apply(self, kind: str, payload: Any, wall: datetime) -> None:
        """asyncio 루프에서만 불린다 — WorldState 를 만지는 유일한 자리."""
        apply_update(self.state, kind, payload, wall)
        self.on_change()

    # ── 명령 (열렸을 때만) ──────────────────────────────────────────────

    def call_reset(self) -> tuple[bool, str]:
        """`/orchestrator/reset` 을 부른다. 요청의 epoch 은 무시되므로 0 을 보낸다.

        **응답의 `message` 를 파싱하지 않는다** — 새 epoch 은 뒤따르는 RESET_BEGIN 이 말한다.
        """
        client = self.node.reset_client if self.node else None
        if client is None:
            return False, "명령이 열려 있지 않다"
        if not client.wait_for_service(timeout_sec=SERVICE_WAIT_S):
            return False, "/orchestrator/reset 서비스가 없다"
        future = client.call_async(Reset.Request(epoch=0))
        # 실행기는 다른 스레드에 있다. 여기서는 결과만 기다린다.
        done = threading.Event()
        future.add_done_callback(lambda _f: done.set())
        if not done.wait(timeout=SERVICE_WAIT_S):
            return False, "/orchestrator/reset 응답이 없다"
        response = future.result()
        return bool(response.ok), response.message

    def send_delivery(self, body: dict[str, Any]) -> tuple[bool, str]:
        """`/deliver` 액션에 goal 을 보낸다. 수락 여부만 돌려준다.

        진행은 `/events` 로 본다 — 액션 피드백을 따로 쓰지 않는다. **거부에는 사유가 없다.**
        """
        client = self.node.deliver_client if self.node else None
        if client is None:
            return False, "명령이 열려 있지 않다"
        if not client.wait_for_server(timeout_sec=SERVICE_WAIT_S):
            return False, "/deliver 액션 서버가 없다"
        request = DeliveryRequest(
            request_id=body.get("request_id", ""),
            mode=int(body.get("mode") or 0),
            destination_id=body.get("destination_id", ""),
            orders=[Order(order_id=o.get("order_id", ""),
                          patient_id=str(o.get("patient_id") or ""),
                          item_id=str(o.get("item_id") or ""))
                    for o in body.get("orders") or []],
        )
        request.header.stamp = Clock(clock_type=ClockType.ROS_TIME).now().to_msg()
        goal_future = client.send_goal_async(Deliver.Goal(request=request))
        done = threading.Event()
        goal_future.add_done_callback(lambda _f: done.set())
        if not done.wait(timeout=SERVICE_WAIT_S):
            return False, "/deliver 가 응답하지 않는다"
        handle = goal_future.result()
        if not handle.accepted:
            # goal 거부에는 사유가 실려 오지 않는다 (api.md §0.4).
            return False, "orchestrator 가 요청을 거부했다 (사유 없음)"
        return True, ""
