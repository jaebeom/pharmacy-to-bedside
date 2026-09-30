"""관제 웹 전체 보기(재범 v1.0): 여벌 AMR·더미 자리 `/isaac/fleet/poses`. Isaac 쪽 발행은 L3 미실행.

백엔드가 std_msgs/String 으로 직접 구독한다. 여기서는 형식·켜는 조건·스테이지 배선만 본다.
"""

import importlib.util
import json
import math
import sys
import unittest
from pathlib import Path

STANDALONE = Path(__file__).resolve().parents[1] / "standalone"
sys.path.insert(0, str(STANDALONE))
from p3sim import bridge  # noqa: E402
from p3sim import traffic_dummies as T  # noqa: E402


def load_stage():
    spec = importlib.util.spec_from_file_location("pharmacy_stage_fleet", STANDALONE / "pharmacy_stage.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FleetPosesMessageTests(unittest.TestCase):
    def encode(self, poses, frame_id="map"):
        return bridge.encode(bridge.FLEET_POSES, stamp=bridge.stamp(12.5), frame_id=frame_id, poses=poses)

    def test_spares_come_first_then_dummies_with_their_kind(self):
        poses = bridge.fleet_pose_items([("amr_2", -4.292, 4.784, -math.pi / 2)], [("dummy_1", 1, 2, 0.5)])
        message = json.loads(self.encode(poses))
        self.assertEqual(["amr_2", "dummy_1"], [p["id"] for p in message["poses"]])
        self.assertEqual(["spare_amr", "dummy"], [p["kind"] for p in message["poses"]])
        self.assertEqual({"v", "stamp", "frame_id", "poses"}, set(message))
        self.assertEqual({"sec": 12, "nanosec": 500000000}, message["stamp"])
        self.assertIsInstance(message["poses"][1]["x"], float)

    def test_an_empty_list_is_a_valid_message(self):
        self.assertEqual([], json.loads(self.encode([]))["poses"])

    def test_bad_items_are_rejected(self):
        good = bridge.fleet_pose_items([("amr_2", 0, 0, 0)])[0]
        for bad in ({**good, "kind": "pedestrian"}, {**good, "x": math.nan}, {**good, "id": ""},
                    {**good, "extra": 1}, {**good, "yaw": True}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                self.encode([bad])
        with self.assertRaises(ValueError):
            self.encode([good], frame_id="")

    def test_reliable_volatile_latest_only(self):
        self.assertEqual(("reliable", "volatile", 1), bridge.QOS[bridge.FLEET_POSES])
        self.assertEqual(5.0, bridge.FLEET_POSES_HZ)


class DummyPosesTests(unittest.TestCase):
    def test_poses_report_the_last_moved_pose_with_yaw(self):
        dummies = T.Dummies.__new__(T.Dummies)
        dummies._items = [{"who": "dummy_1", "xy": (1.0, 2.0), "yaw": 0.25}]
        self.assertEqual([("dummy_1", 1.0, 2.0, 0.25)], dummies.poses())


class StageWiringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.stage = load_stage()
        cls.source = (STANDALONE / "pharmacy_stage.py").read_text(encoding="utf-8")

    def args(self, *extra):
        return self.stage.parse_args(["--amr", "--amr-combined", "/x.usd", *extra])

    def test_on_only_with_a_spare_or_a_dummy(self):
        wanted = self.stage.fleet_poses_wanted
        self.assertFalse(wanted(self.args()))
        self.assertTrue(wanted(self.args("--amr-count", "2")))
        self.assertTrue(wanted(self.args("--traffic-dummies", "2")))
        self.assertFalse(wanted(self.stage.parse_args(["--traffic-dummies", "2"])))

    def test_the_bridge_publishes_the_topic_and_the_loop_sends_it(self):
        self.assertIn("((bridge.FLEET_POSES,) if fleet_poses_wanted(args) else ())", self.source)
        self.assertIn("ros.publish(bridge.FLEET_POSES, bridge.encode(", self.source)
        self.assertIn('frame_id="map"', self.source)


if __name__ == "__main__":
    unittest.main()
