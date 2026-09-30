"""M0609 보충의 끝: 홈 복귀와 결과 순서, lot_id. ROS 없이 돈다(test_reset_fence 의 노드 대역·관절 plant 를 쓴다).

관측(마클2, master02, 5d6a10b): 보충이 끝나면 팔이 slot_a_approach 에 멈췄다. at_home=false.
orchestrator 로그 "arm lot_id=lot-drug-ibu-01 (다르다. 재고는 선반 값)".

- 성공·실패: 홈에 돌아온 뒤 결과를 낸다. 결과가 나간 직후 at_home 은 true 이고 뒤따르는 복귀 스레드가 없다.
- 취소: 결과를 곧바로 낸 뒤 홈으로 간다(orchestrator drain·대체 goal 이 종결을 cancel_wait_s 까지만 기다린다).
- lot_id 는 지어내지 않는다.
"""

import threading
import time
import types

import test_reset_fence as rf

nodes = rf.nodes
HOME = (0.0,) * 6


def refill_node(nodes, monkeypatch):
    """닫힌 루프 대역. 그리퍼를 닫으면 holding 이 true 가 되고, 관절은 명령값으로 바로 간다."""
    node, m0609 = rf.m0609_harness(nodes, monkeypatch, start=HOME)
    node._max_joint_speed = 25.0                      # 한 점 0.5 rad. 테스트가 빨리 끝나게
    node._waypoint_timeout = 2.0
    node.grip = {'closed': False, 'answers': True}
    node.gripper = rf._Pub(lambda msg: node.grip.update(closed=bool(msg.data)))
    node._gripper_pub = node.gripper
    running = {'on': True}

    def holding_loop():
        while running['on']:
            with node._lock:
                node._holding.update(node.grip['closed'] and node.grip['answers'])
            time.sleep(0.02)

    threading.Thread(target=holding_loop, daemon=True).start()
    node.stop_threads = lambda: (running.update(on=False), node.stop_homing(), node.plant.stop())
    return node, m0609


def handle_for(node, item_id='drug-ibu', slot=0, **request):
    """결과를 내는 순간의 관절값·at_home·복귀 스레드를 적는 goal handle."""
    handle = types.SimpleNamespace(request=types.SimpleNamespace(item_id=item_id, slot=slot, **request),
                                   is_cancel_requested=False, state=None, at_result=None)

    def finish(state):
        handle.state = state
        handle.at_result = {'joints': node.plant.joints, 'homing': node._homing}

    handle.succeed = lambda: finish('succeeded')
    handle.abort = lambda: finish('aborted')
    handle.canceled = lambda: finish('canceled')
    handle.publish_feedback = lambda feedback: None
    return handle


def at_home_pose(joints):
    return all(abs(value) <= 0.05 for value in joints)


def test_success_returns_home_before_the_result_and_at_home_is_true_right_after(nodes, monkeypatch):
    node, _ = refill_node(nodes, monkeypatch)
    try:
        handle = handle_for(node)
        result = node._execute_refill(handle)
        assert handle.state == 'succeeded' and result.success
        assert at_home_pose(handle.at_result['joints'])                  # 결과 순간 이미 홈이다(후퇴 자세가 아니다)
        assert node.at_home() is True                                     # 결과 직후 true
        assert node._homing_thread is None and not node._homing           # 결과 뒤 복귀 스레드가 없다
        assert result.lot_id == ''                                        # 지어내지 않는다
        [done] = [e for e in node._event_pub.sent if e.name.endswith('REFILL_DONE')]
        assert done.detail == 'drug-ibu slot a'
        assert rf.frozen(node.joints, 0.2)                                # 결과 뒤 관절 명령 없음
    finally:
        node.stop_threads()


def test_failure_also_returns_home_before_the_result(nodes, monkeypatch):
    node, _ = refill_node(nodes, monkeypatch)
    try:
        node.grip['answers'] = False                                      # 잡았는데 holding 이 안 온다
        handle = handle_for(node)
        result = node._execute_refill(handle)
        assert handle.state == 'aborted' and not result.success and result.lot_id == ''
        assert at_home_pose(handle.at_result['joints'])
        assert node.at_home() is True and node._homing_thread is None
    finally:
        node.stop_threads()


def test_cancel_answers_at_once_then_goes_home(nodes, monkeypatch):
    node, _ = refill_node(nodes, monkeypatch)
    try:
        handle = handle_for(node)
        original = node.move_to

        def move_then_cancel(target, cancelled=None):
            reached = original(target, cancelled)
            if target == node._poses['slot_a_approach']:
                handle.is_cancel_requested = True                         # 슬롯 앞에서 cancel
            return reached

        node.move_to = move_then_cancel
        node._execute_refill(handle)
        assert handle.state == 'canceled'
        assert not at_home_pose(handle.at_result['joints'])               # 결과는 홈으로 가기 전에 나갔다
        assert rf.wait_until(lambda: node.at_home() is True)              # 그 뒤 홈으로 돌아왔다
    finally:
        node.stop_threads()


def test_lot_id_comes_back_only_when_the_goal_carries_one(nodes, monkeypatch):
    node, _ = refill_node(nodes, monkeypatch)
    try:
        result = node._execute_refill(handle_for(node, lot_id='lot-ibu-03'))
        assert result.lot_id == 'lot-ibu-03'
        assert node._event_pub.sent[-1].detail == 'drug-ibu slot a lot lot-ibu-03'
    finally:
        node.stop_threads()


def test_a_reset_barrier_during_the_refill_still_skips_homing(nodes, monkeypatch):
    """#78 그대로: barrier 를 지난 goal 은 결과 전에도 뒤에도 복귀 명령을 내지 않는다."""
    node, _ = refill_node(nodes, monkeypatch)
    try:
        handle = handle_for(node)
        original = node.move_to

        def move_then_reset(target, cancelled=None):
            reached = original(target, cancelled)
            if target == node._poses['shelf_approach'] and not node.fenced():
                node.on_reset_begin(2)
            return reached

        node.move_to = move_then_reset
        node._execute_refill(handle)
        assert handle.state == 'aborted'
        assert not at_home_pose(handle.at_result['joints'])
        assert rf.frozen(node.joints, 0.3) and not node._homing
    finally:
        node.stop_threads()


# 관절 한계 ------------------------------------------------------------------------

class _Recorder:
    def __init__(self):
        self.lines = []

    def __getattr__(self, level):
        return lambda text, **kwargs: self.lines.append((level, text))


def test_a_waypoint_outside_the_joint_limits_is_refused_before_any_command(nodes, monkeypatch):
    node, m0609 = refill_node(nodes, monkeypatch)
    try:
        node._limits = m0609.seq.M0609_JOINT_LIMITS
        node._poses = dict(node._poses, slot_a_insert=(1.5, 1.5, 2.8, 1.5, 1.5, 1.5))    # joint_3 150° 밖
        log = _Recorder()
        node.get_logger = lambda: log
        handle = handle_for(node)
        result = node._execute_refill(handle)
        assert handle.state == 'aborted' and not result.success
        assert node.joints.sent == [] and node.gripper.sent == []                         # 한 관절도 안 움직였다
        [error] = [text for level, text in log.lines if level == 'error']
        assert 'slot_a_insert_joints joint_3=2.8000' in error and '[-2.6180, 2.6180]' in error
        assert node.at_home() is True
    finally:
        node.stop_threads()


def test_joint_6_two_pi_apart_teach_values_run_normally_and_limits_can_be_overridden(nodes, monkeypatch):
    node, m0609 = refill_node(nodes, monkeypatch)
    try:
        node._limits = m0609.seq.M0609_JOINT_LIMITS
        for joint_6 in (3.7457, -2.5352, -3.7749):
            node._poses = dict.fromkeys(node._poses, (0.3, 0.2, 1.1, 0.0, 1.2, joint_6))
            node._event_pub.sent.clear()
            result = node._execute_refill(handle_for(node))
            assert result.success, joint_6
        node._poses = dict.fromkeys(node._poses, (0.3, 0.2, 1.1, 0.0, 1.2, 0.0))
        node._poses['slot_a_insert'] = (0.3, 0.2, 2.8, 0.0, 1.2, 0.0)                   # joint_3 150° 밖
        assert not node._execute_refill(handle_for(node)).success
        node._limits = tuple((-3.2, 3.2) for _ in range(6))                              # 파라미터로 덮으면 통과
        assert node._execute_refill(handle_for(node)).success
    finally:
        node.stop_threads()


def test_homing_to_a_home_outside_the_limits_sends_nothing(nodes, monkeypatch):
    node, m0609 = refill_node(nodes, monkeypatch)
    try:
        node._limits = m0609.seq.M0609_JOINT_LIMITS
        node._home = (0.0, 0.0, -3.0, 0.0, 0.0, 0.0)
        node.plant.joints = (0.5,) * 6
        node._left_home = True
        node.start_homing()
        assert rf.wait_until(lambda: not node._homing)
        assert node.joints.sent == []
    finally:
        node.stop_threads()


# 쥔 채 시작 ---------------------------------------------------------------------

def test_refill_opens_the_gripper_once_before_moving(nodes, monkeypatch):
    """쥔 채 종료(#113) 뒤 재기동이어도 보충은 그리퍼를 열고 시작한다. 이미 열려 있으면 무해하다."""
    node, _ = refill_node(nodes, monkeypatch)
    try:
        order = []
        node.gripper = rf._Pub(lambda msg: (order.append(('gripper', bool(msg.data))),
                                            node.grip.update(closed=bool(msg.data))))
        node._gripper_pub = node.gripper
        node.joints._on_publish = (lambda plant_command: (lambda msg: (order.append(('joint', None)),
                                                                     plant_command(msg))))(node.joints._on_publish)
        node.grip['closed'] = True                                         # 쥔 채 시작
        node._gripper_closed = True
        result = node._execute_refill(handle_for(node))
        assert result.success
        assert order[0] == ('gripper', False)                              # 첫 명령이 열기다(관절보다 먼저)
        assert [value for kind, value in order if kind == 'gripper'] == [False, True, False]
    finally:
        node.stop_threads()


def test_starting_with_holding_true_warns_once_and_does_not_open(nodes, monkeypatch):
    node, _ = refill_node(nodes, monkeypatch)
    try:
        log = _Recorder()
        node.get_logger = lambda: log
        node._on_holding(types.SimpleNamespace(data=True))
        node._on_holding(types.SimpleNamespace(data=True))
        warnings = [text for level, text in log.lines if level == 'warn']
        assert warnings == ['쥔 채 시작했다(gripper/holding=true). 다음 보충은 그리퍼를 열고 시작한다.']
        assert node.gripper.sent == []                                    # 기동 때 스스로 열지 않는다
        node.stop_threads()

        node, _ = refill_node(nodes, monkeypatch)
        log = _Recorder()
        node.get_logger = lambda: log
        node._on_holding(types.SimpleNamespace(data=False))
        node._on_holding(types.SimpleNamespace(data=True))                 # 첫 값이 false 면 경고 없음
        assert [text for level, text in log.lines if level == 'warn'] == []
    finally:
        node.stop_threads()

