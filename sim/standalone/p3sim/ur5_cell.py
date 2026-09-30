"""UR5 on a fixed pedestal at the belt end with deck slots: a stand-in for the docked Ridgeback_UR5 (Isaac side).

Library parts only: Isaac 5.1 asset Isaac/Robots/UniversalRobots/ur5/ur5.usd from get_assets_root_path(), and the
UR5 Lula kinematics shipped with isaacsim.robot_motion.motion_generation (load_supported_lula_kinematics_solver_config,
end effector tool0, cspace shoulder_pan_joint..wrist_3_joint). The tool is suction, as contract 2.1 /amr_1/gripper/
command says "true = 닫기(흡착)": on suck the pouch follows the end link by teleport every update (no prim edits while
simulating, see PouchPool). Imports Isaac inside methods.
"""

import math

from . import common
from . import layout as L
from . import sensors as S

UR5_ASSET = "/Isaac/Robots/UniversalRobots/ur5/ur5.usd"
UR5_JOINTS = ("shoulder_pan_joint", "shoulder_lift_joint", "elbow_joint", "wrist_1_joint", "wrist_2_joint",
              "wrist_3_joint")
TOOL_DOWN = (0.0, 1.0, 0.0, 0.0)
#: 받침대 UR5 밑동의 TF 프레임 이름(네임스페이스 뒤에 붙는다). **결정 47(재범 9/21)**: `amr_1/base_link` 는
#: base_driver 가 이동 베이스용으로 내는 이름이라, 스테이지가 그것을 child 로 내면 어느 조합에서든 계약 3절
#: 위반이다. 새 이름은 공식 Ridgeback+UR5 자산·URDF 의 링크 이름과 같다 — **강제가 아니라 읽는 사람이 덜
#: 헷갈려서다**(`isaac:nameOverride` 로 다른 이름도 된다).
UR5_BASE_LINK = "ur_arm_base_link"


PEDESTAL_SIZE = (0.30, 0.30)  # the stand's (x, y) footprint, m; --ur5-pedestal-size overrides it for a run


class Ur5Cell:
    def __init__(self, stage, world, root, cfg, log):
        """cfg: base (x, y, z top of pedestal), usd ('' = assets root), deck_center, deck_count, deck_slot_size,
        deck_wall, ready, tcp_offset, tcp_speed, clearance, pause_s, timeout_s, tolerance, suck_distance, pouch_height,
        loop, namespace."""
        self.stage, self.world, self.root, self.cfg, self.log = stage, world, root, cfg, log
        self.robot = None
        self.demo = None
        self.held = None
        self.deck_fill = []
        self.render_products = 0
        self.last_ik = None  # (tcp target, solved, {joint: target}) of the last ik_to, for ik_report
        self.pinned = []  # (joint path, localPos0 written) from _pin_world_joints, checked again in ready()

    # ---- build (before world.reset) ----
    def build(self):
        import numpy as np
        from isaacsim.core.api.objects import FixedCuboid
        from isaacsim.core.prims import SingleArticulation
        from isaacsim.core.utils.stage import add_reference_to_stage

        cfg = self.cfg
        bx, by, bz = cfg["base"]
        # The stand is 0.30 x 0.30 and as tall as the base, so raising the base grows a column under the shoulder.
        # L3-2 12d (9/20, base z 0.80): upper_arm hit its own pedestal 65 times at impulse 162, where z 0.45 had 3 at
        # 17.9. A run can make the footprint narrower to tell that obstacle apart from the shoulder height. The stand
        # is a stand-in for the AMR deck, not a real device, so neither its footprint nor its height is a contract
        # value.
        #
        # Narrowing has a floor, though: the arm's shoulder and elbow turn in a plane that contains the base axis
        # (UR5_DH joints 2 and 3 have d = 0), so a column under the shoulder is in the sweep whenever the arm reaches
        # below horizontal, however thin it is. L3-2 12h (base z 0.90, footprint 0.10): while lowering into a deck
        # slot the forearm rode the column for 240-360 ticks at z 0.58-0.63 and shoulder_lift stuck at 1.33 rad.
        # A shorter stand takes the column out of that band instead of only moving its side. The robot is fixed to the
        # world (see _pin_world_joints), so it does not fall when the stand no longer reaches it.
        px, py = pedestal_footprint(cfg.get("pedestal_size"))
        ph = pedestal_height(cfg.get("pedestal_height"), bz)
        FixedCuboid(prim_path=f"{self.root}/Pedestal", name="ur5_pedestal", position=np.array((bx, by, ph / 2.0)),
                    scale=np.array((px, py, ph)), size=1.0, color=np.array(L.COLORS["carriage"]))
        if (px, py) != PEDESTAL_SIZE:
            self.log(f"ur5 pedestal_size=[{px:.4f}, {py:.4f}] default={list(PEDESTAL_SIZE)} (diagnostic)")
        if abs(ph - bz) > 1e-9:
            self.log(f"ur5 pedestal_height={ph:.4f} base_z={bz:.4f} gap={bz - ph:.4f} (diagnostic: the stand no "
                     f"longer reaches the robot, which is fixed to the world)")
        boxes, self.slots = L.deck_boxes(cfg["deck_center"], cfg["deck_count"], cfg["deck_slot_size"], cfg["deck_wall"])
        from . import scene

        scene.build_boxes(f"{self.root}/Deck", boxes)
        usd = cfg["usd"]
        if not usd:
            from isaacsim.storage.native import get_assets_root_path

            # 5.1.0 nucleus.py: waits up to the asset-root timeout setting (default 10 s), then raises RuntimeError.
            assets = get_assets_root_path()
            if assets is None:
                raise RuntimeError("get_assets_root_path() returned None; pass --ur5-usd with a local UR5 USD")
            usd = assets + UR5_ASSET
        self.usd = usd
        prim_path = f"{self.root}/UR5"
        add_reference_to_stage(usd_path=usd, prim_path=prim_path)
        self.prim_path = prim_path
        from pxr import Usd

        names = {p.GetName() for p in Usd.PrimRange(self.stage.GetPrimAtPath(prim_path), Usd.TraverseInstanceProxies())}
        self.end_link = S.pick_end_link(names)
        if "base_link" not in names or self.end_link is None:
            self.stage.RemovePrim(self.root)  # before play only: nothing simulates yet
            raise RuntimeError(f"UR5 reference {usd} did not load (base_link or any of {S.END_LINK_CANDIDATES} "
                               f"missing; {len(names)} prims)")
        self.log(f"ur5 end_link={self.end_link} candidates={S.END_LINK_CANDIDATES} "
                 f"end_to_tool={'known' if self.end_link in S.END_TO_TOOL else 'identity (unconfirmed)'}")
        # SIM-9 (L3-2 9/20, 13a2dfd pin_check): the UR5 prim's composed USD position stayed at the origin although
        # SingleArticulation got position=pedestal, so PhysX parsed the fixed-base robot at the origin. Author the
        # prim translation in USD here, before world.reset parses physics; the world anchor below matches it.
        placed_ok, placed = place_prim(self.stage, prim_path, cfg["base"])
        self.log(f"ur5 prim_translate set_ok={placed_ok} composed_world={common.format_values(placed)} "
                 f"pedestal={common.format_values(cfg['base'])}")
        self._pin_world_joints(prim_path, cfg["base"])
        # Added to the scene only after the reference is known good, so a failed load can be dropped cleanly.
        self.robot = self.world.scene.add(SingleArticulation(prim_path=prim_path, name="ur5_loading",
                                                             position=np.array(cfg["base"])))
        self.log(f"ur5 built usd={usd} prim={prim_path} base={common.format_values(cfg['base'])} "
                 f"deck_slots={[common.format_values(s, 3) for s in self.slots]}")

    def _pin_world_joints(self, prim_path, base_xyz):
        """Move joints that fix the UR5 to the world (body0 empty) to the pedestal.

        9/17 master02 3b114c4: Lula FK of tool0 and the end prim pose agreed at (0.80, 0.21, 0.27) with the pedestal at
        (3.25, 0.55, 0.45). Our reading: the asset's world-fixed root joint keeps its authored world anchor (localPos0
        is in world coordinates when body0 is empty), so the robot simulates at the stage origin whatever the prim
        translation is. Not confirmed; the log line shows what the asset has."""
        from pxr import Gf, Usd, UsdPhysics

        found = []
        for prim in Usd.PrimRange(self.stage.GetPrimAtPath(prim_path), Usd.TraverseInstanceProxies()):
            if not prim.IsA(UsdPhysics.Joint):
                continue
            joint = UsdPhysics.Joint(prim)
            body0 = joint.GetBody0Rel().GetTargets()
            if body0:
                continue
            before = joint.GetLocalPos0Attr().Get() or Gf.Vec3f(0.0, 0.0, 0.0)
            if prim.IsInstanceProxy():
                found.append(f"{prim.GetPath()}(instance proxy, not moved, local_pos0={tuple(before)})")
                continue
            after = Gf.Vec3f(*(float(b) + float(o) for b, o in zip(before, base_xyz, strict=True)))
            written = joint.GetLocalPos0Attr().Set(after)
            self.pinned.append((str(prim.GetPath()), tuple(float(v) for v in after)))
            found.append(f"{prim.GetPath()} body1={[str(t) for t in joint.GetBody1Rel().GetTargets()]} "
                         f"local_pos0={common.format_values(tuple(before))}->{common.format_values(tuple(after))} "
                         f"set_ok={bool(written)} articulation_root={prim.HasAPI(UsdPhysics.ArticulationRootAPI)}")
        self.log(f"ur5 world_joints count={len(found)} {found or 'none (base not fixed by a joint)'}")

    def add_camera_and_tf(self, render_hz, world_root=None):
        """Hand camera on tool0 and TF graph with contract frame names. Call after build(), before world.reset.

        `world_root` 를 주면 `map → <밑동>` 정적 TF 도 낸다(그 프림의 이름이 부모 프레임 이름이 된다).
        """
        import omni.graph.core as og
        import usdrt.Sdf
        from pxr import Gf, Sdf, Usd, UsdGeom

        cfg = self.cfg
        ns = cfg.get("namespace", "/amr_1")
        stage = self.stage
        links = {p.GetName(): p for p in Usd.PrimRange(stage.GetPrimAtPath(self.prim_path),
                                                       Usd.TraverseInstanceProxies())}
        end = self.end_link
        missing = [name for name in ("base_link", end, *S.UR5_LINKS) if name not in links]
        if missing:
            raise RuntimeError(f"UR5 links {missing} not found under {self.prim_path}")
        proxies = [str(p.GetPath()) for p in (links["base_link"], links[end], *[links[n] for n in S.UR5_LINKS])
                   if p.IsInstanceProxy()]
        if proxies:
            raise RuntimeError(f"UR5 links are instance proxies {proxies[:3]}; "
                               "cannot add the camera or isaac:nameOverride")
        from . import geometry as G

        end_path = links[end].GetPath()
        to_tool = S.END_TO_TOOL.get(end, (1.0, 0.0, 0.0, 0.0))
        # USD cameras look along -Z with +Y up; 180 deg about x makes the view follow the tool +Z, expressed in the end
        # prim's frame through END_TO_TOOL.
        camera_quat = G.quat_multiply(to_tool, (0.0, 1.0, 0.0, 0.0))
        camera_offset = G.quat_rotate(to_tool, cfg["camera_offset"])
        camera = UsdGeom.Camera.Define(stage, end_path.AppendChild("hand_camera"))
        xform = UsdGeom.Xformable(camera)
        xform.AddTranslateOp().Set(Gf.Vec3d(*camera_offset))
        xform.AddOrientOp().Set(Gf.Quatf(*map(float, camera_quat)))
        camera.CreateFocalLengthAttr(float(cfg["camera_focal_mm"]))
        camera.CreateClippingRangeAttr(Gf.Vec2f(0.01, 10.0))
        # REP 103 optical frame (x right, y down, z forward) = camera frame turned 180 deg about x again.
        optical = UsdGeom.Xform.Define(stage, camera.GetPath().AppendChild("optical"))
        optical.AddOrientOp().Set(Gf.Quatf(0.0, 1.0, 0.0, 0.0))
        # 받침대 UR5 의 밑동 프레임 이름. 기본은 `amr_1/base_link` 인데 **그 이름의 작성자는 base_driver 다**
        # (계약 420–434줄: 부모 `amr_1/odom`). 한 바퀴 조합에서 같은 child 에 부모가 둘이면 tf2 트리가
        # 메시지마다 뒤집히고 fleet 의 `map → amr_1/base_link` 조회(도착 판정의 유일한 위치 출처)가 깨진다.
        # 재범 결정 47 이 새 이름을 정할 때까지 인자로 둔다 — 기본값은 지금 이름이라 동작이 안 바뀐다.
        base_frame = cfg.get("base_frame") or S.frame(ns, UR5_BASE_LINK)
        names = {links["base_link"]: base_frame, optical.GetPrim(): S.frame(ns, "hand_camera_optical")}
        names.update({links[name]: S.frame(ns, name) for name in (*S.UR5_LINKS, end)})
        # 결정 23 (재범 9/20): deck_slot_N = centre of the slot floor's top face, where a pouch rests. The Floor cuboid
        # is scaled to (sx, sy, wall) around its centre, so a child at local z +0.5 sits wall/2 higher, on that face.
        deck_paths = []
        for i in range(cfg["deck_count"]):
            top = UsdGeom.Xform.Define(stage, f"{self.root}/Deck/DeckSlot{i + 1}Floor/{L.DECK_FRAME_CHILD}")
            top.AddTranslateOp().Set(Gf.Vec3d(0.0, 0.0, 0.5))
            deck_paths.append(str(top.GetPath()))
        for path, name in zip(deck_paths, S.deck_frames(ns, cfg["deck_count"]), strict=True):
            names[stage.GetPrimAtPath(path)] = name
        for prim, name in names.items():
            if not prim.IsValid():
                raise RuntimeError(f"frame prim for {name} is not valid")
            prim.CreateAttribute("isaac:nameOverride", Sdf.ValueTypeNames.String).Set(name)
        skip = S.frame_skip(render_hz, cfg["camera_max_hz"])
        width, height = cfg["camera_resolution"]
        dynamic = [str(links[name].GetPath()) for name in (*S.UR5_LINKS, end)] + [str(optical.GetPath())]
        keys = og.Controller.Keys
        og.Controller.edit(
            {"graph_path": f"{self.root}/SensorGraph", "evaluator_name": "execution"},
            {
                keys.CREATE_NODES: [
                    ("OnTick", "omni.graph.action.OnPlaybackTick"),
                    ("SimTime", "isaacsim.core.nodes.IsaacReadSimulationTime"),
                    ("RenderProduct", "isaacsim.core.nodes.IsaacCreateRenderProduct"),
                    ("CameraRgb", "isaacsim.ros2.bridge.ROS2CameraHelper"),
                    ("CameraInfo", "isaacsim.ros2.bridge.ROS2CameraInfoHelper"),
                    ("TfDynamic", "isaacsim.ros2.bridge.ROS2PublishTransformTree"),
                    ("TfStatic", "isaacsim.ros2.bridge.ROS2PublishTransformTree"),
                ],
                keys.CONNECT: [
                    ("OnTick.outputs:tick", "RenderProduct.inputs:execIn"),
                    ("RenderProduct.outputs:execOut", "CameraRgb.inputs:execIn"),
                    ("RenderProduct.outputs:execOut", "CameraInfo.inputs:execIn"),
                    ("RenderProduct.outputs:renderProductPath", "CameraRgb.inputs:renderProductPath"),
                    ("RenderProduct.outputs:renderProductPath", "CameraInfo.inputs:renderProductPath"),
                    ("OnTick.outputs:tick", "TfDynamic.inputs:execIn"),
                    ("OnTick.outputs:tick", "TfStatic.inputs:execIn"),
                    ("SimTime.outputs:simulationTime", "TfDynamic.inputs:timeStamp"),
                    ("SimTime.outputs:simulationTime", "TfStatic.inputs:timeStamp"),
                ],
                keys.SET_VALUES: [
                    ("SimTime.inputs:resetOnStop", False),
                    ("RenderProduct.inputs:cameraPrim", [usdrt.Sdf.Path(str(camera.GetPath()))]),
                    ("RenderProduct.inputs:width", int(width)),
                    ("RenderProduct.inputs:height", int(height)),
                    ("CameraRgb.inputs:type", "rgb"),
                    ("CameraRgb.inputs:nodeNamespace", ns.strip("/") + "/hand_camera"),
                    ("CameraRgb.inputs:topicName", "image_raw"),
                    ("CameraRgb.inputs:frameId", S.frame(ns, "hand_camera_optical")),
                    ("CameraRgb.inputs:qosProfile", S.SENSOR_QOS_DEPTH2),
                    ("CameraRgb.inputs:frameSkipCount", skip),
                    ("CameraInfo.inputs:nodeNamespace", ns.strip("/") + "/hand_camera"),
                    ("CameraInfo.inputs:topicName", "camera_info"),
                    ("CameraInfo.inputs:frameId", S.frame(ns, "hand_camera_optical")),
                    ("CameraInfo.inputs:qosProfile", S.SENSOR_QOS_DEPTH2),
                    ("CameraInfo.inputs:frameSkipCount", skip),
                    ("TfDynamic.inputs:parentPrim", [usdrt.Sdf.Path(str(links["base_link"].GetPath()))]),
                    ("TfDynamic.inputs:targetPrims", [usdrt.Sdf.Path(path) for path in dynamic]),
                    ("TfDynamic.inputs:topicName", "tf"),
                    ("TfStatic.inputs:parentPrim", [usdrt.Sdf.Path(str(links["base_link"].GetPath()))]),
                    ("TfStatic.inputs:targetPrims", [usdrt.Sdf.Path(path) for path in deck_paths]),
                    ("TfStatic.inputs:topicName", "tf_static"),
                    ("TfStatic.inputs:staticPublisher", True),
                ],
            },
        )
        if world_root:
            # 밑동 프레임에는 **부모가 없다** — 위 두 발행기에서 밑동은 parentPrim 이라 child 로 안 나간다.
            # 전에는 이름이 `amr_1/base_link` 라 base_driver 의 `odom → amr_1/base_link` 가 **우연히** 부모를
            # 붙여 줬다(그 변환은 AMR 자세라 값은 틀렸다). 이름을 갈랐으니 그 우연도 없어진다 —
            # 팔이 `<zone>/cabinet`(부모 `map`)을 조회하면 **끊긴 두 트리 사이**라 실패한다(K5 에서 물린다).
            # 받침대 UR5 는 월드 고정이라 이 변환을 아는 것은 스테이지뿐이다. 그래서 여기서 낸다.
            og.Controller.edit(
                {"graph_path": f"{self.root}/BaseFrameGraph", "evaluator_name": "execution"},
                {
                    keys.CREATE_NODES: [
                        ("BaseTick", "omni.graph.action.OnPlaybackTick"),
                        ("BaseTime", "isaacsim.core.nodes.IsaacReadSimulationTime"),
                        ("TfBase", "isaacsim.ros2.bridge.ROS2PublishTransformTree"),
                    ],
                    keys.CONNECT: [
                        ("BaseTick.outputs:tick", "TfBase.inputs:execIn"),
                        ("BaseTime.outputs:simulationTime", "TfBase.inputs:timeStamp"),
                    ],
                    keys.SET_VALUES: [
                        ("BaseTime.inputs:resetOnStop", False),
                        ("TfBase.inputs:parentPrim", [usdrt.Sdf.Path(world_root)]),
                        ("TfBase.inputs:targetPrims", [usdrt.Sdf.Path(str(links["base_link"].GetPath()))]),
                        ("TfBase.inputs:topicName", "tf_static"),
                        ("TfBase.inputs:staticPublisher", True),
                    ],
                },
            )
            self.log(f"ur5 base_frame_tf parent={world_root.rsplit('/', 1)[-1]} child={base_frame} "
                     f"topic=tf_static (받침대 UR5 는 월드 고정이라 이 변환을 아는 것은 스테이지뿐이다)")
        self.render_products = 1
        self.log(f"ur5 sensors camera={camera.GetPath()} resolution={width}x{height} "
                 f"rate={S.published_rate(render_hz, skip):.1f}Hz(skip {skip}) "
                 f"topics=/{ns.strip('/')}/hand_camera/image_raw,camera_info "
                 f"frame={S.frame(ns, 'hand_camera_optical')} "
                 f"tf_parent={base_frame} tf_dynamic={len(dynamic)} tf_static={len(deck_paths)} "
                 f"world_root={world_root or '-'} (결정 47: 밑동 이름은 {S.frame(ns, UR5_BASE_LINK)})")

    # ---- after world.reset ----
    def ready(self, log_dofs):
        import numpy as np
        from isaacsim.core.prims import SingleXFormPrim
        from isaacsim.core.utils.types import ArticulationAction
        from isaacsim.robot_motion.motion_generation import ArticulationKinematicsSolver, LulaKinematicsSolver
        from isaacsim.robot_motion.motion_generation.interface_config_loader import (
            load_supported_lula_kinematics_solver_config,
        )
        from pxr import Usd

        robot = self.robot
        for _ in range(50):
            if robot.handles_initialized and robot.get_joint_positions() is not None:
                break
            robot.initialize()
            self.world.step(render=True)
        else:
            raise RuntimeError(f"UR5 at {self.prim_path} gives no joint positions after 50 tries")
        log_dofs(robot)
        names = list(robot.dof_names)
        missing = [n for n in UR5_JOINTS if n not in names]
        if missing:
            raise RuntimeError(f"UR5 dofs {missing} missing; have {names}")
        self.arm_idx = np.array([robot.get_dof_index(n) for n in UR5_JOINTS])
        links = {p.GetName(): str(p.GetPath()) for p in Usd.PrimRange(self.stage.GetPrimAtPath(self.prim_path),
                                                                     Usd.TraverseInstanceProxies())}
        end = self.end_link
        if end not in links:
            raise RuntimeError(f"{end} not under {self.prim_path}; links: {sorted(links)}")
        self.tool = SingleXFormPrim(prim_path=links[end], name="ur5_end_link")
        kinematics = load_supported_lula_kinematics_solver_config("UR5")
        if not kinematics:
            raise RuntimeError("load_supported_lula_kinematics_solver_config('UR5') returned nothing")
        self.lula = LulaKinematicsSolver(**kinematics)
        position, orientation = robot.get_world_pose()
        self.lula.set_robot_base_pose(robot_position=position, robot_orientation=orientation)
        self.solver = ArticulationKinematicsSolver(robot, self.lula, "tool0")
        self._action = ArticulationAction
        report = pin_report(self.stage, self.prim_path, self.pinned, self.cfg["base"])
        self.log(f"ur5 pin_check {report['line']}")
        for problem in report["problems"]:
            self.log(f"ur5 pin_failed {problem}")
        self.log(f"ur5 ready joints={list(UR5_JOINTS)} end_link={links[end]} ik_frame=tool0(lula) lula={kinematics} "
                 f"base_pose={common.format_values(position)}")
        prim_xyz = tuple(map(float, self.tool.get_world_pose()[0]))
        fk_xyz = self.tcp()[1][0]
        base_link = SingleXFormPrim(prim_path=links["base_link"], name="ur5_base_link")
        base_link_xyz = tuple(map(float, base_link.get_world_pose()[0]))
        from_base = math.dist(fk_xyz, self.cfg["base"])
        self.log(f"ur5 tcp_source fk_tool0={common.format_values(fk_xyz)} end_prim={common.format_values(prim_xyz)} "
                 f"difference_m={math.dist(fk_xyz, prim_xyz):.4f} base_link={common.format_values(base_link_xyz)} "
                 f"articulation={common.format_values(position)} pedestal={common.format_values(self.cfg['base'])} "
                 f"tool0_from_pedestal_m={from_base:.3f} (tcp uses fk)")
        if from_base > 1.2 or math.dist(base_link_xyz, self.cfg["base"]) > 0.05:
            self.log("ur5 base_frame_mismatch: the simulated UR5 is not on its pedestal; picks will fail IK")

    # ---- motion helpers ----
    def tcp(self):
        """(TCP xyz, (tool0 xyz, tool0 quat)) in world from Lula forward kinematics of the current joints.

        Same frame the IK solves for. 9/17 master02 7ae2879: the start point read from the end prim pose (an
        instance proxy under the UR5 reference) came out about 2.5 m from the pedestal, so every interpolated target
        failed IK."""
        from . import geometry as G

        position, rotation = self.solver.compute_end_effector_pose()
        xyz = tuple(map(float, position))
        quat = G.quat_from_matrix([[float(v) for v in row] for row in rotation])
        return L_tcp(xyz, quat, self.cfg["tcp_offset"]), (xyz, quat)

    def ik_to(self, tcp_xyz):
        import numpy as np

        from . import geometry as G

        offset = G.quat_rotate(TOOL_DOWN, self.cfg["tcp_offset"])
        flange = np.array([t - o for t, o in zip(tcp_xyz, offset, strict=True)])
        action, solved = self.solver.compute_inverse_kinematics(target_position=flange,
                                                                target_orientation=np.array(TOOL_DOWN))
        targets = {}
        positions = getattr(action, "joint_positions", None)
        if positions is not None:
            indices = getattr(action, "joint_indices", None)
            names = ([self.robot.dof_names[int(i)] for i in indices] if indices is not None
                     else list(self.robot.dof_names))
            targets = {name: float(value) for name, value in zip(names, positions, strict=False)
                       if value is not None}
        self.last_ik = (tuple(float(v) for v in tcp_xyz), bool(solved), targets)
        if solved:
            self.robot.apply_action(action)
        return solved

    def slot_centres(self):
        """상판 칸의 **지금** 세계 좌표. 빌드 때 계산한 `self.slots` 를 그대로 쓰지 않는다.

        지금은 상판이 월드 고정이라 두 값이 같다. **K2b 로 상판이 베이스 위로 가면 달라진다** —
        그때 `self.slots` 를 쓰면 봉투 센서의 "상판 칸 안인가" 판정이 **AMR 이 움직인 만큼 틀린다.**
        조회 실패가 아니라 조용히 틀린 값이라, 그때 가서 고치면 이미 늦다(9/21 에 TF 에서 같은 것을 봤다).
        프림을 못 읽으면 빌드 값으로 물러난다 — 진단 경로가 센서를 멈추면 안 된다.
        """
        try:
            from isaacsim.core.prims import SingleXFormPrim

            centres = []
            for index in range(self.cfg["deck_count"]):
                path = f"{self.root}/Deck/DeckSlot{index + 1}Floor"
                prim = SingleXFormPrim(prim_path=path, name=f"ur5_deck_slot_{index + 1}")
                centres.append(tuple(float(v) for v in prim.get_world_pose()[0]))
            return centres
        except Exception as error:  # 진단 경로가 센서를 멈추면 안 된다
            self.log(f"ur5 slot_centres fell back to build values {type(error).__name__}: {error}")
            return list(self.slots)

    def spawn_at(self, tcp_xyz):
        """관절을 ready 자세로 **직접 써서** 스폰한다. 드라이브 목표만 주는 `ik_to` 와 다르다.

        왜 필요한가(비전 9/21, 실습23a): `--mode ros` 에서는 아무도 팔을 ready 로 보내지 않아 USD 의 0 자세로
        서 있다. 0 자세는 팔을 수평으로 다 편 자세이고, 팔 노드는 기동 때 홈으로 가지 않으므로 **첫 픽이
        그 자세에서 출발한다.** `move_to_pose` 는 관절 공간 직선이고 중간 충돌 검사가 없다 — selfdemo 만
        돌던 실습12 는 이 구간을 본 적이 없다.

        반환 (풀렸나, 관절 이름→값). 못 풀면 아무것도 쓰지 않는다 — 반쯤 옮긴 자세가 제일 나쁘다.
        """
        import numpy as np

        solved = self.ik_to(tcp_xyz)
        _tcp, _ok, targets = self.last_ik
        if not solved or not targets:
            return (False, targets)
        names = [name for name in UR5_JOINTS if name in targets]
        indices = np.array([self.robot.get_dof_index(name) for name in names])
        values = np.array([targets[name] for name in names])
        self.robot.set_joint_positions(values, joint_indices=indices)
        self.robot.set_joint_velocities(np.zeros(len(names)), joint_indices=indices)
        return (True, {name: targets[name] for name in names})

    def ik_report(self):
        """One line for a TIMEOUT: the last IK solution's joint targets against the joints as they are now.

        L3-2 9/20: every tcp phase stopped about 6.5-7 cm short. A large gap here means the joints did not follow the
        solution (drives, gravity, a collision, a limit); a small gap with the TCP still off means the solution itself
        was that far from the target (an approximate solve under the fixed tool orientation)."""
        if self.last_ik is None:
            return "no ik call yet"
        target_xyz, solved, targets = self.last_ik
        actual = self.robot.get_joint_positions()
        names = list(self.robot.dof_names)
        now = {name: float(actual[i]) for i, name in enumerate(names)} if actual is not None else {}
        return joint_gap_line(target_xyz, solved, targets, now)

    def follow(self):
        import numpy as np

        from . import geometry as G

        if self.held is None:
            return
        obj, local_xyz, local_quat = self.held
        _tcp, (xyz, quat) = self.tcp()
        obj.set_world_pose(position=np.array(G.tcp_world(xyz, quat, local_xyz)),
                           orientation=np.array(G.quat_multiply(quat, local_quat)))
        obj.set_linear_velocity(np.zeros(3))
        obj.set_angular_velocity(np.zeros(3))

    def suck(self, on, pouch_obj):
        from . import geometry as G

        if on and self.held is None and pouch_obj is not None:
            tcp, (xyz, quat) = self.tcp()
            pos, rot = pouch_obj.get_world_pose()
            pos, rot = tuple(map(float, pos)), tuple(map(float, rot))
            if math.dist(tcp, pos) <= self.cfg["suck_distance"]:
                local_xyz, local_quat = G.relative_pose(xyz, quat, pos, rot)
                self.held = (pouch_obj, local_xyz, local_quat)
                self.log(f"ur5 suction on distance={math.dist(tcp, pos):.4f}")
            else:
                self.log(f"ur5 suction miss distance={math.dist(tcp, pos):.4f} limit={self.cfg['suck_distance']}")
        elif on and self.held is None:
            self.log(f"ur5 suction miss target=none limit={self.cfg['suck_distance']}")
        elif not on and self.held is not None:
            self.held = None
            self.log("ur5 suction off")

    def suck_nearest(self, candidates):
        """Close suction on the candidate pouch nearest the TCP within suck_distance, the same distance rule as suck().

        Candidates are the belt pouch and the pouches already carried to the deck, so a deck pouch can be picked
        again. Still a virtual attach (teleport, see follow): not counted as a physical grasp."""
        if self.held is not None:
            return
        tcp, _ = self.tcp()
        placed = [(obj, tuple(map(float, obj.get_world_pose()[0]))) for obj in candidates]
        target, distance = nearest_within(tcp, placed, self.cfg["suck_distance"])
        if target is None:
            nearest = "-" if distance is None else f"{distance:.4f}"
            self.log(f"ur5 suction miss target=none candidates={len(placed)} nearest={nearest} "
                     f"limit={self.cfg['suck_distance']}")
            return
        self.suck(True, target)

    def holding(self):
        return self.held is not None


def joint_gap(targets, actual):
    """[(joint, target, actual, difference)] sorted by the size of the difference, largest first."""
    rows = [(name, value, actual[name], value - actual[name]) for name, value in targets.items()
            if name in actual]
    return sorted(rows, key=lambda row: abs(row[3]), reverse=True)


def joint_gap_line(target_xyz, solved, targets, actual):
    """ik_report's text: the IK target, whether it solved, and the joints that are furthest from the solution."""
    rows = joint_gap(targets, actual)
    if not rows:
        return (f"tcp_target={common.format_values(target_xyz)} solved={solved} "
                f"joint_targets={len(targets)} joints_read={len(actual)} (nothing to compare)")
    worst = ", ".join(f"{name}: want {value:.4f} have {have:.4f} diff {diff:+.4f}"
                      for name, value, have, diff in rows[:3])
    return (f"tcp_target={common.format_values(target_xyz)} solved={solved} "
            f"max_joint_diff_rad={abs(rows[0][3]):.4f} joints={len(rows)} worst[{worst}]")


def pedestal_footprint(requested):
    """The stand's (x, y) footprint in m: `requested` when given, else PEDESTAL_SIZE, what the stage always used."""
    if requested is None:
        return PEDESTAL_SIZE
    px, py = (float(value) for value in requested)
    if px <= 0.0 or py <= 0.0:
        raise ValueError(f"pedestal size must be positive, got {requested}")
    return (px, py)


def pedestal_height(requested, base_z):
    """The stand's height in m: `requested` when given, else `base_z`, which is what every run so far used.

    Lower than the base leaves a gap between the stand's top and the robot. That is on purpose: the robot is fixed to
    the world, so the stand carries no load and a shorter one takes the column out of the arm's sweep.
    """
    if requested is None:
        return base_z
    height = float(requested)
    if height <= 0.0:
        raise ValueError(f"pedestal height must be positive, got {requested}")
    if height > base_z:
        raise ValueError(f"pedestal height {height} is above the robot base {base_z}; the stand would swallow it")
    return height


def place_prim(stage, prim_path, world_xyz):
    """Author prim_path's translation in USD so its composed world position is world_xyz. Pure pxr.

    Returns (ok, composed world translation read back). Uses XformCommonAPI when the prim's op order allows it, else
    the prim's existing translate op, else a new one. The value is converted into the parent's frame, so a translated
    parent (e.g. the Loading root) does not shift the robot."""
    from pxr import Gf, Usd, UsdGeom

    prim = stage.GetPrimAtPath(prim_path)
    time = Usd.TimeCode.Default()
    parent = prim.GetParent()
    parent_world = (UsdGeom.Xformable(parent).ComputeLocalToWorldTransform(time)
                    if parent and parent.IsA(UsdGeom.Xformable) else Gf.Matrix4d(1.0))
    local = parent_world.GetInverse().Transform(Gf.Vec3d(*map(float, world_xyz)))
    xformable = UsdGeom.Xformable(prim)
    ok = UsdGeom.XformCommonAPI(prim).SetTranslate(local)
    if not ok:
        translate = [op for op in xformable.GetOrderedXformOps() if op.GetOpType() == UsdGeom.XformOp.TypeTranslate]
        op = translate[0] if translate else xformable.AddTranslateOp()
        value = Gf.Vec3f(local) if op.GetPrecision() == UsdGeom.XformOp.PrecisionFloat else local
        ok = bool(op.Set(value))
    placed = tuple(float(v) for v in xformable.ComputeLocalToWorldTransform(time).ExtractTranslation())
    return bool(ok), placed


def pin_report(stage, prim_path, pinned, base_xyz, tolerance=1e-4):
    """Read back, after world.reset, what _pin_world_joints meant to set (L3-2 9/20: the log said localPos0 moved to
    the pedestal but the articulation and base_link stayed at the origin; the old line printed the value written, not
    one read back). Pure pxr, so a usd-core stage works too.

    Reports each pinned joint's composed localPos0 and the layer holding its strongest opinion, the UR5 prim's and
    base_link's composed world translation, and whether base_link resets the xform stack. problems lists what does not
    match: a readback different from the value written, base_link away from the pedestal, a reset xform stack."""
    from pxr import Usd, UsdGeom, UsdPhysics

    problems, joints = [], []
    for path, written in pinned:
        attr = UsdPhysics.Joint(stage.GetPrimAtPath(path)).GetLocalPos0Attr()
        value = attr.Get()
        readback = tuple(float(v) for v in value) if value is not None else None
        stack = attr.GetPropertyStack(Usd.TimeCode.Default())
        layer = stack[0].layer.identifier if stack else "-"
        joints.append(f"{path} written={common.format_values(written)} "
                      f"readback={common.format_values(readback) if readback else None} strongest_layer={layer}")
        if readback is None or math.dist(readback, written) > tolerance:
            problems.append(f"joint={path} localPos0 readback {readback} != written {written} (layer {layer})")
    base_link = next((p for p in Usd.PrimRange(stage.GetPrimAtPath(prim_path), Usd.TraverseInstanceProxies())
                      if p.GetName() == "base_link"), None)
    time = Usd.TimeCode.Default()
    prim_xyz = tuple(UsdGeom.Xformable(stage.GetPrimAtPath(prim_path)).ComputeLocalToWorldTransform(time)
                     .ExtractTranslation())
    base_xyz_now, resets = None, None
    if base_link is not None:
        xformable = UsdGeom.Xformable(base_link)
        base_xyz_now = tuple(xformable.ComputeLocalToWorldTransform(time).ExtractTranslation())
        resets = xformable.GetResetXformStack()
        if resets:
            problems.append(f"base_link {base_link.GetPath()} resets the xform stack: "
                            "it ignores the UR5 prim transform")
        if math.dist(base_xyz_now, base_xyz) > 0.05:
            problems.append(f"base_link composed world {common.format_values(base_xyz_now)} is not the pedestal "
                            f"{common.format_values(base_xyz)}")
    else:
        problems.append(f"no base_link under {prim_path}")
    base_text = common.format_values(base_xyz_now) if base_xyz_now else None
    line = (f"ur5_prim={common.format_values(prim_xyz)} base_link={base_text} "
            f"base_link_resets_xform_stack={resets} joints={joints or 'none pinned'}")
    return {"line": line, "problems": problems}


def nearest_within(tcp, placed, limit):
    """(obj, distance) of the (obj, xyz) pair nearest tcp if within limit, else (None, nearest distance or None)."""
    best = min(placed, key=lambda item: math.dist(tcp, item[1]), default=None)
    if best is None:
        return None, None
    distance = math.dist(tcp, best[1])
    return (best[0], distance) if distance <= limit else (None, distance)


def L_tcp(xyz, quat, offset):
    from . import geometry as G

    return G.tcp_world(xyz, quat, offset)
