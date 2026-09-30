"""Geometry adapter preserves the established ROS controller and wire layout."""
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'standalone'))
from p3sim import workcell_layout as W  # noqa: E402


def fixture():
    cells = {}
    for i in range(9):
        for col, kind in enumerate(('cylinder', 'module')):
            cells[f'shelf_{i}/r0c{col}'] = {
                'shelf': f'shelf_{i}', 'row': 0, 'col': col, 'type': kind, 'access': 'front',
                'surface': [float(i), 1., .5], 'height': .12 if col == 0 else .14,
                'size': {'diameter': .07, 'height': .12} if col == 0 else {'x': .06, 'y': .10, 'z': .14}}
    return {'version': 1, 'frame': 'hospital_world_m_z_up', 'cells': cells,
            'source_sha256': 'test', 'targets': {'round': {'center': [0., 1., 1.], 'axis': [0, 0, -1],
                        'depth': .2, 'floor_z': .8, 'inner_diameter': .2},
                        'module': {'entry_center': [1., 1., 1.], 'axis': [0, 1, 0],
                                   'depth': .2, 'opening': {'x': .2, 'z': .2}}}, 'obstacles': [],
            'rail': {'origin': [0., 0., 0.], 'x_stroke': 20., 'y_limits': [-.1, .33],
                     'z_limits': [0., 1.1], 'carriage_height': .25},
            'belt': {'start': [-1., 0., .5], 'length': 1.6, 'yaw': -1.57},
            'amr_start': [2., 2.], 'camera': {'eye': [0., -2., 2.], 'target': [0., 0., 0.], 'focal_mm': 20.}}


class WorkcellTests(unittest.TestCase):
    def test_compaction_preserves_union_and_inlet_semantics(self):
        def box(name, center, size):
            return {'name': name, 'center': center, 'size': size}
        outer = box('Dispenser_outer', [0., 0., 0.], [2., 2., 2.])
        inner = box('Dispenser_inner', [0., 0., 0.], [1., 1., 1.])
        edge = box('Dispenser_edge', [1., 0., 0.], [1., 1., 1.])
        inlet = box('RoundBinFloor', [0., 0., 0.], [.1, .1, .1])
        duplicate = dict(outer, name='Dispenser_duplicate')
        panel = box('NestedPanel', [0., 0., 0.], [.2, .2, .2])
        retained, covered = W.compact_body_obstacles([inner, outer, edge, inlet, duplicate, panel])
        self.assertEqual(retained, [outer, edge, inlet])
        self.assertEqual(covered, {'Dispenser_inner': 'Dispenser_outer',
                                   'Dispenser_duplicate': 'Dispenser_outer',
                                   'NestedPanel': 'Dispenser_inner'})
        self.assertEqual(W.compact_body_obstacles(retained), (retained, {}))
        only_inlet, covered_inlet = W.compact_body_obstacles(
            [inlet, box('SmallBody', [0., 0., 0.], [.05, .05, .05])])
        self.assertEqual([b['name'] for b in only_inlet], ['RoundBinFloor', 'SmallBody'])
        self.assertEqual(covered_inlet, {})
        sticking_out = box('RoundBinFloor', [2., 0., 0.], [1., 1., 1.])
        partial, partial_covered = W.compact_body_obstacles([outer, sticking_out])
        self.assertEqual([b['name'] for b in partial], ['Dispenser_outer', 'RoundBinFloor'])
        self.assertEqual(partial_covered, {})
        tighter, covered_tight = W.compact_body_obstacles(
            [outer, box('MidBody', [0., 0., 0.], [1.5, 1.5, 1.5]), panel])
        self.assertEqual([b['name'] for b in tighter], ['Dispenser_outer'])
        self.assertEqual(covered_tight['NestedPanel'], 'MidBody')
        self.assertEqual(covered_tight['MidBody'], 'Dispenser_outer')
        nested_inlet = box('RoundBinOuter', [0., 0., 0.], [2., 2., 2.])
        same_class, same_covered = W.compact_body_obstacles([nested_inlet, inlet])
        self.assertEqual([b['name'] for b in same_class], ['RoundBinOuter'])
        self.assertEqual(same_covered, {'RoundBinFloor': 'RoundBinOuter'})

    def test_compaction_keeps_payload_filter_union(self):
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'src/rokey_p3_manipulation'))
        from rokey_p3_manipulation.scene_v2 import OWN_TARGET_PREFIXES
        self.assertEqual(W.COLLISION_SKIP_CLASSES, tuple(OWN_TARGET_PREFIXES.items()))
        boxes = [{'name': 'RoundBinOuter', 'center': [0., 0., 0.], 'size': [2., 2., 2.]},
                 {'name': 'Dispenser_Blocker', 'center': [0., 0., 0.], 'size': [1., 1., 1.]}]

        def filtered(items):
            return [b['name'] for b in items if not b['name'].startswith(OWN_TARGET_PREFIXES['round'])]
        self.assertEqual(filtered(boxes), filtered(W.compact_body_obstacles(boxes)[0]))
        self.assertEqual(filtered(W.compact_body_obstacles(boxes)[0]), ['Dispenser_Blocker'])
        front = [{'name': 'DispenserFront', 'center': [0., 0., 0.], 'size': [2., 2., 2.]},
                 {'name': 'BodyPanel', 'center': [0., 0., 0.], 'size': [1., 1., 1.]}]

        def module_filtered(items):
            return [b['name'] for b in items if not b['name'].startswith(OWN_TARGET_PREFIXES['module'])]
        self.assertEqual(module_filtered(front), module_filtered(W.compact_body_obstacles(front)[0]))

    def load(self, data):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'workcell.json'
            path.write_text(json.dumps(data))
            return W.load(path)

    def test_geometry_does_not_replace_motion_profiles(self):
        args = SimpleNamespace(rail_speed=.8, rail_accel=1., joint_max_speed=[2., 3.])
        data = self.load(fixture())
        W.configure(args, data)
        self.assertEqual((args.rail_speed, args.rail_accel, args.joint_max_speed), (.8, 1., [2., 3.]))
        self.assertEqual(args.mode, 'ros')
        self.assertFalse(args.ros_refill_selfdemo)
        self.assertTrue(args.amr)
        message = W.inventory_for_planning(data)
        self.assertEqual(message['rail']['origin'], [0., 0., .25])
        self.assertEqual(len(message['cells']), 18)
        self.assertTrue(all(c['present'] for c in message['cells']))
        self.assertEqual(message['cells'][0]['pose']['xyz'][2], .56)
        self.assertEqual(W.room(args, data)['v2']['cells'], data['cells'])

    def test_rejects_inlets_dimensions_and_camera_before_isaac(self):
        for change in [lambda d: d['targets'].update(round={}),
                       lambda d: d['cells']['shelf_0/r0c0'].update(height=-1),
                       lambda d: d['targets']['module'].update(axis=[1, 0, 0]),
                       lambda d: d['camera'].update(focal_mm=float('nan'))]:
            with self.subTest(change=change):
                data = fixture()
                change(data)
                with self.assertRaises((ValueError, KeyError)):
                    self.load(data)

    def test_launch_snapshot_survives_file_change_and_matches_offline_source(self):
        import pharmacy_stage
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'layout.json'
            path.write_text(json.dumps(fixture()))
            args = pharmacy_stage.parse_args(['--workcell-layout', str(path), '--base-usd', 'base.usda',
                                              '--amr-combined', 'amr.usd'])
            before = pharmacy_stage.room(args)
            source = W.inventory_for_planning(args.workcell_data)['source']
            path.write_text('{}')
            self.assertEqual(pharmacy_stage.room(args), before)
            self.assertEqual(source, W.layout_source(args.workcell_data))
            self.assertEqual(source, 'hospital_workcell:'+args.workcell_data['_layout_sha256'])
            self.assertNotEqual(args.workcell_data.get('source_sha256'), args.workcell_data['_layout_sha256'])

    def test_rejects_duplicate_kind_and_nonfinite_geometry(self):
        data = fixture()
        data['cells']['shelf_0/r0c1']['type'] = 'cylinder'
        with self.assertRaisesRegex(ValueError, 'one cylinder'):
            self.load(data)
        data = fixture()
        data['rail']['y_limits'] = [float('nan'), .33]
        with self.assertRaisesRegex(ValueError, 'rail y_limits'):
            self.load(data)
        data = fixture()
        data['cells']['shelf_0/r0c0']['surface'][0] = float('inf')
        with self.assertRaisesRegex(ValueError, 'nonfinite'):
            self.load(data)

    def test_workcell_applies_hospital_scene_flags_unless_given(self):
        import pharmacy_stage
        from p3sim import base_scene
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'layout.json'
            path.write_text(json.dumps(fixture()))
            args = pharmacy_stage.parse_args(['--workcell-layout', str(path), '--base-usd', 'base.usda',
                                              '--amr-combined', 'amr.usd'])
            self.assertEqual(args.base_deactivate, list(base_scene.HOSPITAL_DEACTIVATE))
            self.assertEqual(args.base_rigid_off, list(base_scene.HOSPITAL_RIGID_OFF))
            self.assertEqual(list(args.pharmacy_origin), [0., 0., 0., 0.])
            args = pharmacy_stage.parse_args(['--workcell-layout', str(path), '--base-usd', 'base.usda',
                                              '--amr-combined', 'amr.usd', '--base-deactivate', 'only_this',
                                              '--base-rigid-off'])
            self.assertEqual(args.base_deactivate, ['only_this'])
            self.assertEqual(args.base_rigid_off, [])

    def test_hospital_usd_world_translate_is_zero(self):
        import re
        root = Path(__file__).resolve().parents[1]/'scenes'
        world = re.compile(r'def Xform "World"\s*\{.*?xformOp:translate = \(([^)]+)\)', re.S)
        for name in ('hospital_layout.usda', 'hospital_navigationv1.usda'):
            with self.subTest(name=name):
                match = world.search((root/name).read_text())
                self.assertIsNotNone(match)
                values = [float(part.strip()) for part in match.group(1).split(',')]
                self.assertEqual(values, [0.0, 0.0, 0.0])

    def test_layout_obstacles_reach_scene_v2_collision_query(self):
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'src/rokey_p3_manipulation'))
        from rokey_p3_manipulation import scene_v2
        data = fixture()
        data['obstacles'] = [{'name': 'TransferBlock', 'center': [0.5, 0.5, 0.5], 'size': [1., 1., 1.]}]
        message = W.inventory_for_planning(self.load(data))
        scene = scene_v2.parse_inventory(json.dumps(message))
        names = {box.name for box in scene_v2.obstacles_at(scene, (0., 0., 0.))}
        self.assertIn('TransferBlock', names)


class ShuffledStockTest(unittest.TestCase):
    """시드 재고: 종류와 빈 칸만 섞는다. 칸 자리와 종류 개수는 그대로다."""

    def cells(self):
        return fixture()['cells']

    def test_same_seed_gives_the_same_placement(self):
        first = W.shuffled_stock(self.cells(), 7, empty=4)
        second = W.shuffled_stock(self.cells(), 7, empty=4)
        self.assertEqual(first, second)
        other, _present = W.shuffled_stock(self.cells(), 8, empty=4)
        self.assertNotEqual(first[0], other)

    def test_kind_counts_and_cell_positions_do_not_change(self):
        source = self.cells()
        cells, _present = W.shuffled_stock(source, 3, empty=4)
        self.assertEqual(sorted(source), sorted(cells))
        self.assertEqual(sorted(c['type'] for c in source.values()),
                         sorted(c['type'] for c in cells.values()))
        for cell_id, cell in cells.items():
            self.assertEqual(source[cell_id]['surface'], cell['surface'])
            self.assertEqual(source[cell_id]['access'], cell['access'])

    def test_size_and_height_follow_the_drawn_type(self):
        source = self.cells()
        shapes = {c['type']: (c['size'], c['height']) for c in source.values()}
        cells, _present = W.shuffled_stock(source, 11, empty=0)
        for cell in cells.values():
            size, height = shapes[cell['type']]
            self.assertEqual(size, cell['size'])
            self.assertEqual(height, cell['height'])

    def test_empty_cells_never_clear_a_whole_kind(self):
        source = self.cells()
        for seed in range(25):
            cells, present = W.shuffled_stock(source, seed, empty=len(source))
            left = {cells[c]['type'] for c, ok in present.items() if ok}
            self.assertEqual({'cylinder', 'module'}, left, seed)

    def test_the_asked_number_of_cells_is_empty(self):
        _cells, present = W.shuffled_stock(self.cells(), 5, empty=4)
        self.assertEqual(4, sum(1 for ok in present.values() if not ok))
        _cells, none_empty = W.shuffled_stock(self.cells(), 5, empty=0)
        self.assertTrue(all(none_empty.values()))


class PrepareIntegrationTest(unittest.TestCase):
    """준비기가 내놓는 투입구 좌표는 기준 에셋 앵커다(재범 9/22 #496, dispenser README)."""

    def setUp(self):
        import ast
        root = Path(__file__).resolve().parents[2]
        self.tree = ast.parse((root/'sim/standalone/prepare_workcell_integration.py').read_text())
        self.asset = json.loads((root/'src/rokey_p3_description/models/dispenser/asset.json').read_text())

    def targets(self):
        import ast
        prepare = next(n for n in self.tree.body
                       if isinstance(n, ast.FunctionDef) and n.name == 'prepare')
        for node in ast.walk(prepare):
            if (isinstance(node, ast.Assign) and len(node.targets) == 1
                    and getattr(node.targets[0], 'id', None) == 'targets'):
                return ast.literal_eval(node.value)
        raise AssertionError('preparer has no targets literal')

    def test_inlet_targets_are_the_reviewed_anchors(self):
        origin = self.asset['origin_in_hospital']
        targets = self.targets()
        for anchor, key, point in [('PillOpening', 'round', 'center'),
                                   ('ModuleEntry', 'module', 'entry_center')]:
            want = [a+b for a, b in zip(origin, self.asset['anchors_local'][anchor], strict=True)]
            for got, expected in zip(targets[key][point], want, strict=True):
                self.assertAlmostEqual(got, expected, places=6)

    def test_shelves_get_measured_boxes_not_a_mesh_collider(self):
        """선반은 층 판마다 얇은 상자와 모서리 기둥 넷이다(재범 화면 9/23: 볼록 껍질이 판을 기울였다)."""
        import ast
        source = (Path(__file__).resolve().parents[2]
                  /'sim/standalone/prepare_workcell_integration.py').read_text()
        assert 'SHELF_APPROXIMATION' not in source           # 선반 메시 근사 값은 더 없다
        assert '--shelf-approximation' not in source
        prepare = next(n for n in self.tree.body
                       if isinstance(n, ast.FunctionDef) and n.name == 'prepare')
        calls = [n for n in ast.walk(prepare)
                 if isinstance(n, ast.Call) and getattr(n.func, 'id', None) == 'collider']
        self.assertEqual(2, len(calls))                      # 판 하나, 기둥 하나(둘 다 반복 안)
        self.assertIn('MeshCollisionAPI', source)            # 조제기 몸통은 그대로 쓴다
        shelf_mesh = [n for n in ast.walk(prepare)
                      if isinstance(n, ast.Attribute) and n.attr == 'CreateApproximationAttr']
        self.assertEqual(1, len(shelf_mesh))                 # 남은 근사는 조제기 것 하나뿐이다

    def test_preparer_authors_no_inlet_offset(self):
        import ast
        body = [n for n in self.tree.body if not (isinstance(n, ast.Expr)
                                                  and isinstance(n.value, ast.Constant))]
        code = '\n'.join(ast.dump(n) for n in body)
        for banned in ('pill_offset', 'pill-offset', 'PillIntegrationBracket', 'integration'):
            self.assertNotIn(banned, code)


if __name__ == '__main__':
    unittest.main()
