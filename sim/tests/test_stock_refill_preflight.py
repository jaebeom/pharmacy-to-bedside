import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'src/rokey_p3_manipulation'))
sys.path.insert(0, str(ROOT/'sim/standalone'))

from check_stock_refill import select_cells, with_stock_obstacles  # noqa: E402
from rokey_p3_manipulation import pick_plan, scene_v2  # noqa: E402
from rokey_p3_manipulation.clearance import Box  # noqa: E402


class StockPreflightTest(unittest.TestCase):
    def setUp(self):
        cells = tuple(scene_v2.CellV2(f's{i}/c{j}', 'cylinder', 'drug-amox', True, 'front',
                                     (i, j, 1.), (.07, .07, .12)) for i in range(3) for j in range(2))
        self.scene = scene_v2.Scene(cells, {}, (Box('wall', (0, 0, 0), (1, 1, 1)),), {}, (), (), (), ())
        self.raw = {'cells': [{'cell': c.cell_id, 'shelf': c.cell_id.split('/')[0],
                               'front_accessible': True} for c in cells]}

    def test_deterministic_selection_covers_three_distinct_shelves(self):
        first = select_cells(self.scene, self.raw, pick_plan.CellPicker(42))
        self.assertEqual(first, select_cells(self.scene, self.raw, pick_plan.CellPicker(42)))
        self.assertEqual(len({c.cell_id.split('/')[0] for c, _ in first}), 3)

    def test_only_explicitly_accessible_cells_are_selected(self):
        for c in self.raw['cells']:
            c['front_accessible'] = c['cell'].endswith('c0')
        self.assertTrue(all(c.cell_id.endswith('c0') for c, _ in
                            select_cells(self.scene, self.raw, pick_plan.CellPicker(42))))

    def test_insufficient_shelves_fail_before_motion(self):
        for c in self.raw['cells']:
            c['shelf'] = 'same'
        with self.assertRaisesRegex(ValueError, 'three distinct'):
            select_cells(self.scene, self.raw, pick_plan.CellPicker(42))

    def test_all_other_present_stock_remains_an_obstacle(self):
        target = self.scene.cells[0]
        augmented = with_stock_obstacles(self.scene, target)
        self.assertEqual(len(augmented.obstacles), 6)
        names = {o.name for o in augmented.obstacles}
        self.assertNotIn('Stock_'+target.cell_id, names)
        self.assertIn('wall', names)
        self.assertTrue(all('Stock_'+c.cell_id in names for c in self.scene.cells[1:]))
        self.assertEqual(len(self.scene.obstacles), 1)
