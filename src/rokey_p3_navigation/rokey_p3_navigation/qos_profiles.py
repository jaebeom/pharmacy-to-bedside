"""계약 v1 2절의 QoS 약어 네 개. 노드마다 다시 쓰지 않는다.

- `SENSOR` (S): best effort, volatile, depth 5
- `RELIABLE` (R): reliable, volatile, depth 10
- `HEARTBEAT` (H): reliable, volatile, depth 1. 5 Hz 로 낸다. 받는 쪽은 1.0 s 없으면 unknown
- `latched(depth)` (L): reliable, transient local
"""

from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy

SENSOR = QoSProfile(
    reliability=ReliabilityPolicy.BEST_EFFORT,
    durability=DurabilityPolicy.VOLATILE,
    history=HistoryPolicy.KEEP_LAST,
    depth=5,
)

RELIABLE = QoSProfile(
    reliability=ReliabilityPolicy.RELIABLE,
    durability=DurabilityPolicy.VOLATILE,
    history=HistoryPolicy.KEEP_LAST,
    depth=10,
)

HEARTBEAT = QoSProfile(
    reliability=ReliabilityPolicy.RELIABLE,
    durability=DurabilityPolicy.VOLATILE,
    history=HistoryPolicy.KEEP_LAST,
    depth=1,
)


def latched(depth):
    """L: 늦게 붙은 구독자도 마지막 값을 받는다."""
    return QoSProfile(
        reliability=ReliabilityPolicy.RELIABLE,
        durability=DurabilityPolicy.TRANSIENT_LOCAL,
        history=HistoryPolicy.KEEP_LAST,
        depth=depth,
    )
