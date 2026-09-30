"""Dispense resend for the tracked pouch (contract 11.2). No Isaac. Vectors D03/D04 cover the same in
test_pharmacy_contract_vectors.py; these pin the model rule and the stage wiring.

    python3 -m unittest discover -s sim/tests -p 'test_[mp]*.py'
"""

import sys
import unittest
from pathlib import Path

STANDALONE = Path(__file__).resolve().parents[1] / "standalone"
sys.path.insert(0, str(STANDALONE))

from p3sim import belt  # noqa: E402


def accepted(fail_closed=False):
    model = belt.BeltModel(1.6, 0.25, 0.15, fail_closed=fail_closed)
    model.accept("r001-0001", "ord-0001", 0.0)
    return model


class IsResendTests(unittest.TestCase):
    def test_same_request_and_order_while_tracked(self):
        self.assertTrue(accepted().is_resend("r001-0001", "ord-0001"))

    def test_other_request_or_order_is_not_a_resend(self):
        model = accepted()
        self.assertFalse(model.is_resend("r001-0001", "ord-0002"))
        self.assertFalse(model.is_resend("r002-0001", "ord-0001"))
        self.assertEqual(belt.BELT_OCCUPIED, model.decide_dispense("ord-0002", True, True))

    def test_not_after_release_reset_or_loss(self):
        free = belt.BeltModel(1.6, 0.25, 0.15)
        self.assertFalse(free.is_resend("", ""))  # empty ids of a free belt never match
        released = accepted()
        released.reset()
        self.assertFalse(released.is_resend("r001-0001", "ord-0001"))
        lost = accepted(fail_closed=True)
        lost.observe(None, None, 1.0)
        self.assertTrue(lost.occupied)
        self.assertFalse(lost.is_resend("r001-0001", "ord-0001"))


class StageWiringTests(unittest.TestCase):
    def test_resend_answers_before_the_rules_and_does_nothing_else(self):
        source = (STANDALONE / "pharmacy_stage.py").read_text()
        dispense = source[source.index("        def dispense(request_id, order_id):"):source.index("def observe_belt")]
        resend = dispense[dispense.index("model.is_resend("):dispense.index("ready = ")]
        self.assertIn('state["pouch"] is not None', resend)
        self.assertIn('return True, ""', resend)
        for action in ("model.accept", "spawn_pouch", "set_belt", "emit("):
            self.assertNotIn(action, resend)


if __name__ == "__main__":
    unittest.main()
