"""spin_until_interrupted 가 종료 중 두 번째 SIGINT(KeyboardInterrupt)를 삼키고 남은 단계를 마저 부르는지.

ROS 그래프 없이 본다.
"""

import pytest

from rokey_p3_bringup import shutdown


class Executor:
    def __init__(self, error):
        self.error = error

    def spin(self):
        raise self.error


class Node:
    def __init__(self, destroy_error=None):
        self.destroy_error = destroy_error
        self.destroyed = 0

    def destroy_node(self):
        self.destroyed += 1
        if self.destroy_error is not None:
            raise self.destroy_error


@pytest.fixture
def shutdowns(monkeypatch):
    calls = []
    monkeypatch.setattr(shutdown.rclpy, 'try_shutdown', lambda: calls.append('try_shutdown'))
    return calls


@pytest.mark.parametrize('stop', [KeyboardInterrupt(), shutdown.ExternalShutdownException()])
def test_first_interrupt_ends_spin_quietly(shutdowns, stop):
    node = Node()
    shutdown.spin_until_interrupted(node, Executor(stop))
    assert node.destroyed == 1 and shutdowns == ['try_shutdown']


def test_second_interrupt_inside_destroy_node_is_swallowed_and_shutdown_still_runs(shutdowns):
    node = Node(destroy_error=KeyboardInterrupt())
    shutdown.spin_until_interrupted(node, Executor(KeyboardInterrupt()))
    assert node.destroyed == 1 and shutdowns == ['try_shutdown']


def test_other_errors_are_not_hidden(shutdowns):
    node = Node()
    with pytest.raises(RuntimeError):
        shutdown.spin_until_interrupted(node, Executor(RuntimeError('boom')))
    assert node.destroyed == 1 and shutdowns == ['try_shutdown']
