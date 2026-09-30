"""Read-only dispenser reference checks shared by CLI and hospital startup."""

import hashlib
import json
import math
from pathlib import Path


def reference_asset():
    return Path(__file__).resolve().parents[3] / "src/rokey_p3_description/models/dispenser/dispenser.usdc"


def anchor_positions(stage, prim_path):
    from pxr import UsdGeom

    cache = UsdGeom.XformCache()
    result = {}
    for name in ("PillOpening", "ModuleEntry", "ConveyorOpening"):
        prim = stage.GetPrimAtPath(prim_path + "/Anchors/" + name)
        if not prim or not prim.IsActive():
            raise ValueError("missing active dispenser anchor: " + name)
        result[name] = list(cache.GetLocalToWorldTransform(prim).ExtractTranslation())
    return result


def check_live_scene(asset, scene, prim_path):
    """Compare the open stage, including session edits, allowing rigid root placement only."""
    from pxr import Usd, UsdGeom

    reference = Usd.Stage.Open(str(asset.resolve()))
    root = scene.GetPrimAtPath(prim_path)
    if not (root and root.IsActive()):
        raise ValueError("scene dispenser missing/inactive")
    source_root = reference.GetDefaultPrim()
    source_cache, scene_cache = (UsdGeom.XformCache(), UsdGeom.XformCache())
    root_matrix = scene_cache.GetLocalToWorldTransform(root)
    for i in range(3):
        for j in range(3):
            dot = sum(root_matrix[i, k] * root_matrix[j, k] for k in range(3))
            if not math.isclose(dot, float(i == j), abs_tol=1e-07):
                raise ValueError("root placement must not scale/shear the asset")
    if not math.isclose(root_matrix.GetDeterminant(), 1.0, abs_tol=1e-07):
        raise ValueError("root reflection is not allowed")
    inverse = root_matrix.GetInverse()
    geometry_count = 0
    for prim in Usd.PrimRange(source_root):
        relative = prim.GetPath().MakeRelativePath(source_root.GetPath())
        actual = scene.GetPrimAtPath(root.GetPath().AppendPath(relative))
        if not (actual and actual.IsActive() and (actual.GetTypeName() == prim.GetTypeName())):
            raise ValueError(str(relative) + " missing/type")
        if not (prim.IsA(UsdGeom.Gprim) or "/Anchors/" in str(prim.GetPath())):
            continue
        expected = source_cache.GetLocalToWorldTransform(prim)
        measured = scene_cache.GetLocalToWorldTransform(actual) * inverse
        if not all(abs(expected[i, j] - measured[i, j]) < 1e-07 for i in range(4) for j in range(4)):
            raise ValueError(str(relative) + " geometry/anchor transform override")
        for name in ("points", "faceVertexCounts", "faceVertexIndices", "size", "radius", "height", "axis"):
            attribute = prim.GetAttribute(name)
            if attribute:
                other = actual.GetAttribute(name)
                if not (other and attribute.Get() == other.Get()):
                    raise ValueError(str(relative) + " shape override: " + name)
        if (prim.IsA(UsdGeom.Imageable)
                and UsdGeom.Imageable(prim).ComputeVisibility() != UsdGeom.Imageable(actual).ComputeVisibility()):
            raise ValueError(str(relative) + " visibility override")
        geometry_count += 1
    expected_paths = {str(p.GetPath().MakeRelativePath(source_root.GetPath())) for p in Usd.PrimRange(source_root)}
    actual_paths = {str(p.GetPath().MakeRelativePath(root.GetPath())) for p in Usd.PrimRange(root)}
    if not expected_paths == actual_paths:
        raise ValueError("extra/missing prims below scene dispenser")
    return {
        "scene_geometry": "PASS",
        "checked_prims": geometry_count,
        "anchors_world": anchor_positions(scene, prim_path),
    }


def check_hospital_dispenser(stage, prim_path):
    asset = reference_asset()
    metadata = json.loads(asset.with_name('asset.json').read_text())
    digest = hashlib.sha256(asset.read_bytes()).hexdigest()
    if digest != metadata['asset_sha256']:
        raise ValueError('reference asset hash differs from asset.json')
    from pxr import Usd, UsdGeom
    reference = Usd.Stage.Open(str(asset))
    cache = UsdGeom.XformCache()
    for name, expected in metadata['anchors_local'].items():
        anchor = reference.GetPrimAtPath('/Dispenser/Anchors/'+name)
        if not anchor or math.dist(cache.GetLocalToWorldTransform(anchor).ExtractTranslation(), expected) > 1e-7:
            raise ValueError('reference anchor differs from asset.json: '+name)
    result = check_live_scene(asset, stage, prim_path)
    result.update(asset_sha256=digest, prim=prim_path)
    return result
