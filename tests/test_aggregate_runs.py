"""Run-directory aggregation against synthetic event_logger output; fixtures are not measurements."""

import contextlib
import importlib.util
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1]


def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, SOURCE / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


aggregate_runs = load("aggregate_runs", "tools/aggregate_runs.py")
evidence = load("evidence", "tools/evidence.py")

FIXTURES = SOURCE / "tests/fixtures/runs"
PROTOCOL = FIXTURES / "pharmacy-lap-pilot-v1.json"
EPOCH_ONE = FIXTURES / "20000101T000000Z-master02-00000001"
LAP = FIXTURES / "20000101T000100Z-master02-00000002"
INTERRUPTED = FIXTURES / "20000101T000300Z-master02-00000003"
REPOSITORY_PROTOCOL = SOURCE / "experiments/protocols/pharmacy-lap-pilot-v1.json"


def values(metrics):
    return {metric["name"]: metric["value"] for metric in metrics}


def counts(metrics, name):
    metric = next(metric for metric in metrics if metric["name"] == name)
    return metric["sample_count"], metric["missing_count"]


class AggregateRunsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def copy(self, source):
        target = self.root / source.name
        shutil.copytree(source, target)
        return target

    def rows(self, run_dir, name):
        return [json.loads(line) for line in (run_dir / name).read_text().splitlines() if line.strip()]

    def write_rows(self, run_dir, name, rows):
        (run_dir / name).write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows))

    def protocol_with(self, change):
        protocol = json.loads(PROTOCOL.read_text())
        change(protocol)
        path = self.root / "protocols" / f"{protocol['protocol_id']}.json"
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps(protocol, indent=2) + "\n")
        return path

    def aggregate(self, run_dir, protocol=PROTOCOL, **kwargs):
        return aggregate_runs.aggregate(run_dir, protocol, **kwargs)

    def assert_run_schema_metrics(self, metrics):
        """The metrics array must pass the run manifest schema as evidence.py reads it."""
        schema = evidence.load_schema(SOURCE, "run")
        evidence.validate_schema(metrics, schema["properties"]["metrics"], schema, "$.metrics")
        for metric in metrics:
            self.assertGreater(metric["sample_count"] + metric["missing_count"], 0)
            if metric["value"] is None:
                self.assertEqual((metric["sample_count"], metric["missing_count"] > 0), (0, True))
            else:
                self.assertGreater(metric["sample_count"], 0)

    def test_one_lap_gives_every_protocol_metric(self):
        result = self.aggregate(LAP)
        self.assertEqual(result["status"], "trial")
        self.assertEqual(values(result["metrics"]), {
            "lap_s": 75.2, "load_s": 40.85, "dispense_to_end_s": 8.0, "return_s": 30.25,
            "refill_s": 64.5, "pick_attempts": 2, "lap_success": 1,
        })
        self.assertEqual(result["protocol_sha256"], evidence.sha256(PROTOCOL))
        self.assertEqual(result["notes"], [])

    def test_every_fixture_metrics_array_passes_the_run_schema(self):
        for run_dir in (EPOCH_ONE, LAP, INTERRUPTED):
            with self.subTest(run=run_dir.name):
                result = self.aggregate(run_dir)
                if result["metrics"] is not None:
                    self.assert_run_schema_metrics(result["metrics"])
                for trip in result["trips"]:
                    self.assert_run_schema_metrics(trip["metrics"])

    def test_epoch_one_is_listed_but_excluded(self):
        result = self.aggregate(EPOCH_ONE)
        self.assertEqual(result["status"], "not_a_trial")
        self.assertIsNone(result["metrics"])
        self.assertEqual([(trip["request_id"], trip["excluded"]) for trip in result["trips"]], [("r001-0001", True)])

    def test_interrupted_trip_is_a_failure_with_missing_times(self):
        result = self.aggregate(INTERRUPTED)
        metrics = result["metrics"]
        self.assertEqual(result["status"], "trial")
        self.assertEqual(values(metrics)["lap_success"], 0)
        self.assertEqual(counts(metrics, "lap_success"), (1, 0))
        for name in ("lap_s", "load_s", "dispense_to_end_s", "return_s", "refill_s"):
            self.assertIsNone(values(metrics)[name], name)
            self.assertEqual(counts(metrics, name), (0, 1), name)
        self.assertEqual((values(metrics)["pick_attempts"], counts(metrics, "pick_attempts")), (0, (1, 0)))
        self.assertIn("r003-0001: refill_s missing (no REFILL_REQUESTED); write that in the manifest notes",
                      result["notes"])

    def test_names_and_units_come_from_the_protocol(self):
        def keep_two(protocol):
            protocol["metrics"] = [metric for metric in protocol["metrics"]
                                   if metric["name"] in ("lap_success", "lap_s")]
        result = self.aggregate(LAP, self.protocol_with(keep_two))
        self.assertEqual([(metric["name"], metric["unit"]) for metric in result["metrics"]],
                         [("lap_s", "s"), ("lap_success", "ratio")])

    def test_unknown_metric_or_protocol_is_rejected(self):
        def extra(protocol):
            protocol["metrics"].append(dict(protocol["metrics"][0], name="docking_error_m", unit="m"))
        with self.assertRaisesRegex(aggregate_runs.Invalid, "docking_error_m"):
            self.aggregate(LAP, self.protocol_with(extra))

        def renamed(protocol):
            protocol["protocol_id"] = "pharmacy-lap-pilot-v2"
        with self.assertRaisesRegex(aggregate_runs.Invalid, "no calculation rules for protocol"):
            self.aggregate(LAP, self.protocol_with(renamed))

    def test_trip_limit_decides_success(self):
        result = self.aggregate(LAP, trip_limit_s=70.0)
        self.assertEqual(values(result["metrics"])["lap_success"], 0)
        self.assertFalse(result["trips"][0]["success_checks"]["lap_s_within_trip_limit"])
        self.assertEqual(values(result["metrics"])["lap_s"], 75.2)

    def test_wrong_reason_is_not_success(self):
        run_dir = self.copy(LAP)
        statuses = self.rows(run_dir, "order_status.jsonl")
        statuses[-1]["reason"] = "auth_mismatch"
        self.write_rows(run_dir, "order_status.jsonl", statuses)
        self.assertEqual(values(self.aggregate(run_dir)["metrics"])["lap_success"], 0)

    def test_unrecorded_order_state_is_missing_not_zero(self):
        run_dir = self.copy(LAP)
        self.write_rows(run_dir, "order_status.jsonl", [])
        metrics = self.aggregate(run_dir)["metrics"]
        self.assertIsNone(values(metrics)["lap_success"])
        self.assertEqual(counts(metrics, "lap_success"), (0, 1))

    def test_stale_events_are_ignored(self):
        run_dir = self.copy(LAP)
        events = self.rows(run_dir, "events.jsonl")
        events.append(dict(events[-1], name="PICK_ATTEMPT", epoch=1, order_id="ord-0001", stale=True))
        self.write_rows(run_dir, "events.jsonl", events)
        result = self.aggregate(run_dir)
        self.assertEqual(values(result["metrics"])["pick_attempts"], 2)
        self.assertIn("ignored 1 stale events from an older epoch", result["notes"])

    def test_events_are_matched_by_stamp_not_file_order(self):
        run_dir = self.copy(LAP)
        events = self.rows(run_dir, "events.jsonl")
        self.write_rows(run_dir, "events.jsonl", list(reversed(events)))
        self.assertEqual(values(self.aggregate(run_dir)["metrics"]), values(self.aggregate(LAP)["metrics"]))

    def test_two_counted_trips_in_one_epoch_are_ambiguous(self):
        run_dir = self.copy(LAP)
        events = self.rows(run_dir, "events.jsonl")
        events.append(dict(events[1], request_id="r002-0002", stamp=200.0))
        self.write_rows(run_dir, "events.jsonl", events)
        result = self.aggregate(run_dir)
        self.assertEqual(result["status"], "ambiguous")
        self.assertIsNone(result["metrics"])
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(aggregate_runs.main(["--run", str(run_dir), "--protocol", str(PROTOCOL)]), 1)

    def test_epoch_without_request_is_a_trial_with_every_metric_missing(self):
        run_dir = self.copy(LAP)
        events = self.rows(run_dir, "events.jsonl")
        self.write_rows(run_dir, "events.jsonl", [event for event in events if event["name"] == "RESET_DONE"])
        self.write_rows(run_dir, "order_status.jsonl", [])
        result = self.aggregate(run_dir)
        self.assertEqual(result["status"], "trial_without_start")
        self.assertTrue(all(metric["value"] is None for metric in result["metrics"]))
        self.assert_run_schema_metrics(result["metrics"])

    def test_open_run_without_meta_uses_event_epochs(self):
        run_dir = self.copy(LAP)
        (run_dir / "meta.json").unlink()
        (run_dir / "orders.jsonl").unlink()
        result = self.aggregate(run_dir)
        self.assertEqual((result["epoch"], result["status"]), (2, "trial"))
        self.assertIsNone(result["trips"][0]["orders"][0]["run_log_state"])

    def test_malformed_input_is_rejected(self):
        run_dir = self.copy(LAP)
        with (run_dir / "events.jsonl").open("a") as handle:
            handle.write('{"name": "DOCKED", "epoch": "2"}\n')
        with self.assertRaisesRegex(aggregate_runs.Invalid, r"events.jsonl:\d+: epoch must be int"):
            self.aggregate(run_dir)
        (run_dir / "events.jsonl").write_text("{not json\n")
        with self.assertRaisesRegex(aggregate_runs.Invalid, "invalid JSON"):
            self.aggregate(run_dir)
        (run_dir / "order_status.jsonl").unlink()
        with self.assertRaisesRegex(aggregate_runs.Invalid, "not an event_logger run directory"):
            self.aggregate(run_dir)

    def test_cli_json_output(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = aggregate_runs.main(["--run", str(LAP), "--protocol", str(PROTOCOL), "--json"])
        result = json.loads(output.getvalue())
        self.assertEqual(code, 0)
        self.assertEqual({"run_dir", "protocol_id", "protocol_sha256", "trips", "metrics"} - result.keys(), set())
        self.assert_run_schema_metrics(result["metrics"])

    @unittest.skipUnless(REPOSITORY_PROTOCOL.is_file(), "pharmacy-lap-pilot-v1 is not in experiments/protocols yet")
    def test_fixture_protocol_metrics_match_the_repository_protocol(self):
        fixture = json.loads(PROTOCOL.read_text())["metrics"]
        repository = json.loads(REPOSITORY_PROTOCOL.read_text())["metrics"]
        self.assertEqual(fixture, repository)
        aggregate_runs.load_protocol(REPOSITORY_PROTOCOL)


if __name__ == "__main__":
    unittest.main()
