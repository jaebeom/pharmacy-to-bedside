"""L1. bt_navigator 가 planner·controller 의 goal 수락을 기다리는 시간. ROS 를 띄우지 않는다.

9/24 50b658a 10건 ord-0003(master02): 복도 정상 주행 중 `Timed out while waiting for action server to acknowledge
goal request for compute_path_to_pose` 한 줄로 NavigateToPose 가 abort(status 6)됐다. planner·controller 쪽에는
실패 줄이 없었다. Jazzy 기본 20 ms 는 Isaac 과 한 PC(rtf 0.38)에서 모자란다.
"""
from pathlib import Path

import yaml

CONFIG = Path(__file__).resolve().parents[1] / "config" / "nav2_params.yaml"
BT = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))["bt_navigator"]["ros__parameters"]


def test_goal_acknowledge_wait_is_not_the_20_ms_default():
    assert BT["default_server_timeout"] >= 200


def test_the_bt_loop_is_still_shorter_than_the_acknowledge_wait():
    assert BT["bt_loop_duration"] < BT["default_server_timeout"]
