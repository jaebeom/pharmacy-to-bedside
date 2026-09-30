"""Measure real shelf boards and pack medicine cells without fixed hospital coordinates."""
from collections import defaultdict
import math


def measure_boards(stage, prim):
    from pxr import Gf, Usd, UsdGeom
    cache = UsdGeom.XformCache()
    levels = defaultdict(lambda: [0., []])
    for part in Usd.PrimRange(prim, Usd.TraverseInstanceProxies()):
        if not part.IsA(UsdGeom.Mesh):
            continue
        mesh = UsdGeom.Mesh(part)
        matrix = cache.GetLocalToWorldTransform(part)
        points = [matrix.Transform(Gf.Vec3d(v)) for v in mesh.GetPointsAttr().Get()]
        indices = mesh.GetFaceVertexIndicesAttr().Get()
        offset = 0
        for count in mesh.GetFaceVertexCountsAttr().Get():
            face = [points[j] for j in indices[offset:offset+count]]
            offset += count
            if count < 3 or max(v[2] for v in face)-min(v[2] for v in face) > .001:
                continue
            z = round(sum(v[2] for v in face)/count, 3)
            for i in range(1, count-1):
                area = Gf.Cross(face[i]-face[0], face[i+1]-face[0])[2]/2
                if area > 0:
                    levels[z][0] += area
                    levels[z][1].extend(face)
    boards = []
    for z, (area, points) in sorted(levels.items()):
        if area > .08:
            boards.append({'z': z, 'min': [min(p[i] for p in points) for i in (0, 1)],
                           'max': [max(p[i] for p in points) for i in (0, 1)], 'area': area})
    if len(boards) < 2:
        raise ValueError('shelf needs a support board and an upper board/roof')
    return boards


def pack_stock(shelf, boards, diameter=.07, height=.12, pitch=.13, margin=.07):
    if (not all(math.isfinite(v) and v > 0 for v in (diameter, height, pitch, margin))
            or pitch <= diameter or margin < diameter/2):
        raise ValueError('invalid medicine packing dimensions')
    boards = sorted(boards, key=lambda b: b['z'])
    if len(boards) < 2:
        raise ValueError('shelf needs a roof above the storage tiers')
    lo = [max(b['min'][i] for b in boards)+margin for i in (0, 1)]
    hi = [min(b['max'][i] for b in boards)-margin for i in (0, 1)]
    if any(a > b for a, b in zip(lo, hi, strict=True)):
        raise ValueError('shelf has no shared interior footprint')
    count = [int((hi[i]-lo[i])/pitch)+1 for i in (0, 1)]
    start = [(lo[i]+hi[i]-(count[i]-1)*pitch)/2 for i in (0, 1)]
    cells = {}
    for row, (board, ceiling) in enumerate(zip(boards, boards[1:], strict=False)):
        if ceiling['z']-board['z'] < height+.05:
            raise ValueError('medicine does not fit below upper board')
        for depth in range(count[1]):
            for col in range(count[0]):
                key = f'{shelf}/r{row}d{depth}c{col}'
                cells[key] = {'shelf': shelf, 'row': row, 'col': col, 'depth_index': depth,
                              'type': 'cylinder', 'access': 'front',
                              'surface': [start[0]+col*pitch, start[1]+depth*pitch, board['z']],
                              'size': {'diameter': diameter, 'height': height}, 'height': height,
                              'front_accessible': depth == 0,
                              'headroom': ceiling['z']-board['z'], 'pitch': pitch, 'margin': margin}
    return cells


def measure_stock(stage, shelf_paths):
    cells, measurements = {}, {}
    for path in shelf_paths:
        prim = stage.GetPrimAtPath(path)
        if not prim or not prim.IsActive():
            raise ValueError('missing active shelf: '+path)
        name = prim.GetName()
        boards = measure_boards(stage, prim)
        cells.update(pack_stock(name, boards))
        measurements[path] = boards
    return mix_medicine(cells), measurements


def mix_medicine(cells):
    """Distribute approximately one module per four positions throughout all tiers."""
    mixed = {}
    for index, (name, source) in enumerate(cells.items()):
        cell = dict(source)
        if index % 4 == 0:
            if (source.get('headroom', 0) < .19 or source.get('pitch', 0) <= .10
                    or source.get('margin', 0) < .05):
                raise ValueError('module does not fit measured packing clearance')
            cell.update(type='module', size={'x': .06, 'y': .10, 'z': .14}, height=.14)
        mixed[name] = cell
    return mixed
