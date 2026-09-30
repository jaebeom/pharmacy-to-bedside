"""Physical pouch probe for the hospital's existing conveyor graphs; no robot commands."""
import json
import math
from pathlib import Path

from .conveyor_end import receiver_status, terminal_status


#: 씬을 루트 스테이지로 열 때 컨베이어 루트. 참조로 불러오면(pharmacy_stage 의 /World/P3Base/Scene) 다른 경로다.
SCENE_CONVEYOR_ROOT = '/World/Conveyor'


class HospitalConveyorProbe:
    def __init__(self, stage, config_path, output, conveyor_root=SCENE_CONVEYOR_ROOT):
        import numpy as np
        from isaacsim.core.api import World
        from isaacsim.core.api.objects import DynamicCuboid
        from pxr import Usd, UsdGeom, UsdPhysics, PhysxSchema, Gf
        from . import scene

        self.config = json.loads(Path(config_path).read_text())
        # 설정의 경로는 씬을 루트로 연 기준(/World/Conveyor/...)이다. 참조 아래면 앞부분만 바꾼다.
        self.conveyor_root = conveyor_root.rstrip('/')
        prefix = SCENE_CONVEYOR_ROOT + '/'

        def moved(path):
            return self.conveyor_root + '/' + path[len(prefix):] if path.startswith(prefix) else path
        self.config['terminal_prim'] = moved(self.config['terminal_prim'])
        self.config['reroute'] = [moved(p) for p in self.config['reroute']]
        self.config['graph_velocities'] = {moved(k): v for k, v in self.config.get('graph_velocities', {}).items()}
        # 선택: 그래프 대신 트랙 대상에 표면 속도를 직접 쓴다({경로: {"linear": xyz, "angular": xyz}}).
        # 참조 아래에서 씬 그래프가 돌지 않을 때(9/23 참조 탐침 01) 씬을 루트로 연 회차의 관측값을 그대로 쓴다.
        self.config['surface_velocities'] = {moved(k): v for k, v in self.config.get('surface_velocities', {}).items()}
        self.direct = []
        root_prefix = self.conveyor_root + '/'
        self.output = Path(output)
        self.log = (self.output/'conveyor-observations.jsonl').open('x')
        self.stage = stage
        self.finished = False
        self.next_sample = 0.
        self.stop_time = None
        self.settled_since = None
        self.start = tuple(self.config['spawn'])
        self.end = tuple(self.config['end'])
        if (len(self.start) != 3 or len(self.end) != 3
                or not all(isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)
                           for x in (*self.start, *self.end))):
            raise ValueError('probe coordinates must be finite XYZ triples')
        terminal = stage.GetPrimAtPath(self.config['terminal_prim'])
        if not terminal or not str(terminal.GetPath()).startswith(root_prefix):
            raise ValueError('terminal must be a measured hospital conveyor surface')
        bounds = UsdGeom.BBoxCache(Usd.TimeCode.Default(), [UsdGeom.Tokens.default_, UsdGeom.Tokens.render,
                                                          UsdGeom.Tokens.proxy]).ComputeWorldBound(terminal)
        aligned = bounds.ComputeAlignedRange()
        self.surface = {'min': list(aligned.GetMin()), 'max': list(aligned.GetMax())}
        self.direction = self.config['terminal_direction']
        self.edge_margin = self.config['edge_margin_m']
        self.height_tolerance = self.config['height_tolerance_m']
        self.pouch_size = (.10, .07, .01)
        self.receiver_surface = None
        # Validate before changing the stage. The terminal must be a thin horizontal surface.
        if (not all(math.isfinite(v) for v in self.surface['min']+self.surface['max'])
                or not 0 < self.surface['max'][2]-self.surface['min'][2] < .05):
            raise ValueError('terminal bounds are not a thin horizontal roller surface')
        terminal_status(self.start, (1, 0, 0, 0), self.pouch_size, self.surface,
                        self.direction, self.edge_margin, self.height_tolerance)
        # Isolate belt transport. Robot joints and bodies remain visible and fixed.
        # This is explicitly not an M0609/AMR motion trial.
        for prim in list(stage.Traverse()):
            if prim.IsA(UsdPhysics.Joint):
                prim.SetActive(False)
            if prim.HasAPI(UsdPhysics.ArticulationRootAPI):
                prim.RemoveAPI(UsdPhysics.ArticulationRootAPI)
            if prim.HasAPI(UsdPhysics.RigidBodyAPI):
                UsdPhysics.RigidBodyAPI(prim).CreateRigidBodyEnabledAttr(False)
        self.velocities = []
        self.targets = []
        root = stage.GetPrimAtPath(self.conveyor_root)
        if not root:
            raise ValueError('missing hospital Conveyor root')
        for path, value in self.config.get('graph_velocities', {}).items():
            if not path.startswith(root_prefix) or not path.endswith('.graph:variable:Velocity'):
                raise ValueError('probe override must address a hospital conveyor velocity')
            if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value):
                raise ValueError('probe conveyor velocity must be finite')
            attr = stage.GetAttributeAtPath(path)
            if not attr:
                raise ValueError('missing conveyor velocity: '+path)
            attr.Set(float(value))
        for prim in Usd.PrimRange(root):
            velocity = prim.GetAttribute('graph:variable:Velocity')
            if velocity:
                self.velocities.append((velocity, velocity.Get()))
            if prim.GetAttribute('node:type').Get() != 'isaacsim.asset.gen.conveyor.IsaacConveyor':
                continue
            targets = prim.GetRelationship('inputs:conveyorPrim').GetTargets()
            if len(targets) != 1:
                raise ValueError('conveyor node must target exactly one body: '+str(prim.GetPath()))
            target = stage.GetPrimAtPath(targets[0])
            if not target:
                raise ValueError('missing conveyor body: '+str(targets[0]))
            body = UsdPhysics.RigidBodyAPI.Apply(target)
            body.CreateRigidBodyEnabledAttr(True)
            body.CreateKinematicEnabledAttr(True)
            surface = PhysxSchema.PhysxSurfaceVelocityAPI.Apply(target)
            surface.CreateSurfaceVelocityEnabledAttr(True)
            surface.CreateSurfaceVelocityAttr(Gf.Vec3f(0))
            self.targets.append(target)
        for path in self.config['reroute']:
            if not path.startswith(root_prefix):
                raise ValueError('probe route must address a hospital conveyor attribute')
            attr = stage.GetAttributeAtPath(path)
            if not attr or not isinstance(attr.Get(), bool):
                raise ValueError('missing sorter route attribute: '+path)
            attr.Set(True)
        # Sorter speed is an input constant instead of a graph variable.
        for prim in Usd.PrimRange(root):
            if prim.GetName() == 'SorterSpeed':
                attr = prim.GetAttribute('inputs:value')
                self.velocities.append((attr, attr.Get()))
        if not self.targets:
            raise ValueError('no hospital conveyor bodies discovered')
        for path, value in self.config['surface_velocities'].items():
            target = stage.GetPrimAtPath(path)
            if not target or target not in self.targets:
                raise ValueError('surface velocity must address a discovered conveyor body: '+path)
            linear = [float(v) for v in value.get('linear', (0, 0, 0))]
            angular = [float(v) for v in value.get('angular', (0, 0, 0))]
            if len(linear) != 3 or len(angular) != 3 or not all(math.isfinite(v) for v in linear+angular):
                raise ValueError('surface velocity must be finite xyz: '+path)
            self.direct.append((target, Gf.Vec3f(*linear), Gf.Vec3f(*angular)))
        if self.direct:
            # 그래프가 돌더라도 같은 몸체를 두 손이 쓰지 않게 그래프 속도는 0 으로 둔다.
            self.stop_belts()
            for target, linear, angular in self.direct:
                api = PhysxSchema.PhysxSurfaceVelocityAPI(target)
                api.CreateSurfaceVelocityAttr(linear)
                api.CreateSurfaceAngularVelocityAttr(angular)
        chute = None
        if self.config.get('outlet_chute'):
            from .outlet_chute import build_chute
            self.receiver_surface, chute = build_chute(stage, self.surface, self.config['outlet_chute'],
                                                      self.direction)
            (self.output/'outlet-chute.json').write_text(json.dumps(chute, indent=2)+'\n')
        self.world = World(stage_units_in_meters=1., physics_dt=1/60, rendering_dt=1/60)
        items = {}
        if self.config.get('inventory'):   # 진열 재현은 선택이다(참조 탐침은 컨베이어만 본다)
            inventory = json.loads(Path(self.config['inventory']).read_text())
            items = scene.build_canisters_v2('/World/Stock', inventory['cells'], .1)
            for path, _obj in items.values():
                UsdPhysics.RigidBodyAPI(stage.GetPrimAtPath(path)).CreateRigidBodyEnabledAttr(False)
        self.pouch = self.world.scene.add(DynamicCuboid(
            prim_path='/World/ConveyorProbe/Pouch', name='hospital_probe_pouch',
            position=np.array(self.start), scale=np.array(self.pouch_size), size=1.,
            mass=.02, color=np.array([.95, .3, .05])))
        self.world.reset()
        self.emit('ready', stock_count=len(items), conveyor_bodies=len(self.targets),
                  conveyor_root=self.conveyor_root, direct_surfaces=len(self.direct),
                  robot_motion=False, physics=True, mode='PHYSICAL_CONVEYOR_PROBE', config=self.config,
                  terminal_surface=self.surface, receiver_surface=self.receiver_surface, chute=chute)

    def stop_belts(self):
        """그래프 속도와(직접 모드면) 표면 속도를 모두 0 으로."""
        for attr, _value in self.velocities:
            attr.Set(0.)
        if not getattr(self, "direct", ()):   # 시험은 __init__ 없이 만든다
            return
        from pxr import Gf, PhysxSchema
        for target, _linear, _angular in self.direct:
            api = PhysxSchema.PhysxSurfaceVelocityAPI(target)
            api.GetSurfaceVelocityAttr().Set(Gf.Vec3f(0))
            api.GetSurfaceAngularVelocityAttr().Set(Gf.Vec3f(0))

    def emit(self, event, **values):
        row = dict(event=event, sim_s=self.world.current_time, **values)
        self.log.write(json.dumps(row)+'\n')
        self.log.flush()
        if event != 'sample':
            print('CONVEYOR_PROBE '+json.dumps(row), flush=True)

    def abort(self):
        """Preserve a non-success result if the application closes before the trial ends."""
        if self.finished:
            return
        self.stop_belts()
        result = {'reason': 'application_closed_before_terminal_result', 'success': False,
                  'elapsed_sim_s': self.world.current_time, 'robot_motion': False,
                  'production_arrival': False}
        self.emit('finished', **result)
        (self.output/'conveyor-result.json').write_text(json.dumps(result, indent=2)+'\n')
        self.finished = True

    def step(self):
        self.world.step(render=True)
        if self.finished:
            return
        now = self.world.current_time
        position, orientation = self.pouch.get_world_pose()
        velocity = self.pouch.get_linear_velocity()
        terminal = terminal_status(position, orientation, self.pouch_size, self.surface,
                                   self.direction, self.edge_margin, self.height_tolerance)
        receiver = (receiver_status(position, orientation, self.pouch_size, self.receiver_surface,
                                    self.height_tolerance) if self.receiver_surface else None)
        if now >= self.next_sample:
            self.emit('sample', position=position.tolist(), velocity=velocity.tolist(), terminal=terminal,
                      receiver=receiver,
                      surfaces={str(p.GetPath()): list(p.GetAttribute(
                          'physxSurfaceVelocity:surfaceVelocity').Get() or (0, 0, 0)) for p in self.targets},
                      angular_surfaces={str(p.GetPath()): list(p.GetAttribute(
                          'physxSurfaceVelocity:surfaceAngularVelocity').Get() or (0, 0, 0))
                          for p in self.targets})
            self.next_sample = now+.1
        reached = receiver['reached'] if receiver is not None else terminal['reached']
        if reached and self.stop_time is None:
            self.stop_belts()
            self.stop_time = now
            self.emit('receiver_surface' if receiver is not None else 'terminal_edge',
                      position=position.tolist(), terminal=terminal, receiver=receiver)
        completed_reason = 'receiver_settled' if receiver is not None else 'terminal_edge_settled'
        # A first arrival does not prove continuous support or rest. A pouch that
        # leaves the surface or keeps moving must start its settling interval again.
        stationary = math.sqrt(sum(v*v for v in velocity)) < .03
        if reached and stationary:
            if self.settled_since is None:
                self.settled_since = now
        else:
            self.settled_since = None
        reason = ('fell' if position[2] < -.05 else
                  'timeout' if now > 90 else
                  completed_reason if self.settled_since is not None and now-self.settled_since >= 1 else None)
        if reason:
            self.stop_belts()
            result = {'reason': reason, 'success': reason == completed_reason,
                      'position': position.tolist(), 'elapsed_sim_s': now, 'robot_motion': False,
                      'terminal': terminal, 'terminal_surface': self.surface, 'receiver': receiver,
                      'receiver_surface': self.receiver_surface, 'production_arrival': False}
            self.emit('finished', **result)
            (self.output/'conveyor-result.json').write_text(json.dumps(result, indent=2)+'\n')
            self.finished = True
