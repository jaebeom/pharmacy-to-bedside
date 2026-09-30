"""Reject stale/incomplete readiness and stopped clocks before motion requests."""
import copy
import sys
import subprocess
import tempfile
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'standalone'))
from p3sim.trial_preflight import (  # noqa: E402
    cache_ready, clock_problem, geometry_key, home_confirmed, plan_cache_invalidate, plan_cache_payload)


def inventory():
    return {'v': 1, 'scene': 'v2', 'source': 'test', 'items': {}, 'rail': {}, 'targets': {}, 'obstacles': [],
            'cells': [{'cell': str(i), 'type': 'cylinder', 'item': 'drug-amox', 'present': True,
                       'shelf': str(i), 'pose': [i, 0, 0]} for i in range(3)]}


def cache(solved=3, total=3, failed=None, source='test'):
    return {'solved': solved, 'total': total, 'failed': {} if failed is None else failed, 'source': source}


class TrialPreflightTests(unittest.TestCase):
    def test_motion_cli_rejects_missing_layout_before_ros(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)/'must-not-be-created'
            script = Path(__file__).resolve().parents[1]/'standalone/run_workcell_refill_trials.py'
            result = subprocess.run([sys.executable, str(script), '--output', str(output)],
                                    capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, 2)
            self.assertIn('motion trials require --layout', result.stderr)
            self.assertFalse(output.exists())

    def test_current_complete_summary_is_required(self):
        self.assertTrue(cache_ready(cache(), inventory()))
        for message in [{}, cache(source='other'), cache(total=2), cache(solved=2, failed={'0': 'no plan'}),
                        cache(failed={'missing': 'x'})]:
            with self.subTest(message=message):
                self.assertFalse(cache_ready(message, inventory()))

    def test_three_feasible_present_shelves_are_required(self):
        self.assertFalse(cache_ready(cache(2, 3, {'0': 'no plan'}), inventory()))
        data = inventory()
        data['cells'][0]['present'] = False
        self.assertFalse(cache_ready(cache(), data))
        data = inventory()
        data['cells'][0]['shelf'] = '1'
        self.assertFalse(cache_ready(cache(), data))

    def test_inventory_republish_does_not_invalidate_matching_source(self):
        self.assertTrue(cache_ready(cache(), inventory()))

    def test_geometry_changes_invalidate_but_presence_does_not(self):
        original = inventory()
        changed = copy.deepcopy(original)
        changed['cells'][0]['present'] = False
        self.assertEqual(geometry_key(original), geometry_key(changed))
        changed['cells'][0]['pose'][0] = 10
        self.assertNotEqual(geometry_key(original), geometry_key(changed))

    def test_clock_must_advance_recently_and_never_reverse(self):
        self.assertIsNone(clock_problem([1., 2.], 1, 5., 4.9))
        for samples, count, updated in [([1., 1.], 1, 5.), ([2., 1.], 1, 5.),
                                       ([1., 2.], 2, 5.), ([1., 2.], 1, 3.)]:
            self.assertIsNotNone(clock_problem(samples, count, 5., updated))

    def test_home_confirmed_accepts_same_spin_after_one_heartbeat(self):
        self.assertTrue(home_confirmed([(1.0, True)], 1.05, 1.30))
        self.assertFalse(home_confirmed([(1.0, True)], 1.05, 1.10))
        self.assertFalse(home_confirmed([(0.1, True)], 1.05, 1.30))
        self.assertTrue(home_confirmed([(1.0, True), (1.10, True)], 1.05, 1.10))
        self.assertFalse(home_confirmed([(1.10, False)], 1.05, 1.20))
        self.assertFalse(home_confirmed([(1.0, True)], 1.05, 6.05))

    def test_stale_latched_cache_is_not_ready_for_new_source(self):
        from types import SimpleNamespace
        old = plan_cache_payload(
            {'0': SimpleNamespace(steps=object(), why=''),
             '1': SimpleNamespace(steps=object(), why=''),
             '2': SimpleNamespace(steps=object(), why='')},
            'A', 1, 1)
        data = inventory()
        data['source'] = 'B'
        self.assertIsNone(plan_cache_payload(
            {'0': SimpleNamespace(steps=object(), why=''),
             '1': SimpleNamespace(steps=object(), why=''),
             '2': SimpleNamespace(steps=object(), why='')},
            'B', 1, 2))
        self.assertFalse(cache_ready(plan_cache_invalidate('B', 2), data))
        self.assertFalse(cache_ready(old, data))


if __name__ == '__main__':
    unittest.main()
