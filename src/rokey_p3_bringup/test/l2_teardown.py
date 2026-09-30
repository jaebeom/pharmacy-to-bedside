"""L2 fixture 가 노드를 내리는 순서와, 앞 테스트가 남긴 액션 엔티티 확인.

rclpy 의 destroy_node 는 액션 서버·클라이언트(waitable)를 없애지 않는다. 그 파이썬 객체가 살아 있는 동안
노드와 participant 가 살아서 그래프에 남고 서버도 계속 보인다(순환 참조라 gc 가 돌 때까지).
9/18 #168 CI 에서 test_stub_arm_m0609 가 앞 테스트들이 남긴 /m0609/refill 서버 9개와 겹쳐 실패했다
(status pub 10, /dev/shm 세그먼트가 L2 테스트마다 8 씩 늘어 80). #181 이 이 도우미를 넣었다.

teardown_nodes 의 순서(9/18 외부 검토 #185 A3 Q3-4 를 따름)
1. 협력 종료: close() 가 있는 노드(orchestrator·arm·m0609_arm·event_logger, 모두 여러 번 불러도 된다)의 close.
   새 요청을 막고 진행 중 실행이 abort 로 빠져나오게 한다. context 와 executor 는 아직 살아 있다.
2. 진행 중 goal 이 끝나기를 goal_wait_s 까지 기다린다(executor 가 아직 돈다).
3. executor.shutdown, spin 스레드 join, MultiThreadedExecutor 의 작업 스레드 join. 하나라도 살아 있으면 여기서 실패한다.
   살아 있는 callback 아래에서 handle 을 없애지 않는다(그 자원은 남고, 다음 fixture 의 assert_no_leftovers 도 잡는다).
   rclpy 7.1.11(Jazzy) 의 Executor.shutdown 은 _is_shutdown 을 켠 뒤 `if not self._is_shutdown` 으로 대기를 건너뛰어
   진행 중 callback 을 기다리지 않는다. MultiThreadedExecutor 는 이를 덮어쓰지 않아 작업 스레드(ThreadPoolExecutor)의
   callback 이 spin 스레드가 끝난 뒤에도 돈다(9/18 정비 docker 확인). 그래서 작업 스레드를 직접 join 한다(비공개 속성).
4. 노드마다 handle 이 살아 있는 ActionServer·ActionClient 만 destroy(액션 타입만 본다. Waitable 일반에 destroy 를
   가정하지 않는다). destroy 는 node.waitables 에서 자기를 빼므로 두 번 부르지 않는다. 노드가 뒤에 자기 액션 엔티티를
   destroy 하게 되면(9/21 뒤 과제) 그쪽도 handle 이 살아 있을 때만 부른다.
5. destroy_node, try_shutdown. gc.collect 는 정리 뒤 확인용이다.
2 에서 끝나지 않은 goal 이 있었으면 5 까지 마친 뒤 목록을 싣고 실패한다.

assert_no_leftovers: fixture 가 rclpy.init 전에 부른다. 이 프로세스에서 handle 이 아직 살아 있는 액션 서버·클라이언트를
**gc 전에** 먼저 센다. 명시 정리가 빠져 자동 gc 로만 치워질 것도 실패로 잡으려는 것이다.
목록에는 gc 뒤에도 남는 것을 함께 적는다.
그래프가 아니라 이 프로세스의 객체를 보므로 같은 도메인의 다른 프로세스(colcon 이 동시에 돌리는 다른 패키지 테스트,
띄워 둔 launch)와 헷갈리지 않는다. 객체 검사라 native 자원이 모두 내려갔다는 증명은 아니다.
"""

import gc
import time

import rclpy
from rclpy.action import ActionClient, ActionServer
from rclpy.exceptions import InvalidHandle

GOAL_WAIT_S = 5.0
JOIN_TIMEOUT_S = 5.0


def _handle(entity):
    return entity._handle if isinstance(entity, ActionServer) else entity._client_handle


def _alive(entity):
    try:
        with _handle(entity):
            return True
    except InvalidHandle:
        return False


def _describe(entity):
    name = getattr(entity, '_action_name', None) or getattr(entity._action_type, '__name__', '?')
    return f'{type(entity._node).__name__}: {type(entity).__name__} {name}'


def _action_entities(node):
    return [w for w in list(node.waitables) if isinstance(w, (ActionServer, ActionClient))]


def active_goals(nodes):
    """아직 끝나지 않은 서버 goal: ['노드 클래스: goal id 앞 8자 상태', ...]."""
    found = []
    for node in nodes:
        for server in _action_entities(node):
            if isinstance(server, ActionServer) and _alive(server):
                for goal_handle in list(server._goal_handles.values()):
                    if goal_handle.is_active:
                        found.append(f'{type(node).__name__}: goal {bytes(goal_handle.goal_id.uuid).hex()[:8]} '
                                     f'status {goal_handle.status}')
    return found


def teardown_nodes(executor, thread, nodes, goal_wait_s=GOAL_WAIT_S):
    """nodes 는 executor 에 붙은 노드 전부(순서대로 내린다). 순서는 모듈 docstring.

    이름을 teardown 으로 하면 import 한 테스트 파일마다 pytest 가 모듈 teardown 으로 불러 버린다.
    """
    for node in nodes:
        close = getattr(node, 'close', None)
        if callable(close):
            close()
    deadline = time.monotonic() + goal_wait_s
    while active_goals(nodes) and time.monotonic() < deadline:
        time.sleep(0.05)
    unfinished = active_goals(nodes)

    executor.shutdown()
    deadline = time.monotonic() + JOIN_TIMEOUT_S
    threads = [thread] if thread is not None else []
    pool = getattr(executor, '_executor', None)                # MultiThreadedExecutor 의 ThreadPoolExecutor
    if pool is not None:
        pool.shutdown(wait=False)                              # 새 작업을 받지 않고, 쉬는 작업 스레드는 끝난다
        threads += list(pool._threads)
    for worker in threads:
        worker.join(timeout=max(0.0, deadline - time.monotonic()))
    alive = [worker.name for worker in threads if worker.is_alive()]
    if alive:
        raise AssertionError(f'executor 스레드 {alive} 가 {JOIN_TIMEOUT_S:g} s 안에 안 끝났다. '
                             '살아 있는 callback 아래에서 handle 을 없애지 않으려고 노드를 내리지 않고 멈춘다. '
                             f'끝나지 않은 goal: {unfinished}')
    for node in nodes:
        for entity in _action_entities(node):
            if _alive(entity):
                entity.destroy()
        node.destroy_node()
    rclpy.try_shutdown()
    gc.collect()
    assert not unfinished, (f'협력 종료(close) 뒤 {goal_wait_s:g} s 안에 끝나지 않은 goal 이 있었다. '
                            f'executor 는 그 callback 이 끝나기를 기다린 뒤 내렸다: {unfinished}')


def leftover_action_entities(collect=True):
    """이 프로세스에서 handle 이 아직 살아 있는 액션 서버·클라이언트. collect 면 gc 뒤에 센다."""
    if collect:
        gc.collect()
    return sorted(_describe(obj) for obj in gc.get_objects()
                  if isinstance(obj, (ActionServer, ActionClient)) and _alive(obj))


def assert_no_leftovers():
    before_gc = leftover_action_entities(collect=False)
    if not before_gc:
        return
    after_gc = leftover_action_entities(collect=True)
    raise AssertionError('앞 테스트가 내리지 않은 액션 서버·클라이언트가 이 프로세스에 남아 있다. '
                         '그 노드·participant 가 그래프에 남아 같은 이름의 서버가 겹친다. '
                         f'그 fixture 가 l2_teardown.teardown_nodes 를 쓰는지 본다. gc 전 {before_gc}, gc 뒤 {after_gc}'
                         '(gc 뒤 0 이면 명시 정리가 빠져 자동 gc 로만 치워질 것이었다)')
