"""L2 한 바퀴 테스트가 트립을 시작하기 전에 발견을 확인한다. 안 되면 그 자리에서 그래프를 싣고 실패한다.

9/17 CI 에서 test_stub_loop 가 두 번 "90.0 s 안에 Deliver 결과가 오지 않았다" 로 실패했다. 로그는 노드가 전부 up 인데
order_generator 가 같은 프로세스의 orchestrator /deliver 를 90 s 동안 못 봤다(발견 실패). 트립 시한 실패와 구별되게
발견만 따로, 짧게 기다린다. 발견이 늦을 뿐이면 기다리는 동안 붙고 테스트는 그대로 돈다.

클라이언트의 server_is_ready() 를 직접 본다(그 노드가 실제로 서버를 봤는지). 노드 내부 속성 이름
(order_generator._client, orchestrator._action_clients·_dispense·_sim_reset)에 기대므로 이름이 바뀌면 여기서 실패한다.
"""

import os
import threading
import time

from rclpy.action import get_action_names_and_types

DISCOVERY_TIMEOUT_S = 20.0

#: 이 pytest 프로세스에서 wait_for_discovery 를 부른 테스트와 그때의 /dev/shm fastrtps 세그먼트 수
#: (앞선 L2 가 남긴 것 추적).
HISTORY = []


def shm_segments():
    """/dev/shm 의 Fast DDS 공유메모리 세그먼트 수. 볼 수 없으면 None."""
    try:
        return sum(1 for name in os.listdir('/dev/shm') if 'fastrtps' in name or 'fast_datasharing' in name)
    except OSError:
        return None


def client_checks(nodes):
    """(설명, server_is_ready 함수) 목록. 있는 노드만."""
    checks = []
    generator, orchestrator = nodes.get('generator'), nodes.get('orchestrator')
    if generator is not None:
        checks.append(('order_generator → /deliver', generator._client.server_is_ready))
    if orchestrator is not None:
        for name, client in orchestrator._action_clients.items():
            checks.append((f'orchestrator → {name} 액션', client.server_is_ready))
        checks.append(('orchestrator → /pharmacy/dispense', orchestrator._dispense.service_is_ready))
        checks.append(('orchestrator → /sim/reset', orchestrator._sim_reset.service_is_ready))
    return checks


def graph_snapshot(node):
    names = sorted(f'{namespace.rstrip("/")}/{name}' for name, namespace in node.get_node_names_and_namespaces())
    actions = sorted(name for name, _ in get_action_names_and_types(node))
    services = sorted(name for name, _ in node.get_service_names_and_types()
                      if not name.split('/')[-1].startswith(('describe_parameters', 'get_parameter', 'list_parameters',
                                                             'set_parameters', 'get_type_description', '_action')))
    return f'노드 {names}\n액션 {actions}\n서비스 {services}'


def wait_for_discovery(nodes, timeout_s=DISCOVERY_TIMEOUT_S, checks=None):
    """모든 클라이언트가 서버를 볼 때까지 기다린다. 걸린 시간(s)을 돌려준다. 시한을 넘으면 AssertionError."""
    checks = client_checks(nodes) if checks is None else checks
    HISTORY.append((os.environ.get('PYTEST_CURRENT_TEST', '?').split(' ')[0], shm_segments()))
    started = time.monotonic()
    while True:
        missing = [label for label, ready in checks if not ready()]
        if not missing:
            return time.monotonic() - started
        if time.monotonic() - started >= timeout_s:
            node = next(iter(nodes.values()))
            raise AssertionError(f'{timeout_s:g} s 안에 발견되지 않았다(트립 전, DDS 발견 실패): {missing}\n'
                                 f'{graph_snapshot(node)}')
        time.sleep(0.05)


class ReadyWatch:
    """트립을 기다리는 동안 generator 의 /deliver 클라이언트가 서버를 보는지 1 s 마다 두 스레드에서 적는다.

    9/17 main CI 에서 wait_for_discovery 는 통과했는데
    order_generator 타이머는 90 s 내내 "/deliver 서버를 기다린다" 였다.
    - 'executor': generator 노드에 붙인 1 s 타이머 콜백(generator 의 _tick 과 같은 executor 스레드 풀)에서 묻는다.
    - 'test': 테스트 스레드(fixture 의 대기 루프)에서 묻는다.
    둘 다 같은 객체 generator._client 에 묻고 id 를 남긴다. 결과가 없으면 report() 를 실패 메시지에 싣는다.
    """

    def __init__(self, generator, observer=None):
        self._generator = generator
        self._observer = observer or generator
        self._client = generator._client
        self._started = time.monotonic()
        self._lock = threading.Lock()
        self._last_test = 0.0
        self.samples = []          # (경과 s, 'executor'|'test', 스레드 이름, ready, id(client), 그래프 상태)
        self._timer = generator.create_timer(1.0, lambda: self._record('executor'))

    def _record(self, where):
        ready = self._client.server_is_ready()
        graph = deliver_graph(self._observer) if where == 'test' else None
        with self._lock:
            self.samples.append((round(time.monotonic() - self._started, 1), where,
                                 threading.current_thread().name, ready, id(self._client), graph))

    def sample_from_test_thread(self):
        """테스트 스레드 대기 루프에서 자주 불러도 1 s 에 한 번만 적는다."""
        now = time.monotonic()
        if now - self._last_test >= 1.0:
            self._last_test = now
            self._record('test')

    def stop(self):
        self._generator.destroy_timer(self._timer)

    def report(self, discovery_s=None):
        with self._lock:
            samples = list(self.samples)
        lines = [f'wait_for_discovery 통과까지 {discovery_s:.2f} s' if discovery_s is not None else '']
        lines.append(f'generator._client id={id(self._client)} (fixture 와 generator 가 같은 객체: '
                     f'{self._client is self._generator._client})')
        for where in ('executor', 'test'):
            mine = [s for s in samples if s[1] == where]
            ready = [s[0] for s in mine if s[3]]
            lines.append(f'{where}: 표본 {len(mine)}, ready {len(ready)}, 처음 ready {ready[0] if ready else None} s, '
                         f'마지막 ready {ready[-1] if ready else None} s, 스레드 {sorted({s[2] for s in mine})}')
        lines.append(f'마지막 표본 12개(경과 s, 어디, 스레드, ready): {[s[:4] for s in samples[-12:]]}')
        graphs = [(s[0], s[5]) for s in samples if s[5] is not None]
        lines.append(f'/deliver 그래프(경과 s, status pub, feedback pub, send_goal 서비스) 처음·마지막: '
                     f'{graphs[:1] + graphs[-1:]}')
        lines.append(f'/dev/shm fastrtps 세그먼트 지금 {shm_segments()}. '
                     f'이 프로세스의 앞선 L2(테스트, 그때 세그먼트): {HISTORY}')
        lines.append(graph_dump(self._observer))
        return '\n'.join(line for line in lines if line)


def action_graph(node, action):
    """그래프에 액션 서버 엔티티가 있는지: (status 발행자 수, feedback 발행자 수, send_goal 서비스 있음)."""
    try:
        services = {name for name, _ in node.get_service_names_and_types()}
        return (node.count_publishers(f'{action}/_action/status'),
                node.count_publishers(f'{action}/_action/feedback'),
                f'{action}/_action/send_goal' in services)
    except Exception as error:
        return f'조회 실패: {error}'


def deliver_graph(node):
    return action_graph(node, '/deliver')


def missing_server_report(node, action):
    """발견 확인 뒤 서버를 놓쳤을 때 실패 메시지에 싣는 것: 그 액션의 그래프 엔티티, 그래프, /dev/shm, 앞선 L2."""
    return (f'{action} 그래프(status pub, feedback pub, send_goal 서비스): {action_graph(node, action)}\n'
            f'{graph_snapshot(node)}\n'
            f'/dev/shm fastrtps 세그먼트 지금 {shm_segments()}. '
            f'이 프로세스의 앞선 L2(테스트, 그때 세그먼트): {HISTORY}')


def graph_dump(node):
    """ros2 action list·ros2 node info /orchestrator·/order_generator 에 해당하는 rclpy 그래프."""
    from rclpy.action import get_action_client_names_and_types_by_node, get_action_server_names_and_types_by_node
    parts = [graph_snapshot(node)]
    for name, getter in (('orchestrator', get_action_server_names_and_types_by_node),
                         ('order_generator', get_action_client_names_and_types_by_node)):
        try:
            actions = sorted(action for action, _ in getter(node, name, '/'))
        except Exception as error:          # 노드가 그래프에서 안 보이면 예외다
            actions = f'조회 실패: {error}'
        try:
            services = sorted(service for service, _ in node.get_service_names_and_types_by_node(name, '/')
                              if '_action' in service)
        except Exception as error:
            services = f'조회 실패: {error}'
        parts.append(f'/{name}: 액션 {actions}, 액션 내부 서비스 {services}')
    return '\n'.join(parts)
