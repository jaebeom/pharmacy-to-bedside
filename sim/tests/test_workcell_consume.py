"""조제실 가득 + 쓴 만큼 줄어드는 재고(재범 9/29 N3). Isaac 부분(치우기)은 L3 미실행."""

import importlib.util
import sys
import unittest
from pathlib import Path

STANDALONE = Path(__file__).resolve().parents[1] / "standalone"
REPO = STANDALONE.parents[1]
sys.path.insert(0, str(STANDALONE))


def load_stage():
    spec = importlib.util.spec_from_file_location("pharmacy_stage_consume", STANDALONE / "pharmacy_stage.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Consume(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.stage = load_stage()
        cls.source = (STANDALONE / "pharmacy_stage.py").read_text(encoding="utf-8")

    def test_the_hospital_preset_fills_every_cell_and_consumes(self):
        args = self.stage.parse_args(["--preset", "hospital"])
        self.assertEqual(0, args.workcell_empty_cells)
        self.assertTrue(args.workcell_consume)

    def test_other_worlds_keep_the_old_respawn(self):
        args = self.stage.parse_args([])
        self.assertFalse(args.workcell_consume)
        self.assertEqual(4, args.workcell_empty_cells)

    def test_a_consumed_canister_is_parked_left_out_of_grasps_and_counted_absent(self):
        body = self.source[self.source.index("def ros_refill_update(closed):"):]
        self.assertIn('if key not in ros_refill["pending"] and key not in ros_refill["consumed"]', body)
        self.assertIn('ros_refill["consumed"].add(key)', body)
        self.assertIn('set(ros_refill.get("consumed", ()))', body)          # publish_inventory: 빈 칸
        self.assertIn("pending={}, consumed=set()", body)                    # 리셋이 다시 채운다
        self.assertLess(self.stage.CONSUMED_PARK_Z, -1.0)                    # 바닥 아래

    def test_the_logical_shelf_matches_the_nine_physical_canisters_per_kind(self):
        # PyYAML 없이 센다 — CI 의 usd-core 단계에는 yaml 이 없다(작전 9/29 #791 Repository checks 실패).
        text = (REPO / "src" / "rokey_p3_orchestrator" / "config" / "dispenser.hospital-v0.yaml").read_text(
            encoding="utf-8")
        shelf = text[text.index("\nshelf:\n"):]
        self.assertEqual(9, shelf.count("lot_id: lot-amox-"))
        self.assertEqual(9, shelf.count("lot_id: lot-ibu-"))


if __name__ == "__main__":
    unittest.main()
