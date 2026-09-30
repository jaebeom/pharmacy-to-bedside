"""The UR5 stand's footprint, and the quoted-string shape the coordinate arguments take. No Isaac.

L3-2 12d (9/20): with --ur5-base "3.25 0.55 0.80" the stand became a 0.30 x 0.30 x 0.80 column under the shoulder and
upper_arm hit it 65 times at impulse 162 (z 0.45 had 3 at 17.9). --ur5-pedestal-size makes that obstacle narrower for
a diagnostic run without changing the shoulder height. The default stays what every run so far used.

    python3 -m unittest discover -s sim/tests -p 'test_[mp]*.py'
"""

import argparse
import sys
import unittest
from pathlib import Path

STANDALONE = Path(__file__).resolve().parents[1] / "standalone"
sys.path.insert(0, str(STANDALONE))

from p3sim import common, ur5_cell  # noqa: E402


class PedestalFootprint(unittest.TestCase):
    def test_default_is_what_the_stage_always_used(self):
        """Not giving the argument must keep 0.30 x 0.30, so the demo path and every earlier run are unchanged."""
        self.assertEqual(ur5_cell.pedestal_footprint(None), (0.30, 0.30))
        self.assertEqual(ur5_cell.PEDESTAL_SIZE, (0.30, 0.30))

    def test_requested_footprint_is_used(self):
        self.assertEqual(ur5_cell.pedestal_footprint((0.12, 0.12)), (0.12, 0.12))

    def test_footprint_may_be_rectangular(self):
        self.assertEqual(ur5_cell.pedestal_footprint((0.12, 0.20)), (0.12, 0.20))

    def test_zero_or_negative_is_refused(self):
        """A zero-scale cuboid is not a stand; fail at build rather than leave the arm standing on nothing."""
        for bad in ((0.0, 0.12), (0.12, -0.3)):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                ur5_cell.pedestal_footprint(bad)

    def test_height_is_separable_too(self):
        """Was "only the footprint is separable, or the arm floats". L3-2 12h showed narrowing has a floor: the arm
        turns in a plane through the base axis, so a column under the shoulder is in the sweep however thin it is.
        A short stand does leave the robot standing clear of it, and that is wanted - the robot is fixed to the world.
        See PedestalHeight for what the height argument does.
        """
        self.assertEqual(ur5_cell.pedestal_height(None, 0.90), 0.90)
        self.assertEqual(ur5_cell.pedestal_height(0.45, 0.90), 0.45)


class PedestalHeight(unittest.TestCase):
    """L3-2 12h: narrowing the footprint has a floor, because the arm turns in a plane through the base axis."""

    def test_default_is_the_base_height(self):
        """Not giving the argument must keep the stand reaching the robot, as every run so far had it."""
        self.assertEqual(ur5_cell.pedestal_height(None, 0.90), 0.90)
        self.assertEqual(ur5_cell.pedestal_height(None, 0.45), 0.45)

    def test_a_shorter_stand_is_allowed(self):
        """On purpose: the robot is fixed to the world, so a stand that stops short carries nothing."""
        self.assertEqual(ur5_cell.pedestal_height(0.45, 0.90), 0.45)

    def test_equal_to_the_base_is_allowed(self):
        self.assertEqual(ur5_cell.pedestal_height(0.90, 0.90), 0.90)

    def test_zero_or_negative_is_refused(self):
        for bad in (0.0, -0.2):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                ur5_cell.pedestal_height(bad, 0.90)

    def test_taller_than_the_base_is_refused(self):
        """A stand above the robot base would swallow the robot; that is never what a run wants."""
        with self.assertRaises(ValueError) as caught:
            ur5_cell.pedestal_height(1.20, 0.90)
        self.assertIn("0.9", str(caught.exception))

    def test_the_cuboid_uses_the_height_for_both_centre_and_scale(self):
        """The stand stands on the floor, so its centre is half its own height, not half the base height.

        Read from the source because building the cuboid needs Isaac.
        """
        source = (STANDALONE / "p3sim" / "ur5_cell.py").read_text()
        self.assertIn("position=np.array((bx, by, ph / 2.0))", source)
        self.assertIn("scale=np.array((px, py, ph))", source)
        self.assertNotIn("bz / 2.0", source)


class QuotedCoordinateArguments(unittest.TestCase):
    """--ur5-base and friends take ONE string, not three tokens. On 9/20 a run died on `--ur5-base 3.25 0.55 0.80`."""

    def test_three_tokens_are_refused_with_a_message_naming_the_shape(self):
        with self.assertRaises(argparse.ArgumentTypeError) as caught:
            common.xyz("3.25")
        self.assertIn("'x y z'", str(caught.exception))
        self.assertIn("ONE quoted argument", str(caught.exception))

    def test_one_string_parses(self):
        self.assertEqual(common.xyz("3.25 0.55 0.80"), (3.25, 0.55, 0.80))
        self.assertEqual(common.xyz("3.25,0.55,0.80"), (3.25, 0.55, 0.80))

    def test_xy_takes_one_string_too(self):
        self.assertEqual(common.xy("0.12 0.12"), (0.12, 0.12))
        self.assertEqual(common.xy("0.12,0.12"), (0.12, 0.12))
        with self.assertRaises(argparse.ArgumentTypeError):
            common.xy("0.12")
        with self.assertRaises(argparse.ArgumentTypeError):
            common.xy("0.12 0.12 0.12")

    def test_xy_refuses_a_non_positive_footprint(self):
        for bad in ("0 0.12", "-0.1 0.12"):
            with self.subTest(bad=bad), self.assertRaises(argparse.ArgumentTypeError):
                common.xy(bad)

    def test_help_shows_the_quoted_shape(self):
        """The trap on 9/20 was that --help printed `--ur5-base UR5_BASE` while neighbours printed `ROW COL`."""
        source = (STANDALONE / "pharmacy_stage.py").read_text()
        for line in ('metavar=\'"x y z"\'', 'metavar=\'"x y"\''):
            self.assertIn(line, source)


if __name__ == "__main__":
    unittest.main()
