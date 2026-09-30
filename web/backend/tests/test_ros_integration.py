"""실제 rclpy 로 한 바퀴. **기본 실행에서 빠진다** (`pytest.ini` 의 `-m "not ros"`).

    python -m pytest tests/ -q -m ros

rclpy 와 빌드된 워크스페이스가 있어야 돈다. skip 이 아니라 마커로 분리한 이유:
skip 이면 없는 환경에서 조용히 넘어가 "안 돌았는데 초록" 이 된다. 마커면 안 부른 것이
분명하고, 부르면 없을 때 **실패**한다.

가짜 발행 노드 → 게이트웨이 브리지 → snapshot. 배선이 실제 DDS 를 타고 도는지 본다.
"""

from __future__ import annotations

import asyncio
import os

import pytest

# 돌고 있는 스택(118)과 섞이지 않게 다른 도메인을 쓴다. 컨텍스트를 만들기 전에 정해야 한다.
os.environ.setdefault("ROS_DOMAIN_ID", "119")

pytestmark = pytest.mark.ros

# rclpy 를 모듈 수준에서 import 하지 않는다. importorskip 을 쓰면 rclpy 가 없는 환경에서 이 모듈이
# 수집 단계에 통째로 skip 되고, 그러면 위 docstring 이 약속한 것과 반대가 된다 — 마커로 뺀 것이 아니라
# 조용히 넘어간 것이 되고, 같은 시험이 환경에 따라 deselected 와 skipped 사이를 오간다.
# (9/20 CI 첫 실행에서 실제로 그랬다. 로컬은 deselected 1, 러너는 skipped 1.)
# 아래 import 는 전부 함수 안에 있다. rclpy 없이도 수집되고 -m 으로만 빠지며, `-m ros` 로 부르면 실패한다.


def _imports():
    import rclpy

    from rclpy.node import Node
    from rosgraph_msgs.msg import Clock as ClockMsg
    from std_msgs.msg import Bool

    from rokey_p3_interfaces.msg import Event
    from rokey_p3_orchestrator.ros_qos import heartbeat_qos, latched_qos, sensor_qos
    return rclpy, Node, ClockMsg, Bool, Event, heartbeat_qos, latched_qos, sensor_qos


async def _run_once():
    from app.ros_bridge import RosBridge
    from app.state import WorldState

    rclpy, Node, ClockMsg, Bool, Event, heartbeat_qos, latched_qos, sensor_qos = _imports()

    state = WorldState()
    bridge = RosBridge(state, robot_id="amr_1")
    bridge.start()
    try:
        context = rclpy.Context()
        context.init()
        talker = Node("fake_talker", context=context)
        events = talker.create_publisher(Event, "/events", latched_qos(500))
        arm = talker.create_publisher(Bool, "/amr_1/arm/at_home", heartbeat_qos())
        clock = talker.create_publisher(ClockMsg, "/clock", sensor_qos(1))

        event = Event()
        event.header.stamp.sec = 2
        event.name = "REQUEST_ACCEPTED"
        event.request_id = "req-int-1"
        event.epoch = 1
        event.detail = '{"mode":1,"destination_id":"bed_a1","orders":[]}'

        clock_msg = ClockMsg()
        clock_msg.clock.sec = 42

        # 구독자가 붙을 틈을 주고 여러 번 보낸다 (heartbeat 는 latched 가 아니다)
        for _ in range(30):
            events.publish(event)
            arm.publish(Bool(data=True))
            clock.publish(clock_msg)
            await asyncio.sleep(0.1)
            if state.seq > 0 and "arm_at_home" in state.signals:
                break

        talker.destroy_node()
        context.try_shutdown()
        await asyncio.sleep(0.3)
        return state
    finally:
        bridge.stop()


def test_a_real_publisher_reaches_the_snapshot():
    from datetime import datetime, timezone

    state = asyncio.run(_run_once())
    snap = state.snapshot(datetime.now(timezone.utc))

    assert snap["epoch"] == 1, "이벤트가 DDS 를 타고 오지 않았다"
    assert snap["trip"] is not None
    assert snap["trip"]["request_id"] == "req-int-1"
    # #104 형식 detail 이 실물 경로에서도 파싱된다
    assert snap["trip"]["mode"] == 1
    assert snap["trip"]["mode_source"] == "event_detail"
    assert snap["trip"]["destination_id"] == "bed_a1"
    # 하트비트 신호도 왔다
    assert snap["signals"]["arm_at_home"]["value"] is True
    assert snap["clock"]["sim_s"] == 42.0
