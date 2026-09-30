"""`ThrottledLog` 를 **있지도 않은 이름으로** 부르지 않았는지 본다.

lap7 (9/21, master02)에서 스테이지가 ③ 직후 죽었다: `moving_warn.log(...)` 인데 그 클래스에는
`hit()` 밖에 없다. `AttributeError` 는 **첫 검출 때** 나므로 그때까지 모든 줄이 정상으로 보인다 —
①② 정차, ③ 배출까지 다 통과한 뒤 sim 101 s 에서 터졌다. 마스터 슬롯 한 번을 그대로 썼다.

내 시험들이 못 잡은 이유: 그 경로를 **원문으로만** 봤다(`assertIn("moving_warn", source)`). 원문은
철자가 틀려도 통과한다. 그래서 여기서는 **이름을 클래스에 대조한다** — 돌려 보지 않고도 잡히는 종류다.
"""

import ast
import unittest
from pathlib import Path

STANDALONE = Path(__file__).resolve().parents[1] / "standalone"


class ThrottledLogCallsExist(unittest.TestCase):

    def setUp(self):
        import sys

        sys.path.insert(0, str(STANDALONE))
        from p3sim import common

        # 클래스에 달린 것 + `__init__` 이 만드는 인스턴스 속성. 후자를 빼면 `not_ready_ik.count` 같은
        # **정상 사용**이 거짓 경보로 잡힌다 — 시험이 거짓 경보를 내면 다음 사람이 시험을 지운다.
        probe = common.ThrottledLog(1)
        self.allowed = {name for name in dir(probe) if not name.startswith("_")}
        self.tree = ast.parse((STANDALONE / "pharmacy_stage.py").read_text())

    def throttled_names(self):
        """`x = common.ThrottledLog(...)` 로 만들어진 이름들."""
        names = set()
        for node in ast.walk(self.tree):
            if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Call):
                continue
            func = node.value.func
            if isinstance(func, ast.Attribute) and func.attr == "ThrottledLog":
                names.update(t.id for t in node.targets if isinstance(t, ast.Name))
        return names

    def test_the_helper_is_used_somewhere(self):
        """이름을 하나도 못 찾으면 아래 시험이 **아무것도 안 보고** 통과한다."""
        self.assertTrue(self.throttled_names())
        self.assertIn("hit", self.allowed)

    def test_every_attribute_used_on_one_actually_exists(self):
        names = self.throttled_names()
        bad = []
        for node in ast.walk(self.tree):
            if (isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)
                    and node.value.id in names and node.attr not in self.allowed):
                bad.append(f"{node.value.id}.{node.attr} (line {node.lineno})")
        self.assertEqual(bad, [], f"ThrottledLog 에 없는 이름이다. 있는 것: {sorted(self.allowed)}")


if __name__ == "__main__":
    unittest.main()
