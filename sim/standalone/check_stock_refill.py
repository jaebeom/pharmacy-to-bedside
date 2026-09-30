#!/usr/bin/env python3
"""Offline random-three diagnostic with every other present stock item as an obstacle.

Input is the existing scene-v2 inventory message, with explicit `front_accessible`
and `shelf` metadata on cells. No ROS imports, commands, cache writes or gate changes.
PYTHONPATH=sim/standalone:src/rokey_p3_manipulation python3 ... --help
"""
import argparse
import hashlib
import json
from pathlib import Path
import signal
import time


def select_cells(scene, raw, picker):
    metadata = {c['cell']: c for c in raw['cells']}
    if len(metadata) != len(raw['cells']):
        raise ValueError('duplicate cell identifiers')
    eligible = [c for c in scene.cells if metadata[c.cell_id].get('front_accessible') is True]
    if any(not metadata[c.cell_id].get('shelf') for c in eligible):
        raise ValueError('eligible cells need an explicit shelf identifier')
    selected, excluded = [], []
    for _ in range(3):
        cell, choice = picker.choose(eligible, 'cylinder', 'drug-amox', exclude=excluded)
        if cell is None:
            raise ValueError('need accessible cylinders on three distinct shelves')
        selected.append((cell, choice))
        shelf = metadata[cell.cell_id]['shelf']
        excluded.extend(c.cell_id for c in eligible if metadata[c.cell_id]['shelf'] == shelf)
    return selected


def with_stock_obstacles(scene, selected):
    from rokey_p3_manipulation.clearance import Box
    neighbors = tuple(Box('Stock_'+c.cell_id, c.center, c.size) for c in scene.cells
                      if c.present and c.cell_id != selected.cell_id)
    return scene._replace(obstacles=scene.obstacles+neighbors)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inventory', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True, help='New JSONL; never overwrite earlier results')
    parser.add_argument('--seed', type=int, required=True)
    parser.add_argument('--rail-select', choices=('first_feasible', 'preferred_first'), required=True)
    parser.add_argument('--budget-s', type=int, default=90,
                        help='Offline wall budget per cell; no motion deadline change')
    args = parser.parse_args()
    if args.budget_s <= 0:
        parser.error('--budget-s must be positive')
    import yaml
    from rokey_p3_manipulation import clearance, m0609_kinematics as kin, pick_plan, scene_v2
    from rokey_p3_manipulation.refill_sequence import load_rail_teach

    source = args.inventory.read_bytes()
    raw = json.loads(source)
    scene = scene_v2.parse_inventory(source)
    selected = select_cells(scene, raw, pick_plan.CellPicker(args.seed))
    config = Path(__file__).resolve().parents[2]/'src/rokey_p3_manipulation/config'
    home = load_rail_teach(yaml.safe_load((config/'m0609_rail_teach.yaml').read_text())).home_joints
    tcp, boxes = clearance.load_collision(yaml.safe_load((config/'m0609_collision.yaml').read_text()))
    model = kin.M0609(kin.ToolTransform(tcp, (0., 0., 0., 1.)))
    seeds = pick_plan.default_seeds(home, 12, seed=1)
    params = scene_v2.PREFERRED_PARAMS if args.rail_select == 'preferred_first' else scene_v2.DEFAULT_PARAMS

    def expired(_signum, _frame):
        raise TimeoutError('offline planning wall budget exceeded; no motion sent')

    previous = signal.signal(signal.SIGALRM, expired)
    try:
        with args.output.open('x') as stream:
            for cell, choice in selected:
                measured = with_stock_obstacles(scene, cell)
                started = time.monotonic()
                signal.alarm(args.budget_s)
                try:
                    steps, reason, minimum = scene_v2.plan_refill(
                        model, measured, cell, boxes, tcp, seeds, params, home,
                        rail_select=args.rail_select)
                    result = {'ok': steps is not None, 'reason': reason, 'clearance_m': minimum,
                              'steps': [s._asdict() for s in steps] if steps else []}
                except TimeoutError as error:
                    result = {'ok': False, 'reason': str(error), 'steps': []}
                finally:
                    signal.alarm(0)
                result.update(mode='OFFLINE_ONLY_WITH_ALL_OTHER_STOCK_OBSTACLES', motion_sent=False,
                              choice=choice._asdict(), obstacles=len(measured.obstacles),
                              rail_select=args.rail_select, elapsed_s=time.monotonic()-started,
                              inventory_sha256=hashlib.sha256(source).hexdigest())
                line = json.dumps(result, ensure_ascii=False)
                print(line, flush=True)
                stream.write(line+'\n')
                stream.flush()
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)


if __name__ == '__main__':
    main()
