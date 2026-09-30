"""#484/#485 workcell layout and opt-in intake fixture, no ROS or physics play.

Shelf-to-port placement is a test fixture, NOT a robot pick/transport.
"""
from collections import defaultdict
import json
import math
from pathlib import Path
import time

from .inlet_capture import Intake, Port

DISPENSER_ORIGIN = (-8.78522324, 11.7254655, 0.)
RAIL_ORIGIN = (-3.30, 10.75, 0.)
RAIL_STROKE = 11.4
Y_LIMITS = (-.10, .33)
Z_LIMITS = (0., 1.10)


def build_layout(stage, dispenser_asset, robot_asset):
    from pxr import Gf, UsdGeom
    from . import layout, scene
    stage.SetEditTarget(stage.GetSessionLayer())
    old = stage.GetPrimAtPath('/World/machine')
    if old:
        old.SetActive(False)
    dispenser = UsdGeom.Xform.Define(stage, '/World/ReviewedDispenser')
    dispenser.GetPrim().GetReferences().AddReference(str(dispenser_asset))
    dispenser.AddTranslateOp().Set(Gf.Vec3d(*DISPENSER_ORIGIN))
    from .dispenser_reference import check_live_scene
    check_live_scene(Path(dispenser_asset), stage, '/World/ReviewedDispenser')
    armroot, robot, _ = scene.build_xy_rail_with_robot(
        stage, '/World/ReviewRailM0609', str(robot_asset), RAIL_ORIGIN, RAIL_STROKE,
        Y_LIMITS, .05, .25, [1e7, 1e5, 1e8], z_limits=Z_LIMITS)
    scene.ensure_link_visuals(stage, robot, ('base_link', 'link_1', 'link_2', 'link_3',
                                            'link_4', 'link_5', 'link_6'))
    for part in layout.rail_boxes(RAIL_ORIGIN, RAIL_STROKE, Y_LIMITS, .05, .25):
        shape = UsdGeom.Cube.Define(stage, armroot+'/Tracks/'+part.name)
        shape.CreateSizeAttr(1)
        shape.CreateDisplayColorAttr([Gf.Vec3f(*part.color)])
        xf = UsdGeom.Xformable(shape)
        xf.AddTranslateOp().Set(Gf.Vec3d(*part.center))
        xf.AddScaleOp().Set(Gf.Vec3f(*part.size))
    return armroot


def shelf_surface(stage, prim):
    """Area-weighted horizontal top faces; choose the real board nearest 0.9 m."""
    from pxr import Gf, Usd, UsdGeom
    levels = defaultdict(float)
    cache = UsdGeom.XformCache()
    for p in Usd.PrimRange(prim, Usd.TraverseInstanceProxies()):
        if not p.IsA(UsdGeom.Mesh):
            continue
        mesh = UsdGeom.Mesh(p)
        matrix = cache.GetLocalToWorldTransform(p)
        points = [matrix.Transform(Gf.Vec3d(v)) for v in mesh.GetPointsAttr().Get()]
        indices = mesh.GetFaceVertexIndicesAttr().Get()
        offset = 0
        for n in mesh.GetFaceVertexCountsAttr().Get():
            face = [points[i] for i in indices[offset:offset+n]]
            offset += n
            if n < 3:
                continue
            z = sum(v[2] for v in face)/n
            if .15 < z < 1.85 and max(v[2] for v in face)-min(v[2] for v in face) < .001:
                for j in range(1, n-1):
                    cross = Gf.Cross(face[j]-face[0], face[j+1]-face[0])
                    if cross[2] > 0:
                        levels[round(z, 3)] += cross[2]/2
    choices = [z for z, area in levels.items() if area > .08]
    if not choices:
        raise ValueError(f'No measured board surface: {prim.GetPath()}')
    bounds = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ['default', 'render']).ComputeWorldBound(
        prim).ComputeAlignedRange()
    return (bounds.GetMin()[0]+bounds.GetMax()[0])/2, bounds.GetMin()[1]+.16, min(
        choices, key=lambda z: abs(z-.9))


class IntakeDemo:
    """Deterministic fixture schedule, real rendered USD poses, explicit synthetic inputs."""

    def __init__(self, stage, output, schedule_fixture=True):
        from pxr import Gf, UsdGeom
        self.stage = stage
        self.output = Path(output)
        self.output.mkdir(parents=True, exist_ok=True)
        self.log = (self.output/'intake-events.jsonl').open('x', encoding='utf-8')
        self.started = time.monotonic()
        self.sequence = 0
        self.current = None
        self.finished = False
        self.subscription = None
        self.items = {}
        self.results = []
        from .dispenser_reference import check_hospital_dispenser
        anchors = check_hospital_dispenser(stage, '/World/ReviewedDispenser')['anchors_world']
        pill, module = anchors['PillOpening'], anchors['ModuleEntry']
        # Fixture centres stand half an item's height/depth outside the actual openings.
        self.models = {
            'pill': Intake(Port('pill', (pill[0], pill[1], pill[2]+.06), (0, 0, -1), (.023, .023, .03))),
            'module': Intake(Port('module', (module[0], module[1]-.05, module[2]),
                                 (0, 1, 0), (.008, .035, .008))),
        }
        for number in range(67, 76):
            shelf = stage.GetPrimAtPath('/World/Environment/hospital/SM_MedShelf_01d_'+str(number))
            if not shelf or not shelf.IsActive():
                raise ValueError(f'Missing active shelf {number}')
            x, y, z = shelf_surface(stage, shelf)
            for kind, dx, height in [('pill', -.17, .12), ('module', .17, .14)]:
                name = f'shelf_{number}_{kind}'
                path = '/World/IntakeTrial/'+name
                if kind == 'pill':
                    shape = UsdGeom.Cylinder.Define(stage, path)
                    shape.CreateRadiusAttr(.035)
                    shape.CreateHeightAttr(height)
                    shape.CreateAxisAttr('Z')
                else:
                    shape = UsdGeom.Cube.Define(stage, path)
                    shape.CreateSizeAttr(1)
                xf = UsdGeom.Xformable(shape)
                home = (x+dx, y, z+height/2+.002)
                move = xf.AddTranslateOp()
                move.Set(Gf.Vec3d(*home))
                turn = xf.AddRotateZOp()
                turn.Set(0.)
                if kind == 'module':
                    xf.AddScaleOp().Set(Gf.Vec3f(.06, .10, .14))
                shape.CreateDisplayColorAttr([Gf.Vec3f(*((.95, .72, .18) if kind == 'pill' else (.15, .65, .8)))])
                self.items[name] = {'kind': kind, 'home': home, 'move': move, 'turn': turn, 'shape': shape,
                                        'held': False, 'angle': 0., 'speed': 0.}
        self.cases = [('held', 'shelf_67_module'), ('misaligned', 'shelf_67_module'),
                      ('outside', 'shelf_67_pill'), ('wrong_kind', 'shelf_67_pill')]
        self.cases += [('normal', name) for name in self.items]
        if not schedule_fixture:
            self.cases = []
        self.emit('trial_ready', items=18, shelves=9, cases=len(self.cases),
                  mode='KINEMATIC_INTAKE_FIXTURE' if schedule_fixture else 'SHELF_DISPLAY',
                  robot_transport=False, physics=False)
        (self.output/'items.json').write_text(json.dumps(
            {n: {'kind': i['kind'], 'home': i['home']} for n, i in self.items.items()}, indent=2))

    def emit(self, event, **data):
        self.log.write(json.dumps(dict(seq=self.sequence, elapsed=time.monotonic()-self.started,
                                       event=event, **data))+'\n')
        self.sequence += 1
        self.log.flush()

    def tick(self, _event=None):
        from pxr import Gf, UsdGeom
        if self.finished:
            return
        now = time.monotonic()-self.started
        if now < 4:  # Show all shelf items before starting fixture cases.
            return
        if self.current is None:
            if not self.cases:
                self.finished = True
                self.emit('trial_finished', results=self.results)
                (self.output/'summary.json').write_text(json.dumps({
                    'mode': 'KINEMATIC_INTAKE_FIXTURE', 'results': self.results,
                    'passed': all(r['pass'] for r in self.results),
                    'physics': 'NOT RUN', 'robot_pick_and_transport': 'NOT RUN'}, indent=2))
                self.log.close()
                return
            case, name = self.cases.pop(0)
            item = self.items[name]
            port_kind = 'module' if case == 'wrong_kind' else item['kind']
            model = self.models[port_kind]
            point = list(model.port.center)
            if case == 'outside':
                point[0] += .10
            item.update(held=case == 'held', angle=math.pi/2 if case == 'misaligned' else 0.)
            item['move'].Set(Gf.Vec3d(*point))
            item['turn'].Set(math.degrees(item['angle']))
            UsdGeom.Imageable(item['shape']).MakeVisible()
            self.current = {'case': case, 'name': name, 'port': port_kind, 'start': now, 'reason': None,
                                'complete': False, 'began': False, 'last_pose': tuple(point), 'last_time': now}
            self.emit('fixture_placed', case=case, item=name, port=port_kind, position=point,
                      held=item['held'], angle=item['angle'], transport='test_fixture_not_robot')
        c = self.current
        item = self.items[c['name']]
        model = self.models[c['port']]
        if model.active:
            sample = model.advance(now)
            item['move'].Set(Gf.Vec3d(*sample['position']))
            self.emit('capture_pose', item=c['name'], position=sample['position'])
            if sample['complete']:
                c['complete'] = True
                UsdGeom.Imageable(item['shape']).MakeInvisible()
                self.emit('stored', item=c['name'], port=c['port'], stored_count=len(model.accepted))
        elif not c['complete']:
            pose = tuple(item['move'].Get())
            dt = now-c['last_time']
            speed = math.dist(pose, c['last_pose'])/dt if dt > 0 else 0.
            c['last_pose'], c['last_time'] = pose, now
            reason = model.offer(now, c['name'], item['kind'], pose, held=item['held'],
                                 angle=item['angle'], speed=speed)
            if reason != c['reason']:
                self.emit('gate', item=c['name'], case=c['case'], reason=reason,
                          speed=speed, held=item['held'], angle=item['angle'])
                c['reason'] = reason
            c['began'] |= reason == 'capture_started'
        duration = 2.1 if c['case'] == 'normal' else .8
        if now-c['start'] >= duration:
            passed = c['complete'] if c['case'] == 'normal' else (
                not c['began'] and c['reason'] == c['case'])
            result = dict(case=c['case'], item=c['name'], reason=c['reason'],
                          complete=c['complete'], **{'pass': passed})
            self.results.append(result)
            self.emit('case_result', **result)
            if not c['complete']:
                model.reset()
                item['move'].Set(Gf.Vec3d(*item['home']))
                item['turn'].Set(0.)
            self.current = None

    def subscribe(self):
        import omni.kit.app
        self.subscription = omni.kit.app.get_app().get_update_event_stream().create_subscription_to_pop(self.tick)
        return self


def build_practice_amr(stage, asset, origin_xy=None, log=print):
    """Reuse practice30/31's actual combined-asset assembly, including riser/tray.

    Keep the hospital base's XY placement; navigation and TF are not started.
    """
    from pxr import UsdGeom
    from . import amr_base, layout
    old = stage.GetPrimAtPath('/World/ridgeback_ur5')
    if origin_xy is None:
        base = stage.GetPrimAtPath('/World/ridgeback_ur5/base_link')
        if not base:
            raise ValueError('hospital AMR base missing; provide origin_xy explicitly')
        position = UsdGeom.XformCache().GetLocalToWorldTransform(base).ExtractTranslation()
        origin_xy = tuple(position[:2])
    root = '/World/PracticeAmr'
    if stage.GetPrimAtPath(root):
        raise ValueError('practice AMR already exists')
    result = amr_base.reference(stage, root, str(asset), origin_xy, log=log)
    moved, joint = amr_base.move_arm_mount(stage, root, log=log)
    if moved != 6 or joint is None:
        raise ValueError('combined asset does not match the practice arm hierarchy')
    amr_base.build_arm_base_frame(stage, root, log=log)
    slots, _tray, frames = amr_base.build_tray_on_base(stage, root, layout, log=log)
    if len(frames) != 3:
        raise ValueError('practice AMR requires three tray positions')
    if old:
        old.SetActive(False)
    return {'root': root, 'articulation': result[0], 'origin_xy': origin_xy,
            'arm_mount': amr_base.ARM_MOUNT_LOCAL, 'tray_slots': slots, 'frames': frames}
