"""An action success alone must not produce a verified integration result."""
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'standalone'))
from summarize_workcell_trial import summarize  # noqa: E402


class TrialReportTests(unittest.TestCase):
    def test_requires_matching_cell_attach_release_and_home(self):
        events = [json.dumps({'topic': 'feedback', 'message': {
            'feedback': {'phase': 'plan cell=shelf_74/r0c0 kind=cylinder'}}})]
        result = {'attempt': 1, 'result': {'success': True}, 'home_observed': True,
                  'last_release': {'cell': 'shelf_74/r0c0', 'target': 'round'}}
        stage = ('refill_ros grasp attached distance=0.04 cell=shelf_74/r0c0 sim_time=5\n'
                 'refill_ros released cell=shelf_74/r0c0 type=cylinder target=round\n')
        good = summarize(events, [result], stage)
        self.assertTrue(good['attempts'][0]['verified'])
        self.assertFalse(good['completed_three'])
        for bad_stage, bad_result in [('', result), (stage, dict(result, home_observed=False)),
                (stage, dict(result, last_release={'cell': 'shelf_75/r0c0', 'target': 'round'}))]:
            self.assertFalse(summarize(events, [bad_result], bad_stage)['attempts'][0]['verified'])

    def test_three_results_must_refer_to_three_distinct_selected_cells(self):
        def batch(cells):
            events, results, logs = [], [], []
            for attempt, cell in enumerate(cells, 1):
                events.append(json.dumps({'topic': 'feedback', 'message': {
                    'feedback': {'phase': f'plan cell={cell} kind=cylinder'}}}))
                results.append({'attempt': attempt, 'result': {'success': True}, 'home_observed': True,
                                'last_release': {'cell': cell, 'target': 'round'}})
                logs.extend([f'refill_ros grasp attached distance=0.04 cell={cell}',
                             f'refill_ros released cell={cell} type=cylinder target=round'])
            return events, results, '\n'.join(logs)
        self.assertTrue(summarize(*batch(['a', 'b', 'c']))['completed_three'])
        self.assertFalse(summarize(*batch(['a', 'a', 'a']))['completed_three'])
        events, results, logs = batch(['a', 'b', 'c'])
        events.append(events[-1])
        self.assertFalse(summarize(events, results, logs)['completed_three'])

    def test_observed_speed_and_clock_regression_are_not_hidden(self):
        events = [json.dumps({'topic': '/clock', 'message': {'clock': {'sec': t, 'nanosec': 0}}})
                  for t in (2, 3, 1)]
        events.append(json.dumps({'topic': '/m0609/rail/joint_states',
                                  'message': {'velocity': [-2.3, .2, .8]}}))
        result = summarize(events, [], '')
        self.assertEqual(result['rail_peak_speed_m_s'], [2.3, .2, .8])
        self.assertEqual(result['clock_reversals'], 1)
        self.assertEqual(result['rail_samples'], 1)


if __name__ == '__main__':
    unittest.main()
