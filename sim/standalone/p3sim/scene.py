"""Isaac-side builders for the pharmacy room boxes from layout.py. Imports Isaac inside functions."""

import math

from . import layout as L


def build_boxes(root, boxes):
    """FixedCuboid for 'fixed' boxes, VisualCuboid for 'visual'. Prim path = root/name."""
    import numpy as np
    from isaacsim.core.api.objects import FixedCuboid, VisualCuboid

    made = {}
    for box in boxes:
        cls = FixedCuboid if box.kind == "fixed" else VisualCuboid
        extra = {}
        if box.yaw:
            extra["orientation"] = np.array((math.cos(box.yaw / 2.0), 0.0, 0.0, math.sin(box.yaw / 2.0)))
        made[box.name] = cls(prim_path=f"{root}/{box.name}", name=f"{root.strip('/').replace('/', '_')}_{box.name}",
                             position=np.array(box.center), scale=np.array(box.size), size=1.0,
                             color=np.array(box.color), **extra)
    return made


def build_canisters_v2(root, cells, mass):
    """v2: one canister per shelf cell, a dynamic cylinder or an upright dynamic box (module) by the cell's type.
    Returns {cell_id: (prim_path, obj)}. Built before the simulation starts; moved only by teleport afterwards."""
    import numpy as np
    from isaacsim.core.api.objects import DynamicCuboid, DynamicCylinder

    from . import layout_v2

    canisters = {}
    for cell_id, cell in sorted(cells.items()):
        path = f"{root}/{cell_id.replace('/', '_')}"
        position = np.array(layout_v2.canister_home(cell))
        size = cell["size"]
        if cell["type"] == "cylinder":
            obj = DynamicCylinder(prim_path=path, name=f"canister_{cell_id.replace('/', '_')}", position=position,
                                  radius=size["diameter"] / 2.0, height=size["height"], mass=mass,
                                  color=np.array(L.COLORS["canister"]))
        else:
            obj = DynamicCuboid(prim_path=path, name=f"canister_{cell_id.replace('/', '_')}", position=position,
                                scale=np.array((size["x"], size["y"], size["z"])), size=1.0, mass=mass,
                                color=np.array(L.COLORS["canister_module"]))
        canisters[cell_id] = (path, obj)
    return canisters


def build_canisters(root, cell_centers, size, mass, pick_cell):
    """One dynamic canister standing on every shelf cell; the pick cell is red. Returns {cell: (prim_path, obj)}."""
    import numpy as np
    from isaacsim.core.api.objects import DynamicCuboid

    canisters = {}
    for (row, col), (x, y, z) in sorted(cell_centers.items()):
        path = f"{root}/Canister_r{row}_c{col}"
        color = L.COLORS["canister_pick"] if (row, col) == tuple(pick_cell) else L.COLORS["canister"]
        obj = DynamicCuboid(prim_path=path, name=f"canister_r{row}_c{col}", position=np.array((x, y, z + size[2] / 2)),
                            scale=np.array(size), size=1.0, mass=mass, color=np.array(color))
        canisters[(row, col)] = (path, obj)
    return canisters


def build_conveyor(stage, path, start_xyz, length, width, thickness, yaw, body="xform", presurface=False):
    """Belt box as a kinematic rigid collider, then Isaac 5.1's CreateConveyorBelt (isaacsim.asset.gen.conveyor), as
    its 5.1.0 test does. Returns the graph 'Velocity' variable attribute (m/s).

    body "xform" (default): the rigid body is an unscaled Xform with the scaled Cube as its collider child.
    body "scaled-cube" (the body until 9/17, kept to reproduce): the rigid body is a unit Cube scaled (length, width,
    thickness). The 5.1.0 conveyor node writes direction * velocity to physxSurfaceVelocity:surfaceVelocity in the
    body's local frame. 9/17 master02, window mode + ros: scaled-cube moved pouches at 1.6x (= x scale) in 5/5 laps
    with the attribute at 0.15, xform at 1.0x in 5/5. Headless selfdemo was 1.0x with both bodies (why: not known).
    presurface applies PhysxSurfaceVelocityAPI (enabled, zero velocity) before the first play; otherwise the node
    applies it on its first compute, after the timeline started."""
    import math

    import omni.kit.commands
    from pxr import Gf, UsdGeom, UsdPhysics

    bx, by, bz = start_xyz
    center = (bx + math.cos(yaw) * length / 2.0, by + math.sin(yaw) * length / 2.0, bz - thickness / 2.0)
    if body not in ("scaled-cube", "xform"):
        raise ValueError(f"belt body must be 'scaled-cube' or 'xform', got {body!r}")
    orient = Gf.Quatf(math.cos(yaw / 2.0), 0.0, 0.0, math.sin(yaw / 2.0))
    if body == "xform":
        root = UsdGeom.Xform.Define(stage, path)
        root.AddTranslateOp().Set(Gf.Vec3d(*center))
        root.AddOrientOp().Set(orient)
        cube = UsdGeom.Cube.Define(stage, f"{path}/Surface")
        cube.CreateSizeAttr(1.0)
        UsdGeom.Xformable(cube).AddScaleOp().Set(Gf.Vec3f(length, width, thickness))
        collider = cube.GetPrim()
    else:
        cube = UsdGeom.Cube.Define(stage, path)
        cube.CreateSizeAttr(1.0)
        xform = UsdGeom.Xformable(cube)
        xform.AddTranslateOp().Set(Gf.Vec3d(*center))
        xform.AddOrientOp().Set(orient)
        xform.AddScaleOp().Set(Gf.Vec3f(length, width, thickness))
        collider = cube.GetPrim()
    cube.CreateDisplayColorAttr([(0.12, 0.12, 0.12)])
    prim = stage.GetPrimAtPath(path)
    rigid = UsdPhysics.RigidBodyAPI.Apply(prim)
    rigid.CreateRigidBodyEnabledAttr(True)
    rigid.CreateKinematicEnabledAttr(True)
    UsdPhysics.CollisionAPI.Apply(collider)
    if presurface:
        from pxr import PhysxSchema

        surface = PhysxSchema.PhysxSurfaceVelocityAPI.Apply(prim)
        surface.CreateSurfaceVelocityEnabledAttr(True)
        surface.CreateSurfaceVelocityAttr(Gf.Vec3f(0.0, 0.0, 0.0))
    result = omni.kit.commands.execute("CreateConveyorBelt", conveyor_prim=prim)
    graph_path = str(prim.GetParent().GetPath()) + "/ConveyorBeltGraph"
    graph = stage.GetPrimAtPath(graph_path)
    if not graph.IsValid():
        siblings = [str(child.GetPath()) for child in prim.GetParent().GetChildren()]
        raise RuntimeError(f"CreateConveyorBelt returned {result!r} but {graph_path} does not exist; "
                           f"prims next to the belt: {siblings}; is isaacsim.asset.gen.conveyor enabled?")
    attr = graph.GetAttribute("graph:variable:Velocity")
    if not attr:
        names = [a.GetName() for a in graph.GetAttributes() if "variable" in a.GetName()]
        raise RuntimeError(f"{graph_path} has no graph:variable:Velocity; variable attributes: {names}")
    return attr


def _link(stage, path, world_xyz, mass, parts):
    """Rigid-body Xform at world_xyz with child cubes parts = [(name, local_center, size, color, collide)]."""
    from pxr import Gf, UsdGeom, UsdPhysics

    xform = UsdGeom.Xform.Define(stage, path)
    xform.AddTranslateOp().Set(Gf.Vec3d(*world_xyz))
    prim = xform.GetPrim()
    UsdPhysics.RigidBodyAPI.Apply(prim)
    UsdPhysics.MassAPI.Apply(prim).CreateMassAttr(float(mass))
    for name, center, size, color, collide in parts:
        cube = UsdGeom.Cube.Define(stage, f"{path}/{name}")
        cube.CreateSizeAttr(1.0)
        cube_xform = UsdGeom.Xformable(cube)
        cube_xform.AddTranslateOp().Set(Gf.Vec3d(*center))
        cube_xform.AddScaleOp().Set(Gf.Vec3f(*size))
        cube.CreateDisplayColorAttr([tuple(color)])
        if collide:
            UsdPhysics.CollisionAPI.Apply(cube.GetPrim())
    return prim


def _prismatic(stage, path, body0, body1, axis, lower, upper, drive):
    from pxr import Sdf, UsdPhysics

    joint = UsdPhysics.PrismaticJoint.Define(stage, path)
    joint.CreateBody0Rel().SetTargets([Sdf.Path(body0)])
    joint.CreateBody1Rel().SetTargets([Sdf.Path(body1)])
    joint.CreateAxisAttr(axis)
    joint.CreateLowerLimitAttr(float(lower))
    joint.CreateUpperLimitAttr(float(upper))
    api = UsdPhysics.DriveAPI.Apply(joint.GetPrim(), "linear")
    api.CreateTypeAttr("force")
    api.CreateStiffnessAttr(float(drive[0]))
    api.CreateDampingAttr(float(drive[1]))
    api.CreateMaxForceAttr(float(drive[2]))
    api.CreateTargetPositionAttr(0.0)
    return joint


def ensure_link_visuals(stage, robot_prim, link_names, log=print, radius=0.06):
    """Make every robot visual mesh render, then log how many visible gprims each arm link has.

    재범 실습3 (9/18): "the robot is cut in the middle"; Kit (omni.fabric) warned `getAttributeCount/getTypes called on
    non-existent path …/link_2/visuals/MF0609_2_1/Scene`. 마클2 read the class asset: every link and gripper part has
    an instanceable `visuals` prim, and the meshes exist. Kit logs from 9/17-9/18: each run warns once (2 lines) about
    one instanced visual, usually link_2 but in some runs (9/17 20:42, 실습6 after #167) the gripper's
    right_outer_knuckle — same code, different prim. Our reading: a race in Fabric's population of instance
    prototypes, whichever prim loses is not drawn. Fix on our stage layer only (the asset file is not touched): every
    instanceable `visuals` prim under the robot (arm links and gripper) is made non-instanceable before the first app
    update. Fallback: an arm link with no visual gprim at all gets a grey stand-in cylinder to the next link's origin.
    Returns {link: gprim count}."""
    from pxr import Gf, Usd, UsdGeom

    from . import geometry as G

    released = []
    for prim in Usd.PrimRange(stage.GetPrimAtPath(robot_prim)):
        if prim.GetName() == "visuals" and prim.IsInstanceable():
            prim.SetInstanceable(False)
            released.append(prim.GetParent().GetName())
    log(f"link_visuals made non-instanceable count={len(released)} parts={released}")
    prims = {p.GetName(): p for p in Usd.PrimRange(stage.GetPrimAtPath(robot_prim), Usd.TraverseInstanceProxies())}
    cache = UsdGeom.XformCache()
    counts = {}
    for index, name in enumerate(link_names):
        link = prims.get(name)
        if link is None:
            log(f"link_visuals {name} missing under {robot_prim}")
            continue
        gprims = [p for p in Usd.PrimRange(link, Usd.TraverseInstanceProxies())
                  if p.IsA(UsdGeom.Gprim) and "collision" not in str(p.GetPath()).lower()
                  and p.GetPath() != link.GetPath()]
        counts[name] = len(gprims)
        nxt = prims.get(link_names[index + 1]) if index + 1 < len(link_names) else None
        if gprims or nxt is None or link.IsInstanceProxy():
            continue
        local = cache.GetLocalToWorldTransform(nxt) * cache.GetLocalToWorldTransform(link).GetInverse()
        offset = tuple(float(v) for v in local.ExtractTranslation())
        length = sum(v * v for v in offset) ** 0.5
        if length < 0.02:
            log(f"link_visuals {name} has no visual gprim; next link origin only {length:.3f} m away, no stand-in")
            continue
        cylinder = UsdGeom.Cylinder.Define(stage, link.GetPath().AppendChild("p3_visual_standin"))
        cylinder.CreateRadiusAttr(float(radius))
        cylinder.CreateHeightAttr(float(length))
        cylinder.CreateAxisAttr("Z")
        cylinder.CreateDisplayColorAttr([(0.75, 0.75, 0.78)])
        xform = UsdGeom.Xformable(cylinder)
        xform.AddTranslateOp().Set(Gf.Vec3d(*(v / 2.0 for v in offset)))
        xform.AddOrientOp().Set(Gf.Quatf(*map(float, G.quat_from_z_to(offset))))
        log(f"link_visuals {name} has no visual gprim → grey stand-in cylinder to {link_names[index + 1]} "
            f"length={length:.3f} radius={radius} offset={[round(v, 3) for v in offset]}")
    log(f"link_visuals gprims={counts}")
    return counts


def build_xy_rail_with_robot(stage, arm_root, robot_usd, origin, x_stroke, y_limits, base_height, carriage_height,
                             drive, robot_child="m0609", log=print, z_limits=None, collide_carriages=False):
    """2-axis rail carrying the robot, as one articulation rooted at arm_root.

    Links under arm_root/Rail: Base (fixed to the world by a fixed joint that carries ArticulationRootAPI), CarriageX
    (prismatic 'rail_x' along X), CarriageY (prismatic 'rail_y' along Y, with the pedestal). The robot USD's
    defaultPrim is referenced at arm_root/Mount, and its own root_joint (a world-fixed joint with ArticulationRootAPI
    in the class asset, dev01 9/17) is re-targeted: body0 = CarriageY, ArticulationRootAPI removed. All links start
    at the rail zero so joint local frames are just offsets. Collisions are only on the base track and the robot.
    With z_limits (v2 scene, 재범 9/18): a CarriageZ lift (prismatic 'rail_z' along Z, green plate) sits on CarriageY
    and carries the robot; the robot's root_joint body0 is CarriageZ.
    Returns (articulation_prim_path, robot_prim_path, joint names)."""
    from pxr import Gf, Sdf, Usd, UsdGeom, UsdPhysics

    ox, oy, oz = origin
    rail = f"{arm_root}/Rail"
    UsdGeom.Xform.Define(stage, arm_root)
    link_origin = (ox, oy, oz + base_height / 2.0)
    parts = L.rail_link_parts(x_stroke, y_limits, base_height, carriage_height, lift=z_limits is not None,
                              collide_carriages=collide_carriages,
                              lift_travel=0.0 if z_limits is None else float(z_limits[1]))
    base = _link(stage, f"{rail}/Base", link_origin, 50.0, parts["Base"])
    # Gantry look (재범 실습1 P4): an orange Y beam spanning both X tracks with a truck over each track, moving with
    # rail_x; the blue Y carriage rides the beam with rail_y (parts in layout.rail_link_parts).
    carriage_x = _link(stage, f"{rail}/CarriageX", link_origin, 10.0, parts["CarriageX"])
    carriage_y = _link(stage, f"{rail}/CarriageY", link_origin, 10.0, parts["CarriageY"])
    root = UsdPhysics.FixedJoint.Define(stage, f"{rail}/root_joint")
    root.CreateBody1Rel().SetTargets([base.GetPath()])
    UsdPhysics.ArticulationRootAPI.Apply(root.GetPrim())
    _prismatic(stage, f"{rail}/rail_x", str(base.GetPath()), str(carriage_x.GetPath()), "X", -x_stroke / 2.0,
               x_stroke / 2.0, drive)
    _prismatic(stage, f"{rail}/rail_y", str(carriage_x.GetPath()), str(carriage_y.GetPath()), "Y", y_limits[0],
               y_limits[1], drive)
    carrier = carriage_y
    names = ("rail_x", "rail_y")
    if z_limits is not None:
        carrier = _link(stage, f"{rail}/CarriageZ", link_origin, 10.0, parts["CarriageZ"])
        _prismatic(stage, f"{rail}/rail_z", str(carriage_y.GetPath()), str(carrier.GetPath()), "Z", z_limits[0],
                   z_limits[1], drive)
        names = ("rail_x", "rail_y", "rail_z")

    mount = UsdGeom.Xform.Define(stage, f"{arm_root}/Mount")
    mount.AddTranslateOp().Set(Gf.Vec3d(ox, oy, oz + carriage_height))
    mount.GetPrim().GetReferences().AddReference(robot_usd)
    robot_prim = f"{arm_root}/Mount/{robot_child}"
    mount_prim = stage.GetPrimAtPath(f"{arm_root}/Mount")
    if not stage.GetPrimAtPath(robot_prim).IsValid():
        children = [child.GetName() for child in mount_prim.GetChildren()]
        raise RuntimeError(f"robot prim {robot_prim} missing after referencing {robot_usd}; Mount children: "
                           f"{children}; check --robot-child and that the USD defaultPrim holds the robot")
    robot_root = stage.GetPrimAtPath(f"{robot_prim}/root_joint")
    if not robot_root.IsValid():
        joints = [str(p.GetPath()) for p in Usd.PrimRange(mount_prim) if "Joint" in p.GetTypeName()][:10]
        raise RuntimeError(f"{robot_prim}/root_joint not found; first joints under Mount: {joints}")
    before = list(robot_root.GetAppliedSchemas())
    robot_root.RemoveAPI(UsdPhysics.ArticulationRootAPI)
    if robot_root.HasAPI(UsdPhysics.ArticulationRootAPI):
        raise RuntimeError(f"could not remove ArticulationRootAPI from {robot_root.GetPath()} (schemas {before}); "
                           "the rail and the robot would be two articulations")
    joint = UsdPhysics.Joint(robot_root)
    joint.GetBody0Rel().SetTargets([Sdf.Path(str(carrier.GetPath()))])
    joint.CreateLocalPos0Attr().Set(Gf.Vec3f(0.0, 0.0, float(carriage_height - base_height / 2.0)))
    joint.CreateLocalRot0Attr().Set(Gf.Quatf(1.0, 0.0, 0.0, 0.0))
    joint.CreateLocalPos1Attr().Set(Gf.Vec3f(0.0, 0.0, 0.0))
    joint.CreateLocalRot1Attr().Set(Gf.Quatf(1.0, 0.0, 0.0, 0.0))
    targets = [str(p) for p in joint.GetBody0Rel().GetTargets()]
    if targets != [str(carrier.GetPath())]:
        raise RuntimeError(f"{robot_root.GetPath()} body0 is {targets}, expected {carrier.GetPath()}")
    roots = [str(p.GetPath()) for p in Usd.PrimRange(stage.GetPrimAtPath(arm_root))
             if p.HasAPI(UsdPhysics.ArticulationRootAPI)]
    if roots != [f"{rail}/root_joint"]:
        raise RuntimeError(f"expected exactly one ArticulationRootAPI at {rail}/root_joint, found {roots}")
    log(f"rail rewire robot_root={robot_root.GetPath()} schemas_before={before} "
        f"schemas_after={list(robot_root.GetAppliedSchemas())} body0={targets} articulation_roots={roots}")
    log(f"rail built root={rail}/root_joint joints=rail_x(X {-x_stroke / 2:.2f}..{x_stroke / 2:.2f}) "
        f"rail_y(Y {y_limits[0]:.2f}..{y_limits[1]:.2f}) "
        f"rail_z={'-' if z_limits is None else f'(Z {z_limits[0]:.2f}..{z_limits[1]:.2f})'} drive={tuple(drive)} "
        f"robot={robot_prim} robot_root_body0={carrier.GetPath()} pedestal_top_z={oz + carriage_height:.3f}")
    return arm_root, robot_prim, names


def add_top_texture(stage, face_path, image_path, size_xy, lift):
    """Textured quad for a pouch's +z face (contract 3: QR face is pouch +z). Call before the simulation starts.

    The quad is its own Mesh prim, not a child of the pouch: DynamicCuboid makes the pouch a Cube gprim, and UsdGeom
    does not support gprims nested under gprims. The caller moves the quad to the pouch pose every update. Points are
    in metres around the pouch centre with the face lift above it. Material: UsdPreviewSurface + UsdUVTexture on st."""
    from pxr import Gf, Sdf, UsdGeom, UsdShade, Vt

    hx, hy = size_xy[0] / 2.0, size_xy[1] / 2.0
    mesh = UsdGeom.Mesh.Define(stage, face_path)
    mesh.CreatePointsAttr(Vt.Vec3fArray([Gf.Vec3f(-hx, -hy, lift), Gf.Vec3f(hx, -hy, lift),
                                          Gf.Vec3f(hx, hy, lift), Gf.Vec3f(-hx, hy, lift)]))
    mesh.CreateFaceVertexCountsAttr([4])
    mesh.CreateFaceVertexIndicesAttr([0, 1, 2, 3])
    mesh.CreateNormalsAttr(Vt.Vec3fArray([Gf.Vec3f(0.0, 0.0, 1.0)] * 4))
    st = UsdGeom.PrimvarsAPI(mesh).CreatePrimvar("st", Sdf.ValueTypeNames.TexCoord2fArray, UsdGeom.Tokens.varying)
    st.Set(Vt.Vec2fArray([Gf.Vec2f(0, 0), Gf.Vec2f(1, 0), Gf.Vec2f(1, 1), Gf.Vec2f(0, 1)]))
    root = f"{face_path}_Looks"
    material = UsdShade.Material.Define(stage, f"{root}/QrMaterial")
    shader = UsdShade.Shader.Define(stage, f"{root}/QrMaterial/Surface")
    shader.CreateIdAttr("UsdPreviewSurface")
    shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(0.8)
    reader = UsdShade.Shader.Define(stage, f"{root}/QrMaterial/StReader")
    reader.CreateIdAttr("UsdPrimvarReader_float2")
    reader.CreateInput("varname", Sdf.ValueTypeNames.Token).Set("st")
    texture = UsdShade.Shader.Define(stage, f"{root}/QrMaterial/Texture")
    texture.CreateIdAttr("UsdUVTexture")
    texture.CreateInput("file", Sdf.ValueTypeNames.Asset).Set(str(image_path))
    texture.CreateInput("st", Sdf.ValueTypeNames.Float2).ConnectToSource(reader.ConnectableAPI(), "result")
    texture.CreateOutput("rgb", Sdf.ValueTypeNames.Float3)
    shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).ConnectToSource(texture.ConnectableAPI(), "rgb")
    material.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")
    UsdShade.MaterialBindingAPI.Apply(mesh.GetPrim()).Bind(material)
    return mesh
