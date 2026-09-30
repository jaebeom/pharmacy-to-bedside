"""Bounded three-shelf friction-grasp trial; no attachment or object following.

Run only on a fresh workcell stage. The nine measured cylinders must exist.
Raw observations are separate from success: both pad contacts and sustained lift.
"""
import json
import math
from pathlib import Path
import random
import secrets
import time


def select_shelves(seed):
    return random.Random(seed).sample(list(range(67, 76)), 3)


def lift_pass(samples, initial_z, minimum_lift=.05, maximum_distance=.10):
    """All samples in the one-second hold must show lift and both pad contacts."""
    return len(samples) >= 60 and all(
        s['position'][2] - initial_z >= minimum_lift
        and s['tcp_distance'] <= maximum_distance
        and s['left_contact'] and s['right_contact'] for s in samples)


class ShelfPickTrial:
    def __init__(self, stage, output, urdf, description, seed=None):
        import numpy as np
        from isaacsim.core.api import World
        from isaacsim.core.prims import SingleArticulation, SingleRigidPrim, SingleXFormPrim
        from isaacsim.robot_motion.motion_generation import LulaKinematicsSolver
        from pxr import Usd, UsdGeom, UsdPhysics, PhysxSchema, UsdShade
        import m0609_refill_stage as refill
        from .workcell_preview import RAIL_ORIGIN
        self.np = np
        self.stage = stage
        self.output = Path(output)
        self.output.mkdir(parents=True, exist_ok=False)
        self.log = (self.output/'events.jsonl').open('x', encoding='utf-8')
        self.seed = secrets.randbits(32) if seed is None else seed
        self.selection = select_shelves(self.seed)
        self.step = 0
        self.phase = 'setup'
        self.item = None
        self.contacts = set()
        self.results = []
        self.wall_start = time.monotonic()
        self.root = '/World/ReviewRailM0609'
        self.robot_path = self.root+'/Mount/m0609'
        self.quat = np.array([math.sqrt(.5), -math.sqrt(.5), 0., 0.])
        self.refill = refill
        self.emit('plan', seed=self.seed, shelves=self.selection, replacement=False,
                  mode='PHYSICS_FRICTION', attachment=False, lift_m=.05, hold_s=1.,
                  tcp_distance_m=.10, both_pad_contacts=True)
        (self.output/'plan.json').write_text(json.dumps({
            'seed': self.seed, 'shelves': self.selection, 'replacement': False,
            'mode': 'PHYSICS_FRICTION', 'physics_dt': 1/60,
            'criteria': '60 consecutive samples: lift >= .05 m, TCP distance <= .10 m, both pads touching'}, indent=2))
        # Existing viewer raised the mount for display. Restore authored rail zero.
        for suffix, z in [('Rail/CarriageZ', .025), ('Mount', .25)]:
            xf = UsdGeom.Xformable(stage.GetPrimAtPath(self.root+'/'+suffix))
            for op in xf.GetOrderedXformOps():
                if op.GetOpType() == UsdGeom.XformOp.TypeTranslate:
                    op.Set((RAIL_ORIGIN[0], RAIL_ORIGIN[1], z))
        frozen = []
        for prim in stage.Traverse():
            path = str(prim.GetPath())
            if path.startswith((self.root+'/', '/World/PracticeAmr/')):
                continue
            if prim.HasAPI(UsdPhysics.RigidBodyAPI):
                UsdPhysics.RigidBodyAPI(prim).GetRigidBodyEnabledAttr().Set(False)
                frozen.append(path)
            if prim.IsA(UsdPhysics.Joint):
                UsdPhysics.Joint(prim).GetJointEnabledAttr().Set(False)
        self.emit('other_dynamics_disabled', paths=frozen)
        self.world = World(stage_units_in_meters=1., physics_dt=1/60, rendering_dt=1/60,
                           backend='numpy', device='cpu')
        ctx = self.world.get_physics_context()
        ctx.enable_gpu_dynamics(False)
        ctx.set_broadphase_type('MBP')
        ctx.set_solver_type('TGS')
        # Keep actual shelf meshes, including gaps between boards. No proxy supports.
        for number in range(67, 76):
            shelf = stage.GetPrimAtPath('/World/Environment/hospital/SM_MedShelf_01d_'+str(number))
            shelf.SetInstanceable(False)
            for prim in Usd.PrimRange(shelf):
                if prim.IsA(UsdGeom.Mesh):
                    UsdPhysics.CollisionAPI.Apply(prim)
                    UsdPhysics.MeshCollisionAPI.Apply(prim).CreateApproximationAttr('none')
        material = UsdShade.Material.Define(stage, '/World/PickTrialMaterial')
        friction = UsdPhysics.MaterialAPI.Apply(material.GetPrim())
        friction.CreateStaticFrictionAttr(1.)
        friction.CreateDynamicFrictionAttr(1.)
        friction.CreateRestitutionAttr(0.)
        self.objects = {}
        for number in range(67, 76):
            path = '/World/IntakeTrial/shelf_'+str(number)+'_pill'
            prim = stage.GetPrimAtPath(path)
            if not prim:
                raise ValueError('missing pill '+path)
            UsdPhysics.CollisionAPI.Apply(prim)
            PhysxSchema.PhysxCollisionAPI.Apply(prim).CreateContactOffsetAttr(.002)
            PhysxSchema.PhysxCollisionAPI(prim).CreateRestOffsetAttr(0.)
            UsdPhysics.RigidBodyAPI.Apply(prim)
            UsdPhysics.MassAPI.Apply(prim).CreateMassAttr(.05)
            UsdShade.MaterialBindingAPI.Apply(prim).Bind(material, UsdShade.Tokens.weakerThanDescendants, 'physics')
            body = self.world.scene.add(SingleRigidPrim(path, name='pill_'+str(number)))
            self.objects[number] = body
            PhysxSchema.PhysxContactReportAPI.Apply(prim).CreateThresholdAttr(0.)
        for prim in Usd.PrimRange(stage.GetPrimAtPath(self.robot_path)):
            if prim.GetName() in ('left_inner_finger', 'right_inner_finger'):
                UsdShade.MaterialBindingAPI.Apply(prim).Bind(
                    material, UsdShade.Tokens.strongerThanDescendants, 'physics')
        refill.override_drives(stage, self.robot_path, refill.DEFAULT_ARM_JOINTS,
                               refill.DEFAULT_DRIVE, False, 'trial_arm')
        refill.override_drives(stage, self.robot_path, ['finger_joint'],
                               refill.DEFAULT_GRIPPER_DRIVE, False, 'trial_gripper')
        self.robot = self.world.scene.add(SingleArticulation(self.root, name='trial_m0609'))
        self.amr = None
        if stage.GetPrimAtPath('/World/PracticeAmr'):
            self.amr = self.world.scene.add(SingleArticulation('/World/PracticeAmr', name='practice_amr'))
        self.base = SingleXFormPrim(self.robot_path+'/base_link', name='trial_base')
        self.flange = SingleXFormPrim(self.robot_path+'/link_6', name='trial_flange')
        self.lula = LulaKinematicsSolver(robot_description_path=str(description), urdf_path=str(urdf))
        self.subscribe_contacts()
        self.world.reset()
        self.arm_indices = np.array([self.robot.get_dof_index(n) for n in self.lula.get_joint_names()])
        self.rail_indices = np.array([self.robot.get_dof_index(n) for n in ('rail_x', 'rail_y', 'rail_z')])
        self.finger_index = np.array([self.robot.get_dof_index('finger_joint')])
        self.emit('physics_ready', dofs=self.robot.dof_names)
        # Initial rest pose only; all trial motion uses drives, never joint teleportation.
        self.command(self.rail_indices, [0., .20, .35])
        self.command(self.arm_indices, [0., 0., 1.57, 0., 1.57, 0.])
        self.command(self.finger_index, [0.])
        if self.amr:
            from .amr_base import ARM_JOINT_NAMES
            from isaacsim.core.utils.types import ArticulationAction
            idx = np.array([self.amr.get_dof_index(n) for n in ARM_JOINT_NAMES])
            self.amr.apply_action(ArticulationAction(joint_indices=idx,
                joint_positions=np.array([0., -1.288212, 1.319241, 0., 1.570788, 0.])))
        self.advance(180)
        self.world.pause()

    def emit(self, event, **data):
        entry = dict(step=self.step, sim_s=self.step/60, wall_s=time.monotonic()-self.wall_start,
                     phase=self.phase, item=self.item, event=event, **data)
        self.log.write(json.dumps(entry)+'\n')
        self.log.flush()
        if event not in ('sample', 'contact'):
            print('SHELF_PICK', json.dumps(entry), flush=True)

    def subscribe_contacts(self):
        from omni.physx import get_physx_simulation_interface
        from omni.physx.bindings._physx import ContactEventType
        from pxr import PhysicsSchemaTools
        wanted = (ContactEventType.CONTACT_FOUND, ContactEventType.CONTACT_PERSIST)

        def callback(headers, data):
            for header in headers:
                if header.type not in wanted:
                    continue
                a = str(PhysicsSchemaTools.intToSdfPath(header.collider0))
                b = str(PhysicsSchemaTools.intToSdfPath(header.collider1))
                points = [data[i] for i in range(header.contact_data_offset,
                                                header.contact_data_offset+header.num_contact_data)]
                if not points or min(float(p.separation) for p in points) > .001:
                    continue
                self.contacts.add((a, b))
                if self.step % 12 == 0:
                    self.emit('contact', a=a, b=b,
                              separation=min(float(p.separation) for p in points))
        self.contact_subscription = get_physx_simulation_interface().subscribe_contact_report_events(callback)

    def command(self, indices, values):
        from isaacsim.core.utils.types import ArticulationAction
        self.robot.apply_action(ArticulationAction(joint_indices=indices,
                                                   joint_positions=self.np.array(values, dtype=float)))

    def tcp(self):
        pos, quat = self.flange.get_world_pose()
        return self.np.array(self.refill.tcp_world(pos, quat, (0., 0., .19671)))

    def sample(self):
        pos = self.objects[self.item].get_world_pose()[0]
        path = '/World/IntakeTrial/shelf_'+str(self.item)+'_pill'
        other = [b if a.startswith(path) else a for a, b in self.contacts
                 if a.startswith(path) or b.startswith(path)]
        return {'position': pos.tolist(), 'tcp': self.tcp().tolist(),
                'tcp_distance': float(self.np.linalg.norm(pos-self.tcp())),
                'left_contact': any('/left_inner_finger/' in p for p in other),
                'right_contact': any('/right_inner_finger/' in p for p in other)}

    def advance(self, count):
        samples = []
        for _ in range(count):
            self.contacts.clear()
            self.world.step(render=True)
            self.step += 1
            if self.item is not None:
                sample = self.sample()
                samples.append(sample)
                if self.step % 6 == 0:
                    self.emit('sample', **sample)
        return samples

    def move_joints(self, indices, target, speed):
        current = self.robot.get_joint_positions()[indices].copy()
        target = self.np.array(target)
        frames = max(30, math.ceil(float(max(abs(target-current)))/speed*60))
        for frame in range(1, frames+1):
            self.command(indices, current+(target-current)*frame/frames)
            self.advance(1)
        self.advance(45)
        error = float(max(abs(self.robot.get_joint_positions()[indices]-target)))
        self.emit('joint_target', error=error, target=target.tolist())
        return error < .03

    def move_tcp(self, target, linear=True):
        target = self.np.array(target, dtype=float)
        start = self.tcp()
        frames = max(30, math.ceil(float(self.np.linalg.norm(target-start))/.08*60)) if linear else 1
        warm = self.robot.get_joint_positions()[self.arm_indices]
        for frame in range(1, frames+1):
            pos = start+(target-start)*frame/frames
            base_pos, base_quat = self.base.get_world_pose()
            self.lula.set_robot_base_pose(base_pos, base_quat)
            offset = self.refill.quat_rotate(self.quat, (0., 0., .19671))
            angles, ok = self.lula.compute_inverse_kinematics('link_6', pos-offset, self.quat, warm_start=warm)
            if not ok:
                self.emit('ik_failed', target=pos.tolist())
                return False
            if not linear:
                if not self.move_joints(self.arm_indices, angles, .45):
                    return False
            else:
                previous = self.robot.get_joint_positions()[self.arm_indices]
                self.command(self.arm_indices, previous+self.np.clip(angles-previous, -.015, .015))
                self.advance(1)
            warm = angles
        self.advance(30)
        error = float(self.np.linalg.norm(self.tcp()-target))
        self.emit('tcp_target', target=target.tolist(), error_m=error)
        return error < .015

    def set_camera(self, home):
        from pxr import Gf, UsdGeom
        from omni.kit.viewport.utility import get_active_viewport
        camera = UsdGeom.Camera.Define(self.stage, '/PickTrialCamera')
        camera.CreateFocalLengthAttr(18)
        camera.CreateHorizontalApertureAttr(24)
        matrix = Gf.Matrix4d().SetLookAt(
            Gf.Vec3d(float(home[0])-1.5, 8.9, 1.9),
            Gf.Vec3d(float(home[0]), 11.05, .95), Gf.Vec3d(0, 0, 1))
        xf = UsdGeom.Xformable(camera)
        xf.ClearXformOpOrder()
        xf.AddTransformOp().Set(matrix.GetInverse())
        get_active_viewport().camera_path = '/PickTrialCamera'

    def run(self):
        self.world.play()
        try:
            for number in self.selection:
                self.item = number
                home = self.objects[number].get_world_pose()[0].copy()
                self.phase = 'rail_to_shelf'
                self.set_camera(home)
                self.emit('attempt_started', home=home.tolist())
                result = {'shelf': number, 'pass': False, 'reason': None}
                rail = [home[0]+3.3, .20, .35]
                self.command(self.finger_index, [0.])
                ok = self.move_joints(self.rail_indices, rail, .5)
                approach = home.copy()
                approach[1] -= .30
                if ok:
                    self.phase = 'approach'
                    ok = self.move_tcp(approach, linear=False)
                if ok:
                    self.phase = 'enter_shelf'
                    ok = self.move_tcp(home)
                if ok:
                    self.phase = 'close'
                    self.command(self.finger_index, [.8])
                    self.advance(90)
                    initial_z = float(self.objects[number].get_world_pose()[0][2])
                    self.phase = 'lift'
                    raised = home.copy()
                    raised[2] += .08
                    ok = self.move_tcp(raised)
                    self.phase = 'hold'
                    samples = self.advance(60)
                    result.update(initial_z=initial_z, samples=samples,
                                  **{'pass': ok and lift_pass(samples, initial_z)})
                    result['reason'] = 'sustained_two_pad_lift' if result['pass'] else 'lift_or_contact_failed'
                    # Return the arm and release where it picked; never reposition the item.
                    self.phase = 'lower'
                    self.move_tcp(home)
                else:
                    result['reason'] = 'motion_target_unreached'
                self.command(self.finger_index, [0.])
                self.advance(60)
                self.phase = 'retract'
                self.move_tcp(approach)
                self.results.append(result)
                self.emit('attempt_result', **result)
                self.phase = 'park'
                self.move_joints(self.arm_indices, [0., 0., 1.57, 0., 1.57, 0.], .45)
            self.emit('trial_finished', passed=sum(r['pass'] for r in self.results), attempted=len(self.results))
        except Exception as error:
            self.emit('trial_error', error=repr(error))
            raise
        finally:
            self.world.pause()
            (self.output/'summary.json').write_text(json.dumps({
                'seed': self.seed, 'selection': self.selection, 'results': self.results,
                'attempted': len(self.results), 'passed': sum(r['pass'] for r in self.results),
                'mode': 'PHYSICS_FRICTION', 'amr_navigation': 'NOT RUN', 'intake_transfer': 'NOT RUN'}, indent=2))
            self.log.close()
