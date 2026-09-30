"""Measured hospital geometry adapter for the EXISTING pharmacy ROS runtime.

No IK, joint streaming, attachment, inventory protocol, or speed implementation.
"""
import hashlib
import json
import math
import random
from pathlib import Path

from . import layout, layout_v2

def layout_source(data):
    """Canonical inventory source: file-byte sha256 of the layout JSON snapshot.

    Both the runtime publisher and inventory_for_planning use this string.
    The JSON field source_sha256 is an asset note and is not a second id.
    """
    return 'hospital_workcell:'+data['_layout_sha256']


# Same skip classes as scene_v2.OWN_TARGET_PREFIXES. Copied so Isaac load does not
# import the arm package. Compact only inside one class so a RoundBin skip cannot
# drop a remaining body box from the carried-item check.
COLLISION_SKIP_CLASSES = (('round', ('RoundBin',)), ('module', ('DispenserFront',)))


def obstacle_class(name):
    for kind, prefixes in COLLISION_SKIP_CLASSES:
        if name.startswith(prefixes):
            return kind
    return 'body'


def _aabb_contains(outer, inner):
    return all(abs(a-b)+size/2 <= span/2 for a, b, size, span in zip(
        inner['center'], outer['center'], inner['size'], outer['size'], strict=True))


def compact_body_obstacles(obstacles):
    """Drop fully contained AABBs only when the covering box shares the skip class.

    Union of the remaining boxes is unchanged inside each class. A RoundBin box
    cannot cover a Dispenser body, and the reverse is also rejected. Equal-size
    duplicates keep the lower index. No tolerance inflation or collision gate change.
    """
    retained, covered = [], {}
    for i, box in enumerate(obstacles):
        kind = obstacle_class(box['name'])
        candidates = []
        for j, other in enumerate(obstacles):
            if i == j or obstacle_class(other['name']) != kind:
                continue
            if _aabb_contains(other, box) and (box['size'] != other['size'] or j < i):
                volume = other['size'][0]*other['size'][1]*other['size'][2]
                candidates.append((volume, j, other['name']))
        if candidates:
            covered[box['name']] = min(candidates)[2]
        else:
            retained.append(box)
    return retained, covered


def load(path):
    raw = Path(path).read_bytes()
    data = json.loads(raw)
    data['_layout_sha256'] = hashlib.sha256(raw).hexdigest()
    if data.get('version') != 1 or data.get('frame') != 'hospital_world_m_z_up':
        raise ValueError('workcell layout requires version 1 and hospital world frame')
    cells = data['cells']
    if len(cells) != 18 or len({c['shelf'] for c in cells.values()}) != 9:
        raise ValueError('workcell requires 9 shelves, each with cylinder and module')
    for shelf in {c['shelf'] for c in cells.values()}:
        if sorted(c['type'] for c in cells.values() if c['shelf'] == shelf) != ['cylinder', 'module']:
            raise ValueError('each shelf requires one cylinder and one module')
    for cell in cells.values():
        if cell['type'] not in ('cylinder', 'module') or cell['access'] != 'front':
            raise ValueError('unsupported workcell cell')
        if len(cell['surface']) != 3 or not all(math.isfinite(v) for v in cell['surface']):
            raise ValueError('nonfinite cell surface')
    for name in ('round', 'module'):
        if name not in data['targets']:
            raise ValueError('missing inlet '+name)
    for box in data['obstacles']:
        if len(box['center']) != 3 or len(box['size']) != 3 or not all(
                math.isfinite(v) for v in box['center']+box['size']) or min(box['size']) <= 0:
            raise ValueError('invalid obstacle '+box['name'])
    rail = data['rail']
    if (len(rail['origin']) != 3 or not all(math.isfinite(v) for v in rail['origin'])
            or not math.isfinite(rail['x_stroke']) or rail['x_stroke'] <= 0
            or not math.isfinite(rail['carriage_height']) or rail['carriage_height'] <= 0):
        raise ValueError('invalid rail origin, stroke or carriage height')
    for axis in ('y_limits', 'z_limits'):
        limits = rail[axis]
        if len(limits) != 2 or not all(math.isfinite(v) for v in limits) or not limits[0] < limits[1]:
            raise ValueError('invalid rail '+axis)
    def vector(value, count, name, positive=False):
        if (not isinstance(value, (list, tuple)) or len(value) != count
                or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)
                       or (positive and v <= 0) for v in value)):
            raise ValueError('invalid '+name)

    for cell in cells.values():
        vector([cell['height']], 1, 'cell height', positive=True)
        keys = ('diameter', 'height') if cell['type'] == 'cylinder' else ('x', 'y', 'z')
        vector([cell['size'][key] for key in keys], len(keys), 'cell size', positive=True)
        if cell['height'] != cell['size']['height' if cell['type'] == 'cylinder' else 'z']:
            raise ValueError('cell height differs from size')
    for name, point, axis in [('round', 'center', [0, 0, -1]), ('module', 'entry_center', [0, 1, 0])]:
        target = data['targets'][name]
        vector(target.get(point), 3, name+' target')
        if target.get('axis') != axis:
            raise ValueError('unsupported '+name+' target axis')
        vector([target['depth']], 1, name+' depth', positive=True)
    target = data['targets']['round']
    vector([target['inner_diameter']], 1, 'round diameter', positive=True)
    vector([target['floor_z']], 1, 'round floor')
    if target['floor_z'] >= target['center'][2]:
        raise ValueError('round floor must be below rim')
    opening = data['targets']['module']['opening']
    vector([opening['x'], opening['z']], 2, 'module opening', positive=True)
    vector(data['belt']['start'], 3, 'belt start')
    vector([data['belt']['length']], 1, 'belt length', positive=True)
    vector([data['belt']['yaw']], 1, 'belt yaw')
    vector(data['amr_start'], 2, 'AMR start')
    camera = data['camera']
    vector(camera['eye'], 3, 'camera eye')
    vector(camera['target'], 3, 'camera target')
    vector([camera['focal_mm']], 1, 'camera focal length', positive=True)
    if math.dist(camera['eye'][:2], camera['target'][:2]) < 1e-9:
        raise ValueError('camera view is parallel to Z-up')
    data['obstacles'] = compact_body_obstacles(data['obstacles'])[0]
    return data


def configure(args, data):
    """Geometry only. Motion remains owned by m0609_arm_node and its defaults."""
    args.workcell_data = data  # Immutable input snapshot for this launch; never reload during motion.
    args.scene = 'v2'
    args.amr = True
    args.mode = 'ros'
    args.ros_refill_selfdemo = False
    args.rail_origin = tuple(data['rail']['origin'])
    args.rail_x_stroke = data['rail']['x_stroke']
    args.rail_y_limits = data['rail']['y_limits']
    args.rail_z_limits = data['rail']['z_limits']
    args.carriage_height = data['rail']['carriage_height']
    args.belt_start = tuple(data['belt']['start'])
    args.belt_length = data['belt']['length']
    args.belt_yaw = data['belt']['yaw']
    args.belt_top = args.belt_start[2]
    args.amr_start = data['amr_start']
    args.full_loop = False  # Hospital navigation routes must be measured separately.
    args.ros_pick_stand_in_s = 0.
    return args


def room(args, data):
    rails = layout.rail_boxes(args.rail_origin, args.rail_x_stroke, args.rail_y_limits,
                              .05, args.carriage_height)
    # All real hospital geometry/colliders are in the prepared base USD.
    return {'boxes': rails, 'cells': {}, 'inlets': {}, 'belt_start': args.belt_start,
            'v2': {'cells': data['cells'], 'targets': data['targets'], 'obstacles': data['obstacles']},
            'zones': None, 'full_loop': None}


def shuffled_stock(cells, seed, empty=0):
    """시드로 섞은 **초기 재고**. 칸의 자리·접근 방향은 그대로 두고 약통 종류와 빈 칸만 정한다.

    잰 배치는 선반마다 왼쪽이 원통, 오른쪽이 모듈로 고정이라 약통이 줄 맞춰 서 있다(재범 9/23). 여기서
    섞되 **종류의 개수는 그대로 둔다**(원통 아홉·모듈 아홉) — 팔이 두 품목을 다 찾을 수 있어야 한다.
    빈 칸도 한 종류를 통째로 비우지 않는다. 같은 시드·같은 입력이면 같은 배치다.

    반환은 `(cells, present)` 한 벌이다. 스테이지가 이 한 벌로 약통을 세우고, QR 면을 붙이고,
    `/m0609/shelf/inventory` 를 낸다 — 팔이 고르는 출처와 화면에 선 약통이 같은 곳에서 나온다.
    """
    order = sorted(cells)
    kinds = sorted(cell['type'] for cell in cells.values())
    shape = {}
    for cell in cells.values():
        shape.setdefault(cell['type'], (cell['size'], cell['height']))
    rng = random.Random(int(seed))
    rng.shuffle(kinds)
    out = {}
    for cell_id, kind in zip(order, kinds, strict=True):
        cell = dict(cells[cell_id])
        size, height = shape[kind]
        cell.update(type=kind, size=dict(size), height=height)
        out[cell_id] = cell
    present = dict.fromkeys(order, True)
    empty = int(empty)
    if empty > 0:
        by_kind = {}
        for cell_id in order:
            by_kind.setdefault(out[cell_id]['type'], []).append(cell_id)
        pool = []
        for _kind, ids in sorted(by_kind.items()):
            keep = rng.choice(ids)          # 종류마다 한 칸은 반드시 남긴다
            pool += [c for c in ids if c != keep]
        rng.shuffle(pool)
        for cell_id in pool[:empty]:
            present[cell_id] = False
    return out, present


def inventory_for_planning(data):
    """Same wire representation the normal runtime publishes; useful for preflight."""
    rail = data['rail']
    message = layout_v2.inventory(data['cells'], dict.fromkeys(data['cells'], True), data['targets'],
        data['obstacles'], rail={'names': ['rail_x', 'rail_y', 'rail_z'],
            'limits': [[-rail['x_stroke']/2, rail['x_stroke']/2], rail['y_limits'], rail['z_limits']],
            'origin': [*rail['origin'][:2], rail['origin'][2]+rail['carriage_height']],
            'parts': layout_v2.rail_parts(rail['origin'], rail['x_stroke'], rail['y_limits'], .05,
                                         rail['carriage_height'], lift_travel=rail['z_limits'][1])})
    message['source'] = layout_source(data)
    return message
