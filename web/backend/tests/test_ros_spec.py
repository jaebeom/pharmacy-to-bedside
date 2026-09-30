"""구독 배선 — **rclpy 없이** 본다.

토픽 이름 오타나 QoS 선택 실수는 실물에서만 드러나는 종류다(그 토픽만 조용히 안 온다).
표로 빼 두었으니 여기서 잡는다.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.ros_spec import SUBSCRIPTIONS, Sub, apply_update, subscriptions
from app.state import WorldState

NOW = datetime(2026, 9, 17, 8, 0, 0, tzinfo=timezone.utc)

# status_monitor_node.py 가 쓰는 것과 같아야 한다. 다르면 한쪽만 메시지를 못 받는다.
EXPECTED_QOS = {
    "/clock": ("sensor_qos", 1),
    "/events": ("latched_qos", 500),
    "/orders/status": ("latched_qos", 50),
    "/pharmacy/dispenser/status": ("latched_qos", 1),
    "/pharmacy/belt": ("heartbeat_qos", None),
    "/amr_1/arm/at_home": ("heartbeat_qos", None),
    "/amr_1/base/stopped": ("heartbeat_qos", None),
    "/amr_1/gripper/holding": ("heartbeat_qos", None),
    "/m0609/arm/at_home": ("heartbeat_qos", None),
}


def test_every_topic_uses_the_same_qos_as_status_monitor():
    got = {s.topic: (s.qos, s.depth) for s in subscriptions("amr_1")}
    for topic, expected in EXPECTED_QOS.items():
        assert got.get(topic) == expected, f"{topic} 의 QoS 가 status_monitor 와 다르다"


def test_rosout_is_latched_so_earlier_lines_arrive():
    rosout = next(s for s in subscriptions("amr_1") if s.topic == "/rosout")
    assert rosout.qos == "latched_qos", "/rosout 은 transient_local 로 발행된다"
    assert rosout.depth and rosout.depth >= 100


def test_the_robot_id_fills_in_the_signal_topics():
    topics = {s.topic for s in subscriptions("amr_3")}
    assert "/amr_3/arm/at_home" in topics
    assert "/amr_1/arm/at_home" not in topics
    # m0609 은 AMR 이 아니라 고정이다
    assert "/m0609/arm/at_home" in topics


def test_the_evaluator_topic_is_left_out_by_default():
    """평가 전용 경로다. 운영 노드는 구독하지 않는다 (계약 2.1절)."""
    assert "/evaluator/cabinet" not in {s.topic for s in subscriptions("amr_1")}
    assert "/evaluator/cabinet" in {s.topic
                                    for s in subscriptions("amr_1", show_evaluator=True)}


def test_the_five_signal_keys_are_exactly_the_documented_ones():
    from app.alarms import SIGNAL_KEYS

    keys = {s.signal_key for s in subscriptions("amr_1") if s.signal_key}
    # belt 는 Bool 이 아니라 BeltState 로 온다 — note_belt 가 신호까지 채운다
    assert keys == set(SIGNAL_KEYS) - {"belt"}


def test_no_topic_is_subscribed_twice():
    topics = [s.topic for s in subscriptions("amr_1", show_evaluator=True)]
    assert len(topics) == len(set(topics))


@pytest.mark.parametrize("sub", SUBSCRIPTIONS, ids=lambda s: s.topic)
def test_every_row_is_well_formed(sub: Sub):
    assert sub.topic.startswith("/")
    assert sub.qos in {"sensor_qos", "heartbeat_qos", "latched_qos", "reliable_qos"}
    assert sub.kind in {"clock", "event", "order", "dispenser", "belt", "signal",
                        "cabinet", "log", "shelf", "tag_read", "speed_limit", "fleet_poses", "p3_alert",
                        "sim_running", "qr_read"}


# ── 받은 것이 상태에 들어가는가 ─────────────────────────────────────────

def test_a_converted_event_reaches_the_snapshot():
    state = WorldState()
    apply_update(state, "clock", 12.5, NOW)
    apply_update(state, "event", {"name": "REQUEST_ACCEPTED", "epoch": 1, "stamp": 2.0,
                                  "request_id": "req-1", "order_id": "", "robot_id": "",
                                  "detail": ""}, NOW)
    snap = state.snapshot(NOW)
    assert snap["epoch"] == 1
    assert snap["trip"]["request_id"] == "req-1"
    assert snap["clock"]["sim_s"] == 12.5


def test_a_signal_payload_carries_its_key():
    state = WorldState()
    apply_update(state, "signal", {"key": "arm_at_home", "value": True}, NOW)
    assert state.snapshot(NOW)["signals"]["arm_at_home"]["value"] is True


def test_a_belt_message_feeds_both_belt_and_the_signal():
    state = WorldState()
    apply_update(state, "belt", {"occupied": True, "at_end": False,
                                 "order_id": "ord-1", "stamp": 7.0}, NOW)
    snap = state.snapshot(NOW)
    assert snap["belt"]["occupied"] is True
    assert snap["signals"]["belt"]["value"] is True


def test_a_warn_log_reaches_the_log_endpoint():
    state = WorldState()
    apply_update(state, "log", {"level": "error", "level_value": 40, "node": "fleet",
                                "message": "GoToZone rejected", "stamp": 1.0}, NOW)
    assert state.logs[0]["node"] == "fleet"


def test_an_unknown_kind_is_ignored_instead_of_crashing():
    """표가 앞서 나가도 서버가 죽지 않아야 한다."""
    state = WorldState()
    apply_update(state, "아직없는것", {"x": 1}, NOW)
    assert state.snapshot(NOW)["seq"] == 0


# ── --host 경고 ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "::1"])
def test_a_local_bind_needs_no_warning(host):
    from app.main import host_warnings

    assert host_warnings(host, allow_commands=True) == []


def test_opening_the_host_warns_that_there_is_no_auth():
    from app.main import host_warnings

    lines = host_warnings("10.10.0.2", allow_commands=False)
    assert len(lines) == 1
    assert "인증이 없다" in lines[0]


def test_opening_the_host_with_commands_warns_twice():
    from app.main import host_warnings

    lines = host_warnings("10.10.0.2", allow_commands=True)
    assert len(lines) == 2
    assert "리셋·배송 요청" in lines[1]
