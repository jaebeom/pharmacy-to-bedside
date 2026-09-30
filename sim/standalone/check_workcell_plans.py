#!/usr/bin/env python3
"""Offline preflight using the unchanged ROS scene_v2 planner (no robot motion).

Run with PYTHONPATH=sim/standalone:src/rokey_p3_manipulation and PyYAML installed.
"""
import argparse
import json
from pathlib import Path
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--layout', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--seed', type=int, required=True)
    parser.add_argument('--rail-select', choices=('first_feasible', 'preferred_first'), default='preferred_first')
    args = parser.parse_args()
    import yaml
    from p3sim import workcell_layout
    from rokey_p3_manipulation import clearance, m0609_kinematics as kin, pick_plan, scene_v2
    from rokey_p3_manipulation.refill_sequence import load_rail_teach

    config = Path(__file__).resolve().parents[2]/'src/rokey_p3_manipulation/config'
    home = load_rail_teach(yaml.safe_load((config/'m0609_rail_teach.yaml').read_text())).home_joints
    tcp, boxes = clearance.load_collision(yaml.safe_load((config/'m0609_collision.yaml').read_text()))
    model = kin.M0609(kin.ToolTransform(tcp, (0., 0., 0., 1.)))
    scene = scene_v2.parse_inventory(json.dumps(
        workcell_layout.inventory_for_planning(workcell_layout.load(args.layout))))
    picker = pick_plan.CellPicker(args.seed)
    seeds = pick_plan.default_seeds(home, 12, seed=1)
    excluded, cache = [], {}
    params = scene_v2.PREFERRED_PARAMS if args.rail_select == 'preferred_first' else scene_v2.DEFAULT_PARAMS
    with args.output.open('x') as stream:
        for attempt in range(1, 4):
            cell, choice = picker.choose(scene.cells, 'cylinder', 'drug-amox', exclude=excluded)
            excluded.append(cell.cell_id)
            started = time.monotonic()
            steps, reason, minimum = scene_v2.plan_refill(
                model, scene, cell, boxes, tcp, seeds, params, home, place_cache=cache,
                rail_select=args.rail_select)
            result = {'mode': 'OFFLINE_PLAN_ONLY', 'attempt': attempt, 'choice': choice._asdict(),
                      'ok': steps is not None, 'reason': reason, 'clearance_m': minimum,
                      'elapsed_s': time.monotonic()-started,
                      'steps': [step._asdict() for step in steps] if steps else []}
            line = json.dumps(result, ensure_ascii=False)
            print(line, flush=True)
            stream.write(line+'\n')
            stream.flush()


if __name__ == '__main__':
    main()
