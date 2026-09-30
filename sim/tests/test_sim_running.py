"""관제 웹 Play/Stop(재범 v1.0, 작전 9/27 ③): 스테이지가 `/p3/sim_running`(std_msgs/Bool)을 낸다. Isaac 쪽은 L3 미실행.

Isaac 없이 볼 수 있는 것만 본다: 토픽 이름·주기, 브리지의 발행기, 본 루프의 배선, 끝날 때 false.
"""

import re
import sys
import unittest
from pathlib import Path

STANDALONE = Path(__file__).resolve().parents[1] / "standalone"
sys.path.insert(0, str(STANDALONE))
from p3sim import bridge  # noqa: E402

SOURCE = (STANDALONE / "pharmacy_stage.py").read_text(encoding="utf-8")


class SimRunningTests(unittest.TestCase):
    def test_topic_and_rate(self):
        self.assertEqual("/p3/sim_running", bridge.SIM_RUNNING)
        self.assertEqual(1.0, bridge.SIM_RUNNING_HZ)
        # JSON 이 아니다 — JSON 표에 넣으면 String 발행기가 하나 더 생긴다.
        self.assertNotIn(bridge.SIM_RUNNING, bridge.QOS)
        self.assertNotIn(bridge.SIM_RUNNING, bridge.SCHEMAS)

    def test_the_bridge_has_a_volatile_bool_publisher(self):
        block = SOURCE[SOURCE.index("class JsonBridge"):]
        self.assertIn("create_publisher(Bool, bridge.SIM_RUNNING", block)
        self.assertIn("durability=DurabilityPolicy.VOLATILE", block)   # 죽은 프로세스의 true 가 남지 않게
        self.assertIn("def publish_running(self, playing):", block)

    def test_the_loop_sends_on_change_and_at_1_hz(self):
        self.assertIn('playing = bool(world.is_playing())', SOURCE)
        self.assertIn('if playing != running["last"] or now >= running["next"]:', SOURCE)
        self.assertIn("common.next_publish_time(running[\"next\"], now, bridge.SIM_RUNNING_HZ)", SOURCE)

    def test_false_is_sent_before_the_node_goes_away(self):
        tail = SOURCE[SOURCE.rindex("finally:"):]
        self.assertLess(tail.index("ros.publish_running(False)"), tail.index("ros.node.destroy_node()"))
        self.assertTrue(re.search(r"except Exception as exc:  # shutdown must continue\n\s+refill.write_line"
                                  r"\(f\"\[pharmacy_stage\] sim_running false", tail))


if __name__ == "__main__":
    unittest.main()
