"""Characterization tests: pin what the belt model and pharmacy_stage do TODAY (main 78a53e3). Isaac is not started.

These are not acceptance tests. They record current behaviour so that the contract A1 revision shows up as a diff.
Each test says one of:
  CURRENT-KEEP     expected to stay after A1 (INT-1 draft 2.4).
  CURRENT-DEFECT   defect candidate (CPS plan 1, 3). A1 is expected to change the expected value; do not read the
                   assertion as the correct behaviour.
  RESOLVED #N      was CURRENT-DEFECT; PR #N fixed it and flipped the assertion in the same PR.

    python3 -m unittest discover -s sim/tests -p 'test_[mp]*.py'
"""

import sys
import unittest
from pathlib import Path

STANDALONE = Path(__file__).resolve().parents[1] / "standalone"
sys.path.insert(0, str(STANDALONE))

from p3sim import belt, bridge  # noqa: E402

STAGE_SOURCE = (STANDALONE / "pharmacy_stage.py").read_text()

END = (1.12, 0.0, 0.0)  # inside the end zone of the model below
MID = (0.5, 0.0, 0.0)


def body(start, end):
    """Source of pharmacy_stage.py between two markers (the stage needs Isaac, so its paths are read as text)."""
    return STAGE_SOURCE[STAGE_SOURCE.index(start):STAGE_SOURCE.index(end)]


def travelling_model():
    """Same geometry as BeltTests in test_pharmacy_stage.py, one pouch accepted at t=0 and moving mid-belt."""
    model = belt.BeltModel(length=1.2, width=0.2, end_zone_length=0.15, settle_speed=0.01, settle_time_s=0.3)
    model.accept("r001-0001", "ord-0001", 0.0)
    model.observe(MID, 0.15, 1.0)
    return model


class BeltCharacterizationTests(unittest.TestCase):
    def test_r1_missing_velocity_counts_as_stopped(self):
        # CURRENT-DEFECT (A1-1): a missing velocity is turned into 0.0 by the stage, and the model takes 0.0 as a
        # settle sample, so POUCH_AT_END can go out with no measured speed. A1 draft: None resets the settle timer.
        # Default only: opt-in --belt-fail-closed (#252) passes None instead, pinned in test_pharmacy_belt_fail_closed.
        self.assertIn("if velocity is not None else 0.0", body("def observe_belt", "def do_reset"))
        model = travelling_model()
        self.assertEqual(["stop_belt"], model.observe(END, 0.15, 2.0)[1])
        self.assertEqual([], model.observe(END, 0.0, 2.1)[0])  # 0.0 standing in for "not received"
        self.assertEqual([belt.POUCH_AT_END], model.observe(END, 0.0, 2.5)[0])

    def test_r2_one_missing_frame_frees_the_belt(self):
        # CURRENT-DEFECT (A1-2): one tick without a pose is the same as the pouch leaving the belt. The belt is
        # reported free and the order id is dropped. A1 draft: occupied stays true (fail-closed).
        # Default only: opt-in --belt-fail-closed (#252) keeps it occupied, pinned in test_pharmacy_belt_fail_closed.
        model = travelling_model()
        _events, notes = model.observe(None, 0.0, 1.1)
        self.assertEqual(["pouch_left_belt"], notes)
        self.assertEqual({"occupied": False, "at_end": False, "order_id": ""}, model.state())
        self.assertEqual("r001-0001", model.request_id)  # partial clear: request_id and dispensed_at stay
        self.assertEqual(0.0, model.dispensed_at)

    def test_r3_pouch_off_the_belt_is_parked_and_next_dispense_accepted(self):
        # CURRENT-DEFECT (A1-2): leaving the belt (a drop) frees the belt, the stage parks the pouch back into the
        # pool and the next Dispense is accepted. No /events message; only a log note.
        # Default only: opt-in --belt-fail-closed (#252) keeps it occupied, pinned in test_pharmacy_belt_fail_closed.
        model = travelling_model()
        self.assertEqual(["pouch_left_belt"], model.observe((0.6, 0.5, 0.0), 0.3, 1.1)[1])
        self.assertEqual("", model.decide_dispense("ord-0002", ready=True, known_order=True))
        observe = body("def observe_belt", "def do_reset")
        self.assertIn('if note == "pouch_left_belt":', observe)
        self.assertIn('remove_pouch("left_belt")', observe)
        self.assertIn("pool.release(index)", body("def remove_pouch", "def spawn_pouch"))

    def test_r4_moving_after_stop_is_not_a_state(self):
        # CURRENT-DEFECT (CPS test 2): after the STOP command the pouch keeps moving in the end zone. The model has no
        # state for "stop failed"; it only never sends POUCH_AT_END and logs at_end_timeout once. The belt surface is
        # not an input at all (running is the command, not an observation).
        model = travelling_model()
        model.observe(END, 0.15, 2.0)
        self.assertFalse(model.running)  # set by the model when the pouch entered the end zone
        for t in (2.5, 5.0, 10.0):
            self.assertEqual([], model.observe(END, 0.05, t)[0])
        self.assertEqual(["at_end_timeout"], model.observe(END, 0.05, 20.5)[1])
        self.assertEqual({"occupied": True, "at_end": False, "order_id": "ord-0001"}, model.state())
        self.assertNotIn("running", model.state())  # not published on /isaac/pharmacy/belt either
        self.assertNotIn("running", bridge.SCHEMAS[bridge.BELT])

    def test_r5_no_arrival_keeps_the_belt_occupied(self):
        # CURRENT-KEEP (A1-2): at_end_timeout does not free the belt; further Dispense calls get belt_occupied.
        model = belt.BeltModel(length=1.2, width=0.2, end_zone_length=0.15)
        model.accept("r001-0001", "ord-0001", 0.0)
        self.assertEqual(["at_end_timeout"], model.observe((0.1, 0.0, 0.0), 0.0, 20.5)[1])
        self.assertEqual([], model.observe((0.1, 0.0, 0.0), 0.0, 40.0)[1])
        self.assertTrue(model.occupied)
        self.assertEqual(belt.BELT_OCCUPIED, model.decide_dispense("ord-0002", ready=True, known_order=True))

    def test_r6_pick_notice_frees_the_belt_only_without_ur5(self):
        # CURRENT-KEEP for stub runs (A1-2 b, to be logged as mode=stub): without --ur5 a matching notice parks the
        # pouch and frees the belt without looking at the arm.
        # RESOLVED #244 with a real arm (A1-4): under --ur5 the notice is counted and skipped before the rule is
        # applied. The refusal of --ur5 with a stand-in is pinned in test_pharmacy_ur5_guard.py.
        notice = {"v": 1, "stamp": {"sec": 30, "nanosec": 0}, "epoch": 1, "order_id": "ord-0001",
                  "source": "POUCH_PICKED"}
        self.assertEqual((True, ""), bridge.pick_notice_applies(notice, 1, "ord-0001", True))
        handle = body("def handle_ros", "def setup_refill_demo")
        received = handle[handle.index("ros.take(bridge.PICK_NOTICE)"):handle.index("bridge.pick_notice_applies(")]
        self.assertIn("continue", received[received.index("if args.ur5:"):])
        self.assertNotIn("remove_pouch", received)
        applied = handle[handle.index("bridge.pick_notice_applies("):handle.index("bridge.RESET_REQUEST")]
        self.assertIn('remove_pouch("ros_pick_notice")', applied)
        self.assertIn("model.reset()", applied)
        self.assertNotIn("cell", applied)

    def test_r7_notice_from_an_old_epoch_is_ignored(self):
        # CURRENT-KEEP: after a reset the epoch moves on and a late notice for the old epoch does nothing.
        notice = {"v": 1, "stamp": {"sec": 30, "nanosec": 0}, "epoch": 1, "order_id": "ord-0001",
                  "source": "POUCH_PICKED"}
        applies, why = bridge.pick_notice_applies(notice, 2, "ord-0001", True)
        self.assertFalse(applies)
        self.assertIn("epoch 1 is not current 2", why)
        self.assertFalse(bridge.pick_notice_applies({**notice, "epoch": 2}, 2, "", False)[0])

    def test_r8_held_pouch_frees_the_belt_only_off_the_belt(self):
        # RESOLVED #251 (contract 11.1 a): on the first tick the UR5 holds the belt pouch the belt stays occupied and
        # state["pouch"] stays set; the model is freed only once the held pouch is outside the belt volume
        # (BeltModel.observe_held, pinned in test_pharmacy_ur5_held.py). 9/21: the stage runs this for **whichever
        # suction holds the pouch** — the pedestal cell or the combined asset's. It used to look at `cell` only, so a
        # pouch held by the combined arm left the belt, hit remove_pouch, and dropped out of pool.in_use; it then sat
        # in the tray invisible to the pouch sensor for the rest of the lap (lap12 ⑧).
        # After release off the belt state["pouch"] is None; RESOLVED #255 (VA-1): the ROS UR5 suction target is the
        # pouch nearest the TCP among the belt pouch and the carried deck pouches (test_pharmacy_ur5_suction.py).
        observe = body("def observe_belt", "def do_reset")
        held = observe[observe.index("holder.held is not None and holder.held[0] is obj"):observe.index("was_running")]
        self.assertIn("holder = cell if cell is not None else amr_suction", observe)
        self.assertLess(held.index("model.observe_held(frame)"), held.index("state.update(pouch=None"))
        self.assertIn("return", held[:held.index("state[\"carried\"]")])
        self.assertNotIn("model.reset()", held)
        self.assertNotIn('cell.suck(closed, state["pouch"])', STAGE_SOURCE)
        self.assertIn("cell.suck_nearest(candidates)", STAGE_SOURCE)

if __name__ == "__main__":
    unittest.main()
