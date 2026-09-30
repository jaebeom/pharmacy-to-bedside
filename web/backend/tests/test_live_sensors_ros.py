"""카메라·스캔 실시간(api.md §1.8)을 실제 rclpy 와 Pillow 로. **기본 실행에서 빠진다** (`-m "not ros"`).

    python -m pytest tests/test_live_sensors_ros.py -q -m ros

ROS 환경(시스템 site-packages)이 있어야 돈다. rclpy·sensor_msgs 와 JPEG 인코더(Ubuntu python3-pil)가 거기 있다.
CI 의 web job 에는 둘 다 없다. requirements 에 넣지 않는다(새 의존성 금지). 그래서 마커로 뺀다 — skip 이 아니다.

가짜 발행 노드 → 브리지 노드 → LiveSensors. 보는 사람이 있을 때만 구독이 걸리고, 5 fps 로만 담기고,
JPEG 이 실제로 디코드되는지, 스캔이 2 Hz 로 솎이는지 본다.
"""

from __future__ import annotations

import io
import math
import os
import threading
import time

import pytest

# 돌고 있는 스택과 섞이지 않게 다른 도메인을 쓴다. 컨텍스트를 만들기 전에 정해야 한다.
os.environ.setdefault("ROS_DOMAIN_ID", "119")

pytestmark = pytest.mark.ros

# rclpy·Pillow 는 함수 안에서만 import 한다 — 없는 환경에서도 수집되고 -m 으로만 빠지게.
# test_ros_integration.py 와 같은 방식이다.


def _wait(cond, timeout=5.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.05)
    return cond()


def test_jpeg_encoding_keeps_colour_order_padding_and_width_limit():
    from PIL import Image

    from app import live_sensors as L
    for encoding, pixel in (("bgr8", b"\xff\x00\x00"), ("rgb8", b"\x00\x00\xff")):
        img = L.frame_to_image({"data": pixel * 64, "width": 8, "height": 8, "encoding": encoding, "step": 24})
        assert img.getpixel((0, 0)) == (0, 0, 255), encoding       # 둘 다 파랑
    row = bytes(range(8)) + b"\xee\xee"                             # 줄 끝 채움 2 바이트
    img = L.frame_to_image({"data": row * 4, "width": 8, "height": 4, "encoding": "mono8", "step": 10})
    assert [img.getpixel((x, 3)) for x in range(8)] == list(range(8))
    big = {"data": b"\x64" * (1280 * 800 * 4), "width": 1280, "height": 800, "encoding": "rgba8", "step": 5120}
    assert Image.open(io.BytesIO(L.encode_jpeg(big))).size == (L.MAX_WIDTH, 400)


def test_the_bridge_subscribes_only_while_watched_and_throttles():
    import rclpy
    from rclpy.executors import MultiThreadedExecutor
    from rclpy.node import Node
    from sensor_msgs.msg import Image as ImageMsg
    from sensor_msgs.msg import LaserScan
    from PIL import Image

    from app import live_sensors as L
    from app.ros_bridge import BridgeNode

    context = rclpy.Context()
    context.init()
    submitted = []
    live = L.LiveSensors()
    bridge = BridgeNode(lambda kind, payload: submitted.append((kind, payload)), live=live, context=context)
    talker = Node("fake_camera", context=context)
    images = talker.create_publisher(ImageMsg, "/amr_1/hand_camera/image_raw", 10)
    scans = talker.create_publisher(LaserScan, "/amr_1/scan", 10)
    executor = MultiThreadedExecutor(context=context)
    executor.add_node(bridge)
    executor.add_node(talker)
    threading.Thread(target=executor.spin, daemon=True).start()

    def publish(seconds, hz=20.0):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            img = ImageMsg(width=320, height=200, encoding="rgb8", step=960)
            img.data = bytes(320 * 200 * 3)
            images.publish(img)
            scan = LaserScan(angle_min=-math.pi, angle_increment=2 * math.pi / 720,
                             range_min=0.1, range_max=20.0, ranges=[3.0] * 720)
            scan.header.frame_id = "amr_1/lidar_link"
            scans.publish(scan)
            time.sleep(1.0 / hz)

    try:
        publish(1.0)
        assert bridge._image_subs == {}                        # 아무도 안 본다 — 구독도 없다
        assert live.frame_seq("amr_hand") == 0

        assert live.acquire("amr_hand")
        assert _wait(lambda: "amr_hand" in bridge._image_subs)
        time.sleep(0.5)                                         # 발견 시간
        before = live.frame_seq("amr_hand")
        publish(2.0)
        stored = live.frame_seq("amr_hand") - before
        assert 5 <= stored <= 11, stored                        # 20 Hz 로 2 s → 5 fps 상한이면 약 10
        seq, jpeg = live.jpeg("amr_hand")
        assert Image.open(io.BytesIO(jpeg)).size == (320, 200)

        live.release("amr_hand")
        assert _wait(lambda: bridge._image_subs == {})          # 다 나가면 구독을 푼다

        got = [p for k, p in submitted if k == "scan"]
        assert got and len(got) <= 4 * 2 + 1                    # 약 4 s 동안 2 Hz
        assert got[-1]["frame"] == "amr_1/lidar_link"           # TF 가 없으면 스캔 프레임 그대로
        assert 0 < len(got[-1]["points"]) <= L.SCAN_MAX_POINTS
    finally:
        executor.shutdown()
        bridge.destroy_node()
        talker.destroy_node()
        context.try_shutdown()
