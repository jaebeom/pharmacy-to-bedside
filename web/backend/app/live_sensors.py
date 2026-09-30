"""카메라 프레임·라이다 스캔을 웹으로 — 순수. rclpy 를 import 하지 않는다(api.md §1.8).

**기본은 꺼짐이다.** 서버 인자 `--live-sensors` 가 있어야 이 객체가 생긴다. 없으면 구독도 0 이다.
켜도 카메라 구독은 **보는 사람이 있을 때만** 건다(`wanted_images`). 그래서 패널을 닫으면 구독이 풀린다.

부하 상한(서버가 지킨다):
- 카메라: 저장 ≤ `STREAM_FPS`, 인코딩 가로 ≤ `MAX_WIDTH` px, JPEG 품질 `JPEG_QUALITY`,
  한 카메라에 동시 시청 ≤ `MAX_VIEWERS`. 인코딩은 새 프레임일 때 한 번만 하고 시청자가 나눠 쓴다.
- 스캔: 저장 ≤ 1 / `SCAN_PERIOD_S` Hz, 점 ≤ `SCAN_MAX_POINTS`.

프레임은 ROS 스레드가 쓰고 asyncio 루프가 읽는다 — 그래서 이 객체만은 잠금으로 지킨다.
스캔은 다른 입력처럼 루프에서만 쓴다(`WorldState.live.note_scan`).
"""

from __future__ import annotations

import math
import threading
from dataclasses import dataclass
from datetime import datetime
from typing import Any

STREAM_FPS = 5.0
MAX_WIDTH = 640
JPEG_QUALITY = 50
MAX_VIEWERS = 3
SCAN_PERIOD_S = 0.5          # 2 Hz
SCAN_MAX_POINTS = 360
CAMERA_STALE_WALL_S = 2.0
SCAN_STALE_WALL_S = 2.0


@dataclass(frozen=True)
class CameraSpec:
    label: str
    image: str               # sensor_msgs/Image. `{robot}` 은 --robot-id
    tag: str | None          # TagRead — 글자 오버레이
    pouches: str | None      # PouchDetectionArray — 글자 오버레이(픽셀 박스는 msg 에 없다)


#: 스트림할 수 있는 카메라. `a1_pick` 같은 촬영 시점은 ROS 토픽이 아니라서 여기 없다.
CAMERAS: dict[str, CameraSpec] = {
    "amr_hand": CameraSpec("AMR 손 카메라(트레이 쪽)", "/{robot}/hand_camera/image_raw",
                           "/{robot}/hand_camera/tag_reads", "/{robot}/hand_camera/pouches"),
    "m0609_hand": CameraSpec("M0609 손 카메라(약통 QR)", "/m0609/hand_camera/image_raw",
                             None, None),   # 약통 판독은 WorldState.container_read 가 이미 받는다
    # QR 추적 영상(재범 9/29): 검출기가 찾은 QR 마다 네 꼭짓점 사각형과 판정 색(초록 읽음·OK, 빨강 다른 주문,
    # 노랑 못 읽음)을 그려 낸다(`qr_overlay`). 글자는 영상 안에 있으니 오버레이 토픽이 없다.
    "amr_qr": CameraSpec("AMR QR 추적(사각형)", "/{robot}/hand_camera/qr_view", None, None),
    "m0609_qr": CameraSpec("M0609 QR 추적(사각형)", "/m0609/hand_camera/qr_view", None, None),
}

#: sensor_msgs/Image encoding → (채널 수, Pillow 모드, Pillow raw 디코더 모드).
#: 인코딩은 Pillow 하나로 한다. requirements 에는 넣지 않는다(새 의존성 금지). 실물 PC 는 venv 가
#: --system-site-packages 라 Ubuntu 의 python3-pil 을 쓴다. 없으면 `available()` 이 False 이고 기능이 꺼진다.
ENCODINGS = {
    "rgb8": (3, "RGB", "RGB"), "bgr8": (3, "RGB", "BGR"),
    "rgba8": (4, "RGBA", "RGBA"), "bgra8": (4, "RGBA", "BGRA"),
    "mono8": (1, "L", "L"),
}


def topic_for(template: str, robot_id: str) -> str:
    return template.format(robot=robot_id)


def available() -> tuple[bool, str]:
    """JPEG 인코더(Pillow)가 있는가. (있나, 없으면 이유)."""
    try:
        import PIL.Image  # noqa: F401
    except ImportError as exc:
        return False, f"Pillow 가 없다({exc}). python3-pil 을 설치하거나 venv 를 --system-site-packages 로 만든다"
    return True, ""


def check_frame(frame: dict[str, Any]) -> tuple[int, str, str]:
    """프레임 모양 검사. (step, Pillow 모드, raw 모드). 모르는 encoding·맞지 않는 크기면 ValueError."""
    enc = frame["encoding"]
    if enc not in ENCODINGS:
        raise ValueError(f"encoding {enc!r} 는 지원하지 않는다")
    channels, mode, raw = ENCODINGS[enc]
    width, height, step = int(frame["width"]), int(frame["height"]), int(frame["step"])
    if width <= 0 or height <= 0 or step < width * channels or len(frame["data"]) < step * height:
        raise ValueError("step·크기가 맞지 않는다")
    return step, mode, raw


def frame_to_image(frame: dict[str, Any]):
    """{data, width, height, encoding, step} → Pillow 이미지(RGB 또는 L). 모르는 encoding·크기면 ValueError."""
    step, mode, raw = check_frame(frame)
    from PIL import Image
    width, height = int(frame["width"]), int(frame["height"])
    data = frame["data"]
    img = Image.frombuffer(mode, (width, height), bytes(data[: step * height]), "raw", raw, step, 1)
    return img.convert("RGB") if mode == "RGBA" else img


def encode_jpeg(frame: dict[str, Any], *, max_width: int = MAX_WIDTH, quality: int = JPEG_QUALITY) -> bytes:
    """프레임 한 장 → JPEG. 가로가 `max_width` 를 넘으면 비율대로 줄인다."""
    import io

    from PIL import Image
    img = frame_to_image(frame)
    width, height = img.size
    if width > max_width:
        img = img.resize((max_width, max(1, round(height * max_width / width))), Image.BILINEAR)
    out = io.BytesIO()
    img.save(out, "JPEG", quality=int(quality))
    return out.getvalue()


def scan_points(ranges, angle_min: float, angle_increment: float, range_min: float, range_max: float,
                *, pose: tuple[float, float, float] | None = None,
                max_points: int = SCAN_MAX_POINTS) -> list[list[float]]:
    """LaserScan → [[x, y], …]. 범위 밖·NaN·inf 는 뺀다. 점이 많으면 고르게 솎는다.

    `pose` 가 있으면 그것(스캔 프레임의 map 자세 x, y, yaw)으로 map 좌표로 옮긴다. 없으면 스캔 프레임 좌표다.
    """
    valid = [(i, float(r)) for i, r in enumerate(ranges)
             if math.isfinite(r) and range_min <= r <= range_max]
    if not valid:
        return []
    stride = max(1, math.ceil(len(valid) / max_points))
    px, py, pyaw = pose if pose is not None else (0.0, 0.0, 0.0)
    out = []
    for i, r in valid[::stride][:max_points]:
        a = pyaw + angle_min + i * angle_increment
        out.append([round(px + r * math.cos(a), 2), round(py + r * math.sin(a), 2)])
    return out


class LiveSensors:
    """카메라 프레임·오버레이·시청자 수·스캔. 켜졌을 때만 만든다."""

    def __init__(self, robot_id: str = "amr_1", *, encoder=None) -> None:
        self.robot_id = robot_id
        self._encode = encoder or encode_jpeg
        self._lock = threading.Lock()
        self._frames: dict[str, dict[str, Any]] = {}
        self._frame_seq: dict[str, int] = {}
        self._jpeg: dict[str, tuple[int, bytes]] = {}
        self._viewers: dict[str, int] = dict.fromkeys(CAMERAS, 0)
        self._overlay: dict[str, dict[str, Any]] = {name: {"tag": None, "pouches": []} for name in CAMERAS}
        self._last_store: dict[str, float] = {}
        self.scan: dict[str, Any] | None = None

    # ── 시청자 ──────────────────────────────────────────────────────────

    def acquire(self, name: str) -> bool:
        with self._lock:
            if self._viewers[name] >= MAX_VIEWERS:
                return False
            self._viewers[name] += 1
            return True

    def release(self, name: str) -> None:
        with self._lock:
            self._viewers[name] = max(0, self._viewers[name] - 1)
            if self._viewers[name] == 0:
                # 아무도 안 보면 프레임을 들고 있지 않는다 — 다시 열면 새 프레임부터 보인다.
                self._frames.pop(name, None)
                self._jpeg.pop(name, None)

    def wanted_images(self) -> set[str]:
        """구독해야 하는 카메라. 브리지가 주기적으로 보고 구독을 걸고 푼다."""
        with self._lock:
            return {name for name, n in self._viewers.items() if n > 0}

    # ── 입력(ROS 스레드) ────────────────────────────────────────────────

    def due(self, name: str, mono: float) -> bool:
        """이 시각의 프레임을 담을 차례인가. 보는 사람이 없거나 `STREAM_FPS` 보다 이르면 False.

        브리지는 이걸 먼저 보고 나서 메시지를 복사한다 — 버릴 프레임은 복사하지 않는다.
        """
        with self._lock:
            return (self._viewers.get(name, 0) > 0
                    and mono - self._last_store.get(name, -math.inf) >= 1.0 / STREAM_FPS)

    def note_frame(self, name: str, frame: dict[str, Any], wall: datetime, mono: float) -> bool:
        """프레임 한 장. `STREAM_FPS` 보다 자주 오면 버린다. 담았으면 True."""
        with self._lock:
            if self._viewers.get(name, 0) == 0:
                return False
            if mono - self._last_store.get(name, -math.inf) < 1.0 / STREAM_FPS:
                return False
            self._last_store[name] = mono
            self._frames[name] = {**frame, "wall": wall}
            self._frame_seq[name] = self._frame_seq.get(name, 0) + 1
            return True

    def note_tag(self, name: str, read: dict[str, Any]) -> None:
        with self._lock:
            self._overlay[name]["tag"] = {
                "tag_id": read.get("tag_id") or "",
                "status": "ok" if int(read.get("status", -1)) == 0 else "unreadable",
                "stamp": float(read.get("stamp", 0.0)),
            }

    def note_pouches(self, name: str, detections: list[dict[str, Any]]) -> None:
        with self._lock:
            self._overlay[name]["pouches"] = [
                {"order_id": d.get("order_id") or "", "confidence": round(float(d.get("confidence", 0.0)), 3),
                 "slot_index": int(d.get("slot_index", -1))} for d in detections]

    # ── 출력 ────────────────────────────────────────────────────────────

    def frame_seq(self, name: str) -> int:
        with self._lock:
            return self._frame_seq.get(name, 0) if name in self._frames else 0

    def jpeg(self, name: str) -> tuple[int, bytes] | None:
        """마지막 프레임의 JPEG. 새 프레임일 때만 인코딩한다. 프레임이 없으면 None."""
        with self._lock:
            frame = self._frames.get(name)
            seq = self._frame_seq.get(name, 0)
            cached = self._jpeg.get(name)
        if frame is None:
            return None
        if cached is not None and cached[0] == seq:
            return cached
        entry = (seq, self._encode(frame))  # 잠금 밖에서 — 인코딩 중에도 ROS 스레드가 막히지 않게
        with self._lock:
            self._jpeg[name] = entry
        return entry

    def cameras(self, now: datetime, *, container_read: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        out = []
        with self._lock:
            for name, spec in CAMERAS.items():
                frame = self._frames.get(name)
                age = None if frame is None else max(0.0, (now - frame["wall"]).total_seconds())
                overlay = {"tag": self._overlay[name]["tag"], "pouches": list(self._overlay[name]["pouches"])}
                if name == "m0609_hand" and container_read is not None:
                    overlay["tag"] = {k: container_read[k] for k in ("tag_id", "status", "stamp")}
                out.append({
                    "name": name, "label": spec.label, "topic": topic_for(spec.image, self.robot_id),
                    "width": None if frame is None else frame["width"],
                    "height": None if frame is None else frame["height"],
                    "stamp": None if frame is None else frame["stamp"],
                    "age_wall_s": age,
                    "stale": age is None or age > CAMERA_STALE_WALL_S,
                    "viewers": self._viewers[name],
                    "overlay": overlay,
                })
        return out

    def note_scan(self, scan: dict[str, Any], wall: datetime) -> None:
        """루프에서만 불린다. `scan` = {robot_id, frame, stamp, points, range_max}."""
        self.scan = {**scan, "wall": wall}

    def scan_view(self, now: datetime) -> dict[str, Any] | None:
        from app.state import iso   # 순환 import 를 피한다
        scan = self.scan
        if scan is None:
            return None
        age = max(0.0, (now - scan["wall"]).total_seconds())
        return {"robot_id": scan["robot_id"], "frame": scan["frame"], "stamp": scan["stamp"],
                "wall": iso(scan["wall"]), "age_wall_s": age, "stale": age > SCAN_STALE_WALL_S,
                "points": scan["points"], "range_max": scan["range_max"]}


def limits() -> dict[str, Any]:
    return {"fps": STREAM_FPS, "max_width": MAX_WIDTH, "jpeg_quality": JPEG_QUALITY,
            "max_viewers": MAX_VIEWERS, "scan_hz": 1.0 / SCAN_PERIOD_S, "scan_max_points": SCAN_MAX_POINTS}
