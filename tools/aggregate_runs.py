#!/usr/bin/env python3
"""Aggregate one event_logger run directory into protocol metrics; never writes a manifest.

hospital-full-acceptance-v1 reads a whole attempt folder instead (tools/hospital_full_metrics.py, `--attempt N`).

A person reads this output and writes evidence/runs/<run-id>.json separately. The input format is
exactly what rokey_p3_orchestrator's event_logger_node.py and run_log.py write. No ROS import.
"""

import argparse
import importlib.util
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location("evidence", Path(__file__).resolve().parent / "evidence.py")
evidence = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(evidence)
_HOSPITAL_SPEC = importlib.util.spec_from_file_location(
    "hospital_full_metrics", Path(__file__).resolve().parent / "hospital_full_metrics.py")
hospital = importlib.util.module_from_spec(_HOSPITAL_SPEC)
_HOSPITAL_SPEC.loader.exec_module(hospital)
Invalid = evidence.Invalid
require = evidence.require

# The calculation rules below implement the definitions of these protocol versions only.
SUPPORTED_PROTOCOLS = ("pharmacy-lap-pilot-v1", *hospital.PROTOCOL_IDS)
DEFAULT_TRIP_LIMIT_S = 600.0  # contract section 7 default; the orchestrator parameter trip_limit_s
EXCLUDED_EPOCH = 1  # protocol purpose 2: the trip right after start-up never crossed the reset barrier
SUCCESS_STATE = "HOLD_RETURN"
SUCCESS_REASON = "pharmacy_only"
DIGITS = 9  # event stamps have nanosecond resolution; drop float noise below that

EVENT_FIELDS = {"name": str, "epoch": int, "request_id": str, "order_id": str, "stale": bool}
STATUS_FIELDS = {"order_id": str, "request_id": str, "state": str, "reason": str}


def _reject_constant(value):
    raise Invalid(f"non-finite JSON: {value}")


def _loads(text, where):
    try:
        return json.loads(text, object_pairs_hook=evidence.no_duplicate_keys, parse_constant=_reject_constant)
    except json.JSONDecodeError as exc:
        raise Invalid(f"{where}: invalid JSON: {exc}") from exc


def _typed(row, fields, where):
    require(type(row) is dict, f"{where}: a line must be a JSON object")
    for key, kind in fields.items():
        require(type(row.get(key)) is kind, f"{where}: {key} must be {kind.__name__}")
    stamp = row.get("stamp")
    require(type(stamp) in (int, float) and math.isfinite(stamp), f"{where}: stamp must be a finite number")
    return row


def read_jsonl(path, fields=None):
    rows = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        row = _loads(line, f"{path.name}:{number}")
        rows.append(_typed(row, fields, f"{path.name}:{number}") if fields else row)
    return rows


def read_run(run_dir):
    run_dir = Path(run_dir)
    for name in ("events.jsonl", "order_status.jsonl"):
        require((run_dir / name).is_file(), f"{run_dir}: {name} is missing; not an event_logger run directory")
    meta = None
    if (run_dir / "meta.json").is_file():
        meta = _loads((run_dir / "meta.json").read_text(encoding="utf-8"), "meta.json")
        require(type(meta) is dict and type(meta.get("epoch")) is int, "meta.json: epoch must be an integer")
    orders = read_jsonl(run_dir / "orders.jsonl") if (run_dir / "orders.jsonl").is_file() else None
    return {
        "events": read_jsonl(run_dir / "events.jsonl", EVENT_FIELDS),
        "statuses": read_jsonl(run_dir / "order_status.jsonl", STATUS_FIELDS),
        "orders": orders,  # written only when event_logger closes the run
        "meta": meta,  # likewise
    }


def _span(start, end):
    if start is None or end is None:
        return None
    return round(end["stamp"] - start["stamp"], DIGITS)


class Trip:
    """One request inside one epoch. Events are grouped by epoch and order events are matched by order_id,
    because the events of arm and isaac carry no request_id (protocol purpose 3)."""

    def __init__(self, accepted, live_events, statuses, trip_limit_s):
        self.accepted = accepted
        self.epoch = accepted["epoch"]
        self.request_id = accepted["request_id"]
        self.trip_limit_s = trip_limit_s
        self.events = [event for event in live_events if event["epoch"] == self.epoch]
        self.statuses = [row for row in statuses if row["request_id"] == self.request_id]  # file order
        order_ids = [row["order_id"] for row in self.statuses]
        order_ids += [event["order_id"] for event in self.named("ORDER_DONE", request_id=self.request_id)]
        self.order_ids = list(dict.fromkeys(order_id for order_id in order_ids if order_id))

    def named(self, name, after=None, **match):
        """Events with this name in stamp order; with `after`, only those at or after its stamp."""
        return [event for event in self.events
                if event["name"] == name
                and (after is None or event["stamp"] >= after["stamp"])
                and all(event[key] == value for key, value in match.items())]

    def first(self, name, after=None, **match):
        found = self.named(name, after, **match)
        return found[0] if found else None

    def last_status(self):
        last = {}
        for row in self.statuses:
            last[row["order_id"]] = row
        return last

    def success_checks(self):
        last = self.last_status()
        done = {event["order_id"] for event in self.named("ORDER_DONE", request_id=self.request_id)}
        orders = self.order_ids
        lap = lap_s(self)
        return {
            "order_status_recorded": bool(orders) and all(order_id in last for order_id in orders),
            "order_done_for_every_order": bool(orders) and all(order_id in done for order_id in orders),
            "last_status_hold_return_pharmacy_only": bool(orders) and all(
                order_id in last and last[order_id]["state"] == SUCCESS_STATE
                and last[order_id]["reason"] == SUCCESS_REASON for order_id in orders),
            "docked": lap is not None,
            "lap_s_within_trip_limit": lap is not None and lap <= self.trip_limit_s,
        }


def lap_s(trip):
    return _span(trip.accepted, trip.first("DOCKED", trip.accepted, request_id=trip.request_id))


def load_s(trip):
    return _span(trip.accepted, trip.first("LOAD_DONE", trip.accepted, request_id=trip.request_id))


def dispense_to_end_s(trip):
    dispensed = next((event for event in trip.named("DISPENSED") if event["order_id"] in trip.order_ids), None)
    if dispensed is None:
        return None
    return _span(dispensed, trip.first("POUCH_AT_END", dispensed, order_id=dispensed["order_id"]))


def return_s(trip):
    returned = trip.first("RETURNED", trip.accepted, request_id=trip.request_id)
    if returned is None:
        return None
    return _span(returned, trip.first("DOCKED", returned, request_id=trip.request_id))


def refill_s(trip):
    requested = trip.first("REFILL_REQUESTED")
    if requested is None:
        return None
    return _span(requested, trip.first("REFILL_DONE", requested))


def pick_attempts(trip):
    return sum(1 for event in trip.named("PICK_ATTEMPT") if event["order_id"] in trip.order_ids)


def lap_success(trip):
    checks = trip.success_checks()
    if not checks.pop("order_status_recorded"):
        return None  # an unrecorded order state is missing data, not a failure
    return int(all(checks.values()))


#: hospital-full-acceptance-v1 metric names with a rule in hospital_full_metrics.compute.
HOSPITAL_RULES = {
    "attempt_success", "scene_workcell_ready", "scene_refill_both", "scene_container_qr", "pouch_to_end_s",
    "scene_pouch_at_end", "scene_pick_in_slot", "scene_delivered_docked", "amr_touch_count", "governor_margin_lines",
    "governor_full_speed_lines", "governor_unknown_lines", "boot_check_pass", "orders10_delivered",
    "orders_beds_all_delivered", "orders10_multipc_delivered", "record_fps_min", "record_drop_ratio_max",
    "record_corrupt_sum", "unplanned_intervention_count", "avoidance_encounters",
    "governor_limit_lines_during_encounters", "vision_detect_rate", "vision_latency_ms", "fresh_clone_step_wall_s",
    "fresh_clone_asset_sha_ok", "rtf", "attempt_wall_s", "reset_dock_pose_error_m", "reset_arm_park_error_rad",
    "pouch_spawn_records",
}

CALCULATORS = {
    "lap_s": lap_s,
    "load_s": load_s,
    "dispense_to_end_s": dispense_to_end_s,
    "return_s": return_s,
    "refill_s": refill_s,
    "pick_attempts": pick_attempts,
    "lap_success": lap_success,
}


def _metric(definition, value):
    counts = {"sample_count": 1, "missing_count": 0} if value is not None else {"sample_count": 0, "missing_count": 1}
    return {"name": definition["name"], "value": value, "unit": definition["unit"], **counts}


def check_metrics(metrics, root=ROOT):
    """The same structure and missing-value rules evidence.py applies to a run manifest."""
    schema = evidence.load_schema(root, "run")
    evidence.validate_schema(metrics, schema["properties"]["metrics"], schema, "$.metrics")
    for metric in metrics:
        require(metric["sample_count"] + metric["missing_count"] > 0, f"{metric['name']}: empty denominator")
        if metric["value"] is None:
            require(metric["sample_count"] == 0 and metric["missing_count"] > 0,
                    f"{metric['name']}: null needs zero samples and explicit missing count")
        else:
            require(metric["sample_count"] > 0, f"{metric['name']}: numeric value requires observed samples")


def load_protocol(protocol_path, root=ROOT):
    protocol_path = Path(protocol_path)
    protocol = evidence.validate_protocol(root, protocol_path)
    require(protocol["protocol_id"] in SUPPORTED_PROTOCOLS,
            f"no calculation rules for protocol {protocol['protocol_id']}; supported: {', '.join(SUPPORTED_PROTOCOLS)}")
    rules = HOSPITAL_RULES if protocol["protocol_id"] in hospital.PROTOCOL_IDS else CALCULATORS
    unknown = [metric["name"] for metric in protocol["metrics"] if metric["name"] not in rules]
    require(not unknown, f"no calculation rule for protocol metrics: {', '.join(unknown)}")
    return protocol, evidence.sha256(protocol_path)


def aggregate_hospital(run_dirs, protocol, protocol_sha256, attempt, root=ROOT):
    """One or more attempt-folder roots → one metrics list (hospital-full-acceptance-v1).

    Normally one root. Phase E (다중 PC) splits one attempt across two hosts — `--run` given twice — and
    `hospital.compute` (via `Folder`) merges them; see its module docstring for the merge rules.
    """
    require(any((Path(root_dir) / "logs").is_dir() or (Path(root_dir) / "event_run").is_dir()
               for root_dir in run_dirs),
            f"{run_dirs}: none of the given roots has logs/ or event_run/; not a hospital-full attempt folder")
    values, notes, info = hospital.compute(run_dirs if len(run_dirs) > 1 else run_dirs[0], protocol["metrics"],
                                           attempt)
    metrics = [_metric(definition, values[definition["name"]]) for definition in protocol["metrics"]]
    check_metrics(metrics, root)
    return {
        "run_dir": str(run_dirs[0]) if len(run_dirs) == 1 else [str(root_dir) for root_dir in run_dirs],
        "protocol_id": protocol["protocol_id"],
        "protocol_sha256": protocol_sha256,
        "trip_limit_s": None,
        "epoch": info["epoch"],
        "status": "trial",
        "attempt": info,
        "trips": [],
        "metrics": metrics,
        "notes": notes,
    }


def aggregate(run_dir, protocol_path, trip_limit_s=DEFAULT_TRIP_LIMIT_S, root=ROOT, attempt=None):
    """`run_dir` is one path, or (hospital-full-acceptance-v1 only, phase E 다중 PC) a list of roots to merge."""
    require(type(trip_limit_s) in (int, float) and math.isfinite(trip_limit_s) and trip_limit_s > 0,
            "trip_limit_s must be a positive finite number")
    protocol, protocol_sha256 = load_protocol(protocol_path, root)
    run_dirs = list(run_dir) if isinstance(run_dir, (list, tuple)) else [run_dir]
    require(run_dirs, "--run 이 하나도 없다")
    if protocol["protocol_id"] in hospital.PROTOCOL_IDS:
        return aggregate_hospital(run_dirs, protocol, protocol_sha256, attempt, root)
    require(len(run_dirs) == 1, f"{protocol['protocol_id']} 은 --run 을 하나만 받는다({len(run_dirs)}개 받음)")
    run_dir = run_dirs[0]
    definitions = protocol["metrics"]
    names = {definition["name"] for definition in definitions}
    run = read_run(run_dir)
    notes = []

    stale = [event for event in run["events"] if event["stale"]]
    if stale:
        notes.append(f"ignored {len(stale)} stale events from an older epoch")
    ordered = sorted(enumerate(run["events"]), key=lambda pair: (pair[1]["stamp"], pair[0]))
    live = [event for _, event in ordered if not event["stale"]]
    epochs = sorted({event["epoch"] for event in live})
    epoch = run["meta"]["epoch"] if run["meta"] else (epochs[-1] if epochs else None)
    if run["meta"] and set(epochs) - {epoch}:
        notes.append(f"events carry epochs {epochs} but meta.json says {epoch}")
    if run["meta"] is None:
        notes.append("meta.json and orders.jsonl are absent: event_logger has not closed this run yet")

    trips = []
    seen = set()
    for event in live:
        if event["name"] != "REQUEST_ACCEPTED":
            continue
        require(event["request_id"], "REQUEST_ACCEPTED without request_id")
        key = (event["epoch"], event["request_id"])
        if key in seen:
            continue
        seen.add(key)
        trip = Trip(event, live, run["statuses"], float(trip_limit_s))
        excluded = trip.epoch == EXCLUDED_EPOCH
        last = trip.last_status()
        judged = {row.get("order_id"): row for row in run["orders"] or []}
        if len(trip.order_ids) > 1:
            notes.append(f"{trip.request_id}: {len(trip.order_ids)} orders; the protocol assumes one order per trip")
        if not excluded and "refill_s" in names and refill_s(trip) is None:
            reason = "no REFILL_REQUESTED" if trip.first("REFILL_REQUESTED") is None else "no REFILL_DONE after it"
            notes.append(f"{trip.request_id}: refill_s missing ({reason}); write that in the manifest notes")
        trips.append({
            "epoch": trip.epoch,
            "request_id": trip.request_id,
            "excluded": excluded,
            "excluded_reason": "epoch 1 never crossed the reset barrier (protocol purpose 2)" if excluded else "",
            "orders": [{
                "order_id": order_id,
                "last_status": last[order_id]["state"] if order_id in last else None,
                "last_reason": last[order_id]["reason"] if order_id in last else None,
                "order_done": trip.first("ORDER_DONE", request_id=trip.request_id, order_id=order_id) is not None,
                "run_log_state": judged[order_id].get("state") if order_id in judged else None,
                "run_log_reason": judged[order_id].get("reason") if order_id in judged else None,
            } for order_id in trip.order_ids],
            "success_checks": trip.success_checks(),
            "metrics": [_metric(definition, CALCULATORS[definition["name"]](trip)) for definition in definitions],
        })

    counted = [trip for trip in trips if not trip["excluded"]]
    if len(counted) == 1:
        status, metrics = "trial", counted[0]["metrics"]
    elif len(counted) > 1:
        status, metrics = "ambiguous", None
        notes.append(f"{len(counted)} counted trips in one run directory; the protocol runs one trip per epoch")
    elif epoch is None:
        status, metrics = "not_a_trial", None
        notes.append("no events and no meta.json: the epoch is unknown")
    elif epoch == EXCLUDED_EPOCH:
        status, metrics = "not_a_trial", None
        notes.append("epoch 1 is not a trial (protocol purpose 2); keep the raw files, leave it out of the denominator")
    else:
        status = "trial_without_start"
        metrics = [_metric(definition, None) for definition in definitions]
        notes.append("no REQUEST_ACCEPTED: record the run, keep it out of the trip denominator (protocol purpose 6)")
    if status in ("trial", "trial_without_start") and not any(
            event["name"] == "RESET_DONE" and event["epoch"] == epoch for event in live):
        notes.append(f"no RESET_DONE for epoch {epoch} in events.jsonl")

    for trip in trips:
        check_metrics(trip["metrics"], root)
    if metrics is not None:
        check_metrics(metrics, root)
    return {
        "run_dir": str(run_dir),
        "protocol_id": protocol["protocol_id"],
        "protocol_sha256": protocol_sha256,
        "trip_limit_s": float(trip_limit_s),
        "epoch": epoch,
        "status": status,
        "trips": trips,
        "metrics": metrics,
        "notes": notes,
    }


def _cell(value):
    return "null" if value is None else str(value)


def render(result):
    run_dir = result["run_dir"]
    lines = [
        f"run        {run_dir if isinstance(run_dir, str) else ' + '.join(run_dir)}",
        f"protocol   {result['protocol_id']}  sha256 {result['protocol_sha256']}",
        f"epoch      {_cell(result['epoch'])}  status {result['status']}  trip_limit_s {_cell(result['trip_limit_s'])}",
    ]
    if result.get("attempt"):
        info = result["attempt"]
        lines.append(f"attempt    {_cell(info['attempt'])}  phase {_cell(info['phase'])}  orders {info['orders']}"
                     f"  run_id {_cell(info['run_id'])}")
    lines += [
        "",
        "trips",
    ]
    if not result["trips"]:
        lines.append("  (none)")
    for trip in result["trips"]:
        flag = f"excluded: {trip['excluded_reason']}" if trip["excluded"] else "counted"
        lines.append(f"  epoch {trip['epoch']}  {trip['request_id']}  {flag}")
        for order in trip["orders"]:
            lines.append(f"    order {order['order_id']}  last {_cell(order['last_status'])}"
                         f"/{_cell(order['last_reason'])}  ORDER_DONE {'yes' if order['order_done'] else 'no'}"
                         f"  run_log {_cell(order['run_log_state'])}/{_cell(order['run_log_reason'])}")
        for check, passed in trip["success_checks"].items():
            lines.append(f"    {'ok  ' if passed else 'FAIL'} {check}")
    lines += ["", "metrics"]
    if result["metrics"] is None:
        lines.append("  (none: this directory is not one trial)")
    else:
        rows = [("name", "value", "unit", "sample", "missing")]
        rows += [(m["name"], _cell(m["value"]), m["unit"], str(m["sample_count"]), str(m["missing_count"]))
                 for m in result["metrics"]]
        widths = [max(len(row[column]) for row in rows) for column in range(5)]
        for row in rows:
            lines.append("  " + "  ".join(cell.ljust(width) for cell, width in zip(row, widths, strict=True)).rstrip())
    lines += ["", "notes"] + ([f"  - {note}" for note in result["notes"]] or ["  (none)"])
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, action="append", required=True,
                        help="one event_logger run directory (hospital-full: one attempt folder). Give it twice "
                             "for phase E 다중 PC (master01 stage root + master02 arm·nav·stack·web root)")
    parser.add_argument("--attempt", type=int, default=None,
                        help="hospital-full attempt index 1-16 (purpose 2); phase-only metrics need it")
    parser.add_argument("--protocol", type=Path, required=True, help="protocol JSON, e.g. experiments/protocols/...")
    parser.add_argument("--trip-limit-s", type=float, default=DEFAULT_TRIP_LIMIT_S,
                        help="orchestrator trip_limit_s used in the run (sim seconds, default 600)")
    parser.add_argument("--json", action="store_true", help="print JSON instead of the table")
    parser.add_argument("--repo", type=Path, default=ROOT, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    try:
        result = aggregate(list(args.run), args.protocol, args.trip_limit_s, args.repo.resolve(), args.attempt)
    except (Invalid, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else render(result))
    return 1 if result["status"] == "ambiguous" else 0


if __name__ == "__main__":
    sys.exit(main())
