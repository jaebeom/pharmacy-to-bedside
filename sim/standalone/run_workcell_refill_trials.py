#!/usr/bin/env python3
"""Send three real Refill goals; record feedback and joint telemetry externally.

Run in the system ROS shell after starting pharmacy_stage and m0609_arm.
The arm node owns random selection, planning and all motion. This is a client only.
"""
import argparse
import json
import re
from pathlib import Path
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--observe-only-seconds', type=float, default=0., help='Record only; send no goals')
    parser.add_argument('--layout', type=Path, help='Exact local layout JSON used by this stage')
    args = parser.parse_args()
    if args.observe_only_seconds < 0:
        parser.error('--observe-only-seconds must be nonnegative')
    if not args.observe_only_seconds and not args.layout:
        parser.error('motion trials require --layout')
    from p3sim import trial_preflight, workcell_layout
    expected = (trial_preflight.geometry_key(workcell_layout.inventory_for_planning(workcell_layout.load(args.layout)))
                if args.layout else None)
    args.output.mkdir(parents=True, exist_ok=False)
    import rclpy
    from rclpy.action import ActionClient
    from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy
    from rosidl_runtime_py.convert import message_to_ordereddict
    from rokey_p3_interfaces.action import Refill
    from rosgraph_msgs.msg import Clock
    from sensor_msgs.msg import JointState
    from std_msgs.msg import Bool, String

    rclpy.init()
    node = rclpy.create_node('hospital_practice_recorder')
    stream = (args.output/'events.jsonl').open('x')
    inventory = {}
    inventory_wall = None
    selected_cell = None
    used_cells = set()
    clock_samples = []
    last_advance_wall = None
    running_trial = False
    home_samples = []
    plan_cache = {}

    def record(topic, message):
        nonlocal last_advance_wall, inventory_wall, selected_cell
        payload = message_to_ordereddict(message)
        stream.write(json.dumps({'wall': time.time(), 'topic': topic, 'message': payload})+'\n')
        stream.flush()
        if topic == '/m0609/shelf/inventory':
            inventory_wall = time.monotonic()
            inventory.clear()
            inventory.update(json.loads(message.data))
        if topic == '/m0609/arm/plan_cache':
            plan_cache.clear()
            plan_cache.update(json.loads(message.data))
        if topic == 'feedback':
            match = re.search(r'\bplan cell=(\S+)', message.feedback.phase)
            if match:
                selected_cell = match.group(1)
        if topic == '/clock':
            stamp = message.clock.sec+message.clock.nanosec/1e9
            if not clock_samples or stamp > clock_samples[-1]:
                last_advance_wall = time.monotonic()
            clock_samples.append(stamp)
        if topic == '/m0609/arm/at_home':
            home_samples.append((time.monotonic(), message.data))

    latched = QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE,
                         durability=DurabilityPolicy.TRANSIENT_LOCAL, history=HistoryPolicy.KEEP_LAST)
    heartbeat = QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE,
                           durability=DurabilityPolicy.VOLATILE, history=HistoryPolicy.KEEP_LAST)
    subscriptions = [node.create_subscription(String, '/m0609/shelf/inventory',
                     lambda msg: record('/m0609/shelf/inventory', msg), latched)]
    subscriptions.append(node.create_subscription(String, '/m0609/arm/plan_cache',
                         lambda msg: record('/m0609/arm/plan_cache', msg), latched))
    subscriptions.append(node.create_subscription(Clock, '/clock', lambda msg: record('/clock', msg), 100))
    subscriptions.append(node.create_subscription(Bool, '/m0609/arm/at_home',
                         lambda msg: record('/m0609/arm/at_home', msg), heartbeat))
    for topic, msg_type in [('/m0609/rail/joint_states', JointState),
                            ('/m0609/rail/joint_command', JointState),
                            ('/m0609/joint_states', JointState),
                            ('/m0609/gripper/holding', Bool)]:
        sensor_qos = QoSProfile(depth=100, reliability=ReliabilityPolicy.BEST_EFFORT)
        subscriptions.append(node.create_subscription(msg_type, topic, lambda msg, t=topic: record(t, msg), sensor_qos))
    client = ActionClient(node, Refill, '/m0609/refill')

    def check_live():
        if not inventory or trial_preflight.geometry_key(inventory) != expected:
            raise RuntimeError('live inventory differs from the captured layout; restart and replan')
        problem = trial_preflight.clock_problem(clock_samples, node.count_publishers('/clock'),
                                                time.monotonic(), last_advance_wall)
        if problem:
            raise RuntimeError(problem)

    def wait(future, seconds, monitor=True):
        deadline = time.monotonic()+seconds
        while not future.done() and time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=.1)
            if running_trial and monitor:
                check_live()
        if not future.done():
            raise TimeoutError(f'ROS operation timed out after {seconds} wall seconds')
        return future.result()

    results = []
    (args.output/'results.json').write_text('[]\n')
    try:
        if args.observe_only_seconds:
            deadline = time.monotonic()+args.observe_only_seconds
            while time.monotonic() < deadline:
                rclpy.spin_once(node, timeout_sec=.1)
            return
        if not client.wait_for_server(timeout_sec=20.):
            raise TimeoutError('Refill action server unavailable')
        deadline = time.monotonic()+1200.
        while not inventory or not trial_preflight.cache_ready(plan_cache, inventory):
            if time.monotonic() >= deadline:
                raise TimeoutError('Current arm plan cache did not finish within 1200 wall seconds')
            rclpy.spin_once(node, timeout_sec=.1)
        (args.output/'preflight.json').write_text(json.dumps({
            'ready_wall': time.time(), 'layout_source': inventory['source'],
            'cells': len(inventory['cells']), 'plan_cache': plan_cache,
            'mode': 'plan_cache topic checked; live clock and geometry checked before each goal'}, indent=2)+'\n')
        print('PLAN_CACHE_READY', flush=True)
        deadline = time.monotonic()+3.
        while time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=.1)
        check_live()
        running_trial = True
        for attempt in range(1, 4):
            check_live()
            if not home_samples or not home_samples[-1][1] or time.monotonic()-home_samples[-1][0] > 1.:
                raise RuntimeError('fresh home observation required before a goal')
            selected_cell = None
            goal_started = time.monotonic()
            goal = Refill.Goal(item_id='drug-amox', slot=0)
            print(f'TRIAL_BEGIN {attempt}', flush=True)
            handle = wait(client.send_goal_async(goal, feedback_callback=lambda msg: record('feedback', msg)), 15.)
            if not handle.accepted:
                raise RuntimeError('Refill goal rejected')
            try:
                response = wait(handle.get_result_async(), 240.)
            except (TimeoutError, RuntimeError):
                try:
                    wait(handle.cancel_goal_async(), 10., monitor=False)
                except (TimeoutError, RuntimeError) as cancel_error:
                    (args.output/'cancel-error.txt').write_text(str(cancel_error)+'\n')
                raise
            result_time = time.monotonic()
            while time.monotonic()-result_time < 5.:
                rclpy.spin_once(node, timeout_sec=.1)
                release = inventory.get('last_release') or {}
                if (trial_preflight.home_confirmed(home_samples, result_time, time.monotonic())
                        and inventory_wall is not None and inventory_wall >= goal_started
                        and selected_cell is not None and release.get('cell') == selected_cell
                        and release.get('target') == 'round'):
                    break
            home = trial_preflight.home_confirmed(home_samples, result_time, time.monotonic())
            release = inventory.get('last_release') or {}
            release_matched = bool(selected_cell and release.get('cell') == selected_cell
                                   and release.get('target') == 'round'
                                   and inventory_wall is not None and inventory_wall >= goal_started)
            repeated = selected_cell in used_cells
            used_cells.add(selected_cell)
            row = {'attempt': attempt, 'status': response.status,
                   'result': message_to_ordereddict(response.result),
                   'last_release': inventory.get('last_release'), 'home_observed': home,
                   'selected_cell': selected_cell, 'release_matched': release_matched, 'repeated_cell': repeated}
            results.append(row)
            print(json.dumps(row), flush=True)
            (args.output/'results.json').write_text(json.dumps(results, indent=2)+'\n')
            # Do not hide a failed motion by issuing another goal before inspection.
            if not response.result.success or not home or not release_matched or repeated:
                break
    except BaseException as error:
        (args.output/'error.json').write_text(json.dumps({
            'error': type(error).__name__, 'message': str(error), 'completed_results': len(results),
            'wall': time.time()}, indent=2)+'\n')
        raise
    finally:
        stream.close()
        client.destroy()
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
