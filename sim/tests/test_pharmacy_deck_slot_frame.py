"""deck_slot_N frame origin = centre of the slot floor's top face (결정 23, 재범 9/20). --ur5 only. No Isaac.

    python3 -m unittest discover -s sim/tests -p 'test_[mp]*.py'
"""

import sys
import unittest
from pathlib import Path

STANDALONE = Path(__file__).resolve().parents[1] / "standalone"
sys.path.insert(0, str(STANDALONE))

from p3sim import layout  # noqa: E402

ROOM = layout.default_layout()
CENTER, COUNT, SIZE, WALL = ROOM["deck_center"], ROOM["deck_count"], ROOM["deck_slot_size"], ROOM["deck_wall"]


class DeckSlotFrameTests(unittest.TestCase):
    def test_frame_is_the_floor_top_face_centre(self):
        boxes, centers = layout.deck_boxes(CENTER, COUNT, SIZE, WALL)
        frames = layout.deck_slot_frames(CENTER, COUNT, SIZE, WALL)
        floors = {box.name: box for box in boxes if box.name.endswith("Floor")}
        self.assertEqual(COUNT, len(frames))
        for i, frame in enumerate(frames):
            floor = floors[f"DeckSlot{i + 1}Floor"]
            self.assertAlmostEqual(floor.center[0], frame[0])
            self.assertAlmostEqual(floor.center[1], frame[1])
            self.assertAlmostEqual(floor.center[2] + floor.size[2] / 2.0, frame[2])  # top face, not the slab centre
            self.assertAlmostEqual(CENTER[2] + WALL, frame[2])

    def test_place_target_relative_to_the_frame(self):
        _boxes, centers = layout.deck_boxes(CENTER, COUNT, SIZE, WALL)
        for center, frame in zip(centers, layout.deck_slot_frames(CENTER, COUNT, SIZE, WALL), strict=True):
            self.assertEqual(center[:2], frame[:2])
            self.assertAlmostEqual(SIZE[2] / 2.0 - WALL, center[2] - frame[2])  # 0.012 m with the defaults
        self.assertAlmostEqual(0.012, SIZE[2] / 2.0 - WALL)

    def test_ur5_cell_publishes_the_top_child(self):
        source = (STANDALONE / "p3sim" / "ur5_cell.py").read_text()
        self.assertIn('f"{self.root}/Deck/DeckSlot{i + 1}Floor/{L.DECK_FRAME_CHILD}"', source)
        self.assertIn("top.AddTranslateOp().Set(Gf.Vec3d(0.0, 0.0, 0.5))", source)  # half of the unit cube: top face
        self.assertNotIn('deck_paths = [f"{self.root}/Deck/DeckSlot{i + 1}Floor" for', source)
        self.assertEqual("Top", layout.DECK_FRAME_CHILD)


if __name__ == "__main__":
    unittest.main()
