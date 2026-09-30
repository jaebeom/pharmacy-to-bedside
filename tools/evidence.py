#!/usr/bin/env python3
"""Validate factual run records and protocols; never infer scientific truth."""

import argparse
import datetime as dt
import hashlib
import json
import math
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlsplit


class Invalid(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise Invalid(message)


def no_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, f"duplicate JSON key: {key}")
        result[key] = value
    return result


def read_json(path):
    require(not path.is_symlink(), f"symlink is not a record: {path}")
    require(path.stat().st_size <= 256 * 1024, f"JSON record exceeds 256 KiB: {path}")
    try:
        return json.loads(
            path.read_text(encoding="utf-8"), object_pairs_hook=no_duplicate_keys,
            parse_constant=lambda value: (_ for _ in ()).throw(Invalid(f"non-finite JSON: {value}")),
        )
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise Invalid(f"invalid JSON at {path}: {exc}") from exc


def json_identity(value):
    """JSON equality treats 1 and 1.0 alike, but never treats True as 1."""
    if type(value) is dict:
        return ("object", tuple(sorted((key, json_identity(item)) for key, item in value.items())))
    if type(value) is list:
        return ("array", tuple(json_identity(item) for item in value))
    if type(value) in (int, float):
        return ("number", value)
    return (type(value).__name__, value)


def validate_schema(value, rule, schema, at="$"):
    """Small fail-closed interpreter for the JSON Schema subset used in schemas/."""
    known = {"$schema", "$id", "$defs", "$ref", "title", "description", "type", "enum",
             "anyOf", "required", "properties", "additionalProperties", "minLength",
             "pattern", "minimum", "maximum", "items", "minItems", "maxItems", "uniqueItems"}
    require(not (rule.keys() - known), f"unsupported schema keyword at {at}: {rule.keys() - known}")
    if "$ref" in rule:
        reference = rule["$ref"]
        require(reference.startswith("#/$defs/"), "only local $defs references are supported")
        validate_schema(value, schema["$defs"][reference.removeprefix("#/$defs/")], schema, at)
        return
    if "anyOf" in rule:
        for choice in rule["anyOf"]:
            try:
                validate_schema(value, choice, schema, at)
                break
            except Invalid:
                pass
        else:
            raise Invalid(f"{at}: no anyOf alternative matches")
    expected = rule.get("type")
    checks = {
        "object": lambda x: type(x) is dict,
        "array": lambda x: type(x) is list,
        "string": lambda x: type(x) is str,
        "integer": lambda x: type(x) in (int, float) and math.isfinite(x) and int(x) == x,
        "number": lambda x: type(x) in (int, float) and math.isfinite(x),
        "boolean": lambda x: type(x) is bool,
        "null": lambda x: x is None,
    }
    if expected:
        allowed = expected if isinstance(expected, list) else [expected]
        require(all(item in checks for item in allowed), f"unsupported schema type at {at}")
        require(any(checks[item](value) for item in allowed), f"{at}: expected {expected}")
    if "enum" in rule:
        require(any(value == item and (type(value) is type(item) or
                    (type(value) in (int, float) and type(item) in (int, float))) for item in rule["enum"]),
                f"{at}: value is outside enum")
    if type(value) is dict:
        require(not (set(rule.get("required", [])) - value.keys()),
                f"{at}: missing fields {set(rule.get('required', [])) - value.keys()}")
        properties = rule.get("properties", {})
        for key, item in value.items():
            if key in properties:
                validate_schema(item, properties[key], schema, f"{at}.{key}")
            else:
                extra = rule.get("additionalProperties", True)
                require(extra is not False, f"{at}: unknown field {key}")
                if isinstance(extra, dict):
                    validate_schema(item, extra, schema, f"{at}.{key}")
    elif type(value) is list:
        require(len(value) >= rule.get("minItems", 0), f"{at}: too few items")
        require(len(value) <= rule.get("maxItems", len(value)), f"{at}: too many items")
        if rule.get("uniqueItems"):
            require(len({json_identity(item) for item in value}) == len(value),
                    f"{at}: duplicate array items")
        for index, item in enumerate(value):
            if "items" in rule:
                validate_schema(item, rule["items"], schema, f"{at}[{index}]")
    elif type(value) is str:
        require(len(value) >= rule.get("minLength", 0), f"{at}: string is too short")
        if "pattern" in rule:
            require(re.search(rule["pattern"], value) is not None, f"{at}: string does not match pattern")
    elif type(value) in (int, float):
        require(math.isfinite(value), f"{at}: non-finite number")
        require(value >= rule.get("minimum", value), f"{at}: number is too small")
        require(value <= rule.get("maximum", value), f"{at}: number is too large")


def timestamp(value):
    try:
        return dt.datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)
    except ValueError as exc:
        raise Invalid(f"invalid UTC timestamp: {value}") from exc


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_path(root, relative):
    path = PurePosixPath(relative)
    require(not path.is_absolute() and ".." not in path.parts and "\\" not in relative,
            f"unsafe relative path: {relative}")
    require(str(path) == relative, f"non-canonical path: {relative}")
    candidate = root / relative
    require(candidate.resolve().is_relative_to(root.resolve()), f"path escapes root: {relative}")
    current = root
    for part in path.parts:
        current = current / part
        require(not current.is_symlink(), f"symlink in path: {relative}")
    return candidate


def load_schema(root, name):
    return read_json(root / "schemas" / f"{name}.schema.json")


def validate_protocol(root, path):
    protocol = read_json(path)
    schema = load_schema(root, "protocol")
    validate_schema(protocol, schema, schema)
    require(path.stem == protocol["protocol_id"], "protocol filename must match protocol_id")
    timestamp(protocol["created_at"])
    if protocol["status"] == "frozen":
        require("frozen_at" in protocol, "frozen protocol needs frozen_at")
        require(timestamp(protocol["frozen_at"]) >= timestamp(protocol["created_at"]),
                "frozen_at precedes created_at")
    else:
        require("frozen_at" not in protocol, "proposed protocol cannot have frozen_at")
    names = [metric["name"] for metric in protocol["metrics"]]
    require(len(set(names)) == len(names), "duplicate protocol metric name")
    if protocol["phase"] == "acceptance":
        require(any("threshold" in metric for metric in protocol["metrics"]),
                "acceptance protocol needs at least one threshold")
    return protocol


def validate_artifact_uri(artifact):
    uri = artifact["uri"]
    require(not any(ord(char) <= 32 for char in uri) and "\\" not in uri,
            "artifact URI contains whitespace/control characters/backslash")
    parsed = urlsplit(uri)
    require("?" not in uri and "#" not in uri and not parsed.username and not parsed.password,
            "artifact URI must not contain query, fragment, or credentials")
    require("%" not in uri, "artifact URI must be unescaped canonical text")
    require(parsed.scheme in ("", "s3", "gs", "https"), "unsupported artifact URI scheme")
    require(not parsed.scheme or bool(parsed.netloc), "external artifact URI needs an authority")
    require(parsed.scheme or not parsed.netloc, "protocol-relative artifact URI is forbidden")
    path = PurePosixPath(unquote(parsed.path))
    require(".." not in path.parts, "artifact path traversal")
    if not parsed.scheme:
        require(not path.is_absolute() and str(path) == uri, "artifact URI must be a relative canonical key")
    else:
        require(parsed.path.startswith("/") and not parsed.path.startswith("//")
                and str(path) == parsed.path, "external artifact path must be canonical")
    require(artifact["sha256"] in path.parts,
            "artifact key must contain its full sha256 as a path segment")


def validate_run(root, path):
    run = read_json(path)
    schema = load_schema(root, "run")
    validate_schema(run, schema, schema)
    require(path.stem == run["run_id"], "run filename must match run_id")
    created = timestamp(run["created_at"])
    require(run["run_id"].startswith(created.strftime("%Y%m%dT%H%M%SZ") + "-" + run["host_id"] + "-"),
            "run_id timestamp/host must match created_at/host_id")
    protocol_path = safe_path(root, run["protocol"]["path"])
    require(sha256(protocol_path) == run["protocol"]["sha256"], "protocol sha256 mismatch")
    protocol = validate_protocol(root, protocol_path)
    require(run["phase"] == protocol["phase"], "run phase does not match protocol phase")
    require(protocol["status"] == "frozen", "recorded run requires a frozen protocol (including pilot)")
    require(timestamp(protocol["frozen_at"]) <= created, "run predates protocol freeze")
    if run["outcome"] == "failed":
        if protocol.get("requires_failure_classification"):
            require("failure_class" in run and "failure_cause" in run,
                    "failed run under a protocol requiring failure classification needs failure_class "
                    "and failure_cause")
    else:
        require(not any(field in run for field in
                         ("failure_class", "failure_cause", "failure_evidence", "retry_run_id")),
                "failure_class/failure_cause/failure_evidence/retry_run_id require outcome=failed")
    if run["phase"] == "acceptance":
        require(not run["code"]["dirty"], "acceptance run requires a clean code commit")
        for component in ("config", "scene"):
            require("sha256" in run["environment"]["fingerprints"][component],
                    f"acceptance {component} fingerprint requires sha256, not N/A")
        exists = subprocess.run(["git", "-C", str(root), "cat-file", "-e",
                                 run["code"]["commit"] + "^{commit}"], capture_output=True)
        require(exists.returncode == 0, "acceptance code commit must exist in this repository")
    require(run["seed"] in protocol["sample_plan"]["seeds"], "run seed is absent from sample plan")
    require(run["repetition_index"] <= protocol["sample_plan"]["repetitions_per_seed"],
            "repetition_index exceeds sample plan")
    actual = {metric["name"]: metric for metric in run["metrics"]}
    require(len(actual) == len(run["metrics"]), "duplicate run metric name")
    expected = {metric["name"]: metric for metric in protocol["metrics"]}
    require(actual.keys() == expected.keys(), "run metric names must exactly match protocol")
    for name, metric in actual.items():
        definition = expected[name]
        require(metric["unit"] == definition["unit"], f"{name}: metric unit mismatch")
        require(metric["sample_count"] + metric["missing_count"] > 0, f"{name}: empty denominator")
        if metric["value"] is None:
            require(metric["sample_count"] == 0 and metric["missing_count"] > 0,
                    f"{name}: null needs zero samples and explicit missing count")
        else:
            require(metric["sample_count"] > 0, f"{name}: numeric value requires observed samples")
    timed_clocks = {metric["clock"] for metric in protocol["metrics"] if metric["clock"] != "none"}
    require(not timed_clocks or run["clocks"]["duration"] in timed_clocks,
            "primary duration clock mismatch: absent from timed protocol metrics")
    uris = [artifact["uri"] for artifact in run["artifacts"]]
    require(len(set(uris)) == len(uris), "duplicate artifact URI")
    for artifact in run["artifacts"]:
        validate_artifact_uri(artifact)
    if run["code"]["dirty"]:
        require("dirty_patch_sha256" in run["code"], "dirty pilot code requires dirty_patch_sha256")
        require(any(item["sha256"] == run["code"]["dirty_patch_sha256"] for item in run["artifacts"]),
                "dirty patch must be retained as a hashed artifact")
    else:
        require("dirty_patch_sha256" not in run["code"], "clean code cannot declare dirty_patch_sha256")
    if "supersedes" in run:
        require(run["supersedes"] != run["run_id"], "run cannot supersede itself")
        previous_path = safe_path(root, "evidence/runs/" + run["supersedes"] + ".json")
        previous = read_json(previous_path)
        require(timestamp(previous["created_at"]) < created, "superseded run must have an earlier timestamp")
        for field in ("code", "host_id", "environment", "clocks", "protocol", "phase", "seed", "repetition_index"):
            require(run[field] == previous[field], f"correction must preserve trial identity: {field}")
        require(len(run.get("correction_reason", "").strip()) >= 10,
                "correction requires a specific correction_reason")
        retained = {(item["uri"], item["sha256"], item["size_bytes"]) for item in run["artifacts"]}
        require(all((item["uri"], item["sha256"], item["size_bytes"]) in retained
                    for item in previous["artifacts"]), "correction must retain original artifacts")
    else:
        require("correction_reason" not in run, "correction_reason requires supersedes")
    return run


def git(root, *args):
    result = subprocess.run(["git", "-C", str(root), *args], capture_output=True)
    detail = result.stderr.decode(errors="replace").strip()
    require(result.returncode == 0, f"git {' '.join(args[:2])} failed: {detail}")
    return result.stdout


def check_immutable(root, base):
    # Resolve to a SHA before using it in revision:path syntax. No shell is invoked.
    reference = git(root, "rev-parse", "--verify", "--end-of-options", base + "^{commit}").decode().strip()
    paths = git(root, "ls-tree", "-r", "--name-only", "-z", reference).decode().split("\0")
    frozen_protocols = set()
    for relative in filter(None, paths):
        path = PurePosixPath(relative)
        record = path.parent == PurePosixPath("evidence/runs") and path.suffix == ".json"
        review = (path.parent in (PurePosixPath("evidence/reviews"), PurePosixPath("evidence/deployments"))
                  and path.suffix == ".md"
                  and path.name != "README.md")
        protocol = path.parent == PurePosixPath("experiments/protocols") and path.suffix == ".json"
        if not (record or review or protocol):
            continue
        before = git(root, "show", reference + ":" + relative)
        if protocol:
            try:
                frozen = json.loads(before)["status"] == "frozen"
            except (ValueError, KeyError, TypeError) as exc:
                raise Invalid(f"invalid base protocol: {relative}") from exc
            if not frozen:
                continue
            frozen_protocols.add(relative)
        current = safe_path(root, relative)
        require(current.is_file(), f"append-only record deleted: {relative}")
        require(current.read_bytes() == before, f"append-only record modified: {relative}")
    for path in sorted((root / "evidence/runs").glob("*.json")):
        run = read_json(path)
        if run["phase"] == "acceptance":
            require(run["protocol"]["path"] in frozen_protocols,
                    f"acceptance protocol must already be frozen in --base: {path.name}")


def validate_repository(root, base=None):
    count = {"protocols": 0, "runs": 0}
    for folder, validator, label in (
        ("experiments/protocols", validate_protocol, "protocols"),
        ("evidence/runs", validate_run, "runs"),
    ):
        directory = safe_path(root, folder)
        if not directory.exists():
            continue
        for path in sorted(directory.iterdir()):
            require(not path.is_symlink(), f"symlink in evidence directory: {path}")
            require(path.is_file(), f"nested directory is not allowed: {path}")
            if path.name in ("README.md", "COLCON_IGNORE"):
                continue
            require(path.suffix == ".json", f"unexpected file in {folder}: {path.name}")
            try:
                validator(root, path)
            except (Invalid, OSError, ValueError, OverflowError) as exc:
                raise Invalid(f"{path.relative_to(root)}: {exc}") from exc
            count[label] += 1
    if base:
        check_immutable(root, base)
    return count


def verify_artifacts(root, manifest, artifact_root):
    run = validate_run(root, manifest)
    verified = 0
    for artifact in run["artifacts"]:
        parsed = urlsplit(artifact["uri"])
        # External stores must be materialized locally at their full URI path,
        # including authority to avoid collisions. This command never downloads.
        key = (parsed.netloc + parsed.path) if parsed.scheme else artifact["uri"]
        local = safe_path(artifact_root, key)
        require(local.is_file(), f"artifact is unavailable locally: {local}")
        require(local.stat().st_size == artifact["size_bytes"], f"artifact size mismatch: {key}")
        require(sha256(local) == artifact["sha256"], f"artifact sha256 mismatch: {key}")
        verified += 1
    return verified


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate", help="check records and optional append-only Git baseline")
    validate.add_argument("--base", help="Git commit/ref whose existing records must be preserved")
    artifacts = commands.add_parser("verify-artifacts", help="check every artifact locally; no network access")
    artifacts.add_argument("manifest", type=Path)
    artifacts.add_argument("--artifact-root", type=Path, required=True)
    args = parser.parse_args()
    try:
        root = args.repo.resolve()
        if args.command == "validate":
            count = validate_repository(root, args.base)
            print(f"Evidence structure OK: {count['protocols']} protocols, {count['runs']} runs. "
                  "This does not verify measurements or human approval.")
        else:
            manifest = args.manifest if args.manifest.is_absolute() else root / args.manifest
            count = verify_artifacts(root, manifest, args.artifact_root.resolve())
            print(f"Verified {count} local artifact hashes/sizes. This does not verify scientific validity.")
    except (Invalid, OSError, ValueError, OverflowError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
