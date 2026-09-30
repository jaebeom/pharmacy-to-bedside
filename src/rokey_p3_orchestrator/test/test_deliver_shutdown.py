"""트립 도중 노드를 내리면 Deliver 실행 스레드가 시한 안에 끝나는지. ROS 없이 돈다.

관측(정비, docker L2): _execute_deliver 가 _deliver_done.wait() 를 시한 없이 기다려, 적재 위치에서 벨트가 안 비어
트립이 기다리는 상태로 테스트를 끝내자 pytest 가 passed 를 찍고도 프로세스가 안 끝났다(concurrent.futures join).
"""

import threading
import time
import types

import test_goal_tokens as gt
import test_server_wait as sw

from rokey_p3_orchestrator import trip_fsm as fsm

orch = sw.orch
JOIN_LIMIT_S = 2.0


def deliver_node(orch, monkeypatch, rclpy_ok=True):
    node = gt.harness(orch, gt.trip())
    for name in ('_execute_deliver', '_run_deliver', '_abort_on_shutdown', 'close', '_to_fsm_request', '_finish',
                 '_end_goal'):
        setattr(node, name, getattr(orch.OrchestratorNode, name).__get__(node))
    node._status = {}
    node._deliver_done = threading.Event()
    node._deliver_result = None
    node._closing = threading.Event()
    node._deliver_idle = threading.Event()
    node._deliver_idle.set()
    node.rclpy_ok = {'value': rclpy_ok}
    monkeypatch.setattr(orch, 'rclpy', types.SimpleNamespace(ok=lambda: node.rclpy_ok['value']))
    return node


def goal_handle(orch):
    order = types.SimpleNamespace(order_id=gt.ORDER, patient_id=gt.PATIENT, item_id=gt.ITEM)
    request = types.SimpleNamespace(request_id='r001-0001', mode=orch.DeliveryRequest.MODE_SINGLE,
                                    destination_id='bed_a1', orders=[order])
    handle = types.SimpleNamespace(request=types.SimpleNamespace(request=request), state=None)
    handle.abort = lambda: setattr(handle, 'state', 'aborted')
    handle.succeed = lambda: setattr(handle, 'state', 'succeeded')
    return handle


def start_trip_waiting_at_load(orch, node):
    """Deliver 실행을 스레드로 띄우고 트립을 적재 위치(DOCKED_LOAD)까지 보낸다. 조제기 서버가 없어 거기서 기다린다."""
    handle = goal_handle(orch)
    out = {}
    worker = threading.Thread(target=lambda: out.update(result=node._execute_deliver(handle)), daemon=True)
    worker.start()
    for _ in range(200):
        if node._action_clients[fsm.GO_TO_ZONE].sent:
            break
        threading.Event().wait(0.01)
    [(_, response)] = node._action_clients[fsm.GO_TO_ZONE].sent
    load = gt._Handle()
    response.resolve(load)
    load.result_future.resolve(gt.result_of(orch, orch.GoalStatus.STATUS_SUCCEEDED, arrived=True, message=''))
    assert node._fsm.state == fsm.DOCKED_LOAD
    return worker, handle, out


def test_closing_the_node_mid_trip_ends_the_deliver_thread_with_abort(orch, monkeypatch):
    node = deliver_node(orch, monkeypatch)
    worker, handle, out = start_trip_waiting_at_load(orch, node)
    threading.Event().wait(3 * orch.DELIVER_POLL_S)
    assert worker.is_alive()                                           # 트립 중에는 계속 기다린다

    published = len(node.published)
    order = []
    original_abort = handle.abort
    handle.abort = lambda: (order.append('abort'), original_abort())
    node.close()                                                       # destroy_node 가 부르는 종료 경로
    order.append('close returned')                     # 이 뒤에 super().destroy_node() 가 액션 서버를 내린다
    assert order == ['abort', 'close returned']                        # abort 가 서버를 내리기 전에 나갔다
    worker.join(JOIN_LIMIT_S)
    assert not worker.is_alive()
    assert handle.state == 'aborted' and out['result'].success is False
    assert len(node.published) == published                            # 주문 상태·이벤트를 새로 내지 않는다
    assert node._fsm.state == fsm.DOCKED_LOAD                          # 종료는 리셋이 아니다


def test_rclpy_shutdown_also_ends_the_deliver_thread(orch, monkeypatch):
    node = deliver_node(orch, monkeypatch)
    worker, handle, _ = start_trip_waiting_at_load(orch, node)
    node.rclpy_ok['value'] = False                                     # SIGINT 뒤 rclpy.try_shutdown
    worker.join(JOIN_LIMIT_S)
    assert not worker.is_alive() and handle.state == 'aborted'


def test_a_finished_trip_still_succeeds_normally(orch, monkeypatch):
    node = deliver_node(orch, monkeypatch)
    worker, handle, out = start_trip_waiting_at_load(orch, node)
    with node._lock:
        node._run([fsm.Finish(True)])
    worker.join(JOIN_LIMIT_S)
    assert not worker.is_alive() and handle.state == 'succeeded' and out['result'].success is True


def test_destroy_node_closes_before_the_rclpy_node_goes_away(orch):
    import inspect
    source = inspect.getsource(orch.OrchestratorNode.destroy_node)
    assert source.index('self.close()') < source.index('super().destroy_node()')


def test_close_gives_up_waiting_after_close_wait_s_but_the_flag_is_already_set(orch, monkeypatch):
    """Deliver 실행이 안 끝나도 close 는 CLOSE_WAIT_S 에서 돌아온다.

    플래그를 먼저 켜므로 대기가 끊겨도 스레드는 풀린다.
    """
    node = deliver_node(orch, monkeypatch)
    node._deliver_idle.clear()                                         # 끝나지 않는 실행 흉내
    monkeypatch.setattr(orch, 'CLOSE_WAIT_S', 0.3)
    started = time.monotonic()
    node.close()
    assert 0.25 <= time.monotonic() - started < 1.0
    assert node._closing.is_set()



# 종료 로그 소음 ---------------------------------------------------------------------
# 정비 머지 뒤 L2(진짜 rclpy): SIGINT 한 번에도
# "abort 를 보내지 못했다: Failed get goal status array: feedback publisher is invalid" 경고가 남았다.
# rclpy 신호 처리기가 destroy_node 전에 context 를 내려 publisher 가 이미 무효다.
# 이중 SIGINT 면 close() 의 대기에서 KeyboardInterrupt traceback 이 났다.

class _Recorder:
    def __init__(self):
        self.lines = []

    def __getattr__(self, level):
        return lambda text, **kwargs: self.lines.append((level, text))


def invalid_publisher_handle():
    handle = types.SimpleNamespace(state=None)

    def abort():
        raise RuntimeError('Failed get goal status array: feedback publisher is invalid')

    handle.abort = abort
    handle.succeed = abort
    return handle


def test_invalid_publisher_during_shutdown_is_not_a_warning_or_error(orch, monkeypatch):
    for closing, context_ok in ((True, True), (False, False)):                 # close 경로, SIGINT 경로
        node = deliver_node(orch, monkeypatch, rclpy_ok=context_ok)
        log = _Recorder()
        node.get_logger = lambda log=log: log
        if closing:
            node._closing.set()
        result = node._abort_on_shutdown(invalid_publisher_handle(), 'r001-0002')
        assert result.success is False
        levels = [level for level, _ in log.lines]
        assert 'warning' not in levels and 'error' not in levels, log.lines
        assert levels == ['info', 'debug']


def test_a_publish_failure_outside_shutdown_still_raises(orch, monkeypatch):
    node = deliver_node(orch, monkeypatch, rclpy_ok=True)
    try:
        node._end_goal(invalid_publisher_handle(), 'abort')
    except RuntimeError:
        return
    raise AssertionError('종료가 아닐 때의 발행 실패를 삼켰다')


def test_close_swallows_a_second_sigint_during_the_wait(orch, monkeypatch):
    node = deliver_node(orch, monkeypatch)

    class Interrupted:
        def wait(self, timeout=None):
            raise KeyboardInterrupt()

    node._deliver_idle = Interrupted()
    node.close()                                                               # traceback 없이 돌아온다
    assert node._closing.is_set()
