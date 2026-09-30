"""계약 2절의 QoS 약어를 하나씩 함수로. 노드만 쓴다(rclpy 를 import 한다).

S = sensor data(best effort, volatile, depth 5)
R = reliable, volatile, depth 10
H = 상태 heartbeat(reliable, volatile, depth 1)
L = latched(reliable, transient local)
"""

from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy


def _profile(reliability, durability, depth):
    return QoSProfile(history=HistoryPolicy.KEEP_LAST, depth=depth,
                      reliability=reliability, durability=durability)


def sensor_qos(depth=5):
    """S. 센서 스트림."""
    return _profile(ReliabilityPolicy.BEST_EFFORT, DurabilityPolicy.VOLATILE, depth)


def reliable_qos(depth=10):
    """R. 일반 명령·결과."""
    return _profile(ReliabilityPolicy.RELIABLE, DurabilityPolicy.VOLATILE, depth)


def heartbeat_qos():
    """H. 상태 토픽. 최신값 하나만 본다. 신선도는 수신 노드가 wall clock 으로 잰다."""
    return _profile(ReliabilityPolicy.RELIABLE, DurabilityPolicy.VOLATILE, 1)


def latched_qos(depth=10):
    """L. 늦게 붙은 구독자도 지난 값을 받는다."""
    return _profile(ReliabilityPolicy.RELIABLE, DurabilityPolicy.TRANSIENT_LOCAL, depth)
