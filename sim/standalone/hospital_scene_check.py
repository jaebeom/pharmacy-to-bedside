#!/usr/bin/env python3
"""Read-only report on a hospital scene before putting the pharmacy stage on it (usd-core, no Isaac).

    python3 sim/standalone/hospital_scene_check.py sim/scenes/hospital_layout.usda            # the scene layer only
    python3 sim/standalone/hospital_scene_check.py /tmp/p3-hospital.usda \
        --hospital-v2       # zero-root origin A and the prim lists of --preset hospital-v2

Reports (a) /clock or ROS 2 graph nodes and physics scenes, (b) conveyor graphs, their belt bodies and composed
scale, (c) robots and articulation roots, (d) top-level placements. With a prepared scene (assets resolvable) and
--pharmacy-origin it also lists base scene prims whose world box overlaps the pharmacy footprint (our v2 layout
boxes, the rail travel and the arm's reach), after --deactivate. Never writes the scene.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from p3sim import base_scene  # noqa: E402

ROS_NODE_HINTS = ("ros2", "clock", "readsimtime")
ROBOT_HINTS = ("/Robots/", "m0617", "m0609", "ur5", "ridgeback")
# Pharmacy footprint beyond the layout boxes (stage frame): the rail carriage travel and robot around it, and the
# arm's reach above the shelves (ours, conservative).
ROBOT_ENVELOPE = ((-1.9, -0.25, 0.0), (1.9, 1.0, 2.3))


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("scene")
    parser.add_argument("--pharmacy-origin", type=float, nargs=4, metavar=("X", "Y", "Z", "YAW_DEG"), default=None)
    parser.add_argument("--deactivate", nargs="*", default=[], metavar="PATH")
    parser.add_argument("--rigid-off", nargs="*", default=[], metavar="PATH")
    parser.add_argument("--hospital-v2", action="store_true",
                        help="재범 결정 (9/18): origin A and the prim lists of pharmacy_stage.py --preset hospital-v2")
    parser.add_argument("--scene-version", choices=("v1", "v2"), default="v2", help="our layout to place (v2)")
    parser.add_argument("--min-height", type=float, default=0.05, help="ignore base prims thinner than this (floors)")
    args = parser.parse_args(argv)
    if args.hospital_v2:
        args.pharmacy_origin = args.pharmacy_origin or list(base_scene.HOSPITAL_ORIGIN_A)
        args.deactivate = list(base_scene.HOSPITAL_DEACTIVATE) + args.deactivate
        args.rigid_off = list(base_scene.HOSPITAL_RIGID_OFF) + args.rigid_off
    return args


def layer_report(path):
    """What the scene layer itself says (no references resolved)."""
    from pxr import Sdf

    layer = Sdf.Layer.FindOrOpen(str(path))
    root = layer.pseudoRoot
    report = {"default_prim": layer.defaultPrim,
              "meters_per_unit": root.GetInfo("metersPerUnit") if root.HasInfo("metersPerUnit") else None,
              "up_axis": root.GetInfo("upAxis") if root.HasInfo("upAxis") else None,
              "placeholders": base_scene.placeholders(path), "ros_or_clock_nodes": [], "physics_scenes": [],
              "graphs": [], "robot_references": [], "top_level": {}}

    def walk(spec):
        for child in spec.nameChildren:
            path_str = str(child.path)
            node_type = child.attributes.get("node:type")
            if child.typeName == "OmniGraphNode" and node_type is not None:
                kind = str(node_type.default)
                if any(h in kind.lower() for h in ROS_NODE_HINTS):
                    report["ros_or_clock_nodes"].append({"path": path_str, "type": kind})
                if kind.endswith("IsaacConveyor"):
                    target = child.relationships.get("inputs:conveyorPrim")
                    report["graphs"].append({"node": path_str, "type": kind, "conveyor_prim": [
                        str(t) for t in (target.targetPathList.GetAddedOrExplicitItems() if target else [])]})
            if child.typeName == "PhysicsScene":
                report["physics_scenes"].append(path_str)
            assets = [str(r.assetPath) for r in child.referenceList.GetAddedOrExplicitItems()]
            assets += [str(r.assetPath) for r in child.payloadList.GetAddedOrExplicitItems()]
            for asset in assets:
                if any(h.lower() in asset.lower() for h in ROBOT_HINTS):
                    report["robot_references"].append({"prim": path_str, "asset": asset})
            walk(child)

    walk(root)
    world = layer.GetPrimAtPath(f"/{layer.defaultPrim}") if layer.defaultPrim else None
    for spec in ([world] + list(world.nameChildren)) if world else []:
        ops = {a.name.split(":", 1)[1]: a.default for a in spec.attributes
               if a.name.startswith("xformOp:") and a.default is not None}
        report["top_level"][str(spec.path)] = {k: _plain(v) for k, v in ops.items()}
    return report


def _plain(value):
    try:
        return [round(float(v), 4) for v in value]
    except TypeError:
        try:
            return [round(float(value.GetReal()), 4)] + [round(float(v), 4) for v in value.GetImaginary()]
        except AttributeError:
            return round(float(value), 4) if isinstance(value, (int, float)) else str(value)


def composed_report(path, pharmacy_origin, deactivate, scene_version, min_height, rigid_off=()):
    """Conveyor bodies, articulations and footprint overlaps on the composed scene (references resolved)."""
    from pxr import Usd, UsdGeom, UsdPhysics

    stage = Usd.Stage.Open(str(path))
    default = stage.GetDefaultPrim()
    paths, missing = base_scene.expand_paths(stage, str(default.GetPath()), deactivate)
    for path_str in paths:
        stage.GetPrimAtPath(path_str).SetActive(False)
    rigid_paths, rigid_missing = base_scene.expand_paths(stage, str(default.GetPath()), rigid_off)
    for path_str in rigid_paths:  # the same override pharmacy_stage.py authors (in memory here, never saved)
        UsdPhysics.RigidBodyAPI.Apply(stage.GetPrimAtPath(path_str)).CreateRigidBodyEnabledAttr(False)
    xforms = UsdGeom.XformCache()
    bodies = []
    articulations = []
    for prim in stage.Traverse():
        if prim.HasAPI(UsdPhysics.ArticulationRootAPI):
            articulations.append(str(prim.GetPath()))
        if prim.HasAPI(UsdPhysics.RigidBodyAPI) and "Conveyor" in str(prim.GetPath()):
            matrix = xforms.GetLocalToWorldTransform(prim)
            velocity = prim.GetAttribute("physxSurfaceVelocity:surfaceVelocity")
            kinematic = prim.GetAttribute("physics:kinematicEnabled")
            enabled = prim.GetAttribute("physics:rigidBodyEnabled")
            bodies.append({"prim": str(prim.GetPath()),
                           "rigid_body_enabled": bool(enabled.Get()) if enabled and enabled.Get() is not None
                           else True,
                           "scale": [round(matrix.GetRow3(i).GetLength(), 4) for i in range(3)],
                           "surface_velocity": _plain(velocity.Get()) if velocity and velocity.Get() is not None
                           else None,
                           "kinematic": bool(kinematic.Get()) if kinematic and kinematic.Get() is not None else None})
    active_graphs = [str(p.GetPath()) for p in stage.Traverse() if p.GetTypeName() == "OmniGraph"]
    report = {"deactivated": len(paths), "deactivate_missing": missing, "rigid_off": len(rigid_paths),
              "rigid_off_missing": rigid_missing, "conveyor_bodies": bodies,
              "rigid_bodies_enabled": sum(1 for b in bodies if b["rigid_body_enabled"]),
              "articulation_roots": articulations, "active_graphs": active_graphs}
    if pharmacy_origin is None:
        return report
    report["footprint"] = footprint_overlaps(stage, pharmacy_origin, scene_version, min_height)
    report["views"] = view_occluders(stage, pharmacy_origin, scene_version, min_height)
    return report


def pharmacy_boxes(scene_version):
    """Our layout boxes (stage frame) plus the robot envelope, as (name, low, high)."""
    import pharmacy_stage as stage_module

    args = stage_module.parse_args(["--scene", scene_version])
    boxes = []
    for box in stage_module.room(args)["boxes"]:
        low = tuple(box.center[i] - box.size[i] / 2 for i in range(3))
        high = tuple(box.center[i] + box.size[i] / 2 for i in range(3))
        boxes.append((box.name, low, high))
    boxes.append(("RobotEnvelope", ROBOT_ENVELOPE[0], ROBOT_ENVELOPE[1]))
    layout = stage_module.room(args)
    start = layout["belt_start"]  # the belt is built by scene.build_conveyor, not a layout box; yaw 0 (+x)
    boxes.append(("Belt", (start[0], start[1] - args.belt_width / 2, start[2] - args.belt_thickness),
                  (start[0] + args.belt_length, start[1] + args.belt_width / 2, start[2])))
    return boxes


def base_prim_boxes(stage, min_height):
    """(path, low, high) of active base scene prims: children of the environment and other top-level prims."""
    from pxr import Usd, UsdGeom

    cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ["default", "render"])
    candidates = []
    for prim in stage.GetDefaultPrim().GetChildren():
        if not prim.IsActive():
            continue
        if prim.GetName() == "Environment":
            for env in prim.GetChildren():
                candidates.extend(child for child in env.GetChildren() if child.IsActive())
        elif prim.GetName() == "Conveyor":  # per track: the group's box spans half the room
            candidates.extend(child for child in prim.GetChildren() if child.IsActive())
        else:
            candidates.append(prim)
    out = []
    for prim in candidates:
        rng = cache.ComputeWorldBound(prim).ComputeAlignedRange()
        if rng.IsEmpty() or rng.GetMax()[2] - rng.GetMin()[2] < min_height:
            continue
        out.append((str(prim.GetPath()), tuple(rng.GetMin()), tuple(rng.GetMax())))
    return out


def view_occluders(stage, pharmacy_origin, scene_version, min_height, samples=40):
    """For each named view: base prims whose world box holds the eye or a point on the sight line to the view's
    subjects (canisters, bins, carriage travel ends, gripper above the top row). Boxes are axis-aligned bounds, so a
    hit is a candidate to look at, not proof of occlusion."""
    import pharmacy_stage as stage_module
    from p3sim import layout_v2, views

    args = stage_module.parse_args(["--scene", scene_version])
    layout = stage_module.room(args)
    homes = [layout_v2.canister_home(c) for c in layout["v2"]["cells"].values()] if layout["v2"] else []
    top = max((h[2] for h in homes), default=0.0)
    targets = layout["v2"]["targets"] if layout["v2"] else {}
    bins = [tuple(targets["round"]["center"]), tuple(targets["module"]["entry_center"])] if targets else []
    ox, oy, oz = args.rail_origin
    carriage = [(ox + s * args.rail_x_stroke / 2, oy, oz + args.carriage_height + 0.8) for s in (-1, 1)]
    subjects = homes + [(x, y, z + 0.45) for x, y, z in homes if z == top] + bins + carriage
    prims = [p for p in base_prim_boxes(stage, min_height) if "Floor" not in p[0]]
    result = {}
    for name in views.VIEW_NAMES:
        eye, target = views.view(scene_version, name)
        eye_base = base_scene.stage_to_base(eye, pharmacy_origin)
        hits = set()
        for path_str, low, high in prims:
            inside = all(low[i] <= eye_base[i] <= high[i] for i in range(3))
            if inside:
                hits.add(("eye", path_str))
        for point in subjects + [target]:
            end = base_scene.stage_to_base(point, pharmacy_origin)
            for k in range(1, samples):
                q = tuple(eye_base[i] + (end[i] - eye_base[i]) * k / samples for i in range(3))
                for path_str, low, high in prims:
                    if all(low[i] <= q[i] <= high[i] for i in range(3)):
                        hits.add(("sight", path_str))
        result[name] = {"eye_base": [round(v, 2) for v in eye_base],
                        "hits": sorted(f"{kind} {p}" for kind, p in hits)}
    return result


def to_base_box(low, high, pharmacy_origin):
    corners = [base_scene.stage_to_base((x, y, z), pharmacy_origin)
               for x in (low[0], high[0]) for y in (low[1], high[1]) for z in (low[2], high[2])]
    return tuple(min(c[i] for c in corners) for i in range(3)), tuple(max(c[i] for c in corners) for i in range(3))


def footprint_overlaps(stage, pharmacy_origin, scene_version, min_height):
    """Base prims (leaf-ish: children of the hospital environment and top-level scene prims) overlapping our boxes."""
    from pxr import Usd, UsdGeom

    cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ["default", "render"])
    default = stage.GetDefaultPrim()
    candidates = []
    for prim in default.GetChildren():
        if not prim.IsActive():
            continue
        if prim.GetName() == "Environment":
            for env in prim.GetChildren():
                candidates.extend(child for child in env.GetChildren() if child.IsActive())
        else:
            candidates.append(prim)
    ours = [(name,) + to_base_box(low, high, pharmacy_origin) for name, low, high in pharmacy_boxes(scene_version)]
    hits = []
    for prim in candidates:
        rng = cache.ComputeWorldBound(prim).ComputeAlignedRange()
        if rng.IsEmpty():
            continue
        low, high = rng.GetMin(), rng.GetMax()
        if high[2] - low[2] < min_height:
            continue
        with_ours = sorted({name for name, lo, hi in ours
                            if all(low[i] < hi[i] and lo[i] < high[i] for i in range(3))})
        if with_ours:
            hits.append({"prim": str(prim.GetPath()), "low": [round(v, 2) for v in low],
                         "high": [round(v, 2) for v in high], "with": with_ours[:6]})
    return hits


def main(argv=None):
    args = parse_args(argv)
    try:
        import pxr  # noqa: F401
    except ImportError:
        print("usd-core (pxr) is needed: python3 -m pip install usd-core", file=sys.stderr)
        return 2
    path = Path(args.scene).expanduser()
    report = {"scene": str(path), "layer": layer_report(path)}
    if not report["layer"]["placeholders"]:
        report["composed"] = composed_report(path, args.pharmacy_origin, args.deactivate, args.scene_version,
                                             args.min_height, args.rigid_off)
    elif args.pharmacy_origin is not None:
        report["composed"] = "skipped: the scene still has asset placeholders (run prepare_hospital_scene.py)"
    print(json.dumps(report, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
