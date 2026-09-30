"""M0609 레일 보충(`rail_enabled`). ROS 없이 돈다(test_reset_fence 의 노드 대역·관절 plant 를 쓴다).

조제실 스테이지(pharmacy_stage.py)의 2축 레일 위 M0609 를 `/m0609/refill` 하나로 구동한다(재범 9/18, 계약 v1 불변).
- 순서: 레일은 팔이 접힌 자세(홈·raise·retreat)일 때만 움직이고, 레일이 허용오차 안에 든 뒤에 팔이 움직인다.
- 레일 시한 초과는 기존 실패 결과(abort)다.
- 끊기면 지나온 팔 경로를 되짚어 접힌 자세로 간 뒤 레일 홈 → 팔 홈이다.
- 레일 끔(기본)은 이전과 같다.
"""

import math
import os
import threading
import time
import types

import pytest
import test_reset_fence as rf
import yaml

from rokey_p3_manipulation import refill_sequence as seq

nodes = rf.nodes
TEACH_FILE = os.path.join(os.path.dirname(__file__), '..', 'config', 'm0609_rail_teach.yaml')


def teach_data():
    with open(TEACH_FILE, encoding='utf-8') as handle:
        return yaml.safe_load(handle)


def teach():
    return seq.load_rail_teach(teach_data())


# ---- teach 파일과 검사(순수) ----------------------------------------------------------------------

def test_the_shipped_teach_moves_the_rail_only_from_folded_poses():
    loaded = teach()
    for letter in seq.RAIL_SLOTS:
        steps = loaded.slots[letter]
        arm = 'home'
        for step in steps:
            if step.rail is not None:
                assert arm == 'home' or arm in loaded.safe_phases, (letter, step.phase, arm)
            elif step.joints is not None:
                arm = step.phase
        assert [s.gripper for s in steps if s.gripper] == [seq.GRIP_CLOSE, seq.GRIP_OPEN]
        # 팔 목표가 모두 M0609 자산 한계 안이다(노드가 보내기 전에 거부하지 않는다).
        for name, joints in seq.rail_arm_targets(loaded, letter):
            assert seq.limit_violation(joints, seq.M0609_JOINT_LIMITS) is None, name
    assert loaded.home_rail == (0.0, 0.0)
    assert loaded.slots['a'][-1].phase == 'retreat' and 'retreat' in loaded.safe_phases


@pytest.mark.parametrize('mutate, message', [
    (lambda d: d['slots']['a'].insert(6, {'phase': 'bad_rail', 'rail': [0.0, 0.0]}), '레일은'),   # descend 뒤
    (lambda d: d['slots']['a'].__setitem__(0, {'phase': 'x', 'rail': [0.0, 0.0], 'joints': [0.0] * 6}), '같이'),
    (lambda d: d['slots']['b'].insert(1, {'phase': 'early', 'gripper': 'open'}), '잡기 전에'),
    (lambda d: d['slots'].pop('b'), 'slots.b'),
    (lambda d: d['slots']['a'][1].__setitem__('tolerance_rad', 0.0), '양수'),
    (lambda d: d['slots']['a'][0].__setitem__('tolerance_rad', 0.01), '팔 단계에만'),
    (lambda d: d['slots']['a'][1].__setitem__('joints', [0.0] * 5), '관절 6개'),
])
def test_a_bad_teach_is_refused_before_the_node_starts(mutate, message):
    data = teach_data()
    mutate(data)
    with pytest.raises(seq.RefillPlanError, match=message):
        seq.load_rail_teach(data)


# ---- 노드(대역) --------------------------------------------------------------------------------

class RailPlant:
    """레일. 기본은 명령값으로 바로 간다. `stuck` 이면 안 움직이고 `lag` 면 명령 쪽으로 천천히 간다."""

    def __init__(self, node, start, mode='follow'):
        self.position = tuple(start)
        self.target = tuple(start)
        self.mode = mode
        self.drift = None
        self._node = node
        self._running = True
        threading.Thread(target=self._loop, daemon=True).start()

    def command(self, message):
        self.target = tuple(message.position)
        if self.mode == 'follow':
            self.position = self.target

    def _loop(self):
        while self._running:
            if self.mode == 'lag':
                pairs = zip(self.position, self.target, strict=True)
                self.position = tuple(p + max(-0.02, min(0.02, t - p)) for p, t in pairs)
            reported = self.position if self.drift is None else self.drift
            with self._node._lock:
                self._node._rail_states.update(reported)
            time.sleep(0.02)

    def stop(self):
        self._running = False


class Log:
    def __init__(self):
        self.lines = []

    def __getattr__(self, level):
        return lambda text, **kwargs: self.lines.append((level, text))


def rail_node(nodes, monkeypatch, rail_mode='follow'):
    loaded = teach()
    node, m0609 = rf.m0609_harness(nodes, monkeypatch, start=loaded.home_joints)
    node._home = loaded.home_joints
    node._rail_teach = loaded
    node._rail_commanded = loaded.home_rail
    node._max_joint_speed = 25.0                      # 한 점 0.5 rad. 테스트가 빨리 끝나게
    node._rail_max_speed = (5.0, 5.0)                 # 한 점 0.1 m
    node._waypoint_timeout = 2.0
    node.log = Log()
    node.get_logger = lambda: node.log
    node.rail = RailPlant(node, loaded.home_rail, rail_mode)
    node.order = []                                   # ('arm'|'rail'|'grip', 값, 그 순간 다른 쪽 상태)

    def on_arm(message):
        node.order.append(('arm', tuple(message.position), node.rail.position))
        node.plant.command(message)

    def on_rail(message):
        node.order.append(('rail', tuple(message.position), node.plant.joints))
        node.rail.command(message)

    node.joints = rf._Pub(on_arm)
    node._joint_command_pub = node.joints
    node.rails = rf._Pub(on_rail)
    node._rail_command_pub = node.rails
    node.grip = {'closed': False}

    def on_grip(message):
        node.grip['closed'] = bool(message.data)
        node.order.append(('grip', bool(message.data), None))

    node.gripper = rf._Pub(on_grip)
    node._gripper_pub = node.gripper
    running = {'on': True}

    def holding_loop():
        while running['on']:
            with node._lock:
                node._holding.update(node.grip['closed'])
            time.sleep(0.02)

    threading.Thread(target=holding_loop, daemon=True).start()
    node.stop_threads = lambda: (running.update(on=False), node.stop_homing(), node.plant.stop(), node.rail.stop())
    return node, loaded


def handle_for(node, slot=0):
    handle = types.SimpleNamespace(request=types.SimpleNamespace(item_id='drug-ibu', slot=slot),
                                   is_cancel_requested=False, state=None, at_result=None, phases=[])

    def finish(state):
        handle.state = state
        handle.at_result = {'joints': node.plant.joints, 'rail': node.rail.position}

    handle.succeed = lambda: finish('succeeded')
    handle.abort = lambda: finish('aborted')
    handle.canceled = lambda: finish('canceled')
    handle.publish_feedback = lambda feedback: handle.phases.append(feedback.phase)
    return handle


def near(a, b, tolerance=1e-6):
    return a is not None and all(abs(x - y) <= tolerance for x, y in zip(a, b, strict=True))


@pytest.mark.parametrize('slot, letter', [(0, 'a'), (1, 'b')])
def test_refill_moves_the_rail_only_while_the_arm_is_folded_and_returns_home(nodes, monkeypatch, slot, letter):
    node, loaded = rail_node(nodes, monkeypatch)
    try:
        handle = handle_for(node, slot)
        result = node._execute_refill(handle)
        assert handle.state == 'succeeded' and result.success
        assert handle.phases == [step.phase for step in loaded.slots[letter]]
        folded = [loaded.home_joints] + [s.joints for s in loaded.slots[letter] if s.phase in loaded.safe_phases]
        rails = [entry for entry in node.order if entry[0] == 'rail']
        assert rails, '레일 명령이 없다'
        for _, _, arm in rails:                                          # 레일 명령 순간 팔은 접힌 자세
            assert any(near(arm, pose) for pose in folded), arm
        # 결과 순간 레일·팔 모두 홈이다. 레일 홈은 팔이 retreat 일 때 갔고, 팔 홈은 그 뒤다.
        assert near(handle.at_result['rail'], loaded.home_rail) and near(handle.at_result['joints'], loaded.home_joints)
        retreat = loaded.slots[letter][-1].joints
        last_rail = max(i for i, entry in enumerate(node.order) if entry[0] == 'rail')
        assert near(node.order[last_rail][2], retreat)
        assert near(node.order[-1][1], loaded.home_joints) and node.order[-1][0] == 'arm'
        [done] = [e for e in node._event_pub.sent if e.name.endswith('REFILL_DONE')]
        assert done.detail == f'drug-ibu slot {letter}'
    finally:
        node.stop_threads()


def test_the_arm_waits_until_the_rail_arrives(nodes, monkeypatch):
    node, loaded = rail_node(nodes, monkeypatch, rail_mode='lag')
    try:
        node._rail_timeout = 5.0
        handle = handle_for(node)
        node._execute_refill(handle)
        assert handle.state == 'succeeded'
        rail_targets = [s.rail for s in loaded.slots['a'] if s.rail is not None]
        # 레일 단계 뒤 첫 팔 명령 순간 레일은 그 단계 목표의 허용오차 안이다(명령만 내고 바로 팔을 움직이지 않는다).
        seen = 0
        for index, entry in enumerate(node.order):
            if entry[0] == 'rail' and near(entry[1], rail_targets[min(seen, len(rail_targets) - 1)]):
                following = next(e for e in node.order[index + 1:] if e[0] == 'arm')
                assert seq.at_pose(following[2], entry[1], node._rail_tolerance), (entry[1], following[2])
                seen += 1
        assert seen >= len(rail_targets)
    finally:
        node.stop_threads()


def test_a_rail_that_never_arrives_aborts_with_the_existing_failure(nodes, monkeypatch):
    node, loaded = rail_node(nodes, monkeypatch, rail_mode='stuck')
    try:
        node._rail_timeout = 0.3
        handle = handle_for(node)
        started = time.monotonic()
        result = node._execute_refill(handle)
        assert handle.state == 'aborted' and not result.success
        assert time.monotonic() - started < 5.0
        assert handle.phases == ['rail_to_shelf']                        # 선반 쪽 팔 단계로 가지 않았다
        assert not [e for e in node.order if e[0] == 'arm' and not near(e[1], loaded.home_joints)]
        assert not [e for e in node._event_pub.sent if e.name.endswith('REFILL_DONE')]
        assert any('레일 도착 못 함' in text for _, text in node.log.lines)
    finally:
        node.stop_threads()


def test_the_rail_is_never_commanded_while_the_arm_is_out(nodes, monkeypatch):
    node, loaded = rail_node(nodes, monkeypatch)
    try:
        node.set_goal_active(True)
        descend = next(s.joints for s in loaded.slots['a'] if s.phase == 'descend')
        node.plant.joints = descend                                       # 선반 안
        time.sleep(0.05)
        assert node.move_rail_to((0.5, 0.0), seq.rail_safe_poses(loaded, 'a')) is False
        assert node.rails.sent == []
        assert any(level == 'error' and '접힌 자세' in text for level, text in node.log.lines)
    finally:
        node.set_goal_active(False)
        node.stop_threads()


def test_cancel_inside_the_shelf_retraces_before_the_rail_goes_home(nodes, monkeypatch):
    node, loaded = rail_node(nodes, monkeypatch)
    try:
        handle = handle_for(node)
        descend = next(s.joints for s in loaded.slots['a'] if s.phase == 'descend')
        original = node.move_to

        def move_then_cancel(target, cancelled=None, tolerance=None, **options):
            reached = original(target, cancelled, tolerance, **options)
            if target == descend:
                handle.is_cancel_requested = True
            return reached

        node.move_to = move_then_cancel
        node._execute_refill(handle)
        assert handle.state == 'canceled'
        assert rf.wait_until(lambda: node.at_home() is True and near(node.rail.position, loaded.home_rail), 5.0)
        after = [entry for entry in node.order if entry[0] in ('arm', 'rail')]
        cancel_at = max(i for i, e in enumerate(after) if e[0] == 'arm' and near(e[1], descend))
        tail = after[cancel_at + 1:]
        first_rail = next(i for i, e in enumerate(tail) if e[0] == 'rail')
        # 레일이 움직이기 전에 팔이 온 길(above_canister → shelf_in_2 → shelf_in_1 → shelf_front → 홈)을 되짚었다.
        visited = [e[1] for e in tail[:first_rail]]
        path = [s.joints for s in loaded.slots['a'] if s.phase in ('above_canister', 'shelf_in_2', 'shelf_in_1',
                                                                    'shelf_front')]
        for pose in reversed(path):
            assert any(near(point, pose) for point in visited), pose
        assert near(tail[first_rail][2], loaded.home_joints)              # 레일 명령 때 팔은 홈
        assert ('grip', True, None) not in node.order                     # 취소 뒤 grasp 에서 닫지 않았다
    finally:
        node.stop_threads()


def test_rail_drift_after_an_arm_step_is_a_warning_not_a_failure(nodes, monkeypatch):
    node, loaded = rail_node(nodes, monkeypatch)
    try:
        handle = handle_for(node)
        original = node.move_to
        insert = next(s.joints for s in loaded.slots['a'] if s.phase == 'insert')

        def move_then_drift(target, cancelled=None, tolerance=None, **options):
            reached = original(target, cancelled, tolerance, **options)
            if target == insert:
                node.rail.drift = (0.9444, -0.10)                        # Simu 가 본 밀림(rail_y 하한)
                time.sleep(0.06)
            return reached

        node.move_to = move_then_drift
        node._rail_timeout = 0.3
        node._execute_refill(handle)
        warns = [text for level, text in node.log.lines if level == 'warn' and '레일이 밀려' in text]
        assert warns and warns[0].startswith('insert:')
    finally:
        node.stop_threads()


def test_insert_points_use_their_tighter_tolerance(nodes, monkeypatch):
    node, loaded = rail_node(nodes, monkeypatch)
    try:
        seen = []
        original = node._wait_until_reached

        def spy(target, cancelled, tolerance=None):
            seen.append((target, tolerance))
            return original(target, cancelled, tolerance)

        node._wait_until_reached = spy
        node._execute_refill(handle_for(node))
        tight = {s.joints for s in loaded.slots['a'] if s.tolerance is not None}
        assert {s.phase for s in loaded.slots['a'] if s.tolerance} == {'inlet_top', 'inlet_mid', 'insert'}
        assert all(tol == 0.0025 for target, tol in seen if target in tight)
        assert all(tol is None for target, tol in seen if target not in tight)
    finally:
        node.stop_threads()


def test_rail_off_publishes_no_rail_command_and_keeps_the_fixed_sequence(nodes, monkeypatch):
    """레일 끔(기본)은 v0 고정 받침 그대로: 여섯 단계, 레일 명령 0건, 끝에 홈."""
    node, m0609 = rf.m0609_harness(nodes, monkeypatch, start=(0.0,) * 6)
    try:
        node._max_joint_speed = 25.0
        node._waypoint_timeout = 2.0
        node._rail_command_pub = rf._Pub()
        node.grip = {'closed': False}
        node.gripper = rf._Pub(lambda msg: node.grip.update(closed=bool(msg.data)))
        node._gripper_pub = node.gripper
        stop = {'on': True}

        def holding_loop():
            while stop['on']:
                with node._lock:
                    node._holding.update(node.grip['closed'])
                time.sleep(0.02)

        threading.Thread(target=holding_loop, daemon=True).start()
        handle = handle_for(node)
        handle.at_result = None
        handle.succeed = lambda: setattr(handle, 'state', 'succeeded')
        node._execute_refill(handle)
        assert handle.state == 'succeeded'
        assert handle.phases == list(seq.PHASES)
        assert node._rail_command_pub.sent == []
        finals = [tuple(message.position) for message in node.joints.sent]
        expected = [step.joints for step in seq.plan_refill(0, node._poses)] + [node._home]
        for pose in expected:                                            # 각 단계 목표를 그 순서로 지난다
            index = next(i for i, point in enumerate(finals) if near(point, pose))
            finals = finals[index + 1:]
        assert math.isclose(sum(node.joints.sent[-1].position), 0.0, abs_tol=1e-9)
    finally:
        stop['on'] = False
        node.stop_homing()
        node.plant.stop()


# ---- 속도·가감속(재범 9/18: 최고 속도의 80%, 가감속 필수) --------------------------------------------

SPEED = (2.094, 2.094, 2.513, 3.142, 3.142, 3.142)     # 노드 기본값(80%)
ACCEL = (4.0, 4.0, 4.0, 6.0, 6.0, 6.0)


def velocities(points, start, period):
    path = [tuple(start)] + list(points)
    return [tuple((b - a) / period for a, b in zip(p, q, strict=True)) for p, q in zip(path, path[1:], strict=False)]


@pytest.mark.parametrize('goal', [(1.5, -0.8, 0.9, 0.3, -2.0, 1.0), (0.02, 0.0, 0.0, 0.0, 0.01, 0.0)])
def test_trapezoid_is_synchronized_and_within_speed_and_accel(goal):
    start = (0.0,) * 6
    period = 0.02
    points = seq.trapezoid_points(start, goal, SPEED, ACCEL, period)
    assert points[-1] == tuple(goal)
    vel = velocities(points, start, period)
    for axis in range(6):
        assert max(abs(v[axis]) for v in vel) <= SPEED[axis] * 1.001
        acc = [(b[axis] - a[axis]) / period for a, b in zip([(0.0,) * 6] + vel, vel, strict=False)]
        assert max(abs(x) for x in acc[:-1]) <= ACCEL[axis] * 1.001 + 1e-9
    # 동기화: 모든 축의 진행률이 매 점 같다(같이 출발·같이 도착).
    for point in points:
        ratios = {round(p / g, 9) for p, g in zip(point, goal, strict=True) if g}
        assert len(ratios) == 1
    # 가감속: 처음과 끝은 느리고 가운데가 빠르다.
    speeds = [max(abs(x) for x in v) for v in vel]
    assert speeds[0] < max(speeds) and speeds[-2] < max(speeds)


def test_trapezoid_without_motion_is_the_goal():
    assert seq.trapezoid_points((0.5, 0.5), (0.5, 0.5), (1.0, 1.0), (1.0, 1.0), 0.02) == [(0.5, 0.5)]


def test_speed_without_accel_is_refused(nodes):
    _, m0609 = nodes
    with pytest.raises(ValueError, match='가감속'):
        m0609.speed_profile(list(SPEED), [0.0], 6, 'rail_joint')
    assert m0609.speed_profile([0.0], [0.0], 6, 'rail_joint') == (None, None)          # 비우면 이전처럼 등속
    assert m0609.speed_profile(list(SPEED), list(ACCEL), 6, 'rail_joint') == (SPEED, ACCEL)
    with pytest.raises(ValueError):
        m0609.speed_profile([1.0] * 5, list(ACCEL), 6, 'rail_joint')


def test_rail_mode_arm_moves_follow_the_profile_and_the_tcp_cap(nodes, monkeypatch):
    from rokey_p3_manipulation import m0609_kinematics as kin
    node, loaded = rail_node(nodes, monkeypatch)
    try:
        node._joint_speed_limits, node._joint_accel_limits = SPEED, ACCEL
        node._rail_max_speed, node._rail_max_accel = (0.8, 0.8), (1.0, 1.0)
        node._tcp_model = kin.M0609(kin.ToolTransform((0.0, 0.0, 0.19671), (0.0, 0.0, 0.0, 1.0)))
        node._tcp_max_speed = 0.8
        node._command_rate_hz = 20.0                                            # v0 명령 주기(기본)
        period = node._period()
        assert period == pytest.approx(0.02)                                    # 레일 모드는 rail_command_rate_hz 50
        retreat = loaded.slots['a'][-1].joints
        points = node._arm_points(retreat, loaded.home_joints, period)          # 사다리꼴만이면 TCP 0.87 m/s
        tcp = seq.peak_speed([retreat] + points, period, lambda q: node._tcp_model.fk(q).position_m)
        assert 0.7 < tcp <= 0.8
        for axis, v in enumerate(SPEED):
            assert max(abs(x[axis]) for x in velocities(points, retreat, period)) <= v * 1.001
        rail = node._rail_points((0.0, 0.0), (0.94, -0.05), period)
        assert max(max(abs(x) for x in v) for v in velocities(rail, (0.0, 0.0), period)) <= 0.8 * 1.001
        handle = handle_for(node)
        node._execute_refill(handle)
        assert handle.state == 'succeeded'
    finally:
        node.stop_threads()


def test_rail_off_keeps_the_old_uniform_step_and_rate(nodes, monkeypatch):
    node, _ = rf.m0609_harness(nodes, monkeypatch, start=(0.0,) * 6)
    try:
        node._joint_speed_limits, node._joint_accel_limits = SPEED, ACCEL       # 기본값이 있어도 레일 끔이면 안 쓴다
        assert node._period() == pytest.approx(1.0 / node._command_rate_hz)
        points = node._arm_points((0.0,) * 6, (1.0,) * 6, node._period())
        assert points == seq.interpolate((0.0,) * 6, (1.0,) * 6, node._max_joint_speed / node._command_rate_hz)
    finally:
        node.plant.stop()


class _Silent:
    """joint_states 를 잠깐 끊는다. 대역 plant 가 Freshness 를 채우지 못하게 막는다."""

    def __init__(self, node):
        self.node = node

    def cut(self, seconds):
        node = self.node
        real_update = node._joints.update
        node._joints.update = lambda value: None
        with node._lock:
            node._joints.clear()
        def restore():
            time.sleep(seconds)
            node._joints.update = real_update

        threading.Thread(target=restore, daemon=True).start()


@pytest.mark.parametrize('gap, grace, expected', [(0.6, 2.0, 'succeeded'), (1.5, 0.3, 'aborted')])
def test_a_short_state_gap_pauses_and_resumes_a_long_one_aborts(nodes, monkeypatch, gap, grace, expected):
    node, loaded = rail_node(nodes, monkeypatch)
    try:
        node._stale_grace = grace
        node._max_joint_speed = 5.0                                       # 한 점 0.1 rad: 이동 중간 점이 생긴다
        handle = handle_for(node)
        original = node.send_joint_command
        targets = [s.joints for s in loaded.slots['a'] if s.joints is not None]
        state = {'done': False}

        def send_then_cut(joints):
            # 선반 쪽 이동 한가운데(목표가 아닌 점)에서 joint_states 를 끊는다. 다음 점을 낼 때 stale 이다.
            sent = original(joints)
            if (sent and not state['done'] and node.rail.position != loaded.home_rail
                    and not any(seq.at_pose(joints, pose, 1e-9) for pose in targets)):
                state['done'] = True
                _Silent(node).cut(gap)
            return sent

        node.send_joint_command = send_then_cut
        node._execute_refill(handle)
        assert handle.state == expected
        texts = [text for _, text in node.log.lines]
        assert any('joint_states 가 끊겼다' in text for text in texts)
        if expected == 'succeeded':
            assert any('다시 온다' in text for text in texts)
    finally:
        node.stop_threads()


def test_state_gaps_are_logged_in_rail_mode(nodes, monkeypatch):
    node, _ = rail_node(nodes, monkeypatch)
    try:
        node._note_gap('rail/joint_states')
        node._note_gap('rail/joint_states')
        assert not [t for _, t in node.log.lines if '수신 공백' in t]
        time.sleep(0.25)
        node._note_gap('rail/joint_states')
        [line] = [t for _, t in node.log.lines if '수신 공백' in t]
        assert line.startswith('rail/joint_states 수신 공백 0.2')
    finally:
        node.stop_threads()


def test_a_move_that_starts_during_a_gap_waits_instead_of_failing(nodes, monkeypatch):
    node, loaded = rail_node(nodes, monkeypatch)
    try:
        node.set_goal_active(True)
        _Silent(node).cut(0.3)
        assert node.joint_positions() is None
        target = loaded.slots['a'][1].joints                                   # shelf_front(레일은 홈이라 무관)
        assert node.move_to(target) is True
        assert any('joint_states 가 끊겼다' in text for _, text in node.log.lines)
    finally:
        node.set_goal_active(False)
        node.stop_threads()


def test_states_back_by_the_time_we_look_mean_go_on(nodes, monkeypatch):
    """stale 로 명령을 못 냈는데 확인하는 순간 이미 다시 와 있으면(늦은 메시지가 한꺼번에 처리) 이어 간다."""
    node, loaded = rail_node(nodes, monkeypatch)
    try:
        node.set_goal_active(True)
        assert node._wait_fresh(node.joint_positions, 'joint_states', None) is True
        assert not [t for _, t in node.log.lines if '끊겼다' in t]
        node._rail_teach = None                                             # 레일 끔은 이전처럼 곧바로 실패
        assert node._wait_fresh(node.joint_positions, 'joint_states', None) is False
    finally:
        node.set_goal_active(False)
        node.stop_threads()


# ---- sim 시계 계단과 명령 간격(실습7-a4: 점마다 2틱, 설계의 1.67배) ------------------------------------

def stepped_clock(node, hz):
    """/clock 흉내: wall 을 따라가되 1/hz 계단으로만 오른다(Isaac physics_dt 1/60, 또는 30 Hz)."""
    origin = time.monotonic()
    node.sim_now = lambda: math.floor((time.monotonic() - origin) * hz) / hz


@pytest.mark.parametrize('hz', [60.0, 30.0])
def test_a_stream_takes_the_designed_time_on_a_stepped_clock(nodes, monkeypatch, hz):
    node, loaded = rail_node(nodes, monkeypatch)
    try:
        node.set_goal_active(True)
        stepped_clock(node, hz)
        period = node._period()
        assert period == pytest.approx(0.02)
        points = [(0.001 * i,) * 6 for i in range(1, 51)]                   # 설계 50 × 0.02 = 1.0 s
        started = node.sim_now()
        assert node._stream(points, node.send_joint_command, node.joint_positions, 'joint_states', None)
        took = node.sim_now() - started
        design = (len(points) - 1) * period
        assert design - 1e-9 <= took <= design + 1.0 / hz + 1e-9               # 예전은 1.67배(60 Hz)·1.67배(30 Hz)
        sent = [m.position for m in node.joints.sent]
        indexes = [points.index(tuple(p)) for p in sent]
        assert indexes == sorted(indexes) and indexes[-1] == len(points) - 1   # 순서대로, 마지막 점은 꼭 낸다
        assert len(sent) <= math.ceil(design * hz) + 1                        # 틱마다 한 번(차례인 것 중 마지막)
    finally:
        node.set_goal_active(False)
        node.stop_threads()


def test_polling_waits_one_tick_in_rail_mode(nodes, monkeypatch):
    node, _ = rail_node(nodes, monkeypatch)
    try:
        stepped_clock(node, 60.0)
        start = node.sim_now()
        assert node._poll(None)
        assert node.sim_now() - start == pytest.approx(1.0 / 60.0, abs=1e-9)
    finally:
        node.stop_threads()


def test_consecutive_arm_moves_do_not_wait_in_between_and_the_path_is_continuous(nodes, monkeypatch):
    node, loaded = rail_node(nodes, monkeypatch)
    try:
        awaited = []
        original = node._wait_until_reached

        def spy(target, cancelled, tolerance=None):
            awaited.append(target)
            return original(target, cancelled, tolerance)

        node._wait_until_reached = spy
        handle = handle_for(node)
        node._execute_refill(handle)
        assert handle.state == 'succeeded'
        steps = loaded.slots['a']
        settle = set()
        for index, step in enumerate(steps):
            if step.joints is None:
                continue
            following = steps[index + 1] if index + 1 < len(steps) else None
            if step.gripper is not None or step.tolerance is not None or following is None or following.joints is None:
                settle.add(step.joints)
        run = [t for t in awaited if t != loaded.home_joints]
        # 잡기·놓기·레일 앞·끝·허용오차 점만 기다린다
        assert set(run) == settle and len(run) == len(settle)
        through = [s.joints for s in steps if s.joints is not None and s.joints not in settle]
        assert through                                                        # 이 teach 에는 이어지는 이동이 있다
        arm = [e[1] for e in node.order if e[0] == 'arm']
        for pose in through:
            at = max(i for i, point in enumerate(arm) if near(point, pose))
            step = max(abs(a - b) for a, b in zip(arm[at], arm[at + 1], strict=True))
            assert step <= 0.5 + 1e-9                     # 다음 이동은 이 목표에서 이어진다(한 점 크기 안)
    finally:
        node.stop_threads()


def test_phase_times_are_logged_once_per_goal_in_rail_mode(nodes, monkeypatch):
    node, loaded = rail_node(nodes, monkeypatch)
    try:
        handle = handle_for(node)
        node._execute_refill(handle)
        [line] = [t for _, t in node.log.lines if '단계 시간' in t]
        assert line.startswith('Refill drug-ibu 단계 시간(sim s') and ' 합 ' in line
        for phase in handle.phases:
            assert f'{phase.split()[0]} ' in line
    finally:
        node.stop_threads()


def test_a_rail_stage_starts_from_the_previous_target_not_the_residual(nodes, monkeypatch):
    """앞 단계가 허용오차 안(남은 오차 ≤ 1 cm)에서 끝나면 다음 단계는 그 목표에서 시작한다.

    x 만 가는 단계에 y 가 섞이지 않는다.
    """
    node, loaded = rail_node(nodes, monkeypatch)
    try:
        node.set_goal_active(True)
        safe = node._all_safe_poses()
        node.rail.drift = (0.3, 0.005)                                        # 도착은 했지만 y 가 5 mm 남았다
        assert node.move_rail_to((0.3, 0.0), safe)
        node.rails.sent.clear()
        node.rail.drift = None
        assert node.move_rail_to((0.6, 0.0), safe)
        assert node.rails.sent and all(m.position[1] == 0.0 for m in node.rails.sent)
    finally:
        node.set_goal_active(False)
        node.stop_threads()
