"""bringup 노드(스텁 넷, isaac_adapter, bringup_check)의 공통 spin·종료.

터미널 Ctrl-C 나 launch 프로세스 그룹에 보낸 SIGINT 는 launch 가 넘기는 SIGINT 와 겹쳐 노드에 두 번 온다.
두 번째가 finally 의 destroy_node·try_shutdown 안에서 KeyboardInterrupt 로 나면 traceback 이 찍힌다(9/17 정비 관측,
stub_sim.py main → destroy_node → rclpy destroy_when_not_in_use). 종료 중의 그 인터럽트는 고장이 아니라 조용히 넘긴다.
각 단계는 따로 감싸서 destroy_node 가 끊겨도 try_shutdown 은 부른다.
"""

import contextlib

import rclpy
from rclpy.executors import ExternalShutdownException


def spin_until_interrupted(node, executor=None):
    """executor(없으면 rclpy.spin)로 돌리다 SIGINT·외부 종료에서 멈추고, 노드와 컨텍스트를 조용히 내린다."""
    try:
        if executor is None:
            rclpy.spin(node)
        else:
            executor.spin()
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        for step in (node.destroy_node, rclpy.try_shutdown):
            with contextlib.suppress(KeyboardInterrupt):
                step()
