#!/usr/bin/env python3
"""Check standalone USD structure and anchors against visible inlet geometry (pxr required)."""
import argparse
import hashlib
import json
import math
from pathlib import Path


def check(asset, metadata):
    from pxr import Usd, UsdGeom
    info = json.loads(metadata.read_text())
    assert hashlib.sha256(asset.read_bytes()).hexdigest() == info['asset_sha256'], 'asset hash mismatch'
    assert asset.stat().st_size == info['asset_bytes'], 'asset size mismatch'
    stage = Usd.Stage.Open(str(asset.resolve()))
    assert stage and stage.GetDefaultPrim().GetPath() == '/Dispenser', 'default prim'
    assert UsdGeom.GetStageMetersPerUnit(stage) == 1. and UsdGeom.GetStageUpAxis(stage) == 'Z', 'units/up axis'
    assert set(stage.GetUsedLayers()) <= {stage.GetRootLayer(), stage.GetSessionLayer()}, 'external layers/references'
    cache = UsdGeom.XformCache()
    bounds = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ['default', 'render'])
    matrix = cache.GetLocalToWorldTransform(stage.GetDefaultPrim())
    assert all(abs(matrix[i, j]-float(i == j)) < 1e-9 for i in range(4) for j in range(4)), 'root identity'
    for prim in stage.Traverse():
        for rel in prim.GetRelationships():
            assert all(stage.GetObjectAtPath(target) for target in rel.GetTargets()), str(rel.GetPath())
        if prim.IsA(UsdGeom.Mesh):
            mesh = UsdGeom.Mesh(prim)
            points = mesh.GetPointsAttr().Get()
            counts = mesh.GetFaceVertexCountsAttr().Get()
            indices = mesh.GetFaceVertexIndicesAttr().Get()
            assert sum(counts) == len(indices) and all(0 <= i < len(points) for i in indices), str(prim.GetPath())
            assert all(math.isfinite(v) for point in points for v in point), 'nonfinite mesh'
    anchors = {}
    for name, expected in info['anchors_local'].items():
        point = cache.GetLocalToWorldTransform(stage.GetPrimAtPath('/Dispenser/Anchors/'+name)).ExtractTranslation()
        assert math.dist(point, expected) < 1e-7, name+' metadata mismatch'
        anchors[name] = list(point)

    def box(name):
        prim = stage.GetPrimAtPath('/Dispenser/Inlets/'+name)
        assert prim, name+' missing'
        bb = bounds.ComputeWorldBound(prim).ComputeAlignedRange()
        return list(bb.GetMin()), list(bb.GetMax())

    rims = [box(f'PillRim{i:02}') for i in range(32)]
    rim_point = [sum((lo[i]+hi[i])/2 for lo, hi in rims)/len(rims) for i in (0, 1)]
    rim_point.append(sum(hi[2] for _, hi in rims)/len(rims))
    assert math.dist(rim_point, anchors['PillOpening']) < 1e-7, 'pill anchor differs from rim'
    left, right, bottom, top = (box('Module'+name) for name in ('Left', 'Right', 'Bottom', 'Top'))
    entry = [(left[1][0]+right[0][0])/2, left[0][1], (bottom[1][2]+top[0][2])/2]
    assert math.dist(entry, anchors['ModuleEntry']) < 1e-7, 'module anchor differs from opening'
    support, plate = box('PillSupport'), box('PillMountPlate')
    assert all(support[0][i] <= plate[1][i]+1e-7 and plate[0][i] <= support[1][i]+1e-7
               for i in range(3)), 'pill support disconnected from mounting plate'
    assert math.isclose(right[0][0]-left[1][0], .08, abs_tol=1e-7), 'module opening width'
    assert math.isclose(top[0][2]-bottom[1][2], .16, abs_tol=1e-7), 'module opening height'
    separation = abs(anchors['PillOpening'][0]-anchors['ModuleEntry'][0])
    assert anchors['PillOpening'][0] < anchors['ModuleEntry'][0], 'reference left/right order changed'
    return {'asset_sha256': info['asset_sha256'], 'anchors_local': anchors,
            'horizontal_separation_m': separation, 'support_connected': True,
            'geometry_anchor_checks': 'PASS', 'robot_motion': 'NOT_CHECKED',
            'internal_intake': 'NOT_IMPLEMENTED'}


def check_scene(asset, scene_file, prim_path):
    from pxr import Usd
    # Direct CLI execution has tools/ on sys.path, rather than the repository root.
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from sim.standalone.p3sim.dispenser_reference import check_live_scene
    scene = Usd.Stage.Open(str(scene_file.resolve()))
    if scene is None:
        raise ValueError('scene could not be opened')
    result = check_live_scene(asset, scene, prim_path)
    result['saved_scene_geometry'] = result.pop('scene_geometry')
    result['live_unsaved_session'] = 'NOT_CHECKED'
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--asset', type=Path, required=True)
    parser.add_argument('--metadata', type=Path, required=True)
    parser.add_argument('--scene', type=Path, help='Saved scene containing the referenced asset')
    parser.add_argument('--prim', help='Dispenser root in --scene')
    args = parser.parse_args()
    if bool(args.scene) != bool(args.prim):
        parser.error('--scene and --prim must be supplied together')
    result = check(args.asset, args.metadata)
    if args.scene:
        result.update(check_scene(args.asset, args.scene, args.prim))
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
