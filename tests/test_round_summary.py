"""tools/round_summary.py: attempt_success 로만 성공을 세고, 실패는 failure_class 로 분류한다."""

import importlib.util
import unittest
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("round_summary", SOURCE / "tools/round_summary.py")
round_summary = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(round_summary)


def run(repetition_index, success, **failure_fields):
    record = {
        "run_id": f"20260101T00000{repetition_index}Z-master01-0000000{repetition_index}",
        "repetition_index": repetition_index,
        "outcome": "succeeded" if success else "failed",
        "metrics": [{"name": "attempt_success", "value": 1 if success else 0, "unit": "ratio",
                     "sample_count": 1, "missing_count": 0}],
    }
    record.update(failure_fields)
    return record


class RoundSummaryTests(unittest.TestCase):
    def test_all_success_passes_the_reference_line(self):
        runs = [run(i, True) for i in range(1, 17)]
        summary = round_summary.summarize(runs, pass_ratio=0.9)
        self.assertEqual(summary["attempts"], 16)
        self.assertEqual(summary["success"], 16)
        self.assertEqual(summary["success_rate"], 1.0)
        self.assertTrue(summary["meets_pass_ratio_reference"])
        self.assertEqual(summary["failure_class_counts"], {"robot": 0, "infra": 0, "operator": 0})
        self.assertEqual(summary["unclassified_failures"], 0)

    def test_fifteen_of_sixteen_meets_the_ninety_percent_reference_line(self):
        runs = [run(i, True) for i in range(1, 16)]
        runs.append(run(16, False, failure_class="robot", failure_cause="Synthetic arm stall."))
        summary = round_summary.summarize(runs, pass_ratio=0.9)
        self.assertEqual(summary["success"], 15)
        self.assertAlmostEqual(summary["success_rate"], 15 / 16)
        self.assertTrue(summary["meets_pass_ratio_reference"])
        self.assertEqual(summary["failure_class_counts"]["robot"], 1)

    def test_fourteen_of_sixteen_misses_the_reference_line(self):
        runs = [run(i, True) for i in range(1, 15)]
        runs.append(run(15, False, failure_class="infra", failure_cause="Synthetic network drop."))
        runs.append(run(16, False, failure_class="operator", failure_cause="Synthetic wrong flag."))
        summary = round_summary.summarize(runs, pass_ratio=0.9)
        self.assertEqual(summary["success"], 14)
        self.assertFalse(summary["meets_pass_ratio_reference"])
        self.assertEqual(summary["failure_class_counts"], {"robot": 0, "infra": 1, "operator": 1})

    def test_robot_failures_are_counted_and_carry_their_own_row(self):
        runs = [run(i, True) for i in range(1, 15)]
        runs.append(run(15, False, failure_class="robot", failure_cause="Synthetic gripper miss."))
        runs.append(run(16, False, failure_class="robot", failure_cause="Synthetic nav timeout.",
                        failure_evidence="#240 0000000001", retry_run_id="20260101T000017Z-master01-00000017"))
        summary = round_summary.summarize(runs, pass_ratio=0.9)
        self.assertEqual(summary["failure_class_counts"]["robot"], 2)
        failure_rows = [row for row in summary["rows"] if row["attempt_success"] == 0]
        self.assertEqual(len(failure_rows), 2)
        self.assertEqual(failure_rows[1]["retry_run_id"], "20260101T000017Z-master01-00000017")

    def test_unclassified_failure_is_counted_separately_not_silently_dropped(self):
        runs = [run(i, True) for i in range(1, 16)]
        runs.append(run(16, False))  # failure_class 누락(마스터가 아직 안 채운 경우)
        summary = round_summary.summarize(runs, pass_ratio=0.9)
        self.assertEqual(summary["unclassified_failures"], 1)
        self.assertEqual(sum(summary["failure_class_counts"].values()), 0)

    def test_metric_value_reads_by_name_not_position(self):
        record = {"metrics": [{"name": "other_metric", "value": 5, "unit": "count",
                               "sample_count": 1, "missing_count": 0},
                              {"name": "attempt_success", "value": 1, "unit": "ratio",
                               "sample_count": 1, "missing_count": 0}]}
        self.assertEqual(round_summary.metric_value(record, "attempt_success"), 1)

    def test_format_table_lists_only_failures_with_their_evidence(self):
        runs = [run(1, True), run(2, False, failure_class="robot", failure_cause="Synthetic stall.",
                                  failure_evidence="#240 9999")]
        summary = round_summary.summarize(runs, pass_ratio=0.9)
        table = round_summary.format_table(summary)
        self.assertIn("FAIL rep=2", table)
        self.assertIn("class=robot", table)
        self.assertIn("evidence=#240 9999", table)
        self.assertNotIn("rep=1", table)


if __name__ == "__main__":
    unittest.main()
