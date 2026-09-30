"""Opt-in ROS client integration; synthetic server, never Isaac/robot L3.

Source the built ROS workspace, use an unused ROS_DOMAIN_ID and set
P3_RUN_ROS_TESTS=1. The synthetic server publishes no robot joint commands.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'standalone'))
from p3sim import workcell_layout  # noqa: E402
from test_workcell_layout import fixture  # noqa: E402


@unittest.skipUnless(os.environ.get('P3_RUN_ROS_TESTS') == '1', 'opt-in isolated ROS integration')
class TrialRosTests(unittest.TestCase):
    def setUp(self):
        import rclpy
        from rclpy.action import ActionServer
        from rclpy.executors import MultiThreadedExecutor
        from rclpy.qos import QoSProfile, DurabilityPolicy, ReliabilityPolicy
        from rokey_p3_interfaces.action import Refill
        from rosgraph_msgs.msg import Clock
        from std_msgs.msg import Bool, String
        self.rclpy = rclpy
        rclpy.init()
        self.node = rclpy.create_node('synthetic_workcell_trial_server')
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.layout = self.root/'workcell.local.json'
        self.layout.write_text(json.dumps(fixture()))
        self.data = workcell_layout.inventory_for_planning(workcell_layout.load(self.layout))
        self.count, self.tick = 0, 0
        self.frozen = False
        self.wrong_release = False
        qos = QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE,
                         durability=DurabilityPolicy.TRANSIENT_LOCAL)
        inventory = self.node.create_publisher(String, '/m0609/shelf/inventory', qos)
        cache = self.node.create_publisher(String, '/m0609/arm/plan_cache', qos)
        clock = self.node.create_publisher(Clock, '/clock', 10)
        home = self.node.create_publisher(Bool, '/m0609/arm/at_home', 10)
        plan = json.dumps({'solved': 18, 'total': 18, 'failed': {}, 'source': self.data['source']})

        def publish():
            if not self.frozen:
                self.tick += 1
            msg = Clock()
            msg.clock.sec, msg.clock.nanosec = divmod(self.tick*50_000_000, 1_000_000_000)
            clock.publish(msg)
            inventory.publish(String(data=json.dumps(self.data)))
            cache.publish(String(data=plan))
            home.publish(Bool(data=True))

        def execute(handle):
            cell = next(c for c in self.data['cells'] if c['type'] == 'cylinder' and c['present'])
            self.count += 1
            handle.publish_feedback(Refill.Feedback(phase=f"plan cell={cell['cell']} kind=cylinder"))
            cell['present'] = False
            self.data['last_release'] = {'cell': 'wrong' if self.wrong_release else cell['cell'], 'target': 'round'}
            handle.succeed()
            return Refill.Result(success=True, lot_id='synthetic')

        self.server = ActionServer(self.node, Refill, '/m0609/refill', execute)
        self.node.create_timer(.05, publish)
        self.executor = MultiThreadedExecutor(num_threads=2)
        self.executor.add_node(self.node)
        self.thread = threading.Thread(target=self.executor.spin, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.executor.shutdown()
        self.thread.join(timeout=5)
        self.server.destroy()
        self.node.destroy_node()
        self.rclpy.shutdown()
        self.temp.cleanup()

    def run_client(self):
        output = self.root/'trial'
        script = Path(__file__).resolve().parents[1]/'standalone/run_workcell_refill_trials.py'
        result = subprocess.run([sys.executable, str(script), '--layout', str(self.layout),
                                 '--output', str(output)], capture_output=True, text=True, timeout=35, check=False)
        return result, output

    def test_three_sequential_results_match_live_release(self):
        result, output = self.run_client()
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
        rows = json.loads((output/'results.json').read_text())
        self.assertEqual(self.count, 3)
        self.assertEqual(len({r['selected_cell'] for r in rows}), 3)
        self.assertTrue(all(r['home_observed'] and r['release_matched'] for r in rows))

    def test_frozen_clock_sends_no_goal_and_preserves_error(self):
        self.frozen = True
        result, output = self.run_client()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.count, 0)
        self.assertEqual(json.loads((output/'results.json').read_text()), [])
        self.assertIn('stopped advancing', (output/'error.json').read_text())

    def test_mismatched_release_stops_after_first_result(self):
        self.wrong_release = True
        result, output = self.run_client()
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
        self.assertEqual(self.count, 1)
        rows = json.loads((output/'results.json').read_text())
        self.assertEqual(len(rows), 1)
        self.assertFalse(rows[0]['release_matched'])


if __name__ == '__main__':
    unittest.main()
