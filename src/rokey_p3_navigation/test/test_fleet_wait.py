"""fleet 의 결과 대기가 cancel 종결 대기 뒤에 끝나는가(결함 후보 F2).

`fleet_node` 는 nav2_msgs 를 import 한다. nav2_msgs 가 없는 환경(Mac, 설치 전 CI 이미지)에서는 건너뛴다.
"""

import importlib.util
import threading
from concurrent.futures import Future

import pytest

# 모듈 수준 importorskip 을 쓰지 않는다. #258 첫 CI(pytest 7.4.4 + launch_testing 플러그인)에서
# navigation 시험이 통째로 빠졌다(collected 0 items / 1 skipped). 로컬 pytest 7.4.4 만으로는 재현되지 않아서
# 플러그인이 수집 중에 모듈을 import 할 때 난 Skipped 가 디렉터리 전체로 번진 것으로 추정한다.
NAV2_MISSING = importlib.util.find_spec('nav2_msgs') is None
pytestmark = pytest.mark.skipif(NAV2_MISSING, reason='CI 에 nav2_msgs 미설치 — fleet _wait_for 시험 미실행')

if not NAV2_MISSING:
    from rokey_p3_navigation.fleet_node import _wait_for, executor_threads


def test_done_future_returns_its_result():
    future = Future()
    future.set_result('done')
    assert _wait_for(future, give_up=lambda: True) == 'done'


def test_unanswered_future_gives_up():
    assert _wait_for(Future(), give_up=lambda: True, poll_s=0.01) is None


def test_waits_until_the_result_arrives_when_not_giving_up():
    future = Future()
    threading.Timer(0.05, future.set_result, args=('late',)).start()
    assert _wait_for(future, give_up=lambda: False, poll_s=0.01) == 'late'


def test_gives_up_only_once_the_deadline_passes():
    calls = []

    def give_up():
        calls.append(None)
        return len(calls) >= 3

    assert _wait_for(Future(), give_up=give_up, poll_s=0.01) is None
    assert len(calls) == 3


@pytest.mark.parametrize(('cpus', 'threads'), [(None, 2), (1, 2), (2, 2), (4, 4), (24, 24)])
def test_executor_threads_follow_cpu_count_with_a_floor_of_two(cpus, threads):
    # 코어가 많은 호스트(마스터 24 코어)는 전과 같은 CPU 수, 1 코어·모름은 #293 이 시험한 2.
    assert executor_threads(cpus) == threads
