"""Put the pharmacy stage on top of a base scene (세준's hospital USD) - pure math, pxr imported lazily.

The stage keeps its own frame as the world frame (rail centre on the floor at the origin): every world-coordinate
call in pharmacy_stage.py (teleports, IK targets, overlap queries, cameras, the inventory JSON) stays as it is. The base
scene is referenced under a wrapper prim whose transform is the inverse of the pharmacy's pose in the base scene, so
the base scene point where the pharmacy origin should sit lands on our origin.

pharmacy_origin = (x, y, z, yaw_deg): our origin and +x direction expressed in the base scene's world frame. The
committed hospital_layout.usda keeps /World at (0, 0, 0), so this is also its map frame.
"""

import fnmatch
import math
import re
from pathlib import Path

BASE_ROOT = "/World/P3Base"
PLACEHOLDER = re.compile(r"__P3_[A-Z_]+__")

# 재범 결정 (9/18, #215 코멘트): M0609 기준(씬 M0617 끔), 원점 A, 우리 벨트(씬 벨트 강체·그래프 끔), /clock 은 우리
# 스테이지 하나. Paths are relative to the hospital scene's default prim and come from hospital_scene_check.py on the
# prepared scene (9/18); pharmacy_stage.py --preset hospital-v2 uses them.
# The old site-A Y (13.3) included hospital_layout.usda's former /World Y offset
# 2.7714578982004503. Keep the physical placement while using the zero-root map frame.
HOSPITAL_ORIGIN_A = (0.25, 10.52854210179955, 0.0, 0.0)

# Deactivated: the 2 medicine cabinets and 24 pill bottle sets on our footprint, the 2 east wall pieces our belt
# passes, and every scene belt graph (ConveyorBeltGraph* and the sorters' ActionGraph). The scene's M0617
# ("manipulator") used to be first here; b9ba0d6 (#233) removed it from the scene, so the 9/18 "M0617 off" decision is
# met by the scene itself.
HOSPITAL_DEACTIVATE = (
    "Environment/hospital/SM_MedicalCabinet_01a2",
    "Environment/hospital/SM_MedicalCabinet_01a_40",
    "Environment/hospital/SM_PillBottleSet_01a10",
    "Environment/hospital/SM_PillBottleSet_01a11",
    "Environment/hospital/SM_PillBottleSet_01a12",
    "Environment/hospital/SM_PillBottleSet_01a13",
    "Environment/hospital/SM_PillBottleSet_01a2_44",
    "Environment/hospital/SM_PillBottleSet_01a3",
    "Environment/hospital/SM_PillBottleSet_01a4",
    "Environment/hospital/SM_PillBottleSet_01a5",
    "Environment/hospital/SM_PillBottleSet_01a6_60",
    "Environment/hospital/SM_PillBottleSet_01a7",
    "Environment/hospital/SM_PillBottleSet_01a8",
    "Environment/hospital/SM_PillBottleSet_01a9",
    "Environment/hospital/SM_PillBottleSet_01e10",
    "Environment/hospital/SM_PillBottleSet_01e11",
    "Environment/hospital/SM_PillBottleSet_01e12",
    "Environment/hospital/SM_PillBottleSet_01e2",
    "Environment/hospital/SM_PillBottleSet_01e3",
    "Environment/hospital/SM_PillBottleSet_01e4",
    "Environment/hospital/SM_PillBottleSet_01e5",
    "Environment/hospital/SM_PillBottleSet_01e6",
    "Environment/hospital/SM_PillBottleSet_01e7",
    "Environment/hospital/SM_PillBottleSet_01e8",
    "Environment/hospital/SM_PillBottleSet_01e9",
    "Environment/hospital/SM_PillBottleSet_01e_52",
    "Environment/hospital/Geo_M2_BaseWallSide3_01",
    "Environment/hospital/Geo_M2_WallDoorCorner5_01",
    "Conveyor/ConveyorTrack_06/ConveyorBeltGraph",
    "Conveyor/ConveyorTrack_12/ConveyorBeltGraph",
    "Conveyor/ConveyorTrack_12/ConveyorBeltGraph_01",
    "Conveyor/ConveyorTrack_02/Sorter/ActionGraph",
    "Conveyor/ConveyorTrack_02/ConveyorBeltGraph",
    "Conveyor/ConveyorTrack_02/ConveyorBeltGraph_01",
    "Conveyor/ConveyorTrack_04/Sorter/ActionGraph",
    "Conveyor/ConveyorTrack_04/ConveyorBeltGraph",
    "Conveyor/ConveyorTrack_04/ConveyorBeltGraph_01",
    "Conveyor/ConveyorTrack_09/Sorter/ActionGraph",
    "Conveyor/ConveyorTrack_09/ConveyorBeltGraph",
    "Conveyor/ConveyorTrack_09/ConveyorBeltGraph_01",
    "Conveyor/ConveyorTrack_03/ConveyorBeltGraph",
    "Conveyor/ConveyorTrack_07/ConveyorBeltGraph",
    "Conveyor/ConveyorTrack/ConveyorBeltGraph",
    "Conveyor/ConveyorTrack_01/ConveyorBeltGraph",
    "Conveyor/ConveyorTrack_05/ConveyorBeltGraph",
    "Conveyor/ConveyorTrack_08/ConveyorBeltGraph",
    "Conveyor/ConveyorTrack_10/ConveyorBeltGraph",
)

# Scene belt rigid bodies: rigid body disabled (they stay visible and keep their collision as static).
HOSPITAL_RIGID_OFF = (
    "Conveyor/ConveyorTrack_06/Belt",
    "Conveyor/ConveyorTrack_12/BeltRamp",
    "Conveyor/ConveyorTrack_12/Belt",
    "Conveyor/ConveyorTrack_02/Rollers",
    "Conveyor/ConveyorTrack_02/Sorter/Sorter_physics",
    "Conveyor/ConveyorTrack_02/Rollers_01",
    "Conveyor/ConveyorTrack_04/Rollers",
    "Conveyor/ConveyorTrack_04/Sorter/Sorter_physics",
    "Conveyor/ConveyorTrack_04/Rollers_01",
    "Conveyor/ConveyorTrack_09/Rollers",
    "Conveyor/ConveyorTrack_09/Sorter/Sorter_physics",
    "Conveyor/ConveyorTrack_09/Rollers_01",
    "Conveyor/ConveyorTrack_03/Rollers",
    "Conveyor/ConveyorTrack_07/Rollers",
    "Conveyor/ConveyorTrack/Rollers",
    "Conveyor/ConveyorTrack_01/Rollers",
    "Conveyor/ConveyorTrack_05/Rollers",
    "Conveyor/ConveyorTrack_08/Rollers",
    "Conveyor/ConveyorTrack_10/Rollers",
)


def wrapper_transform(pharmacy_origin):
    """(translate xyz, rotate_z_deg) for the wrapper: world = Rz(-yaw) * (base - origin)."""
    x, y, z, yaw = (float(v) for v in pharmacy_origin)
    c, s = math.cos(math.radians(-yaw)), math.sin(math.radians(-yaw))
    return (-(c * x - s * y), -(s * x + c * y), -z), -yaw


def base_to_stage(point, pharmacy_origin):
    """A base scene world point in our stage frame."""
    x, y, z, yaw = (float(v) for v in pharmacy_origin)
    dx, dy, dz = point[0] - x, point[1] - y, point[2] - z
    c, s = math.cos(math.radians(-yaw)), math.sin(math.radians(-yaw))
    return (c * dx - s * dy, s * dx + c * dy, dz)


def stage_to_base(point, pharmacy_origin):
    """A stage point in the base scene's world frame."""
    x, y, z, yaw = (float(v) for v in pharmacy_origin)
    c, s = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
    return (x + c * point[0] - s * point[1], y + s * point[0] + c * point[1], z + point[2])


def placeholders(path):
    """`__P3_…__` tokens left in a text USD (the committed hospital_layout.usda before prepare_hospital_scene.py)."""
    path = Path(path)
    if path.suffix != ".usda":
        return []
    return sorted(set(PLACEHOLDER.findall(path.read_text(errors="replace"))))


def layer_units(data):
    """(metersPerUnit, upAxis) authored in the root layer header of a .usda file, as text.

    'unset' when the header does not author the key, 'unknown' when the file is not text USD (a binary .usd needs pxr
    to read). Only the root layer: referenced assets keep their own units."""
    if not data.startswith(b"#usda"):
        return "unknown", "unknown"
    text = data.decode("utf-8", errors="replace")
    body = re.search(r"^(def|over|class)\s", text, re.MULTILINE)
    header = text[:body.start()] if body else text
    meters = re.search(r"^\s*metersPerUnit\s*=\s*([-+0-9.eE]+)\s*$", header, re.MULTILINE)
    up = re.search(r'^\s*upAxis\s*=\s*"(\w+)"\s*$', header, re.MULTILINE)
    return (meters.group(1) if meters else "unset"), (up.group(1) if up else "unset")


def scene_prim_path(path, root=BASE_ROOT, default_prim="World"):
    """씬 파일 기준 prim 경로(`/World/Environment/…`, 앵커 JSON 모양) → 스테이지에 붙은 경로
    (`<root>/Scene/Environment/…`).

    add_base_scene 은 씬의 기본 프림(`/World`)을 `<root>/Scene` 에 reference 한다. 기본 프림 밖 경로는 그대로 둔다.
    """
    prefix = f"/{default_prim}"
    if path == prefix or path.startswith(prefix + "/"):
        return f"{root}/Scene{path[len(prefix):]}"
    return path


def expand_paths(stage, base, patterns):
    """Absolute prim paths for patterns relative to `base`; the last component may hold fnmatch wildcards
    (e.g. Environment/hospital/SM_PillBottleSet_*). Returns (paths, patterns that matched nothing)."""
    from pxr import Sdf

    found, missing = [], []
    for pattern in patterns:
        rel = pattern.strip("/")
        parent_rel, _, leaf = rel.rpartition("/")
        parent = stage.GetPrimAtPath(Sdf.Path(base).AppendPath(parent_rel) if parent_rel else Sdf.Path(base))
        if not any(ch in leaf for ch in "*?["):
            prim = stage.GetPrimAtPath(Sdf.Path(base).AppendPath(rel))
            matches = [prim] if prim and prim.IsValid() else []
        else:
            matches = [c for c in parent.GetChildren() if fnmatch.fnmatchcase(c.GetName(), leaf)] if parent else []
        if matches:
            found.extend(str(m.GetPath()) for m in matches)
        else:
            missing.append(pattern)
    return found, missing


#: 루트 프림 가운데 장면 물체가 아닌 것(렌더 설정·측정 도구). 함께 싣지 않는다.
ROOT_PRIMS_NOT_SCENE = ("Render", "OmniverseKit_Persp", "OmniverseKit_Front", "OmniverseKit_Top",
                        "OmniverseKit_Right", "Viewport_Measure")


def root_prims_outside_default(usd_path):
    """기본 프림 **밖** 루트에 `def` 로 정의된 프림 이름. reference 는 기본 프림만 가져오므로 이것들은 빠진다.

    9/23: `hospital_navigationv1.usda` 의 병상 여섯(D5–D10)이 루트에 있어, GUI 로 열면 보이고 스테이지로는
    사라졌다. 빠지는 것을 알리려고 이름을 돌려준다(`over` 는 정의가 아니라 빼고, 렌더 설정도 뺀다).
    """
    from pxr import Sdf

    layer = Sdf.Layer.FindOrOpen(str(usd_path))
    if layer is None:
        return []
    default = layer.defaultPrim
    return [spec.name for spec in layer.rootPrims
            if spec.name != default and spec.specifier == Sdf.SpecifierDef and spec.name not in ROOT_PRIMS_NOT_SCENE]


def add_base_scene(stage, usd_path, pharmacy_origin, deactivate=(), rigid_off=(), root=BASE_ROOT,
                   root_prims=False):
    """Reference usd_path (its default prim) at root + "/Scene" under a wrapper Xform; deactivate paths given
    relative to the base scene's default prim. Returns a dict for the log (missing deactivation paths included).
    Works on an Isaac stage and on a usd-core stage (tests).

    `root_prims`: 기본 프림 밖 루트 프림도 root + "/SceneRoot/<이름>" 에 하나씩 reference 한다(같은 wrapper 아래라
    좌표는 기본 프림과 같이 움직인다). 끄면 싣지 않고 이름만 `root_prims_skipped` 에 적는다."""
    from pxr import Gf, Sdf, Usd, UsdGeom, UsdPhysics

    translate, rotate_z = wrapper_transform(pharmacy_origin)
    wrapper = UsdGeom.Xform.Define(stage, root)
    wrapper.ClearXformOpOrder()
    wrapper.AddTranslateOp().Set(Gf.Vec3d(*translate))
    wrapper.AddRotateZOp().Set(float(rotate_z))
    scene = stage.DefinePrim(f"{root}/Scene")
    scene.GetReferences().ClearReferences()
    scene.GetReferences().AddReference(str(usd_path))
    outside = root_prims_outside_default(usd_path)
    loaded_roots = []
    if root_prims:
        for name in outside:
            holder = stage.DefinePrim(f"{root}/SceneRoot/{name}")
            holder.GetReferences().ClearReferences()
            holder.GetReferences().AddReference(str(usd_path), Sdf.Path(f"/{name}"))
            loaded_roots.append(name)
    paths, missing = expand_paths(stage, f"{root}/Scene", deactivate)
    for path in paths:
        stage.GetPrimAtPath(path).SetActive(False)
    done = [p[len(root) + len("/Scene/"):] for p in paths]
    rigid_paths, rigid_missing = expand_paths(stage, f"{root}/Scene", rigid_off)
    for path in rigid_paths:  # keep the mesh and its (now static) collision, stop it being a body
        UsdPhysics.RigidBodyAPI.Apply(stage.GetPrimAtPath(path)).CreateRigidBodyEnabledAttr(False)
    # Articulation roots still active in the base scene: nothing in this stage drives them (they only fall or stand).
    prefix = f"{root}/Scene/"
    articulations = [str(prim.GetPath())[len(prefix):]
                     for prim in Usd.PrimRange(scene, Usd.TraverseInstanceProxies(Usd.PrimDefaultPredicate))
                     if prim.HasAPI(UsdPhysics.ArticulationRootAPI)]
    # Hospital integration must preserve the reviewed asset before physics starts.
    # Inspect all children so an inactive known dispenser cannot silently bypass this check.
    from .dispenser_reference import check_hospital_dispenser
    dispenser_checks = [check_hospital_dispenser(stage, str(child.GetPath()))
                        for child in scene.GetAllChildren()
                        if child.GetName() in ('IntegratedDispenser', 'ReviewedDispenser')]
    layer = Sdf.Layer.FindOrOpen(str(usd_path))
    meters = layer.pseudoRoot.GetInfo("metersPerUnit") if layer and layer.pseudoRoot.HasInfo("metersPerUnit") else None
    up = layer.pseudoRoot.GetInfo("upAxis") if layer and layer.pseudoRoot.HasInfo("upAxis") else None
    return {"root": root, "scene": f"{root}/Scene", "translate": [round(v, 4) for v in translate],
            "rotate_z_deg": round(rotate_z, 4), "deactivated": done, "missing": missing + rigid_missing,
            "rigid_off": len(rigid_paths), "articulations": articulations,
            "meters_per_unit": meters, "up_axis": up, "loaded": bool(scene.GetChildren()),
            "root_prims_loaded": loaded_roots, "root_prims_skipped": [] if root_prims else outside,
            "dispenser_checks": dispenser_checks}
