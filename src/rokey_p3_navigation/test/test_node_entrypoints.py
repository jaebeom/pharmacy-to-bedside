"""setup.py 의 콘솔 진입점이 실제로 있는 이름인가. ROS 없이 본다.

#407 CI 에서 시험이 잘못된 클래스 이름을 import 해 navigation 시험이 **하나도 돌지 않았다**
(수집 단계 ERROR). 이름 불일치는 로컬에서도 잡을 수 있다 — 모듈을 import 하지 않고
소스에서 정의를 찾는다(rclpy 가 없어도 돈다).
"""

import ast
import pathlib

import pytest

PACKAGE = pathlib.Path(__file__).resolve().parents[1] / 'rokey_p3_navigation'
SETUP = pathlib.Path(__file__).resolve().parents[1] / 'setup.py'


def defined_names(module):
    tree = ast.parse((PACKAGE / f'{module}.py').read_text(encoding='utf-8'))
    return {node.name for node in tree.body
            if isinstance(node, (ast.ClassDef, ast.FunctionDef))}


def entry_points():
    """setup.py 의 console_scripts 를 (이름, 모듈, 함수) 로 읽는다."""
    tree = ast.parse(SETUP.read_text(encoding='utf-8'))
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and ' = ' in node.value:
            name, target = node.value.split(' = ', 1)
            if ':' in target and target.startswith('rokey_p3_navigation.'):
                module, function = target.split(':', 1)
                yield name, module.split('.', 1)[1], function


@pytest.mark.parametrize(('name', 'module', 'function'), list(entry_points()))
def test_entry_point_exists(name, module, function):
    assert function in defined_names(module), f'{name}: {module}.{function} 가 없다'


def test_every_node_module_has_a_class_and_main():
    for path in PACKAGE.glob('*_node.py'):
        names = defined_names(path.stem)
        assert 'main' in names, f'{path.name}: main 이 없다'
        assert any(name[0].isupper() for name in names), f'{path.name}: 노드 클래스가 없다'
