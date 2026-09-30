"""Arm aisle box over the belt end (p3sim/aisle.py). Margins are inputs only; no defaults. No Isaac.

    python3 -m unittest discover -s sim/tests -p 'test_[mp]*.py'
"""

import math
import sys
import unittest
from pathlib import Path

STANDALONE = Path(__file__).resolve().parents[1] / "standalone"
sys.path.insert(0, str(STANDALONE))

from p3sim import aisle, belt  # noqa: E402

L, W, END = 1.6, 0.25, 0.15  # stage defaults (sim/scenes/README.md 3)


class AisleBoxTests(unittest.TestCase):
    def test_box_from_the_formula(self):
        box = aisle.belt_aisle_box(L, W, END, 0.1, 0.2, 0.05, 0.6)
        self.assertEqual(("belt", ""), (box.frame, box.problem))
        for got, want in zip(box.lower + box.upper, (1.35, -0.175, 0.0, 1.8, 0.175, 0.6), strict=True):
            self.assertAlmostEqual(want, got)

    def test_whole_belt_choice_is_just_other_inputs(self):
        # decision 20 option 2 ("the whole belt is the aisle"): m_along = L - end_zone, same function
        box = aisle.belt_aisle_box(L, W, END, L - END, 0.2, 0.05, 0.6)
        self.assertAlmostEqual(0.0, box.lower[0])

    def test_any_unset_margin_gives_no_box(self):
        for i, name in enumerate(aisle.MARGINS):
            margins = [0.1, 0.2, 0.05, 0.6]
            margins[i] = None
            with self.subTest(unset=name):
                box = aisle.belt_aisle_box(L, W, END, *margins)
                self.assertEqual((None, None), (box.lower, box.upper))
                self.assertIn(name, box.problem)
                self.assertIn("decision 20", box.problem)
        problem = aisle.belt_aisle_box(L, W, END, None, None, None, None).problem
        self.assertTrue(all(name in problem for name in aisle.MARGINS))

    def test_invalid_values_give_no_box(self):
        for margins in ((-0.1, 0.2, 0.05, 0.6), (0.1, 0.2, 0.05, 0.0), (0.1, math.nan, 0.05, 0.6),
                        (0.1, 0.2, True, 0.6)):
            with self.subTest(margins=margins):
                self.assertIsNone(aisle.belt_aisle_box(L, W, END, *margins).lower)
        self.assertIsNone(aisle.belt_aisle_box(0.0, W, END, 0.1, 0.2, 0.05, 0.6).lower)
        self.assertIsNone(aisle.belt_aisle_box(L, W, 2.0, 0.1, 0.2, 0.05, 0.6).lower)

    def test_no_default_margins(self):
        with self.assertRaises(TypeError):
            aisle.belt_aisle_box(L, W, END)

    def test_world_from_belt_inverts_belt_frame(self):
        start, yaw = (1.35, 1.0, 0.75), 0.4
        m = aisle.world_from_belt(start, yaw)
        local = (0.7, -0.05, 0.1)
        world = tuple(sum(m[r][c] * v for c, v in enumerate((*local, 1.0))) for r in range(3))
        for got, want in zip(belt.belt_frame(world, start, yaw), local, strict=True):
            self.assertAlmostEqual(want, got)


if __name__ == "__main__":
    unittest.main()
