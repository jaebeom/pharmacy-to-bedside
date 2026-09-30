"""노드를 내리면(close·destroy_node) 팔 노드의 액션 실행·홈 복귀가 시한 안에 멈추는지. ROS 없이 돈다.

#111(orchestrator Deliver)과 같은 규칙: 종료는 리셋이 아니다. 새 이벤트 없이 goal 을 abort 하고
관절·그리퍼 명령을 더 내지 않는다. M0609 는 캐니스터를 쥔 채 멈출 수 있지만 그리퍼를 열지 않는다.
전에는 destroy_node 만으로는 안 풀리고 rclpy 종료·취소·sim 시한(60·90 s)·/clock 정지를 기다렸다.
"""

import inspect
import threading
import time
import types

import test_m0609_refill_finish as rf_finish
import test_reset_fence as rf

nodes = rf.nodes
JOIN_LIMIT_S = 2.0


def test_closing_m0609_mid_refill_aborts_quickly_and_keeps_the_gripper(nodes, monkeypatch):
    node, _ = rf_finish.refill_node(nodes, monkeypatch)
    try:
        node._max_joint_speed = 0.5                                        # 0.5 rad/s. 한 자세에 1 s 넘게 걸린다
        handle = rf_finish.handle_for(node)
        worker = threading.Thread(target=node._execute_refill, args=(handle,), daemon=True)
        worker.start()
        assert rf.wait_until(lambda: node.grip['closed'], limit=15.0)       # 잡았다. 들어 올리는 중
        time.sleep(0.2)
        events = len(node._event_pub.sent)
        grip_commands = len(node.gripper.sent)

        node.close()                                                       # destroy_node 가 부르는 종료 경로
        worker.join(JOIN_LIMIT_S)
        assert not worker.is_alive()
        assert handle.state == 'aborted'
        assert rf.frozen(node.joints, 0.3)                                  # 관절 명령을 더 내지 않는다
        assert len(node.gripper.sent) == grip_commands and node.grip['closed']   # 열지 않는다(쥔 채)
        assert len(node._event_pub.sent) == events                          # REFILL_DONE 등 새 이벤트 없음
        assert node._homing_thread is None or not node._homing_thread.is_alive()
    finally:
        node.stop_threads()


def test_closing_m0609_stops_the_homing_thread(nodes, monkeypatch):
    node, _ = rf.m0609_harness(nodes, monkeypatch, start=(1.5,) * 6)
    try:
        node._max_joint_speed = 0.3
        node._left_home = True
        node.start_homing()
        assert rf.wait_until(lambda: len(node.joints.sent) >= 3)
        thread = node._homing_thread
        node.close()
        thread.join(JOIN_LIMIT_S)
        assert not thread.is_alive() and not node._homing
        assert rf.frozen(node.joints, 0.3)
        node.start_homing()                                                 # 종료 뒤에는 다시 안 간다
        assert node._homing_thread is thread
    finally:
        node.plant.stop()


def test_closing_ur5_mid_pick_aborts_without_events_and_stops_homing(nodes, monkeypatch):
    node, arm = rf.ur5_harness(nodes, monkeypatch, start=(1.0,) * 6)
    try:
        # 홈 복귀 타이머 중 close → 복귀가 멈추고 ARM_HOME 없음
        node._max_joint_speed = 0.3
        node.start_homing()
        assert rf.wait_until(lambda: len(node.joints.sent) >= 3)
        node.close()
        assert rf.wait_until(lambda: not node.homing(), limit=JOIN_LIMIT_S)
        assert rf.frozen(node.joints, 0.3)
        assert all(event.name != arm.Event.ARM_HOME for event in node._event_pub.sent)

        # PickPouch 실행이 대기 중 close → abort(outcome timeout), 새 이벤트·홈 복귀 없음
        node._closing.clear()
        handle = types.SimpleNamespace(request=types.SimpleNamespace(order_id='ord-0001'),
                                       is_cancel_requested=False, state=None)
        handle.succeed = lambda: setattr(handle, 'state', 'succeeded')
        handle.abort = lambda: setattr(handle, 'state', 'aborted')
        handle.canceled = lambda: setattr(handle, 'state', 'canceled')

        def run_pick_waiting(goal_handle, generation):
            node.publish_event(arm.Event.PICK_ATTEMPT)
            while node.wait(0.05):                                          # 검출을 기다리는 흉내
                pass
            return node._stopped_outcome(goal_handle, float('inf'), arm.perm.OUTCOME_NOT_DETECTED, '대기')

        node._run_pick = run_pick_waiting
        out = {}
        worker = threading.Thread(target=lambda: out.update(result=node._execute_pick(handle)), daemon=True)
        timers = len(node.timers)
        worker.start()
        assert rf.wait_until(lambda: node._event_pub.sent and node.goal_active())
        events = len(node._event_pub.sent)
        node.close()
        worker.join(JOIN_LIMIT_S)
        assert not worker.is_alive() and handle.state == 'aborted'
        assert out['result'].outcome == arm.perm.OUTCOME_TIMEOUT and out['result'].success is False
        assert len(node._event_pub.sent) == events and len(node.timers) == timers
        node.set_goal_active(True)
        assert node.send_joint_command(arm.np.full(6, 0.5)) is False
        node.set_gripper(False)
        assert node.gripper.sent == []
    finally:
        node.set_goal_active(False)
        node.plant.stop()


def test_destroy_node_closes_before_the_rclpy_node_goes_away(nodes):
    arm, m0609 = nodes
    for cls in (arm.ArmNode, m0609.M0609ArmNode):
        source = inspect.getsource(cls.destroy_node)
        assert source.index('self.close()') < source.index('super().destroy_node()'), cls.__name__


def test_each_close_guard_on_its_own(nodes, monkeypatch):
    """겹친 방어라 위 흐름 테스트만으로는 어느 한 곳이 빠져도 모른다. 각 문을 따로 본다."""
    m0609_node, m0609 = rf.m0609_harness(nodes, monkeypatch, start=(0.5,) * 6)
    ur5_node, arm = rf.ur5_harness(nodes, monkeypatch, start=(0.5,) * 6)
    try:
        for node, event_name in ((m0609_node, m0609.Event.REFILL_DONE), (ur5_node, arm.Event.ARM_HOME)):
            node.close()
            started = time.monotonic()
            assert node.wait(10.0) is False and time.monotonic() - started < 0.5      # 대기는 곧바로 끝난다
            node.set_goal_active(True)
            assert node.send_joint_command((0.1,) * 6) is False                        # 관절 명령 없음
            node.set_goal_active(False)
            node.set_gripper(False)
            assert node.gripper.sent == []                                             # 그리퍼 명령 없음(열지 않는다)
            node.publish_event(event_name)
            assert node._event_pub.sent == []                                          # 이벤트 없음
            assert node._homing_stopped() is True                                      # 복귀 루프가 멈춘다
            assert node.joints.sent == []
    finally:
        m0609_node.plant.stop()
        ur5_node.plant.stop()


# 종료 로그 소음 ---------------------------------------------------------------------
# 정비 머지 뒤 L2(진짜 rclpy): m0609_arm 이 SIGINT 에서
# "[ERROR] Error raised in execute callback: Failed get goal status array: feedback publisher is invalid"
# + RCLError traceback 을 냈다(두 트리 모두). 실행 콜백이 무효 goal_handle 을 닫았다.

class _Recorder:
    def __init__(self):
        self.lines = []

    def __getattr__(self, level):
        return lambda text, **kwargs: self.lines.append((level, text))


def _raise_invalid():
    raise RuntimeError('Failed get goal status array: feedback publisher is invalid')


def test_end_goal_is_quiet_only_while_shutting_down(nodes, monkeypatch):
    m0609_node, _ = rf.m0609_harness(nodes, monkeypatch, start=(0.0,) * 6)
    ur5_node, _ = rf.ur5_harness(nodes, monkeypatch, start=(0.0,) * 6)
    try:
        for node in (m0609_node, ur5_node):
            handle = types.SimpleNamespace(abort=_raise_invalid, succeed=_raise_invalid, canceled=_raise_invalid)
            try:
                node._end_goal(handle, 'abort')                                   # 종료가 아니면 그대로 올린다
                raise AssertionError('종료가 아닐 때의 발행 실패를 삼켰다')
            except RuntimeError:
                pass
            log = _Recorder()
            node.get_logger = lambda log=log: log
            node._closing.set()
            for how in ('abort', 'succeed', 'canceled'):
                node._end_goal(handle, how)
            assert [level for level, _ in log.lines] == ['debug'] * 3

            def interrupted(limit_s=2.0):
                raise KeyboardInterrupt()

            node.stop_homing = interrupted
            node.close()                                                          # 이중 SIGINT 도 traceback 없음
    finally:
        m0609_node.plant.stop()
        ur5_node.plant.stop()


def test_m0609_refill_on_a_dead_context_ends_without_warning_or_error(nodes, monkeypatch):
    """SIGINT 경로: rclpy 신호 처리기가 context 를 먼저 내렸고 close 는 아직이다. 보충이 멈추고 조용히 닫힌다."""
    node, m0609 = rf_finish.refill_node(nodes, monkeypatch)
    try:
        monkeypatch.setattr(m0609, 'rclpy', types.SimpleNamespace(ok=lambda: False))
        log = _Recorder()
        node.get_logger = lambda: log
        handle = rf_finish.handle_for(node)
        handle.abort = _raise_invalid
        result = node._execute_refill(handle)
        assert result.success is False
        levels = [level for level, _ in log.lines]
        assert 'warn' not in levels and 'error' not in levels, log.lines
        assert any(level == 'info' and '노드 종료(shutdown)' in text for level, text in log.lines)
    finally:
        node.stop_threads()
