import unittest

from sim.standalone.p3sim.shelf_stock import mix_medicine, pack_stock


class ShelfStockTest(unittest.TestCase):
    def boards(self):
        return [{'z': z, 'min': [2., 4.], 'max': [2.855, 4.76]} for z in (.17, .50, .88, 1.25, 1.63, 2.)]

    def test_all_five_tiers_are_stocked_below_roof(self):
        cells = pack_stock('shelf', self.boards())
        self.assertEqual(len(cells), 150)
        self.assertEqual({c['row'] for c in cells.values()}, set(range(5)))
        self.assertEqual(sum(c['front_accessible'] for c in cells.values()), 30)
        self.assertTrue(all(c['surface'][2]+c['height'] < 2. for c in cells.values()))

    def test_positions_have_no_overlapping_cylinders(self):
        cells = list(pack_stock('shelf', self.boards()).values())
        for i, cell in enumerate(cells):
            for other in cells[i+1:]:
                if cell['row'] == other['row']:
                    a, b = cell['surface'], other['surface']
                    self.assertGreater((a[0]-b[0])**2+(a[1]-b[1])**2, .07**2)

    def test_short_headroom_is_rejected(self):
        boards = self.boards()
        boards[1]['z'] = .25
        with self.assertRaisesRegex(ValueError, 'does not fit'):
            pack_stock('shelf', boards)

    def test_overlapping_pitch_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'dimensions'):
            pack_stock('shelf', self.boards(), pitch=.06)

    def test_quarter_modules_are_distributed_across_all_tiers(self):
        original = pack_stock('shelf', self.boards())
        cells = mix_medicine(original)
        self.assertEqual(sum(c['type'] == 'module' for c in cells.values()), 38)
        for row in range(5):
            kinds = [c['type'] for c in cells.values() if c['row'] == row]
            self.assertIn('module', kinds)
            self.assertIn('cylinder', kinds)
        self.assertTrue(all(c['type'] == 'cylinder' for c in original.values()))

    def test_module_dimensions_and_type_match(self):
        cells = mix_medicine(pack_stock('shelf', self.boards()))
        for key, cell in cells.items():
            self.assertEqual(cell['surface'], pack_stock('shelf', self.boards())[key]['surface'])
            if cell['type'] == 'module':
                self.assertEqual(cell['height'], cell['size']['z'])
                self.assertEqual(cell['size'], {'x': .06, 'y': .10, 'z': .14})

    def test_cylinder_headroom_is_not_enough_for_module(self):
        boards = self.boards()
        boards[1]['z'] = .35
        with self.assertRaisesRegex(ValueError, 'module does not fit'):
            mix_medicine(pack_stock('shelf', boards))
