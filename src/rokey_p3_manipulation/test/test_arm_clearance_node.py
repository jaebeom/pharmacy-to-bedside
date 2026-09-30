"""arm 노드의 `ArmClearance` 발행(opt-in, 계약 11.6). ROS 없이 ArmNode 메서드를 빌린 Harness 로 돈다.

`test_reset_fence` 의 대역 모듈을 빌린다(없는 것만 넣고 끝나면 뺀다). TF·시계·발행기만 대역이다.
여기의 통로 상자·반지름은 **시험용 기하**다. 실제 값이 아니다(미측정).
"""

import importlib.util
import threading
import types

import numpy as np
import test_reset_fence as rf

from rokey_p3_manipulation import belt_lane_clearance as lane
from rokey_p3_manipulation import ur5_kinematics as kin
from rokey_p3_manipulation.reset_fence import ResetFence

nodes = rf.nodes

BORROWED = ('clearance_judgement', '_publish_clearance', '_lane_pose_quiet', '_on_gripper_state', '_on_joint_states',
            '_setup_clearance', '_clearance_config_from_parameters', '_subscribe_gripper_state')
POSE = (0.3, -1.2, 1.4, -1.6, -1.57, 0.2)
NAMES = ['shoulder_pan_joint', 'shoulder_lift_joint', 'elbow_joint', 'wrist_1_joint', 'wrist_2_joint', 'wrist_3_joint']
FAR = (100.0, 100.0, 100.0), (101.0, 101.0, 101.0)


def stamp(seconds):
    """joint_states header.stamp. rclpy 가 있으면 진짜 builtin_interfaces Time 이다."""
    sec, nanosec = int(seconds), int(round((seconds - int(seconds)) * 1e9))
    if importlib.util.find_spec('builtin_interfaces') is not None:
        from builtin_interfaces.msg import Time
        return Time(sec=sec, nanosec=nanosec)
    return types.SimpleNamespace(sec=sec, nanosec=nanosec)


class _Time:
    def __init__(self, nanoseconds):
        self.nanoseconds = nanoseconds

    @classmethod
    def from_msg(cls, value):
        return cls(int(value.sec) * 1_000_000_000 + int(value.nanosec))


class _Tf:
    """lane 프레임 하나만 아는 TF. 없으면 LookupError(시험에서 TransformException 자리)."""

    def __init__(self):
        self.frames = {}

    def lookup_transform(self, parent, child, when, timeout=None):
        if (parent, child) not in self.frames:
            raise LookupError(f'{parent} <- {child}')
        (x, y, z), (qx, qy, qz, qw) = self.frames[(parent, child)]
        return types.SimpleNamespace(transform=types.SimpleNamespace(
            translation=types.SimpleNamespace(x=x, y=y, z=z),
            rotation=types.SimpleNamespace(x=qx, y=qy, z=qz, w=qw)))

    def clear(self):
        pass


def geometry(lower, upper):
    return lane.LaneConfig(base_from_lane=None, lower=lower, upper=upper, link_radii=(0.05,) * 6,
                           tool_length=0.10, tool_radius=0.05, payload_size=(0.10, 0.07, 0.01),
                           payload_center=(0.0, 0.0, 0.005))


def harness(nodes, monkeypatch, config=None, lane_frame='lane'):
    arm, _ = nodes
    monkeypatch.setattr(arm, 'RclTime', _Time)
    monkeypatch.setattr(arm, 'TransformException', LookupError)
    node = type('ClearanceHarness', (), {n: getattr(arm.ArmNode, n) for n in BORROWED})()
    node._lock = threading.Lock()
    node._closing = threading.Event()
    node._epoch = 0
    node._fence = ResetFence()
    node._joint_names = list(NAMES)
    node._joints = arm.Freshness(arm.STALE_JOINTS_S)
    node._joints_stamp = None
    node._holding = arm.Freshness(arm.STALE_STATUS_S)
    node._gripper_view = arm.clear_state.GripperView(arm.STALE_STATUS_S, arm.GripperState.STATE_HELD,
                                                     arm.GripperState.STATE_RELEASED)
    node._clearance_seq = arm.clear_state.StampSeq()
    node._clearance_pub = rf._Pub()
    node._gripper_state_subscribed = False
    node._clearance_region = 'belt_corridor'
    node._clearance_lane_frame = lane_frame
    node._clearance_config = config if config is not None else geometry(*FAR)
    node._arm_base_frame = 'amr_1/base_link'
    node._limits = kin.UR5_JOINT_LIMITS
    node._tf_buffer = _Tf()
    node._tf_buffer.frames[('amr_1/base_link', 'lane')] = ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0, 1.0))
    node.get_logger = lambda: rf._Logger()
    return node, arm


def joints(node, seconds, values=POSE):
    node._on_joint_states(types.SimpleNamespace(name=list(NAMES), position=list(values),
                                                header=types.SimpleNamespace(stamp=stamp(seconds))))


def gripper(node, arm, state, seq=1, epoch=1):
    node._on_gripper_state(types.SimpleNamespace(epoch=epoch, seq=seq, state=state, last_applied_command_seq=0))


def published(node):
    return node._clearance_pub.sent


def last(node):
    return published(node)[-1]


def ready(node, arm, state=None):
    node._epoch = 1
    joints(node, 10.0)
    gripper(node, arm, arm.GripperState.STATE_RELEASED if state is None else state)


# epoch -----------------------------------------------------------------------

def test_nothing_is_published_before_any_event(nodes, monkeypatch):
    node, arm = harness(nodes, monkeypatch)
    joints(node, 10.0)
    node._publish_clearance()
    assert published(node) == []


def test_before_any_reset_the_epoch_is_one(nodes, monkeypatch):
    node, arm = harness(nodes, monkeypatch)
    ready(node, arm)
    node._publish_clearance()
    assert last(node).epoch == 1


def test_barrier_is_unknown_with_the_last_reset_done_epoch(nodes, monkeypatch):
    node, arm = harness(nodes, monkeypatch)
    ready(node, arm)
    node._fence.begin(2)
    node._fence.done(2)
    node._fence.begin(3)
    node._epoch = 3                                               # RESET_BEGIN(3) 을 받았다
    node._publish_clearance()
    message = last(node)
    assert message.epoch == 2
    assert message.clearance == arm.ArmClearance.CLEARANCE_UNKNOWN
    assert 'barrier' in message.detail and np.isnan(message.margin_m)


# 판정 --------------------------------------------------------------------------

def test_clear_with_a_fresh_released_gripper(nodes, monkeypatch):
    node, arm = harness(nodes, monkeypatch)
    ready(node, arm)
    node._publish_clearance()
    message = last(node)
    assert message.clearance == arm.ArmClearance.CLEARANCE_CLEAR
    assert message.region == 'belt_corridor' and message.detail == ''
    assert message.margin_m > 1.0
    assert message.header.stamp == stamp(10.0)                   # 판정에 쓴 joint_states 의 stamp


def test_seq_counts_joint_state_stamps_not_publications(nodes, monkeypatch):
    node, arm = harness(nodes, monkeypatch)
    ready(node, arm)
    node._publish_clearance()
    node._publish_clearance()
    assert [m.seq for m in published(node)] == [1, 1]
    joints(node, 10.1)
    gripper(node, arm, arm.GripperState.STATE_RELEASED, seq=2)
    node._publish_clearance()
    assert last(node).seq == 2


def test_without_gripper_state_it_is_unknown_even_if_the_bool_says_empty(nodes, monkeypatch):
    # 물리 경로의 흡착 입력은 GripperState 뿐이다. 기존 Bool holding 은 보지 않는다.
    node, arm = harness(nodes, monkeypatch)
    node._epoch = 1
    joints(node, 10.0)
    with node._lock:
        node._holding.update(False)
    node._publish_clearance()
    message = last(node)
    assert message.clearance == arm.ArmClearance.CLEARANCE_UNKNOWN
    assert 'GripperState' in message.detail
    assert message.margin_m > 1.0                                 # 링크·공구 여유는 남긴다


def test_links_inside_the_lane_are_intruding_without_gripper_state(nodes, monkeypatch):
    center = kin.link_frames(POSE)[-1][:3, 3]
    node, arm = harness(nodes, monkeypatch, config=geometry(tuple(center - 0.01), tuple(center + 0.01)))
    node._epoch = 1
    joints(node, 10.0)
    node._publish_clearance()
    message = last(node)
    assert message.clearance == arm.ArmClearance.CLEARANCE_INTRUDING and message.margin_m <= 0.0


def test_gripper_state_of_another_epoch_is_ignored(nodes, monkeypatch):
    node, arm = harness(nodes, monkeypatch)
    node._epoch = 1
    joints(node, 10.0)
    gripper(node, arm, arm.GripperState.STATE_RELEASED, epoch=7)
    node._publish_clearance()
    assert last(node).clearance == arm.ArmClearance.CLEARANCE_UNKNOWN


def test_missing_geometry_and_tf_are_unknown_with_a_reason(nodes, monkeypatch):
    cases = {
        'lane frame unset': {'lane_frame': ''},
        'tf missing': {'lane_frame': 'other'},
        'radii unset': {'config': geometry(*FAR)._replace(link_radii=None)},
        'lane box unset': {'config': geometry(None, None)},
    }
    for name, kwargs in cases.items():
        node, arm = harness(nodes, monkeypatch, **kwargs)
        ready(node, arm)
        node._publish_clearance()
        message = last(node)
        assert message.clearance == arm.ArmClearance.CLEARANCE_UNKNOWN, name
        assert message.detail and np.isnan(message.margin_m), name


def test_no_joint_states_is_unknown(nodes, monkeypatch):
    node, arm = harness(nodes, monkeypatch)
    node._epoch = 1
    node._publish_clearance()
    assert last(node).clearance == arm.ArmClearance.CLEARANCE_UNKNOWN


def test_disabled_or_closing_publishes_nothing(nodes, monkeypatch):
    node, arm = harness(nodes, monkeypatch)
    ready(node, arm)
    node._clearance_pub = None                                    # arm_clearance_enabled=false 면 발행기가 없다
    node._publish_clearance()
    node, arm = harness(nodes, monkeypatch)
    ready(node, arm)
    node._closing.set()
    node._publish_clearance()
    assert published(node) == []


# 기본 구성(끔)과 기본값 --------------------------------------------------------------

def recording(node, values):
    """create_* 호출을 기록하고, get_parameter 는 values 사전에서 읽는다."""
    node.created = []
    node.create_publisher = lambda kind, topic, qos: node.created.append(('publisher', topic)) or rf._Pub()
    node.create_subscription = lambda kind, topic, cb, qos, callback_group=None: node.created.append(
        ('subscription', topic))
    node.create_timer = lambda period, cb, callback_group=None: node.created.append(('timer', period))
    node.get_parameter = lambda name: types.SimpleNamespace(value=values[name])
    node._callbacks = None
    return node


def test_default_is_off_and_creates_no_topic_subscription_or_timer(nodes, monkeypatch):
    # 머지 확인 ①: 기본 구성(끔)에서는 새 토픽·구독·타이머를 하나도 만들지 않는다.
    node, arm = harness(nodes, monkeypatch)
    defaults = dict(arm.CLEARANCE_PARAMETERS)
    assert defaults['arm_clearance_enabled'] is False
    recording(node, defaults)
    node._clearance_pub = None
    node._clearance_enabled = defaults['arm_clearance_enabled']
    node._setup_clearance('/amr_1')
    assert node.created == [] and node._clearance_pub is None


def test_enabled_creates_one_publisher_subscription_and_timer(nodes, monkeypatch):
    node, arm = harness(nodes, monkeypatch)
    recording(node, dict(arm.CLEARANCE_PARAMETERS))
    node._clearance_pub = None
    node._clearance_enabled = True
    node._setup_clearance('/amr_1')
    assert node.created == [('publisher', '/amr_1/arm/clear_of_belt'), ('subscription', '/amr_1/gripper/state'),
                            ('timer', 0.1)]
    assert node._clearance_pub is not None


def test_parameter_defaults_are_all_unset_geometry(nodes, monkeypatch):
    # 머지 확인 ③: 통로 상자·링크 반지름·공구·파지물에 추측한 기본값이 없다.
    # 기본값에서 만든 설정은 전부 미설정(None)이다.
    node, arm = harness(nodes, monkeypatch)
    recording(node, dict(arm.CLEARANCE_PARAMETERS))
    config = node._clearance_config_from_parameters()
    assert all(value is None for value in config), config
    node._clearance_config = config
    ready(node, arm)
    node._publish_clearance()
    assert last(node).clearance == arm.ArmClearance.CLEARANCE_UNKNOWN and last(node).detail
