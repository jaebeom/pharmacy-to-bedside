"""UR5 `PickPouch` 의 `gripper_observation: state` 경로(계약 11.6 GripperState·GripperCommand seq 규칙).

기본 경로(bool)는 `test_ur5_pick_characterization.py` 가 고정하고, 그쪽 결함 후보 시험은 그대로 둔다.
여기서는 opt-in 경로에서 그 결함 후보가 해소되는지와 seq 규칙을 본다. Rig 는 특성 시험 것을 빌리고,
GripperCommand 에 반응해 GripperState 를 내는 가짜 흡착 plant 를 붙인다. 실제 흡착·해제는 L3(미실행)다.
"""

import importlib.util
import time
import types

import test_reset_fence as rf
import test_ur5_pick_characterization as ch

nodes = rf.nodes
ORDER = ch.ORDER


def _now_msg():
    if importlib.util.find_spec('builtin_interfaces') is not None:
        from builtin_interfaces.msg import Time
        return Time(sec=100, nanosec=0)
    return None


class GripperPlant:
    """isaac 흉내. 명령을 적용하면 last_applied 를 올리고 state 를 바꾼다.

    tick 마다 물리 seq 를 올려 GripperState 를 낸다.
    """

    def __init__(self, rig, state):
        self.rig, self.state, self.applied, self.seq = rig, state, 0, 0
        self.applies = True        # 명령을 적용하나
        self.catches = True        # 닫으면 붙나(miss 면 RELEASED 로 남는다)
        self.opens = True          # 열면 떨어지나
        self.alive = True          # GripperState 를 계속 내나
        self.epoch = 1
        self.commands = []

    def command(self, message):
        self.commands.append((message.epoch, message.command_seq, message.close))
        if not self.applies or message.epoch != self.epoch or message.command_seq <= self.applied:
            return
        self.applied = message.command_seq
        held, released = self.rig.arm.GripperState.STATE_HELD, self.rig.arm.GripperState.STATE_RELEASED
        if message.close:
            self.state = held if self.catches else released
        elif self.opens:
            self.state = released
        self.tick()

    def tick(self):
        if not self.alive:
            return
        self.seq += 1
        self.rig.node._on_gripper_state(types.SimpleNamespace(epoch=self.epoch, seq=self.seq, state=self.state,
                                                              last_applied_command_seq=self.applied))


class StateRig(ch.Rig):
    def __init__(self, arm, monkeypatch):
        super().__init__(arm, monkeypatch)
        node = self.node
        for name in ('_publish_gripper_command', '_on_gripper_state'):
            setattr(node, name, getattr(arm.ArmNode, name).__get__(node))
        node._epoch = 1
        node._gripper_view = arm.clear_state.GripperView(arm.STALE_STATUS_S, arm.GripperState.STATE_HELD,
                                                         arm.GripperState.STATE_RELEASED)
        node._command_seq = arm.clear_state.CommandSeq()
        node._last_command = None
        node.get_clock = lambda: types.SimpleNamespace(now=lambda: types.SimpleNamespace(to_msg=_now_msg))
        self.plant = GripperPlant(self, arm.GripperState.STATE_RELEASED)
        node._gripper_command_pub = rf._Pub(self.plant.command)
        self.plant_follows = False                 # Bool plant 는 끈다. state 모드는 Bool holding 을 보지 않는다
        base_wait = node.wait

        def wait(sim_seconds, cancelled=None):
            self.plant.tick()
            return base_wait(sim_seconds, cancelled)

        node.wait = wait

    def ready(self):
        self.base(True)
        self.belt(True, ORDER)
        self.pouches(ORDER)
        self.plant.tick()


def rig(nodes, monkeypatch):
    arm, _ = nodes
    return StateRig(arm, monkeypatch), arm


def test_state_path_ok_sends_seq_commands_on_both_topics(nodes, monkeypatch):
    r, arm = rig(nodes, monkeypatch)
    r.ready()
    handle, result = r.execute(ch._goal(arm, 'belt', 0))
    assert result.outcome == 'ok' and handle.state == 'succeeded'
    assert r.names() == [arm.Event.PICK_ATTEMPT, arm.Event.POUCH_PICKED, arm.Event.POUCH_LOADED]
    # 같은 값이 Bool 과 GripperCommand 에 나간다. command_seq 는 epoch 1 에서 1 부터.
    assert r.gripper_commands() == [False, True, False]
    assert r.plant.commands == [(1, 1, False), (1, 2, True), (1, 3, False)]


def test_held_from_before_the_close_command_is_not_a_grasp(nodes, monkeypatch):
    # #246 의 결함 후보(bool 경로에서는 그대로 고정)가 state 경로에서 해소된다: 명령 전의 HELD 는 PENDING 이다.
    r, arm = rig(nodes, monkeypatch)
    r.plant.state = arm.GripperState.STATE_HELD
    r.plant.applies = False                                     # isaac 이 명령을 적용하지 않는다
    r.ready()
    handle, result = r.execute(ch._goal(arm, 'belt', 0))
    assert result.outcome == 'timeout' and handle.state == 'aborted'
    assert arm.Event.POUCH_PICKED not in r.names()


def test_close_applied_but_released_is_grasp_failed(nodes, monkeypatch):
    r, arm = rig(nodes, monkeypatch)
    r.plant.catches = False                                     # 닫았지만 닿는 봉투가 없다(miss 도 적용이다)
    r.ready()
    _handle, result = r.execute(ch._goal(arm, 'belt', 0))
    assert result.outcome == 'grasp_failed'
    assert arm.Event.POUCH_PICKED not in r.names()


def test_released_after_the_close_was_applied_is_a_drop(nodes, monkeypatch):
    r, arm = rig(nodes, monkeypatch)
    r.ready()

    def drop():
        r.plant.state = arm.GripperState.STATE_RELEASED
        r.plant.tick()                                          # isaac 은 계속 낸다(10 Hz)

    r.on_move[3] = drop
    _handle, result = r.execute(ch._goal(arm, 'belt', 0))
    assert result.outcome == 'dropped'
    assert r.names() == [arm.Event.PICK_ATTEMPT, arm.Event.POUCH_PICKED]


def test_lost_gripper_state_mid_transfer_is_not_a_drop_and_stops(nodes, monkeypatch):
    # bool 경로의 결함 후보(unknown 이면 이송 계속)가 state 경로에서 해소된다: 관측 소실이면 멈춘다.
    r, arm = rig(nodes, monkeypatch)
    r.ready()

    def lose():
        r.plant.alive = False
        with r.node._lock:
            r.node._gripper_view.clear()

    r.on_move[3] = lose
    _handle, result = r.execute(ch._goal(arm, 'belt', 0))
    assert result.outcome == 'timeout'
    assert arm.Event.POUCH_LOADED not in r.names()
    assert len(r.poses) == 4                                    # 놓기 자세로 가지 않았다


def test_release_not_applied_gives_no_loaded(nodes, monkeypatch):
    # bool 경로의 결함 후보(해제 뒤 0.3 s 대기만으로 LOADED)가 state 경로에서 해소된다.
    r, arm = rig(nodes, monkeypatch)
    r.ready()
    r.on_move[4] = lambda: setattr(r.plant, 'applies', False)   # 놓기 자세부터 isaac 이 명령을 적용하지 않는다
    _handle, result = r.execute(ch._goal(arm, 'belt', 0))
    assert result.outcome == 'timeout'
    assert arm.Event.POUCH_LOADED not in r.names()


def test_release_applied_but_still_held_gives_no_loaded(nodes, monkeypatch):
    r, arm = rig(nodes, monkeypatch)
    r.plant.opens = False                                       # 열기를 적용했는데 HELD 로 남는다
    r.ready()
    _handle, result = r.execute(ch._goal(arm, 'belt', 0))
    assert result.outcome == 'timeout'
    assert arm.Event.POUCH_LOADED not in r.names()


def test_unknown_epoch_sends_no_command_and_times_out(nodes, monkeypatch):
    r, arm = rig(nodes, monkeypatch)
    r.node._epoch = 0                                           # /events 를 하나도 못 받았다
    r.ready()
    _handle, result = r.execute(ch._goal(arm, 'belt', 0))
    assert r.plant.commands == []
    assert result.outcome == 'timeout'
    assert arm.Event.POUCH_PICKED not in r.names()


def test_gripper_state_of_another_epoch_is_ignored(nodes, monkeypatch):
    r, arm = rig(nodes, monkeypatch)
    r.plant.epoch = 5                                           # isaac 은 다른 epoch 에 있다
    r.ready()
    _handle, result = r.execute(ch._goal(arm, 'belt', 0))
    assert result.outcome == 'timeout'
    assert arm.Event.POUCH_PICKED not in r.names()


def test_command_seq_restarts_at_one_after_reset_done(nodes, monkeypatch):
    r, arm = rig(nodes, monkeypatch)
    r.node._publish_gripper_command(True)
    r.node._publish_gripper_command(False)
    with r.node._lock:
        r.node._fence.begin(2)
        r.node._fence.done(2)
        r.node._command_seq.reset()                             # on_reset 이 하는 일(계약 11.6)
    r.node._epoch = 2
    r.node._publish_gripper_command(True)
    assert r.plant.commands == [(1, 1, True), (1, 2, False), (2, 1, True)]


def test_state_mode_timeouts_are_bounded_by_the_action_deadline(nodes, monkeypatch):
    # 관측 소실로 기다려도 계약 7절 시한(60 s sim) 안에서 끝난다.
    r, arm = rig(nodes, monkeypatch)
    r.plant.applies = False
    r.ready()
    start, wall = r.clock, time.monotonic()
    r.execute(ch._goal(arm, 'belt', 0))
    assert 59.0 <= r.clock - start <= 61.0
    assert time.monotonic() - wall < 30.0
