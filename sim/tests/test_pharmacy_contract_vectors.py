"""Contract vectors (src/rokey_p3_interfaces/contract_vectors/conveyor_arm/v1) run on the sim belt. No Isaac.

The runner replays each vector on BeltModel plus the few rules pharmacy_stage.py adds around it (dispense, held
release, pick_notice, reset), in the reading the vector asks for: no options = default stage, fail_closed =
--belt-fail-closed. Vectors the stage cannot pass yet are expected failures (strict: once fixed, the unexpected
success fails the run, and the fixing PR removes the entry). A missing vector file fails; it is never skipped.

    python3 -m unittest discover -s sim/tests -p 'test_[mp]*.py'
"""

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STANDALONE = ROOT / "sim" / "standalone"
sys.path.insert(0, str(STANDALONE))

from p3sim import belt, bridge  # noqa: E402

VECTOR_DIR = ROOT / "src" / "rokey_p3_interfaces" / "contract_vectors" / "conveyor_arm" / "v1"
DISPENSE = VECTOR_DIR / "dispense.json"

# Stage geometry defaults (pharmacy_stage.py): belt 1.6 x 0.25 m, end zone 0.15 m.
LENGTH, WIDTH, END_ZONE = 1.6, 0.25, 0.15
FRAMES = {"mid": (LENGTH / 2, 0.0, 0.0), "end": (LENGTH - END_ZONE / 2, 0.0, 0.0),
          "off": (LENGTH / 2, WIDTH, 0.0), "lost": None}

# id -> reason. Remove the entry in the PR that fixes the defect.
EXPECTED_FAILURES = {}


class StageModel:
    """BeltModel and the stage rules around it, without Isaac."""

    def __init__(self, params, options):
        self.fail_closed = bool(options.get("fail_closed") or options.get("speed_missing_resets_settle"))
        self.model = belt.BeltModel(LENGTH, WIDTH, END_ZONE, params["settle_speed"], params["settle_time_s"],
                                    fail_closed=self.fail_closed)
        self.epoch = belt.FIRST_EPOCH
        self.pouch = False  # a pool pouch is on the belt (state["pouch"] is not None)

    def dispense(self, t, request_id, order_id):
        if self.model.is_resend(request_id, order_id) and self.pouch:
            return {"accepted": True, "message": "", "dispensed": 0}
        message = self.model.decide_dispense(order_id, True, True, True)
        dispensed = 0
        if message == "":
            dispensed = self.model.accept(request_id, order_id, t).count(belt.DISPENSED)
            self.pouch = True
        return {"accepted": message == "", "message": message, "dispensed": dispensed}

    def observe(self, t, at, speed, held):
        frame = FRAMES[at]
        if held:  # observe_belt held branch (--ur5): free only off the belt, else return before observe
            if self.model.observe_held(frame):
                self.pouch = False
            return {}
        if speed is None and not self.fail_closed:
            speed = 0.0  # stage default: a missing velocity counts as stopped
        _events, notes = self.model.observe(frame, speed, t)
        if "pouch_left_belt" in notes:
            self.pouch = False  # remove_pouch("left_belt")
        return {}

    def pick_notice(self, order_id, epoch):
        message = {"v": 1, "stamp": {"sec": 0, "nanosec": 0}, "epoch": epoch, "order_id": order_id,
                   "source": "POUCH_PICKED"}
        applies, _why = bridge.pick_notice_applies(message, self.epoch, self.model.order_id,
                                                   self.model.at_end and self.pouch)
        if applies:
            self.pouch = False
            self.model.reset()
        return {}

    def reset(self, epoch):
        self.pouch = False
        self.model.reset()
        self.epoch = epoch
        return {}

    def observed(self):
        return self.model.state()


def replay(document, vector):
    stage = StageModel(document["params"], vector.get("options", {}))
    mismatches = []
    for step in vector["steps"]:
        t = step["t"]
        if "dispense" in step:
            result = stage.dispense(t, step["dispense"]["request_id"], step["dispense"]["order_id"])
        elif "pouch" in step:
            pouch = step["pouch"]
            result = stage.observe(t, pouch["at"], pouch.get("speed"), pouch.get("held", False))
        elif "pick_notice" in step:
            result = stage.pick_notice(step["pick_notice"]["order_id"], step["pick_notice"]["epoch"])
        elif "reset" in step:
            result = stage.reset(step["reset"]["epoch"])
        else:
            raise ValueError(f"{vector['id']} t={t}: unknown step {sorted(step)}")
        seen = {**stage.observed(), **result}
        for key, want in step.get("expect", {}).items():
            if key not in seen:
                mismatches.append(f"t={t} {key}: not produced by this runner")
            elif seen[key] != want:
                mismatches.append(f"t={t} {key}: want {want!r} got {seen[key]!r}")
    return mismatches


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


class VectorFileTests(unittest.TestCase):
    def test_dispense_vectors_exist(self):
        self.assertTrue(DISPENSE.is_file(), f"missing {DISPENSE.relative_to(ROOT)}")

    def test_expected_failures_name_real_vectors(self):
        ids = {vector["id"] for vector in load(DISPENSE)["vectors"]}
        self.assertLessEqual(set(EXPECTED_FAILURES), ids)


class DispenseVectorTests(unittest.TestCase):
    pass


def _add_vector_tests():
    if not DISPENSE.is_file():
        return  # VectorFileTests fails instead
    document = load(DISPENSE)
    for vector in document["vectors"]:
        def test(self, vector=vector):
            mismatches = replay(document, vector)
            self.assertEqual([], mismatches, f"{vector['id']} {vector['title']}")
        name = f"test_{vector['id']}"
        if vector["id"] in EXPECTED_FAILURES:
            test = unittest.expectedFailure(test)
        test.__doc__ = f"{vector['id']} {vector['title']}"
        setattr(DispenseVectorTests, name, test)


_add_vector_tests()


if __name__ == "__main__":
    unittest.main()
