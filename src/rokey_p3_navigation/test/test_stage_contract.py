"""스테이지가 정한 값을 **받는 쪽인 우리가 읽어** 대조한다. ROS 없이 돈다.

#435: 세션 사이에 말로 맞춘 값은 두 벌로 남고, 어긋나도 아무도 안 본다. 증상은 늘 "조용히 안 된다"다
(K4 의 QoS 불일치, `amr_1/base_link` 이름).

여기서 대조하는 것은 **스테이지가 소유한 값**이다. 깨지는 쪽이 받는 쪽(주행)이라 우리가 읽는다.
- dummy 조인트 이름 셋: 다르면 `base_driver` 가 자기 관절을 못 찾아 0 만 낸다(조용히 안 움직인다).
- 명령·관측 주기: 스테이지가 늦게 내면 `base_driver` 의 stale 판정(1.0 s wall)에 걸린다.

`sim/` 은 ROS 패키지가 아니라 경로로 읽는다. 파일이 없으면 건너뛴다(그 자체가 신호는 아니다).
"""

import ast
import contextlib
import importlib.util
import pathlib

import pytest
import yaml

REPO = pathlib.Path(__file__).resolve().parents[3]
STAGE = REPO / 'sim' / 'standalone' / 'p3sim' / 'amr_base.py'
NAVIGATION = pathlib.Path(__file__).resolve().parents[1]

pytestmark = pytest.mark.skipif(not STAGE.is_file(), reason=f'{STAGE} 가 없다')


def stage_module():
    """`p3sim` 패키지를 통하지 않고 파일만 읽는다(패키지 __init__ 이 Isaac 을 끌지 않게)."""
    spec = importlib.util.spec_from_file_location('amr_base_for_test', STAGE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def declared_defaults(module_name):
    """노드 소스의 `declare_parameter('이름', 기본값)` 를 AST 로 읽는다(rclpy 없이)."""
    tree = ast.parse((NAVIGATION / 'rokey_p3_navigation' / f'{module_name}.py')
                     .read_text(encoding='utf-8'))
    found = {}
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == 'declare_parameter' and len(node.args) == 2
                and isinstance(node.args[0], ast.Constant)):
            with contextlib.suppress(ValueError):
                found[node.args[0].value] = ast.literal_eval(node.args[1])
    return found


def params_file():
    return yaml.safe_load((NAVIGATION / 'config' / 'navigation_params.yaml')
                          .read_text(encoding='utf-8'))


def test_joint_names_match_the_stage():
    names = list(stage_module().JOINT_NAMES)
    defaults = declared_defaults('base_driver_node')
    assert [defaults['joint_x'], defaults['joint_y'], defaults['joint_yaw']] == names, (
        'base_driver 기본값이 스테이지의 JOINT_NAMES 와 다르다. 다르면 조용히 0 만 낸다')


def test_joint_names_in_the_params_file_match_the_stage():
    names = list(stage_module().JOINT_NAMES)
    driver = params_file()['base_driver']['ros__parameters']
    assert [driver['joint_x'], driver['joint_y'], driver['joint_yaw']] == names


def test_command_rate_matches_the_stage():
    # 스테이지의 권장 주기(COMMAND_HZ)와 우리 명령 주기가 같아야 한다. 느리면 stale 판정에 걸린다.
    assert params_file()['base_driver']['ros__parameters']['command_rate_hz'] == pytest.approx(
        stage_module().COMMAND_HZ)


def test_our_stale_window_is_longer_than_the_stage_period():
    # 관측이 한 번 빠져도 곧바로 stale 이 되지 않아야 한다. 주기보다 넉넉해야 한다.
    driver = params_file()['base_driver']['ros__parameters']
    period = 1.0 / stage_module().COMMAND_HZ
    assert driver['joint_states_timeout_s'] > period * 2
