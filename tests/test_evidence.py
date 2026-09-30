"""Adversarial structural checks; fixtures are not experimental evidence."""

import copy
import importlib.util
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("evidence", SOURCE / "tools/evidence.py")
evidence = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(evidence)


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        shutil.copytree(SOURCE / "schemas", self.root / "schemas")
        (self.root / "experiments/protocols").mkdir(parents=True)
        (self.root / "evidence/runs").mkdir(parents=True)
        fixtures = SOURCE / "tests/fixtures/evidence"
        self.protocol_path = self.root / "experiments/protocols/synthetic-pilot-v1.json"
        shutil.copyfile(fixtures / self.protocol_path.name, self.protocol_path)
        self.protocol = json.loads(self.protocol_path.read_text())
        self.run = json.loads((fixtures / "20000101T000002Z-master01-00000001.json").read_text())
        self.run_path = self.root / "evidence/runs" / (self.run["run_id"] + ".json")
        self.git("init", "-q")
        # 자동 gc·maintenance 를 끈다. 뒤에서(detached) 돌면 .git/objects 에 늦게 써서 cleanup rmtree 와 겹친다.
        for key, value in (("gc.auto", "0"), ("gc.autoDetach", "false"),
                           ("maintenance.auto", "false"), ("maintenance.autoDetach", "false")):
            self.git("config", key, value)
        self.git("add", ".")
        self.git("-c", "user.name=Harness Tests", "-c", "user.email=tests@example.invalid",
                 "commit", "-qm", "synthetic baseline")
        self.run["code"]["commit"] = self.git("rev-parse", "HEAD").strip()
        self.write_run()

    def git(self, *args):
        return subprocess.check_output(["git", "-C", str(self.root), *args], text=True,
                                       stderr=subprocess.PIPE)

    def write_run(self):
        self.run_path.write_text(json.dumps(self.run, indent=2) + "\n")

    def write_protocol(self):
        self.protocol_path.write_text(json.dumps(self.protocol, indent=2) + "\n")
        self.run["protocol"]["sha256"] = evidence.sha256(self.protocol_path)
        self.write_run()

    def acceptance(self):
        self.protocol["phase"] = self.run["phase"] = "acceptance"
        self.protocol["metrics"][0]["threshold"] = {"operator": "<=", "value": 30}
        for component in ("config", "scene"):
            self.run["environment"]["fingerprints"][component] = {"sha256": "b" * 64}
        self.write_protocol()

    def reject(self, pattern):
        self.write_run()
        with self.assertRaisesRegex(evidence.Invalid, pattern):
            evidence.validate_repository(self.root)

    def commit_records(self):
        self.git("add", ".")
        self.git("-c", "user.name=Harness Tests", "-c", "user.email=tests@example.invalid",
                 "commit", "-qm", "synthetic records")
        return self.git("rev-parse", "HEAD").strip()

    def test_all_outcomes_including_failed_and_timeout_are_valid(self):
        for outcome in ("succeeded", "failed", "aborted", "timeout"):
            with self.subTest(outcome=outcome):
                self.run["outcome"] = outcome
                self.write_run()
                self.assertEqual(evidence.validate_repository(self.root)["runs"], 1)

    def test_missing_outcome_is_rejected(self):
        del self.run["outcome"]
        self.reject("missing fields")

    def test_unknown_fields_cannot_smuggle_trusted_status(self):
        self.run["review_status"] = "verified"
        self.reject("unknown field")

    def test_nan_infinity_and_overflow_are_rejected(self):
        for value in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(value=value):
                self.run["metrics"][0]["value"] = value
                self.reject("non-finite")
        self.run_path.write_text(self.run_path.read_text().replace("-Infinity", "1e999"))
        with self.assertRaisesRegex(evidence.Invalid, "expected"):
            evidence.validate_repository(self.root)

    def test_duplicate_json_key_is_rejected(self):
        self.run_path.write_text(self.run_path.read_text().replace('"outcome": "failed"',
                                 '"outcome": "failed", "outcome": "succeeded"'))
        with self.assertRaisesRegex(evidence.Invalid, "duplicate JSON key"):
            evidence.validate_repository(self.root)

    def test_missing_values_cannot_be_silently_replaced_with_zero(self):
        self.run["metrics"][0]["value"] = 0
        self.reject("requires observed samples")

    def test_zero_denominator_and_metric_omission_are_rejected(self):
        self.run["metrics"][0]["missing_count"] = 0
        self.reject("empty denominator")
        self.run["metrics"] = []
        self.reject("too few items")

    def test_extra_metric_and_unit_change_are_rejected(self):
        self.run["metrics"][0]["unit"] = "ms"
        self.reject("unit mismatch")
        self.run["metrics"][0]["name"] = "unregistered"
        self.reject("exactly match")

    def test_clock_and_seed_contamination_are_rejected(self):
        self.run["clocks"]["duration"] = "monotonic"
        self.reject("clock mismatch")
        self.run["clocks"]["duration"] = "simulation"
        self.run["seed"] = 999
        self.reject("absent from sample plan")

    def test_numeric_equivalent_seeds_are_duplicates(self):
        self.protocol["sample_plan"]["seeds"] = [0, 0.0]
        self.write_protocol()
        self.reject("duplicate array items")

    def test_dual_clock_metrics_are_valid(self):
        self.protocol["metrics"].append({
            "name": "elapsed_wall_seconds", "unit": "s", "description": "Synthetic local elapsed time.",
            "denominator": "One synthetic initiated cycle.", "aggregation": "single",
            "clock": "monotonic", "missing_policy": "record_missing"})
        self.run["metrics"].append({"name": "elapsed_wall_seconds", "value": 3.0, "unit": "s",
                                    "sample_count": 1, "missing_count": 0})
        self.run["metrics"][0].update(value=2.5, sample_count=1, missing_count=0)
        self.write_protocol()
        for primary_clock in ("simulation", "monotonic"):
            with self.subTest(primary_clock=primary_clock):
                self.run["clocks"]["duration"] = primary_clock
                self.write_run()
                self.assertEqual(evidence.validate_repository(self.root)["runs"], 1)

    def test_pilot_cannot_be_relabelled_acceptance(self):
        self.run["phase"] = "acceptance"
        self.reject("phase does not match")

    def test_all_runs_require_freeze(self):
        self.protocol["status"] = "proposed"
        del self.protocol["frozen_at"]
        self.write_protocol()
        self.reject("requires a frozen protocol")

    def test_acceptance_requires_clean_existing_commit(self):
        self.acceptance()
        evidence.validate_repository(self.root)
        self.run["code"]["dirty"] = True
        self.reject("clean code")
        self.run["code"]["dirty"] = False
        self.run["code"]["commit"] = "0" * 40
        self.reject("commit must exist")

    def test_acceptance_requires_a_threshold(self):
        self.protocol["phase"] = self.run["phase"] = "acceptance"
        self.write_protocol()
        self.reject("at least one threshold")

    def test_acceptance_config_and_scene_cannot_be_na(self):
        self.acceptance()
        for component in ("config", "scene"):
            with self.subTest(component=component):
                self.run["environment"]["fingerprints"][component] = {
                    "not_applicable": "Synthetic missing fingerprint for rejection test."}
                self.reject("fingerprint requires sha256")
                self.run["environment"]["fingerprints"][component] = {"sha256": "b" * 64}

    def test_acceptance_cannot_freeze_protocol_and_report_in_same_pr(self):
        self.acceptance()
        self.run_path.unlink()
        self.protocol["status"] = "proposed"
        del self.protocol["frozen_at"]
        self.protocol_path.write_text(json.dumps(self.protocol, indent=2) + "\n")
        base = self.commit_records()
        self.protocol["status"] = "frozen"
        self.protocol["frozen_at"] = "2000-01-01T00:00:01Z"
        self.write_protocol()
        with self.assertRaisesRegex(evidence.Invalid, "already be frozen in --base"):
            evidence.validate_repository(self.root, base)
        self.run_path.unlink()
        frozen_base = self.commit_records()
        self.write_run()
        self.assertEqual(evidence.validate_repository(self.root, frozen_base)["runs"], 1)

    def test_acceptance_cannot_introduce_new_protocol_with_results(self):
        base = self.git("rev-parse", "HEAD").strip()
        self.acceptance()
        new_path = self.protocol_path.with_name("synthetic-acceptance-v1.json")
        self.git("checkout", "--", "experiments/protocols/synthetic-pilot-v1.json")
        self.protocol["protocol_id"] = "synthetic-acceptance-v1"
        self.protocol_path = new_path
        self.run["protocol"]["path"] = "experiments/protocols/synthetic-acceptance-v1.json"
        self.write_protocol()
        with self.assertRaisesRegex(evidence.Invalid, "already be frozen in --base"):
            evidence.validate_repository(self.root, base)

    def test_dirty_pilot_requires_saved_patch(self):
        self.run["code"]["dirty"] = True
        self.reject("dirty_patch_sha256")
        self.run["code"]["dirty_patch_sha256"] = "1" * 64
        self.reject("retained as a hashed artifact")

    def test_protocol_hash_tamper_is_rejected(self):
        self.protocol_path.write_text(self.protocol_path.read_text() + "\n")
        self.reject("protocol sha256 mismatch")

    def test_protocol_path_traversal_is_rejected(self):
        for path in ("../protocol.json", "experiments/protocols/../../secret.json",
                     "/tmp/protocol.json", "experiments/protocols/a.json\n"):
            with self.subTest(path=path):
                self.run["protocol"]["path"] = path
                self.reject("pattern")

    def test_symlinked_protocol_is_rejected(self):
        outside = self.root / "outside.json"
        self.protocol_path.rename(outside)
        self.protocol_path.symlink_to(outside)
        self.reject("symlink")

    def test_unsafe_or_mutable_artifact_uris_are_rejected(self):
        digest = self.run["artifacts"][0]["sha256"]
        for uri in (f"https://host/{digest}/log?token=secret", f"https://user:pw@host/{digest}/log",
                    f"../{digest}/log", f"https://host/%2e%2e/{digest}/log",
                    "s3://bucket/latest/log", f"file:///tmp/{digest}/log"):
            with self.subTest(uri=uri):
                self.run["artifacts"][0]["uri"] = uri
                self.reject("artifact|unsupported")

    def test_artifact_hash_size_and_missing_file_verification(self):
        artifact_root = self.root / "raw"
        path = artifact_root / self.run["artifacts"][0]["uri"]
        path.parent.mkdir(parents=True)
        shutil.copyfile(SOURCE / "tests/fixtures/evidence/synthetic-artifact.txt", path)
        self.assertEqual(evidence.verify_artifacts(self.root, self.run_path, artifact_root), 1)
        path.write_bytes(b"X" * path.stat().st_size)
        with self.assertRaisesRegex(evidence.Invalid, "sha256 mismatch"):
            evidence.verify_artifacts(self.root, self.run_path, artifact_root)
        path.write_bytes(b"short")
        with self.assertRaisesRegex(evidence.Invalid, "size mismatch"):
            evidence.verify_artifacts(self.root, self.run_path, artifact_root)
        path.unlink()
        with self.assertRaisesRegex(evidence.Invalid, "unavailable locally"):
            evidence.verify_artifacts(self.root, self.run_path, artifact_root)

    def test_external_artifacts_are_verified_from_local_authority_path(self):
        artifact = self.run["artifacts"][0]
        artifact["uri"] = "s3://synthetic-bucket/" + artifact["uri"]
        self.write_run()
        artifact_root = self.root / "raw"
        path = artifact_root / artifact["uri"].removeprefix("s3://")
        path.parent.mkdir(parents=True)
        shutil.copyfile(SOURCE / "tests/fixtures/evidence/synthetic-artifact.txt", path)
        self.assertEqual(evidence.verify_artifacts(self.root, self.run_path, artifact_root), 1)

    def test_failed_record_cannot_be_deleted_or_rewritten(self):
        base = self.commit_records()
        original = self.run_path.read_bytes()
        self.run["outcome"] = "succeeded"
        self.write_run()
        with self.assertRaisesRegex(evidence.Invalid, "append-only record modified"):
            evidence.validate_repository(self.root, base)
        self.run_path.write_bytes(original)
        self.run_path.unlink()
        with self.assertRaisesRegex(evidence.Invalid, "append-only record deleted"):
            evidence.validate_repository(self.root, base)

    def test_frozen_protocol_cannot_be_changed(self):
        base = self.git("rev-parse", "HEAD").strip()
        self.protocol["timeout"]["seconds"] = 120
        self.write_protocol()
        with self.assertRaisesRegex(evidence.Invalid, "append-only record modified"):
            evidence.validate_repository(self.root, base)

    def test_review_cannot_be_rewritten(self):
        reviews = self.root / "evidence/reviews"
        reviews.mkdir()
        path = reviews / "20000101-test.md"
        path.write_text("Synthetic review, not a real approval.\n")
        base = self.commit_records()
        path.write_text("changed\n")
        with self.assertRaisesRegex(evidence.Invalid, "append-only record modified"):
            evidence.validate_repository(self.root, base)

    def test_deployment_cannot_be_deleted(self):
        deployments = self.root / "evidence/deployments"
        deployments.mkdir()
        path = deployments / "20000101-test.md"
        path.write_text("Synthetic deployment, no actual host action.\n")
        base = self.commit_records()
        path.unlink()
        with self.assertRaisesRegex(evidence.Invalid, "append-only record deleted"):
            evidence.validate_repository(self.root, base)

    def test_correction_adds_record_without_removing_original(self):
        base = self.commit_records()
        previous = copy.deepcopy(self.run)
        self.run["supersedes"] = previous["run_id"]
        self.run["correction_reason"] = "Synthetic correction of reported metric only."
        self.run["created_at"] = "2000-01-01T00:00:03Z"
        self.run["run_id"] = "20000101T000003Z-master01-00000002"
        self.run_path = self.run_path.with_name(self.run["run_id"] + ".json")
        self.write_run()
        self.assertEqual(evidence.validate_repository(self.root, base)["runs"], 2)


    def test_correction_cannot_replace_trial_identity(self):
        self.test_correction_adds_record_without_removing_original()
        self.run["code"]["commit"] = "f" * 40
        self.reject("preserve trial identity")

    def test_correction_cannot_discard_original_artifacts(self):
        self.test_correction_adds_record_without_removing_original()
        self.run["artifacts"][0]["size_bytes"] += 1
        self.reject("retain original artifacts")

    def test_correction_requires_reason(self):
        self.test_correction_adds_record_without_removing_original()
        del self.run["correction_reason"]
        self.reject("correction_reason")

    def test_requires_failure_classification_is_opt_in(self):
        """default synthetic fixture's protocol has no requires_failure_classification flag, so its
        outcome=failed run (no failure_class/failure_cause) passes exactly as before — v3's new gate is
        opt-in per protocol, not retroactive."""
        self.assertEqual(evidence.validate_repository(self.root)["runs"], 1)

    def test_requires_failure_classification_gate(self):
        self.protocol["requires_failure_classification"] = True
        self.write_protocol()
        self.reject("needs failure_class and failure_cause")
        self.run["failure_class"] = "robot"
        self.run["failure_cause"] = "Synthetic robot fault for the classification gate test."
        self.write_run()
        self.assertEqual(evidence.validate_repository(self.root)["runs"], 1)

    def test_failure_fields_require_outcome_failed(self):
        self.run["outcome"] = "succeeded"
        for field, value in (("failure_class", "robot"), ("failure_cause", "Synthetic cause."),
                             ("failure_evidence", "#240 0000000000"),
                             ("retry_run_id", "20000101T000009Z-master01-00000009")):
            with self.subTest(field=field):
                self.run[field] = value
                self.reject("require outcome=failed")
                del self.run[field]

    def test_failure_class_enum_and_retry_run_id_pattern(self):
        self.run["failure_class"] = "not_a_real_class"
        self.run["failure_cause"] = "Synthetic cause."
        self.reject("outside enum")
        self.run["failure_class"] = "infra"
        self.write_run()
        evidence.validate_repository(self.root)
        self.run["retry_run_id"] = "not-a-run-id"
        self.reject("does not match pattern")


if __name__ == "__main__":
    unittest.main()
