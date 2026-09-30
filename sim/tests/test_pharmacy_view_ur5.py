"""The `ur5` viewport preset: the loading cell, seen from the corridor. No Isaac.

실습12d-v (9/20 master02): the window-mode UR5 run was recorded with `--view none` because no preset frames the cell,
and the arm came out a thumbnail in one corner. `overview` cannot be used: the cell is about 3.2 m off its axis, past
the 60 deg frame. This preset stands beside the pedestal at its top height and looks almost along +y, so the
pedestal's top face is edge-on - that is what tells "the upper arm rests on the top" apart from "it is wedged at the
edge", which two capture descriptions could not settle.

    python3 -m unittest discover -s sim/tests -p 'test_[mp]*.py'
"""

import sys
import unittest
from pathlib import Path

STANDALONE = Path(__file__).resolve().parents[1] / "standalone"
sys.path.insert(0, str(STANDALONE))

from p3sim import layout as L  # noqa: E402
from p3sim import views  # noqa: E402

ROOM = L.default_layout()
WALL_FACE = ROOM["wall_x"] + ROOM["wall_thickness"] / 2.0  # corridor side of the corridor wall
BASE = ROOM["ur5_base"]

# What the capture has to show at once: the stand top and bottom, the shoulder's working height, the belt end and the
# pouch on it, the wall face the elbow is suspected of reaching, and both ends of the deck.
SUBJECTS = {
    "pedestal_top": (BASE[0], BASE[1], BASE[2]),
    "pedestal_top_raised": (BASE[0], BASE[1], 0.80),  # the diagnostic height used from 실습12d on
    "pedestal_foot": (BASE[0], BASE[1], 0.0),
    "shoulder_working_height": (BASE[0], BASE[1], 1.40),
    "belt_end": (2.95, 1.00, ROOM["belt_top"]),
    "pouch_on_belt": (2.806, 0.993, 0.755),
    "wall_face_low": (WALL_FACE, BASE[1], 0.30),
    "wall_face_high": (WALL_FACE, BASE[1], 1.40),
    "deck_first": (2.98, 0.05, 0.47),
    "deck_last": (3.62, 0.05, 0.47),
}


class Ur5View(unittest.TestCase):
    def setUp(self):
        self.eye, self.target = views.UR5_VIEW

    def test_it_is_selectable_and_not_a_pharmacy_view(self):
        """--view takes it, but the room-side checks in test_pharmacy_stage must not claim it."""
        self.assertIn("ur5", views.CORRIDOR_VIEW_NAMES)
        self.assertNotIn("ur5", views.VIEW_NAMES)
        self.assertIn("ur5", views.ALL_VIEW_NAMES)

    def test_both_scenes_use_the_same_pose(self):
        """The cell's coordinates come from the shared room, so v1 and v2 see it the same way."""
        for scene in ("v1", "v2"):
            self.assertEqual(views.view(scene, "ur5"), views.UR5_VIEW)

    def test_the_eye_stands_in_the_corridor(self):
        """Unlike every other view. Standing on the pharmacy side would put the wall between it and the cell."""
        self.assertGreater(self.eye[0], WALL_FACE)
        self.assertGreater(self.eye[2], 0.0)

    def test_every_subject_is_in_frame_at_both_aspects(self):
        for name, point in SUBJECTS.items():
            for aspect in (views.ASPECT, views.HALF_SCREEN_ASPECT):
                with self.subTest(subject=name, aspect=round(aspect, 2)):
                    self.assertTrue(views.in_frame(self.eye, self.target, point, aspect=aspect))

    def test_the_view_is_near_level_with_the_pedestal_top(self):
        """A steep view flattens the top face and the wedge and the rest look alike from above."""
        run = ((self.target[0] - self.eye[0]) ** 2 + (self.target[1] - self.eye[1]) ** 2) ** 0.5
        self.assertLess(abs(self.eye[2] - self.target[2]) / run, 0.10)
        # The stand's top is 0.45 by default and 0.80 in the diagnostic runs, so the eye sits between the two and
        # neither top face is seen from far above.
        self.assertGreaterEqual(self.eye[2], BASE[2])
        self.assertLessEqual(self.eye[2], 0.85)

    def test_the_wall_face_and_a_candidate_elbow_separate_horizontally(self):
        """The question is whether the elbow is in front of the wall face or past it, so the two must not overlap.

        The candidate is where a correct elbow-up solution for the pouch puts the elbow (2R geometry, base z 0.80).
        """
        elbow = (2.976, 0.823, 1.065)
        on_wall = (WALL_FACE, elbow[1], elbow[2])
        gap = abs(views.frame_coords(self.eye, self.target, elbow)[1]
                  - views.frame_coords(self.eye, self.target, on_wall)[1])
        self.assertGreater(gap, 0.05)  # about 4% of the frame width or more

    def test_nothing_in_the_room_blocks_the_sight_line(self):
        boxes = L.wall_boxes(ROOM["wall_x"], ROOM["wall_y_range"], ROOM["wall_height"], ROOM["wall_thickness"],
                             (0.845, 1.155), (0.60, 0.95), ROOM["door_y"], ROOM["door_width"])
        for step in range(21):
            point = tuple(e + (t - e) * step / 20 for e, t in zip(self.eye, self.target, strict=True))
            for box in boxes:
                inside = all(abs(point[i] - box.center[i]) <= box.size[i] / 2.0 for i in range(3))
                self.assertFalse(inside, f"sight line crosses {box.name}")


if __name__ == "__main__":
    unittest.main()
