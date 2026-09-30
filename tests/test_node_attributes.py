"""ROS 노드가 rclpy `Node` 의 내부 속성 이름을 덮어쓰지 않는지 본다.

ROS 없이 돈다. 파일을 `ast` 로 읽어 `self.<이름> = ...` 만 본다.

왜 있는가: `orchestrator_node.py` 가 액션 클라이언트 표를 `self._clients` 에 두었다가
`create_client()` 안의 `self._clients.append(client)` 에서
`AttributeError: 'dict' object has no attribute 'append'` 로 죽었다. 노드를 실제로 띄워야
보이는 고장이라 ROS 가 없는 클라우드 세션에서는 L2 가 도는 CI 전까지 안 보인다.
이 검사가 그 자리를 메운다.
"""
import ast
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / 'src'

#: rclpy `Node` 가 자기 것으로 쓰는 속성. 앞 여섯은 `create_*` 가 만든 것을 담는 목록이라
#: 덮어쓰면 그 `create_*` 호출이 바로 깨진다. 뒤 넷은 노드의 기본 상태다.
#: 새로 부딪히는 이름이 있으면 여기에 더한다.
RESERVED = frozenset({
    '_publishers', '_subscriptions', '_clients', '_services', '_timers', '_guards',
    '_context', '_parameters', '_logger', '_handle',
})


def node_sources():
    """`Node` 를 상속하는 클래스가 있는 파일만."""
    for path in sorted(SRC.rglob('*.py')):
        text = path.read_text(encoding='utf-8')
        if 'Node' in text:
            yield path, ast.parse(text, filename=str(path))


def shadowed(tree):
    """`self.<예약 이름> = ...` 을 (이름, 줄번호) 로."""
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        for target in targets:
            if (isinstance(target, ast.Attribute)
                    and isinstance(target.value, ast.Name) and target.value.id == 'self'
                    and target.attr in RESERVED):
                out.append((target.attr, target.lineno))
    return out


class NodeAttributeTests(unittest.TestCase):
    def test_no_node_shadows_an_rclpy_attribute(self):
        problems = []
        for path, tree in node_sources():
            for name, line in shadowed(tree):
                relative = path.relative_to(SRC.parent)
                problems.append(f'{relative}:{line}: self.{name} 은 rclpy Node 가 쓰는 이름이다')
        self.assertEqual([], problems, '\n'.join(problems))

    def test_the_check_would_have_caught_the_original_bug(self):
        tree = ast.parse('class A(Node):\n    def __init__(self):\n        self._clients = {}\n')
        self.assertEqual([('_clients', 3)], shadowed(tree))

    def test_a_different_name_is_fine(self):
        tree = ast.parse('class A(Node):\n    def __init__(self):\n        self._action_clients = {}\n')
        self.assertEqual([], shadowed(tree))


if __name__ == '__main__':
    unittest.main()
