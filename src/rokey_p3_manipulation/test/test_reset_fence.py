"""리셋 barrier 울타리. RESET_BEGIN 부터 같은 epoch 의 RESET_DONE 까지 팔 명령 0건.

앞 절은 순수 표(ResetFence, ClockWatch)다. 뒤 절은 arm_node·m0609_arm_node 의 메서드를 빌린 Harness 에
가짜 발행기·관절 plant 를 붙여 실제 스레드(홈 복귀·goal 실행)를 돌린다. ROS 가 없는 곳에서는 이 모듈 안에서만
대역 모듈을 넣고 끝나면 뺀다. 실제 L2(bringup 스텁 리셋)는 따로 본다.
테스트 이름 test_reset_fences_home_and_finally_publishers·test_clockwatch_rebases_on_reset 는 PR #61 설계 A1·A2 다.
"""

import importlib
import importlib.util
import sys
import threading
import time
import types

import pytest

from rokey_p3_manipulation.reset_fence import ClockWatch, ResetFence

# 순수 표 ------------------------------------------------------------------


def test_fence_closes_on_begin_and_opens_on_the_same_epoch_done():
    fence = ResetFence()
    assert not fence.fenced
    assert fence.begin(2) and fence.fenced
    assert not fence.begin(2)                     # 중복 RESET_BEGIN
    assert fence.done(1) and fence.fenced         # 이전 epoch 의 늦은 RESET_DONE 은 울타리를 안 연다
    assert fence.done(2) and not fence.fenced
    assert not fence.done(2)                      # 중복 RESET_DONE
    assert not fence.begin(2)                     # 끝난 epoch 의 늦은 RESET_BEGIN


def test_fence_generation_changes_at_every_barrier_edge():
    fence = ResetFence()
    start = fence.generation
    fence.begin(2)
    assert fence.generation == start + 1
    fence.done(2)
    assert fence.generation == start + 2


def test_reset_done_without_begin_does_not_close_the_fence():
    """지금 orchestrator(RESET_BEGIN 발행 전)는 RESET_DONE 만 낸다. 기존 동작을 깨지 않는다."""
    fence = ResetFence()
    assert fence.done(2) and not fence.fenced


def test_latched_replay_in_order_ends_open_or_closed_like_the_last_barrier():
    fence = ResetFence()
    for name, epoch in [('begin', 2), ('done', 2), ('begin', 3), ('done', 3), ('begin', 4)]:
        getattr(fence, name)(epoch)
    assert fence.fenced and fence.fenced_epoch == 4


def test_clockwatch_rebases_on_reset():
    wall = {'now': 0.0}
    watch = ClockWatch(100.0, limit_s=2.0, wall=lambda: wall['now'])
    wall['now'] = 1.0
    assert not watch.stalled(101.0)
    # 리셋: sim time 이 작아졌다. 멈춤이 아니다.
    wall['now'] = 3.5
    assert not watch.stalled(0.2)
    watch.rebase(0.2)                             # RESET_DONE 에서 기준을 다시 잡는다
    wall['now'] = 5.0
    assert not watch.stalled(0.3)
    wall['now'] = 6.9
    assert not watch.stalled(0.3)
    wall['now'] = 7.1
    assert watch.stalled(0.3)                     # 새 기준에서 2 s 넘게 안 바뀌면 멈춤


# 노드 대역 ------------------------------------------------------------------

class _StubType(type):
    def __getattr__(cls, name):
        if name.startswith('__'):
            raise AttributeError(name)
        if name.isupper():
            return f'{cls.__name__}.{name}'
        nested = _StubType(name, (), {'__init__': _stub_init})
        setattr(cls, name, nested)
        return nested


def _stub_init(self, *args, **fields):
    self.__dict__.update(fields)
    self.__dict__.setdefault('header', types.SimpleNamespace(stamp=None))


def _module(name, **attrs):
    module = types.ModuleType(name)
    module.__dict__.update(attrs)
    return module


def _types(name, names):
    module = _module(name, **{n: _StubType(n, (), {'__init__': _stub_init}) for n in names})

    def make(attr):
        if attr.startswith('__'):
            raise AttributeError(attr)
        stub = _StubType(attr, (), {'__init__': _stub_init})
        setattr(module, attr, stub)
        return stub

    module.__getattr__ = make
    return module


def _fake_modules():
    fakes = {}

    def missing(name):
        return importlib.util.find_spec(name) is None

    if missing('rclpy'):
        for name in ('rclpy.action', 'rclpy.callback_groups', 'rclpy.duration', 'rclpy.executors',
                     'rclpy.node', 'rclpy.parameter', 'rclpy.qos', 'rclpy.time'):
            fakes[name] = _types(name, ())
        fakes['rclpy'] = _module('rclpy', ok=lambda: True)
    if missing('rokey_p3_interfaces'):
        fakes['rokey_p3_interfaces'] = _module('rokey_p3_interfaces')
        fakes['rokey_p3_interfaces.action'] = _types('rokey_p3_interfaces.action', ())
        fakes['rokey_p3_interfaces.msg'] = _types('rokey_p3_interfaces.msg', ())
        fakes['rokey_p3_interfaces.srv'] = _types('rokey_p3_interfaces.srv', ())
    for package in ('sensor_msgs', 'std_msgs'):
        if missing(package):
            fakes[package] = _module(package)
            fakes[f'{package}.msg'] = _types(f'{package}.msg', ())
    if missing('tf2_ros'):
        fakes['tf2_ros'] = _types('tf2_ros', ())
    return fakes


@pytest.fixture(scope='module')
def nodes():
    fakes = _fake_modules()
    added = [name for name in fakes if name not in sys.modules]
    for name in added:
        sys.modules[name] = fakes[name]
    try:
        arm = importlib.import_module('rokey_p3_manipulation.arm_node')
        m0609 = importlib.import_module('rokey_p3_manipulation.m0609_arm_node')
        yield arm, m0609
    finally:
        if added:
            for name in added + ['rokey_p3_manipulation.arm_node', 'rokey_p3_manipulation.m0609_arm_node']:
                sys.modules.pop(name, None)


class _Pub:
    def __init__(self, on_publish=None):
        self.sent = []
        self._on_publish = on_publish

    def publish(self, message):
        self.sent.append(message)
        if self._on_publish:
            self._on_publish(message)


class _Logger:
    def __getattr__(self, level):
        return lambda *args, **kwargs: None


class _Plant:
    """관절은 명령값으로 바로 간다. 50 Hz 로 노드의 joint Freshness 를 채운다."""

    def __init__(self, node, start):
        self.joints = tuple(start)
        self._node = node
        self._running = True
        threading.Thread(target=self._loop, daemon=True).start()

    def command(self, message):
        self.joints = tuple(message.position)

    def _loop(self):
        while self._running:
            with self._node._lock:
                self._node._joints.update(self.joints)
            time.sleep(0.02)

    def stop(self):
        self._running = False


def wait_until(predicate, limit=3.0):
    deadline = time.monotonic() + limit
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


def frozen(publisher, seconds=0.3):
    """seconds 동안 새 발행이 없었나."""
    before = len(publisher.sent)
    time.sleep(seconds)
    return len(publisher.sent) == before


def _common(node, module, monkeypatch):
    monkeypatch.setattr(module, 'rclpy', types.SimpleNamespace(ok=lambda: True))
    node._lock = threading.Lock()
    node._fence = ResetFence()
    node._closing = threading.Event()
    node._epoch = 0
    node._goal_active = False
    node._homing = False
    node._homing_cancelled = False
    node._gripper_closed = False
    node._holding_seen = False
    node._joint_names = [f'joint_{i}' for i in range(1, 7)]
    node._home_tolerance = 0.05
    node._via = None                     # via_joint_positions 기본값(끔)
    node._command_rate_hz = 50.0
    node._max_joint_speed = 1.0
    node._robot_id = 'test'
    node.gripper = _Pub()
    node._gripper_pub = node.gripper
    node._event_pub = _Pub()
    node._at_home_pub = _Pub()
    node.get_logger = lambda: _Logger()
    node.get_clock = lambda: types.SimpleNamespace(
        now=lambda: types.SimpleNamespace(nanoseconds=int(time.monotonic() * 1e9), to_msg=lambda: None))


def m0609_harness(nodes, monkeypatch, start):
    _, m0609 = nodes
    names = ('on_reset_begin', 'on_reset', 'fenced', 'generation', 'fence_moved', '_wait_goal_idle',
             'joint_positions', 'gripper_holding', 'epoch', 'set_goal_active', 'goal_active', 'moving', 'at_home',
             'send_joint_command', 'set_gripper', 'dropped', 'publish_event', 'sim_now', 'wait', 'move_to',
             '_wait_until_reached', 'start_homing', '_home_worker', '_wait_for_joints', '_homing_stopped',
             'stop_homing', '_accept_refill', '_execute_refill', '_publish_feedback', '_run_refill',
             '_wait_for_hold', '_stopped', '_return_home', '_limit_text', 'close', '_on_holding', '_end_goal',
             '_go_home', '_run_fixed_steps', '_run_rail_steps', '_apply_gripper', 'rail_positions', 'send_rail_command',
             'move_rail_to', '_rail_home', '_all_safe_poses', '_fold_tolerance', '_warn_rail_drift', '_on_rail_states',
             '_arm_points', '_rail_points', '_wait_fresh', '_note_gap', '_period', '_run_v2', '_on_inventory',
             '_plan_cell', '_precompute_plans', '_stream', '_poll', '_log_phase_times', '_hold_preferred',
             '_plan_cache_key', '_read_plan_cache_file', '_write_plan_cache_file')
    node = type('M0609Harness', (), {n: getattr(m0609.M0609ArmNode, n) for n in names})()
    _common(node, m0609, monkeypatch)
    node._joints = m0609.Freshness(m0609.STALE_JOINTS_S)
    node._holding = m0609.Freshness(m0609.STALE_STATUS_S)
    node._home = (0.0,) * 6
    node._commanded = tuple(start)
    node._open_loop = False
    node._limits = tuple((-6.3, 6.3) for _ in range(6))
    node._waypoint_tolerance = 0.05
    node._waypoint_timeout = 5.0
    node._state_gap_grace = 0.2      # 35fb28a: 상태 공백은 시한에서 뺀다(노드 기본값과 같다)
    node._refill_timeout = 30.0
    node._grasp_settle = 0.01
    node._release_settle = 0.01
    node._hold_timeout = 0.5
    node._poses = {key: (1.0 + 0.1 * index,) * 6 for index, key in enumerate(m0609.seq.POSE_KEYS)}
    node._homing_thread = None
    node._left_home = False
    node._rail_teach = None                          # 레일 끔(기본). test_m0609_rail 이 켠다
    node._scene_v2 = False                           # 장면 v1(기본). test_scene_v2 가 켠다
    node._rail_states = m0609.Freshness(m0609.STALE_JOINTS_S)
    node._rail_commanded = None
    node._rail_command_pub = None
    node._rail_joint_names = ['rail_x', 'rail_y']
    node._rail_tolerance = 0.01
    node._rail_timeout = 2.0
    node._rail_max_speed = (0.2, 0.2)
    node._rail_max_accel = None
    node._joint_speed_limits = None
    node._joint_accel_limits = None
    node._stale_grace = 3.0
    node._tcp_model = None
    node._tcp_max_speed = 0.0
    node._rail_command_rate = 50.0
    node._gap_warn = 0.2
    node._last_seen = {}
    node._arm_trail = []
    node._chained = False
    node._phase_marks = []
    node.plant = _Plant(node, start)
    node.joints = _Pub(node.plant.command)
    node._joint_command_pub = node.joints
    return node, m0609


def ur5_harness(nodes, monkeypatch, start):
    arm, _ = nodes
    names = ('on_reset_begin', 'on_reset', 'fenced', 'generation', 'fence_moved', '_wait_goal_idle',
             'joint_positions', 'epoch', 'set_goal_active', 'goal_active', 'homing', 'moving', 'send_joint_command',
             'set_gripper', 'gripper_closed', 'publish_event', 'home_joints', 'sim_now', 'wait', 'move_to',
             'move_home', 'move_via', 'start_homing', '_homing_stopped', 'stop_homing', '_wait_for_arrival',
             '_accept_pick', '_execute_pick', 'close', '_stopped_outcome', '_end_goal')
    node = type('ArmHarness', (), {n: getattr(arm.ArmNode, n) for n in names})()
    _common(node, arm, monkeypatch)
    node._joints = arm.Freshness(arm.STALE_JOINTS_S)
    node._holding = arm.Freshness(arm.STALE_STATUS_S)
    node._base_stopped = arm.Freshness(arm.STALE_STATUS_S)
    node._belt = arm.Freshness(arm.STALE_STATUS_S)
    node._gripper_view = arm.clear_state.GripperView(arm.STALE_STATUS_S, 2, 1)
    node._command_seq = arm.clear_state.CommandSeq()
    node._last_command = None
    node._gripper_command_pub = None
    node._pouches = None
    node._tag_read = None
    node._tf_buffer = types.SimpleNamespace(clear=lambda: None)
    node._clock_watch = ClockWatch(0.0)
    node._goal_generation = 0
    node._home = arm.np.zeros(6)
    node._limits = tuple((-6.3, 6.3) for _ in range(6))
    node._cabinet_frame = 'bed_a1/cabinet'
    node._callbacks = None
    node.timers = []

    def create_timer(period, callback, callback_group=None):
        timer = types.SimpleNamespace(alive=True)
        node.timers.append(timer)

        def loop():
            while timer.alive:
                callback()
                time.sleep(period)
        threading.Thread(target=loop, daemon=True).start()
        return timer

    node.create_timer = create_timer
    node.destroy_timer = lambda timer: setattr(timer, 'alive', False)
    node.plant = _Plant(node, start)
    node.joints = _Pub(node.plant.command)
    node._joint_command_pub = node.joints
    return node, arm


# A1 ---------------------------------------------------------------------------

def test_reset_fences_home_and_finally_publishers_m0609_homing(nodes, monkeypatch):
    """M0609 홈 복귀 중 RESET_BEGIN → 명령 0건. barrier 중 복귀·그리퍼·새 goal 없음. RESET_DONE 뒤 스스로 복귀."""
    node, m0609 = m0609_harness(nodes, monkeypatch, start=(1.0,) * 6)
    try:
        node._left_home = True
        node.start_homing()
        assert wait_until(lambda: len(node.joints.sent) >= 3)
        node.on_reset_begin(2)
        assert not node._homing                                  # RESET_BEGIN 이 복귀를 접고 끝날 때까지 기다렸다
        assert frozen(node.joints)
        thread = node._homing_thread
        node.start_homing()                                      # finally·on_reset 이 부르는 것과 같다
        assert node._homing_thread is thread and not node._homing   # barrier 중에는 복귀 스레드를 안 만든다
        node.set_goal_active(True)                               # goal 이 살아 있어도 발행 자체가 막힌다
        assert node.send_joint_command((0.5,) * 6) is False
        node.set_goal_active(False)
        node.set_gripper(True)
        assert frozen(node.joints) and node.gripper.sent == []
        goal = types.SimpleNamespace(item_id='drug-amox', slot=0)
        assert node._accept_refill(goal) == m0609.GoalResponse.REJECT

        paused = len(node.joints.sent)
        node.on_reset(2)                                         # 같은 epoch 의 RESET_DONE
        assert wait_until(lambda: len(node.joints.sent) > paused)
        assert wait_until(lambda: node.at_home() is True)
    finally:
        node.stop_homing()
        node.plant.stop()


def test_reset_fences_home_and_finally_publishers_m0609_goal_finally(nodes, monkeypatch):
    """M0609 보충 실행 중 RESET_BEGIN → goal 이 멈추고 finally 가 홈 복귀를 시작하지 않는다(cancel 없이도)."""
    node, _ = m0609_harness(nodes, monkeypatch, start=(0.0,) * 6)
    try:
        handle = types.SimpleNamespace(request=types.SimpleNamespace(item_id='drug-amox', slot=0),
                                       is_cancel_requested=False, state=None, publish_feedback=lambda fb: None)
        handle.succeed = lambda: setattr(handle, 'state', 'succeeded')
        handle.abort = lambda: setattr(handle, 'state', 'aborted')
        handle.canceled = lambda: setattr(handle, 'state', 'canceled')
        worker = threading.Thread(target=node._execute_refill, args=(handle,), daemon=True)
        worker.start()
        assert wait_until(lambda: len(node.joints.sent) >= 20)          # 홈에서 0.4 rad 쯤 떠났다
        node.on_reset_begin(2)
        at_begin = len(node.joints.sent)
        worker.join(3.0)
        assert handle.state == 'aborted'
        assert frozen(node.joints, 0.5) and frozen(node.gripper)
        assert len(node.joints.sent) <= at_begin + 1                     # 검사를 막 지난 한 점까지만
        assert not node._homing
    finally:
        node.stop_homing()
        node.plant.stop()


def test_reset_done_without_begin_keeps_the_existing_m0609_self_homing(nodes, monkeypatch):
    node, _ = m0609_harness(nodes, monkeypatch, start=(1.0,) * 6)
    try:
        node._left_home = True
        node.on_reset(2)                                         # RESET_BEGIN 없이 RESET_DONE 만(12호 전)
        assert wait_until(lambda: len(node.joints.sent) >= 3)
    finally:
        node.stop_homing()
        node.plant.stop()


def test_reset_fences_home_and_finally_publishers_ur5(nodes, monkeypatch):
    """UR5 홈 복귀 타이머 중 RESET_BEGIN → 명령 0건. finally 도 barrier 를 지났으면 홈으로 안 간다."""
    node, arm = ur5_harness(nodes, monkeypatch, start=(1.0,) * 6)
    try:
        node.start_homing()
        assert wait_until(lambda: len(node.joints.sent) >= 3)
        node.on_reset_begin(2)
        assert not node.homing()
        assert frozen(node.joints)
        timers = len(node.timers)
        node.start_homing()
        node.set_goal_active(True)                               # goal 이 살아 있어도 발행 자체가 막힌다
        assert node.send_joint_command(arm.np.full(6, 0.5)) is False
        node.set_goal_active(False)
        node.set_gripper(True)
        assert len(node.timers) == timers and node.gripper.sent == [] and frozen(node.joints)
        goal = types.SimpleNamespace(order_id='ord-0001', source=arm.PickPouch.Goal.SOURCE_BELT, target_slot=0)
        assert node._accept_pick(goal) == arm.GoalResponse.REJECT

        # RESET_DONE: 울타리가 열린다. UR5 는 isaac 이 홈으로 되돌리므로 스스로 복귀하지 않는다(기존).
        node.on_reset(2)
        assert not node.fenced() and len(node.timers) == timers

        # barrier 를 지난 goal 의 finally 는 홈 복귀를 시작하지 않는다.
        handle = types.SimpleNamespace(request=types.SimpleNamespace(order_id='ord-0001'),
                                       is_cancel_requested=False, state=None)
        handle.succeed = lambda: setattr(handle, 'state', 'succeeded')
        handle.abort = lambda: setattr(handle, 'state', 'aborted')
        handle.canceled = lambda: setattr(handle, 'state', 'canceled')

        def run_pick_hit_by_reset(goal_handle, generation):
            node.on_reset_begin(3)
            return arm.perm.OUTCOME_TIMEOUT, '리셋 barrier'

        node._run_pick = run_pick_hit_by_reset
        node._execute_pick(handle)
        assert handle.state == 'aborted'
        assert len(node.timers) == timers and not node.homing()
    finally:
        node.stop_homing()
        node.plant.stop()


def test_m0609_precompute_keeps_going_when_the_inventory_moves(nodes):
    """#490 후속(9/23): 미리 계산 도중 재고가 다시 와도(세대 +1) 남은 칸을 끝까지 풀고 요약을 낸다.

    `_on_inventory` 는 이 스레드가 살아 있으면 새로 띄우지 않는다. 그래서 세대가 바뀌었다고 여기서 그만두면
    남은 칸을 아무도 미리 풀지 않는다(#490 이 그랬다).
    """
    _, m0609 = nodes
    node = type('Precompute', (), {name: getattr(m0609.M0609ArmNode, name) for name in
                                   ('_precompute_plans', '_plan_cache_key', '_read_plan_cache_file',
                                    '_write_plan_cache_file')})()
    node._plan_cache_dir = ''          # 파일 계획 캐시 끔. 이 시험은 미리 푸는 순서만 본다
    node._lock = threading.Lock()
    node._v2_cache_lock = threading.Lock()
    node._closing = threading.Event()
    node._scene = 'scene'
    node._inventory_generation = 1
    node._inventory_source = 'src'
    pending = ['c1', 'c2', 'c3']
    solved = types.SimpleNamespace(steps=object(), why='', seconds=1.0)
    node._v2_cache = types.SimpleNamespace(missing=lambda scene: list(pending),
                                           entries=lambda: dict.fromkeys(('c1', 'c2', 'c3'), solved))

    def plan(scene, cell):
        pending.remove(cell)
        node._inventory_generation += 1          # 계산하는 사이에 재고가 다시 왔다

    node._plan_cell = plan
    published = []
    node._publish_plan_cache_payload = published.append
    node.get_logger = lambda: types.SimpleNamespace(info=lambda *args, **kwargs: None)
    node._precompute_plans()
    assert pending == []
    assert len(published) == 1
    assert published[0]['solved'] == 3 and published[0]['generation'] == 4
